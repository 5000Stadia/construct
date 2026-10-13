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


def gate(*verdicts, calls=None, mutate=None, **overrides):
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
        if mutate is not None:
            mutate(report)
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


def _set_entry(**fields):
    return lambda report: report["pairs"][0].update(fields)


@pytest.mark.parametrize("label,kwargs", [
    ("pairs [None]", {"pairs": [None]}),
    ("components [None]", {"components": [None]}),
    ("not_asked not a list", {"not_asked": "none"}),
    ("requested_as a string", {"mutate": _set_entry(requested_as=["0"])}),
    ("requested_as a bool", {"mutate": _set_entry(requested_as=[True])}),
    ("requested_as out of range", {"mutate": _set_entry(requested_as=[5])}),
    ("requested_as not a list", {"mutate": _set_entry(requested_as=0)}),
    ("wrong pair ids", {"mutate": _set_entry(a="person:x", b="person:y")}),
    ("unknown verdict", {"mutate": _set_entry(verdict="maybe")}),
    ("reason not a string", {"mutate": _set_entry(reason=None)}),
    ("component members not strings", {"components": [{"members": [1], "status": "x"}]}),
])
def test_a_malformed_report_fails_closed(w, monkeypatch, label, kwargs):
    # cr on 4951dc4: never an escaping exception; nothing written; the normal identity stop
    monkeypatch.setattr(w.porcelain, "merge_gate", gate("same", "same", **kwargs),
                        raising=False)
    _adjudicate(w)
    assert game._closure(w, KEEP) == {KEEP} and not game._held_apart(w, KEEP, FRAG)
    _stops(w)


# ---- the real engine verb (pattern-buffer R48, MERGE-GATE-VERB-V1) -------------------------
# Skipped on an engine pinned before R48. Only the MODEL is stubbed: the verb builds the
# request, validates the model's batch, elects components and writes the report itself.

def _verb_world(tmp_path, verdict):
    from patternbuffer.porcelain import Porcelain
    if not hasattr(Porcelain, "merge_gate"):
        pytest.skip("the pinned engine has no merge_gate verb (before pattern-buffer R48)")
    from patternbuffer.merge_gate import batch_request
    asked = []

    def model(prompt, schema):
        request = batch_request(schema)
        if request is None:
            return {"items": []}
        asked.append(request)
        return {"verdicts": [{"pair_id": p["pair_id"], "verdict": verdict, "keep": "a",
                              "reason": f"the source names one clerk ({verdict})"}
                             for p in request["pairs"]]}
    w = game._world(tmp_path / "v.world", "v", model=model)
    w.porcelain.ingest_structured(
        _person(HERO, "Hero") + _person(KEEP, "Tomas Breck", ["breck"])
        + _person(FRAG, aliases=["breck"]), frame="canon", classify="rules")
    w.porcelain.reconcile()
    return w, asked


def test_the_real_verb_two_same_answers_merge(tmp_path):
    w, asked = _verb_world(tmp_path, "same")
    try:
        _adjudicate(w)
        assert len(asked) == 2                                    # two fresh askings
        assert asked[0]["pairs"][0]["a"]["context"]               # the source reached the model
        assert game._closure(w, KEEP) == {KEEP, FRAG}
        game._stage_confirm_identity(w, _arc(), {KEEP})
    finally:
        w.close()


def test_the_real_verb_two_different_answers_hold_apart(tmp_path):
    w, _asked = _verb_world(tmp_path, "different")
    try:
        _adjudicate(w)
        assert game._held_apart(w, KEEP, FRAG) and game._closure(w, KEEP) == {KEEP}
    finally:
        w.close()


def test_the_real_verb_unsure_leaves_the_stop(tmp_path):
    w, _asked = _verb_world(tmp_path, "unsure")
    try:
        _adjudicate(w)
        assert game._closure(w, KEEP) == {KEEP}
        _stops(w)
    finally:
        w.close()
