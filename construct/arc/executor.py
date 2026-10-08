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
from construct.arc.grammar import Arc, Phase, Rung, Weight

# --- the executor was split along four seams (audit 2026-10 tier 2 #7); every name
# --- below is RE-EXPORTED so `from construct.arc.executor import X` keeps working.
from construct.arc.timeline import (  # noqa: F401
    ENTRY_MARGIN, PLOT, SESSION, SOURCE_STEP, TURN_EPOCH, _ENTRY_EPOCH, _RUNG_THRESHOLDS,
    compute_entry_epoch, counters_from_session, current_epoch, horizon_metadata, navigate,
    set_entry_epoch, turn_time)
from construct.arc.supersession import active_beats, resolve_beat_id  # noqa: F401
from construct.arc.conclusion import (  # noqa: F401
    COVERAGE, OUTCOME_SHAPES, _PHASE_ORDER, arc_concluded, arc_coverage, arc_outcome,
    climax_ready, conclusion_from_coverage, coverage_summary, current_phase,
    delta_type_from_coverage, pillar_coverage)
from construct.arc.concealment import (  # noqa: F401
    _CONCEAL_STOP, _CONCEAL_WORD, _is_placeholder_premise, _premise_keys, arc_entities,
    arc_protected_keys, concealed_tokens, value_leaks)


#: Lifecycle terminals (LIVING-WORLD-GENERATOR §3). `active` is the live state;
#: the four terminals are reached at most once each. `won` ends a story (main
#: arc); the three non-won terminals emit FALLOUT (a standing world-consequence
#: that seeds later generation) and, for the main arc in win_loss, end the story.
LIFECYCLE_TERMINALS = ("won", "lost", "cancelled", "incompletable")

logger = logging.getLogger(__name__)


@dataclass
class TickTrace:
    clocks_fired: list[str]
    beats_achieved: list[str]
    beats_closed: list[str]


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
        # Runtime guard (founder ruling 2026-06-25 / Cx 178): a REFUSAL clock NEVER fires on a
        # turn counter. Turns don't close stories, and emitting its effect would fabricate a
        # `refusal_conclusion` in canon. The source authors abandonment-`Occurred` refusals, but
        # this defends a PERSISTED or hand-authored old-shape (`TurnsQuiet`) refusal that reaches
        # here — the guarantee is "no quiet-turn conclusion can EVER be emitted", not just authored.
        if clock.rung is Rung.REFUSAL:
            from construct.arc.conditions import COUNTER_ATOMS, atoms_of
            if any(isinstance(a, COUNTER_ATOMS) for a in atoms_of(clock.fires_when)):
                logger.warning(
                    "suppressed counter-based REFUSAL clock %s (turns never force a close)",
                    clock.clock_id)
                continue
        firing_id = f"event:{clock.clock_id.split(':', 1)[1]}_fired_{turn}"
        effects = [dict(item) for item in clock.effects]
        for item in effects:
            item.setdefault("valid_from", turn_time(turn))
            item.setdefault("caused_by", firing_id)  # link consequence -> cause
        # The firing event in canon too (kind row) so the situation lens can
        # walk back from a served effect and surface this as a LIVE thread on
        # re-entry (PB SITUATION-LENS-V1, letter 058). plot: keeps the status.
        canon_event = [{"entity": firing_id, "attribute": "kind",
                        "value": "clock_fired", "valid_from": turn_time(turn)}]
        world.porcelain.ingest_structured(canon_event + effects)  # canon — world consequences
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


def beat_pass(world: Any, arc: Arc, reads: Any,
              turn: int) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """Re-evaluate ALL pending beats (letter 006 default), LAST in the
    tick. Achievements committed as status+justified_by; flagged
    unreachable beats closed (repair is post-v1 — logged loudly). A `correlates`
    beat additionally fires the reveal: on achievement, the two entities are
    `correlate`d as-of this turn (PB AKA-CORRELATION-V1) — facets of one
    identity, not merged. Returns (achieved, closed, revealed) where revealed is
    the list of correlated (a, b) pairs this tick."""
    achieved, closed, revealed = [], [], []
    for beat in active_beats(reads, arc):
        status = reads.state(beat.beat_id, "status", frame=PLOT)
        if status not in (None, "pending"):
            continue
        if beat.unreachable_if is not None and \
                evaluate(beat.unreachable_if, reads) is Truth.TRUE:
            rows = [
                {"entity": beat.beat_id, "attribute": "status", "value": "closed",
                 "valid_from": turn_time(turn)},
            ]
            # DRIFT-HANDLING.md §2 (D2): the CLOSURE WITNESS — what actually
            # evaluated TRUE at close time (deciding leaves per shape, UNKNOWNs,
            # the exact causal clock-firing event id, the clock-necessity
            # verdict), captured against the SAME reads that closed the beat.
            # Fail-open: a witness failure never blocks the close — an absent
            # witness classifies D-HARD downstream, the conservative default.
            try:
                from construct.arc.drift import closure_witness_of
                witness = closure_witness_of(beat.unreachable_if, reads, turn)
                rows.append({"entity": beat.beat_id, "attribute": "closure_witness",
                             "value": json.dumps(witness),
                             "valid_from": turn_time(turn)})
            except Exception:  # noqa: BLE001 — the close stands; D-HARD covers it
                logger.warning("closure witness failed for %s (classifies D-HARD)",
                               beat.beat_id, exc_info=True)
            world.porcelain.ingest_structured(rows, frame=PLOT)
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
            if beat.correlates is not None:
                a, b = beat.correlates
                try:
                    rcpt = world.porcelain.correlate(
                        a, b, evidence=f"reveal: {beat.beat_id}", at=turn_time(turn))
                    outcome = rcpt.get("outcome") if isinstance(rcpt, dict) else rcpt
                    if outcome == "vetoed_distinct":
                        logger.warning("reveal %s vetoed: %s ≠ %s are asserted distinct",
                                       beat.beat_id, a, b)
                    else:
                        revealed.append((a, b))
                        logger.info("reveal: correlated %s ~ %s (%s)", a, b, outcome)
                except Exception as exc:  # a reveal must never sink the tick
                    logger.warning("reveal correlate %s~%s failed: %s", a, b, exc)
    return achieved, closed, revealed


@dataclass
class ConclusiveCandidate:
    """The 'something happened this scene that could end the story' signal the
    turn loop assembles from its tick trace — the explicit candidate Gate A needs
    (reading only `reads` would lose the 'just this turn' distinction — Cx C1#3)."""
    climax_beat_achieved: bool = False       # a climax_ready_beat was achieved this tick
    refusal_or_deadline_fired: bool = False  # an abandonment/authored-deadline clock fired this tick
    required_beat_foreclosed: bool = False   # a required beat closed this tick
    # (post_climax_window_expired removed 2026-06-25 / Cx 176 — turns never force a close)

    def any(self) -> bool:
        return (self.climax_beat_achieved or self.refusal_or_deadline_fired
                or self.required_beat_foreclosed)


def conclusive_eligible(reads: Any, arc: Arc, *, contract: str,
                        candidate: ConclusiveCandidate) -> bool:
    """Gate A — the cheap, deterministic eligibility check before we spend the
    LLM final-page judge (Gate B). Returns False (→ don't even ask) unless ALL:
    Story contract; in CRISIS/CLIMAX/FALLING (or a refusal/foreclosure path is
    live); minimum arc progress; and a candidate event this turn. The post-climax
    window expiring is itself a candidate, so it can fire with no fresh event."""
    from construct.arc.conditions import ClockFired
    if contract != "story":
        return False
    refusal_fired = evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE
    foreclosed = _required_unreachable(reads, arc)
    phase = current_phase(reads, arc)
    if not (phase in (Phase.CRISIS, Phase.CLIMAX, Phase.FALLING)
            or refusal_fired or foreclosed):
        return False
    if not (climax_ready(reads, arc) or foreclosed or refusal_fired):
        return False
    return candidate.any()


# --- the arc lifecycle (LIVING-WORLD-GENERATOR §3) ----------------------

@dataclass
class Fallout:
    """The world-consequence emitted when an arc dies (a TRUE canon fact, the
    engine membrane — PB letter 072 §2). `directive` is the host-side narrator
    briefing (never stored). `term_id` is the terminal event the consequence
    chains to via `caused_by`, so the situation lens surfaces it as a live
    thread (generator fuel) on re-entry."""
    arc_id: str
    lifecycle: str
    term_id: str
    entity: str
    attribute: str
    value: str
    directive: str


#: delta_type → the standing world-consequence its UNRESOLVED arc leaves behind.
#: A deterministic phrasing map (no model call in P1): the attribute/value is the
#: canon consequence row; `say` is the diegetic acknowledgment directive. tension
#: is (entity, stronger_drive, weaker_drive); the consequence records that the
#: drive the arc meant to resolve was left standing.
#: Phrasings are CHARACTER-ARC shaped (keyed on delta_type), NOT genre-specific:
#: they describe how a person was left unchanged, and the narrator re-voices them
#: in the world's own style (noir, fantasy, sci-fi…). Keep them genre-neutral so
#: they don't bias the render toward any one kind of story (founder, P2).
_FALLOUT = {
    "drive_inverted": (
        "unchecked_drive",
        "{say}'s {strong} was never overcome — it still rules them."),
    "desire_at_cost": (
        "desire_unresolved",
        "{say}'s aim was neither won nor surrendered — it hangs unresolved."),
    "desire_renounced": (
        "desire_ungiven",
        "{say} never let go of {strong}; it still holds them."),
    "identity_accepted": (
        "identity_unreconciled",
        "{say} never came to terms with who they are — the rift remains."),
    "homecoming_changed": (
        "homecoming_denied",
        "{say} never returned changed — the way back stays closed."),
}
_DEFAULT_FALLOUT = ("arc_unresolved",
                    "{say}'s story closed unresolved — the stakes linger.")


def _human(entity: str) -> str:
    """A readable name for an entity id, for the narrator directive (not stored). A `person:` slug
    is a proper NAME → Title-Case it (founder blind test: 'clara_vale' addressed as lowercase 'clara
    vale'); obj/place stay lowercase so prose reads naturally ('you lift the brass token')."""
    local = entity.split(":", 1)[-1].replace("_", " ")
    return local.title() if str(entity).startswith("person:") else local


#: The settled-death vocabulary (word-boundary matched). Deliberately NARROW:
#: eligibility rejects only the explicit corpse — "body"-class words (the
#: scene-image surface uses them) are too loose here (bodyguard, busybody).
_SETTLED_DEATH_WORDS = ("dead", "slain", "corpse", "killed", "lifeless",
                        "murdered")


def person_can_act(reads: Any, entity: str) -> bool:
    """CLOSED action-eligibility for a person in CURRENT canon (cr D3 round
    5): ONE predicate shared by repair walkability and any delivery/NPC
    eligibility read, so the two can never diverge on whether a person can
    act. False on an explicit settled death — `alive` false-ish, `dead`
    true-ish, or a death word on role/state/condition/status. Absent rows
    are ELIGIBLE (most living cast carry no liveness rows; this rejects
    only the explicit corpse). Fail-open on read errors — the witness
    driving-entity gate still stands above it."""
    import re as _re
    try:
        if str(reads.state(entity, "alive") or "").strip().lower() in (
                "false", "no", "0"):
            return False
        if str(reads.state(entity, "dead") or "").strip().lower() in (
                "true", "yes", "1"):
            return False
        blob = " ".join(str(reads.state(entity, a) or "")
                        for a in ("role", "state", "condition", "status")
                        ).lower()
        return not any(_re.search(rf"\b{w}\b", blob)
                       for w in _SETTLED_DEATH_WORDS)
    except Exception:  # noqa: BLE001
        return True


def _required_unreachable(reads: Any, arc: Arc) -> bool:
    """Is a REQUIRED beat closed (its `unreachable_if` fired)? The path-foreclosed
    half of `incompletable`. Reads beat statuses `beat_pass` already wrote."""
    for beat in active_beats(reads, arc):
        if beat.weight is Weight.REQUIRED and \
                reads.state(beat.beat_id, "status", frame=PLOT) == "closed":
            # a closure whose beat has been SUPERSEDED is repaired, not
            # foreclosed — active_beats already swapped it out, so any closed
            # beat still HERE is genuinely unrepaired (§3 R4).
            return True
    return False


def _repair_exhausted(reads: Any, arc: Arc) -> bool:
    """Is repair exhausted? DRIFT-HANDLING D3 completes the P1 reservation:
    exhausted == the universal refusal backstop has fired, OR the arc's
    repair BUDGET is spent (committed replace/re-open repairs counted off the
    durable `repair_charge_<n>` plot rows — atomic with each repair's own
    batch, cr D3 blocker 5). A freshly-closed required beat with
    budget remaining and the refusal armed is NOT incompletable — the hard
    rule (PB letter 072 §5): incompletable is repair-EXHAUSTED, never
    first-unreachable. Note `_required_unreachable` (above) already sees only
    UNREPAIRED closures — a superseded/reopened beat left the closed set."""
    from construct.arc.conditions import ClockFired
    if evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE:
        return True
    from construct.arc.drift import REPAIR_BUDGET, repair_spent
    return repair_spent(reads, arc.arc_id) >= REPAIR_BUDGET


def _cancelled(reads: Any, arc: Arc) -> bool:
    """Was this arc explicitly cancelled (a host-written `event:arc_cancelled_<id>`
    in the session frame)? Reserved authoring escape hatch — no P1 path emits it
    automatically. Read via `events()` (a D3 round-3 oracle exposed the
    latent defect here: an `event:`-classified row never folds through
    `state()` — the `_last_try_turn` lesson — so the old state() read could
    never see a naturally-written cancellation); the state() fallback keeps
    any legacy non-event-classified row honored."""
    slug = arc.arc_id.split(":", 1)[1]
    eid = f"event:arc_cancelled_{slug}"
    try:
        if any(e.event_id == eid
               for e in reads.events(kind="arc_cancelled", frame=SESSION)):
            return True
    except Exception:  # noqa: BLE001 — fall through to the legacy read
        pass
    return reads.state(eid, "kind", frame=SESSION) == "arc_cancelled"


def arc_lifecycle(reads: Any, arc: Arc) -> str:
    """Classify the arc: `won | lost | cancelled | incompletable | active`.
    Won-first (it's the strongest signal — reuses `arc_outcome`). `incompletable`
    is checked BEFORE `lost` so a foreclosed path is named precisely rather than
    read as a mere timeout; both require the refusal backstop, so the ordering
    only refines the diagnosis. Derived each tick; the host persists transitions."""
    outcome = arc_outcome(reads, arc)
    if outcome == "won":
        return "won"
    if _cancelled(reads, arc):
        return "cancelled"
    if _required_unreachable(reads, arc) and _repair_exhausted(reads, arc):
        return "incompletable"
    if outcome == "lost":
        return "lost"
    return "active"


def stored_lifecycle(reads: Any, arc: Arc) -> str:
    """The persisted lifecycle state (so re-entry never re-fires fallout)."""
    return reads.state(arc.arc_id, "lifecycle", frame=PLOT) or "active"


def set_lifecycle(world: Any, arc: Arc, value: str, turn: int) -> None:
    world.porcelain.ingest_structured([
        {"entity": arc.arc_id, "attribute": "lifecycle", "value": value,
         "valid_from": turn_time(turn)},
    ], frame=PLOT)


def emit_fallout(world: Any, arc: Arc, lifecycle: str, turn: int) -> Fallout:
    """Write the dead arc's standing world-CONSEQUENCE to canon (the membrane:
    a true world-fact with `caused_by` → the terminal event, via the ingestor
    doorway — exactly the `clock_pass` effect-commit pattern). Returns the Fallout
    record (the narrator directive is host-side, never stored). The DERIVED notion
    "this is dramatic tension" is NEVER written — only the concrete consequence."""
    slug = arc.arc_id.split(":", 1)[1]
    term_id = f"event:arc_terminal_{slug}"
    entity, strong, _weak = arc.shape.tension
    attribute, say = _FALLOUT.get(arc.shape.delta_type, _DEFAULT_FALLOUT)
    canon = [
        {"entity": term_id, "attribute": "kind", "value": "arc_terminal",
         "valid_from": turn_time(turn)},
        {"entity": entity, "attribute": attribute, "value": strong,
         "caused_by": term_id, "valid_from": turn_time(turn)},
    ]
    world.porcelain.ingest_structured(canon)  # canon — a true world consequence
    directive = say.format(say=_human(entity), strong=_human(strong))
    logger.info("arc fallout: %s -> %s (%s.%s=%s caused_by %s)",
                arc.arc_id, lifecycle, entity, attribute, strong, term_id)
    return Fallout(arc_id=arc.arc_id, lifecycle=lifecycle, term_id=term_id,
                   entity=entity, attribute=attribute, value=strong,
                   directive=directive)
