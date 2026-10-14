"""PLACE-NAME-ANCHOR r2 (docs/design/PLACE-NAME-ANCHOR.md, cr GREEN; R20 runs 10-12).

The briefing's location anchor named the scene only from the player frame, and the frame never
held the scene's name: "YOU ARE AT the place you now stand in." on nearly every turn. Now the
player knows the name of the place they stand in: concealment first (fail closed), the frame's
own name read at the horizon, the canon name at the horizon, one rules write, and the trace set
only on a receipt-confirmed row."""

from construct import turnloop
from construct.adapter import PorcelainWorldReads
from construct.arc.executor import turn_time
from construct.turnloop import TurnTrace, _name_the_scene, settle_opening
from tests.test_integration import (  # noqa: F401
    PLAYER, PLAYER_FRAME, make_arc, run_turn, seed_arc, world)
from tests.test_placements_by_rule import StubProvider, _Spy

SCENE = "place:study"
H = turn_time(2)          # the turn's play horizon covers its own coordinate
_BASE = {"kind": "action", "claims_are": "act", "moves_to": "", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""}


def _name(world, value="the study", frame="canon", vf=None):
    row = {"entity": SCENE, "attribute": "name", "value": value}
    row.update({"valid_from": vf} if vf is not None else {})
    world.porcelain.ingest_structured([row], frame=frame, classify="rules")


def _turn(world, verdict=None, text="I look around."):
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE, **(verdict or {})}, {"prose": "The room keeps still."}])
    r = run_turn(world, arc, prov, text, turn=2, scope=[PLAYER, SCENE])
    prompt = next(c[0] for c in reversed(prov.calls) if "YOU ARE AT" in c[0])
    return r, prompt


def _frame_name(world, entity=SCENE):
    st = world.porcelain.state(entity, "name", frame=PLAYER_FRAME)
    return st["fact"]["value"] if st["status"] == "known" else None


def _helper(world, horizon=None, scene=SCENE, arc=None):
    trace = TurnTrace(turn=2)
    _name_the_scene(world.porcelain, arc or make_arc(), scene, player_frame=PLAYER_FRAME,
                    turn=2, horizon=horizon, live_reads=PorcelainWorldReads(world), trace=trace)
    return trace


# ---------------------------------------------------------------- the rule, end to end (1-3)

def test_a_named_scene_is_named_in_the_frame_and_the_anchor(world, monkeypatch):
    _name(world)
    spy = _Spy(world, monkeypatch)
    r, prompt = _turn(world)
    assert _frame_name(world) == "the study"
    assert "YOU ARE AT: the study." in prompt
    assert r.trace.place_named == SCENE
    writes = [m for rows, m in spy.calls for row in rows
              if row.get("entity") == SCENE and row.get("attribute") == "name"]
    assert writes == ["rules"]


def test_a_name_the_frame_already_holds_is_kept(world, monkeypatch):
    _name(world)
    _name(world, "the den", frame=PLAYER_FRAME)
    r, prompt = _turn(world)
    assert _frame_name(world) == "the den" and "YOU ARE AT: the den." in prompt
    assert r.trace.place_named == ""


def test_a_conflicted_frame_name_is_not_overwritten(world, monkeypatch):
    # two same-time frame names fold to one value in the engine, so the frame read itself
    # reports `conflicted` here: the branch under test is the helper's, not the fold's
    _name(world)
    real = world.porcelain.state

    def state(entity, attribute, *a, frame="canon", **k):
        if frame == PLAYER_FRAME and attribute == "name":
            return {"status": "conflicted"}
        return real(entity, attribute, *a, frame=frame, **k)
    monkeypatch.setattr(world.porcelain, "state", state)
    trace = _helper(world)
    assert trace.place_named == ""
    assert not world.porcelain.facts(PLAYER_FRAME, entity=SCENE, attribute="name")


def test_a_concealed_name_is_never_mirrored(world, monkeypatch):
    _name(world)
    monkeypatch.setattr(turnloop, "arc_protected_keys", lambda arc, reads=None: {(SCENE, "name")})
    r, prompt = _turn(world)
    assert _frame_name(world) is None and r.trace.place_named == ""
    assert "YOU ARE AT the place you now stand in." in prompt


def test_an_entity_valued_name_is_never_mirrored(world):
    # cr on 61f16d6: a `known` name whose value is an entity id is not a name to speak
    world.porcelain.ingest_structured([
        {"entity": "person:keeper", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": SCENE, "attribute": "name", "value": "person:keeper",
         "value_type": "entity"}], frame="canon", classify="rules")
    st = world.porcelain.state(SCENE, "name")
    assert st["status"] == "known" and st["fact"]["value_type"] == "entity"
    r, prompt = _turn(world)
    assert r.trace.place_named == "" and _frame_name(world) is None
    assert "YOU ARE AT the place you now stand in." in prompt


# ---------------------------------------------------------------- horizons (4, 8)

def test_a_canon_name_past_the_horizon_is_not_mirrored(world):
    _name(world, vf=H + 5000.0)
    trace = _helper(world, horizon=H)
    assert trace.place_named == "" and _frame_name(world) is None


def test_a_frame_name_past_the_horizon_does_not_suppress_the_mirror(world):
    _name(world, vf=10.0)
    _name(world, "the later den", frame=PLAYER_FRAME, vf=H + 5000.0)
    trace = _helper(world, horizon=H)
    assert trace.place_named == SCENE
    st = world.porcelain.state(SCENE, "name", frame=PLAYER_FRAME, as_of=H)
    assert st["status"] == "known" and st["fact"]["value"] == "the study"


# ---------------------------------------------------------------- failure modes (5, 9, 10)

def test_an_unreadable_name_writes_nothing(world, monkeypatch):
    _name(world)

    def boom(*a, **k):
        raise RuntimeError("store unreadable")
    monkeypatch.setattr(world.porcelain, "state", boom)
    trace = _helper(world)
    assert trace.place_named == ""


def test_unreadable_protection_fails_closed(world, monkeypatch):
    _name(world)

    def boom(*a, **k):
        raise RuntimeError("concealment unreadable")
    monkeypatch.setattr(turnloop, "arc_protected_keys", boom)
    trace = _helper(world)
    assert trace.place_named == "" and _frame_name(world) is None
    assert "place_name (protection unreadable)" in trace.dropped_cohorts


def test_a_refused_write_leaves_the_trace_empty(world, monkeypatch):
    _name(world)
    real = world.porcelain.ingest_structured

    def empty(rows, *a, frame=None, **kw):
        if frame == PLAYER_FRAME:
            return {"rows": []}
        return real(rows, *a, frame=frame, **kw)
    monkeypatch.setattr(world.porcelain, "ingest_structured", empty)
    assert _helper(world).place_named == ""


def test_a_raising_write_leaves_the_trace_empty_and_the_turn_completes(world, monkeypatch):
    _name(world)
    real = world.porcelain.ingest_structured

    def boom(rows, *a, frame=None, **kw):
        if frame == PLAYER_FRAME and any(r.get("attribute") == "name" for r in rows):
            raise RuntimeError("gate refused")
        return real(rows, *a, frame=frame, **kw)
    monkeypatch.setattr(world.porcelain, "ingest_structured", boom)
    r, prompt = _turn(world)
    assert r.trace.place_named == "" and "YOU ARE AT the place you now stand in." in prompt


# ---------------------------------------------------------------- after a move, the opening (6, 7, 11)

def test_a_place_moved_into_this_turn_is_named_this_turn(world):
    world.porcelain.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:hall", "attribute": "name", "value": "the long hall"},
        {"entity": SCENE, "attribute": "connects_to", "value": "place:hall",
         "value_type": "entity", "timeless": True}], frame="canon", classify="rules")
    r, prompt = _turn(world, {"moves_to": "the long hall"}, "I go to the long hall.")
    assert world.porcelain.locate(PLAYER)[0] == "place:hall"
    assert r.trace.place_named == "place:hall"
    assert "YOU ARE AT: the long hall." in prompt


def test_the_opening_names_its_scene(world):
    _name(world)
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": []})
    trace = settle_opening(world, arc, "The study is quiet.", turn=0)
    assert trace.place_named == SCENE and _frame_name(world) == "the study"


def test_a_blank_opening_still_names_its_scene(world):
    _name(world)
    arc = make_arc()
    seed_arc(world, arc)
    trace = settle_opening(world, arc, "   ", turn=0)
    assert trace.place_named == SCENE and _frame_name(world) == "the study"
