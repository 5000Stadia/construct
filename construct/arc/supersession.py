"""Beat supersession: the reads-backed overlay that replaces repaired beats.

Owns the supersession-chain walk (`resolve_beat_id`) and the arc's LIVE beat set
(`active_beats`, DRIFT-HANDLING.md §3 R4) — the sealed beats with superseded ones
swapped for their repair replacements. Everything that must see the live beats
(conclusion, concealment, the commit passes, drift) reads them through here so the
chain rule has one home. Re-exported by `construct.arc.executor`.
"""

from __future__ import annotations

from typing import Any

from construct.arc.grammar import Arc
from construct.arc.timeline import PLOT


def resolve_beat_id(reads: Any, beat_id: str) -> str:
    """DRIFT-HANDLING.md §3 R4: the terminal id of a beat's supersession
    chain (identity when unsuperseded). One walker — delegates to
    `conditions.resolve_superseded_beat` so `BeatAchieved` evaluation and
    every structural read here can never diverge on the chain rule."""
    from construct.arc.conditions import resolve_superseded_beat
    return resolve_superseded_beat(reads, beat_id, PLOT)


def active_beats(reads: Any, arc: Arc) -> tuple:
    """The arc's LIVE beat set (§3 R4): the sealed beats with superseded ones
    replaced by their repair replacements, materialized via
    `io.beat_from_reads`. READS-BACKED overlay — never baked into the Arc —
    so the legacy `arc_cache` load path and a same-turn repair are coherent
    by construction. Fail-open per beat: an unmaterializable replacement
    keeps the sealed beat (a repair that cannot be read never crashes a
    turn)."""
    out = []
    for b in arc.beats:
        rid = resolve_beat_id(reads, b.beat_id)
        if rid == b.beat_id:
            out.append(b)
            continue
        from construct.arc.io import beat_from_reads
        rb = beat_from_reads(reads, rid, frame=PLOT, arc_id=arc.arc_id)
        out.append(rb if rb is not None else b)
    return tuple(out)
