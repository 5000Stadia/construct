"""The arc/clock commit halves (ARC-LAYER §2.4, §3; TURN-LOOP §2).

The evaluation halves live in `conditions`/`lint` (pure logic); this
module owns the COMMITS — every write goes through
`porcelain.ingest_structured(frame=...)`, the sanctioned doorway.
Clock effects land in canon (world consequences, `caused_by`-chained);
firing events, beat statuses, and pacing receipts land in the
host-owned frames.
"""

from __future__ import annotations

import contextvars
import json
import logging
from dataclasses import dataclass
from typing import Any

from construct.arc.conditions import PacingCounters, Truth, evaluate
from construct.arc.grammar import Arc, Phase, Pillar, Rung, Weight

#: Lifecycle terminals (LIVING-WORLD-GENERATOR §3). `active` is the live state;
#: the four terminals are reached at most once each. `won` ends a story (main
#: arc); the three non-won terminals emit FALLOUT (a standing world-consequence
#: that seeds later generation) and, for the main arc in win_loss, end the story.
LIFECYCLE_TERMINALS = ("won", "lost", "cancelled", "incompletable")

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
        marks = [r.valid_from for r in world.buffer.all_rows()
                 if getattr(r, "valid_from", None) is not None]
    except Exception:  # never let the epoch computation sink a build
        logger.exception("compute_entry_epoch: all_rows read failed; using TURN_EPOCH")
        marks = []
    hi = max(marks) if marks else 0.0
    # When TURN_EPOCH already sits above every authored row (the normal case — small chapter
    # coordinates 1..n), keep it EXACTLY (a true no-op for one-timeframe worlds). Only raise
    # when a row reaches/exceeds the epoch (the calendar-year leak), clearing it by the margin.
    return TURN_EPOCH if hi < TURN_EPOCH else hi + ENTRY_MARGIN


def turn_time(turn: int) -> float:
    return current_epoch() + float(turn)


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
    _epoch = current_epoch()
    last_mark_turn = max((m - _epoch for m in marks
                          if m is not None and m >= _epoch), default=0)
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


def arc_outcome(reads: Any, arc: Arc) -> str | None:
    """Win/loss classification (WIN-LOSS-CONDITIONS §10), evaluated after the
    full tick. **Total priority, won-first:** `"won"` if the destination's
    `world_condition` holds — reaching the climax is the stronger, more specific
    signal, so it WINS a same-tick tie with the refusal clock (protecting player
    agency); else `"lost"` if a failure terminal holds — the refusal clock fired,
    or the arc's optional `failure_when` Expr; else `None`. Deliberately NOT
    triggered by an unreachable REQUIRED beat — that is the repair trigger with
    the refusal clock as backstop (Cx 063), never an immediate loss. The host
    decides whether to terminate on this; the engine only supplies the atoms."""
    from construct.arc.conditions import ClockFired

    if evaluate(arc.shape.world_condition, reads) is Truth.TRUE:
        return "won"
    if evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE:
        return "lost"
    if arc.failure_when is not None and evaluate(arc.failure_when, reads) is Truth.TRUE:
        return "lost"
    return None


# --- pillar coverage (STORY-SHAPES §0a/§8 — conclusion as effect) -------
#: Tri-state coverage of a causal pillar, computed host-side from the player
#: frame. The conclusory scene is the NARRATED EFFECT of this coverage; it is
#: never a win/loss gate.
COVERAGE = ("genuine", "false", "unfilled")


def pillar_coverage(reads: Any, pillar: Pillar) -> str:
    """Coverage of ONE pillar from the player frame. 'genuine' wins a tie with
    'false' — a real cause established trumps a lingering red herring."""
    if pillar.genuine_via is not None and \
            evaluate(pillar.genuine_via, reads) is Truth.TRUE:
        return "genuine"
    if pillar.false_via is not None and \
            evaluate(pillar.false_via, reads) is Truth.TRUE:
        return "false"
    return "unfilled"


def arc_coverage(reads: Any, arc: Arc) -> dict[str, str]:
    """{pillar_id: coverage} across all the arc's pillars (host-side; the engine
    never infers pillar coverage). Empty when the arc declares no pillars."""
    return {p.pillar_id: pillar_coverage(reads, p) for p in arc.pillars}


def coverage_summary(reads: Any, arc: Arc) -> dict:
    """Digest of pillar coverage for the conclusory scene + the convergence pull.
    Counts are over REQUIRED pillars (the causes that must be addressed; optional
    pillars enrich but never gate). `complete` = every required pillar is covered
    one way or the other (genuine OR false) — the case is ready to land, soundly or
    not; `sound` = every required pillar GENUINELY covered (a clean case)."""
    cov = arc_coverage(reads, arc)
    required = [p.pillar_id for p in arc.pillars if p.required]
    genuine = [pid for pid in required if cov[pid] == "genuine"]
    false = [pid for pid in required if cov[pid] == "false"]
    unfilled = [pid for pid in required if cov[pid] == "unfilled"]
    return {
        "coverage": cov,
        "required": required,
        "genuine": genuine,
        "false": false,
        "unfilled": unfilled,
        "complete": bool(required) and not unfilled,
        "sound": bool(required) and len(genuine) == len(required),
    }


def conclusion_from_coverage(summary: dict, *,
                             cost_disposition: str = "peril_redemption",
                             world_event: str | None = None,
                             cost_weight: float = 0.0) -> dict | None:
    """Map pillar coverage → the conclusory OUTCOME_SHAPE, as the EFFECT of the causes
    the player put in place — NEVER a win/loss verdict (STORY-SHAPES §0a, CATALOG §0).

    `summary` is `coverage_summary(...)`. `cost_disposition` sets the polarity (CATALOG §0
    finding 3): `peril_redemption`/`repair`/`sacrifice` read GENUINE coverage as the sound
    ending and FALSE as the wrong/costly one; `fail_forward` (comedy) INVERTS it — a
    false-filled engine pillar means the comic engine is LIVE (the desired blowup),
    `genuine` (defused) is the anticlimax, all-`unfilled` is the damp squib. `world_event`
    ('win'|'loss'|None) is read ALONGSIDE coverage for shapes whose ending also reads an
    external result (finding 5 — Contest's scoreboard: sound coverage + 'loss' = "proved
    himself, lost the decision" = costly_victory; 'win' on an unsound-but-complete case =
    a hollow bittersweet). `cost_weight` in [0,1] is the run's accrued-cost integral; it
    downgrades a clean win toward costly_victory (the §0a "integral of the whole run").

    Returns {outcome∈OUTCOME_SHAPES, sound, effect_sound, wrong_case, basis} or None when
    the arc declares no required pillars (→ the legacy world_condition terminal owns close).
    `sound` = all required GENUINE (polarity-independent; used by delta_type). `effect_sound`
    = the conclusion is the INTENDED/positive resolution UNDER this cost_disposition (CATALOG
    §0 finding 3 / Cx 027 — for fail_forward a live comic blowup is effect-sound even though
    nothing is genuine). `wrong_case` = the player committed to a MISTAKEN case (a false-
    filled required cause) → the curtain twist is warranted; ALWAYS False under fail_forward
    (a false-fill there is success fuel, never a wrong case)."""
    required = summary.get("required") or []
    if not required:
        return None
    genuine, false_, unfilled = (summary["genuine"], summary["false"], summary["unfilled"])
    all_genuine, complete = summary["sound"], summary["complete"]
    high_cost = cost_weight >= 0.5

    if cost_disposition == "fail_forward":
        # Comedy inverts: false == the comic engine is LIVE (the desired blowup); genuine ==
        # defused (anticlimax); unfilled == never lit (damp squib). A false-fill is SUCCESS,
        # never a wrong case → wrong_case is always False. `cost_weight` here must be
        # collateral-derived, NOT false-count (the caller honors this — Cx 027 blocker 3).
        live, unlit = len(false_), len(unfilled)
        if live == len(required):
            outcome = "costly_victory" if high_cost else "triumph"  # comeuppance vs warm
            basis = "comic engine fully live → " + ("comeuppance" if high_cost else "warm blowup")
        elif live >= 1:
            outcome, basis = "partial", "a near-miss collision; some fuses lit"
        elif unlit == len(required):
            outcome, basis = "quiet_failure", "the damp squib — nothing was ever lit"
        else:
            outcome, basis = "partial", "the anticlimax — everything tidily defused"
        effect_sound = outcome in ("triumph", "costly_victory", "partial")
        return {"outcome": outcome, "sound": all_genuine, "effect_sound": effect_sound,
                "wrong_case": False, "basis": basis}

    # Normal polarity (genuine is the sound fill; a false-filled required cause = wrong case).
    wrong_case = bool(false_)
    if all_genuine:
        if world_event == "loss":  # Rocky: proved on the causes, the external result went against
            outcome, basis = "costly_victory", \
                "proved on the causes, though the external result went against"
        else:
            outcome = "costly_victory" if high_cost else "triumph"
            basis = "all causes genuinely established" + (" at heavy cost" if high_cost else "")
    elif complete:  # every required pillar covered, but ≥1 falsely → a wrong/mixed case lands
        outcome, basis = "bittersweet", \
            "the case concludes but rests on a false cause — it lands wrongly"
    elif world_event == "win" and genuine:  # a scoreboard win on an unsound case = hollow
        outcome, basis = "bittersweet", \
            "won the external result, but the proof was never truly earned"
    elif genuine:  # partial progress, some causes still open at a forced close
        outcome, basis = "partial", "some causes established, others left open"
    elif false_:  # built only on red herrings
        outcome, basis = "failure", "the case rests entirely on false causes"
    else:  # nothing established
        outcome, basis = "quiet_failure", "the causes were never established"
    return {"outcome": outcome, "sound": all_genuine, "effect_sound": all_genuine,
            "wrong_case": wrong_case, "basis": basis}


#: TRANSFORMATION reconciliation (CATALOG §0 finding 4): the arc's ConclusionShape
#: `delta_type` should DERIVE from pillar coverage, not be declared in parallel.
def delta_type_from_coverage(summary: dict) -> str | None:
    """Derive the character-delta type from pillar coverage (Transformation). All causes
    genuine → `drive_inverted` (the change holds); partial-genuine → `desire_renounced`
    (turned from the old life, repair unfinished); else None (no inversion — the old self
    persists). Keeps delta_type a FUNCTION of coverage so a declared delta can't contradict
    the pillar state. None when no required pillars."""
    if not (summary.get("required") or []):
        return None
    if summary["sound"]:
        return "drive_inverted"
    if summary["genuine"]:
        return "desire_renounced"
    return None


# --- conclusive outcomes (CONCLUSIVE-OUTCOME-SPEC C1, Gate A) -----------
#: The narrative-shaped ending vocabulary (host enum, NOT engine). Replaces the
#: binary won/lost AT THE PLAYER-FACING terminal receipt; `arc_outcome`/
#: `arc_lifecycle` stay binary internally. `pyrrhic` was collapsed into
#: `costly_victory` (overlap destabilizes the judge — Cx Q-S1). The free
#: `outcome_gloss` carries the specifics.
OUTCOME_SHAPES = ("triumph", "costly_victory", "bittersweet",
                  "partial", "failure", "quiet_failure")

_PHASE_ORDER = {Phase.SETUP: 0, Phase.RISING: 1, Phase.CRISIS: 2,
                Phase.CLIMAX: 3, Phase.FALLING: 4}


def climax_ready(reads: Any, arc: Arc) -> bool:
    """Has the arc reached climax readiness — K of its `climax_ready_beats`
    achieved? (Fields existed; this is the one interpretation tests pin — Cx C1#2.)"""
    if not arc.climax_ready_beats:
        return False
    got = sum(1 for bid in arc.climax_ready_beats
              if reads.state(bid, "status", frame=PLOT) == "achieved")
    return got >= arc.climax_ready_k


def current_phase(reads: Any, arc: Arc) -> Phase:
    """Deterministically derive the arc's current dramatic phase from world state
    (Cx C1#1 — no persisted phase exists). Concluded → FALLING; climax-ready →
    CLIMAX; else the furthest phase among ACHIEVED beats (default SETUP)."""
    if arc_concluded(reads, arc):
        return Phase.FALLING
    if climax_ready(reads, arc):
        return Phase.CLIMAX
    achieved = [b.phase for b in arc.beats
                if reads.state(b.beat_id, "status", frame=PLOT) == "achieved"]
    if not achieved:
        return Phase.SETUP
    return max(achieved, key=lambda p: _PHASE_ORDER[p])


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
    """A readable name for an entity id, for the narrator directive (not stored)."""
    return entity.split(":", 1)[-1].replace("_", " ")


def _required_unreachable(reads: Any, arc: Arc) -> bool:
    """Is a REQUIRED beat closed (its `unreachable_if` fired)? The path-foreclosed
    half of `incompletable`. Reads beat statuses `beat_pass` already wrote."""
    for beat in arc.beats:
        if beat.weight is Weight.REQUIRED and \
                reads.state(beat.beat_id, "status", frame=PLOT) == "closed":
            return True
    return False


def _repair_exhausted(reads: Any, arc: Arc) -> bool:
    """Is repair exhausted? **P1 operationalization:** no repair generator exists
    yet, so "exhausted" == the universal refusal backstop has fired. A freshly-
    closed required beat with the refusal clock still ARMED is therefore NOT
    incompletable — the hard rule (PB letter 072 §5): incompletable is repair-
    exhausted, never first-unreachable. Reserve a `repair_budget` counter here
    for P2's repair attempts."""
    from construct.arc.conditions import ClockFired
    return evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE


def _cancelled(reads: Any, arc: Arc) -> bool:
    """Was this arc explicitly cancelled (a host-written `event:arc_cancelled_<id>`
    in the session frame)? Reserved authoring escape hatch — no P1 path emits it
    automatically."""
    slug = arc.arc_id.split(":", 1)[1]
    return reads.state(f"event:arc_cancelled_{slug}", "kind",
                       frame=SESSION) == "arc_cancelled"


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


def arc_protected_keys(arc: Arc) -> set[tuple[str, str]]:
    """The `(entity, attribute)` KEYS the hidden arc turns on — its beats'
    conditions + the destination + premise (GATED-INGEST-COHORT, momentous
    default-deny, option A). The ingest gate default-denies a NEW, UNLICENSED
    narrator assertion of one of these (it would hand away the answer / grant
    the win), routing it to quarantine for arc review; ordinary detail on the
    SAME entities (a different attribute) still promotes — so improv isn't
    strangled, only the load-bearing facts are protected."""
    from construct.arc.conditions import InFrame, StateIs, atoms_of

    keys: set[tuple[str, str]] = set()
    exprs = [b.achievable_via for b in arc.beats]
    exprs += [b.unreachable_if for b in arc.beats if b.unreachable_if]
    exprs += [arc.shape.world_condition, arc.shape.premise]
    # PILLAR CLUE FACTS are load-bearing answers too (Cx 041): the genuine/false coverage
    # conditions reference the clue facts the player must EARN through play. Protect them so
    # no narrator path (incl. card-weaving's deliver_card) can promote/mirror an unearned
    # clue — only the authorized interview-delivery write (`learn_clue_items` straight to
    # knows:<protagonist>) lands them.
    for pillar in arc.pillars:
        if pillar.genuine_via is not None:
            exprs.append(pillar.genuine_via)
        if pillar.false_via is not None:
            exprs.append(pillar.false_via)
    for expr in exprs:
        for atom in atoms_of(expr):
            if isinstance(atom, (StateIs, InFrame)):
                keys.add((atom.entity, atom.attribute))
    return keys


def arc_entities(arc: Arc) -> set[str]:
    """Entity ids the arc references (for arc_touch detection and the
    irony-delta scope)."""
    from construct.arc.conditions import atoms_of
    from construct.arc.lint import _entity_referents

    out: set[str] = set()
    exprs = [b.achievable_via for b in arc.beats]
    exprs += [b.unreachable_if for b in arc.beats if b.unreachable_if]
    exprs += [arc.shape.world_condition, arc.shape.premise]
    # Pillar coverage conditions reference the clue FACT entities (STORY-SHAPES §8 / Cx 032
    # blocker 1): include them so the scenario scope surfaces the clues the player gathers.
    for pillar in arc.pillars:
        if pillar.genuine_via is not None:
            exprs.append(pillar.genuine_via)
        if pillar.false_via is not None:
            exprs.append(pillar.false_via)
    for expr in exprs:
        for atom in atoms_of(expr):
            out.update(_entity_referents(atom))
    out.add(arc.protagonist)
    return out
