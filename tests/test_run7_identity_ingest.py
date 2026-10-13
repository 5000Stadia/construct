"""R20 run 7's two build/turn defects (eval/12 run 7; pattern-buffer's diagnosis, mbaab95).

1. The reconcile's homonym pass held the hero apart from their own fragment: it read
   extraction's role words in `kind` ("condemned man" beside "person") as two kinds.
   The reconcile now holds apart only pairs in two id NAMESPACES (person:harth /
   place:harth). A same-namespace pair whose kinds differ could be role noise or two
   people sharing a name, and nothing tells them apart (cr RED on 381b3de), so the
   identity confirm never merges one: touching a load-bearing id it stops the build,
   otherwise it is held apart as before.
2. An `attr:*` declaration item in a turn's batch, after the attribute holds data, made
   the engine refuse the whole batch. The turn's ingest wrapper drops such items."""

from types import SimpleNamespace

import pytest

from construct import game, turnloop
from construct.game import IdentityUnresolvedError


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


def test_reconcile_leaves_same_namespace_pairs_to_the_confirm():
    # stage 2 only: the person/person pair is decided later (see the real-engine tests)
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
    assert trace.dropped_declarations == ["attr:keeps · arity"]
    assert "attr:keeps" in caplog.text
    held = {f["value"] for f in keeps_world.porcelain.facts("canon")
            if f["entity"] == "person:quill" and f["attribute"] == "keeps"}
    assert held == {"obj:ink", "obj:knife"}


def test_wrapper_filters_items_passed_by_keyword(keeps_world):
    p = turnloop._FailOpenIngest(keeps_world.porcelain, turnloop.TurnTrace(turn=1))
    receipt = p.ingest_structured(items=[dict(_DECLARATION), _knife()], frame="canon",
                                  classify="rules")
    assert len(turnloop._receipt_rows(receipt)) == 1


# ---- 1b. same name, one namespace, different kinds: through reconcile AND confirm, real engine

def _named_world(tmp_path, people):
    w = game._world(tmp_path / "n.world", "n", model=None)
    rows = []
    for entity, kind, aliases in people:
        rows.append({"entity": entity, "attribute": "kind", "value": kind})
        rows += [{"entity": entity, "attribute": "alias", "value": a} for a in aliases]
    w.porcelain.ingest_structured(rows, frame="canon", classify="rules")
    game._stage_reconcile_identity(w, None)
    return w


_LYSAS = [("person:lysa", "laundress", ["lysa", "the laundress"]),
          ("person:lysa_fen", "clerk", ["lysa fen", "lysa"]),
          ("person:hero", "person", ["hero"])]
# R20 run 7, as the engine saw it: one person, role words in kind
_ELIAS = [("person:elias", "condemned man", ["elias", "venn"]),
          ("person:elias_venn", "person", ["elias venn", "venn"])]


def _arc(protagonist):
    return SimpleNamespace(arc_id="arc:main", protagonist=protagonist)


def test_two_people_sharing_a_name_stay_distinct(tmp_path):
    w = _named_world(tmp_path, _LYSAS)
    assert not w.porcelain.distinct_between("person:lysa", "person:lysa_fen")  # live after stage 2
    game._stage_confirm_identity(w, _arc("person:hero"), set())               # not load-bearing
    assert w.porcelain.distinct_between("person:lysa", "person:lysa_fen")
    assert set(w.porcelain.closure("person:lysa")) == {"person:lysa"}


def test_a_load_bearing_same_name_pair_stops_the_build_and_is_never_merged(tmp_path):
    w = _named_world(tmp_path, _LYSAS)
    with pytest.raises(IdentityUnresolvedError, match="kinds differ"):
        game._stage_confirm_identity(w, _arc("person:lysa_fen"), set())
    assert set(w.porcelain.closure("person:lysa_fen")) == {"person:lysa_fen"}


def test_run7_hero_fragment_stops_instead_of_splitting(tmp_path):
    w = _named_world(tmp_path, _ELIAS)
    with pytest.raises(IdentityUnresolvedError) as err:
        game._stage_confirm_identity(w, _arc("person:elias_venn"), set())
    assert {frozenset(p[:2]) for p in err.value.pairs} == {
        frozenset(("person:elias", "person:elias_venn"))}
    # neither held apart (the run 7 split) nor merged on no evidence
    assert not w.porcelain.distinct_between("person:elias", "person:elias_venn")
    assert set(w.porcelain.closure("person:elias_venn")) == {"person:elias_venn"}


def test_a_required_holder_counts_as_load_bearing(tmp_path):
    w = _named_world(tmp_path, _LYSAS)
    with pytest.raises(IdentityUnresolvedError):
        game._stage_confirm_identity(w, _arc("person:hero"), {"person:lysa"})


# 3. A question is not a fact (R20 run 7, finding 4): the turn-4 line mixed a statement with
#    "Quill, who keeps the wash tally ink and knife?", and the player-input ingest wrote
#    `Quill keeps obj:wash_tally_ink` / `obj:knife` to canon. Only statements are extracted.

_RUN7_T4 = ("I nod at the key still hanging useless in Quill’s hand. “Leave chapel dangling; "
            "the wet scrape is the road. Quill, who keeps the wash tally ink and knife, and who "
            "had the ledger open between the hymn and the moment Dena brought it here?”")


def test_the_run7_question_is_not_extracted():
    kept = turnloop._declarative_part(_RUN7_T4)
    assert "who keeps" not in kept
    assert kept.startswith("I nod at the key") and "the wet scrape is the road." in kept


@pytest.mark.parametrize("line,expected", [
    ("Who did it?", ""),
    ("Is it locked? I try the handle.", "I try the handle."),
    ("I open the drawer and take the letter", "I open the drawer and take the letter"),
    ("I say, “Wait here.” Then I go.", "I say, “Wait here.” Then I go."),
    ("“Where were you?” I ask her.", "I ask her."),
])
def test_declarative_part(line, expected):
    assert turnloop._declarative_part(line) == expected
