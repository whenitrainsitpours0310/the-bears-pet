"""Locate one of the three bear sprites near the mouse on a Windows screen."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


FINAL_ATLASES = {
    "Dropout Bear": "qa/look/spritesheet-v2-v3-clean.png",
    "Graduation Bear": "qa/extended-atlas-final.png",
    "Late Registration Bear": "qa/spritesheet-extended-v4.png",
}
CELL_SIZE = (192, 208)


def atlas_frame(pet_root: Path, name: str, row: int, frame: int) -> Image.Image:
    """Read a cell from the exact atlas uploaded to Pets."""
    with Image.open(pet_root / name / FINAL_ATLASES[name]) as atlas:
        left, top = frame * CELL_SIZE[0], row * CELL_SIZE[1]
        return atlas.crop((left, top, left + CELL_SIZE[0], top + CELL_SIZE[1])).convert("RGBA")


def idle_frame(pet_root: Path, name: str) -> Image.Image:
    return atlas_frame(pet_root, name, 0, 0)


@dataclass(frozen=True)
class Match:
    name: str
    box: tuple[int, int, int, int]
    error: float
    scale: float | None = None


@dataclass(frozen=True)
class Template:
    name: str
    rgb: np.ndarray
    mask: np.ndarray
    half_rgb: np.ndarray
    half_mask: np.ndarray
    scale: float = 1.0
    initial: bool = True

    @property
    def size(self) -> tuple[int, int]:
        return self.rgb.shape[1], self.rgb.shape[0]


def make_templates(pet_root: Path, scales: Iterable[float]) -> list[Template]:
    templates: list[Template] = []
    for name in ("Dropout Bear", "Late Registration Bear", "Graduation Bear"):
        if not (pet_root / name / FINAL_ATLASES[name]).exists():
            continue
        # The desktop pet switches to row 7 while a chat is running. Graduation's
        # flying poses differ enough from idle that an idle-only detector misses it.
        frames = [(0, 0, True)]
        if name == "Graduation Bear":
            frames.extend((7, frame, True) for frame in range(6))
            # Waiting and review appear when a chat changes status. Search
            # their first frames on entry; track every frame once found.
            frames.extend((row, frame, frame == 0)
                          for row in (6, 8) for frame in range(6))
        for row, frame, initial in frames:
            image = atlas_frame(pet_root, name, row, frame)
            for scale in scales:
            # Resize the entire atlas cell before cropping. Cropping first
            # changes the sampling phase and damages small-scale matches.
                target_w = max(24, round(image.width * scale))
                target_h = max(24, round(image.height * scale))
                # The desktop renderer interpolates at non-integer pet sizes.
                resized = image.resize((target_w, target_h), Image.Resampling.BILINEAR)
                alpha = np.asarray(resized.getchannel("A"))
                ys, xs = np.where(alpha > 200)
                if len(xs) == 0:
                    continue
                resized = resized.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
                pixels = np.asarray(resized, dtype=np.uint8)
                mask = pixels[:, :, 3] >= 230
                if mask.sum() < 150:
                    continue
                templates.append(Template(name, pixels[:, :, :3].copy(), mask,
                                          pixels[::3, ::3, :3].copy(), mask[::3, ::3].copy(),
                                          scale, initial))
    return templates


def _correlate_valid(scene: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """FFT correlation with the same valid-window convention as matchTemplate."""
    sh, sw = scene.shape
    kh, kw = kernel.shape
    shape = (sh + kh - 1, sw + kw - 1)
    spectrum = np.fft.rfftn(scene, s=shape, axes=(0, 1))
    response = np.fft.irfftn(
        spectrum * np.fft.rfftn(kernel[::-1, ::-1], s=shape, axes=(0, 1)),
        s=shape, axes=(0, 1),
    )
    return response[kh - 1 : sh, kw - 1 : sw]


def _best_for_template(
    scene_rgb: np.ndarray, template: Template, scene_gray: np.ndarray
) -> tuple[int, int, float] | None:
    th, tw = template.rgb.shape[:2]
    sh, sw = scene_rgb.shape[:2]
    if th > sh or tw > sw:
        return None
    # The grayscale pass searches the whole crop. The final RGB check rejects
    # similarly shaped icons that do not have this bear's palette.
    template_gray = np.dot(template.rgb.astype(np.float32), (0.299, 0.587, 0.114))
    mask = template.mask.astype(np.float32)
    sum_mask = float(mask.sum())
    scene_sq = _correlate_valid(scene_gray * scene_gray, mask)
    cross = _correlate_valid(scene_gray, template_gray * mask)
    constant = float(np.sum(template_gray * template_gray * mask))
    errors = np.maximum(0.0, scene_sq - 2.0 * cross + constant) / (sum_mask * 255.0 * 255.0)
    candidates = np.argpartition(errors.ravel(), min(4, errors.size - 1))[:5]
    best: tuple[int, int, float] | None = None
    for index in candidates:
        y, x = np.unravel_index(index, errors.shape)
        patch = scene_rgb[y : y + th, x : x + tw].astype(np.int16)
        target = template.rgb.astype(np.int16)
        target_saturation = target.max(axis=2) - target.min(axis=2)
        accent = template.mask & (target_saturation > 60) & (target.max(axis=2) > 100)
        if accent.sum() >= 100:
            scene_saturation = patch.max(axis=2) - patch.min(axis=2)
            if np.mean(scene_saturation[accent] > 40) < 0.25:
                # Gray input fields and text can resemble the dark door
                # silhouette, but they cannot reproduce the bear's colors.
                continue
        color_error = float(np.mean(np.abs(patch[template.mask] - target[template.mask]))) / 255.0
        if best is None or color_error < best[2]:
            best = int(x), int(y), color_error
    return best


def detect(
    screen: Image.Image,
    screen_origin: tuple[int, int],
    cursor: tuple[int, int],
    templates: list[Template],
    *,
    max_error: float = 0.18,
    previous: Match | None = None,
) -> Match | None:
    """Return a bear only when the cursor touches its matched visible pixels."""
    pixels = np.asarray(screen.convert("RGB"), dtype=np.uint8)
    gray = np.dot(pixels.astype(np.float32), (0.299, 0.587, 0.114))
    ox, oy = screen_origin
    if previous is not None:
        # Keep every animation frame at the known scale. Selecting only the
        # closest-sized frames dropped Graduation as soon as its pose changed.
        if previous.scale is not None:
            ordered = [t for t in templates if t.name == previous.name
                       and t.scale == previous.scale]
        else:
            previous_height = previous.box[3] - previous.box[1]
            ordered = sorted((t for t in templates if t.name == previous.name),
                             key=lambda t: abs(t.size[1] - previous_height))[:7]
        found = _detect_ordered(pixels, gray, (ox, oy), cursor, ordered, max_error)
        if found is not None:
            return found
        return None

    # Search a one-third-resolution image first, then verify the most promising
    # sizes at full resolution. This allows fine size increments without a
    # full-size FFT for every template.
    half = pixels[::3, ::3]
    half_gray = gray[::3, ::3]
    ranked: list[tuple[float, Template]] = []
    for template in (t for t in templates if t.initial):
        small = Template(template.name, template.half_rgb, template.half_mask,
                         template.half_rgb, template.half_mask, template.scale,
                         template.initial)
        result = _best_for_template(half, small, half_gray)
        if result is not None:
            ranked.append((result[2], template))
    ranked.sort(key=lambda item: item[0])
    return _detect_ordered(pixels, gray, (ox, oy), cursor,
                           [item[1] for item in ranked[:8]], max_error)


def _detect_ordered(
    pixels: np.ndarray,
    gray: np.ndarray,
    origin: tuple[int, int],
    cursor: tuple[int, int],
    templates: list[Template],
    max_error: float,
) -> Match | None:
    ox, oy = origin
    best: Match | None = None
    for template in templates:
        result = _best_for_template(pixels, template, gray)
        if result is None:
            continue
        x, y, error = result
        if error > max_error:
            continue
        local_x = cursor[0] - ox - x
        local_y = cursor[1] - oy - y
        width, height = template.size
        if not (0 <= local_x < width and 0 <= local_y < height):
            continue
        # A pet's moving hands, feet and rings may occupy pixels that are
        # transparent in this particular animation frame. Use its full bounds
        # for hover after the image itself has passed the color match.
        candidate = Match(template.name, (ox + x, oy + y, ox + x + width, oy + y + height),
                          error, template.scale)
        if best is None or candidate.error < best.error:
            best = candidate
    return best
