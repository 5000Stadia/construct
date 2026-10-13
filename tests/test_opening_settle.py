"""The opening's settle (OPENING-SETTLE-AND-ELSEWHERE Part B, cr GREEN at r3).

R20 run 7: the opening showed a torn sack by a hearth in the warrant room, seen from the
player's cell, and no frame ever held it; turn 1 then rendered both in the cell. The
opening's prose now goes through the turn's fact pipeline once, with no turn artifacts.

The extraction rows below are hand-written to match the run 7 opening sentence (that
opening was never extracted, so there is no recorded payload). They prove the pipeline
keeps a correct reading correct; they cannot stop a fresh extraction from misplacing a
distant vista, which the spec records as a residual risk."""

from construct.adapter import PorcelainWorldReads, frame_facts
from construct.arc.timeline import counters_from_session
from construct.named_elsewhere import named_elsewhere
from construct.turnloop import settle_opening
from tests.test_integration import PLAYER, PLAYER_FRAME, make_arc, seed_arc, world  # noqa: F401

_OPENING = ("Past Dena's shoulder, through the open angle toward the warrant room, you can "
            "see firelight and the edge of a torn laundry sack slumped near the hearth.")
_ROWS = [
    {"entity": "obj:torn_laundry_sack", "attribute": "kind", "value": "object"},
    {"entity": "obj:torn_laundry_sack", "attribute": "in", "value": "place:warrant_room"},
    {"entity": "obj:hearth", "attribute": "kind", "value": "hearth"},
    {"entity": "obj:hearth", "attribute": "in", "value": "place:warrant_room"},
    # a person placed by the opening's prose: the opening stages the cast, never moves it
    {"entity": "person:rival", "attribute": "in", "value": "place:warrant_room"},
]


def _seed(world):
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:warrant_room", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:warrant_room", "attribute": "name", "value": "the warrant room"},
    ], frame="canon", classify="rules")
    world._extractions.append({"items": list(_ROWS)})
    return arc


def _in(world, frame, entity):
    snap = world.porcelain.snapshot([entity], frame=frame)
    return next((f["value"] for f in snap.get("facts", [])
                 if f["entity"] == entity and f["attribute"] == "in"), None)


def _session_rows(world):
    return {(f.entity, f.attribute) for f in frame_facts(world, "session:main")}


def test_the_opening_reaches_canon_and_the_player_frame_where_it_put_things(world):
    arc = _seed(world)
    before = _session_rows(world)
    rival_before = _in(world, "canon", "person:rival")
    turns_before = counters_from_session(PorcelainWorldReads(world), arc).turns_elapsed
    trace = settle_opening(world, arc, _OPENING, turn=0)
    assert not [c for c in trace.dropped_cohorts if "opening_settle" in c]
    for ent in ("obj:torn_laundry_sack", "obj:hearth"):
        assert _in(world, "canon", ent) == "place:warrant_room"
        assert _in(world, PLAYER_FRAME, ent) == "place:warrant_room"
    assert _in(world, "canon", "person:rival") == rival_before            # no cast move
    # no hidden turn: no event:turn_* row, transcript, memory, last-seen or audit row
    assert _session_rows(world) == before
    assert counters_from_session(PorcelainWorldReads(world), arc).turns_elapsed == turns_before


def test_then_turn_one_naming_them_gets_the_not_here_line(world):
    # the two parts together: what the opening showed is now player-known, elsewhere
    arc = _seed(world)
    settle_opening(world, arc, _OPENING, turn=0)
    got = named_elsewhere(world, player_frame=PLAYER_FRAME,
                          player_input="Let me see the sack and the hearth.",
                          protagonist=PLAYER, scene="place:study", scene_features=[],
                          ancestors=[])
    # the place's name is canon-only here, so the line names it by its id's own words
    assert [(e, pl) for e, _l, pl in got] == [("obj:torn_laundry_sack", "warrant room"),
                                              ("obj:hearth", "warrant room")]


def test_an_extractor_failure_leaves_play_as_before(world):
    arc = make_arc()
    seed_arc(world, arc)
    # no scripted extraction: the stub model raises inside extract
    trace = settle_opening(world, arc, _OPENING, turn=0)
    assert any("post_extract" in c for c in trace.dropped_cohorts)
    assert _in(world, "canon", "obj:torn_laundry_sack") is None


def test_empty_prose_settles_nothing(world):
    arc = make_arc()
    seed_arc(world, arc)
    assert settle_opening(world, arc, "  ", turn=0).dropped_cohorts == []
