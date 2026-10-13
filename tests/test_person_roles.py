"""PERSON-ROLES-V1 (pattern-buffer R49) as construct reads it.

A person's kind is always "person"; what they are at a time is a dated, set-valued
`role`. The engine's ingest gate moves a person's non-person kind ("corpse", "condemned
man") into role. Construct reads every role in force, not only the fold's winner."""

from types import SimpleNamespace

from construct import game
from construct.adapter import state_value, state_values
from construct.session import Session

HERO = "person:hero"


def _ingest(w, rows):
    w.porcelain.ingest_structured(
        [dict(zip(("entity", "attribute", "value"), r[:3]), **(r[3] if len(r) > 3 else {}))
         for r in rows],
        frame="canon", classify="rules")


def _world(tmp_path):
    return game._world(tmp_path / "r.world", "r", model=None)


def test_roles_in_force_at_a_time(tmp_path):
    w = _world(tmp_path)
    _ingest(w, [
        ("person:tomas", "name", "Tomas Breck"),
        ("person:tomas", "role", "prisoner", {"valid_from": 1.0, "valid_to": 5.0}),
        ("person:tomas", "role", "father", {"valid_from": 2.0}),
        ("person:tomas", "role", "hero", {"valid_from": 7.0}),
    ])
    p = w.porcelain
    assert state_values(p, "person:tomas", "role", as_of=0.5) == []
    assert sorted(state_values(p, "person:tomas", "role", as_of=3.0)) == ["father", "prisoner"]
    assert state_values(p, "person:tomas", "role", as_of=6.0) == ["father"]
    assert sorted(state_values(p, "person:tomas", "role", as_of=8.0)) == ["father", "hero"]
    # the winner alone is the newest member
    assert state_value(p, "person:tomas", "role", as_of=8.0) == "hero"


def test_state_values_on_a_one_valued_key_and_an_unknown_entity(tmp_path):
    w = _world(tmp_path)
    _ingest(w, [("person:tomas", "name", "Tomas Breck"),
                ("person:tomas", "background", "a clerk of the warrant room")])
    p = w.porcelain
    assert state_values(p, "person:tomas", "background") == ["a clerk of the warrant room"]
    assert state_values(p, "person:nobody", "role") == []


def test_a_person_kind_becomes_a_role(tmp_path):
    w = _world(tmp_path)
    _ingest(w, [("person:tomas", "name", "Tomas Breck"),
                ("person:tomas", "kind", "condemned man", {"valid_from": 1.0})])
    p = w.porcelain
    assert state_value(p, "person:tomas", "kind") == "person"
    assert state_values(p, "person:tomas", "role", as_of=2.0) == ["condemned man"]


def _contents(w, scope):
    host = SimpleNamespace(_world=w, _arc=SimpleNamespace(protagonist=HERO),
                           _horizon=lambda: None, _scope=scope)
    return Session._scene_contents(host, "place:cell")


def test_a_corpse_kind_still_reaches_the_image_as_a_body(tmp_path):
    """The kind arrives as a role; an older role that still holds is read too,
    not just the newest one the fold serves."""
    w = _world(tmp_path)
    _ingest(w, [
        ("place:cell", "name", "the cell"),
        (HERO, "in", "place:cell"),
        ("person:vale", "name", "Father Vale"),
        ("person:vale", "in", "place:cell"),
        ("person:vale", "kind", "corpse"),
        ("person:vale", "role", "priest", {"valid_from": 1.0}),
        ("person:nessa", "name", "Nessa Reed"),
        ("person:nessa", "in", "place:cell"),
        ("person:nessa", "kind", "smuggler"),
    ])
    assert state_value(w.porcelain, "person:vale", "role") == "priest"
    out = _contents(w, ["person:vale", "person:nessa"])
    assert "the body of Father Vale" in out
    assert "Nessa" not in out  # the living stay theatre of the mind
