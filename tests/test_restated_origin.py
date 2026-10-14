"""RESTATED-ORIGIN r2 (docs/design/RESTATED-ORIGIN.md, cr GREEN; R20 run 11's key-ring).

"...grabbing for the key-ring at his belt" was extracted as `in obj:belt` (restating where it
was) AND `in person:player`, one batch, one valid time: the engine served it `conflicted`.
Construct now stamps the whole containment family at the turn (attributes kept as written)
and drops a row that only restates the current container when the same batch moves the
thing. Two new places stay, for the engine's honest conflict."""

from construct.turnloop import _drop_restated_origins, _stamp_temporal_state, settle_opening
from tests.test_integration import PLAYER, make_arc, run_turn, seed_arc, world  # noqa: F401
from tests.test_placements_by_rule import StubProvider

T = 1000.0
_BASE = {"kind": "action", "claims_are": "act", "moves_to": "", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""}


def _seed_ring(world):
    world.porcelain.ingest_structured([
        {"entity": "obj:belt", "attribute": "kind", "value": "belt"},
        {"entity": "obj:belt", "attribute": "in", "value": "place:study"},
        {"entity": "obj:key_ring", "attribute": "kind", "value": "key-ring"},
        {"entity": "obj:key_ring", "attribute": "name", "value": "key-ring"},
        {"entity": "obj:key_ring", "attribute": "in", "value": "obj:belt"}],
        frame="canon", classify="rules")


def _row(entity, attribute, value, vf=T):
    r = {"entity": entity, "attribute": attribute, "value": value, "value_type": "entity"}
    if vf is not None:
        r["valid_from"] = vf
    return r


# ---------------------------------------------------------------- the pure rule (1-7b)

def test_run_11s_key_ring_drops_the_restated_belt(world):
    _seed_ring(world)
    rows = [_row("obj:key_ring", "in", "obj:belt"), _row("obj:key_ring", "in", PLAYER)]
    kept, dropped = _drop_restated_origins(world.porcelain, rows, as_of=None)
    assert kept == [rows[1]] and dropped == [("obj:key_ring", "obj:belt")]


def test_two_new_places_stay_for_the_honest_conflict(world):
    _seed_ring(world)
    rows = [_row("obj:key_ring", "in", "place:a"), _row("obj:key_ring", "in", "place:b")]
    assert _drop_restated_origins(world.porcelain, rows, as_of=None) == (rows, [])


def test_no_known_container_keeps_both(world):
    rows = [_row("obj:ghost", "in", "obj:belt"), _row("obj:ghost", "in", PLAYER)]
    assert _drop_restated_origins(world.porcelain, rows, as_of=None) == (rows, [])
    world.porcelain.ingest_structured([
        {"entity": "obj:twin", "attribute": "in", "value": "obj:belt", "valid_from": 5.0},
        {"entity": "obj:twin", "attribute": "in", "value": PLAYER, "valid_from": 5.0}],
        frame="canon", classify="rules")
    assert world.porcelain.state("obj:twin", "in")["status"] == "conflicted"
    rows = [_row("obj:twin", "in", "obj:belt"), _row("obj:twin", "in", "place:study")]
    assert _drop_restated_origins(world.porcelain, rows, as_of=None) == (rows, [])


def test_different_valid_times_are_different_groups(world):
    _seed_ring(world)
    rows = [_row("obj:key_ring", "in", "obj:belt", T), _row("obj:key_ring", "in", PLAYER, T + 1)]
    assert _drop_restated_origins(world.porcelain, rows, as_of=None) == (rows, [])


def test_a_lone_restatement_is_kept(world):
    _seed_ring(world)
    rows = [_row("obj:key_ring", "in", "obj:belt")]
    assert _drop_restated_origins(world.porcelain, rows, as_of=None) == (rows, [])


def test_other_attributes_of_the_entity_survive(world):
    _seed_ring(world)
    alias = {"entity": "obj:key_ring", "attribute": "alias", "value": "the warder's keys"}
    name = {"entity": "obj:key_ring", "attribute": "name", "value": "key-ring"}
    rows = [alias, _row("obj:key_ring", "in", "obj:belt"), name,
            _row("obj:key_ring", "in", PLAYER)]
    kept, _ = _drop_restated_origins(world.porcelain, rows, as_of=None)
    assert alias in kept and name in kept and len(kept) == 3


def test_a_holding_form_groups_with_in_after_the_family_stamp(world):
    _seed_ring(world)
    raw = [_row("obj:key_ring", "in", "obj:belt", vf=None),
           _row("obj:key_ring", "held_by", PLAYER, vf=None)]
    stamped = _stamp_temporal_state(raw, 3)
    assert stamped[0]["valid_from"] == stamped[1]["valid_from"]          # one coordinate
    assert stamped[1]["attribute"] == "held_by"                          # kept as written
    kept, dropped = _drop_restated_origins(world.porcelain, stamped, as_of=None)
    assert [r["attribute"] for r in kept] == ["held_by"]
    assert dropped == [("obj:key_ring", "obj:belt")]


def test_the_family_stamp_keeps_explicit_times_and_other_attributes():
    rows = _stamp_temporal_state([
        {"entity": "obj:a", "attribute": "worn_by", "value": PLAYER},
        {"entity": "obj:b", "attribute": "carried_by", "value": PLAYER},
        {"entity": "obj:c", "attribute": "held_by", "value": PLAYER, "valid_from": 7.0},
        {"entity": "obj:d", "attribute": "colour", "value": "red"}], 4)
    assert rows[0]["valid_from"] == rows[1]["valid_from"] != 7.0
    assert rows[2]["valid_from"] == 7.0 and "valid_from" not in rows[3]


# ---------------------------------------------------------------- end to end (8, 9)

def test_the_player_channel_folds_the_key_ring_to_the_player(world):
    _seed_ring(world)
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([
        {"items": [{"entity": "obj:key_ring", "attribute": "in", "value": "obj:belt"},
                   {"entity": "obj:key_ring", "attribute": "in", "value": "person:you"}]},
        {"items": []}])
    prov = StubProvider([dict(_BASE), {"prose": "The key-ring comes away in your fist."}])
    r = run_turn(world, arc, prov, "I grab the key-ring at his belt.", turn=2,
                 scope=[PLAYER, "place:study", "obj:belt", "obj:key_ring"])
    assert ("obj:key_ring", "obj:belt") in r.trace.restated_origin
    st = world.porcelain.state("obj:key_ring", "in")
    assert st["status"] == "known" and st["fact"]["value"] == PLAYER


def test_the_settle_folds_the_key_ring_to_the_player(world):
    _seed_ring(world)
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": [
        {"entity": "obj:key_ring", "attribute": "in", "value": "obj:belt"},
        {"entity": "obj:key_ring", "attribute": "held_by", "value": PLAYER}]})
    trace = settle_opening(world, arc, "The key-ring is yours, lifted off his belt.", turn=0)
    assert ("obj:key_ring", "obj:belt") in trace.restated_origin
    st = world.porcelain.state("obj:key_ring", "in")
    assert st["status"] == "known" and st["fact"]["value"] == PLAYER
