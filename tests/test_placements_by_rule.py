"""PLACEMENTS-BY-RULE (docs/design/PLACEMENTS-BY-RULE.md r2): every placement or companionship
row construct decides itself is written with classify="rules" — movable STATE, no model call —
while the guardrails (kind, name, place containment) keep their verdicts."""
import sqlite3

from construct import game
from construct.adapter import PorcelainWorldReads
from construct.arc.executor import turn_time
from construct.cast import CastNode
from construct.provider import _SILENT_DEFAULTS
from construct.provider import StubProvider as _Stub
from construct.turnloop import _grant_moved_place, _mint_held_object
from tests.test_integration import PLAYER, make_arc, run_turn, seed_arc, world  # noqa: F401

_BASE = {"kind": "action", "claims_are": "act", "moves_to": "", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""}


def StubProvider(responses):  # noqa: N802
    return _Stub(responses, silent_defaults={
        **_SILENT_DEFAULTS, "ndg": ("directive", {"thread": "", "directive": ""}),
        "npt": ("acts", {"acts": False, "action": "", "speaks": False, "intent": "",
                         "line_hint": ""})})


class _Spy:
    """Records every ingest_structured call's rows and classify mode."""

    def __init__(self, world, monkeypatch):
        self.calls: list[tuple[list, str]] = []
        real = world.porcelain.ingest_structured

        def spy(rows, *a, **kw):
            self.calls.append((list(rows), kw.get("classify", "inline")))
            return real(rows, *a, **kw)
        monkeypatch.setattr(world.porcelain, "ingest_structured", spy)

    def mode(self, entity, attribute, value=None):
        modes = [m for rows, m in self.calls for r in rows
                 if r.get("entity") == entity and r.get("attribute") == attribute
                 and (value is None or r.get("value") == value)]
        assert modes, f"no write of {entity} · {attribute}"
        return modes[-1]


def _verdict(world, entity, attribute):
    """The stored durability verdict of the latest row on (entity, attribute)."""
    facts = world.porcelain.facts("canon", entity=entity, attribute=attribute)
    aid = facts[-1]["provenance"]["assertion_id"]
    conn = sqlite3.connect(f"file:{world.buffer.path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT durability FROM sidecar_classification "
                           "WHERE assertion_id=?", (aid,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _turn(world, verdict, text, scope, turn=2, cast=None):
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE, **verdict}, {"prose": "It is done."}])
    return run_turn(world, arc, prov, text, turn=turn, scope=scope, cast=cast)


# ------------------------------------------------------- 1. a spy per table row

def test_take_is_rules_and_state(world, monkeypatch):
    world.ingest_structured([
        {"entity": "obj:spoon", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:spoon", "attribute": "in", "value": "place:study"},
        {"entity": "obj:spoon", "attribute": "name", "value": "brass spoon"}])
    spy = _Spy(world, monkeypatch)
    r = _turn(world, {"takes": "the brass spoon"}, "I pick up the brass spoon.",
              ["obj:spoon", PLAYER, "place:study"])
    assert r.trace.took == "obj:spoon"
    assert spy.mode("obj:spoon", "in", PLAYER) == "rules"
    assert _verdict(world, "obj:spoon", "in") == "STATE"            # 2. stored STATE


def test_drop_is_rules(world, monkeypatch):
    world.ingest_structured([{"entity": "obj:opener", "attribute": "kind", "value": "object"},
                             {"entity": "obj:opener", "attribute": "name", "value": "opener"},
                             {"entity": "obj:opener", "attribute": "in", "value": PLAYER}])
    spy = _Spy(world, monkeypatch)
    r = _turn(world, {"drops": "opener"}, "I set the opener down.",
              [PLAYER, "obj:opener", "place:study"])
    assert r.trace.dropped == "obj:opener"
    assert spy.mode("obj:opener", "in", "place:study") == "rules"


def test_move_with_a_carried_object_is_rules(world, monkeypatch):
    world.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:hall", "attribute": "name", "value": "hall"}])
    spy = _Spy(world, monkeypatch)
    _turn(world, {"moves_to": "the hall"}, "I walk to the hall.",
          [PLAYER, "place:study", "place:hall"])
    assert spy.mode(PLAYER, "in", "place:hall") == "rules"


def test_improv_grant_and_mint_are_rules_with_guardrails_kept(world, monkeypatch):
    spy = _Spy(world, monkeypatch)
    at = turn_time(3)
    got, _ = _grant_moved_place(world, PLAYER, "the lamplit square", at=at)
    assert got == "place:lamplit_square"
    assert spy.mode(PLAYER, "in", got) == "rules"
    assert spy.mode(got, "kind") == "rules"
    # 3. guardrails kept: structural kind and the name stay CONSTITUTIVE under rules
    assert _verdict(world, got, "kind") == "CONSTITUTIVE"
    assert _verdict(world, got, "name") == "CONSTITUTIVE"
    assert _verdict(world, PLAYER, "in") == "STATE"
    oid = _mint_held_object(world, PLAYER, "a brass key", at=turn_time(4))
    assert oid and spy.mode(oid, "in", PLAYER) == "rules"
    assert _verdict(world, oid, "in") == "STATE"


def test_pre_scene_placement_and_npc_follow_and_companionship_are_rules(world, monkeypatch):
    from tests.test_cast_moves import _seed_person
    world.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:hall", "attribute": "name", "value": "hall"}])
    _seed_person(world, "person:edda", "Edda", "place:study")
    spy = _Spy(world, monkeypatch)
    _turn(world, {"moves_to": "the hall", "moved_with": ["npc_0"], "joins": ["npc_0"]},
          "Edda, come with me to the hall.", [PLAYER, "place:study", "place:hall",
                                              "person:edda"])
    modes = {m for rows, m in spy.calls for r in rows
             if r.get("entity") == "person:edda" and r.get("attribute") in
             ("in", "accompanying")}
    assert modes and modes <= {"rules"}


def test_dismissal_is_rules(world, monkeypatch):
    from tests.test_cast_moves import _seed_person
    _seed_person(world, "person:edda", "Edda", "place:study")
    world.ingest_structured([{"entity": "person:edda", "attribute": "accompanying",
                              "value": PLAYER, "value_type": "entity"}])
    spy = _Spy(world, monkeypatch)
    _turn(world, {"npcs_dismissed": ["npc_0"]}, "Leave me, Edda.",
          [PLAYER, "place:study", "person:edda"])
    dep = [m for rows, m in spy.calls for r in rows
           if str(r.get("entity", "")).startswith("event:departed")
           or (r.get("entity") == "person:edda" and r.get("attribute") == "accompanying")]
    assert dep and set(dep) == {"rules"}


def test_build_stages_are_rules(world, monkeypatch):
    world.ingest_structured([
        {"entity": "place:yard", "attribute": "kind", "value": "yard", "timeless": True},
        {"entity": "person:ana", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:ana", "attribute": "name", "value": "Ana"}])
    spy = _Spy(world, monkeypatch)
    game._stage_ensure_located_people(world, ["person:ana", "place:yard"], "", [])
    assert spy.mode("person:ana", "in") == "rules"
    arc = make_arc()
    seed_arc(world, arc)
    game._stage_ground_play_as_figure(world, arc, [PLAYER, "place:yard"], "player", [])
    assert spy.mode(PLAYER, "in") == "rules"      # "player" matches person:player: it stages
    game._stage_cast_in_place(world, arc, (CastNode("person:ana", presence="at_scene"),),
                              None)
    staged = [m for rows, m in spy.calls for r in rows
              if r.get("attribute") == "in" and r.get("entity") in ("person:ana", PLAYER)]
    assert staged and set(staged) == {"rules"}


def test_player_extraction_stays_batch(world, monkeypatch):
    """Control: the player's own claims still go to the model."""
    spy = _Spy(world, monkeypatch)
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([
        {"items": [{"entity": "obj:plank", "attribute": "kind", "value": "plank"}]},
        {"items": []}])
    run_turn(world, arc, StubProvider([{**_BASE, "asserts_or_reveals": True},
                                       {"prose": "Done."}]),
             "I bar the door with a plank.", turn=2, scope=[PLAYER, "place:study"])
    assert spy.mode("obj:plank", "kind") == "batch"


# ------------------------------------------------------------- 4. no flicker

def test_take_then_drop_elsewhere_never_snaps_back(world):
    world.ingest_structured([
        {"entity": "obj:spoon", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:spoon", "attribute": "in", "value": "place:study"},
        {"entity": "obj:spoon", "attribute": "name", "value": "brass spoon"},
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:hall", "attribute": "name", "value": "hall"}])
    arc = make_arc()
    seed_arc(world, arc)
    scope = ["obj:spoon", PLAYER, "place:study", "place:hall"]
    for turn, verdict, text in ((2, {"takes": "the brass spoon"}, "I take the spoon."),
                                (3, {"moves_to": "the hall"}, "I walk to the hall."),
                                (4, {"drops": "brass spoon"}, "I set the spoon down.")):
        world._extractions.extend([{"items": []}, {"items": []}])
        run_turn(world, arc, StubProvider([{**_BASE, **verdict}, {"prose": "…"}]), text,
                 turn=turn, scope=scope)
    assert world.porcelain.locate("obj:spoon")[0] == "place:hall"
    assert PorcelainWorldReads(world).location_chain("obj:spoon")[0] == "place:hall"


def test_pre_scene_object_placement_is_rules(world, monkeypatch):
    """The step to an unlocated table within the scene places the table: a host placement."""
    from tests.test_move_to_unplaced_object import _ingest, _obj, _turn as _mturn
    _ingest(world, _obj("obj:table", "the table"))
    spy = _Spy(world, monkeypatch)
    _mturn(world, "I step to the table.", "the table", within=True)
    assert spy.mode("obj:table", "in", "place:study") == "rules"
