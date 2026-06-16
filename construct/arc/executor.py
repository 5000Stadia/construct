"""The arc/clock commit halves (ARC-LAYER §2.4, §3; TURN-LOOP §2).

The evaluation halves live in `conditions`/`lint` (pure logic); this
module owns the COMMITS — every write goes through
`porcelain.ingest_structured(frame=...)`, the sanctioned doorway.
Clock effects land in canon (world consequences, `caused_by`-chained);
firing events, beat statuses, and pacing receipts land in the
host-owned frames.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from construct.arc.conditions import PacingCounters, Truth, evaluate
from construct.arc.grammar import Arc, Rung, Weight

logger = logging.getLogger(__name__)

PLOT = "plot:main"
SESSION = "session:main"

#: Turns live on the world timeline ABOVE all authoring/ingestion time,
#: so a turn's writes never valid-time-tie with session-zero rows (the
#: engine's simultaneity guard correctly refuses to fake supersession
#: on ties). Authoring uses small coordinates (chapters 1..n); play
#: starts at the epoch.
TURN_EPOCH = 1000.0


def turn_time(turn: int) -> float:
    return TURN_EPOCH + float(turn)


@dataclass
class TickTrace:
    clocks_fired: list[str]
    beats_achieved: list[str]
    beats_closed: list[str]


def counters_from_session(reads: Any, arc: Arc) -> PacingCounters:
    """Fold the pacing counters from the session frame (§2.5):
    turns_elapsed = turn events; turns_quiet = turns since the last
    beat achievement or arc-entity interaction."""
    turns = reads.events(kind="turn", frame=SESSION)
    elapsed = len(turns)
    marks = [e.at for e in reads.events(kind="beat_achieved", frame=SESSION)]
    marks += [e.at for e in reads.events(kind="arc_touch", frame=SESSION)]
    last_mark_turn = max((m - TURN_EPOCH for m in marks
                          if m is not None and m >= TURN_EPOCH), default=0)
    quiet = max(0, elapsed - int(last_mark_turn))
    return PacingCounters(turns_elapsed=elapsed, turns_quiet=quiet)


def clock_pass(world: Any, arc: Arc, reads: Any, counters: PacingCounters,
               turn: int) -> list[str]:
    """Fire due clocks (the §12.1 deterministic executor). Effects →
    canon; the firing event + status → plot:. Returns fired clock ids."""
    fired: list[str] = []
    for clock in tuple(arc.clocks) + (arc.refusal_clock,):
        status = reads.state(clock.clock_id, "status", frame=PLOT)
        if status != "armed":
            continue
        verdict = evaluate(clock.fires_when, reads, counters)
        if verdict is not Truth.TRUE:
            continue
        effects = [dict(item) for item in clock.effects]
        for item in effects:
            item.setdefault("valid_from", turn_time(turn))
        world.porcelain.ingest_structured(effects)  # canon — world consequences
        firing_id = f"event:{clock.clock_id.split(':', 1)[1]}_fired_{turn}"
        plot_items = [
            {"entity": firing_id, "attribute": "kind", "value": "clock_fired",
             "valid_from": turn_time(turn)},
            {"entity": firing_id, "attribute": "agent", "value": clock.clock_id,
             "value_type": "entity", "valid_from": turn_time(turn)},
        ]
        if clock.rearm != "repeat":
            plot_items.append({"entity": clock.clock_id, "attribute": "status",
                               "value": "fired", "valid_from": turn_time(turn)})
        world.porcelain.ingest_structured(plot_items, frame=PLOT)
        fired.append(clock.clock_id)
        logger.info("clock fired: %s (rung=%s)", clock.clock_id,
                    clock.rung.value if clock.rung else "-")
    return fired


def beat_pass(world: Any, arc: Arc, reads: Any, turn: int) -> tuple[list[str], list[str]]:
    """Re-evaluate ALL pending beats (letter 006 default), LAST in the
    tick. Achievements committed as status+justified_by; flagged
    unreachable beats closed (repair is post-v1 — logged loudly)."""
    achieved, closed = [], []
    for beat in arc.beats:
        status = reads.state(beat.beat_id, "status", frame=PLOT)
        if status not in (None, "pending"):
            continue
        if beat.unreachable_if is not None and \
                evaluate(beat.unreachable_if, reads) is Truth.TRUE:
            world.porcelain.ingest_structured([
                {"entity": beat.beat_id, "attribute": "status", "value": "closed",
                 "valid_from": turn_time(turn)},
            ], frame=PLOT)
            closed.append(beat.beat_id)
            logger.warning("beat closed (unreachable): %s — repair is post-v1; "
                           "the refusal clock backstops", beat.beat_id)
            continue
        if evaluate(beat.achievable_via, reads) is Truth.TRUE:
            world.porcelain.ingest_structured([
                {"entity": beat.beat_id, "attribute": "status", "value": "achieved",
                 "valid_from": turn_time(turn)},
                {"entity": beat.beat_id, "attribute": "justified_by",
                 "value": json.dumps({"turn": turn}), "valid_from": turn_time(turn)},
            ], frame=PLOT)
            mark = f"event:beat_mark_{beat.beat_id.split(':', 1)[1]}_{turn}"
            world.porcelain.ingest_structured([
                {"entity": mark, "attribute": "kind", "value": "beat_achieved",
                 "valid_from": turn_time(turn)},
            ], frame=SESSION)
            achieved.append(beat.beat_id)
            logger.info("beat achieved: %s", beat.beat_id)
    return achieved, closed


def arc_concluded(reads: Any, arc: Arc) -> bool:
    """Has the arc reached its destination? True iff the conclusion
    shape's `world_condition` is satisfied (the climax sufficiency set
    achieved) OR the refusal clock has fired (the tragedy-of-absence
    ending). Deterministic. Drives the bounded/endless distinction:
    bounded worlds settle into aftermath here; endless worlds carry on."""
    from construct.arc.conditions import ClockFired

    if evaluate(arc.shape.world_condition, reads) is Truth.TRUE:
        return True
    refusal = arc.refusal_clock.clock_id
    return evaluate(ClockFired(refusal), reads) is Truth.TRUE


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


def arc_entities(arc: Arc) -> set[str]:
    """Entity ids the arc references (for arc_touch detection and the
    irony-delta scope)."""
    from construct.arc.conditions import atoms_of
    from construct.arc.lint import _entity_referents

    out: set[str] = set()
    exprs = [b.achievable_via for b in arc.beats]
    exprs += [b.unreachable_if for b in arc.beats if b.unreachable_if]
    exprs += [arc.shape.world_condition, arc.shape.premise]
    for expr in exprs:
        for atom in atoms_of(expr):
            out.update(_entity_referents(atom))
    out.add(arc.protagonist)
    return out
