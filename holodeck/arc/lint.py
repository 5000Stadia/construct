"""Arc lint — the deterministic validity checks (ARC-LAYER §9).

Run at session zero and after every repair. Checks are numbered to match
the design doc. Where a check operationalizes a softer design statement,
the docstring says exactly how (v1 operationalizations are deliberate
and revisable with play data).
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass

from holodeck.arc.conditions import (
    COUNTER_ATOMS,
    BeatAchieved,
    ClockFired,
    InFrame,
    Located,
    Occurred,
    StateIs,
    Truth,
    WorldReads,
    atoms_of,
    evaluate,
)
from holodeck.arc.grammar import Arc, Beat, Rung, Weight

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LintFinding:
    check: str
    message: str


def _entity_referents(atom: object) -> list[str]:
    """Entity ids an atom's evaluation depends on existing."""
    if isinstance(atom, StateIs):
        return [atom.entity]
    if isinstance(atom, Located):
        return [atom.entity, atom.place]
    if isinstance(atom, InFrame):
        return [atom.entity]
    if isinstance(atom, Occurred):
        return list(atom.participants)
    return []


def lint_arc(arc: Arc, world: WorldReads, session_length_turns: int | None = None) -> list[LintFinding]:
    findings: list[LintFinding] = []
    beat_ids = {b.beat_id for b in arc.beats}

    # Check 1 — every atom references existing entities/frames (or known
    # frontier: an unknown entity is an authoring error, a thunk is not).
    for beat in arc.beats:
        exprs = [beat.achievable_via] + ([beat.unreachable_if] if beat.unreachable_if else [])
        for expr in exprs:
            for atom in atoms_of(expr):
                for entity in _entity_referents(atom):
                    if not world.has_entity(entity):
                        findings.append(LintFinding(
                            "1-referents",
                            f"beat {beat.beat_id}: unknown entity {entity!r}",
                        ))
                if isinstance(atom, BeatAchieved) and atom.beat_id not in beat_ids:
                    findings.append(LintFinding(
                        "1-referents",
                        f"beat {beat.beat_id}: unknown beat {atom.beat_id!r}",
                    ))

    # Check 2 — path-independence: ≥2 satisfying subsets of the climax
    # sufficiency set whose precondition atom sets are disjoint.
    # v1 operationalization: among k-combinations of the climax beats,
    # two combinations exist whose unioned achievable_via atoms share
    # nothing.
    climax_beats = [arc.beat(bid) for bid in arc.climax_ready_beats if bid in beat_ids]
    if len(climax_beats) < len(arc.climax_ready_beats):
        findings.append(LintFinding(
            "2-paths", "climax_ready references beats missing from the arc"))
    else:
        combos = list(itertools.combinations(climax_beats, arc.climax_ready_k))
        disjoint_pair_found = False
        for left, right in itertools.combinations(combos, 2):
            left_atoms = {a for b in left for a in atoms_of(b.achievable_via)}
            right_atoms = {a for b in right for a in atoms_of(b.achievable_via)}
            if left_atoms and right_atoms and not (left_atoms & right_atoms):
                disjoint_pair_found = True
                break
        if not disjoint_pair_found:
            findings.append(LintFinding(
                "2-paths",
                "no two disjoint precondition paths into the climax "
                "sufficiency set (path-independence fails)",
            ))

    # Check 3 — every required beat has a bound escalation clock.
    bound = {c.bound_to for c in arc.clocks if c.rung is not None}
    for beat in arc.beats:
        if beat.weight is Weight.REQUIRED and beat.beat_id not in bound:
            findings.append(LintFinding(
                "3-clocks", f"required beat {beat.beat_id} has no bound escalation clock"))

    # Check 4 — the refusal clock: exists, counter-only condition,
    # threshold reachable within the total phase budget.
    refusal = arc.refusal_clock
    if refusal.rung is not Rung.REFUSAL:
        findings.append(LintFinding("4-refusal", "refusal clock not tagged rung=REFUSAL"))
    non_counter = [a for a in atoms_of(refusal.fires_when) if not isinstance(a, COUNTER_ATOMS)]
    if non_counter:
        findings.append(LintFinding(
            "4-refusal",
            f"refusal clock condition must be counter-only; found {non_counter!r}",
        ))
    if arc.phase_budget:
        total_budget = sum(arc.phase_budget.values())
        thresholds = [a.at_least for a in atoms_of(refusal.fires_when)
                      if isinstance(a, COUNTER_ATOMS)]
        if thresholds and min(thresholds) > total_budget:
            findings.append(LintFinding(
                "4-refusal",
                "refusal threshold exceeds the total phase budget — unreachable",
            ))

    # Check 5 — no beat gates on raw plot: facts (only the sanctioned
    # BeatAchieved / ClockFired forms).
    for beat in arc.beats:
        for atom in atoms_of(beat.achievable_via):
            if isinstance(atom, (StateIs, InFrame)):
                frame = getattr(atom, "frame", "canon")
                if str(frame).startswith("plot:"):
                    findings.append(LintFinding(
                        "5-plot-gating",
                        f"beat {beat.beat_id} gates on raw plot: frame content",
                    ))

    # Check 6 — phase budgets sum to the session-length intent.
    if session_length_turns is not None:
        total = sum(arc.phase_budget.values())
        if total != session_length_turns:
            findings.append(LintFinding(
                "6-budget",
                f"phase budgets sum to {total}, session intent is {session_length_turns}",
            ))

    # Check 7 — confront-rung effects are world-scale: fires_when must
    # not reference the protagonist's location or any person's survival;
    # effects must not reference the protagonist. (v1 operationalization
    # of "no specific NPC's survival, no player location".)
    for clock in arc.clocks:
        if clock.rung is not Rung.CONFRONT:
            continue
        for atom in atoms_of(clock.fires_when):
            if isinstance(atom, Located) and atom.entity == arc.protagonist:
                findings.append(LintFinding(
                    "7-confront", f"clock {clock.clock_id} depends on player location"))
            if isinstance(atom, StateIs) and atom.attribute in ("alive", "dead") \
                    and atom.entity.startswith("person:"):
                findings.append(LintFinding(
                    "7-confront", f"clock {clock.clock_id} depends on NPC survival"))
        for effect in clock.effects:
            if arc.protagonist in str(effect.values()):
                findings.append(LintFinding(
                    "7-confront",
                    f"clock {clock.clock_id} effect references the protagonist",
                ))

    return findings


def lint_post_repair(replacement_beats: list[Beat], world: WorldReads) -> list[LintFinding]:
    """Check 8 — the novelty check (§7): a repair may not reintroduce the
    impossibility that forced it. Every replacement beat must (a) have
    referents that still exist and (b) not have its unreachable_if
    already TRUE against current canon."""
    findings: list[LintFinding] = []
    for beat in replacement_beats:
        for atom in atoms_of(beat.achievable_via):
            for entity in _entity_referents(atom):
                if not world.has_entity(entity):
                    findings.append(LintFinding(
                        "8-novelty",
                        f"replacement beat {beat.beat_id}: referent {entity!r} "
                        f"does not exist — already impossible",
                    ))
        if beat.unreachable_if is not None:
            verdict = evaluate(beat.unreachable_if, world)
            if verdict is Truth.TRUE:
                findings.append(LintFinding(
                    "8-novelty",
                    f"replacement beat {beat.beat_id}: unreachable_if already "
                    f"TRUE — repair reintroduces its own trigger",
                ))
    return findings
