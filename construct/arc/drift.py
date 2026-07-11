"""Drift handling — when the player leaves the road (DRIFT-HANDLING.md).

D1: D-SOFT detection (§2) via `drift_state`, a pure reader in the
`salient_moments` discipline (explicit inputs, no hidden reads, unit-testable
without a world), plus the diegetic-quiet gate constants (§2/§3 R1) and the
small SESSION-frame receipt helpers that make R1's no-re-preach and R2's
one-relocation-per-beat idempotent.

D2: the CLOSURE-WITNESS contract (§2) — `closure_witness_of` walks a beat's
`unreachable_if` at close time and records what actually evaluated TRUE (the
per-shape deciding leaves, UNKNOWNs, the exact causal clock-firing EVENT id,
and the clock-NECESSITY verdict, all captured against the SAME reads that
closed the beat, so later classification never re-evaluates a moved world) —
plus `classify_closure` (D-MISSED iff the witness proves the closure
clock-caused; everything else, including no-witness pre-contract closures and
UNKNOWN on the path, is D-HARD, the conservative default), the `on_expiry`
occurrence-annotation helpers (§2: a fired deadline proves the WINDOW closed,
never that the staged moment happened — occurrence-facts need the authored
`clock:<id>/on_expiry` note), and the R3 idempotency/callback row helpers
(§3 R3). R4 (repair, the D-HARD response) is D3's — a D-HARD classification
is recorded and goes no further here.

The orchestration (cohort calls, canon commits, briefing directives) lives in
`construct/turnloop.py`'s `_drift_pass` — this module intentionally never
imports `construct.turnloop` (no `construct/arc/*` module does; keeping that
invariant is what makes the eager top-level import back into `turnloop.py`
safe). No engine change of any kind.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from construct.arc.conditions import (
    AllOf, AnyOf, AtLeast, ClockFired, Expr, Not, Truth, evaluate,
)
from construct.arc.executor import PLOT, SESSION, turn_time
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


# ---- D2: the closure-witness contract (§2) ---------------------------------

def _leaf_key(atom: Any) -> str:
    """A stable human-readable identity for a witness leaf — the atom's type
    plus its addressing fields. Debug/audit surface only; the classifier never
    parses these back."""
    name = type(atom).__name__
    for attrs in (("clock_id",), ("beat_id",), ("entity", "attribute"),
                  ("frame", "entity", "attribute"), ("kind",), ("entity", "place"),
                  ("at_least",)):
        if all(hasattr(atom, a) for a in attrs):
            return f"{name}({'.'.join(str(getattr(atom, a)) for a in attrs)})"
    return name


def _clock_firing_event(reads: Any, atom: ClockFired) -> str | None:
    """The EXACT causal firing event for a TRUE ClockFired leaf (§2, cr r3
    point 4): for `ClockFired(n)` threshold shapes, the horizon-visible event
    that MADE the threshold true — the n-th firing ordered by event time then
    id — never an arbitrary matching event. Mirrors `evaluate`'s own read
    (`kind="clock_fired"` in the atom's plot frame, the clock id among the
    agents) so the witness can never cite an event the evaluation didn't see."""
    try:
        rows = [r for r in reads.events(kind="clock_fired", frame=atom.plot_frame)
                if atom.clock_id in r.agents]
    except Exception:  # noqa: BLE001 — a failed read proves nothing
        return None
    rows.sort(key=lambda r: (r.at if r.at is not None else 0, r.event_id))
    if len(rows) < atom.n:
        return None
    return rows[atom.n - 1].event_id


def _true_leaves(expr: Expr, reads: Any, out_true: list, out_unknown: list) -> Truth:
    """Walk `expr` recording the DECIDING leaves per shape (§2): AnyOf records
    its TRUE branches' leaves; AllOf all leaves; AtLeast the satisfied leaves;
    Not records the negated subtree's evaluation (its leaves land in whichever
    bucket their own truth puts them — the Not's flip happens above them).
    UNKNOWN/INDETERMINATE atoms are recorded as UNKNOWN wherever encountered.
    Returns the node's own three-valued truth (identical to `evaluate` — the
    walk IS an evaluation, just one that remembers)."""
    if isinstance(expr, Not):
        # the child's leaves record under their OWN truth; the flip is above them
        v = _true_leaves(expr.operand, reads, out_true, out_unknown)
        return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE}.get(
            v, Truth.INDETERMINATE)
    if isinstance(expr, (AllOf, AnyOf, AtLeast)):
        verdicts = [_true_leaves(op, reads, out_true, out_unknown)
                    for op in expr.operands]
        if isinstance(expr, AllOf):
            if any(v is Truth.FALSE for v in verdicts):
                return Truth.FALSE
            if any(v is Truth.INDETERMINATE for v in verdicts):
                return Truth.INDETERMINATE
            return Truth.TRUE
        if isinstance(expr, AnyOf):
            if any(v is Truth.TRUE for v in verdicts):
                return Truth.TRUE
            if any(v is Truth.INDETERMINATE for v in verdicts):
                return Truth.INDETERMINATE
            return Truth.FALSE
        trues = sum(1 for v in verdicts if v is Truth.TRUE)
        unknowns = sum(1 for v in verdicts if v is Truth.INDETERMINATE)
        if trues >= expr.k:
            return Truth.TRUE
        if trues + unknowns >= expr.k:
            return Truth.INDETERMINATE
        return Truth.FALSE
    # an atom leaf: evaluate it once and remember where it landed.
    verdict = evaluate(expr, reads)
    leaf: dict = {"kind": type(expr).__name__, "key": _leaf_key(expr)}
    if verdict is Truth.TRUE:
        if isinstance(expr, ClockFired):
            leaf["clock_id"] = expr.clock_id
            leaf["firing_event"] = _clock_firing_event(reads, expr)
        out_true.append(leaf)
    elif verdict is Truth.INDETERMINATE:
        out_unknown.append(leaf)
    return verdict


def _evaluate_clocks_false(expr: Expr, reads: Any) -> Truth:
    """`evaluate` with every ClockFired leaf FORCED FALSE — the clock-necessity
    probe (§2): if the closure still stands without any clock, the clock was
    incidental and the closure is NOT clock-caused."""
    if isinstance(expr, ClockFired):
        return Truth.FALSE
    if isinstance(expr, Not):
        v = _evaluate_clocks_false(expr.operand, reads)
        return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE}.get(
            v, Truth.INDETERMINATE)
    if isinstance(expr, AllOf):
        vs = [_evaluate_clocks_false(op, reads) for op in expr.operands]
        if any(v is Truth.FALSE for v in vs):
            return Truth.FALSE
        if any(v is Truth.INDETERMINATE for v in vs):
            return Truth.INDETERMINATE
        return Truth.TRUE
    if isinstance(expr, AnyOf):
        vs = [_evaluate_clocks_false(op, reads) for op in expr.operands]
        if any(v is Truth.TRUE for v in vs):
            return Truth.TRUE
        if any(v is Truth.INDETERMINATE for v in vs):
            return Truth.INDETERMINATE
        return Truth.FALSE
    if isinstance(expr, AtLeast):
        vs = [_evaluate_clocks_false(op, reads) for op in expr.operands]
        trues = sum(1 for v in vs if v is Truth.TRUE)
        unknowns = sum(1 for v in vs if v is Truth.INDETERMINATE)
        if trues >= expr.k:
            return Truth.TRUE
        if trues + unknowns >= expr.k:
            return Truth.INDETERMINATE
        return Truth.FALSE
    return evaluate(expr, reads)


def closure_witness_of(unreachable_if: Expr, reads: Any, turn: int) -> dict:
    """The closure witness (§2), computed AT CLOSE TIME against the SAME reads
    that closed the beat — later classification never re-evaluates a moved
    world. Records: the deciding TRUE leaves (per-shape semantics), UNKNOWN
    leaves, each TRUE ClockFired leaf's exact causal firing-event id, and the
    clock-NECESSITY verdict (`clock_caused`: TRUE ClockFired present AND the
    expression with every clock leaf forced FALSE no longer evaluates TRUE)."""
    out_true: list = []
    out_unknown: list = []
    _true_leaves(unreachable_if, reads, out_true, out_unknown)
    has_true_clock = any(l.get("kind") == "ClockFired" for l in out_true)
    clock_caused = bool(
        has_true_clock
        and _evaluate_clocks_false(unreachable_if, reads) is not Truth.TRUE)
    return {
        "true_leaves": out_true,
        "unknown_leaves": out_unknown,
        "clock_caused": clock_caused,
        "firing_events": [l["firing_event"] for l in out_true
                          if l.get("kind") == "ClockFired"
                          and l.get("firing_event")],
        "turn": turn,
    }


def read_closure_witness(reads: Any, beat_id: str) -> dict | None:
    """The persisted witness for a closed beat, or None (a pre-contract
    closure — classified D-HARD, the conservative default). All-or-nothing
    parse: a malformed witness reads as ABSENT, never as a partial truth."""
    raw = reads.state(beat_id, "closure_witness", frame=PLOT)
    if raw is None:
        return None
    try:
        w = json.loads(str(raw))
        return w if isinstance(w, dict) else None
    except (TypeError, ValueError):
        return None


def classify_closure(witness: dict | None) -> str:
    """§2's witness-based classifier, a pure read of the persisted witness:
    D-MISSED iff the witness PROVES the closure clock-caused — a TRUE
    ClockFired leaf with a captured firing event, clock-necessity verified at
    close time, and NO unknown on the path. Everything else — no witness,
    mixed compound where the world-state half sufficed, UNKNOWN anywhere on
    the path, a firing event that could not be captured — is D-HARD, the
    conservative default (repair's province, never absence-narration's)."""
    if not witness:
        return "D-HARD"
    if witness.get("unknown_leaves"):
        return "D-HARD"
    if not witness.get("clock_caused"):
        return "D-HARD"
    if not witness.get("firing_events"):
        return "D-HARD"
    return "D-MISSED"


# ---- D2: the occurrence rule (§2) — the authored `on_expiry` annotation ----

def on_expiry_items(clock_id: str, note: str) -> list[dict]:
    """The authoring-side row for the occurrence annotation: `clock:<id>` /
    `on_expiry` in the PLOT frame. Without this authored note, a fired
    deadline proves only that the WINDOW closed — R3 consequences stay
    lapse-facts; the staged moment is never asserted to have happened."""
    return [{"entity": clock_id, "attribute": "on_expiry", "value": note,
             "timeless": True}]


def read_on_expiry(reads: Any, clock_id: str) -> str | None:
    """The authored occurrence note for a clock, or None (lapse-facts only)."""
    val = reads.state(clock_id, "on_expiry", frame=PLOT)
    return str(val) if val else None


# ---- D2: R3 idempotency + the durable callback contract (§3 R3) ------------

def moment_receipt(reads: Any, beat_id: str) -> bool:
    """Once per beat (§3 R3): True when this beat's missed moment has already
    been processed — the R3 response never re-fires for the same closure."""
    slug = beat_id.split(":", 1)[-1]
    return reads.state(f"session:moment_{slug}", "done", frame=SESSION) is not None


def mark_moment(world: Any, beat_id: str, event_id: str, turn: int) -> None:
    """The R3 idempotency row (the relocation-receipt discipline)."""
    slug = beat_id.split(":", 1)[-1]
    world.porcelain.ingest_structured([
        {"entity": f"session:moment_{slug}", "attribute": "done",
         "value": event_id, "valid_from": turn_time(turn)},
    ], frame=SESSION)


def callback_rows(beat_id: str, affected: list[str], directive: str,
                  caused_by: str, turn: int) -> list[dict]:
    """The durable pending/consumed callback (§3 R3 point 3): `affected` is a
    JSON id list PINNED `value_type="literal"` (cr: untyped JSON is identity-
    classified by arc IO and can be silently dropped at scale — the target
    match must never vanish while status/directive survive)."""
    eid = f"callback:moment_missed_{beat_id.split(':', 1)[-1]}"
    return [
        {"entity": eid, "attribute": "affected", "value": json.dumps(affected),
         "value_type": "literal", "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "directive", "value": directive,
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "status", "value": "pending",
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "caused_by", "value": caused_by,
         "valid_from": turn_time(turn)},
    ]


def pending_callbacks(reads: Any, *, as_of: float | None = None) -> list[dict]:
    """Every PENDING callback with a VALID affected list — horizon-safe scan
    over the SESSION frame. The affected parse is all-or-empty (§3 R3): a
    malformed/absent list means the callback cannot target-match and is
    SKIPPED (never surfaced blind, never crashes the scan)."""
    out: list[dict] = []
    try:
        from construct.adapter import frame_facts
    except Exception:  # noqa: BLE001 — no adapter, no callbacks
        return out
    try:
        rows = frame_facts(reads, SESSION, prefix="callback:moment_missed_",
                           as_of=as_of)
    except Exception:  # noqa: BLE001 — a failed scan surfaces nothing
        return out
    by_entity: dict[str, dict] = {}
    for r in rows:
        by_entity.setdefault(str(r.entity), {})[str(r.attribute)] = r.value
    for eid, attrs in by_entity.items():
        if attrs.get("status") != "pending":
            continue
        try:
            affected = json.loads(str(attrs.get("affected") or ""))
            if not isinstance(affected, list):
                continue
        except (TypeError, ValueError):
            continue  # all-or-empty: malformed target list never surfaces blind
        directive = str(attrs.get("directive") or "")
        if not directive:
            continue
        out.append({"entity": eid, "affected": [str(a) for a in affected],
                    "directive": directive})
    return out


def mark_callback_surfaced(world: Any, callback_entity: str, turn: int) -> None:
    """Supersede `status` → surfaced (once-only by supersession)."""
    world.porcelain.ingest_structured([
        {"entity": callback_entity, "attribute": "status", "value": "surfaced",
         "valid_from": turn_time(turn)},
    ], frame=SESSION)


def record_absence_declined(world: Any, turn: int, beat_id: str, reason: str) -> None:
    """§5 telemetry: the `absence_declined` session receipt (the decline
    discipline — telemetry, never a lock; only `mark_moment` blocks a retry)."""
    slug = beat_id.split(":", 1)[-1]
    eid = f"event:absence_declined_{slug}_{turn}"
    world.porcelain.ingest_structured([
        {"entity": eid, "attribute": "kind", "value": "absence_declined",
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "beat", "value": beat_id,
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "reason", "value": reason,
         "valid_from": turn_time(turn)},
    ], frame=SESSION)
    logger.info("absence-consequence declined (turn %d, beat %s): %s",
                turn, beat_id, reason)


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
