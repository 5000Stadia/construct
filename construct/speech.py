"""UTTERANCE-NOT-FACT (docs/design/UTTERANCE-NOT-FACT.md r3, R42 first slice; ruleset IR-5).

`strip_speech` — the one deterministic scanner that separates what the player's character SAYS
(quoted spans) from the rest of the line, so a spoken claim never reaches factual extraction.
Pure; no model; no world.
"""
from __future__ import annotations

#: opener → its one partner. ASCII "'" is an opener only at a word boundary (see _opens).
_PAIRS = {'"': '"', "“": "”", "«": "»", "‘": "’", "'": "'"}
#: characters before which an ASCII "'" may open (start-of-line counts too)
_BOUNDARY_BEFORE = set(" \t\n(—–-:,;")
#: characters after which an ASCII "'" may close (end-of-line counts too)
_CLOSE_AFTER = set(" \t\n.,;:!?)—–-\"”»")


def _opens(text: str, i: int) -> bool:
    ch = text[i]
    if ch not in _PAIRS:
        return False
    if ch != "'":
        return True
    before_ok = i == 0 or text[i - 1] in _BOUNDARY_BEFORE
    after_ok = i + 1 < len(text) and not text[i + 1].isspace()
    return before_ok and after_ok          # so `don't` / `Quincy's` never open


def _closes(text: str, i: int, opener: str) -> bool:
    if text[i] != _PAIRS[opener]:
        return False
    if opener != "'":
        return True
    return i + 1 >= len(text) or text[i + 1] in _CLOSE_AFTER


def strip_speech(text: str) -> tuple[str, list[str]]:
    """(the line without its spoken spans, the spans' inner text in order).

    Left to right: an opener starts a span that closes only on ITS partner; the outermost span
    wins (inner quotes are part of it); an UNMATCHED opener strips to the end of the line —
    fail closed, the rest is treated as speech."""
    out: list[str] = []
    spans: list[str] = []
    i, n = 0, len(text or "")
    text = text or ""
    while i < n:
        if _opens(text, i):
            opener = text[i]
            j = i + 1
            while j < n and not _closes(text, j, opener):
                j += 1
            spans.append(text[i + 1:j].strip())
            i = j + 1                       # past the closer (or past the end when unmatched)
            out.append(" ")
            continue
        out.append(text[i])
        i += 1
    rest = " ".join("".join(out).split())
    return rest, [s for s in spans if s]
