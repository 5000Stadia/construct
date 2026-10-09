"""Conclusion and coverage: whether the arc has reached its destination, how, and in
what dramatic phase.

Owns `arc_concluded` / `arc_outcome` (won/lost classification), the pillar-coverage
digest (`pillar_coverage`, `arc_coverage`, `coverage_summary`) and the conclusory
OUTCOME_SHAPE derived from it (`conclusion_from_coverage`, `delta_type_from_coverage`,
`OUTCOME_SHAPES`), plus `climax_ready` and `current_phase` (the derived dramatic phase).
The conclusion is the narrated EFFECT of coverage, never a win/loss gate. Re-exported by
`construct.arc.executor`.
"""

from __future__ import annotations

from typing import Any

from construct.arc.conditions import Truth, evaluate
from construct.arc.grammar import (
    Arc, BeatStatus, CostDisposition, Coverage, DeltaType, Outcome, OutcomeShape, Phase,
    Pillar, WorldEvent,
)
from construct.arc.supersession import active_beats, resolve_beat_id
from construct.arc.timeline import PLOT


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


def arc_outcome(reads: Any, arc: Arc) -> Outcome | None:
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
        return Outcome.WON
    if evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE:
        return Outcome.LOST
    if arc.failure_when is not None and evaluate(arc.failure_when, reads) is Truth.TRUE:
        return Outcome.LOST
    return None


# --- pillar coverage (STORY-SHAPES §0a/§8 — conclusion as effect) -------
#: Tri-state coverage of a causal pillar, computed host-side from the player
#: frame. The conclusory scene is the NARRATED EFFECT of this coverage; it is
#: never a win/loss gate.
COVERAGE: tuple[Coverage, ...] = (Coverage.GENUINE, Coverage.FALSE, Coverage.UNFILLED)


def pillar_coverage(reads: Any, pillar: Pillar) -> Coverage:
    """Coverage of ONE pillar from the player frame. 'genuine' wins a tie with
    'false' — a real cause established trumps a lingering red herring."""
    if pillar.genuine_via is not None and \
            evaluate(pillar.genuine_via, reads) is Truth.TRUE:
        return Coverage.GENUINE
    if pillar.false_via is not None and \
            evaluate(pillar.false_via, reads) is Truth.TRUE:
        return Coverage.FALSE
    return Coverage.UNFILLED


def arc_coverage(reads: Any, arc: Arc) -> dict[str, Coverage]:
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
    genuine = [pid for pid in required if cov[pid] == Coverage.GENUINE]
    false = [pid for pid in required if cov[pid] == Coverage.FALSE]
    unfilled = [pid for pid in required if cov[pid] == Coverage.UNFILLED]
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
                             cost_disposition: str = CostDisposition.PERIL_REDEMPTION,
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

    if cost_disposition == CostDisposition.FAIL_FORWARD:
        # Comedy inverts: false == the comic engine is LIVE (the desired blowup); genuine ==
        # defused (anticlimax); unfilled == never lit (damp squib). A false-fill is SUCCESS,
        # never a wrong case → wrong_case is always False. `cost_weight` here must be
        # collateral-derived, NOT false-count (the caller honors this — Cx 027 blocker 3).
        live, unlit = len(false_), len(unfilled)
        if live == len(required):
            outcome = (OutcomeShape.COSTLY_VICTORY if high_cost
                       else OutcomeShape.TRIUMPH)  # comeuppance vs warm
            basis = "comic engine fully live → " + ("comeuppance" if high_cost else "warm blowup")
        elif live >= 1:
            outcome, basis = OutcomeShape.PARTIAL, "a near-miss collision; some fuses lit"
        elif unlit == len(required):
            outcome, basis = OutcomeShape.QUIET_FAILURE, "the damp squib — nothing was ever lit"
        else:
            outcome, basis = OutcomeShape.PARTIAL, "the anticlimax — everything tidily defused"
        effect_sound = outcome in (OutcomeShape.TRIUMPH, OutcomeShape.COSTLY_VICTORY,
                                   OutcomeShape.PARTIAL)
        return {"outcome": outcome, "sound": all_genuine, "effect_sound": effect_sound,
                "wrong_case": False, "basis": basis}

    # Normal polarity (genuine is the sound fill; a false-filled required cause = wrong case).
    wrong_case = bool(false_)
    if all_genuine:
        if world_event == WorldEvent.LOSS:  # Rocky: proved on the causes, the external result went against
            outcome, basis = OutcomeShape.COSTLY_VICTORY, \
                "proved on the causes, though the external result went against"
        else:
            outcome = (OutcomeShape.COSTLY_VICTORY if high_cost
                       else OutcomeShape.TRIUMPH)
            basis = "all causes genuinely established" + (" at heavy cost" if high_cost else "")
    elif complete:  # every required pillar covered, but ≥1 falsely → a wrong/mixed case lands
        outcome, basis = OutcomeShape.BITTERSWEET, \
            "the case concludes but rests on a false cause — it lands wrongly"
    elif world_event == WorldEvent.WIN and genuine:  # a scoreboard win on an unsound case = hollow
        outcome, basis = OutcomeShape.BITTERSWEET, \
            "won the external result, but the proof was never truly earned"
    elif genuine:  # partial progress, some causes still open at a forced close
        outcome, basis = OutcomeShape.PARTIAL, "some causes established, others left open"
    elif false_:  # built only on red herrings
        outcome, basis = OutcomeShape.FAILURE, "the case rests entirely on false causes"
    else:  # nothing established
        outcome, basis = OutcomeShape.QUIET_FAILURE, "the causes were never established"
    return {"outcome": outcome, "sound": all_genuine, "effect_sound": all_genuine,
            "wrong_case": wrong_case, "basis": basis}


#: TRANSFORMATION reconciliation (CATALOG §0 finding 4): the arc's ConclusionShape
#: `delta_type` should DERIVE from pillar coverage, not be declared in parallel.
def delta_type_from_coverage(summary: dict) -> DeltaType | None:
    """Derive the character-delta type from pillar coverage (Transformation). All causes
    genuine → `drive_inverted` (the change holds); partial-genuine → `desire_renounced`
    (turned from the old life, repair unfinished); else None (no inversion — the old self
    persists). Keeps delta_type a FUNCTION of coverage so a declared delta can't contradict
    the pillar state. None when no required pillars."""
    if not (summary.get("required") or []):
        return None
    if summary["sound"]:
        return DeltaType.DRIVE_INVERTED
    if summary["genuine"]:
        return DeltaType.DESIRE_RENOUNCED
    return None


# --- conclusive outcomes (CONCLUSIVE-OUTCOME-SPEC C1, Gate A) -----------
#: The narrative-shaped ending vocabulary (host enum, NOT engine). Replaces the
#: binary won/lost AT THE PLAYER-FACING terminal receipt; `arc_outcome`/
#: `arc_lifecycle` stay binary internally. `pyrrhic` was collapsed into
#: `costly_victory` (overlap destabilizes the judge — Cx Q-S1). The free
#: `outcome_gloss` carries the specifics.
OUTCOME_SHAPES: tuple[OutcomeShape, ...] = (
    OutcomeShape.TRIUMPH, OutcomeShape.COSTLY_VICTORY, OutcomeShape.BITTERSWEET,
    OutcomeShape.PARTIAL, OutcomeShape.FAILURE, OutcomeShape.QUIET_FAILURE)

_PHASE_ORDER = {Phase.SETUP: 0, Phase.RISING: 1, Phase.CRISIS: 2,
                Phase.CLIMAX: 3, Phase.FALLING: 4}


def climax_ready(reads: Any, arc: Arc) -> bool:
    """Has the arc reached climax readiness — K of its `climax_ready_beats`
    achieved? (Fields existed; this is the one interpretation tests pin — Cx C1#2.)"""
    if not arc.climax_ready_beats:
        return False
    # the sealed id TUPLE is never rewritten; each element resolves through
    # the supersession chain at read time (§3 R4 — a replaced climax beat
    # counts via its replacement).
    got = sum(1 for bid in arc.climax_ready_beats
              if reads.state(resolve_beat_id(reads, bid), "status",
                             frame=PLOT) == BeatStatus.ACHIEVED)
    return got >= arc.climax_ready_k


def current_phase(reads: Any, arc: Arc) -> Phase:
    """Deterministically derive the arc's current dramatic phase from world state
    (Cx C1#1 — no persisted phase exists). Concluded → FALLING; climax-ready →
    CLIMAX; else the furthest phase among ACHIEVED beats (default SETUP)."""
    if arc_concluded(reads, arc):
        return Phase.FALLING
    if climax_ready(reads, arc):
        return Phase.CLIMAX
    achieved = [b.phase for b in active_beats(reads, arc)
                if reads.state(b.beat_id, "status", frame=PLOT) == BeatStatus.ACHIEVED]
    if not achieved:
        return Phase.SETUP
    return max(achieved, key=lambda p: _PHASE_ORDER[p])
