"""Quote hover state and screen-safe bubble placement."""

from __future__ import annotations

from dataclasses import dataclass

from detector import Match
from quotes import QuoteDeck


@dataclass(frozen=True)
class BubbleState:
    match: Match
    quote: dict[str, str]


class HoverController:
    def __init__(self, deck: QuoteDeck, delay: float = 0.35, quote_seconds: float = 10.0):
        self.deck = deck
        self.delay = delay
        self.quote_seconds = quote_seconds
        self._candidate: str | None = None
        self._since = 0.0
        self._quote_since = 0.0
        self._visible: BubbleState | None = None

    def update(self, match: Match | None, now: float) -> BubbleState | None:
        if match is None:
            self._candidate = None
            self._visible = None
            return None
        if match.name != self._candidate:
            self._candidate = match.name
            self._since = now
            self._visible = None
            return None
        if now - self._since < self.delay:
            return None
        if self._visible is None:
            self._visible = BubbleState(match, self.deck.next())
            self._quote_since = now
        else:
            quote = self._visible.quote
            if now - self._quote_since >= self.quote_seconds:
                quote = self.deck.next()
                self._quote_since = now
            self._visible = BubbleState(match, quote)
        return self._visible


def bubble_position(
    pet: tuple[int, int, int, int],
    bubble_size: tuple[int, int],
    screen: tuple[int, int, int, int],
) -> tuple[int, int, bool]:
    """Place beside the pet; return x, y, and whether the tail points right."""
    left, top, right, bottom = pet
    sw_left, sw_top, sw_right, sw_bottom = screen
    width, height = bubble_size
    gap = 12
    # Prefer the right side, including a little vertical overlap so the tail
    # visibly connects to the bear. Switch sides near the screen boundary.
    on_left = right + gap + width > sw_right and left - gap - width >= sw_left
    x = left - gap - width if on_left else right + gap
    x = max(sw_left, min(x, sw_right - width))
    y = top + (bottom - top - height) // 2
    y = max(sw_top, min(y, sw_bottom - height))
    return x, y, on_left
