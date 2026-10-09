"""The transport-neutral event types and the reply chunker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class InboundEvent:
    """A transport-neutral inbound message. `update_ids` are the source
    update ids this event covers (one normally; several when an adapter
    coalesces a burst) — the adapter uses them for exactly-once bookkeeping."""

    platform: str
    external_id: str
    chat_id: str
    text: str
    update_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Outbound:
    chat_id: str
    chunks: list[str] = field(default_factory=list)
    image: str | None = None  # SCENE-IMAGERY: a location image to show BEFORE the text
                              # (set ONLY on a scene change — see _scene_image)


def chunk(text: str, limit: int,
          length: Callable[[str], int] = len) -> list[str]:
    """Split `text` into ≤`limit` pieces, never silently truncating (the
    Kernos-bot lesson). Prefers a newline boundary, then a hard cut. Always
    returns ≥1 chunk (empty text → one empty string, so a turn always
    answers).

    `length` measures a string against `limit` (default `len`, code points).
    A transport whose limit counts something else passes its own measure — e.g.
    Telegram counts UTF-16 code units. Cuts are always on code-point boundaries,
    so a surrogate pair (any astral character) is never split."""
    text = text or ""
    if length(text) <= limit:
        return [text]
    chunks: list[str] = []
    while length(text) > limit:
        fit = limit if length is len else _longest_fit(text, limit, length)
        cut = text.rfind("\n", 0, fit)
        if cut <= 0:
            cut = fit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks or [""]


def _longest_fit(text: str, limit: int, length: Callable[[str], int]) -> int:
    """Largest prefix size k (in code points, ≥1) with length(text[:k]) ≤ limit.
    `length` must be monotonic in the prefix. ≥1 so a limit smaller than one
    character still makes progress."""
    lo, hi = 1, min(len(text), limit)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if length(text[:mid]) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return lo
