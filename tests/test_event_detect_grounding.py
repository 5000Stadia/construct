"""EVENT-DETECT-GROUNDING (R20 run 13): an authored event carries its meaning, and the
event detector judges the action against that meaning and the place the player stands.

Run 13's climax `Occurred("fog_bell_window_taken_at_lower_chain")` (the river boom at the
lower chain tower) fired when the player broke his wrist chain in a lane: the detector saw
only the de-slugged kind."""
import dataclasses

import jsonschema
import pytest

from construct import cohorts
from construct.adapter import PorcelainWorldReads
from construct.arc import io as arc_io
from construct.arc.build import ARC_SCHEMA, _build_arc
from construct.arc.conditions import Occurred
from construct.arc.grammar import Beat, Phase, Weight
from construct.provider import StubProvider
from construct.turnloop import TurnTrace, _fire_event_occurs, _frame_place_name
from tests.test_integration import PLAYER, make_arc, seed_arc, world  # noqa: F401

PLAYER_FRAME = f"knows:{PLAYER}"
BOOM = ("Hobb drops the lower chain, the river boom at the lower chain tower, during the "
        "fog-bell blind window, and the barge carrying the protagonist passes")


def _proposal(what: str = BOOM) -> dict:
    return {
        "protagonist": PLAYER, "theme": "the river's timetable",
        "delta_type": "desire_at_cost", "tension": [PLAYER, "drive:freedom", "drive:debt"],
        "beats": [
            {"id": "beat:learn", "phase": "rising", "weight": "optional",
             "kind": "player_learns", "entity": "fact:secret", "attribute": "culprit",
             "value": "person:rival", "what": "ignored for player_learns"},
            {"id": "beat:boom", "phase": "climax", "weight": "required",
             "kind": "event_occurs", "entity": "lower_chain_dropped", "attribute": "",
             "value": "", "what": what},
        ],
    }


def _boom_arc(what: str = BOOM):
    base = make_arc()
    return dataclasses.replace(base, beats=(*base.beats, Beat(
        "beat:boom", Phase.CLIMAX, Weight.OPTIONAL,
        achievable_via=Occurred("lower_chain_dropped"), what=what)))


def _detect_prompt(provider) -> str:
    return [c[0] for c in provider.calls if "AUTHORED story events" in c[0]][-1]


# 1. authoring round-trip
def test_authored_what_round_trips_through_plot_rows(world):
    arc = _build_arc(_proposal())
    boom = next(b for b in arc.beats if b.beat_id == "beat:boom")
    learn = next(b for b in arc.beats if b.beat_id == "beat:learn")
    assert boom.what == BOOM
    assert learn.what == ""                       # player_learns never carries a meaning
    rows = arc_io._beat_rows(boom, arc.arc_id)
    assert {"entity": "beat:boom", "attribute": "what", "value": BOOM,
            "value_type": "literal", "timeless": True} in rows
    world.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc),
                                      classify="rules")
    reads = PorcelainWorldReads(world)
    loaded = arc_io.arc_from_frame(reads, arc.arc_id)
    assert next(b for b in loaded.beats if b.beat_id == "beat:boom").what == BOOM
    assert arc_io.beat_from_reads(reads, "beat:boom", arc_id=arc.arc_id).what == BOOM


# 2. byte-shape
def test_beat_without_meaning_writes_todays_rows():
    beat = Beat("beat:x", Phase.CLIMAX, Weight.REQUIRED, achievable_via=Occurred("x_done"))
    rows = arc_io._beat_rows(beat, "arc:main")
    assert [r["attribute"] for r in rows] == [
        "kind", "part_of", "beat_phase", "weight", "achievable_via", "status"]


# 3. old world
def test_sealed_arc_without_meaning_rows_loads_empty(world):
    arc = _boom_arc(what="")
    seed_arc(world, arc)
    reads = PorcelainWorldReads(world)
    loaded = arc_io.arc_from_frame(reads, arc.arc_id)
    assert next(b for b in loaded.beats if b.beat_id == "beat:boom").what == ""
    assert arc_io.beat_from_reads(reads, "beat:boom", arc_id=arc.arc_id).what == ""


# 4. detector candidates
@pytest.mark.parametrize("what,line", [
    (BOOM, f"- lower_chain_dropped :: {BOOM}"),
    ("", "- lower_chain_dropped :: lower chain dropped"),
])
def test_detector_gets_authored_meaning_or_slug(world, what, line):
    arc = _boom_arc(what)
    seed_arc(world, arc)
    provider = StubProvider([{"occurred": []}])
    _fire_event_occurs(world, world.porcelain, PorcelainWorldReads(world), [arc], provider,
                       "I grind my wrist chain on the drain-lip", "assured", 2,
                       TurnTrace(turn=2), PLAYER)
    assert line in _detect_prompt(provider)


# 5. the place
def test_detector_shown_the_scene_name_only_when_known(world):
    arc = _boom_arc()
    seed_arc(world, arc)
    for scene_name, expect in (("dark runoff lane", True), ("", False)):
        provider = StubProvider([{"occurred": []}])
        _fire_event_occurs(world, world.porcelain, PorcelainWorldReads(world), [arc],
                           provider, "I grind my wrist chain on the drain-lip", "assured", 2,
                           TurnTrace(turn=2), PLAYER, scene_name=scene_name)
        prompt = _detect_prompt(provider)
        assert ("THE PLAYER IS AT: dark runoff lane" in prompt) is expect
        assert ("THE PLAYER IS AT:" in prompt) is expect


def test_frame_place_name_reads_the_player_frame(world):
    assert _frame_place_name(world.porcelain, "place:study", PLAYER_FRAME, None) == ""
    world.porcelain.ingest_structured([{"entity": "place:study", "attribute": "name",
                                        "value": "the study"}], frame=PLAYER_FRAME,
                                      classify="rules")
    assert _frame_place_name(world.porcelain, "place:study", PLAYER_FRAME, None) == "the study"
    assert _frame_place_name(world.porcelain, None, PLAYER_FRAME, None) == ""

    class Raising:
        def state(self, *a, **k):
            raise RuntimeError("unreadable")
    assert _frame_place_name(Raising(), "place:study", PLAYER_FRAME, None) == ""


# 6. the rule
def test_detector_prompt_carries_the_grounding_rule():
    provider = StubProvider([{"occurred": []}])
    cohorts.detect_events(provider, "I act", "assured",
                          [{"kind": "k", "what": "the act"}], scene_name="the lane")
    prompt = provider.calls[-1][0]
    assert "The same word for a different thing (another chain, another door, " \
           "another key) is not the event." in prompt
    assert ("If the description names a place and the player is somewhere else, it did "
            "not happen unless the description says it can be done from afar.") in prompt


# 7. schemas
def test_both_beat_schemas_require_what():
    for schema in (ARC_SCHEMA, cohorts.GEN_ARC_SCHEMA):
        item = schema["properties"]["beats"]["items"]
        assert "what" in item["properties"] and "what" in item["required"]
        jsonschema.validate(
            {"id": "beat:l", "phase": "rising", "weight": "optional", "kind": "player_learns",
             "entity": "fact:x", "attribute": "a", "value": "v", "what": ""}, item)


# 8. fail-open
def test_raising_detector_fires_nothing(world, monkeypatch):
    arc = _boom_arc()
    seed_arc(world, arc)

    def boom(*a, **k):
        raise RuntimeError("detector down")
    monkeypatch.setattr(cohorts, "detect_events", boom)
    trace = TurnTrace(turn=2)
    fired = _fire_event_occurs(world, world.porcelain, PorcelainWorldReads(world), [arc],
                               StubProvider([]), "I act", "assured", 2, trace, PLAYER,
                               scene_name="the lane")
    assert fired == []
    assert any(d.startswith("detect_events") for d in trace.dropped_cohorts)
    assert not PorcelainWorldReads(world).events(kind="lower_chain_dropped")


# the arc cache and a drift repair carry the meaning too
def test_arc_cache_round_trips_meaning_and_omits_it_when_empty():
    arc = _boom_arc()
    assert arc_io.arc_from_cache(arc_io.arc_to_cache(arc)) == arc
    plain = make_arc()
    assert all("what" not in b for b in arc_io.arc_to_cache(plain)["beats"])
    assert arc_io.arc_from_cache(arc_io.arc_to_cache(plain)) == plain


def test_drift_repair_replacement_keeps_the_meaning(world):
    # The replacement carries the dead beat's own mechanic verbatim, so its meaning too.
    from tests import test_drift as td
    from construct.arc.executor import active_beats
    from construct.turnloop import _drift_pass
    w = world
    base = td._dhard_arc()
    arc = dataclasses.replace(base, beats=(dataclasses.replace(base.beats[0], what=BOOM),
                                           *base.beats[1:]))
    td.seed_arc(w, arc)
    td._stage_clerk(w)
    reads = td._close_dhard(w, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([{"hook": "A clerk arrives asking after the shortfall.",
                              "confidence": 0.9}])
    _drift_pass(w, w.porcelain, live_reads=reads, trace=trace, provider=provider, turn=5,
                arc=arc, cast=td._dhard_cast(), scene=td.SCENE, npcs=[], horizon=None,
                minutes_now=None, rung=None, fuel=[], spines={})
    live = active_beats(reads, arc)
    assert [b.beat_id for b in live] == ["beat:discover_r1"]
    assert live[0].what == BOOM
