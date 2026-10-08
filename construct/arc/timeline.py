"""Timeline and pacing: where "now" sits on the world's valid-time axis, and how fast the
arc is being nudged forward.

Owns the frame-name constants (`PLOT`, `SESSION`), the turn epoch and its
entry-epoch contextvar (`_ENTRY_EPOCH`, `current_epoch`, `set_entry_epoch`,
`compute_entry_epoch`, `turn_time`), the as-of play-horizon metadata, the pacing
counters folded from the session frame, and the deterministic navigator
(`navigate`, `_RUNG_THRESHOLDS`). `construct.arc.executor` re-exports all of it, so
callers (and tests that reset `executor._ENTRY_EPOCH`) keep using the executor
names; there is exactly ONE `_ENTRY_EPOCH` contextvar object and it lives here.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

from construct.arc.conditions import PacingCounters
from construct.arc.grammar import Arc, Rung

logger = logging.getLogger(__name__)

PLOT = "plot:main"
SESSION = "session:main"

#: Turns live on the world timeline ABOVE all authoring/ingestion time,
#: so a turn's writes never valid-time-tie with session-zero rows (the
#: engine's simultaneity guard correctly refuses to fake supersession
#: on ties). Authoring uses small coordinates (chapters 1..n); play
#: starts at the epoch.
#:
#: STAGING-AFTERMATH-SCATTER fix (obs #3 half 3, Cx 127): a source fiction that
#: narrates the whole arc lets Stage-1 extraction stamp rows at CALENDAR YEARS
#: (e.g. 1974.0) — ABOVE this default epoch — so an aftermath `in` ("Jack in
#: Providence Hospital") folds as the CURRENT location and the opening cast is
#: scattered. The fix is a per-SCENARIO entry epoch computed ABOVE every pre-play
#: `valid_from` (`compute_entry_epoch`), set on a contextvar so `turn_time` (and the
#: pacing fold) put opening staging + every live turn unambiguously on top. Default
#: stays TURN_EPOCH (one-timeframe worlds — anchor/deduction — are a byte-for-byte
#: no-op; the contextvar is only raised when a world is built/opened with a stored
#: `entry_epoch`). All `turn_time` stamping is main-thread (the concurrent npc phase
#: only runs MODEL calls; commits are serial), so the contextvar is read consistently.
TURN_EPOCH = 1000.0

#: Margin above the highest pre-play `valid_from` (headroom so the first turns never tie).
ENTRY_MARGIN = 1000.0

#: AS-OF PLAY HORIZON (B' S2, Cx 253): the source-axis spacing for ingested-fiction worlds.
#: Each source chunk i lands at `i * SOURCE_STEP` on ONE monotone valid-time coordinate, so
#: the opening chunk (1) sits far below the aftermath (chunk N). The opening is then staged
#: just ABOVE chunk 1 (`opening_as_of`), and live turns advance the play horizon within the
#: reserved band [opening_as_of, next_source_as_of). SOURCE_STEP is deliberately HUGE (not a
#: magic 1000 — Cx 253 §1): the band must never be exhausted into the next source chunk by
#: turn-count arithmetic, so the horizon guard stays fail-closed.
SOURCE_STEP = 1_000_000.0


def horizon_metadata(source_step: float = SOURCE_STEP) -> tuple[float, float]:
    """`(opening_as_of, next_source_as_of)` for a horizon (ingested-fiction) world. The
    opening is staged at `source_step + ENTRY_MARGIN` — strictly above chunk 1's source rows
    (at `source_step`), so opening staging supersedes them — and the next source chunk sits
    at `2 * source_step`, the fail-closed ceiling the play horizon must remain below."""
    return source_step + ENTRY_MARGIN, 2.0 * source_step

_ENTRY_EPOCH: contextvars.ContextVar[float] = contextvars.ContextVar(
    "construct_entry_epoch", default=TURN_EPOCH)


def current_epoch() -> float:
    """The live-play time origin for this context (the scenario entry epoch, or
    TURN_EPOCH when none is set)."""
    return _ENTRY_EPOCH.get()


def set_entry_epoch(epoch: float):
    """Raise the live-play time origin for this context so opening staging + every live
    turn sit ABOVE all pre-play canon `valid_from` (obs #3 half 3). Returns the contextvar
    token (pass to `_ENTRY_EPOCH.reset` to restore). Idempotent; never lowers below
    TURN_EPOCH."""
    return _ENTRY_EPOCH.set(max(TURN_EPOCH, float(epoch)))


def compute_entry_epoch(world: Any) -> float:
    """The scenario entry epoch: strictly above every pre-play canon `valid_from` so the
    opening dossier/staging and all live turns win the containment fold over aftermath rows
    the source prose narrates (obs #3 half 3, Cx 127). Reads the append-log directly. Falls
    back to TURN_EPOCH when nothing exceeds it (one-timeframe worlds → a no-op)."""
    try:
        # AXIS-HEAD take-up (PB 096): the log's high-water mark over ALL rows,
        # ALL frames — the epoch must sit above every pre-play valid_from,
        # wherever it landed (a seeded knows: row anchoring the head is PB's
        # own fixture now). The last engine-internal read, retired.
        hi = float(world.porcelain.axis_heads().get("valid_head") or 0.0)
    except Exception:  # never let the epoch computation sink a build
        logger.exception("compute_entry_epoch: axis_heads read failed; using TURN_EPOCH")
        hi = 0.0
    # When TURN_EPOCH already sits above every authored row (the normal case — small chapter
    # coordinates 1..n), keep it EXACTLY (a true no-op for one-timeframe worlds). Only raise
    # when a row reaches/exceeds the epoch (the calendar-year leak), clearing it by the margin.
    return TURN_EPOCH if hi < TURN_EPOCH else hi + ENTRY_MARGIN


def turn_time(turn: int) -> float:
    return current_epoch() + float(turn)


def counters_from_session(reads: Any, arc: Arc) -> PacingCounters:
    """Fold the pacing counters from the session frame (§2.5):
    turns_elapsed = turn events; turns_quiet = turns since the last
    beat achievement or arc-entity interaction."""
    turns = reads.events(kind="turn", frame=SESSION)
    elapsed = len(turns)
    marks = [e.at for e in reads.events(kind="beat_achieved", frame=SESSION)]
    marks += [e.at for e in reads.events(kind="arc_touch", frame=SESSION)]
    _epoch = current_epoch()
    last_mark_turn = max((m - _epoch for m in marks
                          if m is not None and m >= _epoch), default=0)
    quiet = max(0, elapsed - int(last_mark_turn))
    return PacingCounters(turns_elapsed=elapsed, turns_quiet=quiet)


# --- the navigator (deterministic policy table, ARC-LAYER §5) -----------

_RUNG_THRESHOLDS = (
    (Rung.SURFACE, 3),
    (Rung.DRAW, 5),
    (Rung.CONVERGE, 7),
    (Rung.CONFRONT, 9),
)


def navigate(counters: PacingCounters, delta_size: int,
             recent_achievement: bool) -> Rung | None:
    """The pacing rung choice. Deterministic; provisional thresholds
    (ARC-LAYER §12.5 calibration constants — tune with play data)."""
    if recent_achievement or delta_size == 0:
        return None  # hold: let it breathe
    choice = None
    for rung, threshold in _RUNG_THRESHOLDS:
        if counters.turns_quiet >= threshold:
            choice = rung
    return choice
