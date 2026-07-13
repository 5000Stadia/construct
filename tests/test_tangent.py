"""WORLD-GROWTH G-A piece A — the pending-adoption state machine."""

import json

import pytest

from construct.tangent import (EXPIRY_TURNS, PENDING, Pending, cancel_rows,
                               declaration, may_confirm, pending_rows,
                               read_pending)


def test_declaration_reads_fail_closed():
    ok = {"declares_tangent_aim": True,
          "tangent_aim": "  build a life  aboard the Gullwing "}
    assert declaration(ok, kind="action") == \
        "build a life aboard the Gullwing"
    # every non-affirmed shape reads NO declaration — including a
    # non-dict verdict (cr piece-A blocker 3)
    assert declaration(None, kind="action") == ""
    assert declaration("verdict", kind="action") == ""
    assert declaration(ok, kind="question") == ""
    assert declaration({}, kind="action") == ""
    assert declaration({"declares_tangent_aim": "true",
                        "tangent_aim": "x"}, kind="action") == ""
    assert declaration({"declares_tangent_aim": 1,
                        "tangent_aim": "x"}, kind="action") == ""
    assert declaration({"declares_tangent_aim": True,
                        "tangent_aim": ""}, kind="action") == ""
    assert declaration({"declares_tangent_aim": True,
                        "tangent_aim": "   "}, kind="action") == ""
    assert declaration({"declares_tangent_aim": True,
                        "tangent_aim": None}, kind="action") == ""
    assert declaration({"declares_tangent_aim": True,
                        "tangent_aim": ["x"]}, kind="action") == ""
    assert declaration({"declares_tangent_aim": True,
                        "tangent_aim": "y" * 301}, kind="action") == ""


def test_pending_record_is_one_coherent_write():
    rows = pending_rows("  a life   aboard ", turn=7,
                        action="I sign on with the Gullwing.", at=5007.0)
    # ONE row carries the WHOLE candidate — hybrids are unrepresentable
    assert len(rows) == 1
    row = rows[0]
    assert (row["entity"], row["attribute"]) == (PENDING, "record")
    assert row["valid_from"] == 5007.0
    rec = json.loads(row["value"])
    assert rec == {"aim": "a life aboard", "declared_turn": 7,
                   "source_action": "I sign on with the Gullwing."}
    # host-bug raises: aim (blank/overlong/mistyped after normalization),
    # action (non-str/blank), turn, at
    for bad in ("", "   ", None, ["x"], "y" * 301):
        with pytest.raises(ValueError):
            pending_rows(bad, turn=7, action="x", at=5007.0)
    for bad in (None, "", "   ", 7):
        with pytest.raises(ValueError):
            pending_rows("aim", turn=7, action=bad, at=5007.0)
    for bad in (True, -1, 1.5, "7", None):
        with pytest.raises(ValueError):
            pending_rows("aim", turn=bad, action="x", at=5007.0)
    for bad in (float("nan"), float("inf"), -1.0, True, None, "5007",
                10**1000, 2**53 + 1):
        # incl. overflow normalized to ValueError and the exactness bound
        # (cr r2 blocker 3 — the growth-assembly temporal boundary)
        with pytest.raises(ValueError):
            pending_rows("aim", turn=7, action="x", at=bad)
        with pytest.raises(ValueError):
            cancel_rows(at=bad)
    assert cancel_rows(at=5008.0)[0]["value"] == ""


class _Reads:
    def __init__(self, record):
        self.record = record

    def state(self, entity, attribute, frame=None):
        assert (entity, attribute, frame) == (PENDING, "record",
                                              "session:main")
        return self.record


def _rec(**over):
    rec = {"aim": "a life aboard", "declared_turn": 7,
           "source_action": "I sign on."}
    rec.update(over)
    return json.dumps(rec)


def test_read_pending_requires_the_complete_validated_shape():
    live = _Reads(_rec())
    p = read_pending(live, turn=10)
    assert p == Pending(aim="a life aboard", declared_turn=7,
                        source_action="I sign on.")
    # the expiry boundary: live at exactly +EXPIRY_TURNS, lapsed past it
    assert read_pending(live, turn=7 + EXPIRY_TURNS) is not None
    assert read_pending(live, turn=7 + EXPIRY_TURNS + 1) is None
    # a FUTURE-declared record is structurally invisible (cr blocker 2)
    assert read_pending(_Reads(_rec(declared_turn=20)), turn=8) is None
    # cancel reads as no candidate
    assert read_pending(_Reads(""), turn=8) is None
    assert read_pending(_Reads(None), turn=8) is None
    # INCOMPLETE or malformed records fail toward the ordinary story:
    for broken in (
            _rec(source_action=""),                      # missing evidence
            json.dumps({"aim": "x", "declared_turn": 7}),  # absent field
            _rec(aim=""),
            _rec(aim="z" * 301),
            _rec(declared_turn="7"),
            _rec(declared_turn=True),
            _rec(declared_turn=-1),
            _rec(source_action="w" * 301),
            "not json",
            json.dumps(["a", "list"])):
        assert read_pending(_Reads(broken), turn=8) is None, broken

    class _Boom:
        def state(self, *a, **k):
            raise RuntimeError("session down")
    assert read_pending(_Boom(), turn=8) is None
    # a malformed HOST turn param is a bug and raises
    for bad in (True, -1, 1.5, "8", None):
        with pytest.raises(ValueError):
            read_pending(live, turn=bad)


def test_pending_construction_is_the_validation():
    # cr r2 blocker 1: forged instances are impossible, not unlikely
    import pytest as _pt
    for kw in (dict(aim=""), dict(aim="   "), dict(aim="z" * 301),
               dict(aim=None), dict(declared_turn=True),
               dict(declared_turn=-1), dict(declared_turn="7"),
               dict(source_action=""), dict(source_action=None),
               dict(source_action="w" * 301)):
        fields = dict(aim="a life aboard", declared_turn=7,
                      source_action="I sign on.")
        fields.update(kw)
        with _pt.raises(ValueError):
            Pending(**fields)


def test_may_confirm_consumes_only_the_validated_value():
    pending = Pending(aim="a life aboard", declared_turn=7,
                      source_action="I sign on.")
    assert may_confirm(pending, turn=8, committed=True) is True
    # cr r2 blocker 2: the EXPIRY invariant holds at THIS boundary too —
    # a cached live read must not confirm past its window
    assert may_confirm(pending, turn=7 + EXPIRY_TURNS,
                       committed=True) is True
    assert may_confirm(pending, turn=7 + EXPIRY_TURNS + 1,
                       committed=True) is False
    assert may_confirm(pending, turn=100, committed=True) is False
    # a single line of enthusiasm adopts nothing: same-turn, uncommitted,
    # absent, or IMPERSONATED (a bare dict) all refuse
    assert may_confirm(pending, turn=7, committed=True) is False
    assert may_confirm(pending, turn=8, committed=False) is False
    assert may_confirm(pending, turn=8, committed="true") is False
    assert may_confirm(None, turn=8, committed=True) is False
    assert may_confirm({"aim": "x", "declared_turn": 7,
                        "source_action": "y"}, turn=8,
                       committed=True) is False
    # cr r3: a SUBCLASS with a bypassed __post_init__ is refused too —
    # exact type, not isinstance

    class ForgedPending(Pending):
        def __post_init__(self):
            pass
    forged = ForgedPending("", True, "")
    assert may_confirm(forged, turn=8, committed=True) is False
    for bad in (True, -1, 1.5, "8", None):
        with pytest.raises(ValueError):
            may_confirm(pending, turn=bad, committed=True)


def test_pending_lifecycle_on_a_real_world(tmp_path):
    # cr piece-A blocker 1's demanded oracle: declare → supersede →
    # cancel → reopen on a REAL World; one coherent candidate throughout,
    # partial-write hybrids unrepresentable (one row IS the write)
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from construct.adapter import PorcelainWorldReads
    w = World(tmp_path / "t.world", world_id="w:t", stance="fiction",
              model=StubModel(fallback=rule_classifier_fallback()),
              title="Tangent")
    w.ingestor.cursor.advance(1.0)
    reads = PorcelainWorldReads(w)
    w.porcelain.ingest_structured(
        pending_rows("a life aboard", turn=7, action="I sign on.",
                     at=1007.0), frame="session:main")
    assert read_pending(reads, turn=8).aim == "a life aboard"
    # SUPERSEDE: one write replaces the WHOLE candidate — aim AND turn
    # AND action move together, no hybrid
    w.porcelain.ingest_structured(
        pending_rows("the smugglers' shore", turn=9,
                     action="I row for Gullwash.", at=1009.0),
        frame="session:main")
    p = read_pending(reads, turn=10)
    assert p == Pending(aim="the smugglers' shore", declared_turn=9,
                        source_action="I row for Gullwash.")
    # CANCEL clears whole
    w.porcelain.ingest_structured(cancel_rows(at=1010.0),
                                  frame="session:main")
    assert read_pending(reads, turn=10) is None
    # REOPEN preserves exactly the persisted state (the cancel)
    w.close()
    w2 = World(tmp_path / "t.world", world_id="w:t", stance="fiction",
               model=StubModel(fallback=rule_classifier_fallback()),
               title="Tangent")
    try:
        assert read_pending(PorcelainWorldReads(w2), turn=11) is None
        # and a fresh declaration after reopen is again ONE candidate
        w2.porcelain.ingest_structured(
            pending_rows("a life aboard", turn=11, action="I return.",
                         at=1011.0), frame="session:main")
        assert read_pending(PorcelainWorldReads(w2),
                            turn=12).declared_turn == 11
    finally:
        w2.close()


# ---- piece B: the author gate + the atomic adoption set --------------------

def _proposal(**over):
    p = {"protagonist": "person:npc",   # the host FORCES this — never trusted
         "delta_type": "identity_accepted",
         "tension": ["person:you", "drive:belonging", "drive:duty"],
         "beats": [{"id": "beat:first_catch", "phase": "rising",
                    "weight": "required", "kind": "event_occurs",
                    "entity": "first_catch", "attribute": "", "value": ""}],
         "hook": "Sefa tosses you the bow line as the tide turns.",
         "title": "The Gullwing's Own"}
    p.update(over)
    return p


def _world_reads(tmp_path):
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from construct.adapter import PorcelainWorldReads
    w = World(tmp_path / "b.world", world_id="w:b", stance="fiction",
              model=StubModel(fallback=rule_classifier_fallback()),
              title="Tangent B")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "person:you", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:sefa", "attribute": "kind", "value": "person",
         "timeless": True},
    ])
    return w, PorcelainWorldReads(w)


def test_build_tangent_arc_forces_protagonist_and_lints(tmp_path):
    from construct.tangent import build_tangent_arc
    w, reads = _world_reads(tmp_path)
    try:
        arc, problems = build_tangent_arc(
            _proposal(), protagonist="person:you", arc_id="arc:tangent_9",
            reads=reads)
        assert problems == [] and arc is not None
        assert arc.protagonist == "person:you"       # FORCED over the
        assert arc.arc_id == "arc:tangent_9"         # proposal's npc pick
        # a proposal the grammar rejects returns problems, commits nothing
        bad, problems = build_tangent_arc(
            _proposal(beats=[{"id": "beat:x", "phase": "nonsense",
                              "weight": "required", "kind": "event_occurs",
                              "entity": "x", "attribute": "", "value": ""}]),
            protagonist="person:you", arc_id="arc:tangent_9", reads=reads)
        assert bad is None and problems
        # a lint-blocked proposal (ungrounded referent) returns problems
        bad, problems = build_tangent_arc(
            _proposal(tension=["person:nobody_here", "drive:a", "drive:b"]),
            protagonist="person:you", arc_id="arc:tangent_9", reads=reads)
        assert bad is None and problems
        bad, problems = build_tangent_arc(
            "not a mapping", protagonist="person:you",
            arc_id="arc:tangent_9", reads=reads)
        assert bad is None and problems
        import pytest as _pt
        with _pt.raises(ValueError):
            build_tangent_arc(_proposal(), protagonist="you",
                              arc_id="arc:t", reads=reads)
        with _pt.raises(ValueError):
            build_tangent_arc(_proposal(), protagonist="person:you",
                              arc_id="tangent", reads=reads)
    finally:
        w.close()


def test_adoption_ops_shape_and_order():
    import pytest as _pt
    from construct.tangent import ADOPTION_RECEIPT_KIND, adoption_ops
    arc_items = [{"entity": "arc:tangent_9", "attribute": "kind",
                  "value": "arc", "frame": "plot:main"}]
    manifest = [{"entity": "arc:portfolio", "attribute": "main_arc",
                 "value": "arc:tangent_9", "frame": "plot:main"}]
    ops = adoption_ops(new_arc_items=arc_items, manifest_items=manifest,
                       retract_ids=["a-77", "a-78"],
                       old_main_id="arc:main", new_main_id="arc:tangent_9",
                       aim="a life aboard", turn=9, at=1009.0)
    kinds = [op["op"] for op in ops]
    # retracts FIRST (the Cx 167 discipline), then asserts only
    assert kinds[:2] == ["retract", "retract"]
    assert set(kinds[2:]) == {"assert"}
    assert ops[0]["assertion_id"] == "a-77" and ops[0]["reason"]
    items = [op["item"] for op in ops if op["op"] == "assert"]
    by = {(i["entity"], i["attribute"]): i.get("value") for i in items}
    # the old main is DEMOTED durably, never silently dropped
    assert by[("arc:main", "demoted")] == ADOPTION_RECEIPT_KIND
    # the durable receipt the phase boundary reads rides the SAME set
    ev = "event:tangent_adopted_9"
    assert by[(ev, "kind")] == ADOPTION_RECEIPT_KIND
    assert by[(ev, "aim")] == "a life aboard"
    assert by[(ev, "old_main")] == "arc:main"
    assert by[(ev, "new_main")] == "arc:tangent_9"
    # the manifest switch is inside the set too
    assert by[("arc:portfolio", "main_arc")] == "arc:tangent_9"
    # host bugs raise: same-id switch, empty items, malformed retracts,
    # blank aim, bad turn/at
    for kw in (dict(new_main_id="arc:main"),
               dict(old_main_id="main"),
               dict(new_arc_items=[]),
               dict(new_arc_items=["row"]),
               dict(manifest_items=[]),
               dict(retract_ids=[""]),
               dict(retract_ids=[7]),
               dict(aim="   "),
               dict(turn=-1), dict(turn=True),
               dict(at=float("nan")), dict(at=2**53 + 1)):
        base = dict(new_arc_items=arc_items, manifest_items=manifest,
                    retract_ids=["a-77"], old_main_id="arc:main",
                    new_main_id="arc:tangent_9", aim="a life aboard",
                    turn=9, at=1009.0)
        base.update(kw)
        with _pt.raises(ValueError):
            adoption_ops(**base)


def test_activate_adoption_fails_closed_without_commit_set():
    from construct.growth import ActivationResult
    from construct.tangent import activate_adoption

    class _NoEnvelope:
        def ingest_structured(self, items, atomic=False):
            raise AssertionError("the sugar path must NEVER carry a "
                                 "mixed-op adoption set")
    ops = [{"op": "retract", "assertion_id": "a-1", "reason": "r"},
           {"op": "assert", "item": {"entity": "arc:t", "attribute": "kind",
                                     "value": "arc"}}]
    r = activate_adoption(_NoEnvelope(), ops)
    assert isinstance(r, ActivationResult)
    assert r.ok is False and r.reason == "adoption_unavailable"
    # malformed sets refuse before any engine call
    assert activate_adoption(_NoEnvelope(), []).reason == "empty_set"
    assert activate_adoption(_NoEnvelope(),
                             [{"op": "upsert"}]).reason == "malformed_op"

    class _Willing:
        def __init__(self):
            self.sets = []

        def commit_set(self, ops_):
            self.sets.append(ops_)
            return {"outcome": "committed",
                    "rows": [{"entity": "arc:t"}]}
    w = _Willing()
    r = activate_adoption(w, ops)
    assert r.ok is True and len(w.sets) == 1 and w.sets[0] == ops

    class _Aborting:
        def commit_set(self, ops_):
            raise RuntimeError("op 3 rejected")
    r = activate_adoption(_Aborting(), ops)
    assert r.ok is False and r.reason.startswith("engine_abort:")

    class _Typed:
        def commit_set(self, ops_):
            return {"outcome": "aborted", "skipped": [{"op": 1}]}
    r = activate_adoption(_Typed(), ops)
    assert r.ok is False and r.reason == "engine_outcome:aborted"
