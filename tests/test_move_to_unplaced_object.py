"""MOVE-TO-UNPLACED-OBJECT (cr GREEN on spec r2): moving to a thing is decided by where it is
(facts first), then by the classifier's tri-state `within_scene`, and by the fixture head-noun
list only when the classifier gave no verdict.

R20 run 9: the player walked "to the gate table" three times; refer resolved it to an object
born in play with no location, and the head noun "table" absorbed every escape as an in-room
step."""

from construct.intent import TurnIntent
from construct.provider import StubProvider
from construct.turnloop import MovementStatus
from tests.test_integration import (PLAYER, PLAYER_FRAME, make_arc, run_turn,  # noqa: F401
                                    seed_arc, world)

_CLASSIFY = {"requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
             "commitment": "", "claims_are": "act"}


def _ingest(world, rows, frame="canon"):
    world.porcelain.ingest_structured(rows, frame=frame)


def _place(pid, name):
    return [{"entity": pid, "attribute": "kind", "value": "room", "timeless": True},
            {"entity": pid, "attribute": "name", "value": name}]


def _obj(oid, name, kind="table", where=None):
    rows = [{"entity": oid, "attribute": "kind", "value": kind, "timeless": True},
            {"entity": oid, "attribute": "name", "value": name}]
    if where:
        rows.append({"entity": oid, "attribute": "in", "value": where, "value_type": "entity"})
    return rows


def _turn(world, line, moves_to, *answers, within=..., turn=2, scope_extra=()):
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    verdict = dict(_CLASSIFY, kind="action", moves_to=moves_to)
    if within is not ...:
        verdict["within_scene"] = within
    provider = StubProvider([verdict, *answers, {"prose": "You go."}])
    r = run_turn(world, arc, provider, line, turn=turn,
                 scope=[PLAYER, "place:study", *scope_extra])
    return r, provider


def _where(world, entity):
    return (world.porcelain.locate(entity) or [None])[0]


# ---- the field is tri-state end to end ------------------------------------------------

def test_within_scene_is_tri_state():
    base = {"kind": "action", "claims_are": "act", "moves_to": "the table"}
    assert TurnIntent.from_verdict(dict(base), "x").within_scene is None
    assert TurnIntent.from_verdict(dict(base, within_scene=True), "x").within_scene is True
    assert TurnIntent.from_verdict(dict(base, within_scene=False), "x").within_scene is False
    for junk in ("yes", 1, 0, None, "false"):
        assert TurnIntent.from_verdict(dict(base, within_scene=junk), "x").within_scene is None


# ---- 1. run 9's shape: an unlocated object, somewhere else --------------------------------

def test_run9_unlocated_table_elsewhere_moves_the_player_and_places_the_table(world):
    _ingest(world, _obj("obj:gate_table", "gate table"))     # refer resolves it, as in run 9
    r, _ = _turn(world, "I slip through the opened door. Gate table first.", "Gate table",
                 {"verdict": "new", "match": ""}, within=False)
    assert r.trace.movement_status != MovementStatus.IN_SCENE
    here = _where(world, PLAYER)
    assert here and here != "place:study"
    assert _where(world, "obj:gate_table") == here      # the table rode the move's commit


# ---- 2. Cx 325/327 kept: a step to a table in the room ------------------------------------

def test_step_to_an_unlocated_table_within_the_scene_stays_and_places_it(world):
    _ingest(world, _obj("obj:table", "the table"))
    r, _ = _turn(world, "I step to the table.", "the table", within=True)
    assert r.trace.movement_status == MovementStatus.IN_SCENE
    assert _where(world, PLAYER) == "place:study"
    assert _where(world, "obj:table") == "place:study"


# ---- 3. located elsewhere: where the PLAYER knows it is ------------------------------------

def test_located_elsewhere_and_known_to_the_player_travels_there(world):
    _ingest(world, _place("place:office", "the office") + _obj("obj:ledger", "the ledger",
                                                               kind="ledger",
                                                               where="place:office"))
    _ingest(world, [{"entity": "obj:ledger", "attribute": "in", "value": "place:office",
                     "value_type": "entity"}], frame=PLAYER_FRAME)
    r, _ = _turn(world, "I go to the ledger.", "the ledger")
    assert _where(world, PLAYER) == "place:office"
    assert r.trace.movement_status != MovementStatus.IN_SCENE


# ---- 9. entitlement: canon knows, the player doesn't --------------------------------------

def test_located_elsewhere_but_unlearned_is_undiscovered_and_leaks_nothing(world):
    _ingest(world, _place("place:vault", "the vault") + _obj("obj:ledger", "the ledger",
                                                             kind="ledger",
                                                             where="place:vault"))
    r, _ = _turn(world, "I go to the ledger.", "the ledger")
    assert r.trace.movement_status == MovementStatus.UNDISCOVERED
    assert _where(world, PLAYER) == "place:study"
    assert "place:vault" not in (r.trace.briefing or "")


# ---- 4. located here: facts win over the field --------------------------------------------

def test_located_here_is_in_scene_whatever_the_classifier_says(world):
    _ingest(world, _obj("obj:lamp", "the lamp", kind="lamp", where="place:study"))
    r, _ = _turn(world, "I go to the lamp.", "the lamp", within=False)
    assert r.trace.movement_status == MovementStatus.IN_SCENE
    assert _where(world, PLAYER) == "place:study"


# ---- 5 / 8. no verdict: today's behaviour on both paths ------------------------------------

def test_no_verdict_unlocated_fixture_keeps_the_head_noun_rule(world):
    _ingest(world, _obj("obj:table", "the table"))
    r, _ = _turn(world, "I step to the table.", "the table")      # field absent
    assert r.trace.movement_status == MovementStatus.IN_SCENE
    assert _where(world, PLAYER) == "place:study"
    assert _where(world, "obj:table") is None                     # untouched, as today


def test_no_verdict_zero_candidate_fixture_keeps_the_head_noun_rule(world):
    r, _ = _turn(world, "I go to the rain barrel.", "the rain barrel")
    assert r.trace.movement_status == MovementStatus.IN_SCENE
    assert _where(world, PLAYER) == "place:study"


# ---- 6. the zero-candidate guard reads the field when given ---------------------------------

def test_zero_candidate_fixture_elsewhere_binds_or_mints(world):
    r, _ = _turn(world, "I cross the yard to the rain barrel.", "the rain barrel",
                 {"verdict": "new", "match": ""}, within=False)
    assert r.trace.movement_status != MovementStatus.IN_SCENE
    assert _where(world, PLAYER) != "place:study"


def test_zero_candidate_within_scene_true_stays(world):
    r, _ = _turn(world, "I go to the hearth.", "the hearth", within=True)
    assert r.trace.movement_status == MovementStatus.IN_SCENE
    assert _where(world, PLAYER) == "place:study"


# ---- 10. the commit seam ------------------------------------------------------------------

def test_existing_place_bind_carries_the_object(world):
    _ingest(world, _place("place:quay", "the quay") + _obj("obj:gate_table", "gate table"))
    r, _ = _turn(world, "I head out to the gate table.", "gate table",
                 {"verdict": "existing", "match": "place:quay"}, within=False)
    assert _where(world, PLAYER) == "place:quay"
    assert _where(world, "obj:gate_table") == "place:quay"


def test_known_place_token_reuse_carries_the_object(world):
    """cr RED on 119fc0a: the phrase resolves exactly to the unlocated object, and a
    different known place shares a token, so known-place reuse wins before the semantic
    bind. Both the player and the object end at the reused place."""
    _ingest(world, _place("place:gate", "the gate") + _obj("obj:gate_table", "gate table"))
    r, _ = _turn(world, "I go out to the gate table.", "gate table", within=False,
                 scope_extra=["place:gate"])
    assert _where(world, PLAYER) == "place:gate"
    assert _where(world, "obj:gate_table") == "place:gate"


def test_blocked_route_moves_neither_player_nor_object(world, monkeypatch):
    import construct.turnloop as tl
    _ingest(world, _place("place:quay", "the quay") + _obj("obj:gate_table", "gate table"))
    monkeypatch.setattr(tl, "_route_obstruction", lambda *a, **k: {
        "status": "blocked", "via": "obj:door1",
        "evidence": [{"entity": "obj:door1", "attribute": "state", "value": "shut"}]})
    r, _ = _turn(world, "I head out to the gate table.", "gate table",
                 {"verdict": "existing", "match": "place:quay"}, within=False)
    assert r.trace.movement_status == MovementStatus.BLOCKED
    assert _where(world, PLAYER) == "place:study"
    assert _where(world, "obj:gate_table") is None


# ---- 11. the scene reaches the classifier ---------------------------------------------------

def test_the_classify_prompt_names_the_current_scene(world):
    _ingest(world, [{"entity": "place:study", "attribute": "name", "value": "the study"}])
    _, provider = _turn(world, "I look around.", "")
    prompt = provider.calls[0][0]
    assert "THE PLAYER IS NOW IN: the study." in prompt
