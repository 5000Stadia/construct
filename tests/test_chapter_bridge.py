"""THE CHAPTER BRIDGE, B1 (docs/design/CHAPTER-BRIDGE-B1.md r3, R36) — changes 2-5.

Change 1 (the walk-away pending/confirm) waits on Kabe's gate g3e598a and is not built here."""
import json

import pytest
from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct import bridge, game
from construct.adapter import HorizonView, PorcelainWorldReads
from construct.arc.conditions import InFrame, Occurred
from construct.arc.grammar import Beat, Phase, Weight
from construct.cast import CastNode, Clue
from construct.semantics import attribute_default

import tests.test_reads_at_horizon as H

PROT = H.PROT


def _fallback(prompt, schema, _rule=rule_classifier_fallback()):
    return _rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}


@pytest.fixture
def hw(tmp_path):
    w = World(tmp_path / "b.world", world_id="w:b", model=StubModel(fallback=_fallback),
              stance="fiction", attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured(H._rows() + [
        {"entity": "person:witness", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "place:docks", "attribute": "kind", "value": "docks", "timeless": True},
        {"entity": "person:witness", "attribute": "in", "value": "place:docks",
         "value_type": "entity", "valid_from": H.OPENING + 3},
        {"entity": "region:wild", "attribute": "kind", "value": "region", "timeless": True},
        {"entity": "place:hut", "attribute": "kind", "value": "hut", "timeless": True},
        {"entity": "place:hut", "attribute": "in", "value": "region:wild",
         "value_type": "entity", "valid_from": H.OPENING + 4},
    ])
    yield w
    w.close()


def _arc(beats):
    from tests.test_story_soundness import _arc as mk
    return mk(beats)


# ------------------------------------------------------------ change 2: outcome categories

def test_outcome_categories(hw):
    from construct.arc.executor import SESSION
    v = HorizonView(hw, H.H)
    reads = PorcelainWorldReads(v)
    arc = _arc([Beat("beat:a", Phase.CLIMAX, Weight.REQUIRED, achievable_via=Occurred("k"))])
    oc = bridge.outcome_category
    assert oc(reads, arc, refusal_fired=True, outcome="lost",
              terminal_location="place:hut") == "abandoned"          # refusal beats elsewhere
    assert oc(reads, arc, refusal_fired=False, outcome="won",
              terminal_location="place:hut") == "elsewhere"          # grown region, unscoped
    assert oc(reads, arc, refusal_fired=False, outcome="won", grade="wrong") == "wrong"
    assert oc(reads, arc, refusal_fired=False, outcome="lost",
              outcome_shape="quiet_failure") == "wrong"
    assert oc(reads, arc, refusal_fired=False, outcome="won",
              terminal_location="place:street") == "right"
    hw.porcelain.ingest_structured([
        {"entity": "event:tangent_adopted_4", "attribute": "kind",
         "value": "tangent_adopted", "valid_from": H.OPENING + 4},
        {"entity": "event:tangent_adopted_4", "attribute": "new_main",
         "value": "arc:main", "valid_from": H.OPENING + 4}], frame=SESSION)
    assert oc(PorcelainWorldReads(HorizonView(hw, H.H)), arc, refusal_fired=False,
              outcome="won") == "elsewhere"                          # adopted from a tangent


# --------------------------------------------------- changes 3 and 4: the accountings

def test_thread_disposition_completeness():
    arc = _arc([Beat("beat:a", Phase.CLIMAX, Weight.REQUIRED, achievable_via=Occurred("k"))])
    threads = [{"thread": "t0"}, {"thread": "t1"}, {"thread": "t2"}]
    partial = {"thread_disposition": [
        {"index": 0, "disposition": "closed", "how": "paid"},
        {"index": 1, "disposition": "carried", "how": "beat:a takes it up"}]}
    probs = bridge.check_threads(partial, 3, arc)
    assert any("[2]" in p for p in probs)
    full = {"thread_disposition": partial["thread_disposition"] + [
        {"index": 2, "disposition": "closed", "how": "settled"}]}
    assert bridge.check_threads(full, 3, arc) == []
    vague = {"thread_disposition": [{"index": 0, "disposition": "carried", "how": "somehow"}]}
    assert any("names no beat" in p for p in bridge.check_threads(vague, 1, arc))
    assert bridge.closed_threads(full, threads)[0].startswith("t0 — closed by the author")
    assert bridge.check_threads({}, 0, arc) == []


def test_response_to_the_outcome(hw):
    reads = PorcelainWorldReads(HorizonView(hw, H.H))
    arc = _arc([Beat("beat:a", Phase.CLIMAX, Weight.REQUIRED,
                     achievable_via=InFrame(f"knows:{PROT}", "person:witness", "saw", "x"))])
    assert bridge.check_response({}, reads, arc, "wrong")                      # missing
    bad = {"responds_to_outcome": {"how": "x", "ids": ["person:later"]}}       # future-only
    assert bridge.check_response(bad, reads, arc, "wrong")
    good = {"responds_to_outcome": {"how": "the witness comes back",
                                    "ids": ["person:witness"]}}
    assert bridge.check_response(good, reads, arc, "wrong") == []
    assert bridge.check_response({}, reads, arc, "") == []      # no recorded outcome


# ------------------------------------------------- change 5: the episode cast

def _learn(bid, weight=Weight.REQUIRED, fact=("fact:secret", "is", "out")):
    return Beat(bid, Phase.RISING, weight,
                achievable_via=InFrame(f"knows:{PROT}", fact[0], fact[1], fact[2]))


def test_episode_cast_rederives_at_the_horizon(hw):
    """6d: chapter-1 metadata says at_scene in the study; at h the witness is at the docks."""
    reads = PorcelainWorldReads(HorizonView(hw, H.H))
    stale = CastNode("person:witness", presence="at_scene", location="place:study")
    arc = _arc([_learn("beat:l")])
    prop = {"clues": [{"beat_id": "beat:l", "holder": "person:witness",
                       "reveal_condition": "pressure"}]}
    cast, probs = bridge.build_episode_cast(prop, arc, (stale,), reads,
                                            door_place="place:street", hook_ids=[],
                                            protagonist=PROT)
    assert probs == []
    node = next(n for n in cast if n.node_id == "person:witness")
    assert (node.presence, node.location) == ("nearby", "place:docks")
    assert node.holds_clues[-1].surface_fact == ("fact:secret", "is", "out")


def test_episode_cast_rejects_unreachable_and_non_ask(hw):
    reads = PorcelainWorldReads(HorizonView(hw, H.H))
    arc = _arc([_learn("beat:l"), _learn("beat:opt", Weight.OPTIONAL, ("fact:secret", "a", "b"))])
    # 6c: a person holder with an EXAMINE-only condition
    examined = {"clues": [{"beat_id": "beat:l", "holder": "person:witness",
                           "reveal_condition": "examined"}]}
    _c, probs = bridge.build_episode_cast(examined, arc, (), reads, door_place="place:street",
                                          hook_ids=[], protagonist=PROT)
    assert any("examined" in p for p in probs)
    # 6b: the optional beat has no holder → a failed attempt naming it
    only_required = {"clues": [{"beat_id": "beat:l", "holder": "person:witness",
                                "reveal_condition": "none"}]}
    _c, probs = bridge.build_episode_cast(only_required, arc, (), reads,
                                          door_place="place:street", hook_ids=[],
                                          protagonist=PROT)
    assert any("beat:opt" in p for p in probs)
    # 6d variant: an unlocated holder nobody names is unreachable
    hw.porcelain.ingest_structured([{"entity": "person:ghost", "attribute": "kind",
                                     "value": "person", "timeless": True}])
    reads2 = PorcelainWorldReads(HorizonView(hw, H.H))
    ghost = {"clues": [{"beat_id": "beat:l", "holder": "person:ghost",
                        "reveal_condition": "none"}]}
    arc1 = _arc([_learn("beat:l")])
    _c, probs = bridge.build_episode_cast(ghost, arc1, (), reads2, door_place="place:street",
                                          hook_ids=[], protagonist=PROT)
    assert any("beat:l" in p for p in probs)


def _bridge_slot(tmp_path, monkeypatch):
    extra = [{"entity": "person:witness", "attribute": "kind", "value": "person",
              "timeless": True},
             # in the cell with the player from chunk 1 (the slot's horizon is opening + 1)
             {"entity": "person:witness", "attribute": "in", "value": "place:cell",
              "value_type": "entity", "valid_from": H.STEP},
             {"entity": "fact:secret", "attribute": "kind", "value": "proposition",
              "timeless": True}]
    real = H._rows
    monkeypatch.setattr(H, "_rows", lambda: real() + extra)
    return H._make_horizon_slot(tmp_path, monkeypatch, name="br")


_CH2 = {
    "protagonist": PROT, "delta_type": "desire_at_cost",
    "tension": [PROT, "drive:duty", "drive:fear"], "title": "Second",
    "hook": "Someone under the lamp has been waiting.",
    "beats": [{"id": "beat:learn", "phase": "rising", "weight": "required",
               "kind": "player_learns", "entity": "fact:secret", "attribute": "is",
               "value": "out"},
              {"id": "beat:act", "phase": "climax", "weight": "required",
               "kind": "event_occurs", "entity": "reckoning", "attribute": "", "value": ""}],
    "clues": [{"beat_id": "beat:learn", "holder": "person:witness",
               "reveal_condition": "none"}],
    "thread_disposition": [{"index": 0, "disposition": "closed", "how": "settled"}],
    "responds_to_outcome": {"how": "the witness has words", "ids": ["person:witness"]},
}


def test_continuation_commits_a_horizon_visible_episode_cast(tmp_path, monkeypatch):
    """6: the episode cast and the holder's seeded fact are committed atomically, stamped at
    the chapter's turn time, visible to a reopened horizon Session; the protagonist's frame
    never gets the answer."""
    from construct.arc.executor import SESSION
    from tests.test_world_polish import _ContProvider
    name = _bridge_slot(tmp_path, monkeypatch)
    game.continue_episode(name, _ContProvider([_CH2]), player_id="u1")
    w = H._open_slot_world(name) if hasattr(H, "_open_slot_world") else World(
        game.slot_path(name, "u1"), world_id=f"w:{name}", stance="fiction",
        model=StubModel(fallback=_fallback))
    try:
        view = HorizonView(w, H.OPENING + 2)
        raw = PorcelainWorldReads(view).state("session:episode", "cast", frame=SESSION)
        blob = json.loads(raw)
        holder = next(n for n in blob["cast"] if n["id"] == "person:witness")
        assert holder["clues"][0]["fact"] == {"entity": "fact:secret", "attribute": "is",
                                              "value": "out"}
        rows = view.porcelain.facts("knows:person:witness", entity="fact:secret")
        assert rows and all((r.get("valid") or [None])[0] is not None for r in rows)
        assert not view.porcelain.facts(f"knows:{PROT}", entity="fact:secret")
    finally:
        w.close()


def test_continuation_sends_back_an_undeliverable_beat(tmp_path, monkeypatch):
    from tests.test_world_polish import _ContProvider
    from construct.provider import task_of
    name = _bridge_slot(tmp_path, monkeypatch)
    bad = {**_CH2, "clues": []}
    prov = _ContProvider([bad, _CH2])
    game.continue_episode(name, prov, player_id="u1")
    gens = [p for (p, _s, _t) in prov.calls if task_of(p) == "gen"]
    assert len(gens) == 2 and "SENT BACK" in gens[1] and "beat:learn" in gens[1]


def test_reopened_session_prefers_the_episode_cast(tmp_path, monkeypatch):
    """6 (continued): the reopened Session reads the slot's episode cast, not the scenario
    meta's chapter-1 cast, and its holder carries the chapter-2 clue."""
    from construct.session import Session
    from tests.test_session import _provider
    from tests.test_world_polish import _ContProvider
    name = _bridge_slot(tmp_path, monkeypatch)
    game.continue_episode(name, _ContProvider([_CH2]), player_id="u1")
    s = Session.open(name, player_id="u1", provider=_provider())
    try:
        node = s._cast.get("person:witness")
        assert node is not None
        assert ("fact:secret", "is", "out") in {c.surface_fact for c in node.holds_clues}
    finally:
        s.close()
