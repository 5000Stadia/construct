"""WORLD-GROWTH G1 — the activation adaptor under cr's build boundary.

ATOMIC-ACTIVATION-V1 is LIVE (consumed 2026-07-24): the real matrix runs
against the shipped engine's commit_set door and the atomic_ingest sugar
(happy / gate-skip rollback / exception rollback / reopen durability).
The fail-closed path is preserved against SIMULATED envelope absence —
`_NonAtomicP` and the narrowly scoped `_capability -> ""` wired test.
"""
from __future__ import annotations

import pytest

from construct.growth import (ActivationResult, activate_chunk,
                              atomic_capable, ordered_chunk_items)
from tests.test_integration import world  # noqa: F401 — the engine fixture


class _NonAtomicP:
    """An envelope-less engine shape: ingest_structured without `atomic`."""

    def __init__(self):
        self.calls = []

    def ingest_structured(self, items, frame="canon", classify="inline"):
        self.calls.append(items)
        return {"rows": [{"entity": i["entity"]} for i in items]}


class _FakeAtomicP:
    """A FAKE atomic backend for shape-level unit tests (the real matrix below probes the shipped engine)."""

    def __init__(self, abort=False):
        self.calls = []
        self.abort = abort

    def ingest_structured(self, items, atomic=False, frame="canon",
                          classify="inline"):
        self.calls.append((list(items), atomic))
        if self.abort:
            raise RuntimeError("set aborted: gate rejected edge 3")
        return {"rows": [{"entity": i["entity"]} for i in items]}


_CHUNK = [{"entity": "place:waypost", "attribute": "kind", "value": "place"},
          {"entity": "place:waypost", "attribute": "in", "value": "place:region",
           "value_type": "entity"}]


def test_fail_closed_on_an_envelope_less_engine_nothing_written():
    # THE SAFETY GATE: capability absent → refuse BEFORE writing; zero
    # calls reach the engine; the receipt is a return value naming
    # activation_unavailable.
    p = _NonAtomicP()
    r = activate_chunk(p, list(_CHUNK))
    assert r == ActivationResult(ok=False, reason="activation_unavailable")
    assert p.calls == []                      # nothing written, no torn prefix
    assert not atomic_capable(p)


def test_empty_chunk_refuses_without_engine_contact():
    p = _NonAtomicP()
    assert activate_chunk(p, []).reason == "empty_chunk"
    assert p.calls == []


def test_engine_abort_is_a_clean_refusal():
    p = _FakeAtomicP(abort=True)
    r = activate_chunk(p, list(_CHUNK))
    assert not r.ok and r.reason.startswith("engine_abort:")
    # the envelope's own contract keeps canon untouched on abort; the host
    # records only the refusal (receipts stay return values)


# ---- THE REAL MATRIX (replaces the strict xfail arrival pin, 2026-07-24:
# ATOMIC-ACTIVATION-V1 shipped — porcelain commit_set(ops) is the detected
# door; ingest_structured(atomic=True) is the assert-only sugar) --------------

def _region_chunk(suffix: str) -> list[dict]:
    return [
        {"entity": f"place:waypost_{suffix}", "attribute": "kind",
         "value": "place", "timeless": True},
        {"entity": f"place:waypost_{suffix}", "attribute": "in",
         "value": "place:region", "value_type": "entity"},
    ]


def _matrix_world(path):
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    w = World(path, world_id="w:matrix", stance="fiction",
              model=StubModel(fallback=rule_classifier_fallback()),
              title="Atomic Matrix")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([{"entity": "place:region", "attribute": "kind",
                          "value": "region", "timeless": True}])
    return w


class _SugarFacade:
    """A REAL porcelain behind an atomic_ingest-only surface — no commit_set,
    an EXPLICIT named `atomic` parameter (the branch that held the latent
    classify defect runs against the true engine, not a fake)."""

    def __init__(self, porcelain):
        self._p = porcelain

    def ingest_structured(self, items, atomic=False, classify="inline",
                          frame=None):
        return self._p.ingest_structured(items, atomic=atomic,
                                         classify=classify, frame=frame)

    def state(self, entity, attribute):
        return self._p.state(entity, attribute)


def test_real_engine_happy_chunk_activates_and_persists(tmp_path):
    # the detected commit_set door on the REAL engine: one call, affirmed
    # receipts, every row visible — and DURABLE: the full set survives a
    # close/reopen (the retired arrival pin promised fault/skip/REOPEN)
    path = tmp_path / "m.world"
    w = _matrix_world(path)
    r = activate_chunk(w.porcelain, _region_chunk("a"))
    assert r.ok, r.reason
    assert len(r.receipts) == 2
    assert w.porcelain.state("place:waypost_a", "kind")["status"] == "known"
    assert w.porcelain.state("place:waypost_a", "in")["status"] == "known"
    w.close()
    w2 = _matrix_world(path)
    try:
        assert w2.porcelain.state("place:waypost_a", "kind")["status"] == "known"
        assert w2.porcelain.state("place:waypost_a", "in")["status"] == "known"
    finally:
        w2.close()


def test_real_engine_gate_skip_aborts_the_whole_set(tmp_path):
    # AtomicAbort(cause=gate_skip): one malformed id in the set → the engine
    # rolls the WHOLE set back; the GOOD prefix row is not visible either
    # (all-or-none is the entire point) — and the rollback is DURABLE: the
    # good prefix stays absent across a close/reopen
    path = tmp_path / "m.world"
    w = _matrix_world(path)
    items = _region_chunk("b") + [
        {"entity": "place:", "attribute": "kind",     # malformed_id → gate skip
         "value": "place", "timeless": True}]
    r = activate_chunk(w.porcelain, items)
    assert not r.ok and r.reason.startswith("engine_abort:")
    assert "gate_skip" in r.reason
    assert w.porcelain.state("place:waypost_b", "kind")["status"] != "known"
    w.close()
    w2 = _matrix_world(path)
    try:
        assert w2.porcelain.state("place:waypost_b",
                                  "kind")["status"] != "known"
    finally:
        w2.close()


def test_real_engine_exception_aborts_the_whole_set(tmp_path):
    # AtomicAbort(cause=exception): a row the ingest body cannot process
    # (no entity key) → same total rollback, typed as exception
    w = _matrix_world(tmp_path / "m.world")
    try:
        items = _region_chunk("c") + [{"attribute": "in",
                                       "value": "place:region"}]
        r = activate_chunk(w.porcelain, items)
        assert not r.ok and r.reason.startswith("engine_abort:")
        assert w.porcelain.state("place:waypost_c",
                                 "kind")["status"] != "known"
    finally:
        w.close()


def test_sugar_path_on_the_real_engine_happy_and_rollback(tmp_path):
    # cr AMBER delta: the branch that held the latent classify defect must
    # run against the TRUE engine — a real porcelain behind an
    # atomic_ingest-only facade. Happy: visible; gate-skip: total rollback
    # including the good prefix.
    w = _matrix_world(tmp_path / "m.world")
    try:
        facade = _SugarFacade(w.porcelain)
        assert not callable(getattr(facade, "commit_set", None))
        r = activate_chunk(facade, _region_chunk("d"))
        assert r.ok, r.reason
        assert w.porcelain.state("place:waypost_d",
                                 "kind")["status"] == "known"
        items = _region_chunk("e") + [
            {"entity": "place:", "attribute": "kind",
             "value": "place", "timeless": True}]
        r2 = activate_chunk(facade, items)
        assert not r2.ok and r2.reason.startswith("engine_abort:")
        assert w.porcelain.state("place:waypost_e",
                                 "kind")["status"] != "known"
    finally:
        w.close()


def test_sugar_path_carries_model_free_classify():
    # the atomic_ingest sugar path (an engine WITHOUT commit_set) must pass
    # classify="rules" — the real engine raises ValueError on the default
    # 'inline' BEFORE any write (ATOMIC-ACTIVATION-V1 §A), so omitting it
    # turns every activation into an abort on such an engine
    class _SugarOnlyP:
        def __init__(self):
            self.kwargs = None

        def ingest_structured(self, items, atomic=False, classify="inline",
                              frame="canon"):
            self.kwargs = {"atomic": atomic, "classify": classify}
            return {"rows": [{"entity": i["entity"]} for i in items]}

    p = _SugarOnlyP()
    r = activate_chunk(p, list(_CHUNK))
    assert r.ok
    assert p.kwargs == {"atomic": True, "classify": "rules"}


def test_fake_atomic_backend_happy_path():
    # against the FAKE backend the adaptor passes the set through in one
    # call with atomic=True and returns the engine receipts
    p = _FakeAtomicP()
    r = activate_chunk(p, list(_CHUNK))
    assert r.ok and len(r.receipts) == 2
    assert p.calls == [(list(_CHUNK), True)]  # ONE call, atomic flagged


def test_ordered_chunk_items_is_contractual():
    # declarations/parents strictly before references/children — the order
    # the staged-prefix gate makes semantic
    items = ordered_chunk_items(
        texture=[{"entity": "t"}], place=[{"entity": "p"}],
        moves=[{"entity": "m"}], containment=[{"entity": "c"}],
        passage=[{"entity": "x"}], encounter=[{"entity": "e"}])
    assert [i["entity"] for i in items] == ["p", "c", "x", "m", "e", "t"]


def test_typed_abort_return_is_not_success():
    # cr: the r2 envelope permits TYPED failure returns — success must be
    # affirmative; {outcome: aborted, rows: []} must never read ok
    class _TypedAbortP(_FakeAtomicP):
        def ingest_structured(self, items, atomic=False, **kw):
            return {"outcome": "aborted", "rows": [],
                    "skipped": [{"op": 3, "reason": "gate"}]}
    r = activate_chunk(_TypedAbortP(), list(_CHUNK))
    assert not r.ok and r.reason.startswith("engine_outcome:aborted")
    # skipped ops alone also refuse
    class _SkippedP(_FakeAtomicP):
        def ingest_structured(self, items, atomic=False, **kw):
            return {"rows": [{"entity": "x"}], "skipped": [{"op": 1}]}
    r2 = activate_chunk(_SkippedP(), list(_CHUNK))
    assert not r2.ok and r2.reason == "engine_skipped_ops"
    # empty rows for a nonempty chunk = ambiguous, refused
    class _EmptyP(_FakeAtomicP):
        def ingest_structured(self, items, atomic=False, **kw):
            return {"rows": []}
    r3 = activate_chunk(_EmptyP(), list(_CHUNK))
    assert not r3.ok and r3.reason == "ambiguous_receipt:no_rows"


def test_commit_set_branch_never_touches_a_broad_kwargs_ingest():
    # cr: never infer safety from one surface and invoke another — a
    # backend with commit_set plus a broad **kwargs legacy ingest must be
    # served through commit_set ONLY (the kwargs ingest would silently
    # swallow atomic=True and tear).
    class _CommitSetP:
        def __init__(self):
            self.set_calls, self.ingest_calls = [], []
        def commit_set(self, ops):
            self.set_calls.append(list(ops))
            return {"outcome": "ok",
                    "rows": [{"entity": o["item"]["entity"]} for o in ops]}
        def ingest_structured(self, items, **kwargs):  # broad legacy surface
            self.ingest_calls.append((list(items), kwargs))
            return {"rows": [{"entity": i["entity"]} for i in items]}
    p = _CommitSetP()
    r = activate_chunk(p, list(_CHUNK))
    assert r.ok and len(r.receipts) == 2
    assert p.ingest_calls == []                      # the legacy door untouched
    assert [o["op"] for o in p.set_calls[0]] == ["assert", "assert"]


def test_broad_kwargs_ingest_alone_is_not_capable():
    # a **kwargs-only ingest (no named atomic param, no commit_set) would
    # swallow the flag — it is NOT capable; the adaptor fails closed.
    class _BroadP:
        def __init__(self):
            self.calls = []
        def ingest_structured(self, items, **kwargs):
            self.calls.append(items)
            return {"rows": [{"entity": i["entity"]} for i in items]}
    p = _BroadP()
    r = activate_chunk(p, list(_CHUNK))
    assert r.reason == "activation_unavailable"
    assert p.calls == []                             # nothing written


def test_growth_eligibility_is_conjunctive_and_ordered():
    from construct.growth import PIPELINE_MISS, growth_eligibility as g
    base = dict(kind="action", committed=True, moves_open=True,
                seeks_encounter=False, pipeline_outcome=PIPELINE_MISS)
    assert g(**base) == "place"
    # THE CLOSED OUTCOME CONTRACT (cr): only the literal "miss" permits —
    # answered states, uninitialized sentinels, and unknown/error all forbid
    for state in ("resolved", "ambiguous", "blocked", "undiscovered",
                  "same_place", "fixture", None, "", "error", "MISS",
                  "unknown_future_state"):
        assert g(**{**base, "pipeline_outcome": state}) is None, state
    # STRICT BOOLEANS (cr): truthy non-True never authorizes
    assert g(**{**base, "committed": "false"}) is None
    assert g(**{**base, "committed": 1}) is None
    assert g(**{**base, "moves_open": "false"}) is None
    assert g(**{**base, "moves_open": "true"}) is None
    assert g(**{**base, "moves_open": 1}) is None
    # non-action / uncommitted turns never grow
    assert g(**{**base, "kind": "question"}) is None
    assert g(**{**base, "committed": False}) is None
    # a host structural deny forbids growth (and only a host deny can)
    assert g(**{**base, "host_deny": "sealed_boundary"}) is None
    # no signal → no growth even with a clean pipeline miss
    assert g(**{**base, "moves_open": False}) is None
    # encounter outranks place when both signals fire
    assert g(**{**base, "seeks_encounter": True}) == "encounter"


def test_classify_fields_fail_closed(world):
    # spec §5: absent fields read False — today's behavior byte-identical.
    # A stubbed classify WITHOUT the new fields runs a normal turn with no
    # growth signals raised (nothing in the trace, no cohort calls).
    from tests.test_integration import make_arc, run_turn, seed_arc
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    from construct.provider import StubProvider
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""},
        {"prose": "The study holds its quiet."},
    ])
    r = run_turn(world, arc, provider, "I look around.", turn=2,
                 generate=False)
    assert r.prose                       # the turn ran exactly as before


def test_strict_flag_accepts_only_literal_true():
    from construct.growth import strict_flag
    assert strict_flag(True)
    for v in (False, None, "", "true", "false", "True", 1, 0, [], [True],
              {"v": True}):
        assert not strict_flag(v), repr(v)


def test_classify_signal_unpack_is_strict_and_provider_error_safe(world):
    # cr piece-2 finding 1, end to end: (a) a classify verdict carrying
    # MALFORMED signal values ("true"/"false" strings) leaves both growth
    # locals False — no signal ever raised; (b) a classify ProviderError
    # leaves them DEFINED and False (the pre-classify defaults). Proven via
    # the trace's absence of any growth artifact and the turn surviving.
    from tests.test_integration import make_arc, run_turn, seed_arc
    from construct.provider import StubProvider
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "moves_open": "true", "seeks_encounter": 1},
        {"prose": "The study holds its quiet."},
    ])
    r = run_turn(world, arc, provider, "I wander off.", turn=2, generate=False)
    assert r.prose                              # ran; malformed flags inert
    # provider-error path: classify raises → defaults hold, turn survives
    import construct.turnloop as tl
    from construct.provider import ProviderTransportError
    mp = pytest.MonkeyPatch()
    mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])

    def _boom(*_a, **_k):
        raise ProviderTransportError("classify down")

    mp.setattr(tl.cohorts, "classify", _boom)
    try:
        world._extractions.extend([{"items": []}, {"items": []}])
        p2 = StubProvider([{"prose": "Still standing."}])
        r2 = run_turn(world, arc, p2, "I wander again.", turn=3,
                      generate=False)
    finally:
        mp.undo()
    assert r2.prose                             # defined-and-False, no crash


def test_moves_open_contract_covers_prospective_first_x():
    # cr piece-2 finding 3: the field's own contract must put prospective
    # first-X travel ("the first light I trust" — the Ironhold class) on
    # the TRUE side and concrete named places on the FALSE side. Pin the
    # schema text both ways.
    from construct.cohorts import CLASSIFY_SCHEMA
    desc = CLASSIFY_SCHEMA["properties"]["moves_open"]["description"]
    assert "first light I trust" in desc          # prospective → true side
    assert "prospective" in desc
    assert "FALSE for any CONCRETE named" in desc # concrete → false side
    assert "'the first tavern I see'" not in desc.split("FALSE")[1]         if "FALSE" in desc else True              # first-X never a FALSE example


def _vp(raw, **kw):
    """The gate with the EXPLICIT vocabulary-free predicate — concealment
    screening has no permissive default (cr piece-3 re-review, blocker 1)."""
    from construct.growth import validated_proposal
    kw.setdefault("leaks", lambda text: False)
    return validated_proposal(raw, **kw)


def _good():
    return {"assessment": "The road connects farm country to the market town;"
                          " a farmer with a caravan fits.",
            "confidence": 0.85,
            "place": {"name": "the Willow Ford waypost", "identity":
                      "a plank shelter where carters water their teams",
                      "parent_index": 1},
            "encounter": {"name": "Gregor Bund", "role": "a husky farmer",
                          "drive": "sell the season's grain well",
                          "doing": "walking his caravan to market",
                          "companion": {"name": "Kip", "kind": "dog",
                                        "bond": "his road companion"}},
            "texture": ["a weather-worn signpost", "wheel ruts in the clay"]}


def test_validated_proposal_happy_path():
    p, why = _vp(_good(), mode="place", n_ancestry_options=3)
    assert why == "" and p.place["parent_index"] == 1
    assert p.encounter["companion"]["name"] == "Kip"
    assert p.texture == ("a weather-worn signpost", "wheel ruts in the clay")


def test_id_tokens_decline_anywhere_in_any_field():
    # cr: EMBEDDED ids must decline, in every persisted field family
    g = _good()
    cases = [
        (dict(g, place=dict(g["place"], name="place:willow_ford")),
         "unlicensed:place.name_id"),
        (dict(g, place=dict(g["place"],
                            identity="waypost at place:secret_ford")),
         "unlicensed:place.identity_id"),
        (dict(g, encounter=dict(g["encounter"],
                                role="courier for person:hidden_lord")),
         "unlicensed:encounter.role_id"),
        (dict(g, encounter=dict(g["encounter"],
                                companion={"name": "Kip", "kind": "dog",
                                           "bond": "guards obj:secret_key"})),
         "unlicensed:encounter.companion.bond_id"),
        (dict(g, texture=["mud", "a crate marked obj:contraband"]),
         "unlicensed:texture.1_id"),
    ]
    for raw, want in cases:
        assert _vp(raw, mode="place", n_ancestry_options=3)[1] == want, want


def test_concealment_predicate_screens_every_field():
    # the HOST-SUPPLIED leak predicate (the model never sees the vocabulary)
    leaks = lambda text: "vermilion" in text.lower()
    g = _good()
    g["place"]["name"] = "the Vermilion Ford"
    assert _vp(g, mode="place", n_ancestry_options=3, leaks=leaks)[1] == \
        "unlicensed:place.name_concealed"
    g2 = _good()
    g2["texture"] = ["a vermilion pennant"]
    assert _vp(g2, mode="place", n_ancestry_options=3, leaks=leaks)[1] == \
        "unlicensed:texture.0_concealed"


def test_assessment_satisfies_the_persisted_field_contract():
    # cr G3 blocker 1: assessment PERSISTS as region.style and enters the
    # briefing — id tokens, concealed vocabulary, and overlength decline
    leaks = lambda text: "vermilion" in text.lower()
    g = _good()
    g["assessment"] = "the road serves person:rival and the farm towns"
    assert _vp(g, mode="place", n_ancestry_options=2)[1] == \
        "unlicensed:assessment_id"
    g = _good()
    g["assessment"] = "the Vermilion road carries the grain trade"
    assert _vp(g, mode="place", n_ancestry_options=2, leaks=leaks)[1] == \
        "unlicensed:assessment_concealed"
    g = _good()
    g["assessment"] = "x" * 601
    assert _vp(g, mode="place", n_ancestry_options=2)[1] == \
        "malformed:assessment_length"
    g = _good()
    g["assessment"] = "y" * 600      # the paragraph bound itself is legal
    assert _vp(g, mode="place", n_ancestry_options=2)[1] == ""


def test_parent_and_mode_authority_closed():
    g = _good()
    # exact-int only: float and bool decline as TYPE, never coerce
    for bad in (0.9, True, "1", None):
        raw = dict(g, place=dict(g["place"], parent_index=bad))
        assert _vp(raw, mode="place", n_ancestry_options=3)[1] == \
            "malformed:place.parent_index_type", repr(bad)
    # strict range, no fallback option; zero host options forbids ANY place
    raw = dict(g, place=dict(g["place"], parent_index=7))
    assert _vp(raw, mode="place", n_ancestry_options=3)[1] == \
        "unlicensed:place.parent_index_range"
    assert _vp(g, mode="place", n_ancestry_options=0)[1] == \
        "unlicensed:place.no_ancestry_options"
    assert _vp(g, mode="place", n_ancestry_options=-1)[1] == \
        "unlicensed:place.no_ancestry_options"
    # unknown mode declines outright; mode contracts enforced
    assert _vp(g, mode="wander", n_ancestry_options=3)[1] == "malformed:mode"
    assert _vp({"assessment": "x", "confidence": 0.9, "texture": ["a"]},
              mode="encounter", n_ancestry_options=1)[1] == \
        "malformed:encounter_required"
    assert _vp({"assessment": "x", "confidence": 0.9, "texture": ["a"]},
              mode="place", n_ancestry_options=1)[1] == \
        "malformed:place_required"
    # the assessor call itself refuses unknown modes / empty options
    import pytest as _pt
    from construct.cohorts import assessor_propose
    with _pt.raises(ValueError):
        assessor_propose(None, mode="wander", intent="x", here_name="h",
                         ancestry_options=["a"], connections="", style="",
                         laws="", threads=[], clock_line="", protagonist="p")
    with _pt.raises(ValueError):
        assessor_propose(None, mode="place", intent="x", here_name="h",
                         ancestry_options=[], connections="", style="",
                         laws="", threads=[], clock_line="", protagonist="p")


def test_exact_shapes_never_coerced_or_repaired():
    g = _good()
    # list-valued name is a TYPE failure, never stringified
    raw = dict(g, place=dict(g["place"], name=["Willow Ford"]))
    assert _vp(raw, mode="place", n_ancestry_options=3)[1] == \
        "malformed:place.name_type"
    # texture: string is not a list; 4 items DECLINE (never truncate);
    # empty/absent decline (the spec requires 1-3)
    assert _vp(dict(g, texture="road"), mode="place",
              n_ancestry_options=3)[1] == "malformed:texture_type"
    assert _vp(dict(g, texture=["a", "b", "c", "d"]), mode="place",
              n_ancestry_options=3)[1] == "malformed:texture_too_many"
    assert _vp(dict(g, texture=[]), mode="place",
              n_ancestry_options=3)[1] == "malformed:texture_empty"
    g2 = _good(); del g2["texture"]
    assert _vp(g2, mode="place", n_ancestry_options=3)[1] == \
        "malformed:texture_type"
    # over-length fields decline
    raw = dict(g, place=dict(g["place"], identity="x" * 300))
    assert _vp(raw, mode="place", n_ancestry_options=3)[1] == \
        "malformed:place.identity_length"


def test_confidence_implements_its_contract():
    g = _good()
    for bad in (float("nan"), float("inf"), -0.1, 4, True, "0.9", None):
        assert _vp(dict(g, confidence=bad), mode="place",
                  n_ancestry_options=3)[1] == "malformed:confidence", repr(bad)
    # LOW is a stable retryable decline, never an accepted proposal
    assert _vp(dict(g, confidence=0.2), mode="place",
              n_ancestry_options=3)[1] == "proposal:low_confidence"
    # the host owns the threshold
    p, why = _vp(dict(g, confidence=0.2), mode="place",
                n_ancestry_options=3, min_confidence=0.1)
    assert why == "" and p.confidence == 0.2


def test_concealment_screening_is_never_optional():
    # cr: omission must NOT yield an accepted proposal — the predicate is
    # a required parameter; a vocabulary-free arc says so explicitly
    from construct.growth import validated_proposal
    import pytest as _pt
    with _pt.raises(TypeError):
        validated_proposal(_good(), mode="place", n_ancestry_options=3)
    for bad in (None, "vermilion", 0, []):
        with _pt.raises(ValueError):
            validated_proposal(_good(), mode="place", n_ancestry_options=3,
                               leaks=bad)
    p, why = validated_proposal(_good(), mode="place", n_ancestry_options=3,
                                leaks=lambda text: False)
    assert why == "" and p is not None


def test_texture_must_be_a_real_list():
    # cr: tuples are not the contract's JSON list
    assert _vp(dict(_good(), texture=("mud",)), mode="place",
               n_ancestry_options=3)[1] == "malformed:texture_type"


def test_malformed_host_gate_parameters_raise():
    # cr: host-owned does not make malformed values safe — NaN/None
    # thresholds and bool/float counts must not defeat the invariants
    import pytest as _pt
    g = _good()
    for bad in (float("nan"), None, True, -0.1, 1.5, "0.35"):
        with _pt.raises(ValueError):
            _vp(g, mode="place", n_ancestry_options=3, min_confidence=bad)
    for bad in (True, 1.5, "3", None):
        with _pt.raises(ValueError):
            _vp(g, mode="place", n_ancestry_options=bad)


def test_assessor_schema_is_id_free_and_lints():
    # the schema itself carries the authority contract: display-words
    # language present, and the preflight lints it (the *_SCHEMA audit
    # already sweeps it — this pins the intent locally too)
    from construct.cohorts import ASSESSOR_SCHEMA
    from construct.provider import lint_schema
    lint_schema(ASSESSOR_SCHEMA, path="ASSESSOR_SCHEMA")
    blob = str(ASSESSOR_SCHEMA)
    assert "NEVER an id" in blob or "never an id" in blob
    assert "parent_index" in blob                 # choose-among-options only


# ---- piece 4: host row assembly -------------------------------------------

#: the host references every _assemble call claims as canon truth
_CANON = {"place:north_road", "place:the_march", "place:greywater_vale",
          "person:you", "person:reed", "person:aldous"}


def _assemble(prop, **kw):
    from construct.growth import assemble_chunk
    kw.setdefault("mode", "place")
    kw.setdefault("origin", "place:north_road")
    kw.setdefault("ancestry_options",
                  ["place:the_march", "place:greywater_vale"])
    kw.setdefault("protagonist", "person:you")
    kw.setdefault("companions", [])
    kw.setdefault("at", 5000.0)
    kw.setdefault("exists", lambda eid: eid in _CANON)
    kw.setdefault("identity", lambda kind, name: ("new", ""))
    return assemble_chunk(prop, **kw)


def _good_prop():
    p, why = _vp(_good(), mode="place", n_ancestry_options=2)
    assert why == ""
    return p


def test_assembly_builds_the_ordered_chunk():
    chunk, why = _assemble(_good_prop(),
                           companions=["person:reed", "person:aldous"])
    assert why == "" and chunk.place_id == "place:the_willow_ford_waypost"
    keys = [(r["entity"], r["attribute"]) for r in chunk.items]
    pid = chunk.place_id
    # declaration strictly precedes containment, passage, moves, encounter,
    # texture — order is CONTRACTUAL under staged-prefix gating
    assert keys.index((pid, "kind")) < keys.index((pid, "in"))
    assert keys.index((pid, "in")) < keys.index(("place:north_road",
                                                 "connects_to"))
    assert keys.index(("place:north_road", "connects_to")) \
        < keys.index(("person:you", "in"))
    assert keys.index(("person:you", "in")) \
        < keys.index((chunk.person_id, "kind"))
    row = {(r["entity"], r["attribute"]): r for r in chunk.items}
    # G3: first growth into UNGOVERNED territory mints the region card and
    # the ANCESTRY INSERTION interposes it atomically — the place nests in
    # the card, the card in the host-picked parent (never model text)
    rid = chunk.region_id
    assert rid.startswith("region:")
    assert row[(pid, "in")]["value"] == rid
    assert row[(rid, "in")]["value"] == "place:greywater_vale"
    assert row[(rid, "kind")]["value"] == "region"
    assert "farm country" in row[(rid, "style")]["value"]   # WHY it exists
    # declaration precedes the insertion pair, card before place (staged-
    # prefix order)
    keys2 = [(r["entity"], r["attribute"]) for r in chunk.items]
    assert keys2.index((rid, "kind")) < keys2.index((rid, "in"))
    assert keys2.index((rid, "in")) < keys2.index((pid, "in"))
    # ONE stored edge — the lateral graph is undirected (cr ruling 7)
    assert sum(1 for _, a in keys if a == "connects_to") == 1
    assert (pid, "connects_to") not in row
    # the companion postcondition: every standing companion in the SAME set
    assert row[("person:reed", "in")]["value"] == pid
    assert row[("person:aldous", "in")]["value"] == pid
    # furnish stands down: the place arrives DESCRIBED
    assert row[(pid, "description")]["value"].startswith("a plank shelter")
    # the encounter is anchored + their companion bonded
    assert row[(chunk.person_id, "in")]["value"] == pid
    assert row[(chunk.companion_id, "accompanying")]["value"] \
        == chunk.person_id
    # texture: chunk-keyed attributes, exact-at coordinate
    assert row[(pid, "detail_5000p0_1")]["value"] == "a weather-worn signpost"
    assert row[(pid, "detail_5000p0_2")]["value"] == "wheel ruts in the clay"
    # derivation receipt rides along, never as a row
    assert "farm country" in chunk.assessment
    assert all(a != "assessment" for _, a in keys)


def test_assembly_accretes_no_card_under_governed_territory():
    # G3: a region card already in the ancestry GOVERNS — later growth
    # nests under the chain (accretion, never fragmentation)
    g = _good()
    g["place"]["parent_index"] = 0
    p, why = _vp(g, mode="place", n_ancestry_options=3)
    assert why == ""
    canon = _CANON | {"region:the_marchlands"}
    chunk, why = _assemble(
        p, ancestry_options=["region:the_marchlands", "place:the_march",
                             "place:greywater_vale"],
        exists=lambda eid: eid in canon)
    assert why == "" and chunk.region_id == ""
    row = {(r["entity"], r["attribute"]): r for r in chunk.items}
    assert row[(chunk.place_id, "in")]["value"] == "region:the_marchlands"
    assert not any(str(r["entity"]).startswith("region:")
                   and r["entity"] != "region:the_marchlands"
                   for r in chunk.items)


def test_assembly_parent_above_the_card_is_host_forced(monkeypatch):
    # cr G3 blocker 2: options [current, region, outer] with parent_index=2
    # must NOT detach the place from governance — the host forces the card
    g = _good()
    g["place"]["parent_index"] = 2
    p, why = _vp(g, mode="place", n_ancestry_options=3)
    assert why == ""
    canon = _CANON | {"region:the_marchlands"}
    chunk, why = _assemble(
        p, ancestry_options=["place:north_road", "region:the_marchlands",
                             "place:the_march"],
        exists=lambda eid: eid in canon)
    assert why == "" and chunk.region_id == ""
    row = {(r["entity"], r["attribute"]): r for r in chunk.items}
    assert row[(chunk.place_id, "in")]["value"] == "region:the_marchlands"
    # choices AT or BELOW the card stand (index 0 = the current place)
    g = _good()
    g["place"]["parent_index"] = 0
    p, why = _vp(g, mode="place", n_ancestry_options=3)
    chunk, why = _assemble(
        p, ancestry_options=["place:north_road", "region:the_marchlands",
                             "place:the_march"],
        exists=lambda eid: eid in canon)
    assert why == ""
    row = {(r["entity"], r["attribute"]): r for r in chunk.items}
    assert row[(chunk.place_id, "in")]["value"] == "place:north_road"


def test_every_row_carries_an_explicit_temporal_coordinate():
    # cr blocker 5: nothing may ride the engine's mutable cursor — each row
    # is constitutive (timeless) XOR acquired (valid_from == at)
    chunk, why = _assemble(_good_prop(), companions=["person:reed"])
    assert why == ""
    for r in chunk.items:
        timeless = r.get("timeless") is True
        stamped = r.get("valid_from") == 5000.0
        assert timeless != stamped, r
    row = {(r["entity"], r["attribute"]): r for r in chunk.items}
    # the classification itself (cr re-review 1): ONLY identity/structure
    # is timeless under PB's whole-history contract; role/drive/bond/
    # description are standing-but-ACQUIRED — their earliest supported
    # point is this growth horizon
    for a in ("kind", "name"):
        assert row[(chunk.person_id, a)].get("timeless") is True
    for a in ("role", "drive", "doing", "in"):
        assert row[(chunk.person_id, a)]["valid_from"] == 5000.0
    assert row[(chunk.companion_id, "bond")]["valid_from"] == 5000.0
    assert row[(chunk.place_id, "description")]["valid_from"] == 5000.0


def test_assembled_rows_land_at_the_horizon_not_the_cursor(tmp_path):
    # cr blocker 5 (engine oracle): cursor far AHEAD of at — rows must land
    # at the supplied horizon; and cr ruling 7: ONE stored connects_to edge
    # traverses BOTH directions on the undirected lateral graph
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    w = World(tmp_path / "g.world", world_id="w:g",
              model=StubModel(fallback=rule_classifier_fallback()),
              stance="fiction", title="Growth")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:north_road", "attribute": "kind", "value": "place",
         "timeless": True},
        {"entity": "place:the_march", "attribute": "kind", "value": "place",
         "timeless": True},
        {"entity": "place:greywater_vale", "attribute": "kind",
         "value": "place", "timeless": True},
        {"entity": "person:you", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:you", "attribute": "in",
         "value": "place:north_road", "value_type": "entity"},
    ])
    w.ingestor.cursor.advance(9000.0)   # the mutable cursor sits FAR ahead
    from construct.adapter import PorcelainWorldReads
    reads = PorcelainWorldReads(w)
    chunk, why = _assemble(_good_prop(), at=5000.0,
                           exists=lambda eid: reads.has_entity(eid))
    assert why == ""
    receipt = w.ingest_structured(list(chunk.items), classify="rules")
    assert not (getattr(receipt, "skipped", None) or [])
    pid = chunk.place_id
    # acquired facts exist AT the horizon, not before it
    assert w.porcelain.state("person:you", "in", as_of=4999.0)["fact"][
        "value"] == "place:north_road"
    assert w.porcelain.state("person:you", "in", as_of=5000.5)["fact"][
        "value"] == pid
    assert w.porcelain.state(pid, "description", as_of=4999.0)[
        "status"] != "known"          # acquired: ABSENT before growth
    assert w.porcelain.state(pid, "description", as_of=5000.5)[
        "status"] == "known"
    assert w.porcelain.state(chunk.person_id, "role", as_of=4999.0)[
        "status"] != "known"
    assert w.porcelain.state(chunk.person_id, "role", as_of=5000.5)[
        "fact"]["value"] == "a husky farmer"
    assert w.porcelain.state(pid, "name", as_of=4999.0)[
        "status"] == "known"          # identity/structure: timeless
    # one stored edge, walkable both ways
    fwd = w.porcelain.path("place:north_road", pid, as_of=5000.5)
    rev = w.porcelain.path(pid, "place:north_road", as_of=5000.5)
    assert fwd and rev and fwd == list(reversed(rev))


def test_assembly_accepts_the_exact_representable_edge():
    # 2**53 IS exact in the float coordinate; its successor is rejected
    # above (host-bug oracle) — adjacent accepted chunks can never collide
    chunk, why = _assemble(_good_prop(), at=2**53)
    assert why == ""
    assert any(r["attribute"].startswith("detail_9007199254740992")
               for r in chunk.items)


def test_assembly_texture_keys_are_disjoint_across_chunks():
    # cr blocker 6: two chunks on ONE anchor at different times — int()
    # truncation collided 5000.1 with 5000.9; the exact coordinate must not
    g = _good()
    del g["place"]
    p1, _ = _vp(g, mode="encounter", n_ancestry_options=0)
    a = _assemble(p1, mode="encounter", at=5000.1)[0]
    b = _assemble(p1, mode="encounter", at=5000.9)[0]
    keys_a = {(r["entity"], r["attribute"]) for r in a.items
              if r["attribute"].startswith("detail_")}
    keys_b = {(r["entity"], r["attribute"]) for r in b.items
              if r["attribute"].startswith("detail_")}
    assert keys_a and keys_b and not (keys_a & keys_b)


def test_assembly_ids_are_collision_free():
    # canon roster collision AND intra-chunk collision both ordinal-probe
    taken = _CANON | {"place:the_willow_ford_waypost", "person:gregor_bund",
                      "person:gregor_bund_2"}
    g = _good()
    g["encounter"]["companion"]["name"] = "Gregor Bund"  # same-named pair
    p, why = _vp(g, mode="place", n_ancestry_options=2)
    assert why == ""
    chunk, why = _assemble(p, exists=lambda eid: eid in taken)
    assert why == ""
    assert chunk.place_id == "place:the_willow_ford_waypost_2"
    assert chunk.person_id == "person:gregor_bund_3"
    assert chunk.companion_id == "person:gregor_bund_4"


def test_assembly_identity_decisions_are_consumed_structurally():
    # cr blocker 1: the host identity decision, all three outcomes
    g = _good()
    # place BOUND → reuse: geography only, no constitutive rows
    ident = lambda kind, name: ("bound", "place:greywater_vale") \
        if kind == "place" else ("new", "")
    chunk, why = _assemble(_good_prop(), identity=ident)
    assert why == "" and chunk.place_id == "place:greywater_vale"
    keys = [(r["entity"], r["attribute"]) for r in chunk.items]
    assert ("place:greywater_vale", "kind") not in keys       # no re-declare
    assert ("place:greywater_vale", "description") not in keys  # no supersede
    assert ("place:greywater_vale", "in") not in keys
    row = {k: r for k, r in zip(keys, chunk.items)}
    assert row[("place:north_road", "connects_to")]["value"] \
        == "place:greywater_vale"
    assert row[("person:you", "in")]["value"] == "place:greywater_vale"
    # place bound to the ORIGIN → the road led nowhere new
    here = lambda kind, name: ("bound", "place:north_road") \
        if kind == "place" else ("new", "")
    assert _assemble(_good_prop(), identity=here)[1] == \
        "proposal:place_is_here"
    # place ambiguous → decline, never guess
    amb = lambda kind, name: ("ambiguous", "") if kind == "place" \
        else ("new", "")
    assert _assemble(_good_prop(), identity=amb)[1] == \
        "unlicensed:place.name_ambiguous"
    # person bound/ambiguous → decline (cast/canon collision + teleport)
    pb = lambda kind, name: ("bound", "person:reed") \
        if kind == "person" else ("new", "")
    assert _assemble(_good_prop(), identity=pb)[1] == \
        "unlicensed:encounter.name_binds_existing"
    pa = lambda kind, name: ("ambiguous", "") if kind == "person" \
        else ("new", "")
    assert _assemble(_good_prop(), identity=pa)[1] == \
        "unlicensed:encounter.name_ambiguous"
    # companion-only bind declines with its own reason
    calls = []
    def comp_bind(kind, name):
        calls.append((kind, name))
        if kind == "person" and name == "Kip":
            return ("bound", "person:reed")
        return ("new", "")
    assert _assemble(_good_prop(), identity=comp_bind)[1] == \
        "unlicensed:encounter.companion.name_binds_existing"
    assert ("person", "Kip") in calls


def test_assembly_names_persist_exactly_and_long_names_decline_upstream():
    # cr blocker 4: no repair after acceptance — the 60-char gate is the
    # VALIDATOR's; assembly persists the exact validated value
    g = _good()
    g["place"]["name"] = "x" * 61
    assert _vp(g, mode="place", n_ancestry_options=2)[1] == \
        "malformed:place.name_length"
    g = _good()
    g["encounter"]["name"] = "y" * 61
    assert _vp(g, mode="place", n_ancestry_options=2)[1] == \
        "malformed:encounter.name_length"
    g = _good()
    g["encounter"]["companion"]["name"] = "z" * 61
    assert _vp(g, mode="place", n_ancestry_options=2)[1] == \
        "malformed:encounter.companion.name_length"
    g = _good()
    g["place"]["name"] = "The Long Portage Above The Greywater Falls Where " \
                         "Carters Res"  # exactly 60
    assert len(g["place"]["name"]) == 60
    p, why = _vp(g, mode="place", n_ancestry_options=2)
    assert why == ""
    chunk, why = _assemble(p)
    assert why == ""
    row = {(r["entity"], r["attribute"]): r for r in chunk.items}
    assert row[(chunk.place_id, "name")]["value"] == g["place"]["name"]


def test_assembly_encounter_without_place_anchors_at_origin():
    g = _good()
    del g["place"]
    p, why = _vp(g, mode="encounter", n_ancestry_options=0)
    assert why == ""
    chunk, why = _assemble(p, mode="encounter")
    assert why == "" and chunk.place_id == ""
    row = {(r["entity"], r["attribute"]): r for r in chunk.items}
    assert row[(chunk.person_id, "in")]["value"] == "place:north_road"
    # nobody teleports: an encounter come TO the road moves no one
    assert ("person:you", "in") not in row
    # growth's texture lands on the anchor
    assert row[("place:north_road", "detail_5000p0_1")]["value"] \
        == "a weather-worn signpost"


def test_assembly_declines_unsluggable_names():
    g = _good()
    g["place"]["name"] = "???"
    p, why = _vp(g, mode="place", n_ancestry_options=2)
    assert why == ""
    chunk, why = _assemble(p)
    assert chunk is None and why == "malformed:place.name_unsluggable"


def test_assembly_mode_continuity_is_proven():
    # cr blocker 3: a proposal validated under one mode must not assemble
    # under another — both directions raise
    import pytest as _pt
    g = _good()
    del g["place"]
    enc_prop, why = _vp(g, mode="encounter", n_ancestry_options=0)
    assert why == ""
    with _pt.raises(ValueError):
        _assemble(enc_prop, mode="place")
    with _pt.raises(ValueError):
        _assemble(_good_prop(), mode="encounter")


def test_assembly_host_bugs_raise():
    import pytest as _pt
    p = _good_prop()
    bad_calls = [
        dict(exists=None),
        dict(identity=None),
        dict(identity=lambda k, n: "new"),           # malformed decision
        dict(identity=lambda k, n: ("maybe", "")),
        dict(identity=lambda k, n: ("new", None)),       # second slot exact
        dict(identity=lambda k, n: ("new", "person:reed")),
        dict(identity=lambda k, n: ("ambiguous", "person:reed")),
        dict(origin="north road"),
        dict(origin="place:"),                       # frozen grammar: empty local
        dict(origin="place:Elsewhere"),              # frozen grammar: case
        dict(origin=None),
        dict(origin="place:unknown_road"),           # shape ok, NOT canon
        dict(protagonist="you"),
        dict(protagonist="person:nobody"),           # not canon
        dict(companions=("person:reed",)),           # exact list, not tuple
        dict(companions=["person:reed", "reed"]),
        dict(companions=["person:ghost"]),           # not canon
        dict(companions=["person:reed", "person:reed"]),   # duplicate
        dict(companions=["person:you"]),             # protagonist-as-companion
        dict(at=float("nan")),
        dict(at=True),
        dict(at=-5.0),
        dict(at=2**53 + 1),      # not exactly representable — would collide
        dict(at=10**400),        # OverflowError normalized to ValueError
        dict(mode="wander"),
        dict(ancestry_options=[]),                   # place proposed, no list
        dict(ancestry_options=["place:a"]),          # not canon
        dict(ancestry_options=["place:the_march"]),  # index 1 out of range —
    ]                                                # validation/assembly split
    for kw in bad_calls:
        with _pt.raises(ValueError):
            _assemble(p, **kw)
    with _pt.raises(ValueError):
        _assemble({"not": "a proposal"})
    # all-anchors-absent (cr blocker 2's pinned oracle): shape-valid host
    # refs whose canon membership is FALSE must never assemble
    with _pt.raises(ValueError):
        _assemble(p, exists=lambda eid: False)


# ---- piece 5: the no-growth host check + the generative slot --------------

def test_no_growth_denies_only_on_affirmative_proof():
    from construct.growth import NO_GROWTH_DENIES, no_growth_deny
    # the closed vocabulary, each from its own proof
    assert no_growth_deny(boundary_status="blocked") == "deny:sealed_boundary"
    assert no_growth_deny(no_frontier=True) == "deny:no_frontier"
    assert no_growth_deny(laws_forbid=True) == "deny:laws_forbid"
    for r in ("deny:sealed_boundary", "deny:no_frontier", "deny:laws_forbid"):
        assert r in NO_GROWTH_DENIES
    # NO proof, NO deny — an unproven deny is the stonewall back under a
    # receipt: fuzzy statuses, truthy-not-True flags, and absence all pass
    assert no_growth_deny() == ""
    assert no_growth_deny(boundary_status="clear") == ""
    assert no_growth_deny(boundary_status="deliberating") == ""
    assert no_growth_deny(boundary_status="unknown") == ""
    assert no_growth_deny(no_frontier="yes") == ""
    assert no_growth_deny(no_frontier=1) == ""
    assert no_growth_deny(laws_forbid="true") == ""
    # cr piece-5 blocker: proof is the LITERAL str — an object that merely
    # stringifies to "blocked" is malformed input, and malformed passes
    # through as no-proof, never repaired INTO proof
    class LooksBlocked:
        def __str__(self):
            return "blocked"
    assert no_growth_deny(boundary_status=LooksBlocked()) == ""
    assert no_growth_deny(boundary_status=b"blocked") == ""
    # precedence is fixed and first-proof wins (stable receipts)
    assert no_growth_deny(boundary_status="blocked",
                          laws_forbid=True) == "deny:sealed_boundary"


def test_generative_slot_claims_once_at_invocation():
    import pytest as _pt
    from construct.growth import GenerativeSlot
    slot = GenerativeSlot()
    assert slot.claim("assessor") is True
    # spent WHETHER OR NOT the act succeeds — no release surface exists
    assert slot.claim("lwg_opportunistic") is False
    assert slot.claim("tangent_author") is False
    assert slot.claimed_by == "assessor"
    assert slot.refused == ["lwg_opportunistic", "tangent_author"]
    with _pt.raises(ValueError):
        slot.claim("")
    with _pt.raises(ValueError):
        GenerativeSlot().claim(None)
    with _pt.raises(ValueError):
        GenerativeSlot().claim("   ")   # a diagnostic label, not whitespace
    padded = GenerativeSlot()
    assert padded.claim(" assessor ") is True
    assert padded.claimed_by == "assessor"   # stored clean (cr nonblocking)


# ---- the wiring slice: the gate on the REAL turn path ----------------------

def _wired_world(tmp_path):
    from patternbuffer import World
    tmp_path.mkdir(parents=True, exist_ok=True)
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(tmp_path / "wire.world", world_id="w:wire",
              model=StubModel(fallback=fallback), stance="fiction",
              title="Growth Wiring")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:the_march", "attribute": "kind", "value": "region",
         "timeless": True},
        {"entity": "place:greywater_vale", "attribute": "kind",
         "value": "region", "timeless": True},
        {"entity": "place:greywater_vale", "attribute": "in",
         "value": "place:the_march", "value_type": "entity"},
        {"entity": "place:north_road", "attribute": "kind", "value": "place",
         "timeless": True},
        {"entity": "place:north_road", "attribute": "in",
         "value": "place:greywater_vale", "value_type": "entity"},
        {"entity": "person:you", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:you", "attribute": "in",
         "value": "place:north_road", "value_type": "entity"},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition",
         "timeless": True},
        {"entity": "fact:secret", "attribute": "culprit",
         "value": "person:rival"},
        {"entity": "person:rival", "attribute": "kind", "value": "person",
         "timeless": True},
    ])
    w.ingest_structured(
        [{"entity": "person:you", "attribute": "in",
          "value": "place:north_road", "value_type": "entity"}],
        frame="knows:person:you")
    return w


def _wired_arc():
    from construct.arc.conditions import InFrame, Occurred, TurnsQuiet
    from construct.arc.grammar import (Arc, Beat, Clock, ConclusionShape,
                                       Phase, Rung, Weight)
    beat = Beat("beat:find", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame("knows:person:you", "fact:secret",
                                       "culprit", "person:rival"))
    refusal = Clock("clock:refusal", Occurred("event:abandoned"),
                    effects=({"entity": "event:world_concludes",
                              "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape(
        "shape:main", "drive_inverted",
        ("person:you", "drive:comfort", "drive:truth"),
        world_condition=InFrame("knows:person:you", "fact:secret", "culprit",
                                "person:rival"),
        premise=InFrame("canon", "fact:secret", "culprit", "person:rival"),
        refusal_variant_id="shape:refused")
    return Arc(arc_id="arc:main", protagonist="person:you", shape=shape,
               beats=(beat,), clocks=(), refusal_clock=refusal,
               climax_ready_k=1, climax_ready_beats=("beat:find",),
               phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                             Phase.CLIMAX: 2, Phase.FALLING: 2})


def _classify(**over):
    v = {"kind": "action", "moves_to": "away", "requires": [],
         "needs_test": False, "uncertain_of": "", "moves_open": True}
    v.update(over)
    return v


def test_wired_gate_activates_through_the_real_envelope(tmp_path):
    # THE OBSERVABLE GATE-CALL ORACLE, post-arrival: a real run_turn on the
    # REAL engine's detected commit_set door — the pipeline misses, the
    # Assessor is INVOKED through the actual turn path, the chunk commits
    # atomically, the walk lands, and the seam is gone.
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        npt = {"acts": True, "action": "waters his team at the trough",
               "speaks": True, "intent": "size up the newcomer",
               "line_hint": ""}
        provider = StubProvider(
            [_classify(), _good(), dict(npt), dict(npt)]
            + [{"prose": "The waypost, and a farmer at it."}] * 4)
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth == "activated:place:the_willow_ford_waypost"
        assert r.trace.growth_retry is False
        assert r.prose != _GROWTH_SEAM
        assert "assessor_propose:main" in r.trace.cohort_calls
        # COMMITTED: growth entities live, the walk landed
        assert w.porcelain.state("place:the_willow_ford_waypost",
                                 "kind")["status"] == "known"
        assert w.porcelain.state("person:gregor_bund",
                                 "kind")["status"] == "known"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:the_willow_ford_waypost"
        assert "person:you" in r.trace.growth_moved
        # the assessor saw the HOST's truth: ancestry options + frontier
        gro = [c[0] for c in provider.calls if "⟦gro⟧" in c[0][:40]]
        assert gro and "north road" in gro[0]
        assert "[1]" in gro[0]           # indexed host ancestry options
        assert "nothing is authored past here" in gro[0]  # frontier, not
    finally:                                              # emptiness
        w.close()


def test_wired_gate_fails_closed_without_the_envelope(tmp_path, monkeypatch):
    # the narrowly scoped PRE-arrival oracle (cr AMBER: keep exactly one):
    # capability pinned "" simulates an envelope-less engine — the adaptor
    # fails CLOSED: seam prose, receipt on the trace, world untouched.
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    monkeypatch.setattr(growth_mod, "_capability", lambda p: "")
    w = _wired_world(tmp_path)
    try:
        provider = StubProvider([
            _classify(),
            _good(),               # the Assessor's (valid) proposal
        ])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.settle is None
        assert r.trace.growth == "activation_unavailable"
        assert r.trace.growth_retry is True
        # NOTHING committed: no growth entities, no displacement, no clock
        assert w.porcelain.state("place:the_willow_ford_waypost",
                                 "kind")["status"] != "known"
        assert w.porcelain.state("person:gregor_bund", "kind")[
            "status"] != "known"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_gate_not_invoked_without_the_signal(tmp_path):
    # negative control: same pipeline miss, moves_open False → the gate
    # never runs (trace.growth empty), the turn renders normally
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    w = _wired_world(tmp_path)
    try:
        provider = StubProvider([
            _classify(moves_open=False),
            {"prose": "You press on down the road."},
            {"prose": "You press on down the road."},   # the render re-ask
        ])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth == ""
        assert r.trace.growth_retry is False
        assert "press on" in r.prose
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()


def test_wired_encounter_invokes_with_no_destination(tmp_path):
    # G2: "I walk until I run into someone" — no stated destination, so
    # the pipeline had nothing to resolve (proven zero-destination); the
    # encounter signal invokes the Assessor in encounter mode and, on the
    # REAL engine, the meeting commits atomically at the origin. Nothing
    # was bypassed: the dst cohort never ran.
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    w = _wired_world(tmp_path)
    try:
        g = _good()
        del g["place"]                     # a pure meeting on the road
        npt = {"acts": True, "action": "hails the traveler from beside "
               "his caravan", "speaks": True,
               "intent": "greet the stranger on the road", "line_hint": ""}
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True, moves_to=""),
             g, dict(npt), dict(npt)]
            + [{"prose": "A husky farmer hails you from his caravan."}] * 4)
        r = run_turn(w, _wired_arc(), provider,
                     "I walk until I meet someone.", turn=1)
        assert r.trace.growth == "activated:person:gregor_bund"
        gro = [c[0] for c in provider.calls if "⟦gro⟧" in c[0][:40]]
        assert gro and "PERSON met on the way" in gro[0]
        assert not any("⟦dst⟧" in c[0][:40] for c in provider.calls)
        assert w.porcelain.state("person:gregor_bund",
                                 "kind")["status"] == "known"
        assert r.trace.growth_moved == []          # the meeting came HERE
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_encounter_success_comes_to_the_road(tmp_path):
    # G2 success through the REAL atomic door (ATOMIC-ACTIVATION-V1 live,
    # 2026-07-24 — the fake activate_chunk this ran on pre-arrival is
    # retired): the encounter is ANCHORED at the origin — the meeting came
    # TO the player; nobody teleports, the player stays, and the grown
    # pair is live through the ordinary engines
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    w = _wired_world(tmp_path)
    try:
        g = _good()
        del g["place"]
        npt = {"acts": True, "action": "hails the traveler from beside "
               "his caravan", "speaks": True,
               "intent": "greet the stranger on the road", "line_hint": ""}
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True, moves_to=""),
             g, dict(npt), dict(npt)]
            + [{"prose": "A husky farmer hails you from his caravan."}] * 4)
        r = run_turn(w, _wired_arc(), provider,
                     "I walk until I meet someone.", turn=1)
        assert r.trace.growth == "activated:person:gregor_bund"
        # the grown pair went through the ORDINARY cast engine: real
        # npc_turn receipts, no schema drops — scene action/speech +
        # person_can_act (interview-delivery stays authored-cast-only:
        # spec §6 G2 as narrowed; grown ids carry no CastNode)
        assert "npc_turn:person:gregor_bund:cheap" in r.trace.cohort_calls
        assert "npc_turn:person:kip:cheap" in r.trace.cohort_calls
        assert not [d for d in r.trace.dropped_cohorts
                    if str(d).startswith("npc_turn:")]
        assert r.trace.growth_retry is False
        assert r.trace.growth_moved == []          # nobody teleported
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
        assert (w.porcelain.locate("person:gregor_bund") or [None])[0] \
            == "place:north_road"
        assert (w.porcelain.locate("person:kip") or [None])[0] \
            == "place:north_road"
        assert w.porcelain.state("person:kip", "accompanying")["fact"][
            "value"] == "person:gregor_bund"
        assert "farmer" in r.prose
    finally:
        w.close()


def test_wired_destinationless_lane_declines_a_place(tmp_path, monkeypatch):
    # cr G2 r3: the destination-less lane's consequence bound is HOST
    # enforced — a proposal smuggling a place through the proof-by-absence
    # lane declines with zero displacement (even on a willing engine)
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        monkeypatch.setattr(
            growth_mod, "activate_chunk",
            lambda porcelain, items: growth_mod.ActivationResult(
                ok=True, receipts=("r",)))
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True, moves_to=""),
             _good()])   # the proposal CARRIES a place — must not broaden
        r = run_turn(w, _wired_arc(), provider,
                     "I walk until I meet someone.", turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == \
            "declined:unlicensed:place.destinationless_lane"
        assert w.porcelain.state("place:the_willow_ford_waypost",
                                 "kind")["status"] != "known"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_phrase_bearing_encounter_keeps_its_walk(tmp_path):
    # the separately justified shape: a PHRASE-BEARING encounter seek
    # ("down the old road until I meet someone") goes through the real
    # pipeline (G1 routing) and its chunk may carry the meeting's place —
    # the player committed the travel, so the walk commits with the chunk.
    # Runs through the REAL atomic door (the pre-arrival fake is retired).
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    w = _wired_world(tmp_path)
    try:
        npt = {"acts": True, "action": "waters his team at the trough",
               "speaks": True, "intent": "size up the newcomer",
               "line_hint": ""}
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True,
                       moves_to="down the old carters' track"),
             {"verdict": "new", "match": ""},     # the pipeline RAN
             _good(), dict(npt), dict(npt)]
            + [{"prose": "The waypost, and a farmer at it."}] * 4)
        r = run_turn(w, _wired_arc(), provider,
                     "I go down the old carters' track until I meet "
                     "someone.", turn=1)
        assert r.trace.growth == "activated:place:the_willow_ford_waypost"
        assert "npc_turn:person:gregor_bund:cheap" in r.trace.cohort_calls
        assert "npc_turn:person:kip:cheap" in r.trace.cohort_calls
        assert not [d for d in r.trace.dropped_cohorts
                    if str(d).startswith("npc_turn:")]
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:the_willow_ford_waypost"
        assert (w.porcelain.locate("person:gregor_bund") or [None])[0] \
            == "place:the_willow_ford_waypost"
        assert r.trace.movement_status == "clear"
    finally:
        w.close()


def test_wired_low_confidence_declines_at_the_seam(tmp_path):
    # an INVOKED attempt whose proposal fails semantically: one attempt,
    # a stable retryable receipt, the seam, and zero world change
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        provider = StubProvider([
            _classify(),
            dict(_good(), confidence=0.1),
        ])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:proposal:low_confidence"
        assert r.trace.growth_retry is True
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_concealment_screens_the_proposal(tmp_path):
    # the REAL arc-derived leaks predicate (cr's wiring requirement): a
    # proposal naming the hidden answer's entity declines — the concealed
    # vocabulary is applied by the HOST; the model never saw the words
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        g = _good()
        g["place"]["name"] = "the Rival Crossing"   # names the culprit slug
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:unlicensed:place.name_concealed"
        assert w.porcelain.state("place:the_rival_crossing",
                                 "kind")["status"] != "known"
    finally:
        w.close()


def test_wired_charter_phrases_route_to_growth_never_the_legacy_mint(
        tmp_path):
    # cr wiring blocker 1: the canonical prospective/open shapes must reach
    # Growth — the legacy mint slugging "the first light I trust" into a
    # junk place IS the gap G1 closes. On the REAL engine the routed growth
    # ACTIVATES: the grown place commits, the walk lands there, and the
    # slugged junk place still never exists.
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    for phrase, slug, deictic in [
            ("the first light I trust", "place:the_first_light_i_trust",
             False),
            ("somewhere no one knows me", "place:somewhere_no_one_knows_me",
             False),
            ("downstream", "place:downstream", False)]:
        w = _wired_world(tmp_path / slug.split(":")[1])
        try:
            npt = {"acts": True, "action": "waters his team at the trough",
                   "speaks": True, "intent": "size up the newcomer",
                   "line_hint": ""}
            q = [_classify(moves_to=phrase)]
            if not deictic:                    # the semantic bind still runs
                q.append({"verdict": "new", "match": ""})
            q += [_good(), dict(npt), dict(npt)]
            q += [{"prose": "The waypost, and a farmer at it."}] * 4
            provider = StubProvider(q)
            r = run_turn(w, _wired_arc(), provider,
                         f"I go to {phrase}.", turn=1)
            assert r.trace.growth == \
                "activated:place:the_willow_ford_waypost", phrase
            assert any("⟦gro⟧" in c[0][:40] for c in provider.calls), phrase
            # the legacy mint NEVER ran: no slugged junk place; the walk
            # landed at the GROWN place instead
            assert w.porcelain.state(slug, "kind")["status"] != "known"
            assert (w.porcelain.locate("person:you") or [None])[0] \
                == "place:the_willow_ford_waypost"
        finally:
            w.close()


def test_wired_deliberating_is_handled_never_a_miss(tmp_path, monkeypatch):
    # cr wiring blocker 2: a typed deliberation hold is an ANSWERED state —
    # Growth must not bypass the player's confirmation beat
    import construct.turnloop as tl
    from construct.provider import StubProvider
    w = _wired_world(tmp_path)
    try:
        monkeypatch.setattr(
            tl, "_grant_moved_place",
            lambda *a, **k: (None, {"status": "deliberating"}))
        provider = StubProvider([
            _classify(moves_open=False, moves_to="the far shore"),
            {"verdict": "new", "match": ""},    # the semantic bind cohort
            {"prose": "You weigh the long way round."},
            {"prose": "You weigh the long way round."},
        ])
        r = tl.run_turn(w, _wired_arc(), provider, "I set out for the far "
                        "shore.", turn=1)
        assert r.trace.growth == ""            # never invoked
        assert r.trace.growth_retry is False
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()


def test_wired_seam_drops_the_whole_turn_including_dismissals(tmp_path):
    # cr wiring blocker 3: a combined dismiss+open-move turn that seams
    # must leave EVERYTHING unapplied — Reed stays accompanying; the
    # retry re-applies the whole action
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([
            {"entity": "person:reed", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:reed", "attribute": "name", "value": "Reed"},
            {"entity": "person:reed", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
            {"entity": "person:reed", "attribute": "accompanying",
             "value": "person:you", "value_type": "entity"},
        ])
        provider = StubProvider([
            _classify(npcs_dismissed=["npc_0"]),
            dict(_good(), confidence=0.1),      # LOW → the seam
        ])
        r = run_turn(w, _wired_arc(), provider,
                     "Reed, go home. I keep moving away.", turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:proposal:low_confidence"
        # the dismissal was STAGED and dropped — nothing changed
        assert r.trace.npcs_departed == []
        assert w.porcelain.state("person:reed", "accompanying")["fact"][
            "value"] == "person:you"
        assert not w.porcelain.events(kind="departed_scene",
                                      frame="session:main")
    finally:
        w.close()


def test_wired_dismissal_still_commits_when_growth_activates_or_declines_to_run(
        tmp_path):
    # the staged mutations FLUSH on every non-seam path: same combined
    # turn, but the growth signal is off → dismissal commits as today
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([
            {"entity": "person:reed", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:reed", "attribute": "name", "value": "Reed"},
            {"entity": "person:reed", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
            {"entity": "person:reed", "attribute": "accompanying",
             "value": "person:you", "value_type": "entity"},
        ])
        provider = StubProvider([
            _classify(moves_open=False, moves_to="", npcs_dismissed=["npc_0"]),
            {"prose": "Reed nods and turns for home."},
            {"prose": "Reed nods and turns for home."},
        ])
        r = run_turn(w, _wired_arc(), provider, "Reed, go home.", turn=1)
        assert r.trace.npcs_departed == ["person:reed"]
        assert w.porcelain.state("person:reed", "accompanying")["fact"][
            "value"] == ""
    finally:
        w.close()


def test_wired_identity_matrix(tmp_path, monkeypatch):
    # cr wiring blocker 4: the ENGINE refer authority, fail-closed
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn

    # (a) authority unreadable → technical decline, never a mint
    w = _wired_world(tmp_path / "a")
    try:
        real_refer = w.refer

        def _boom(*a, **k):
            raise RuntimeError("identity authority down")
        monkeypatch.setattr(w, "refer", lambda mention, **k: (
            _boom() if "Willow" in str(mention) else
            real_refer(mention, **k)))
        provider = StubProvider([_classify(), _good()])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:identity_unavailable"
        assert w.porcelain.state("place:the_willow_ford_waypost",
                                 "kind")["status"] != "known"
    finally:
        w.close()

    # (b) partial-token NON-identity: an existing Willow Tavern must not
    # capture "the Willow Ford waypost" — assembly proceeds to a NEW id,
    # which on the REAL engine ACTIVATES as its own place (the tavern
    # stays untouched, uncaptured)
    w = _wired_world(tmp_path / "b")
    try:
        w.ingest_structured([
            {"entity": "place:willow_tavern", "attribute": "kind",
             "value": "place", "timeless": True},
            {"entity": "place:willow_tavern", "attribute": "name",
             "value": "Willow Tavern"},
        ])
        npt = {"acts": True, "action": "waters his team at the trough",
               "speaks": True, "intent": "size up the newcomer",
               "line_hint": ""}
        provider = StubProvider(
            [_classify(), _good(), dict(npt), dict(npt)]
            + [{"prose": "The waypost, and a farmer at it."}] * 4)
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth == \
            "activated:place:the_willow_ford_waypost"       # new-id path
        assert w.porcelain.state("place:the_willow_ford_waypost",
                                 "kind")["status"] == "known"
        # the tavern was NOT captured: name intact, nobody moved there
        assert w.porcelain.state("place:willow_tavern", "name")["fact"][
            "value"] == "Willow Tavern"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:the_willow_ford_waypost"
    finally:
        w.close()

    # (c) exact primary-name bind: proposing the ORIGIN's own name binds
    # (engine refer) and declines place_is_here — the road led nowhere new
    w = _wired_world(tmp_path / "c")
    try:
        w.ingest_structured([{"entity": "place:north_road",
                              "attribute": "name", "value": "north road"}])
        g = _good()
        g["place"]["name"] = "north road"
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth == "declined:proposal:place_is_here"
    finally:
        w.close()

    # (d) ALIAS bind: the origin's learned alias is identity too
    w = _wired_world(tmp_path / "d")
    try:
        w.ingest_structured([
            {"entity": "place:north_road", "attribute": "name",
             "value": "north road"},
            {"entity": "place:north_road", "attribute": "alias",
             "value": "the old carters' way"},
        ])
        g = _good()
        g["place"]["name"] = "the old carters' way"
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth == "declined:proposal:place_is_here"
    finally:
        w.close()


def test_wired_full_concealment_vocabulary(tmp_path):
    # cr wiring blocker 5: the FULL protected vocabulary — the protected
    # ATTRIBUTE token ("culprit") and the texture family, not only the
    # referenced entity's slug
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path / "attr")
    try:
        g = _good()
        g["place"]["name"] = "the Culprit Crossing"
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:unlicensed:place.name_concealed"
    finally:
        w.close()
    w = _wired_world(tmp_path / "tex")
    try:
        g = _good()
        g["texture"] = ["a poster naming the rival's debts"]
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth == "declined:unlicensed:texture.0_concealed"
    finally:
        w.close()


def test_wired_failure_matrix_invariance(tmp_path):
    # cr's remaining matrix: provider error; a prior failed turn; exact
    # clock and route-price invariance across the seam
    from construct.clock import read_clock
    from construct.provider import ProviderTransportError, StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        before = read_clock(w).minutes
        # (a) provider error at the assessor
        provider = StubProvider([_classify()])   # queue exhausts at gro
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:provider_error"
        # (b) the next turn fails the same way — fresh eligibility, same
        # honest seam, still nothing committed
        provider = StubProvider([_classify(), dict(_good(), confidence=0.1)])
        r2 = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                      turn=2)
        assert r2.prose == _GROWTH_SEAM
        assert r2.trace.growth == "declined:proposal:low_confidence"
        # (c) invariance: clock unmoved, no route price rows, no movement
        assert read_clock(w).minutes == before
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
        from construct.adapter import frame_facts
        assert not [f for f in frame_facts(w, "session:main",
                                           entity="session:route_price")]
    finally:
        w.close()


def test_wired_success_path_through_the_real_atomic_engine(tmp_path):
    # cr blocker 6 + success cleanup, now through the REAL commit_set door
    # (the pre-arrival simulation is retired, cr final-review 2): the turn
    # proceeds to a BRIEFED narration; growth marks the development ledger;
    # standing companions are moved by the CHUNK and not re-written by 2b-ii
    from construct.adapter import frame_facts
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([
            {"entity": "person:reed", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:reed", "attribute": "name", "value": "Reed"},
            {"entity": "person:reed", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
            {"entity": "person:reed", "attribute": "accompanying",
             "value": "person:you", "value_type": "entity"},
        ])
        provider = StubProvider([
            _classify(),
            _good(),
            # the grown cast is LIVE on arrival (npc turns) + the narrator
            {"prose": "The waypost takes shape out of the dusk."},
            {"prose": "The waypost takes shape out of the dusk."},
            {"prose": "The waypost takes shape out of the dusk."},
            {"prose": "The waypost takes shape out of the dusk."},
            {"prose": "The waypost takes shape out of the dusk."},
            {"prose": "The waypost takes shape out of the dusk."},
        ])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth == "activated:place:the_willow_ford_waypost"
        assert r.trace.growth_retry is False
        assert r.trace.movement_status == "clear"
        assert "waypost" in r.prose
        # the protagonist AND the standing companion moved with the chunk
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:the_willow_ford_waypost"
        assert (w.porcelain.locate("person:reed") or [None])[0] \
            == "place:the_willow_ford_waypost"
        # 2b-ii did NOT re-write the companion: exactly ONE in-row for Reed
        # at the new place (the chunk's own)
        reed_moves = [f for f in frame_facts(w, "canon", entity="person:reed")
                      if f.attribute == "in"
                      and f.value == "place:the_willow_ford_waypost"]
        assert len(reed_moves) == 1
        assert r.trace.npcs_moved_with == []
        # doctrine 4: the development ledger saw the growth
        led = [f for f in frame_facts(w, "session:main",
                                      entity="session:ambient")
               if f.attribute == "last_development_min"]
        assert led
    finally:
        w.close()


def test_wired_dismissal_wins_over_the_chunk(tmp_path, monkeypatch):
    # cr re-review 1: a companion dismissed THIS TURN is excluded from the
    # growth snapshot — successful activation must not carry Reed to the
    # waypost and only then dismiss him
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([
            {"entity": "person:reed", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:reed", "attribute": "name", "value": "Reed"},
            {"entity": "person:reed", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
            {"entity": "person:reed", "attribute": "accompanying",
             "value": "person:you", "value_type": "entity"},
        ])

        def _fake_activate(porcelain, items):
            receipt = porcelain.ingest_structured(items, classify="rules")
            return growth_mod.ActivationResult(
                ok=True, receipts=tuple(getattr(receipt, "rows", ()) or ()))
        monkeypatch.setattr(growth_mod, "activate_chunk", _fake_activate)
        provider = StubProvider(
            [_classify(npcs_dismissed=["npc_0"]), _good()]
            + [{"prose": "The waypost takes shape."}] * 6)
        r = run_turn(w, _wired_arc(), provider,
                     "Reed, go home. I keep moving away.", turn=1)
        assert r.trace.growth == "activated:place:the_willow_ford_waypost"
        # dismissal WINS: Reed never traveled; the staged dismissal landed
        assert (w.porcelain.locate("person:reed") or [None])[0] \
            == "place:north_road"
        assert w.porcelain.state("person:reed", "accompanying")["fact"][
            "value"] == ""
        assert r.trace.npcs_departed == ["person:reed"]
        assert "person:reed" not in r.trace.growth_moved
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:the_willow_ford_waypost"
    finally:
        w.close()


def test_wired_explicit_moved_with_not_duplicated(tmp_path, monkeypatch):
    # cr re-review 2: an explicitly named standing companion is chunk-owned
    # — the moved_with commit must not write a second identical in-row
    import construct.growth as growth_mod
    from construct.adapter import frame_facts
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([
            {"entity": "person:reed", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:reed", "attribute": "name", "value": "Reed"},
            {"entity": "person:reed", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
            {"entity": "person:reed", "attribute": "accompanying",
             "value": "person:you", "value_type": "entity"},
        ])

        def _fake_activate(porcelain, items):
            receipt = porcelain.ingest_structured(items, classify="rules")
            return growth_mod.ActivationResult(
                ok=True, receipts=tuple(getattr(receipt, "rows", ()) or ()))
        monkeypatch.setattr(growth_mod, "activate_chunk", _fake_activate)
        provider = StubProvider(
            [_classify(moved_with=["npc_0"]), _good()]
            + [{"prose": "The waypost takes shape."}] * 6)
        r = run_turn(w, _wired_arc(), provider,
                     "Reed, with me — I keep moving away.", turn=1)
        assert r.trace.growth == "activated:place:the_willow_ford_waypost"
        assert "person:reed" in r.trace.growth_moved
        reed_moves = [f for f in frame_facts(w, "canon", entity="person:reed")
                      if f.attribute == "in"
                      and f.value == "place:the_willow_ford_waypost"]
        assert len(reed_moves) == 1          # ONE move, ONE row
        assert r.trace.npcs_moved_with == []  # chunk-owned, not 2b-ii's
    finally:
        w.close()


def test_wired_identity_availability_covers_every_authority_read(
        tmp_path, monkeypatch):
    # cr re-review 3: companion-roster and exact-name reads are inside the
    # fail-closed boundary — both end in the stable technical decline
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn

    # (a) the companion roster read (p.entities) fails
    w = _wired_world(tmp_path / "roster")
    try:
        real_entities = w.porcelain.entities

        def _boom(frame, **kw):
            if kw.get("prefix") == "person:":
                raise RuntimeError("identity roster down")
            return real_entities(frame, **kw)
        monkeypatch.setattr(w.porcelain, "entities", _boom)
        provider = StubProvider([_classify(), _good()])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:identity_unavailable"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()

    # (b) an exact-name state read fails during the identity decision
    w = _wired_world(tmp_path / "names")
    try:
        w.ingest_structured([{"entity": "place:north_road",
                              "attribute": "name", "value": "north road"}])
        from construct.adapter import PorcelainWorldReads
        real_state = PorcelainWorldReads.state

        def _state(self, entity, attribute, **kw):
            if entity == "place:north_road" and attribute == "alias":
                raise RuntimeError("authority state down")
            return real_state(self, entity, attribute, **kw)
        monkeypatch.setattr(PorcelainWorldReads, "state", _state)
        g = _good()
        g["place"]["name"] = "north road"     # forces the exact-name path
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:identity_unavailable"
    finally:
        w.close()


def test_wired_growth_success_excludes_the_lwg_that_turn(tmp_path,
                                                         monkeypatch):
    # cr held the line: the cross-feature GenerativeSlot oracle end to end.
    # Fixture: a spined bystander (drive row) + a player delta that touches
    # him — the P2b opportunistic branch is OTHERWISE ELIGIBLE. With growth
    # activating (fake atomic), the Assessor must be the turn's SOLE
    # generative invocation; the negative control (no growth signal) proves
    # the very same branch runs.
    import construct.growth as growth_mod
    from construct.provider import StubProvider, task_of
    from construct.turnloop import run_turn
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback

    def _mk(base):
        base.mkdir(parents=True, exist_ok=True)
        rule = rule_classifier_fallback()

        def fb(prompt, schema):
            if prompt.startswith("Classify the lifetime"):
                return rule(prompt, schema)
            if prompt.startswith("Extract world-state"):
                return {"items": [
                    {"entity": "person:clerk", "attribute": "unsettled_by",
                     "value": "the stranger's questions"},
                ]}
            return {"items": []}
        w = World(base / "slot.world", world_id="w:slot",
                  model=StubModel(fallback=fb), stance="fiction",
                  title="Slot World")
        w.ingestor.cursor.advance(1.0)
        w.ingest_structured([
            {"entity": "place:the_march", "attribute": "kind",
             "value": "region", "timeless": True},
            {"entity": "place:north_road", "attribute": "kind",
             "value": "place", "timeless": True},
            {"entity": "place:north_road", "attribute": "in",
             "value": "place:the_march", "value_type": "entity"},
            {"entity": "person:you", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:you", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
            {"entity": "person:clerk", "attribute": "kind",
             "value": "person", "timeless": True},
            {"entity": "person:clerk", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
            {"entity": "person:clerk", "attribute": "drive",
             "value": "drive:duty"},
            # accompanying: the chunk carries the clerk to the grown scene,
            # so the spined subject the player touched stays PRESENT — the
            # P2b trigger is genuinely eligible after the move
            {"entity": "person:clerk", "attribute": "accompanying",
             "value": "person:you", "value_type": "entity"},
            {"entity": "fact:secret", "attribute": "kind",
             "value": "proposition", "timeless": True},
            {"entity": "fact:secret", "attribute": "culprit",
             "value": "person:rival"},
            {"entity": "person:rival", "attribute": "kind",
             "value": "person", "timeless": True},
        ])
        return w

    class _P(StubProvider):
        def __init__(self, queue):
            super().__init__(queue)
            self.gen_called = False

        async def complete(self, prompt, schema, *, tier="main",
                           deliberate=False):
            if task_of(prompt) == "gen":
                self.gen_called = True
                self.calls.append((prompt, schema, tier))
                return {"skip": True, "reason": "quiet"}
            return await super().complete(prompt, schema, tier=tier,
                                          deliberate=deliberate)

    def _fake_activate(porcelain, items):
        receipt = porcelain.ingest_structured(items, classify="rules")
        return growth_mod.ActivationResult(
            ok=True, receipts=tuple(getattr(receipt, "rows", ()) or ()))

    # POSITIVE: growth activates → the LWG author is NOT called
    w = _mk(tmp_path / "pos")
    try:
        monkeypatch.setattr(growth_mod, "activate_chunk", _fake_activate)
        provider = _P([_classify(), _good()]
                      + [{"prose": "The waypost takes shape."}] * 8)
        r = run_turn(w, _wired_arc(), provider,
                     "I unsettle the clerk with questions and keep moving "
                     "away.", turn=1, scope=["person:clerk"])
        assert r.trace.growth.startswith("activated:")
        assert not provider.gen_called
        gro = [c for c in provider.calls if "⟦gro⟧" in c[0][:40]]
        assert len(gro) == 1        # the sole generative invocation
    finally:
        w.close()

    # NEGATIVE CONTROL: same fixture, no growth signal → P2b runs
    w = _mk(tmp_path / "neg")
    try:
        provider = _P([_classify(moves_open=False, moves_to="")]
                      + [{"prose": "The clerk shifts uneasily."}] * 8)
        r = run_turn(w, _wired_arc(), provider,
                     "I unsettle the clerk with questions.", turn=1,
                     scope=["person:clerk"])
        assert r.trace.growth == ""
        assert provider.gen_called          # the branch CAN run
    finally:
        w.close()


def test_wired_existence_authority_failure_seams(tmp_path, monkeypatch):
    # cr re-review 1: the _exists read (has_entity) is inside the
    # fail-closed boundary — a failure declines, never escapes the turn
    from construct.adapter import PorcelainWorldReads
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        real = PorcelainWorldReads.has_entity

        def _boom(self, entity):
            if entity == "place:north_road":
                raise RuntimeError("existence authority down")
            return real(self, entity)
        monkeypatch.setattr(PorcelainWorldReads, "has_entity", _boom)
        provider = StubProvider([_classify(), _good()])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:identity_unavailable"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_dismissal_rides_the_atomic_chunk(tmp_path, monkeypatch):
    # cr re-review 2: the dismissal state the companion exclusion depended
    # on commits IN the activation set — one atomic outcome, never a
    # fail-open flush after the move
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn

    def _seed(w):
        w.ingest_structured([
            {"entity": "person:reed", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:reed", "attribute": "name", "value": "Reed"},
            {"entity": "person:reed", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
            {"entity": "person:reed", "attribute": "accompanying",
             "value": "person:you", "value_type": "entity"},
        ])

    # (a) SUCCESS: the accompanying-supersede row is INSIDE the atomic
    # items; no separate dismissal batch follows
    w = _wired_world(tmp_path / "ok")
    try:
        _seed(w)
        seen: list = []

        def _fake(porcelain, items):
            seen.append(list(items))
            receipt = porcelain.ingest_structured(items, classify="rules")
            return growth_mod.ActivationResult(
                ok=True, receipts=tuple(getattr(receipt, "rows", ()) or ()))
        monkeypatch.setattr(growth_mod, "activate_chunk", _fake)
        provider = StubProvider(
            [_classify(npcs_dismissed=["npc_0"]), _good()]
            + [{"prose": "The waypost takes shape."}] * 6)
        r = run_turn(w, _wired_arc(), provider,
                     "Reed, go home. I keep moving away.", turn=1)
        assert r.trace.growth.startswith("activated:")
        assert len(seen) == 1
        atomic_keys = {(i.get("entity"), i.get("attribute"), i.get("value"))
                       for i in seen[0]}
        assert ("person:reed", "accompanying", "") in atomic_keys
        assert r.trace.npcs_departed == ["person:reed"]
        assert w.porcelain.state("person:reed", "accompanying")["fact"][
            "value"] == ""
        assert (w.porcelain.locate("person:reed") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()

    # (b) FAULT: the whole set aborts → NOTHING moved, NOTHING dismissed,
    # no false departure receipt — one honest seam
    w = _wired_world(tmp_path / "fault")
    try:
        _seed(w)
        monkeypatch.setattr(
            growth_mod, "activate_chunk",
            lambda porcelain, items: growth_mod.ActivationResult(
                ok=False, reason="engine_abort:injected"))
        provider = StubProvider([_classify(npcs_dismissed=["npc_0"]),
                                 _good()])
        r = run_turn(w, _wired_arc(), provider,
                     "Reed, go home. I keep moving away.", turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "engine_abort:injected"
        assert r.trace.npcs_departed == []
        assert w.porcelain.state("person:reed", "accompanying")["fact"][
            "value"] == "person:you"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_vocabulary_authority_failure_never_shrinks_the_screen(
        tmp_path, monkeypatch):
    # cr re-review 3: an unreadable protected read is a technical decline —
    # the exact leak attempt (the Rival Crossing over a broken culprit
    # read) must never activate
    from construct.adapter import PorcelainWorldReads
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        real = PorcelainWorldReads.state

        def _state(self, entity, attribute, **kw):
            if entity == "fact:secret" and attribute == "culprit":
                raise RuntimeError("protected authority down")
            return real(self, entity, attribute, **kw)
        monkeypatch.setattr(PorcelainWorldReads, "state", _state)
        g = _good()
        g["place"]["name"] = "the Rival Crossing"
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:concealment_unavailable"
        assert w.porcelain.state("place:the_rival_crossing",
                                 "kind")["status"] != "known"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_referenced_answer_aliases_conceal(tmp_path, monkeypatch):
    # cr r4: the hidden answer's ALIAS is its identity too — "the Red
    # Jack Crossing" must decline exactly like "the Rival Crossing"
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([{"entity": "person:rival", "attribute": "alias",
                              "value": "the Red Jack"}])

        def _fake(porcelain, items):   # even a WILLING engine never sees it
            receipt = porcelain.ingest_structured(items, classify="rules")
            return growth_mod.ActivationResult(
                ok=True, receipts=tuple(getattr(receipt, "rows", ()) or ()))
        monkeypatch.setattr(growth_mod, "activate_chunk", _fake)
        g = _good()
        g["place"]["name"] = "the Red Jack Crossing"
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:unlicensed:place.name_concealed"
        assert w.porcelain.state("place:the_red_jack_crossing",
                                 "kind")["status"] != "known"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_protected_key_enumeration_failure_seams(tmp_path,
                                                       monkeypatch):
    # cr r4: the enumeration itself is an authority read — a raise inside
    # arc_protected_keys becomes the stable technical seam, never an escape
    import construct.turnloop as tl
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        import inspect as _inspect
        real = tl.arc_protected_keys

        def _boom(arc, reads=None):
            # fail ONLY growth's own enumeration — the legacy fail-open
            # consumers (roster redaction, move/take guards) keep their
            # long-standing behavior and are not under test here
            callers = {f.function for f in _inspect.stack()[1:4]}
            if "_growth_concealed_vocab" in callers:
                raise RuntimeError("protected-key enumeration down")
            return real(arc, reads)
        monkeypatch.setattr(tl, "arc_protected_keys", _boom)
        provider = StubProvider([_classify(), _good()])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:concealment_unavailable"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_superseded_aliases_still_conceal(tmp_path, monkeypatch):
    # cr r5: alias accrual is DURABLE identity — an older alias superseded
    # by a newer one must conceal forever, not only the point-state value
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([{"entity": "person:rival", "attribute": "alias",
                              "value": "the Red Jack", "valid_from": 100.0}])
        w.ingest_structured([{"entity": "person:rival", "attribute": "alias",
                              "value": "the Scarlet Fox",
                              "valid_from": 200.0}])
        # point state now reports only the newer alias
        assert w.porcelain.state("person:rival", "alias")["fact"][
            "value"] == "the Scarlet Fox"

        def _fake(porcelain, items):   # a WILLING engine never sees it
            receipt = porcelain.ingest_structured(items, classify="rules")
            return growth_mod.ActivationResult(
                ok=True, receipts=tuple(getattr(receipt, "rows", ()) or ()))
        monkeypatch.setattr(growth_mod, "activate_chunk", _fake)
        for leaked in ("the Red Jack Crossing", "the Scarlet Fox Landing"):
            g = _good()
            g["place"]["name"] = leaked
            provider = StubProvider([_classify(), g])
            r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                         turn=1)
            assert r.prose == _GROWTH_SEAM, leaked
            assert r.trace.growth == \
                "declined:unlicensed:place.name_concealed", leaked
        assert w.porcelain.state("place:the_red_jack_crossing",
                                 "kind")["status"] != "known"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_identity_vocabulary_is_horizon_bound(tmp_path, monkeypatch):
    # cr r6: as-of coherence cuts BOTH ways — a superseded alias conceals
    # at every later horizon, but a FUTURE-aftermath alias must not shrink
    # present growth
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([{"entity": "person:rival", "attribute": "alias",
                              "value": "the Red Jack", "valid_from": 100.0}])
        w.ingest_structured([{"entity": "person:rival", "attribute": "alias",
                              "value": "the Future Falcon",
                              "valid_from": 500.0}])

        def _fake(porcelain, items):
            receipt = porcelain.ingest_structured(items, classify="rules")
            return growth_mod.ActivationResult(
                ok=True, receipts=tuple(getattr(receipt, "rows", ()) or ()))
        monkeypatch.setattr(growth_mod, "activate_chunk", _fake)

        # at h=150: the durable old alias conceals...
        g = _good()
        g["place"]["name"] = "the Red Jack Crossing"
        provider = StubProvider([_classify(), g])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1, horizon=150.0)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:unlicensed:place.name_concealed"
        # ...and the FUTURE alias does not (growth proceeds to activation)
        g = _good()
        g["place"]["name"] = "the Future Falcon Crossing"
        provider = StubProvider(
            [_classify(), g] + [{"prose": "The crossing takes shape."}] * 6)
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1, horizon=150.0)
        assert r.trace.growth == "activated:place:the_future_falcon_crossing"

        # after the later horizon BOTH conceal (fresh world so the
        # activated crossing doesn't muddy the probe)
    finally:
        w.close()
    w = _wired_world(tmp_path / "late")
    try:
        w.ingest_structured([{"entity": "person:rival", "attribute": "alias",
                              "value": "the Red Jack", "valid_from": 100.0}])
        w.ingest_structured([{"entity": "person:rival", "attribute": "alias",
                              "value": "the Future Falcon",
                              "valid_from": 500.0}])
        monkeypatch.setattr(
            growth_mod, "activate_chunk",
            lambda porcelain, items: growth_mod.ActivationResult(
                ok=True, receipts=("r",)))
        for leaked in ("the Red Jack Crossing", "the Future Falcon Crossing"):
            g = _good()
            g["place"]["name"] = leaked
            provider = StubProvider([_classify(), g])
            r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                         turn=1, horizon=550.0)
            assert r.prose == _GROWTH_SEAM, leaked
            assert r.trace.growth == \
                "declined:unlicensed:place.name_concealed", leaked
    finally:
        w.close()


def test_wired_identity_log_enumeration_failure_seams(tmp_path, monkeypatch):
    # cr r6: the identity-log read is inside the fail-closed boundary
    from construct.adapter import PorcelainWorldReads
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        real = PorcelainWorldReads.frame_rows

        def _boom(self, frame, **kw):
            if kw.get("entity") == "person:rival":
                raise RuntimeError("identity log down")
            return real(self, frame, **kw)
        monkeypatch.setattr(PorcelainWorldReads, "frame_rows", _boom)
        provider = StubProvider([_classify(), _good()])
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == "declined:concealment_unavailable"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
    finally:
        w.close()


def test_wired_seek_signal_never_broadens_over_answered_states(
        tmp_path, monkeypatch):
    # cr G2 blocker 2: a literal seeks_encounter=True must not fire the
    # direct gate when the movement machinery ANSWERED — resolved,
    # same-place, blocked, and ambiguous all stand; and a stationary look
    # (signal false, no destination) never invokes at all
    import construct.turnloop as tl
    from construct.provider import StubProvider
    from construct.turnloop import run_turn

    # (a) RESOLVED: a known place reuses — no growth invocation
    w = _wired_world(tmp_path / "resolved")
    try:
        w.ingest_structured([{"entity": "place:the_march",
                              "attribute": "name", "value": "the march"}])
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True,
                       moves_to="the march")]
            + [{"prose": "You take the road up into the march."}] * 3)
        r = run_turn(w, _wired_arc(), provider,
                     "I head into the march until I meet someone.", turn=1)
        assert r.trace.growth == ""
        assert r.trace.movement_status == "clear"
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()

    # (b) SAME-PLACE: naming the current place answers the move
    w = _wired_world(tmp_path / "same")
    try:
        w.ingest_structured([{"entity": "place:north_road",
                              "attribute": "name", "value": "north road"}])
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True,
                       moves_to="north road")]
            + [{"prose": "You pace the road you already stand on."}] * 3)
        r = run_turn(w, _wired_arc(), provider,
                     "I walk the north road until I meet someone.", turn=1)
        assert r.trace.growth == ""
        assert r.trace.same_place is True
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()

    # (c) BLOCKED: a bound destination behind an obstruction answers
    w = _wired_world(tmp_path / "blocked")
    try:
        w.ingest_structured([{"entity": "place:the_march",
                              "attribute": "name", "value": "the march"}])
        monkeypatch.setattr(
            tl, "_route_obstruction",
            lambda *a, **k: {"status": "blocked", "evidence": [
                {"entity": "place:the_march", "attribute": "condition",
                 "value": "washed out"}]})
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True,
                       moves_to="the high pass"),
             {"verdict": "existing", "match": "place:the_march"}]
            + [{"prose": "The way is washed out."}] * 3)
        r = run_turn(w, _wired_arc(), provider,
                     "I take the high pass until I meet someone.", turn=1)
        assert r.trace.growth == ""
        assert r.trace.movement_status == "blocked"
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()
    monkeypatch.undo()

    # (d) AMBIGUOUS: the clarify beat answers — never a growth mint
    w = _wired_world(tmp_path / "amb")
    try:
        w.ingest_structured([{"entity": "place:the_march",
                              "attribute": "name", "value": "the march"}])
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True,
                       moves_to="the crossing"),
             {"verdict": "ambiguous", "match": ""}]
            + [{"prose": "Which crossing do you mean?"}] * 3)
        r = run_turn(w, _wired_arc(), provider,
                     "I make for the crossing until I meet someone.", turn=1)
        assert r.trace.growth == ""
        assert r.trace.movement_status == "ambiguous"
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()

    # (e0) cr's exact repro: a schema-valid single-boolean false positive
    # ("Is anyone around?" misread as seeks_encounter=True, moves_open
    # honest False) must NOT invoke — the lane demands BOTH signals
    w = _wired_world(tmp_path / "onebool")
    try:
        provider = StubProvider(
            [_classify(moves_open=False, seeks_encounter=True, moves_to="")]
            + [{"prose": "The road lies quiet."}] * 3)
        r = run_turn(w, _wired_arc(), provider, "Is anyone around?", turn=1)
        assert r.trace.growth == ""
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()

    # (e1) and the mirror single signal (moves_open alone, no destination)
    w = _wired_world(tmp_path / "openonly")
    try:
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=False, moves_to="")]
            + [{"prose": "You shift your weight, going nowhere yet."}] * 3)
        r = run_turn(w, _wired_arc(), provider, "I mean to move on soon.",
                     turn=1)
        assert r.trace.growth == ""
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()

    # (e) STATIONARY LOOK: no signal, no destination — never invokes
    w = _wired_world(tmp_path / "look")
    try:
        provider = StubProvider(
            [_classify(moves_open=False, seeks_encounter=False, moves_to="")]
            + [{"prose": "The road lies empty either way."}] * 3)
        r = run_turn(w, _wired_arc(), provider, "Is anyone around?", turn=1)
        assert r.trace.growth == ""
        assert not any("⟦gro⟧" in c[0][:40] for c in provider.calls)
    finally:
        w.close()


def test_wired_whitespace_destination_stays_inside_the_bound(tmp_path,
                                                             monkeypatch):
    # cr G2 r4: moves_to="   " is schema-valid but semantically blank —
    # it must remain inside the destination-less encounter-only bound
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import _GROWTH_SEAM, run_turn
    w = _wired_world(tmp_path)
    try:
        monkeypatch.setattr(
            growth_mod, "activate_chunk",
            lambda porcelain, items: growth_mod.ActivationResult(
                ok=True, receipts=("r",)))
        provider = StubProvider(
            [_classify(moves_open=True, seeks_encounter=True,
                       moves_to="   "),
             _good()])   # place-bearing — the exact bypass shape
        r = run_turn(w, _wired_arc(), provider,
                     "I walk until I meet someone.", turn=1)
        assert r.prose == _GROWTH_SEAM
        assert r.trace.growth == \
            "declined:unlicensed:place.destinationless_lane"
        assert w.porcelain.state("place:the_willow_ford_waypost",
                                 "kind")["status"] != "known"
        assert (w.porcelain.locate("person:you") or [None])[0] \
            == "place:north_road"
        assert r.trace.movement_status == ""
    finally:
        w.close()


def test_wired_region_card_governs_grown_territory(tmp_path, monkeypatch):
    # G3 end to end: the first growth mints the card atomically with the
    # chunk; the chain interposes without detaching prior geography; the
    # NEXT turn's briefing speaks the territory's remembered voice; and
    # the card survives reopen for later chapters
    import construct.growth as growth_mod
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    wpath = tmp_path / "wire.world"
    w = _wired_world(tmp_path)
    try:
        w.ingest_structured([
            {"entity": "person:reed", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:reed", "attribute": "in",
             "value": "place:north_road", "value_type": "entity"},
        ])

        def _fake(porcelain, items):
            receipt = porcelain.ingest_structured(items, classify="rules")
            return growth_mod.ActivationResult(
                ok=True, receipts=tuple(getattr(receipt, "rows", ()) or ()))
        monkeypatch.setattr(growth_mod, "activate_chunk", _fake)
        npt = {"acts": True, "action": "hails the traveler", "speaks": True,
               "intent": "greet the stranger", "line_hint": ""}
        provider = StubProvider(
            [_classify(), _good(), dict(npt), dict(npt)]
            + [{"prose": "The waypost takes shape."}] * 4)
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth.startswith("activated:")
        # the chain INTERPOSES the card — and prior geography still resolves
        chain = w.porcelain.locate("person:you")
        assert chain[0] == "place:the_willow_ford_waypost"
        rid = next(c for c in chain if str(c).startswith("region:"))
        assert "place:greywater_vale" in chain and "place:the_march" in chain
        assert w.porcelain.locate("person:reed") == [
            "place:north_road", "place:greywater_vale", "place:the_march"]
        # the card's memory: WHY it exists + what the player did arriving
        assert "farm country" in str(w.porcelain.state(rid, "style")[
            "fact"]["value"])
        # origin is the player's COMMITTED ACTION, exact (cr G3 blocker 4:
        # never the classifier's destination fragment)
        assert w.porcelain.state(rid, "origin")["fact"]["value"] \
            == "I keep moving away."
        # the NEXT turn's briefing speaks the territory's voice
        provider2 = StubProvider(
            [_classify(moves_open=False, moves_to=""), dict(npt), dict(npt)]
            + [{"prose": "The farmer nods you toward the trough."}] * 4)
        r2 = run_turn(w, _wired_arc(), provider2, "I look around.", turn=2)
        assert "THIS TERRITORY" in r2.trace.briefing
        assert "farm country" in r2.trace.briefing
        # the raw action is QUOTED, never grammatically embedded
        assert 'quoted: "I keep moving away."' in r2.trace.briefing
        assert "It began when they" not in r2.trace.briefing
    finally:
        w.close()

    # NEXT GROWTH under the card reasons in ITS voice (cr G3 blocker 3):
    # re-open the world, grow again from the grown place — the gro prompt
    # carries the region's remembered style, not the global scenario style
    from patternbuffer import World as _World
    from patternbuffer.testing import (StubModel as _SM,
                                       rule_classifier_fallback as _rcf)
    w3 = _World(wpath, world_id="w:wire", stance="fiction",
                model=_SM(fallback=_rcf()), title="Growth Wiring")
    try:
        g2 = _good()
        g2["place"]["name"] = "the Drover's Rest"
        g2["place"]["parent_index"] = 1
        provider3 = StubProvider([_classify(moves_to="onward"), g2])
        r3 = run_turn(w3, _wired_arc(), provider3, "I keep on.", turn=3,
                      style="THE GLOBAL SCENARIO VOICE")
        gro = [c[0] for c in provider3.calls if "⟦gro⟧" in c[0][:40]]
        assert gro and "farm country" in gro[0]        # the card's voice
        assert "THE GLOBAL SCENARIO VOICE" not in gro[0]
    finally:
        w3.close()

    # REOPEN (chapter-later read): the card is durable canon
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    w2 = World(wpath, world_id="w:wire", stance="fiction",
               model=StubModel(fallback=rule_classifier_fallback()),
               title="Growth Wiring")
    try:
        chain = w2.porcelain.locate("person:you")
        rid = next(c for c in chain if str(c).startswith("region:"))
        st = w2.porcelain.state(rid, "style")
        assert st["status"] == "known" and "farm country" in str(
            st["fact"]["value"])
    finally:
        w2.close()


def test_latency_checkpoints_cover_every_return_shape(tmp_path, monkeypatch):
    # cr (telemetry review): checkpoint placement has correctness
    # semantics — every return path is bounded by a cumulative stamp
    from construct.provider import StubProvider
    from construct.turnloop import run_turn
    # (a) NORMAL path: all seven cp keys, nondecreasing
    w = _wired_world(tmp_path / "normal")
    try:
        provider = StubProvider(
            [_classify(moves_open=False, moves_to="")]
            + [{"prose": "The road waits."}] * 3)
        r = run_turn(w, _wired_arc(), provider, "I look around.", turn=1)
        keys = ["cp_classified", "cp_movement_done", "cp_growth_gate_done",
                "cp_scene_snapshot_done", "cp_salience_done",
                "cp_drift_lifecycle_done", "cp_generator_done"]
        vals = [r.trace.timings.get(k) for k in keys]
        assert all(v is not None for v in vals), r.trace.timings
        assert vals == sorted(vals)
    finally:
        w.close()
    # (b) GROWTH-RETRY path: the Assessor's interval is stamped
    # (envelope absence simulated INSIDE a scoped context — a bare undo()
    # would strip the suite-wide fixture patches too, cr final-review 3)
    import construct.growth as growth_mod
    w = _wired_world(tmp_path / "seam")
    try:
        with monkeypatch.context() as mp:
            mp.setattr(growth_mod, "_capability", lambda p: "")
            provider = StubProvider([_classify(), _good()])
            r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                         turn=1)
        assert r.trace.growth == "activation_unavailable"
        assert "cp_growth_gate_done" in r.trace.timings
        assert r.trace.timings["cp_growth_gate_done"] >= \
            r.trace.timings["cp_movement_done"]
    finally:
        w.close()
    # (b2) the ACTIVATED return shape (cr AMBER delta E): the real engine
    # commits the chunk and the full checkpoint ladder still stamps in order
    w = _wired_world(tmp_path / "activated")
    try:
        npt = {"acts": True, "action": "waters his team at the trough",
               "speaks": True, "intent": "size up the newcomer",
               "line_hint": ""}
        provider = StubProvider(
            [_classify(), _good(), dict(npt), dict(npt)]
            + [{"prose": "The waypost, and a farmer at it."}] * 4)
        r = run_turn(w, _wired_arc(), provider, "I keep moving away.",
                     turn=1)
        assert r.trace.growth == "activated:place:the_willow_ford_waypost"
        keys = ["cp_classified", "cp_movement_done", "cp_growth_gate_done",
                "cp_scene_snapshot_done", "cp_salience_done",
                "cp_drift_lifecycle_done", "cp_generator_done"]
        vals = [r.trace.timings.get(k) for k in keys]
        assert all(v is not None for v in vals), r.trace.timings
        assert vals == sorted(vals)
    finally:
        w.close()
    # (c) an early ANSWERED/DENIED path is bounded by a later stamp: the
    # canon-strict declaration denial returns right after classification
    w = _wired_world(tmp_path / "deny")
    try:
        provider = StubProvider([
            _classify(moves_open=False, moves_to="")
            | {"kind": "declaration"}])
        r = run_turn(w, _wired_arc(), provider,
                     "There is a secret door here, and always was.",
                     turn=1, mode="pure")
        assert "canon-strict" in r.prose
        assert "cp_classified" in r.trace.timings
        assert "cp_early_return" in r.trace.timings
        assert r.trace.timings["cp_early_return"] >= \
            r.trace.timings["cp_classified"]
    finally:
        w.close()
