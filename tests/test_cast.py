"""The populated cast — clue→pillar distribution, solvability, and the bridge to
coverage (STORY-SHAPES §8). Pure host-side; no model calls.
"""

from construct.arc.executor import arc_coverage, pillar_coverage
from construct.cast import (
    CastNode,
    Clue,
    build_pillars,
    cast_from_proposal,
    cast_seed_plan,
    check_solvability,
    clues_for_pillar,
    floor_clues,
    floor_debt,
    genuine_reachable,
    is_solvable,
    learn_clue_items,
    revealable_clues,
)

from tests.fixtureworld import FixtureWorld

PROT = "person:player"
FRAME = f"knows:{PROT}"


def _world(player_knows: set) -> FixtureWorld:
    return FixtureWorld(entities=set(), states={}, chains={},
                        frames={FRAME: set(player_knows)}, event_log={})


# a small mystery cast: motive (clerk, genuine) + means (porter genuine, + a red herring)
def _cast() -> tuple[CastNode, ...]:
    return (
        CastNode("person:clerk", "witness", "night clerk", holds_clues=(
            Clue("clue:debt", "pillar:motive", ("fact:motive", "is", "debt"),
                 coverage_effect="genuine"),
        )),
        CastNode("person:porter", "suspect", "dock porter", holds_clues=(
            Clue("clue:key", "pillar:means", ("fact:means", "is", "spare_key"),
                 coverage_effect="genuine"),
            # a STRONG red herring pointing means at the wrong person, debunked by clue:key
            Clue("clue:grudge", "pillar:means", ("fact:means", "blamed", "person:cook"),
                 coverage_effect="false", is_red_herring=True, debunked_by="clue:key"),
        )),
    )


REQUIRED = ["pillar:motive", "pillar:means"]


def test_genuine_reachable_counts_only_genuine_nonherring():
    cast = _cast()
    assert genuine_reachable("pillar:motive", cast) == 1
    assert genuine_reachable("pillar:means", cast) == 1  # the red herring does not count
    assert len(clues_for_pillar("pillar:means", cast)) == 2


def test_solvable_when_every_required_pillar_has_a_genuine_clue():
    assert is_solvable(REQUIRED, _cast())
    assert check_solvability(REQUIRED, _cast()) == []


def test_unsolvable_when_a_required_pillar_has_no_genuine_clue():
    cast = (CastNode("person:clerk", holds_clues=(
        Clue("clue:debt", "pillar:motive", ("fact:motive", "is", "debt")),)),)
    problems = check_solvability(["pillar:motive", "pillar:means"], cast)
    assert any("pillar:means" in p for p in problems)


def test_strong_red_herring_needs_a_reachable_debunked_by():
    # missing debunked_by
    cast = (CastNode("person:x", holds_clues=(
        Clue("clue:g", "pillar:means", ("fact:means", "is", "key"), coverage_effect="genuine"),
        Clue("clue:rh", "pillar:means", ("fact:means", "blamed", "y"),
             coverage_effect="false", is_red_herring=True),)),)
    assert any("missing debunked_by" in p for p in check_solvability(["pillar:means"], cast))
    # unreachable debunked_by
    cast2 = (CastNode("person:x", holds_clues=(
        Clue("clue:g", "pillar:means", ("fact:means", "is", "key"), coverage_effect="genuine"),
        Clue("clue:rh", "pillar:means", ("fact:means", "blamed", "y"),
             coverage_effect="false", is_red_herring=True, debunked_by="clue:nope"),)),)
    assert any("unreachable" in p for p in check_solvability(["pillar:means"], cast2))


def test_genuine_clue_behind_unsupported_gate_does_not_count():
    # Cx 032 blocker 2: a required pillar whose only genuine clue is trust/object_seen-gated
    # is NOT live-reachable in v1 → must fail solvability (not silently pass).
    cast = (CastNode("person:x", holds_clues=(
        Clue("clue:g", "pillar:means", ("fact:means", "is", "key"),
             coverage_effect="genuine", reveal_condition="trust"),)),)
    assert genuine_reachable("pillar:means", cast) == 0
    assert any("pillar:means" in p for p in check_solvability(["pillar:means"], cast))
    # the SAME clue at reveal_condition 'pressure' is reachable
    cast2 = (CastNode("person:x", holds_clues=(
        Clue("clue:g", "pillar:means", ("fact:means", "is", "key"),
             coverage_effect="genuine", reveal_condition="pressure"),)),)
    assert is_solvable(["pillar:means"], cast2)


def test_unknown_holder_is_flagged_when_known_ids_given():
    cast = (CastNode("person:ghost", holds_clues=(
        Clue("clue:g", "pillar:means", ("fact:means", "is", "key"), coverage_effect="genuine"),)),)
    # without known_ids: holder not checked (solvable)
    assert is_solvable(["pillar:means"], cast)
    # with known_ids that omit the holder: flagged
    problems = check_solvability(["pillar:means"], cast, known_ids={"person:real"})
    assert any("person:ghost" in p for p in problems)


def test_debunker_behind_unsupported_gate_is_flagged():
    cast = (CastNode("person:x", holds_clues=(
        Clue("clue:g", "pillar:means", ("fact:means", "is", "key"), coverage_effect="genuine"),
        Clue("clue:rh", "pillar:means", ("fact:means", "blamed", "y"),
             coverage_effect="false", is_red_herring=True, debunked_by="clue:deb"),
        Clue("clue:deb", "pillar:means", ("fact:means", "cleared", "y"),
             coverage_effect="genuine", reveal_condition="object_seen"),)),)
    assert any("gated behind an unsupported" in p for p in check_solvability(["pillar:means"], cast))


def test_build_pillars_makes_coverage_conditions_over_the_player_frame():
    pillars = build_pillars(
        [("pillar:motive", "the motive", True), ("pillar:means", "the means", True)],
        _cast(), PROT)
    by_id = {p.pillar_id: p for p in pillars}
    # genuine + false conditions authored from the distributed clues
    assert by_id["pillar:motive"].genuine_via is not None
    assert by_id["pillar:means"].false_via is not None   # the red herring feeds false_via
    # unfilled until the clue is learned
    assert pillar_coverage(_world(set()), by_id["pillar:motive"]) == "unfilled"
    # genuine once the genuine clue's fact lands in the player frame
    assert pillar_coverage(_world({("fact:motive", "is", "debt")}),
                           by_id["pillar:motive"]) == "genuine"
    # false once the red-herring fact is held (and no genuine means clue yet)
    assert pillar_coverage(_world({("fact:means", "blamed", "person:cook")}),
                           by_id["pillar:means"]) == "false"


def test_weave_pick_returns_governance_decision():
    # CARD-WEAVING / Cx 039 #2: the governance cohort decides let_run|pepper_hook|deliver_card
    # and carries the master judgment + floor framing in its prompt.
    from construct.cohorts import weave_pick
    from construct.provider import StubProvider
    prov = StubProvider([{"decision": "pepper_hook", "card_id": "clue:motive",
                          "seam_hint": "as the brandy is poured",
                          "directive": "the heir's hand shakes when the will comes up"}])
    out = weave_pick(prov, scene="the parlor, tense and quiet",
                     cards=["clue:motive :: the heir keeps starting a sentence about Tuesday"],
                     floor_debt=["clue:motive :: ..."], momentum="going dry",
                     protagonist="person:player")
    assert out["decision"] == "pepper_hook" and out["card_id"] == "clue:motive"
    prompt = prov.calls[0][0]
    assert "MASTER JUDGMENT" in prompt and "LET IT RUN" in prompt and "FLOOR DEBT" in prompt


def test_floor_set_is_hooked_genuine_required_clues():
    # CARD-WEAVING / Cx 039: the proposal floor = genuine, non-herring clues for REQUIRED
    # pillars that carry a non-spoiling hook. A clue without a hook can't be softly proposed.
    cast = (
        CastNode("person:heir", holds_clues=(
            Clue("clue:motive", "pillar:motive", ("fact:motive", "is", "debt"),
                 coverage_effect="genuine", hook_text="the heir won't meet your eye on the will"),)),
        CastNode("person:cook", holds_clues=(  # genuine but NO hook → not floor-bearing
            Clue("clue:means", "pillar:means", ("fact:means", "is", "vial"),
                 coverage_effect="genuine"),
            # a red herring — never floor-bearing even with a hook
            Clue("clue:rh", "pillar:means", ("fact:means", "blamed", "x"),
                 coverage_effect="false", is_red_herring=True, debunked_by="clue:means",
                 hook_text="the cook keeps glancing at the door"),)),
    )
    req = ["pillar:motive", "pillar:means"]
    fc = floor_clues(cast, req)
    assert [c.clue_id for c in fc] == ["clue:motive"]  # only the hooked genuine required clue
    # debt = floor cards whose hook isn't yet proposed/delivered
    assert [c.clue_id for c in floor_debt(cast, req, proposed_ids=set())] == ["clue:motive"]
    assert floor_debt(cast, req, proposed_ids={"clue:motive"}) == []  # floor satisfied


def test_cast_from_proposal_parses_hook_text():
    prop = {"pillars": [{"id": "pillar:motive", "label": "m", "required": True}],
            "cast": [{"id": "person:heir", "clues": [
                {"clue_id": "clue:motive", "pillar_id": "pillar:motive",
                 "fact": {"entity": "fact:motive", "attribute": "is", "value": "debt"},
                 "coverage_effect": "genuine",
                 "hook_text": "the heir flinches at the will"}]}]}
    cast, _ = cast_from_proposal(prop)
    clue = cast[0].holds_clues[0]
    assert clue.hook_text == "the heir flinches at the will"
    # the hook is NOT the surface_fact (the safety seam): the fact stays withheld
    assert clue.surface_fact == ("fact:motive", "is", "debt")


def test_cast_seed_plan_seeds_each_holder_frame():
    plan = dict(cast_seed_plan(_cast()))
    assert set(plan) == {"knows:person:clerk", "knows:person:porter"}
    # the clerk's frame holds the motive fact (an ordinary fact, no clue/pillar metadata)
    assert {"entity": "fact:motive", "attribute": "is", "value": "debt"} in plan["knows:person:clerk"]
    # the porter holds both its clues (genuine key + the red herring)
    assert len(plan["knows:person:porter"]) == 2
    # an empty node contributes no frame
    assert cast_seed_plan((CastNode("person:mute"),)) == []


def test_learn_clue_writes_the_surface_fact():
    clue = Clue("clue:debt", "pillar:motive", ("fact:motive", "is", "debt"))
    assert learn_clue_items(clue) == [{"entity": "fact:motive", "attribute": "is", "value": "debt"}]


def test_revealable_clues_gates_by_condition():
    node = CastNode("person:x", holds_clues=(
        Clue("c1", "p", ("f", "a", "v1"), reveal_condition="none"),
        Clue("c2", "p", ("f", "a", "v2"), reveal_condition="trust"),
        Clue("c3", "p", ("f", "a", "v3"), reveal_condition="pressure"),
        Clue("c4", "p", ("obj:ledger", "a", "v4"), reveal_condition="object_seen"),
    ))
    # baseline: only the unconditional clue
    assert [c.clue_id for c in revealable_clues(node)] == ["c1"]
    # with trust: c1 + c2
    assert [c.clue_id for c in revealable_clues(node, trust=True)] == ["c1", "c2"]
    # under pressure: c1 + c3
    assert [c.clue_id for c in revealable_clues(node, pressure=True)] == ["c1", "c3"]
    # EXAMINE channel (EXAMINE-CHANNEL.md): examined/scrutiny gate physical-clue holders
    enode = CastNode("obj:bag", holds_clues=(
        Clue("e_glance", "p", ("obj:bag", "a", "v1"), reveal_condition="examined"),
        Clue("e_close", "p", ("obj:bag", "a", "v2"), reveal_condition="scrutiny"),
    ))
    assert [c.clue_id for c in revealable_clues(enode, examined=True)] == ["e_glance"]
    # scrutiny implies examined → both surface on close inspection
    assert [c.clue_id for c in revealable_clues(enode, scrutiny=True)] == ["e_glance", "e_close"]
    # with the object seen: c1 + c4
    assert [c.clue_id for c in revealable_clues(node, objects_seen=frozenset({"obj:ledger"}))] \
        == ["c1", "c4"]


def test_revealable_clues_put_genuine_before_red_herrings():
    """The one-clue-per-turn delivery breaks after the first revealable clue, so a freely-
    revealed red herring sitting first in the holder's list starved the genuine clue behind
    it (the live run: Orme's misdirection delivered, his carbolic tell never did, wrong man
    accused). Genuine clues must lead so the per-turn slot serves truth first."""
    node = CastNode("person:orme", holds_clues=(
        Clue("h1", "p", ("f", "a", "lie1"), reveal_condition="none", is_red_herring=True),
        Clue("h2", "p", ("f", "a", "lie2"), reveal_condition="none", is_red_herring=True),
        Clue("g1", "p", ("f", "a", "truth"), reveal_condition="pressure"),
    ))
    order = [c.clue_id for c in revealable_clues(node, pressure=True)]
    assert order == ["g1", "h1", "h2"]  # genuine first, herrings trail (stable)


def _staged(node_id, presence, location="", clues=(), first_witness=False, is_culprit=False):
    return CastNode(node_id, presence=presence, location=location, holds_clues=clues,
                    first_witness=first_witness, is_culprit=is_culprit)


def test_cast_location_plan_stages_at_scene_and_defines_remote_places():
    from construct.cast import cast_location_plan
    cast = (
        _staged("person:firth", "at_scene", first_witness=True),
        _staged("person:bell", "offscene", "place:bell_cottage"),
    )
    items = cast_location_plan(cast, "place:library")
    # at_scene member placed at the crime scene; offscene member at their place
    assert {"entity": "person:firth", "attribute": "in", "value": "place:library",
            "value_type": "entity"} in items
    assert {"entity": "person:bell", "attribute": "in", "value": "place:bell_cottage",
            "value_type": "entity"} in items
    # the remote place is made canonically referable (kind + derived name); the scene is not redefined
    assert {"entity": "place:bell_cottage", "attribute": "kind", "value": "place"} in items
    assert {"entity": "place:bell_cottage", "attribute": "name", "value": "bell cottage"} in items
    assert not any(it["entity"] == "place:library" for it in items)


def test_staging_gate_passes_when_culprit_reachable_via_discovery_chain():
    from construct.cast import check_solvability
    req = ["pillar:who"]
    # Firth (at_scene, first witness) holds a clue NAMING Bell (offscene) → discovery chain;
    # Bell (the culprit, offscene with a place) holds the genuine clue.
    cast = (
        _staged("person:firth", "at_scene", first_witness=True, clues=(
            Clue("c_name", "pillar:who", ("person:bell", "seen_near", "library")),)),
        _staged("person:quill", "at_scene", clues=()),
        _staged("person:bell", "offscene", "place:bell_cottage", is_culprit=True, clues=(
            Clue("c_who", "pillar:who", ("person:bell", "did_it", "true")),)),
    )
    assert check_solvability(req, cast, require_staging=True) == []


def test_staging_gate_flags_stranded_culprit_and_missing_first_witness():
    from construct.cast import check_solvability
    req = ["pillar:who"]
    # Bell is the culprit, offscene, with a place — but NO at_scene clue names him → stranded.
    # And no at_scene member is a first_witness.
    cast = (
        _staged("person:quill", "at_scene", clues=(
            Clue("c1", "pillar:who", ("fact:x", "is", "y")),)),
        _staged("person:ada", "at_scene", clues=()),
        _staged("person:bell", "offscene", "place:bell_cottage", is_culprit=True, clues=(
            Clue("c_who", "pillar:who", ("person:bell", "did_it", "true")),)),
    )
    problems = check_solvability(req, cast, require_staging=True)
    assert any("culprit person:bell" in p for p in problems)
    assert any("first_witness" in p for p in problems)


def test_staging_gate_flags_an_unreachable_genuine_required_clue_holder():
    # Cx 061 #1: EVERY genuine required-clue holder must be reachable, not just one per
    # pillar. A reachable at_scene witness covers pillar:who, but a SECOND genuine clue on an
    # unreachable (un-named) offscene holder is a dead card → must fail.
    from construct.cast import check_solvability
    req = ["pillar:who"]
    cast = (
        _staged("person:firth", "at_scene", first_witness=True, clues=(
            Clue("c1", "pillar:who", ("fact:a", "is", "b")),)),
        _staged("person:quill", "at_scene", is_culprit=True, clues=()),
        # offscene, has a place, but NO at_scene clue names them → unreachable, yet holds a
        # genuine required clue:
        _staged("person:ghost", "offscene", "place:far", clues=(
            Clue("c2", "pillar:who", ("fact:c", "is", "d")),)),
    )
    problems = check_solvability(req, cast, require_staging=True)
    assert any("holder person:ghost" in p for p in problems)


def test_staging_gate_rejects_naming_chain_via_non_live_clue():
    # Cx 061 #2: a discovery edge via a trust/object_seen clue is DEAD (the turn loop only
    # surfaces none/pressure), so it must NOT confer reachability on the offscene culprit.
    from construct.cast import check_solvability
    req = ["pillar:who"]
    cast = (
        _staged("person:firth", "at_scene", first_witness=True, clues=(
            # names Bell, but only behind 'trust' → not live-deliverable
            Clue("c_name", "pillar:who", ("person:bell", "seen", "x"), reveal_condition="trust"),)),
        _staged("person:quill", "at_scene", clues=()),
        _staged("person:bell", "offscene", "place:cottage", is_culprit=True, clues=(
            Clue("c_who", "pillar:who", ("person:bell", "did", "it")),)),
    )
    problems = check_solvability(req, cast, require_staging=True)
    assert any("culprit person:bell" in p for p in problems)


def test_staging_gate_requires_singleton_culprit_and_first_witness():
    # Cx 061 #4: exactly one culprit + exactly one first_witness.
    from construct.cast import check_solvability
    req = ["pillar:who"]
    cast = (
        _staged("person:a", "at_scene", first_witness=True, is_culprit=True, clues=(
            Clue("c1", "pillar:who", ("fact:a", "is", "b")),)),
        _staged("person:b", "at_scene", first_witness=True, is_culprit=True, clues=()),
    )
    problems = check_solvability(req, cast, require_staging=True)
    assert any("exactly ONE is_culprit" in p for p in problems)
    assert any("exactly ONE first_witness" in p for p in problems)


def test_solvability_counts_object_scrutiny_clue_when_reachable():
    # EXAMINE-CHANNEL.md (Cx 073 pin): a required pillar covered ONLY by an object's `scrutiny`
    # clue is solvable when the object is physically reachable, and fails when it's stranded.
    from construct.cast import check_solvability
    req = ["pillar:means"]
    reachable = (
        _staged("person:witness", "at_scene", first_witness=True, is_culprit=True, clues=(
            Clue("c_name", "pillar:means", ("obj:bag", "noted", "x")),)),
        _staged("person:other", "at_scene", clues=()),
        _staged("obj:bag", "at_scene", clues=(  # the physical means clue, examinable at-scene
            Clue("c_vial", "pillar:means", ("fact:means", "is", "vial_missing"),
                 reveal_condition="scrutiny"),)),
    )
    assert check_solvability(req, reachable, require_staging=True) == []
    # same clue on an OFF-SCENE object with no naming lead → unreachable → fails
    stranded = (
        _staged("person:witness", "at_scene", first_witness=True, is_culprit=True, clues=(
            Clue("c1", "pillar:means", ("fact:x", "is", "y")),)),
        _staged("person:other", "at_scene", clues=()),
        _staged("obj:bag", "offscene", "place:vault", clues=(
            Clue("c_vial", "pillar:means", ("fact:means", "is", "vial_missing"),
                 reveal_condition="scrutiny"),)),
    )
    assert any("obj:bag" in p for p in check_solvability(req, stranded, require_staging=True))


def test_staging_gate_is_off_by_default_backward_compat():
    from construct.cast import check_solvability
    # A plain cast with no presence/location/culprit data must still pass the legacy gate.
    req = ["pillar:who"]
    cast = (CastNode("person:x", holds_clues=(
        Clue("c", "pillar:who", ("fact:a", "is", "b")),)),)
    assert check_solvability(req, cast) == []  # require_staging defaults False


def test_revealable_clues_rank_genuine_then_context_then_false():
    """Cx 049 non-blocking: rank on coverage_effect too, so a 'false'/'context' clue that
    forgot the is_red_herring flag still can't jump a genuine clue's per-turn slot."""
    node = CastNode("person:x", holds_clues=(
        Clue("ctx", "p", ("f", "a", "c"), reveal_condition="none", coverage_effect="context"),
        Clue("fls", "p", ("f", "a", "f"), reveal_condition="none", coverage_effect="false"),
        Clue("gen", "p", ("f", "a", "g"), reveal_condition="none", coverage_effect="genuine"),
    ))
    assert [c.clue_id for c in revealable_clues(node)] == ["gen", "ctx", "fls"]


def test_is_pressing_treats_directed_questioning_as_pressure():
    """The live whodunit run failed because pressure-gated clues never surfaced: the
    agent questioned witnesses POLITELY ('ask Mara to describe what she saw') and the old
    detector only fired on overt hostility. Directed investigative questioning IS pressing
    a witness — the broadened detector must catch it (the delivery-gap fix)."""
    from construct.turnloop import _is_pressing

    # Polite-but-directed questioning of a witness → pressing (the case the fix unblocks).
    assert _is_pressing("ask mara to describe what she saw", needs_test=False)
    assert _is_pressing("where were you last night?", needs_test=False)
    assert _is_pressing("tell me what happened", needs_test=False)
    assert _is_pressing("what do you know about the knife?", needs_test=False)
    # Overt pressure still counts.
    assert _is_pressing("i confront orme about the blood", needs_test=False)
    # An uncertain action (classify flagged needs_test) is pressing regardless of words.
    assert _is_pressing("i search the room", needs_test=True)
    # A bland, non-investigative statement with no probe/question is NOT pressing.
    assert not _is_pressing("i walk slowly toward the river", needs_test=False)
    assert not _is_pressing("i sit down by the fire", needs_test=False)


_PROPOSAL = {
    "pillars": [
        {"id": "pillar:motive", "label": "the motive", "required": True},
        {"id": "pillar:means", "label": "the means", "required": True},
    ],
    "cast": [
        {"id": "person:clerk", "shape_role": "witness", "surface_role": "night clerk",
         "clues": [{"clue_id": "clue:debt", "pillar_id": "pillar:motive",
                    "fact": {"entity": "fact:motive", "attribute": "is", "value": "debt"},
                    "coverage_effect": "genuine"}]},
        {"id": "person:porter", "shape_role": "suspect", "surface_role": "porter",
         "clues": [
             {"clue_id": "clue:key", "pillar_id": "pillar:means",
              "fact": {"entity": "fact:means", "attribute": "is", "value": "spare_key"},
              "coverage_effect": "genuine"},
             {"clue_id": "clue:grudge", "pillar_id": "pillar:means",
              "fact": {"entity": "fact:means", "attribute": "blamed", "value": "person:cook"},
              "coverage_effect": "false", "is_red_herring": True, "debunked_by": "clue:key"},
             {"clue_id": "clue:bad", "pillar_id": "pillar:means",
              "fact": {"entity": "fact:means"}},  # malformed → dropped
         ]},
    ],
}


def test_cast_from_proposal_parses_and_drops_malformed():
    cast, specs = cast_from_proposal(_PROPOSAL)
    assert specs == [("pillar:motive", "the motive", True), ("pillar:means", "the means", True)]
    by_id = {n.node_id: n for n in cast}
    assert set(by_id) == {"person:clerk", "person:porter"}
    # the malformed clue (no attribute/value) was dropped; the two valid ones kept
    assert len(by_id["person:porter"].holds_clues) == 2
    # and the parsed cast is solvable + builds pillars that read coverage
    assert is_solvable([s[0] for s in specs], cast)
    pillars = build_pillars(specs, cast, PROT)
    assert {p.pillar_id for p in pillars} == {"pillar:motive", "pillar:means"}


def test_author_cast_cohort_roundtrips_through_the_parser():
    # the generation cohort returns a SCHEMA-VALID proposal; cast_from_proposal + is_solvable
    # consume it. (The parser's fail-soft on malformed clues is covered separately — the
    # cohort itself only ever emits schema-valid output.)
    import copy
    from construct.cohorts import author_cast
    from construct.provider import StubProvider
    clean = copy.deepcopy(_PROPOSAL)
    clean["cast"][1]["clues"] = clean["cast"][1]["clues"][:2]  # drop the malformed clue
    provider = StubProvider([clean])
    proposal = author_cast(provider, digest="a small mystery", theme="theft",
                           shape_label="deduction", protagonist=PROT,
                           people=["person:clerk", "person:porter"])
    cast, specs = cast_from_proposal(proposal)
    assert is_solvable([s[0] for s in specs], cast)
    assert genuine_reachable("pillar:means", cast) == 1


def test_conclusion_profile_handoff_for_contest_and_farce():
    # Cx 029 non-blocking: pin the game_type → conclusion_profile handoff that Session reads
    # into cost_disposition / reads_world_event (the polarity + scoreboard switches).
    from construct.story_shapes import conclusion_profile, shapes_for
    contest = conclusion_profile("tactical_combat")
    assert shapes_for("tactical_combat")["shape"] == "contest"
    assert contest["cost_disposition"] == "peril_redemption"
    assert contest["reads_world_event"] is True  # Contest reads the scoreboard
    farce = conclusion_profile("mistaken_identity")
    assert shapes_for("mistaken_identity")["shape"] == "farce"
    assert farce["cost_disposition"] == "fail_forward"  # comedy inverts coverage polarity
    assert not farce.get("reads_world_event")


def test_end_to_end_cast_to_arc_coverage():
    # cast → build_pillars → an arc → arc_coverage reads the woven player frame
    import dataclasses
    from construct.arc.conditions import InFrame
    from construct.arc.grammar import Arc, Clock, ConclusionShape
    pillars = build_pillars(
        [("pillar:motive", "the motive", True), ("pillar:means", "the means", True)],
        _cast(), PROT)
    shape = ConclusionShape("shape:t", "desire_at_cost", (PROT, "a", "b"),
                            world_condition=InFrame(FRAME, "x", "y", "z"),
                            premise=InFrame(FRAME, "x", "y", "z"), refusal_variant_id="r")
    arc = Arc(arc_id="arc:main", protagonist=PROT, shape=shape, beats=(), clocks=(),
              refusal_clock=Clock("clock:refusal", shape.world_condition, ()),
              climax_ready_k=1, climax_ready_beats=(), pillars=pillars)
    # player has learned the motive (genuine) but built the means on the red herring
    w = _world({("fact:motive", "is", "debt"), ("fact:means", "blamed", "person:cook")})
    cov = arc_coverage(w, arc)
    assert cov == {"pillar:motive": "genuine", "pillar:means": "false"}


def _deduction_cast_with_signature():
    # a minimal deduction cast that SHIPS the signature: a strong red herring (with a reachable
    # debunker) + a cross-suspicion edge (the butler's clue points at the doctor).
    return (
        CastNode("person:butler", "witness", "the butler", first_witness=True,
                 presence="at_scene", holds_clues=(
            Clue("clue:opp", "pillar:opportunity", ("person:doctor", "seen_entering", "the study"),
                 coverage_effect="genuine", reveal_condition="none"),)),
        CastNode("person:doctor", "suspect", "the doctor", presence="at_scene", is_culprit=True,
                 holds_clues=(
            Clue("clue:means", "pillar:means", ("fact:means", "is", "vial_gone"),
                 coverage_effect="genuine", reveal_condition="pressure"),
            Clue("clue:redherring", "pillar:means", ("fact:means", "claimed", "natural"),
                 coverage_effect="false", is_red_herring=True, reveal_condition="none",
                 debunked_by="clue:means"),)),
    )


def test_signature_support_passes_a_well_formed_deduction_cast():
    from construct.cast import validate_signature_support
    cast = _deduction_cast_with_signature()
    assert validate_signature_support(["deduction"], cast) == []
    assert validate_signature_support("deduction", cast) == []  # scalar shape accepted


def test_signature_support_flags_a_missing_red_herring():
    from construct.cast import validate_signature_support
    # drop the red herring clue → deduction signature incomplete
    butler, doctor = _deduction_cast_with_signature()
    doctor = CastNode("person:doctor", "suspect", "the doctor", presence="at_scene",
                      is_culprit=True, holds_clues=(doctor.holds_clues[0],))  # genuine only
    probs = validate_signature_support(["deduction"], (butler, doctor))
    assert any("red herring" in p for p in probs)


def test_signature_support_flags_missing_cross_suspicion():
    from construct.cast import validate_signature_support
    # two people, but no clue references another cast member → no cross-suspicion edge
    cast = (
        CastNode("person:a", "witness", "A", first_witness=True, presence="at_scene", holds_clues=(
            Clue("clue:1", "pillar:x", ("fact:x", "is", "y"), coverage_effect="genuine",
                 reveal_condition="none"),
            Clue("clue:rh", "pillar:x", ("fact:x", "claimed", "z"), coverage_effect="false",
                 is_red_herring=True, reveal_condition="none", debunked_by="clue:1"),)),
        CastNode("person:b", "suspect", "B", presence="at_scene", is_culprit=True, holds_clues=()),
    )
    probs = validate_signature_support(["deduction"], cast)
    assert any("cross-suspicion" in p for p in probs)


def test_signature_support_noop_for_non_deduction_shapes():
    from construct.cast import validate_signature_support
    # a bond/romance world is prompt + live-acceptance only in v1 — no hard lint, no false flags
    cast = _deduction_cast_with_signature()  # cast content irrelevant for non-deduction
    assert validate_signature_support(["bond"], cast) == []
    assert validate_signature_support([], cast) == []
