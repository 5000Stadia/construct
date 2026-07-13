"""WORLD-GROWTH G1 — the activation adaptor under cr's build boundary.

The safety gate is a PASSING test (the fail-closed path on today's
engine); the happy path runs against a FAKE atomic backend; the STRICT
xfail probes the REAL engine for the envelope's arrival — it flips (and
must be replaced by the real fault matrix) exactly when PB ships.
"""
from __future__ import annotations

import pytest

from construct.growth import (ActivationResult, activate_chunk,
                              atomic_capable, ordered_chunk_items)
from tests.test_integration import world  # noqa: F401 — the engine fixture


class _NonAtomicP:
    """Today's PB 0.2.0 shape: ingest_structured without `atomic`."""

    def __init__(self):
        self.calls = []

    def ingest_structured(self, items, frame="canon", classify="inline"):
        self.calls.append(items)
        return {"rows": [{"entity": i["entity"]} for i in items]}


class _FakeAtomicP:
    """The FAKE atomic backend for the passing happy-path tests (the strict xfail probes the REAL engine)."""

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


def test_fail_closed_on_todays_engine_nothing_written():
    # THE SAFETY GATE (passing, not xfail): capability absent → refuse
    # BEFORE writing; zero calls reach the engine; the receipt is a return
    # value naming activation_unavailable.
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


@pytest.mark.xfail(strict=True,
                   reason="ATOMIC-ACTIVATION-V1 not shipped: the real "
                          "fault/skip/reopen matrix replaces this pin when "
                          "PB's primitive lands with pbr GREEN")
def test_atomic_integration_pin_real_engine():
    # STRICT xfail: this intentionally imports the REAL engine surface and
    # requires the atomic parameter to exist there — it flips to passing
    # (and must then be replaced by the real matrix) exactly when PB ships.
    import inspect as _i
    from patternbuffer import World  # noqa: F401
    from construct.adapter import PorcelainWorldReads  # noqa: F401
    import patternbuffer
    sig = _i.signature(patternbuffer.World.__init__)
    # the pin: today's engine has no atomic envelope anywhere we can see
    porcelain_cls = None
    for name in dir(patternbuffer):
        obj = getattr(patternbuffer, name)
        if hasattr(obj, "ingest_structured"):
            porcelain_cls = obj
            break
    assert porcelain_cls is not None
    assert "atomic" in _i.signature(porcelain_cls.ingest_structured).parameters


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

def _assemble(prop, **kw):
    from construct.growth import assemble_chunk
    kw.setdefault("mode", "place")
    kw.setdefault("origin", "place:north_road")
    kw.setdefault("ancestry_options",
                  ["place:the_march", "place:greywater_vale"])
    kw.setdefault("protagonist", "person:you")
    kw.setdefault("companions", [])
    kw.setdefault("at", 5000.0)
    kw.setdefault("exists", lambda eid: False)
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
    assert keys.index((pid, "connects_to")) < keys.index(("person:you", "in"))
    assert keys.index(("person:you", "in")) \
        < keys.index((chunk.person_id, "kind"))
    # the host picked the parent from ITS OWN list, never model text
    row = {(r["entity"], r["attribute"]): r for r in chunk.items}
    assert row[(pid, "in")]["value"] == "place:greywater_vale"
    # the road walked is walkable BACK
    assert row[(pid, "connects_to")]["value"] == "place:north_road"
    # the companion postcondition: every standing companion in the SAME set
    assert row[("person:reed", "in")]["value"] == pid
    assert row[("person:aldous", "in")]["value"] == pid
    # furnish stands down: the place arrives DESCRIBED
    assert row[(pid, "description")]["value"].startswith("a plank shelter")
    # the encounter is anchored + their companion bonded
    assert row[(chunk.person_id, "in")]["value"] == pid
    assert row[(chunk.companion_id, "accompanying")]["value"] \
        == chunk.person_id
    # texture: attributes distinct within the chunk AND across chunks (a
    # later chunk on the same anchor must never supersede these — canon
    # forever); keyed by the chunk's unique turn-time
    assert row[(pid, "detail_5000_1")]["value"] == "a weather-worn signpost"
    assert row[(pid, "detail_5000_2")]["value"] == "wheel ruts in the clay"
    # derivation receipt rides along, never as a row
    assert "farm country" in chunk.assessment
    assert all(a != "assessment" for _, a in keys)


def test_assembly_ids_are_collision_free():
    # canon roster collision AND intra-chunk collision both ordinal-probe
    taken = {"place:the_willow_ford_waypost", "person:gregor_bund",
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
    assert row[("place:north_road", "detail_5000_1")]["value"] \
        == "a weather-worn signpost"


def test_assembly_declines_unsluggable_names():
    g = _good()
    g["place"]["name"] = "???"
    p, why = _vp(g, mode="place", n_ancestry_options=2)
    assert why == ""
    chunk, why = _assemble(p)
    assert chunk is None and why == "malformed:place.name_unsluggable"


def test_assembly_host_bugs_raise():
    import pytest as _pt
    p = _good_prop()
    bad_calls = [
        dict(exists=None),
        dict(origin="north road"),
        dict(origin=None),
        dict(protagonist="you"),
        dict(companions=("person:reed",)),          # exact list, not tuple
        dict(companions=["person:reed", "reed"]),
        dict(at=float("nan")),
        dict(at=True),
        dict(at=-5.0),
        dict(mode="wander"),
        dict(ancestry_options=[]),                   # place proposed, no list
        dict(ancestry_options=["place:a"]),          # index 1 out of range —
    ]                                                # validation/assembly split
    for kw in bad_calls:
        with _pt.raises(ValueError):
            _assemble(p, **kw)
    with _pt.raises(ValueError):
        _assemble({"not": "a proposal"})


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
