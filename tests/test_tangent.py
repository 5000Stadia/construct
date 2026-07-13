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
    def __init__(self, record, adopted_turns=()):
        self.record = record
        self.adopted_turns = adopted_turns

    def state(self, entity, attribute, frame=None):
        assert (entity, attribute, frame) == (PENDING, "record",
                                              "session:main")
        return self.record

    def events(self, kind=None, frame=None):
        from types import SimpleNamespace
        return [SimpleNamespace(event_id=f"event:tangent_adopted_{t}",
                                kind=kind) for t in self.adopted_turns]


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

    # a CONSUMED generation is ineligible forever (cr piece-C blocker 2):
    # an adoption receipt at turn 9 spends every declaration <= 9, while a
    # NEWER declaration stays eligible
    assert read_pending(_Reads(_rec(), adopted_turns=(9,)), turn=10) is None
    assert read_pending(_Reads(_rec(declared_turn=10),
                               adopted_turns=(9,)), turn=11) is not None

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


def _seed_portfolio(w, reads):
    from construct.arc import io as arc_io
    from construct.tangent import build_tangent_arc
    old, problems = build_tangent_arc(
        _proposal(beats=[{"id": "beat:old_thread", "phase": "rising",
                          "weight": "required", "kind": "event_occurs",
                          "entity": "old_thread", "attribute": "",
                          "value": ""}]),
        protagonist="person:you", arc_id="arc:main_case", reads=reads)
    assert problems == []
    w.porcelain.ingest_structured(
        arc_io.arc_to_items(old, frame="plot:main")
        + arc_io.index_items(old, frame="plot:main")
        + arc_io.portfolio_items(["arc:main_case"],
                                 main_arc_id="arc:main_case",
                                 frame="plot:main"), frame="plot:main")
    return old


def test_adoption_ops_from_verified_state_and_reconstruction(tmp_path):
    # cr piece-B r2 blockers 1+2: the set is built ONLY from the exact
    # linted Arc + the VERIFIED portfolio; success is pinned by
    # RECONSTRUCTING the portfolio after applying the ops on a real World
    import pytest as _pt
    from construct.arc import io as arc_io
    from construct.tangent import (ADOPTION_RECEIPT_KIND, PortfolioState,
                                   adoption_ops, build_tangent_arc,
                                   read_portfolio_state)
    w, reads = _world_reads(tmp_path)
    try:
        _seed_portfolio(w, reads)
        state = read_portfolio_state(reads)
        assert type(state) is PortfolioState
        assert state.main_arc == "arc:main_case"
        assert {a for a, _ in state.retracts} == {"arc_ids", "main_arc"}
        arc, problems = build_tangent_arc(
            _proposal(), protagonist="person:you", arc_id="arc:tangent_9",
            reads=reads)
        assert problems == []
        ops = adoption_ops(arc=arc, portfolio=state,
                           protagonist="person:you", aim="a life aboard",
                           turn=9, at=1009.0, reads=reads)
        # retracts first, covering every located control row
        assert [o["op"] for o in ops[:len(state.retracts)]] == \
            ["retract"] * len(state.retracts)
        assert {o["assertion_id"] for o in ops
                if o["op"] == "retract"} == {aid for _, aid
                                             in state.retracts}
        # APPLY the set the way the envelope would (retracts then asserts)
        for op in ops:
            if op["op"] == "retract":
                w.porcelain.retract(op["assertion_id"], op["reason"])
            else:
                item = dict(op["item"])
                frame = item.pop("frame", None)
                w.porcelain.ingest_structured([item], frame=frame,
                                              classify="rules")
        # RECONSTRUCTION: exactly one loadable new main; the old main a
        # retained member carrying the durable demotion (cursor advanced
        # past the adoption horizon — reads are as-of)
        w.ingestor.cursor.advance(2000.0)
        assert arc_io.main_arc_from_frame(reads) == "arc:tangent_9"
        loaded = {a.arc_id: a for a in arc_io.portfolio_from_frame(reads)}
        assert set(loaded) == {"arc:main_case", "arc:tangent_9"}
        assert loaded["arc:tangent_9"].protagonist == "person:you"
        assert reads.state("arc:main_case", "demoted",
                           frame="plot:main") == ADOPTION_RECEIPT_KIND
        # the durable receipt reads through the EVENT path (the same read
        # the piece-C phase boundary consumes)
        evs = reads.events(kind=ADOPTION_RECEIPT_KIND, frame="session:main")
        assert [e.event_id for e in evs] == ["event:tangent_adopted_9"]
        ev_attrs = {r.attribute: r.value for r in w.buffer.visible(
            entity="event:tangent_adopted_9", frame="session:main")}
        assert ev_attrs["new_main"] == "arc:tangent_9"
        assert ev_attrs["old_main"] == "arc:main_case"
        assert ev_attrs["aim"] == "a life aboard"
        # host bugs raise: a non-Arc, a dict impersonating the state, an
        # arc already in the portfolio, blank aim, bad turn/at
        with _pt.raises(ValueError):
            adoption_ops(arc="arc:tangent_9", portfolio=state,
                         protagonist="person:you",
                         aim="x", turn=9, at=1009.0, reads=reads)
        with _pt.raises(ValueError):
            adoption_ops(arc=arc, portfolio={"main_arc": "arc:main_case"},
                         protagonist="person:you",
                         aim="x", turn=9, at=1009.0, reads=reads)
        old_arc, _ = build_tangent_arc(
            _proposal(), protagonist="person:you",
            arc_id="arc:tangent_dup", reads=reads)
        dup_state = PortfolioState(
            arc_ids=("arc:main_case", "arc:tangent_dup"),
            main_arc="arc:main_case",
            retracts=(("arc_ids", "a-1"), ("main_arc", "a-2")))
        with _pt.raises(ValueError):     # already a member — never re-adopt
            adoption_ops(arc=old_arc, portfolio=dup_state,
                         protagonist="person:you", aim="x",
                         turn=9, at=1009.0, reads=reads)
        # a MUTATED exact-type Arc is refused at the envelope's door
        # (cr r3 blocker 2: type proves nothing about content)
        import dataclasses as _dc
        gutted = _dc.replace(arc, beats=())
        with _pt.raises(ValueError):
            adoption_ops(arc=gutted, portfolio=state,
                         protagonist="person:you", aim="a life aboard",
                         turn=9, at=1009.0, reads=reads)
        # cr r4 blocker 2: the player binds INDEPENDENTLY — a protagonist
        # swap to an existing person refuses; so does a gutted arc id
        swapped = _dc.replace(arc, protagonist="person:sefa")
        with _pt.raises(ValueError):
            adoption_ops(arc=swapped, portfolio=state,
                         protagonist="person:you", aim="a life aboard",
                         turn=9, at=1009.0, reads=reads)
        blank_id = _dc.replace(arc, arc_id="arc:")
        with _pt.raises(ValueError):
            adoption_ops(arc=blank_id, portfolio=state,
                         protagonist="person:you", aim="a life aboard",
                         turn=9, at=1009.0, reads=reads)
        # cr r5: per-ROLE grammar — a cross-prefix id refuses in every
        # role, not merely a some-allowed-prefix union
        for mutant in (_dc.replace(arc, arc_id="shape:not_an_arc"),
                       _dc.replace(arc, shape=_dc.replace(
                           arc.shape, shape_id="arc:not_a_shape")),
                       _dc.replace(arc, beats=tuple(
                           _dc.replace(b, beat_id="clock:not_a_beat")
                           for b in arc.beats)),
                       _dc.replace(arc, refusal_clock=_dc.replace(
                           arc.refusal_clock,
                           clock_id="beat:not_a_clock"))):
            with _pt.raises(ValueError):
                adoption_ops(arc=mutant, portfolio=state,
                             protagonist="person:you",
                             aim="a life aboard", turn=9, at=1009.0,
                             reads=reads)
        # cr r4 blocker 1: a well-shaped state with UNRELATED existing ids
        # refuses at the door (the fresh re-read equality)
        forged = PortfolioState(
            arc_ids=state.arc_ids, main_arc=state.main_arc,
            retracts=(("arc_ids", "a:9998"), ("main_arc", "a:9999")))
        with _pt.raises(ValueError):
            adoption_ops(arc=arc, portfolio=forged,
                         protagonist="person:you", aim="a life aboard",
                         turn=9, at=1009.0, reads=reads)
        for kw in (dict(aim="   "), dict(turn=-1), dict(turn=True),
                   dict(at=float("nan")), dict(at=2**53 + 1),
                   dict(protagonist="you")):
            base = dict(arc=arc, portfolio=state,
                        protagonist="person:you", aim="a life aboard",
                        turn=9, at=1009.0, reads=reads)
            base.update(kw)
            with _pt.raises(ValueError):
                adoption_ops(**base)
    finally:
        w.close()


def test_portfolio_state_is_verified_or_absent(tmp_path):
    # cr r2 blocker 1: no control rows located → NO adoption (never a
    # blind retract); forged states raise at construction
    import pytest as _pt
    from construct.tangent import PortfolioState, read_portfolio_state
    w, reads = _world_reads(tmp_path)
    try:
        assert read_portfolio_state(reads) is None   # nothing seeded
    finally:
        w.close()
    good = dict(arc_ids=("arc:main_case",), main_arc="arc:main_case",
                retracts=(("arc_ids", "a-1"), ("main_arc", "a-2")))
    for kw in (dict(arc_ids=()), dict(arc_ids=("main",)),
               dict(arc_ids=("arc:Main",)),          # exact grammar
               dict(arc_ids=["arc:main_case"]),      # exact TUPLE, no list
               dict(arc_ids=("arc:a", "arc:a")),     # unique
               dict(main_arc="arc:other"),
               dict(retracts=[("arc_ids", "a-1"), ("main_arc", "a-2")]),
               dict(retracts=(("arc_ids", "a-1"),)),   # one attr ≠ both
               dict(retracts=(("arc_ids", "a-1"),
                              ("arc_ids", "a-2"))),    # same attr twice
               dict(retracts=(("arc_ids", "a-1"),
                              ("main_arc", "a-1"))),   # duplicate id
               dict(retracts=(("arc_ids", "a-1"),
                              ("main_arc", None))),    # None id
               dict(retracts=(("other", "a-1"),
                              ("main_arc", "a-2"))),   # unknown attr
               dict(retracts=(("arc_ids", "a-1"), ("main_arc", "a-2"),
                              ("arc_ids", "a-3")))):   # exactly TWO
        base = dict(good)
        base.update(kw)
        with _pt.raises(ValueError):
            PortfolioState(**base)


def test_build_tangent_arc_ids_and_reload(tmp_path):
    # cr r2 blocker 3: exact id grammar, collision + uniqueness, and the
    # serialize/reload oracle
    import pytest as _pt
    from construct.arc import io as arc_io
    from construct.tangent import build_tangent_arc
    w, reads = _world_reads(tmp_path)
    try:
        with _pt.raises(ValueError):
            build_tangent_arc(_proposal(), protagonist="person:you",
                              arc_id="arc:", reads=reads)
        with _pt.raises(ValueError):
            build_tangent_arc(_proposal(), protagonist="person:you",
                              arc_id="arc:Tangent-9", reads=reads)
        # duplicate DERIVED beat ids decline (cr r3: "beat:a-b" and
        # "beat:a_b" normalize to ONE persisted id — judged post-build)
        dup = _proposal(beats=[
            {"id": "beat:a-b", "phase": "rising", "weight": "required",
             "kind": "event_occurs", "entity": "x", "attribute": "",
             "value": ""},
            {"id": "beat:a_b", "phase": "crisis", "weight": "required",
             "kind": "event_occurs", "entity": "y", "attribute": "",
             "value": ""}])
        bad, problems = build_tangent_arc(dup, protagonist="person:you",
                                          arc_id="arc:tangent_9",
                                          reads=reads)
        assert bad is None and \
            "build: duplicate derived beat ids" in problems
        # an arc id already living in the PLOT frame collides (cr r3:
        # arcs are plot rows — canon has_entity proves the wrong boundary)
        w.porcelain.ingest_structured([
            {"entity": "arc:taken", "attribute": "protagonist",
             "value": "person:you", "frame": "plot:main"}],
            frame="plot:main")
        bad, problems = build_tangent_arc(_proposal(),
                                          protagonist="person:you",
                                          arc_id="arc:taken", reads=reads)
        assert bad is None and \
            "preflight: id_collision:arc:taken" in problems
        # cr r4 blocker 3: the separately stored REFUSAL clock is in the
        # collision set too
        w.porcelain.ingest_structured([
            {"entity": "clock:refusal_tangent_77", "attribute": "kind",
             "value": "clock", "frame": "plot:main"}], frame="plot:main")
        bad, problems = build_tangent_arc(
            _proposal(), protagonist="person:you",
            arc_id="arc:tangent_77", reads=reads)
        assert bad is None and \
            "preflight: id_collision:clock:refusal_tangent_77" in problems
        # SERIALIZE/RELOAD: the built arc round-trips whole
        arc, problems = build_tangent_arc(
            _proposal(), protagonist="person:you", arc_id="arc:tangent_9",
            reads=reads)
        assert problems == []
        w.porcelain.ingest_structured(
            arc_io.arc_to_items(arc, frame="plot:main")
            + arc_io.index_items(arc, frame="plot:main")
            + arc_io.portfolio_items(["arc:tangent_9"],
                                     main_arc_id="arc:tangent_9",
                                     frame="plot:main"), frame="plot:main")
        loaded = {a.arc_id: a
                  for a in arc_io.portfolio_from_frame(reads)}
        got = loaded["arc:tangent_9"]
        assert got.protagonist == arc.protagonist
        assert [b.beat_id for b in got.beats] == \
            [b.beat_id for b in arc.beats]
        assert got.shape.delta_type == arc.shape.delta_type
    finally:
        w.close()


def test_author_tangent_arc_prompt_is_aim_and_visible_only():
    from construct.cohorts import author_tangent_arc
    from construct.provider import StubProvider, task_of
    provider = StubProvider([_proposal()])
    out = author_tangent_arc(
        provider, aim="build a life aboard the Gullwing",
        protagonist="person:you",
        visible_facts="- the Gullwing, a coastal ketch\n- Sefa, her master",
        style="salt-plain, unhurried",
        available_ids=["person:you", "person:sefa"])
    assert out["title"] == "The Gullwing's Own"
    prompt = provider.calls[0][0]
    assert task_of(prompt) == "tga"
    assert "build a life aboard the Gullwing" in prompt
    assert "must be EXACTLY this id): person:you" in prompt
    assert "a coastal ketch" in prompt
    assert "salt-plain" in prompt


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
    # malformed sets refuse before any engine call (cr r2 blocker 4:
    # full op SHAPES, not just the tag)
    assert activate_adoption(_NoEnvelope(), []).reason == "empty_set"
    assert activate_adoption(_NoEnvelope(),
                             [{"op": "upsert"}]).reason == "malformed_op"
    assert activate_adoption(_NoEnvelope(),
                             [{"op": "assert"}]).reason == "malformed_op"
    assert activate_adoption(_NoEnvelope(), [
        {"op": "assert", "item": {"entity": "", "attribute": "k"}}
    ]).reason == "malformed_op"
    assert activate_adoption(_NoEnvelope(),
                             [{"op": "retract"}]).reason == "malformed_op"
    assert activate_adoption(_NoEnvelope(), [
        {"op": "retract", "assertion_id": "a-1", "reason": ""}
    ]).reason == "malformed_op"
    # an all-assert or all-retract set is NOT an adoption
    assert activate_adoption(_NoEnvelope(), [ops[1]]).reason == \
        "not_an_adoption_set"
    assert activate_adoption(_NoEnvelope(), [ops[0]]).reason == \
        "not_an_adoption_set"

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


def test_read_portfolio_state_is_horizon_bound_and_conflict_closed(tmp_path):
    # cr r3 blocker 1's repro: an old manifest at 100 and a FUTURE one at
    # 1000 — at horizon 500 the state is the OLD manifest with ITS
    # assertion ids; at head (both visible) the constitutive multiplicity
    # fails CLOSED (a conflicted fold is not a safe adoption base)
    import json
    from construct.adapter import PorcelainWorldReads
    from construct.tangent import read_portfolio_state
    w, _ = _world_reads(tmp_path)
    try:
        w.porcelain.ingest_structured([
            {"entity": "arc:portfolio", "attribute": "arc_ids",
             "value": json.dumps(["arc:old"]), "value_type": "literal",
             "valid_from": 100.0},
            {"entity": "arc:portfolio", "attribute": "main_arc",
             "value": "arc:old", "value_type": "literal",
             "valid_from": 100.0},
            {"entity": "arc:portfolio", "attribute": "arc_ids",
             "value": json.dumps(["arc:future"]), "value_type": "literal",
             "valid_from": 1000.0},
            {"entity": "arc:portfolio", "attribute": "main_arc",
             "value": "arc:future", "value_type": "literal",
             "valid_from": 1000.0},
        ], frame="plot:main")
        horizon_reads = PorcelainWorldReads(w, horizon=500.0)
        state = read_portfolio_state(horizon_reads)
        assert state is not None and state.main_arc == "arc:old"
        assert state.arc_ids == ("arc:old",)
        w.ingestor.cursor.advance(5000.0)
        head_reads = PorcelainWorldReads(w)
        assert read_portfolio_state(head_reads) is None   # multiplicity
    finally:
        w.close()


# ---- piece C: the two-beat wiring on the real turn path --------------------

def _wired(tmp_path):
    import tests.test_growth as tg
    w = tg._wired_world(tmp_path)
    return tg, w


def _seed_wired_portfolio(w):
    from construct.arc import io as arc_io
    import tests.test_growth as tg
    arc = tg._wired_arc()
    w.porcelain.ingest_structured(
        arc_io.arc_to_items(arc, frame="plot:main")
        + arc_io.index_items(arc, frame="plot:main")
        + arc_io.portfolio_items([arc.arc_id], main_arc_id=arc.arc_id,
                                 frame="plot:main"), frame="plot:main")
    return arc


def test_wired_beat1_persists_and_supersedes(tmp_path):
    from construct.provider import StubProvider
    from construct.tangent import read_pending
    from construct.turnloop import run_turn
    from construct.adapter import PorcelainWorldReads
    tg, w = _wired(tmp_path)
    try:
        arc = _seed_wired_portfolio(w)
        provider = StubProvider([
            tg._classify(moves_open=False, moves_to="",
                         declares_tangent_aim=True,
                         tangent_aim="a life aboard the Gullwing")]
            + [{"prose": "The tide agrees with you."}] * 3)
        r = run_turn(w, arc, provider, "Forget the case — I'm making a "
                     "life on this boat.", turn=1)
        assert r.trace.tangent == "pending:a life aboard the Gullwing"
        reads = PorcelainWorldReads(w)
        p1 = read_pending(reads, turn=2)
        assert p1 is not None and p1.declared_turn == 1
        # the turn rendered NORMALLY — a declaration is not a seam
        assert "tide agrees" in r.prose
        # BEAT 2 never fires on the declaration turn itself (host gate) —
        # no confirm cohort ran
        assert not any("⟦tgc⟧" in c[0][:40] for c in provider.calls)
        # a NEWER declaration supersedes whole
        provider = StubProvider([
            tg._classify(moves_open=False, moves_to="",
                         declares_tangent_aim=True,
                         tangent_aim="the smugglers' shore is home now")]
            + [{"prose": "Gullwash rises off the bow."}] * 3)
        r2 = run_turn(w, arc, provider, "No — Gullwash. That's my story.",
                      turn=2)
        p2 = read_pending(reads, turn=3)
        assert p2.aim == "the smugglers' shore is home now"
        assert p2.declared_turn == 2
    finally:
        w.close()


def test_wired_beat2_fails_closed_without_the_envelope(tmp_path):
    # the full confirm→author→adopt path on PB 0.2.0: adoption_unavailable,
    # the pending SURVIVES, the manifest is untouched, and the ordinary
    # action still renders (no seam — unlike growth, the action is real
    # without the arc swap)
    from construct.arc import io as arc_io
    from construct.provider import StubProvider
    from construct.tangent import pending_rows, read_pending
    from construct.turnloop import run_turn
    from construct.adapter import PorcelainWorldReads
    tg, w = _wired(tmp_path)
    try:
        arc = _seed_wired_portfolio(w)
        w.porcelain.ingest_structured(
            pending_rows("a life aboard the Gullwing", turn=1,
                         action="Forget the case.", at=1001.0),
            frame="session:main")
        provider = StubProvider([
            tg._classify(moves_open=False, moves_to=""),
            {"consistent": True, "abandons": False},
            _proposal(),
        ] + [{"prose": "You sign the Gullwing's book."}] * 3)
        r = run_turn(w, arc, provider, "I sign on with the Gullwing.",
                     turn=2)
        assert r.trace.tangent == "adoption_unavailable"
        assert "⟦tgc⟧" in provider.calls[1][0][:40]
        tga = [c[0] for c in provider.calls if "⟦tga⟧" in c[0][:40]]
        assert tga
        # cr piece-C blocker 3: the author sees ONLY the player-visible
        # world — the hidden answer's person (canon-only) is absent; the
        # player-frame place is present
        assert "person:rival" not in tga[0]
        assert "place:north_road" in tga[0]
        reads = PorcelainWorldReads(w)
        assert arc_io.main_arc_from_frame(reads) == arc.arc_id  # unmoved
        assert read_pending(reads, turn=3) is not None          # survives
        assert "Gullwing's book" in r.prose                     # no seam
        assert r.trace.replanned == ""
    finally:
        w.close()


def test_wired_beat2_negative_and_cancel(tmp_path):
    from construct.provider import StubProvider
    from construct.tangent import pending_rows, read_pending
    from construct.turnloop import run_turn
    from construct.adapter import PorcelainWorldReads
    tg, w = _wired(tmp_path)
    try:
        arc = _seed_wired_portfolio(w)
        w.porcelain.ingest_structured(
            pending_rows("a life aboard the Gullwing", turn=1,
                         action="Forget the case.", at=1001.0),
            frame="session:main")
        # INCONSISTENT: the deed serves the old story — pending survives,
        # no author call, no generative slot spent on judging
        provider = StubProvider([
            tg._classify(moves_open=False, moves_to=""),
            {"consistent": False, "abandons": False},
        ] + [{"prose": "The ledger keeps its secrets."}] * 3)
        r = run_turn(w, arc, provider, "I re-examine the ledger.", turn=2)
        assert r.trace.tangent == "declined:inconsistent"
        assert not any("⟦tga⟧" in c[0][:40] for c in provider.calls)
        reads = PorcelainWorldReads(w)
        assert read_pending(reads, turn=3) is not None
        # ABANDONS: the deed walks back — the pending cancels whole
        provider = StubProvider([
            tg._classify(moves_open=False, moves_to=""),
            {"consistent": False, "abandons": True},
        ] + [{"prose": "The case pulls you back."}] * 3)
        r = run_turn(w, arc, provider, "Enough dreaming — back to the "
                     "case.", turn=3)
        assert r.trace.tangent == "cancelled"
        assert read_pending(reads, turn=4) is None
    finally:
        w.close()


def test_wired_adoption_success_with_a_willing_envelope(tmp_path,
                                                        monkeypatch):
    # fake-envelope success: the manifest flips whole, the session reload
    # is armed (trace.replanned — the reshape path), the narrator carries
    # the world's YES, the receipt clears, and the old main survives
    # demoted as a side arc
    import construct.tangent as tangent_mod
    from construct.arc import io as arc_io
    from construct.provider import StubProvider
    from construct.tangent import (ADOPTION_RECEIPT_KIND, pending_rows,
                                   read_pending)
    from construct.turnloop import run_turn
    from construct.adapter import PorcelainWorldReads
    tg, w = _wired(tmp_path)
    try:
        arc = _seed_wired_portfolio(w)
        w.porcelain.ingest_structured(
            pending_rows("a life aboard the Gullwing", turn=1,
                         action="Forget the case.", at=1001.0),
            frame="session:main")

        real = tangent_mod.activate_adoption

        def _willing(porcelain, ops):
            for op in ops:
                if op["op"] == "retract":
                    porcelain.retract(op["assertion_id"], op["reason"])
                else:
                    item = dict(op["item"])
                    frame = item.pop("frame", None)
                    porcelain.ingest_structured([item], frame=frame,
                                                classify="rules")
            from construct.growth import ActivationResult
            return ActivationResult(ok=True, receipts=("r",))
        monkeypatch.setattr(tangent_mod, "activate_adoption", _willing)
        provider = StubProvider([
            tg._classify(moves_open=False, moves_to=""),
            {"consistent": True, "abandons": False},
            _proposal(),
        ] + [{"prose": "Sefa tosses you the bow line."}] * 3)
        r = run_turn(w, arc, provider, "I sign on with the Gullwing.",
                     turn=2)
        assert r.trace.tangent == "adopted:arc:tangent_2"
        assert r.trace.replanned == "arc:tangent_2"
        assert "THE STORY TURNS" in r.trace.briefing
        assert "bow line" in r.trace.briefing   # the hook, not a summary
        # SAME-TURN PHASE BOUNDARY (cr piece-C blocker 1): the demoted
        # main's hidden destination never reaches the narrator after the
        # adoption lands — the rest of the turn obeys the new main
        assert "person:rival" not in r.trace.briefing
        assert "fact:secret" not in r.trace.briefing
        assert r.trace.drift == []              # no old-main drift pass
        reads = PorcelainWorldReads(w)
        w.ingestor.cursor.advance(5000.0)
        assert arc_io.main_arc_from_frame(reads) == "arc:tangent_2"
        loaded = {a.arc_id for a in arc_io.portfolio_from_frame(reads)}
        assert loaded == {arc.arc_id, "arc:tangent_2"}
        assert reads.state(arc.arc_id, "demoted",
                           frame="plot:main") == ADOPTION_RECEIPT_KIND
        assert read_pending(reads, turn=3) is None    # receipt cleared
        # cr piece-C blocker 2: even if the best-effort clear had FAILED,
        # the consumed generation cannot adopt twice — restore the exact
        # pre-adoption record (simulating the failed clear) and run the
        # next confirming action: the receipt makes it ineligible, the
        # confirm cohort never runs, main stays the tangent
        w.porcelain.ingest_structured(
            pending_rows("a life aboard the Gullwing", turn=1,
                         action="Forget the case.", at=1001.5),
            frame="session:main")
        assert read_pending(reads, turn=3) is None    # consumed forever
        provider = StubProvider([
            tg._classify(moves_open=False, moves_to="")]
            + [{"prose": "The deck settles under you."}] * 4)
        r2 = run_turn(w, arc, provider, "I coil the lines and make "
                      "myself useful.", turn=3)
        assert r2.trace.tangent == ""                 # never armed
        assert not any("⟦tgc⟧" in c[0][:40] for c in provider.calls)
        assert arc_io.main_arc_from_frame(reads) == "arc:tangent_2"
    finally:
        w.close()
