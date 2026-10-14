"""NARRATED-OBJECTS-LAND (docs/design/NARRATED-OBJECTS-LAND.md r2, cr GREEN; R20 run 11).

An object the narrator settle promoted with no live location, tied by a receipt-confirmed
entity-valued row to something present at the scene, is placed `in` the scene by rule.
Run 11: "The lower pin drops free onto the wet stone below the bell-pull" settled as
`part_of obj:bell_pull_plate` with no `in`, and the next turn's take was refused.

The settles here are the opening's (`settle_opening` shares the turn's fact pipeline); the
scene is the player's place, `place:study`. The receipt-boundary cases call the phase
directly with hand-made receipts."""

from construct.turnloop import TurnTrace, _land_narrated_objects, settle_opening
from tests.test_integration import PLAYER, PLAYER_FRAME, make_arc, seed_arc, world  # noqa: F401
from tests.test_placements_by_rule import _Spy, _verdict

SCENE = "place:study"
PROSE = "The lower pin drops free onto the stone below the bell-pull."


def _seed(world, *rows):
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "obj:bell_pull_plate", "attribute": "kind", "value": "plate"},
        {"entity": "obj:bell_pull_plate", "attribute": "in", "value": SCENE},
        {"entity": "obj:irons", "attribute": "kind", "value": "irons"},
        {"entity": "obj:irons", "attribute": "in", "value": PLAYER},
        *rows], frame="canon", classify="rules")
    return arc


def _settle(world, arc, rows):
    world._extractions.append({"items": list(rows)})
    return settle_opening(world, arc, PROSE, turn=0)


def _in(world, frame, entity):
    st = world.porcelain.state(entity, "in", frame=frame)
    return st["fact"]["value"] if st["status"] == "known" else None


_PIN = [{"entity": "obj:lower_pin", "attribute": "kind", "value": "pin"},
        {"entity": "obj:lower_pin", "attribute": "part_of", "value": "obj:bell_pull_plate"},
        {"entity": "obj:lower_pin", "attribute": "fastening_anything", "value": "false"}]


def test_run_11s_pin_lands_in_the_scene_as_state_by_rule(world, monkeypatch):
    arc = _seed(world)
    spy = _Spy(world, monkeypatch)
    trace = _settle(world, arc, _PIN)
    assert _in(world, "canon", "obj:lower_pin") == SCENE
    assert _in(world, PLAYER_FRAME, "obj:lower_pin") == SCENE
    assert trace.landed == ["obj:lower_pin"]
    assert spy.mode("obj:lower_pin", "in", SCENE) == "rules"      # no model call for it
    assert _verdict(world, "obj:lower_pin", "in") == "STATE"
    assert "obj:lower_pin" in world.porcelain.contents(SCENE)      # the next scene lists it


def test_a_tie_through_what_the_protagonist_holds_lands(world):
    arc = _seed(world)
    _settle(world, arc, [{"entity": "obj:pulp", "attribute": "kind", "value": "pulp"},
                         {"entity": "obj:pulp", "attribute": "on", "value": "obj:irons"}])
    assert _in(world, "canon", "obj:pulp") == SCENE


def test_a_part_of_something_present_counts_through_composition(world):
    # the door has no location of its own: it is part_of the cupboard, which is in the scene
    arc = _seed(world, {"entity": "obj:cupboard", "attribute": "kind", "value": "cupboard"},
                {"entity": "obj:cupboard", "attribute": "in", "value": SCENE},
                {"entity": "obj:door", "attribute": "kind", "value": "door"},
                {"entity": "obj:door", "attribute": "part_of", "value": "obj:cupboard"})
    assert world.porcelain.locate("obj:door") == []
    _settle(world, arc, [{"entity": "obj:hasp", "attribute": "kind", "value": "hasp"},
                         {"entity": "obj:hasp", "attribute": "against", "value": "obj:door"}])
    assert _in(world, "canon", "obj:hasp") == SCENE


def test_something_tied_only_to_an_absent_place_stays_absent(world):
    arc = _seed(world)
    trace = _settle(world, arc, [
        {"entity": "obj:letter", "attribute": "kind", "value": "letter"},
        {"entity": "obj:letter", "attribute": "sent_from", "value": "place:flat"}])
    assert _in(world, "canon", "obj:letter") is None and trace.landed == []


def test_literal_rows_alone_are_not_a_tie(world):
    arc = _seed(world)
    _settle(world, arc, [{"entity": "obj:pin", "attribute": "kind", "value": "pin"},
                         {"entity": "obj:pin", "attribute": "position",
                          "value": "below the bell-pull"}])
    assert _in(world, "canon", "obj:pin") is None


def test_a_located_or_held_object_is_never_moved(world):
    arc = _seed(world, {"entity": "obj:cup", "attribute": "kind", "value": "cup"},
                {"entity": "obj:cup", "attribute": "in", "value": "place:flat"},
                {"entity": "obj:coin", "attribute": "kind", "value": "coin"},
                {"entity": "obj:coin", "attribute": "in", "value": PLAYER})
    trace = _settle(world, arc, [
        {"entity": "obj:cup", "attribute": "beside", "value": "obj:bell_pull_plate"},
        {"entity": "obj:coin", "attribute": "against", "value": "obj:bell_pull_plate"}])
    assert _in(world, "canon", "obj:cup") == "place:flat"
    assert _in(world, "canon", "obj:coin") == PLAYER
    assert trace.landed == []


def test_a_conflicted_location_is_left_alone(world):
    arc = _seed(world, {"entity": "obj:belt", "attribute": "kind", "value": "belt"})
    world.porcelain.ingest_structured([
        {"entity": "obj:key_ring", "attribute": "in", "value": "obj:belt", "valid_from": 5.0},
        {"entity": "obj:key_ring", "attribute": "in", "value": PLAYER, "valid_from": 5.0}],
        frame="canon", classify="rules")
    assert world.porcelain.state("obj:key_ring", "in")["status"] == "conflicted"
    trace = _settle(world, arc, [{"entity": "obj:key_ring", "attribute": "against",
                                  "value": "obj:bell_pull_plate"}])
    assert trace.landed == []


# ------------------------------------------------ the receipt boundary (r2, cr), called directly

def _phase(world, arc, promote, receipt):
    trace = TurnTrace(turn=1)
    rows = _land_narrated_objects(world.porcelain, arc, promote, receipt, scene=SCENE, turn=1,
                                  horizon=None, player_frame=PLAYER_FRAME, canon_table={},
                                  trace=trace)
    return rows, trace


def _promoted(world, rows):
    """Write `rows` to canon as the promotion would, returning the rows and their receipt."""
    receipt = world.porcelain.ingest_structured(rows, frame="canon", classify="rules")
    return rows, (receipt.to_dict()["rows"] if hasattr(receipt, "to_dict") else receipt["rows"])


def test_an_empty_promotion_receipt_lands_nothing(world):
    arc = _seed(world)
    promote, _ = _promoted(world, list(_PIN))
    rows, trace = _phase(world, arc, promote, [])
    assert rows == [] and trace.landed == []
    assert _in(world, "canon", "obj:lower_pin") is None
    assert _in(world, PLAYER_FRAME, "obj:lower_pin") is None


def test_a_receipt_missing_the_tie_row_lands_nothing(world):
    arc = _seed(world)
    promote, receipt = _promoted(world, list(_PIN))
    receipt = [r for r in receipt if r.get("attribute") != "part_of"]
    rows, trace = _phase(world, arc, promote, receipt)
    assert rows == [] and _in(world, "canon", "obj:lower_pin") is None


def test_a_receipt_missing_an_unrelated_row_still_lands(world):
    arc = _seed(world)
    promote, receipt = _promoted(world, list(_PIN))
    receipt = [r for r in receipt if r.get("attribute") != "fastening_anything"]
    rows, trace = _phase(world, arc, promote, receipt)
    assert trace.landed == ["obj:lower_pin"]
    assert [(r["entity"], r["attribute"]) for r in rows] == [("obj:lower_pin", "in")]
    assert _in(world, PLAYER_FRAME, "obj:lower_pin") == SCENE


def test_an_unconfirmed_landing_is_not_mirrored(world, monkeypatch):
    arc = _seed(world)
    promote, receipt = _promoted(world, list(_PIN))
    real = world.porcelain.ingest_structured

    def empty_for_landing(rows, *a, **kw):
        if any(r.get("attribute") == "in" and r.get("entity") == "obj:lower_pin" for r in rows):
            return {"rows": []}
        return real(rows, *a, **kw)
    monkeypatch.setattr(world.porcelain, "ingest_structured", empty_for_landing)
    rows, trace = _phase(world, arc, promote, receipt)
    assert rows == [] and trace.landed == []
    assert _in(world, PLAYER_FRAME, "obj:lower_pin") is None


def test_a_raising_landing_never_sinks_the_settle(world, monkeypatch):
    arc = _seed(world)
    promote, receipt = _promoted(world, list(_PIN))
    real = world.porcelain.ingest_structured

    def boom(rows, *a, **kw):
        if any(r.get("entity") == "obj:lower_pin" and r.get("attribute") == "in" for r in rows):
            raise RuntimeError("gate refused")
        return real(rows, *a, **kw)
    monkeypatch.setattr(world.porcelain, "ingest_structured", boom)
    rows, trace = _phase(world, arc, promote, receipt)
    assert rows == [] and trace.landed == []
    assert _in(world, PLAYER_FRAME, "obj:lower_pin") is None


def test_an_epilogue_or_empty_promotion_does_nothing(world):
    arc = _seed(world)
    assert _phase(world, arc, [], []) == ([], TurnTrace(turn=1))


def test_a_settle_whose_promotion_returns_an_empty_receipt_lands_nothing(world, monkeypatch):
    arc = _seed(world)
    real = world.porcelain.ingest_structured

    def empty_promote(rows, *a, frame=None, classify=None, **kw):
        if frame == "canon" and classify == "batch":
            return {"rows": []}
        return real(rows, *a, frame=frame, classify=classify, **kw)
    monkeypatch.setattr(world.porcelain, "ingest_structured", empty_promote)
    trace = _settle(world, arc, _PIN)
    assert trace.landed == []
    assert _in(world, "canon", "obj:lower_pin") is None
    assert _in(world, PLAYER_FRAME, "obj:lower_pin") is None


def test_a_settle_whose_promotion_ingest_raises_lands_nothing(world, monkeypatch):
    # cr on 6fe9154: the first-phase boundary itself. The promotion's canon/batch ingest
    # raises; the settle's fail-open ingest yields an empty receipt, so nothing lands.
    arc = _seed(world)
    real = world.porcelain.ingest_structured

    raised = []

    def raising_promote(rows, *a, frame=None, classify=None, **kw):
        if frame == "canon" and classify == "batch":
            raised.append([r.get("entity") for r in rows])
            raise RuntimeError("promotion gate refused")
        return real(rows, *a, frame=frame, classify=classify, **kw)
    monkeypatch.setattr(world.porcelain, "ingest_structured", raising_promote)
    trace = _settle(world, arc, _PIN)
    assert raised and "obj:lower_pin" in raised[0]            # the promotion did raise
    assert trace.landed == []
    assert _in(world, "canon", "obj:lower_pin") is None
    assert _in(world, PLAYER_FRAME, "obj:lower_pin") is None
