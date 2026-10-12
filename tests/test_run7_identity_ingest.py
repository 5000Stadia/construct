"""R20 run 7's two build/turn defects (eval/12 run 7; pattern-buffer's diagnosis, mbaab95).

1. The reconcile's homonym pass held the hero apart from their own fragment: it read
   extraction's role words in `kind` ("condemned man" beside "person") as two kinds.
   A homonym is now two id NAMESPACES (person:harth / place:harth), never two kind strings.
2. An `attr:*` declaration item in a turn's batch, after the attribute holds data, made
   the engine refuse the whole batch. The turn's ingest wrapper drops such items."""

from types import SimpleNamespace

import pytest

from construct import game, turnloop


class _Porcelain:
    def __init__(self, collisions):
        self._collisions = collisions
        self.rejected: list[tuple[str, str]] = []

    def reconcile(self):
        return {}

    def adjudicate_deferred(self):
        return {}

    def typing_conflicts(self):
        return []

    def fidelity_audit(self):
        return {"name_collisions": self._collisions}

    def reject(self, a, b):
        self.rejected.append((a, b))
        return {"outcome": "rejected"}


def _reconcile(collisions):
    p = _Porcelain(collisions)
    game._stage_reconcile_identity(SimpleNamespace(porcelain=p), None)
    return p.rejected


def test_same_namespace_role_kinds_are_not_homonyms():
    # run 7: anchor 'venn' -> the hero's fragment and the arc's id, kinds differ only by role words
    assert _reconcile([{"anchor": "venn", "live": True,
                        "entities": ["person:elias", "person:elias_venn"],
                        "kinds": ["condemned man/person", "person"]}]) == []


def test_cross_namespace_pair_is_still_a_homonym():
    assert _reconcile([{"anchor": "harth", "live": True,
                        "entities": ["person:harth", "place:harth"],
                        "kinds": ["person", "village"]}]) == [("person:harth", "place:harth")]


def test_mixed_group_rejects_only_the_cross_namespace_pairs():
    rejected = _reconcile([{"anchor": "quill", "live": True,
                            "entities": ["person:quill", "person:warrant_clerk_quill", "obj:quill"],
                            "kinds": ["clerk/person", "warrant clerk", "pen"]}])
    assert sorted(rejected) == [("person:quill", "obj:quill"),
                                ("person:warrant_clerk_quill", "obj:quill")]


def test_dead_group_is_left_alone():
    assert _reconcile([{"anchor": "harth", "live": False,
                        "entities": ["person:harth", "place:harth"],
                        "kinds": ["person", "village"]}]) == []


# ---- 2. the turn's ingest wrapper, on the real engine --------------------------------

_DECLARATION = {"entity": "attr:keeps", "attribute": "arity", "value": "set_valued"}


@pytest.fixture
def keeps_world(tmp_path):
    w = game._world(tmp_path / "w.world", "w", model=None)
    w.porcelain.ingest_structured([{"entity": "person:quill", "attribute": "keeps",
                                    "value": "obj:ink", "value_type": "entity"}],
                                  frame="canon", classify="rules")
    return w


def _knife():
    return {"entity": "person:quill", "attribute": "keeps", "value": "obj:knife",
            "value_type": "entity"}


def test_engine_refuses_a_batch_carrying_a_late_declaration(keeps_world):
    # negative control: the failure the wrapper exists for
    with pytest.raises(ValueError, match="after folded data already exists"):
        keeps_world.porcelain.ingest_structured([dict(_DECLARATION), _knife()],
                                                frame="canon", classify="rules")


def test_wrapper_drops_the_declaration_and_keeps_the_batch(keeps_world, caplog):
    trace = turnloop.TurnTrace(turn=1)
    p = turnloop._FailOpenIngest(keeps_world.porcelain, trace)
    receipt = p.ingest_structured([dict(_DECLARATION), _knife()], frame="canon",
                                  classify="rules")
    assert [r["attribute"] for r in turnloop._receipt_rows(receipt)] == ["keeps"]
    assert trace.dropped_cohorts == []
    assert "attr:keeps" in caplog.text
    held = {f["value"] for f in keeps_world.porcelain.facts("canon")
            if f["entity"] == "person:quill" and f["attribute"] == "keeps"}
    assert held == {"obj:ink", "obj:knife"}


def test_wrapper_filters_items_passed_by_keyword(keeps_world):
    p = turnloop._FailOpenIngest(keeps_world.porcelain, turnloop.TurnTrace(turn=1))
    receipt = p.ingest_structured(items=[dict(_DECLARATION), _knife()], frame="canon",
                                  classify="rules")
    assert len(turnloop._receipt_rows(receipt)) == 1
