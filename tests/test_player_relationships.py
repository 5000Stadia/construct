"""Build-side player↔cast relationship authoring (task #75, OPENING-GROUNDING).

`game.seed_player_relationships` writes the player's STANDING relationship to each PERSON
cast member into `knows:<protagonist>` as `relationship_to_<id>` facts, which the grounded
cold open (`Session._player_grounding`) consumes. These tests cover the wiring deterministically
with a stub provider (no live model)."""
from __future__ import annotations

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import PorcelainWorldReads
from construct.cast import cast_from_proposal
from construct.game import seed_player_relationships
from construct.provider import StubProvider, task_of

PLAYER = "person:player"


class _RelProvider(StubProvider):
    """Returns a canned relationship roster for the 'rel' cohort; one entry brushes a
    concealed token to exercise screening downstream."""

    def __init__(self, rels):
        super().__init__([])
        self._rels = rels

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if task_of(prompt) == "rel":
            return {"relationships": self._rels}
        return {"items": []}


def _world(tmp_path):
    rule = rule_classifier_fallback()

    def fb(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    w = World(tmp_path / "rel.world", world_id="w:rel", stance="fiction",
              model=StubModel(fallback=fb))
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "role", "value": "a bureau detective"},
        {"entity": "person:reed", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:vale", "attribute": "kind", "value": "person", "timeless": True},
    ])
    return w


def _cast():
    proposal = {"pillars": [], "cast": [
        {"id": "person:reed", "shape_role": "ally", "surface_role": "your partner", "clues": []},
        {"id": "person:vale", "shape_role": "witness", "surface_role": "a witness", "clues": []},
    ]}
    nodes, _ = cast_from_proposal(proposal)
    return nodes


def test_relationships_land_in_player_frame(tmp_path):
    w = _world(tmp_path)
    prov = _RelProvider([
        {"target": "person:reed", "relationship": "your newly assigned partner on the case"},
        {"target": "person:vale", "relationship": "a dockside witness you've been sent to question"},
    ])
    n = seed_player_relationships(w, prov, PLAYER, _cast(), digest="a world")
    assert n == 2
    reads = PorcelainWorldReads(w)
    assert reads.state(PLAYER, "relationship_to_person:reed", frame=f"knows:{PLAYER}") == \
        "your newly assigned partner on the case"
    assert reads.state(PLAYER, "relationship_to_person:vale", frame=f"knows:{PLAYER}") == \
        "a dockside witness you've been sent to question"
    w.close()


def test_unknown_or_out_of_roster_targets_are_dropped(tmp_path):
    w = _world(tmp_path)
    prov = _RelProvider([
        {"target": "person:reed", "relationship": "your partner"},
        {"target": "person:ghost", "relationship": "someone not in the cast"},  # not in roster
        {"target": "", "relationship": "no target"},                            # malformed
        {"target": "person:vale", "relationship": ""},                          # empty phrase
    ])
    n = seed_player_relationships(w, prov, PLAYER, _cast(), digest="a world")
    assert n == 1                                                # only the valid in-roster row
    reads = PorcelainWorldReads(w)
    assert reads.state(PLAYER, "relationship_to_person:ghost", frame=f"knows:{PLAYER}") is None
    w.close()


def test_protected_relationship_key_is_screened(tmp_path):
    w = _world(tmp_path)
    prov = _RelProvider([
        {"target": "person:reed", "relationship": "your partner"},
        {"target": "person:vale", "relationship": "a witness"},
    ])
    # defensively protect the relationship key to person:vale — it must not be written
    protected = {(PLAYER, "relationship_to_person:vale")}
    n = seed_player_relationships(w, prov, PLAYER, _cast(), digest="a world", protected=protected)
    assert n == 1
    reads = PorcelainWorldReads(w)
    assert reads.state(PLAYER, "relationship_to_person:reed", frame=f"knows:{PLAYER}") == "your partner"
    assert reads.state(PLAYER, "relationship_to_person:vale", frame=f"knows:{PLAYER}") is None
    w.close()


def test_leaky_relationship_value_is_screened_at_build(tmp_path):
    # Cx 337: a relationship value brushing the arc's concealed vocabulary must NOT be
    # persisted into knows:<prot> (defense in depth, not only at render). The protected key
    # (fact:secret, culprit) yields concealed tokens {secret, culprit}; a phrase naming the
    # culprit is dropped before storage.
    w = _world(tmp_path)
    prov = _RelProvider([
        {"target": "person:reed", "relationship": "your partner"},
        {"target": "person:vale", "relationship": "the culprit behind the dock killings"},
    ])
    protected = {("fact:secret", "culprit")}
    n = seed_player_relationships(w, prov, PLAYER, _cast(), digest="x", protected=protected)
    assert n == 1                                                  # only the clean value survives
    reads = PorcelainWorldReads(w)
    assert reads.state(PLAYER, "relationship_to_person:reed", frame=f"knows:{PLAYER}") == "your partner"
    assert reads.state(PLAYER, "relationship_to_person:vale", frame=f"knows:{PLAYER}") is None
    w.close()


def test_no_person_cast_writes_nothing(tmp_path):
    w = _world(tmp_path)
    prov = _RelProvider([])
    # roster with only the protagonist + a non-person holder → empty roster → no call, no rows
    proposal = {"pillars": [], "cast": [
        {"id": "obj:ledger", "shape_role": "evidence", "surface_role": "a ledger", "clues": []}]}
    nodes, _ = cast_from_proposal(proposal)
    assert seed_player_relationships(w, prov, PLAYER, nodes, digest="x") == 0
    assert not any(task_of(p) == "rel" for (p, _s, _t) in prov.calls)   # no wasted model call
    w.close()


def test_authoring_failure_is_fail_open(tmp_path):
    w = _world(tmp_path)

    class _Boom(StubProvider):
        def __init__(self):
            super().__init__([])

        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            raise RuntimeError("provider down")

    # a provider failure must not raise — the build proceeds with zero relationship rows
    assert seed_player_relationships(w, _Boom(), PLAYER, _cast(), digest="x") == 0
    w.close()
