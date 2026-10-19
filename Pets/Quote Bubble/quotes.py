"""Load editable, sourced quotations and cycle without repeats per round."""

from __future__ import annotations

import json
import random
from pathlib import Path


class QuoteDeck:
    def __init__(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not data:
            raise ValueError("quotes.json must contain a nonempty list")
        self.quotes = [q for q in data if all(q.get(key) for key in ("text", "source", "url"))]
        if not self.quotes:
            raise ValueError("No valid quotations found")
        self._remaining: list[int] = []
        self._last: int | None = None

    def next(self) -> dict[str, str]:
        if not self._remaining:
            self._remaining = list(range(len(self.quotes)))
            random.shuffle(self._remaining)
            if len(self._remaining) > 1 and self._remaining[-1] == self._last:
                self._remaining[0], self._remaining[-1] = self._remaining[-1], self._remaining[0]
        index = self._remaining.pop()
        self._last = index
        return self.quotes[index]
