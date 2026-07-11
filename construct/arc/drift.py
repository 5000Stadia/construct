"""Drift handling — when the player leaves the road (DRIFT-HANDLING.md).

D1 slice ONLY: D-SOFT detection (§2) via `drift_state`, a pure reader in the
`salient_moments` discipline (explicit inputs, no hidden reads, unit-testable
without a world), plus the diegetic-quiet gate constants (§2/§3 R1) and the
small SESSION-frame receipt helpers that make R1's no-re-preach and R2's
one-relocation-per-beat idempotent. D-MISSED/D-HARD (the closure-witness
contract) are D2's; R3/R4 (absence-consequence, repair) are D2/D3's — nothing
here classifies or writes toward them. The relocate MECHANISM itself (the
`relocate_pick` cohort call, the carrier-move commit, the briefing directive)
lives in `construct/turnloop.py`'s `_drift_pass`/`_relocate_beat` — this
module intentionally never imports `construct.turnloop` (no `construct/arc/*`
module does; keeping that invariant is what makes the eager top-level import
back into `turnloop.py` safe). No engine change of any kind.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from construct.arc.executor import SESSION, turn_time
from construct.arc.grammar import Rung

logger = logging.getLogger(__name__)

#: R1's OWN cadence (§3 R1 point 2): at most one nudge per this many diegetic
#: minutes. Deliberately DISTINCT from RELOCATE_QUIET_MIN below (cr r2 oracle
#: gap 7) — the two constants must never be conflated or unified.
NUDGE_QUIET_MIN: float = 60.0

#: The D-SOFT drift LICENSE (§2): a pending REQUIRED beat only drifts once the
#: world has been development-quiet this many diegetic minutes since the last
#: mint/beat/clock/fallout (read off the LWG development ledger via
#: `_last_development_min`). The rising rung is a NECESSARY co-signal (story
#: pressure); this diegetic gate is what makes the license honest — never a
#: turn count (turns are free).
RELOCATE_QUIET_MIN: float = 240.0

#: The relocation threshold rung (§8 open item, resolved at D1 build time): the
#: rung immediately BELOW the refusal-warning rung. `Rung.REFUSAL` is the
#: terminal warning itself (never reached by `navigate()`'s own threshold
#: ladder — it fires off the refusal CLOCK, not pacing); `Rung.CONFRONT` is
#: the highest rung the ladder ever returns, i.e. "relocate BEFORE the refusal
#: clock is in sight" (§3 R2 step 1).
RELOCATE_RUNG = Rung.CONFRONT

#: `Rung` is ordered SURFACE < DRAW < CONVERGE < CONFRONT < REFUSAL
#: (grammar.py) — a plain tuple gives the ordinal comparison `navigate()`
#: doesn't itself expose (needed to test "has the rung risen to at least X").
_RUNG_ORDER = (Rung.SURFACE, Rung.DRAW, Rung.CONVERGE, Rung.CONFRONT, Rung.REFUSAL)

#: Mirrors `construct.arc.executor._RUNG_THRESHOLDS` (the single source of
#: truth for the ladder's turn-counted thresholds) so drift's own rung read
#: (`rung_from_counters`, below) can never drift apart from the nudge ladder's
#: numbers — same threshold table, a different (sustained-quiet-only) query.
from construct.arc.executor import _RUNG_THRESHOLDS  # noqa: E402


def _rung_at_least(rung: Rung | None, floor: Rung) -> bool:
    if rung is None:
        return False
    try:
        return _RUNG_ORDER.index(rung) >= _RUNG_ORDER.index(floor)
    except ValueError:
        return False


def rung_from_counters(counters: Any) -> Rung | None:
    """The rung ladder read purely off SUSTAINED quiet (`counters.turns_quiet`),
    independent of `navigate()`'s own this-turn zero-delta / recent-achievement
    escape hatch — that hatch is a nudge-PACING concern (don't escalate on a
    turn where nothing happened), not drift's (drift cares whether quiet has
    been sustained across many turns, which `turns_quiet` already encodes on
    its own). Reuses the SAME `_RUNG_THRESHOLDS` table as `navigate()` so the
    two readings never diverge on the ladder itself (§2: the rung is a
    NECESSARY co-signal, not an independently-tuned one)."""
    choice: Rung | None = None
    for rung, threshold in _RUNG_THRESHOLDS:
        if counters.turns_quiet >= threshold:
            choice = rung
    return choice


@dataclass(frozen=True)
class Drift:
    """One classified drift condition (§2). D1 emits D-SOFT only — `cls` is
    carried explicitly (not inferred from the record's own type) so D2 can
    extend the classifier without changing this record's shape."""

    beat_id: str
    cls: str  # "D-SOFT" in D1; "D-MISSED"/"D-HARD" reserved for D2


def drift_state(pending_required: list[str], rung: Rung | None,
                quiet_minutes: float) -> list[Drift]:
    """Pure classifier (§2, §7 D1). D-SOFT iff: at least one REQUIRED beat is
    pending, the rung has risen to at least `RELOCATE_RUNG`, AND the diegetic
    quiet gate is open (`quiet_minutes >= RELOCATE_QUIET_MIN`). Explicit
    inputs, no hidden reads, unit-testable without a world (the
    `salient_moments` discipline). D1 ONLY — D-MISSED/D-HARD need the D2
    closure-witness contract and are never produced here, regardless of
    input shape."""
    if not pending_required:
        return []
    if not _rung_at_least(rung, RELOCATE_RUNG):
        return []
    if quiet_minutes < RELOCATE_QUIET_MIN:
        return []
    return [Drift(beat_id=b, cls="D-SOFT") for b in pending_required]


# ---- SESSION-frame receipts (idempotency bookkeeping only — no cohort/commit
# logic here; that's turnloop.py's `_drift_pass`/`_relocate_beat`) ----------

def last_nudge_thread(reads: Any) -> str | None:
    """R1 no-re-preach (§3 R1 point 1): the thread surfaced by the LAST nudge,
    or None if no nudge has fired yet this story."""
    val = reads.state("session:drift", "last_nudge_thread", frame=SESSION)
    return str(val) if val else None


def last_nudge_min(reads: Any) -> float | None:
    """The diegetic-minute stamp of the last nudge (§3 R1 point 2's cadence
    gate reads this), or None before any nudge has fired."""
    val = reads.state("session:drift", "last_nudge_min", frame=SESSION)
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def nudge_suppressed(reads: Any, minutes_now: float | None) -> bool:
    """§3 R1 point 2: a nudge fired within the last `NUDGE_QUIET_MIN` diegetic
    minutes suppresses the next. No diegetic clock (`minutes_now` is None)
    never suppresses on its own — turns are free; only the story clock gates
    this, exactly as the ambient trigger's own quiet gate does."""
    if minutes_now is None:
        return False
    last = last_nudge_min(reads)
    if last is None:
        return False
    return (minutes_now - last) < NUDGE_QUIET_MIN


def mark_nudge(world: Any, thread: str, minutes_now: float, turn: int) -> None:
    """Record the surfaced thread + the diegetic-minute stamp (§3 R1 points
    1-2). Called only after a nudge actually fires (never on suppression or
    drop)."""
    world.porcelain.ingest_structured([
        {"entity": "session:drift", "attribute": "last_nudge_thread",
         "value": thread, "valid_from": turn_time(turn)},
        {"entity": "session:drift", "attribute": "last_nudge_min",
         "value": minutes_now, "valid_from": turn_time(turn)},
    ], frame=SESSION)


def relocation_receipt(reads: Any, beat_id: str) -> dict | None:
    """One relocation per beat (§3 R2 point 4): the existing receipt, or None.
    A beat with an existing receipt is not relocated again in D1 — escalation
    to R4 on a second drift is D3's, not this slice's."""
    slug = beat_id.split(":", 1)[-1]
    new_staging = reads.state(f"session:relocated_{slug}", "new_staging", frame=SESSION)
    if new_staging is None:
        return None
    old_staging = reads.state(f"session:relocated_{slug}", "old_staging", frame=SESSION)
    return {"beat_id": beat_id, "old_staging": old_staging, "new_staging": new_staging}


def mark_relocation(world: Any, beat_id: str, old_staging: str | None,
                    new_staging: str, turn: int) -> None:
    """Write BOTH the per-beat idempotency row (`session:relocated_<slug>` —
    what `relocation_receipt` reads back) AND the `relocation_receipt` EVENT
    (§5 telemetry: session receipts, the generator receipt discipline —
    `_record_attempt`'s shape in construct/arc/generator.py)."""
    slug = beat_id.split(":", 1)[-1]
    eid = f"event:relocated_{slug}_{turn}"
    world.porcelain.ingest_structured([
        {"entity": eid, "attribute": "kind", "value": "relocation_receipt",
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "beat", "value": beat_id,
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "old_staging", "value": old_staging or "",
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "new_staging", "value": new_staging,
         "valid_from": turn_time(turn)},
        {"entity": f"session:relocated_{slug}", "attribute": "new_staging",
         "value": new_staging, "valid_from": turn_time(turn)},
        {"entity": f"session:relocated_{slug}", "attribute": "old_staging",
         "value": old_staging or "", "valid_from": turn_time(turn)},
    ], frame=SESSION)
    logger.info("drift relocation committed: %s -> %s (beat %s)",
                old_staging, new_staging, beat_id)


def record_relocate_declined(world: Any, turn: int, beat_id: str, reason: str) -> None:
    """§5 telemetry: the `relocate_declined` session receipt (the generator
    receipt discipline — `_record_decline`'s shape). Never blocks a future
    attempt on this beat (only a COMMITTED relocation does, via
    `mark_relocation`'s idempotency row) — a decline is telemetry, not a
    lock."""
    slug = beat_id.split(":", 1)[-1]
    eid = f"event:relocate_declined_{slug}_{turn}"
    world.porcelain.ingest_structured([
        {"entity": eid, "attribute": "kind", "value": "relocate_declined",
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "beat", "value": beat_id,
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "reason", "value": reason,
         "valid_from": turn_time(turn)},
    ], frame=SESSION)
    logger.info("drift relocation declined (turn %d, beat %s): %s", turn, beat_id, reason)
