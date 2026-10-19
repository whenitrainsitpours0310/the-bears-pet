from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image, ImageOps

from bubble import HoverController, bubble_position
from detector import Match, atlas_frame, detect, idle_frame, make_templates
from quotes import QuoteDeck


HERE = Path(__file__).resolve().parent
PETS = HERE.parent


class BubbleTests(unittest.TestCase):
    def test_hover_enter_leave_and_round(self) -> None:
        deck = QuoteDeck(HERE / "quotes.json")
        hover = HoverController(deck, delay=0.3)
        match = Match("Dropout Bear", (20, 20, 150, 170), 0.01)
        seen = []
        for index in range(len(deck.quotes)):
            t = index * 2.0
            self.assertIsNone(hover.update(match, t))
            self.assertIsNone(hover.update(match, t + 0.2))
            state = hover.update(match, t + 0.4)
            self.assertIsNotNone(state)
            seen.append(state.quote["text"])
            self.assertEqual(state.quote, hover.update(match, t + 0.6).quote)
            self.assertIsNone(hover.update(None, t + 0.8))
        self.assertEqual(len(set(seen)), len(deck.quotes))

    def test_quote_changes_after_ten_seconds_of_hover(self) -> None:
        hover = HoverController(QuoteDeck(HERE / "quotes.json"), delay=0.3,
                                quote_seconds=10.0)
        match = Match("Graduation Bear", (20, 20, 150, 170), 0.01)
        self.assertIsNone(hover.update(match, 0.0))
        first = hover.update(match, 0.4)
        self.assertIsNotNone(first)
        self.assertEqual(first.quote, hover.update(match, 10.3).quote)
        second = hover.update(match, 10.5)
        self.assertNotEqual(first.quote, second.quote)
        self.assertEqual(second.quote, hover.update(match, 11.0).quote)

    def test_quote_corpus_is_sourced_and_unique(self) -> None:
        deck = QuoteDeck(HERE / "quotes.json")
        self.assertEqual(len(deck.quotes), 75)
        self.assertEqual(len({q["text"].casefold() for q in deck.quotes}), 75)
        self.assertTrue(all(q["url"].startswith("https://") for q in deck.quotes))

    def test_screen_edges_and_negative_monitor(self) -> None:
        screen = (-1920, 0, 0, 1080)
        for pet in [(-1910, 100, -1800, 250), (-120, 910, -10, 1050)]:
            x, y, left = bubble_position(pet, (306, 142), screen)
            self.assertGreaterEqual(x, screen[0])
            self.assertGreaterEqual(y, screen[1])
            self.assertLessEqual(x + 306, screen[2])
            self.assertLessEqual(y + 142, screen[3])
            if pet[0] == -120:
                self.assertTrue(left)

    def test_detect_three_bears_at_different_sizes(self) -> None:
        templates = make_templates(PETS, [round(i / 20, 2) for i in range(10, 31)])
        for name, scale in [
            ("Dropout Bear", 1.0),
            ("Late Registration Bear", 0.8),
            ("Graduation Bear", 0.9),
            ("Graduation Bear", 0.5),
        ]:
            with self.subTest(name=name, scale=scale):
                frame = idle_frame(PETS, name)
                frame = frame.resize((round(192 * scale), round(208 * scale)), Image.Resampling.NEAREST)
                screen = Image.new("RGB", (360, 360), "#eeeeee")
                screen.paste(frame, (90, 85), frame)
                found = detect(screen, (0, 0), (150, 140), templates)
                self.assertIsNotNone(found)
                self.assertEqual(found.name, name)
                self.assertIsNone(detect(screen, (0, 0), (10, 10), templates, previous=found))

    def test_graduation_running_animation_keeps_hover(self) -> None:
        templates = make_templates(PETS, [round(i / 20, 2) for i in range(10, 31)])
        previous = None
        for frame_index in range(6):
            frame = atlas_frame(PETS, "Graduation Bear", 7, frame_index)
            frame = frame.resize((202, 218), Image.Resampling.BILINEAR)
            screen = Image.new("RGB", (430, 430), "#111111")
            screen.paste(frame, (100, 90), frame)
            with self.subTest(frame=frame_index):
                found = detect(screen, (0, 0), (180, 170), templates, previous=previous)
                self.assertIsNotNone(found)
                self.assertEqual(found.name, "Graduation Bear")
                previous = found

        for row, frame_index in ((6, 3), (8, 4), (0, 0)):
            frame = atlas_frame(PETS, "Graduation Bear", row, frame_index)
            frame = frame.resize((202, 218), Image.Resampling.BILINEAR)
            screen = Image.new("RGB", (430, 430), "#111111")
            screen.paste(frame, (100, 90), frame)
            with self.subTest(row=row, frame=frame_index):
                found = detect(screen, (0, 0), (180, 170), templates, previous=previous)
                self.assertIsNotNone(found)
                previous = found

    def test_gray_shapes_do_not_impersonate_late_registration(self) -> None:
        templates = make_templates(PETS, [round(i / 20, 2) for i in range(10, 31)])
        frame = idle_frame(PETS, "Late Registration Bear")
        frame = frame.resize((96, 104), Image.Resampling.BILINEAR)
        gray = ImageOps.grayscale(frame).convert("RGBA")
        gray.putalpha(frame.getchannel("A"))
        screen = Image.new("RGB", (360, 360), "#2f2f2f")
        screen.paste(gray, (90, 85), gray)
        self.assertIsNone(detect(screen, (0, 0), (130, 130), templates))


if __name__ == "__main__":
    unittest.main()
