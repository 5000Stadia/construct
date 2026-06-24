"""Pillar coverage — the conclusion-as-effect spine (STORY-SHAPES §0a/§8).

A pillar is a CAUSE; its coverage (genuine / false / unfilled), computed host-side
from the PLAYER frame, determines the narrated conclusory scene (the effect), never a
win/loss verdict. These guard the tri-state computation + the required-pillar digest.
"""

from construct.arc.conditions import InFrame
from construct.arc.executor import (
    COVERAGE,
    OUTCOME_SHAPES,
    arc_coverage,
    conclusion_from_coverage,
    coverage_summary,
    delta_type_from_coverage,
    pillar_coverage,
)
from construct.arc.grammar import (
    Arc,
    Clock,
    ConclusionShape,
    Phase,
    Pillar,
    Weight,
)

from tests.fixtureworld import FixtureWorld


def _world(player_knows: set) -> FixtureWorld:
    """A world whose player frame holds exactly `player_knows` (entity,attr,value)."""
    return FixtureWorld(
        entities={"person:player", "person:cray", "person:porter", "obj:ledger"},
        states={},
        chains={},
        frames={"knows:person:player": set(player_knows)},
        event_log={},
    )


def _arc(pillars: tuple[Pillar, ...]) -> Arc:
    """A minimal arc carrying only the pillars under test (the rest is inert)."""
    shape = ConclusionShape(
        shape_id="shape:t", delta_type="desire_at_cost",
        tension=("person:player", "truth", "ease"),
        world_condition=InFrame("knows:person:player", "x", "y", "z"),
        premise=InFrame("knows:person:player", "x", "y", "z"),
        refusal_variant_id="refusal:t",
    )
    refusal = Clock(clock_id="clock:refusal", fires_when=shape.world_condition, effects=())
    return Arc(
        arc_id="arc:main", protagonist="person:player", shape=shape,
        beats=(), clocks=(), refusal_clock=refusal,
        climax_ready_k=1, climax_ready_beats=(), pillars=pillars,
    )


# the genuine vs false clue facts for the "means" pillar
_GENUINE = InFrame("knows:person:player", "fact:means", "established", "true")
_FALSE = InFrame("knows:person:player", "fact:means", "blamed", "person:porter")


def test_pillar_unfilled_when_no_clue_surfaced():
    p = Pillar("pillar:means", "the means", genuine_via=_GENUINE, false_via=_FALSE)
    assert pillar_coverage(_world(set()), p) == "unfilled"


def test_pillar_genuine_when_genuine_clue_in_player_frame():
    p = Pillar("pillar:means", "the means", genuine_via=_GENUINE, false_via=_FALSE)
    w = _world({("fact:means", "established", "true")})
    assert pillar_coverage(w, p) == "genuine"


def test_pillar_false_when_red_herring_held_as_true():
    p = Pillar("pillar:means", "the means", genuine_via=_GENUINE, false_via=_FALSE)
    w = _world({("fact:means", "blamed", "person:porter")})
    assert pillar_coverage(w, p) == "false"


def test_genuine_wins_tie_with_false():
    # a real cause established trumps a lingering red herring (both present)
    p = Pillar("pillar:means", "the means", genuine_via=_GENUINE, false_via=_FALSE)
    w = _world({("fact:means", "established", "true"),
                ("fact:means", "blamed", "person:porter")})
    assert pillar_coverage(w, p) == "genuine"


def test_coverage_values_are_in_the_enum():
    p = Pillar("pillar:means", "the means", genuine_via=_GENUINE)
    assert pillar_coverage(_world(set()), p) in COVERAGE


def test_arc_coverage_maps_every_pillar():
    pillars = (
        Pillar("pillar:motive", "the motive",
               genuine_via=InFrame("knows:person:player", "fact:motive", "k", "true")),
        Pillar("pillar:means", "the means", genuine_via=_GENUINE),
    )
    w = _world({("fact:means", "established", "true")})
    cov = arc_coverage(w, _arc(pillars))
    assert cov == {"pillar:motive": "unfilled", "pillar:means": "genuine"}


def test_coverage_summary_sound_vs_complete_vs_partial():
    motive = Pillar("pillar:motive", "the motive",
                    genuine_via=InFrame("knows:person:player", "fact:motive", "k", "true"),
                    false_via=InFrame("knows:person:player", "fact:motive", "blamed", "x"))
    means = Pillar("pillar:means", "the means", genuine_via=_GENUINE, false_via=_FALSE)
    flavor = Pillar("pillar:mood", "ambience", required=False, genuine_via=_GENUINE)
    arc = _arc((motive, means, flavor))

    # nothing surfaced → neither complete nor sound
    s0 = coverage_summary(_world(set()), arc)
    assert s0["required"] == ["pillar:motive", "pillar:means"]
    assert not s0["complete"] and not s0["sound"]
    assert s0["unfilled"] == ["pillar:motive", "pillar:means"]

    # both required genuinely covered → complete AND sound (flavor ignored in counts)
    s1 = coverage_summary(_world({("fact:motive", "k", "true"),
                                  ("fact:means", "established", "true")}), arc)
    assert s1["complete"] and s1["sound"]
    assert s1["genuine"] == ["pillar:motive", "pillar:means"]

    # one genuine, one red herring → complete (case lands) but NOT sound (wrong case)
    s2 = coverage_summary(_world({("fact:motive", "k", "true"),
                                  ("fact:means", "blamed", "person:porter")}), arc)
    assert s2["complete"] and not s2["sound"]
    assert s2["false"] == ["pillar:means"]


def test_no_pillars_is_backward_compatible_empty():
    arc = _arc(())
    assert arc_coverage(_world(set()), arc) == {}
    s = coverage_summary(_world(set()), arc)
    # no required pillars → never "complete"/"sound" (legacy world_condition terminal)
    assert not s["complete"] and not s["sound"] and s["required"] == []


# ---- conclusion as EFFECT of coverage (STORY-SHAPES §0a, CATALOG §0) ---------

def _summary(required, genuine, false_, unfilled):
    """A coverage_summary-shaped dict, built directly for the selector tests."""
    return {
        "required": list(required), "genuine": list(genuine),
        "false": list(false_), "unfilled": list(unfilled),
        "complete": bool(required) and not unfilled,
        "sound": bool(required) and len(genuine) == len(required),
    }


def test_conclusion_none_without_pillars():
    # no required pillars → the legacy world_condition terminal owns the close
    assert conclusion_from_coverage(_summary([], [], [], [])) is None


def test_conclusion_sound_is_triumph():
    s = _summary(["a", "b"], ["a", "b"], [], [])
    r = conclusion_from_coverage(s)
    assert r["outcome"] == "triumph" and r["sound"] and r["outcome"] in OUTCOME_SHAPES


def test_conclusion_sound_at_high_cost_is_costly_victory():
    s = _summary(["a", "b"], ["a", "b"], [], [])
    assert conclusion_from_coverage(s, cost_weight=0.7)["outcome"] == "costly_victory"


def test_conclusion_complete_with_false_is_bittersweet():
    # every required pillar covered, but one on a red herring → it lands WRONGLY
    s = _summary(["a", "b"], ["a"], ["b"], [])
    r = conclusion_from_coverage(s)
    assert r["outcome"] == "bittersweet" and not r["sound"]


def test_conclusion_partial_then_failure_then_quiet():
    # some genuine progress, not complete → partial
    assert conclusion_from_coverage(_summary(["a", "b"], ["a"], [], ["b"]))["outcome"] == "partial"
    # no genuine, a false cause, still incomplete → failure
    assert conclusion_from_coverage(_summary(["a", "b"], [], ["a"], ["b"]))["outcome"] == "failure"
    # every required pillar covered but all on red herrings → it lands wrongly (bittersweet)
    assert conclusion_from_coverage(_summary(["a", "b"], [], ["a", "b"], []))["outcome"] == "bittersweet"
    assert conclusion_from_coverage(_summary(["a"], [], ["a"], []))["outcome"] == "bittersweet"
    # nothing established at all → quiet failure
    assert conclusion_from_coverage(_summary(["a", "b"], [], [], ["a", "b"]))["outcome"] == "quiet_failure"


def test_rocky_case_sound_coverage_plus_scoreboard_loss_is_costly_victory():
    # proved himself, lost the decision (CATALOG §0 finding 5): sound + world loss
    s = _summary(["competence", "rival", "standard"],
                 ["competence", "rival", "standard"], [], [])
    r = conclusion_from_coverage(s, world_event="loss")
    assert r["outcome"] == "costly_victory" and r["sound"]


def test_hollow_win_scoreboard_win_on_unsound_case_is_bittersweet():
    s = _summary(["competence", "standard"], ["competence"], [], ["standard"])
    r = conclusion_from_coverage(s, world_event="win")
    assert r["outcome"] == "bittersweet" and not r["sound"]


def test_farce_inversion_engine_live_is_triumph():
    # fail_forward: a FALSE-filled engine pillar = the comic engine LIVE = the blowup
    s = _summary(["mistaken_id", "fuses"], [], ["mistaken_id", "fuses"], [])
    r = conclusion_from_coverage(s, cost_disposition="fail_forward")
    assert r["outcome"] == "triumph"  # warm comic triumph


def test_farce_inversion_high_collateral_is_comeuppance():
    s = _summary(["mistaken_id", "fuses"], [], ["mistaken_id", "fuses"], [])
    r = conclusion_from_coverage(s, cost_disposition="fail_forward", cost_weight=0.8)
    assert r["outcome"] == "costly_victory"  # comeuppance lands on the deserving


def test_farce_damp_squib_is_the_only_real_failure():
    # everything defused (genuine) = anticlimax; nothing lit (unfilled) = damp squib
    defused = _summary(["mistaken_id", "fuses"], ["mistaken_id", "fuses"], [], [])
    assert conclusion_from_coverage(defused, cost_disposition="fail_forward")["outcome"] == "partial"
    unlit = _summary(["mistaken_id", "fuses"], [], [], ["mistaken_id", "fuses"])
    assert conclusion_from_coverage(unlit, cost_disposition="fail_forward")["outcome"] == "quiet_failure"


def test_wrong_case_flags_a_false_filled_cause_normal_polarity():
    # normal polarity: a false-filled required cause = a wrong case → twist warranted
    assert conclusion_from_coverage(_summary(["a", "b"], ["a"], ["b"], []))["wrong_case"]
    # all genuine → not a wrong case
    assert not conclusion_from_coverage(_summary(["a"], ["a"], [], []))["wrong_case"]
    # incomplete-but-no-false (partial) → not a wrong case (just unfinished)
    assert not conclusion_from_coverage(_summary(["a", "b"], ["a"], [], ["b"]))["wrong_case"]


def test_farce_all_false_is_triumph_not_wrong_case_and_effect_sound():
    # Cx 027 blocker 3: a fully-live farce (all required false) is a WARM triumph, is
    # effect_sound, and is NOT a wrong case — so the unsound-case twist must not fire.
    s = _summary(["mistaken_id", "fuses"], [], ["mistaken_id", "fuses"], [])
    r = conclusion_from_coverage(s, cost_disposition="fail_forward")  # cost_weight defaults 0
    assert r["outcome"] == "triumph"
    assert r["effect_sound"] is True
    assert r["wrong_case"] is False
    assert r["sound"] is False  # 'sound' still means all-genuine — decoupled from effect_sound


def test_delta_type_derives_from_coverage():
    assert delta_type_from_coverage(_summary(["a", "b"], ["a", "b"], [], [])) == "drive_inverted"
    assert delta_type_from_coverage(_summary(["a", "b"], ["a"], [], ["b"])) == "desire_renounced"
    assert delta_type_from_coverage(_summary(["a", "b"], [], [], ["a", "b"])) is None
    assert delta_type_from_coverage(_summary([], [], [], [])) is None
