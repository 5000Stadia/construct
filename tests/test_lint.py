"""Arc lint over a fixture arc — the meter-conspiracy mini arc, green
case plus one violation per check."""

import dataclasses

from construct.arc.conditions import (
    BeatAchieved,
    InFrame,
    Located,
    Occurred,
    StateIs,
    TurnsQuiet,
    AllOf,
)
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.arc.lint import lint_arc, lint_post_repair

from tests.fixtureworld import FixtureWorld


def make_world() -> FixtureWorld:
    return FixtureWorld(
        entities={
            "person:player", "person:clerk", "obj:ledger", "obj:meter",
            "place:wellhead", "place:office", "fact:conspiracy",
        },
    )


def make_arc() -> Arc:
    discover = Beat(
        "beat:discover", Phase.SETUP, Weight.REQUIRED,
        achievable_via=InFrame("knows:player", "fact:conspiracy", "suspected", True),
    )
    evidence = Beat(
        "beat:evidence", Phase.RISING, Weight.REQUIRED,
        achievable_via=StateIs("obj:ledger", "examined", True),
        unreachable_if=StateIs("obj:ledger", "condition", "burned"),
    )
    witness = Beat(
        "beat:witness", Phase.RISING, Weight.OPTIONAL,
        achievable_via=Occurred("confession", participants=("person:clerk",)),
    )
    shape = ConclusionShape(
        "shape:cost_of_truth", "drive_inverted",
        ("person:player", "drive:comfort", "drive:truth"),
        world_condition=BeatAchieved("beat:evidence"),
        premise=StateIs("person:clerk", "alive", True),
        refusal_variant_id="shape:town_falls",
    )
    clocks = (
        Clock("clock:escalate_discover", TurnsQuiet(4),
              effects=({"event": "gossip", "caused_by": "process:conspiracy"},),
              bound_to="beat:discover", rung=Rung.SURFACE),
        Clock("clock:escalate_evidence", TurnsQuiet(6),
              effects=({"event": "meter_dark", "caused_by": "process:conspiracy"},),
              bound_to="beat:evidence", rung=Rung.CONVERGE),
        Clock("clock:blackout", TurnsQuiet(8),
              effects=({"event": "district_blackout", "caused_by": "process:conspiracy"},),
              bound_to="arc:main", rung=Rung.CONFRONT),
    )
    refusal = Clock("clock:refusal", TurnsQuiet(12),
                    effects=({"event": "conclude_refused", "caused_by": "process:conspiracy"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    return Arc(
        arc_id="arc:main",
        protagonist="person:player",
        shape=shape,
        beats=(discover, evidence, witness),
        clocks=clocks,
        refusal_clock=refusal,
        climax_ready_k=1,
        climax_ready_beats=("beat:evidence", "beat:witness"),
        phase_budget={Phase.SETUP: 8, Phase.RISING: 12, Phase.CRISIS: 6,
                      Phase.CLIMAX: 3, Phase.FALLING: 3},
    )


def test_green_arc_lints_clean():
    findings = lint_arc(make_arc(), make_world(), session_length_turns=32)
    assert findings == []


def test_check1_unknown_referent():
    arc = make_arc()
    bad = Beat("beat:bad", Phase.RISING, Weight.OPTIONAL,
               achievable_via=StateIs("obj:nonexistent", "found", True))
    arc = dataclasses.replace(arc, beats=arc.beats + (bad,))
    assert any(f.check == "1-referents" for f in lint_arc(arc, make_world()))


def test_check2_no_disjoint_paths():
    arc = make_arc()
    shared = StateIs("obj:ledger", "examined", True)
    a = Beat("beat:a", Phase.CLIMAX, Weight.OPTIONAL, achievable_via=shared)
    b = Beat("beat:b", Phase.CLIMAX, Weight.OPTIONAL, achievable_via=shared)
    arc = dataclasses.replace(
        arc, beats=arc.beats + (a, b), climax_ready_beats=("beat:a", "beat:b"))
    assert any(f.check == "2-paths" for f in lint_arc(arc, make_world()))


def test_check3_required_beat_without_clock():
    arc = make_arc()
    naked = Beat("beat:naked", Phase.CRISIS, Weight.REQUIRED,
                 achievable_via=StateIs("obj:meter", "repaired", True))
    arc = dataclasses.replace(arc, beats=arc.beats + (naked,))
    assert any(f.check == "3-clocks" for f in lint_arc(arc, make_world()))


def test_check4_refusal_clock_not_counter_only():
    arc = make_arc()
    bad_refusal = dataclasses.replace(
        arc.refusal_clock,
        fires_when=AllOf((TurnsQuiet(12), StateIs("obj:meter", "dark", True))),
    )
    arc = dataclasses.replace(arc, refusal_clock=bad_refusal)
    assert any(f.check == "4-refusal" for f in lint_arc(arc, make_world()))


def test_check4_refusal_threshold_beyond_budget():
    arc = make_arc()
    far = dataclasses.replace(arc.refusal_clock, fires_when=TurnsQuiet(99))
    arc = dataclasses.replace(arc, refusal_clock=far)
    assert any(f.check == "4-refusal" for f in lint_arc(arc, make_world()))


def test_check5_raw_plot_gating():
    arc = make_arc()
    bad = Beat("beat:meta", Phase.RISING, Weight.OPTIONAL,
               achievable_via=InFrame("plot:main", "beat:evidence", "weight", "required"))
    arc = dataclasses.replace(arc, beats=arc.beats + (bad,))
    assert any(f.check == "5-plot-gating" for f in lint_arc(arc, make_world()))


def test_check6_budget_mismatch():
    findings = lint_arc(make_arc(), make_world(), session_length_turns=50)
    assert any(f.check == "6-budget" for f in findings)


def test_check7_confront_depends_on_player_location():
    arc = make_arc()
    bad = Clock("clock:ambush", Located("person:player", "place:wellhead"),
                effects=({"event": "ambush", "caused_by": "process:conspiracy"},),
                bound_to="arc:main", rung=Rung.CONFRONT)
    arc = dataclasses.replace(arc, clocks=arc.clocks + (bad,))
    assert any(f.check == "7-confront" for f in lint_arc(arc, make_world()))


def test_check8_post_repair_novelty():
    world = make_world()
    world.states[("canon", "obj:ledger", "condition")] = "burned"
    repaired = Beat(
        "beat:evidence_v2", Phase.RISING, Weight.REQUIRED,
        achievable_via=StateIs("obj:ledger", "examined", True),
        unreachable_if=StateIs("obj:ledger", "condition", "burned"),
    )
    findings = lint_post_repair([repaired], world)
    assert any(f.check == "8-novelty" for f in findings)

    fresh = Beat(
        "beat:testimony", Phase.RISING, Weight.REQUIRED,
        achievable_via=Occurred("confession", participants=("person:clerk",)),
    )
    assert lint_post_repair([fresh], world) == []
