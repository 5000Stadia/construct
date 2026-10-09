"""Build-progress humanizing: raw build stage lines to warm `[k/N]` pings."""

from __future__ import annotations


#: Raw build stage line (substring) → the warm, player-facing progress line we
#: stream during a build. Lines with no mapping are internal and stay silent
#: (the per-chunk "extracted" lines are collapsed into one rolling counter).
_STAGE_LINES = (
    ("Authoring the hidden source story", "· Authoring the source story…"),
    ("Ingesting prose", "· Ingesting it into the pattern-buffer…"),
    ("Reconciling identity", "· Reconciling identities (coreference)…"),
    ("Declaring passability", "· Recording how the places connect…"),
    ("Authoring the hidden arc", "· Weaving the hidden arc into a private frame…"),
    ("Seeding character knowledge", "· Seeding each character's knowledge frame…"),
    ("thematic introduction", "· Composing your way in…"),
    ("back-of-the-book premise", "· Composing your way in…"),
    # The build's LONGEST stage (~most of the wall-clock — hundreds of serial classify calls):
    # surface it so the player isn't left staring at one line through the silent bottleneck.
    ("Classifying durability", "· Classifying what's durable vs. fleeting…"),
    ("Distilling narrative flavor", "· Distilling tone & texture…"),
    ("Sealing the scenario", "· Sealing the world snapshot…"),
    ("Viability gate", "· Final checks before the doors open…"),
)


def _humanize_stage(msg: str) -> str | None:
    """Turn a raw `game._emit` stage line into a warm progress ping, or None to
    stay silent (internal steps / noise). The per-chunk extraction lines all
    collapse to ONE populating phase (so they don't spam, and so the overall
    counter advances by phase, not by chunk)."""
    import re
    text = (msg or "").strip()
    if re.search(r"chunk (\d+)/(\d+) extracted", text):
        return "· Entering people, places & things into the pattern-buffer…"
    for needle, line in _STAGE_LINES:
        if needle in text:
            return line
    return None


#: How many distinct phases the full build streams — the overall `[k/N]`
#: denominator. Numbering is by first appearance (robust to emission order), and
#: not every build hits all of them, so the bar may finish a step or two short.
_BUILD_STEP_TOTAL = len({line for _, line in _STAGE_LINES})


class _StageProgress:
    """Per-build OVERALL-completion numbering. Each DISTINCT humanized phase
    advances a `[k/N]` counter shown on every progress line, so the player sees
    progress toward the whole build rather than a phase-local fraction (founder).
    A repeated phase — chiefly the populating chunks, which collapse to one line —
    is shown once and never re-advances or re-emits."""

    def __init__(self, total: int = _BUILD_STEP_TOTAL) -> None:
        self._total = max(total, 1)
        self._seen: set[str] = set()
        self._step = 0

    def line(self, msg: str) -> str | None:
        base = _humanize_stage(msg)
        if not base or base in self._seen:
            return None  # internal/noise, or a phase already shown (no spam)
        self._seen.add(base)
        self._step = min(self._step + 1, self._total)
        body = base[2:] if base.startswith("· ") else base
        return f"· [{self._step}/{self._total}] {body}"
