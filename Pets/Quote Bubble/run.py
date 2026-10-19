"""Show Kanye quote bubbles beside the ChatGPT desktop pet on Windows.

Run: python "Pets/Quote Bubble/run.py" --show-pet
Stop: python "Pets/Quote Bubble/run.py" --stop
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PIL import ImageGrab

from bubble import HoverController, bubble_position
from detector import Match, detect, make_templates
from quotes import QuoteDeck


ROOT = Path(__file__).resolve().parent
PET_ROOT = ROOT.parent
POLL_MS = 240
SEARCH_RADIUS = 215
MATCH_GRACE_SECONDS = 1.2
CURSOR_JITTER_PIXELS = 8
SCALES = tuple(round(i / 20, 2) for i in range(10, 31))  # 0.50 through 1.50
TRANSPARENT = "#010203"
MUTEX_NAME = "Local\\KanyeQuoteBubble"
STOP_FILE = ROOT / ".stop"
HEARTBEAT_FILE = ROOT / ".heartbeat"

THEMES = {
    "Dropout Bear": {"name": "THE COLLEGE DROPOUT", "bg": "#4B211C", "edge": "#F2A93B", "text": "#FFF1D2", "accent": "#CD2D46"},
    "Late Registration Bear": {"name": "LATE REGISTRATION", "bg": "#311B25", "edge": "#B88955", "text": "#F7E9D3", "accent": "#8E4A5D"},
    "Graduation Bear": {"name": "GRADUATION", "bg": "#251C55", "edge": "#F5BE51", "text": "#F7F0FF", "accent": "#D556B5"},
}


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]


def desktop_bounds() -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    return x, y, x + user32.GetSystemMetrics(78), y + user32.GetSystemMetrics(79)


def monitor_bounds(x: int, y: int) -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.argtypes = [POINT, ctypes.c_ulong]
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = ctypes.c_int
    monitor = user32.MonitorFromPoint(POINT(x, y), 2)  # nearest monitor
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        r = info.rcMonitor
        return r.left, r.top, r.right, r.bottom
    return desktop_bounds()


def cursor_position() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise OSError("GetCursorPos failed")
    return point.x, point.y


def acquire_single_instance() -> tuple[object, bool]:
    """Keep the mutex handle alive for the lifetime of the process."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, 0, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle, ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def show_desktop_pet() -> None:
    """Send the documented default Windows Show pet shortcut."""
    user32 = ctypes.windll.user32
    user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte,
                                  ctypes.c_ulong, ctypes.c_size_t]
    user32.keybd_event.restype = None
    for key in (0x5B, 0x12, 0x50):  # Win, Alt, P
        user32.keybd_event(key, 0, 0, 0)
    for key in (0x50, 0x12, 0x5B):
        user32.keybd_event(key, 0, 2, 0)  # KEYEVENTF_KEYUP


def outer_hwnd(window: tk.Tk) -> int:
    window.update_idletasks()
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    # Tk's winfo_id is the client child; styles and position belong to its wrapper.
    return user32.GetParent(window.winfo_id()) or window.winfo_id()


def make_click_through(window: tk.Tk) -> None:
    user32 = ctypes.windll.user32
    hwnd = outer_hwnd(window)
    get_style = user32.GetWindowLongPtrW
    set_style = user32.SetWindowLongPtrW
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    ex_style = get_style(hwnd, -20)  # GWL_EXSTYLE
    set_style(hwnd, -20, ex_style | 0x20 | 0x80000 | 0x80)  # TRANSPARENT, LAYERED, TOOLWINDOW


def place_window(window: tk.Tk, x: int, y: int, width: int, height: int) -> None:
    """Use virtual-desktop coordinates, including monitors left of the primary."""
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos.restype = ctypes.c_int
    if not user32.SetWindowPos(outer_hwnd(window), None, x, y, width, height,
                                0x0004 | 0x0010):  # SWP_NOZORDER | SWP_NOACTIVATE
        raise ctypes.WinError()


class BubbleWindow:
    WIDTH = 306
    MIN_HEIGHT = 142

    def __init__(self):
        self.window = tk.Tk()
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.wm_attributes("-transparentcolor", TRANSPARENT)
        self.canvas = tk.Canvas(self.window, width=self.WIDTH, height=self.MIN_HEIGHT,
                                bg=TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.window.update_idletasks()
        make_click_through(self.window)
        self._shown = False
        self._content: tuple[str, str, str, bool] | None = None
        self._height = self.MIN_HEIGHT

    def hide(self) -> None:
        if self._shown:
            self.window.withdraw()
            self._shown = False

    def show(self, match: Match, quote: dict[str, str], screen: tuple[int, int, int, int]) -> None:
        _, _, tail_right = bubble_position(match.box, (self.WIDTH, self._height), screen)
        theme = THEMES[match.name]
        content = (match.name, quote["text"], quote["source"], tail_right)
        if content != self._content:
            self._height = self._draw(theme, quote, tail_right)
            self._content = content
        x, y, _ = bubble_position(match.box, (self.WIDTH, self._height), screen)
        if not self._shown:
            self.window.deiconify()
            self.window.lift()
            self._shown = True
        place_window(self.window, x, y, self.WIDTH, self._height)

    def _draw(self, theme: dict[str, str], quote: dict[str, str], tail_right: bool) -> int:
        c = self.canvas
        c.delete("all")
        c.create_rectangle(21, 17, 25, 21, fill=theme["accent"], outline="")
        c.create_text(32, 20, text=theme["name"], anchor="w", fill=theme["edge"],
                      font=("Consolas", 9, "bold"))
        body = c.create_text(22, 40, text=quote["text"], anchor="nw", width=254,
                             fill=theme["text"], font=("Consolas", 12, "bold"),
                             tags="quote-text")
        divider_y = max(104, c.bbox(body)[3] + 10)
        c.create_line(21, divider_y, 270, divider_y, fill=theme["accent"], width=2)
        source = c.create_text(22, divider_y + 9, text=quote["source"], anchor="nw",
                               width=254, fill=theme["edge"], font=("Consolas", 8),
                               tags="quote-source")
        height = max(self.MIN_HEIGHT, c.bbox(source)[3] + 14)
        c.configure(height=height)
        # Draw the stepped silhouette behind measured text, so longer quotes
        # expand the bubble instead of covering the attribution.
        l, r = (9, 296) if tail_right else (10, 287)
        bottom = height - 12
        c.create_polygon(l+8, 4, r-8, 4, r-8, 10, r, 10, r, bottom-6,
                         r-8, bottom-6, r-8, bottom, l+8, bottom,
                         l+8, bottom-6, l, bottom-6, l, 10, l+8, 10,
                         fill=theme["bg"], outline=theme["edge"], width=3,
                         tags="background")
        middle = height // 2
        if tail_right:
            c.create_polygon(287, middle-9, 304, middle, 287, middle+9,
                             fill=theme["bg"], outline=theme["edge"], width=3,
                             tags="background")
            c.create_line(287, middle-8, 287, middle+8,
                          fill=theme["bg"], width=4, tags="background")
        else:
            c.create_polygon(10, middle-9, 0, middle, 10, middle+9,
                             fill=theme["bg"], outline=theme["edge"], width=3,
                             tags="background")
            c.create_line(10, middle-8, 10, middle+8,
                          fill=theme["bg"], width=4, tags="background")
        c.tag_lower("background")
        return height


def main() -> None:
    parser = argparse.ArgumentParser(description="Kanye quote bubbles for ChatGPT desktop pets")
    parser.add_argument("--show-pet", action="store_true",
                        help="also summon the pet using the default Win+Alt+P shortcut")
    parser.add_argument("--stop", action="store_true", help="stop the running bubble")
    parser.add_argument("--status", action="store_true", help="check whether the bubble is running")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This overlay requires Windows.")
    if args.stop:
        STOP_FILE.write_text("stop", encoding="utf-8")
        print("Stop requested. The quote bubble will close shortly.")
        return
    if args.status:
        try:
            age = time.time() - float(HEARTBEAT_FILE.read_text(encoding="ascii"))
        except (FileNotFoundError, ValueError):
            age = float("inf")
        if 0 <= age < 10:
            print("Quote bubble is running.")
            return
        raise SystemExit("Quote bubble is not running.")
    mutex, already_running = acquire_single_instance()
    if already_running:
        if args.show_pet:
            show_desktop_pet()
        print("Quote bubble is already running.")
        return
    STOP_FILE.unlink(missing_ok=True)
    # Make screen capture and window coordinates use physical pixels on mixed-DPI monitors.
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()
    templates = make_templates(PET_ROOT, SCALES)
    if not templates:
        raise SystemExit("No bear frames found under Pets.")
    controller = HoverController(QuoteDeck(ROOT / "quotes.json"))
    bubble = BubbleWindow()
    detector_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bear-detector")
    pending: Future[Match | None] | None = None
    pending_cursor: tuple[int, int] | None = None
    previous: Match | None = None
    last_cursor: tuple[int, int] | None = None
    last_seen = 0.0
    still_since = time.monotonic()
    next_search = 0.0
    next_heartbeat = 0.0
    if args.show_pet:
        show_desktop_pet()
    print("Quote bubble running. Move the pointer over a ChatGPT bear; press Ctrl+C here to stop.", flush=True)

    def tick() -> None:
        nonlocal pending, pending_cursor, previous, last_cursor, last_seen
        nonlocal still_since, next_search, next_heartbeat
        if STOP_FILE.exists():
            bubble.window.destroy()
            return
        try:
            cursor = cursor_position()
            now = time.monotonic()
            if now >= next_heartbeat:
                HEARTBEAT_FILE.write_text(str(time.time()), encoding="ascii")
                next_heartbeat = now + 3.0
            if pending is not None and pending.done():
                result = pending.result()
                capture_cursor = pending_cursor
                pending = None
                pending_cursor = None
                # A completed search belongs to the screenshot taken at its
                # original cursor position. Ignore it after the pointer leaves.
                if capture_cursor is not None and (cursor[0] - capture_cursor[0]) ** 2 + (cursor[1] - capture_cursor[1]) ** 2 <= CURSOR_JITTER_PIXELS ** 2:
                    if result is not None:
                        previous = result
                        last_seen = now
                        state = controller.update(result, now)
                    elif previous is not None and now - last_seen < MATCH_GRACE_SECONDS and previous.box[0] <= cursor[0] < previous.box[2] and previous.box[1] <= cursor[1] < previous.box[3]:
                        state = controller.update(previous, now)
                    else:
                        previous = None
                        next_search = now + 3.0
                        state = controller.update(None, now)
                    if state is None:
                        bubble.hide()
                    else:
                        l, t, r, b = state.match.box
                        bubble.show(state.match, state.quote, monitor_bounds((l+r)//2, (t+b)//2))
            if previous is not None and now - last_seen >= MATCH_GRACE_SECONDS:
                previous = None
                controller.update(None, now)
                bubble.hide()
            inside_previous = (previous is not None
                               and previous.box[0] <= cursor[0] < previous.box[2]
                               and previous.box[1] <= cursor[1] < previous.box[3])
            moved_far = (last_cursor is None or
                         (cursor[0] - last_cursor[0]) ** 2
                         + (cursor[1] - last_cursor[1]) ** 2
                         > CURSOR_JITTER_PIXELS ** 2)
            if moved_far and not inside_previous:
                last_cursor = cursor
                still_since = now
                next_search = 0.0
                previous = None
                last_seen = 0.0
                controller.update(None, now)
                bubble.hide()
                bubble.window.after(POLL_MS, tick)
                return
            if inside_previous:
                last_cursor = cursor
            # A hover requires a still pointer. Avoid expensive whole-crop
            # searches while the pointer moves or rests away from a pet.
            if pending is not None or now - still_since < 0.35 or now < next_search:
                bubble.window.after(POLL_MS, tick)
                return
            bounds = desktop_bounds()
            x, y = cursor
            crop = (max(bounds[0], x-SEARCH_RADIUS), max(bounds[1], y-SEARCH_RADIUS),
                    min(bounds[2], x+SEARCH_RADIUS), min(bounds[3], y+SEARCH_RADIUS))
            screenshot = ImageGrab.grab(bbox=crop, all_screens=True)
            pending_cursor = cursor
            pending = detector_pool.submit(detect, screenshot, crop[:2], cursor,
                                           templates, previous=previous)
        except Exception as exc:
            # Keep an in-flight worker registered so capture errors cannot
            # queue unbounded searches behind it.
            pending_cursor = None
            previous = None
            next_search = time.monotonic() + 3.0
            bubble.hide()
            print(f"Quote bubble capture error: {exc}", file=sys.stderr, flush=True)
        bubble.window.after(POLL_MS, tick)

    bubble.window.after(0, tick)
    try:
        bubble.window.mainloop()
    finally:
        detector_pool.shutdown(wait=False, cancel_futures=True)
        HEARTBEAT_FILE.unlink(missing_ok=True)
        STOP_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
