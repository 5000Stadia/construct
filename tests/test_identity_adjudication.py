"""IDENTITY-CONFIRM role-noise adjudication (spec r6, cr GREEN; R20 run 8).

The evidence-free vouch is replaced in its slot: a same-kind alias_not_specific pair with
exactly one load-bearing id is merged only on two fresh `same` answers from pattern-buffer's
merge gate (MERGE-GATE-VERB-V1), asked on one frozen, source-backed request; held apart only
on two `different`s with a checked receipt; anything else is left for the identity stop.

The gate here is a stub of the verb's report contract; the world, its audit, closures,
merges and rejects are the real engine."""

import itertools
from types import SimpleNamespace

import pytest

from construct import game

HERO, KEEP, FRAG = "person:hero", "person:tomas_breck", "person:breck"
SOURCE = ("Tomas Breck kept the wash tally. The bell rang twice. Breck locked the ledger "
          "cupboard. Breck said nothing more.")
_ids = itertools.count(1)


def _person(entity, name=None, aliases=()):
    rows = [{"entity": entity, "attribute": "kind", "value": "person"}]
    if name:
        rows.append({"entity": entity, "attribute": "name", "value": name})
    rows += [{"entity": entity, "attribute": "alias", "value": a} for a in aliases]
    return rows


@pytest.fixture
def w(tmp_path):
    w = game._world(tmp_path / "a.world", "a", model=None)
    w.porcelain.ingest_structured(
        _person(HERO, "Hero") + _person(KEEP, "Tomas Breck", ["breck"])
        + _person(FRAG, aliases=["breck"]), frame="canon", classify="rules")
    w.porcelain.reconcile()
    yield w
    w.close()


def _arc():
    return SimpleNamespace(arc_id="arc:main", protagonist=HERO)


def gate(*verdicts, calls=None, **overrides):
    """A merge_gate stub: one report per call, verdicts taken in call order (one per
    requested pair, or a single verdict for all). `overrides` patch the report."""
    answers = list(verdicts)

    def _gate(pairs, *, context=None, batch_size=25):
        verdict = answers.pop(0)
        if calls is not None:
            calls.append({"pairs": pairs, "context": context})
        entries = [{"pair_id": f"p{i + 1:04d}", "a": a, "b": b, "verdict": verdict,
                    "keep": "a", "reason": f"reason {verdict}", "status": "answered",
                    "requested_as": [i]} for i, (a, b) in enumerate(pairs)]
        report = {"gate": "merge_gate", "status": "asked", "call_id": f"{next(_ids):032x}",
                  "cached": False, "requested": [list(p) for p in pairs], "pairs": entries,
                  "not_asked": [], "components": [
                      {"members": [e["a"], e["b"]], "status": "would_merge"}
                      for e in entries if verdict == "same"]}
        report.update(overrides)
        return report
    return _gate


def _adjudicate(w, holders=(KEEP,), source=SOURCE):
    game._stage_adjudicate_identity(w, _arc(), set(holders), source)


def _stops(w, holders=(KEEP,)):
    with pytest.raises(game.IdentityUnresolvedError):
        game._stage_confirm_identity(w, _arc(), set(holders))


def test_the_engine_reads_this_pair_as_the_vouch_residue(w):
    # the witness: same kind, one load-bearing id, auto_declined / alias_not_specific
    assert game._fidelity_vouched_pairs(
        w.porcelain.fidelity_audit()["name_collisions"], {HERO, KEEP}) == [(KEEP, FRAG)]


def test_two_same_answers_merge_into_the_load_bearing_id(w, monkeypatch):
    calls = []
    monkeypatch.setattr(w.porcelain, "merge_gate", gate("same", "same", calls=calls),
                        raising=False)
    merges = []
    real_merge = w.porcelain.merge
    monkeypatch.setattr(w.porcelain, "merge",
                        lambda a, b, **k: (merges.append((a, b, k)), real_merge(a, b, **k))[1])
    _adjudicate(w)
    assert len(calls) == 2 and calls[0] == calls[1]               # one frozen request, twice
    assert game._closure(w, KEEP) == {KEEP, FRAG}
    (a, b, kw), = merges
    assert (a, b) == (KEEP, FRAG) and kw["representative"] == KEEP
    assert kw["evidence"].startswith("merge gate x2 ")
    game._stage_confirm_identity(w, _arc(), {KEEP})               # decided: no stop


def test_the_context_is_source_backed_capped_and_names_only_the_pair(w, monkeypatch):
    calls = []
    monkeypatch.setattr(w.porcelain, "merge_gate", gate("unsure", "unsure", calls=calls),
                        raising=False)
    _adjudicate(w, source=SOURCE + " " + "Breck waited. " * 5)
    ctx = calls[0]["context"]
    assert set(ctx) == {KEEP, FRAG}
    assert all(len(v) <= 2 and all(len(x) <= 400 for x in v) for v in ctx.values())
    assert ctx[KEEP][0] == "Tomas Breck kept the wash tally."
    assert not any("bell rang" in x for v in ctx.values() for x in v)


@pytest.mark.parametrize("first,second", [("same", "unsure"), ("same", "different"),
                                          ("unsure", "unsure"), ("different", "same")])
def test_anything_but_two_agreeing_answers_writes_nothing_and_stops(w, monkeypatch,
                                                                     first, second):
    monkeypatch.setattr(w.porcelain, "merge_gate", gate(first, second), raising=False)
    _adjudicate(w)
    assert game._closure(w, KEEP) == {KEEP} and not game._held_apart(w, KEEP, FRAG)
    _stops(w)


def test_two_different_answers_hold_the_pair_apart(w, monkeypatch):
    monkeypatch.setattr(w.porcelain, "merge_gate", gate("different", "different"),
                        raising=False)
    _adjudicate(w)
    assert game._held_apart(w, KEEP, FRAG) and game._closure(w, KEEP) == {KEEP}
    game._stage_confirm_identity(w, _arc(), {KEEP})               # decided: no stop


def test_a_bad_reject_receipt_is_not_counted(w, monkeypatch):
    monkeypatch.setattr(w.porcelain, "merge_gate", gate("different", "different"),
                        raising=False)
    monkeypatch.setattr(w.porcelain, "reject", lambda a, b: {"outcome": "vetoed"})
    _adjudicate(w)
    _stops(w)


def test_a_same_inside_a_conflicting_component_is_not_a_merge(w, monkeypatch):
    conflicting = [{"members": [FRAG, KEEP], "status": "conflicting_component"}]
    monkeypatch.setattr(w.porcelain, "merge_gate",
                        gate("same", "same", components=conflicting), raising=False)
    _adjudicate(w)
    assert game._closure(w, KEEP) == {KEEP}
    _stops(w)


@pytest.mark.parametrize("override", [
    {"cached": True},
    {"call_id": ""},
    {"requested": [["person:x", "person:y"]]},
    {"pairs": []},                                                # coverage missing
])
def test_a_report_that_does_not_answer_the_request_is_void(w, monkeypatch, override):
    monkeypatch.setattr(w.porcelain, "merge_gate", gate("same", "same", **override),
                        raising=False)
    _adjudicate(w)
    assert game._closure(w, KEEP) == {KEEP}
    _stops(w)


def test_a_reused_answer_is_rejected(w, monkeypatch):
    monkeypatch.setattr(w.porcelain, "merge_gate",
                        gate("same", "same", call_id="ab" * 16), raising=False)
    _adjudicate(w)
    assert game._closure(w, KEEP) == {KEEP}


def test_a_raising_gate_writes_nothing(w, monkeypatch):
    def _boom(pairs, **k):
        raise RuntimeError("model down")
    monkeypatch.setattr(w.porcelain, "merge_gate", _boom, raising=False)
    _adjudicate(w)
    _stops(w)


def test_no_verb_no_source_or_two_load_bearing_ids_never_ask(w, monkeypatch):
    calls = []
    monkeypatch.setattr(w.porcelain, "merge_gate", gate("same", "same", calls=calls),
                        raising=False)
    _adjudicate(w, source="")                                     # interview path: no source
    _adjudicate(w, holders=(KEEP, FRAG))                          # two load-bearing ids
    assert calls == [] and game._closure(w, KEEP) == {KEEP}
    monkeypatch.delattr(w.porcelain, "merge_gate")
    _adjudicate(w)                                                # an engine without the verb
    _stops(w)


def test_a_pair_that_changes_between_asking_and_writing_is_left_open(w, monkeypatch):
    real = gate("different", "different")

    def _gate(pairs, **k):
        report = real(pairs, **k)
        if not hasattr(_gate, "asked"):
            _gate.asked = True
        else:
            w.porcelain.reject(KEEP, FRAG)                        # someone decided meanwhile
        return report
    monkeypatch.setattr(w.porcelain, "merge_gate", _gate, raising=False)
    rejects = []
    real_reject = w.porcelain.reject
    monkeypatch.setattr(w.porcelain, "reject",
                        lambda a, b: (rejects.append((a, b)), real_reject(a, b))[1])
    _adjudicate(w)
    assert rejects == [(KEEP, FRAG)]                              # only the outside one


def test_the_build_no_longer_has_an_evidence_free_vouch():
    assert not hasattr(game, "_stage_vouch_merges")
