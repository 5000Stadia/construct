"""STORY SOUNDNESS (docs/design/STORY-SOUNDNESS.md r4, R35): the producer fixed point.

Planted faults, each with a passing twin; reshape on and off (P10, the miracle channel);
advisory-only wiring (nothing gates)."""
import pytest
from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import HorizonView, PorcelainWorldReads
from construct.arc.conditions import (
    AllOf, AtLeast, BeatAchieved, ClockFired, InFrame, Located, Occurred, StateIs,
    TurnsQuiet,
)
from construct.arc.grammar import (
    Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight,
)
from construct.arc.soundness import analyse
from construct.cast import CastNode, Clue
from construct.semantics import attribute_default

PROT = "person:prot"
PF = f"knows:{PROT}"
STEP = 1_000_000.0
H = STEP + 1010.0
FUTURE = 10 * STEP


def _fallback(prompt, schema, _rule=rule_classifier_fallback()):
    return _rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}


@pytest.fixture
def w(tmp_path):
    world = World(tmp_path / "s.world", world_id="w:s", model=StubModel(fallback=_fallback),
                  stance="fiction", attribute_default=attribute_default)
    world.ingestor.cursor.advance(1.0)
    world.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:far", "attribute": "kind", "value": "field", "timeless": True},
        {"entity": PROT, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PROT, "attribute": "in", "value": "place:study", "value_type": "entity",
         "valid_from": STEP},
        {"entity": "person:breen", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:breen", "attribute": "in", "value": "place:study",
         "value_type": "entity", "valid_from": STEP},
        {"entity": "person:dead", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:dead", "attribute": "in", "value": "place:study",
         "value_type": "entity", "valid_from": STEP},
        {"entity": "person:dead", "attribute": "alive", "value": "false", "valid_from": STEP},
        {"entity": "person:x", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:gate", "attribute": "kind", "value": "gate", "timeless": True},
        {"entity": "obj:gate", "attribute": "state", "value": "shut", "valid_from": STEP},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition",
         "timeless": True},
        {"entity": "person:future", "attribute": "kind", "value": "person",
         "valid_from": FUTURE},
    ])
    yield world
    world.close()


def _arc(beats, clocks=(), world_condition=None, failure_when=None):
    beats = tuple(beats)
    wc = world_condition or AtLeast(1, tuple(BeatAchieved(b.beat_id) for b in beats))
    shape = ConclusionShape("shape:main", "drive_inverted", (PROT, "drive:a", "drive:b"),
                            world_condition=wc, premise=StateIs(PROT, "kind", "person"),
                            refusal_variant_id="shape:refused")
    refusal = Clock("clock:refusal", Occurred("event:abandoned"),
                    effects=({"entity": "event:concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    return Arc(arc_id="arc:main", protagonist=PROT, shape=shape, beats=beats,
               clocks=tuple(clocks), refusal_clock=refusal, climax_ready_k=1,
               climax_ready_beats=(beats[0].beat_id,), failure_when=failure_when,
               phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                             Phase.CLIMAX: 2, Phase.FALLING: 2})


def _req(bid, cond):
    return Beat(bid, Phase.CLIMAX, Weight.REQUIRED, achievable_via=cond)


def _clue(cid, fact, holder="person:breen", **kw):
    return CastNode(holder, holds_clues=(Clue(cid, "pillar:p", fact, **kw),),
                    presence="at_scene", location="place:study")


def _run(w, arc, cast=(), *, reshape=False, kind="fresh"):
    v = HorizonView(w, H)
    return analyse(arc, cast, PROT, PorcelainWorldReads(v), horizon=H, world=v, kind=kind,
                   reshape=reshape, goal_statement="find out")


def _codes(rep, subject=None):
    return [f.code for f in rep.findings if subject is None or f.subject == subject]


# --------------------------------------------------------------------- planted faults

def test_1_event_with_a_participant(w):
    arc = _arc([_req("beat:confess", Occurred("confession", participants=("person:breen",)))])
    assert _codes(_run(w, arc), "beat:confess") == ["S1"]
    assert _codes(_run(w, arc, reshape=True), "beat:confess") == ["S12"]
    twin = _arc([_req("beat:confess", Occurred("confession"))],
                clocks=[Clock("clock:c", TurnsQuiet(3),
                              effects=({"entity": "event:confession_x", "attribute": "kind",
                                        "value": "confession"},),
                              bound_to="arc:main", rung=Rung.SURFACE)])
    assert "beat:confess" not in [f.subject for f in _run(w, twin).findings]


def test_2_nested_event(w):
    arc = _arc([_req("beat:n", AllOf((InFrame(PF, "fact:secret", "is", "out"),
                                      Occurred("signal"))))])
    cast = (_clue("clue:s", ("fact:secret", "is", "out")),)
    rep = _run(w, arc, cast)
    assert _codes(rep, "beat:n") == ["S1"]
    assert any("only writes protagonist-only bare-beat events" in x
               for f in rep.findings for x in f.witness)
    assert _codes(_run(w, arc, cast, reshape=True), "beat:n") == ["S12"]


def test_3_orphan_state(w):
    arc = _arc([_req("beat:gate", StateIs("obj:gate", "state", "open"))])
    assert _codes(_run(w, arc), "beat:gate") == ["S1"]
    assert _codes(_run(w, arc, reshape=True), "beat:gate") == ["S12"]
    twin = _arc([_req("beat:gate", StateIs("obj:gate", "state", "open"))],
                clocks=[Clock("clock:g", TurnsQuiet(4),
                              effects=({"entity": "obj:gate", "attribute": "state",
                                        "value": "open"},),
                              bound_to="arc:main", rung=Rung.SURFACE)])
    assert "beat:gate" not in [f.subject for f in _run(w, twin).findings]


def test_4_world_condition_short_of_k(w):
    good = [_req(f"beat:g{i}", Occurred(f"k{i}")) for i in range(2)]
    bad = [_req(f"beat:b{i}", Occurred(f"x{i}", participants=("person:breen",)))
           for i in range(2)]
    beats = good + bad
    arc = _arc(beats, world_condition=AtLeast(3, tuple(BeatAchieved(b.beat_id)
                                                        for b in beats)))
    assert "S2" in _codes(_run(w, arc), "world_condition")


def test_5_dead_holder(w):
    arc = _arc([_req("beat:learn", InFrame(PF, "fact:secret", "is", "out"))])
    rep = _run(w, arc, (_clue("clue:d", ("fact:secret", "is", "out"), holder="person:dead"),))
    assert "S3" in _codes(rep, "beat:learn")
    twin = _run(w, arc, (_clue("clue:d", ("fact:secret", "is", "out")),))
    assert _codes(twin, "beat:learn") == []


def test_6_future_only_referent(w):
    arc = _arc([_req("beat:f", InFrame(PF, "person:future", "is", "here"))])
    assert "S4" in _codes(_run(w, arc, kind="continuation"), "person:future")
    fresh = _codes(_run(w, arc, kind="fresh"), "person:future")
    assert "S9" in fresh and "S4" not in fresh


def test_7_orphan_clue(w):
    arc = _arc([_req("beat:k", Occurred("k"))])
    rep = _run(w, arc, (_clue("clue:o", ("fact:secret", "is", "loose")),))
    assert "S7" in _codes(rep, "clue:o")
    herring = (_clue("clue:o", ("fact:secret", "is", "loose"), is_red_herring=True,
                     coverage_effect="false"),)
    assert "S7" not in _codes(_run(w, arc, herring))


def test_8_layers_and_witness(w):
    a = _req("beat:a", InFrame(PF, "fact:secret", "is", "out"))
    b = _req("beat:b", StateIs("obj:gate", "state", "open"))
    clock = Clock("clock:after_a", BeatAchieved("beat:a"),
                  effects=({"entity": "obj:gate", "attribute": "state", "value": "open"},),
                  bound_to="arc:main", rung=Rung.SURFACE)
    arc = _arc([a, b], clocks=[clock])
    cast = (_clue("clue:s", ("fact:secret", "is", "out")),)
    rep = _run(w, arc, cast)
    assert not [f for f in rep.findings if f.subject in ("beat:a", "beat:b")]
    la = rep.layers[repr(a.achievable_via)]
    lb = rep.layers[repr(b.achievable_via)]
    assert la < lb
    gone = _run(w, arc, ())
    wit = [x for f in gone.findings if f.subject == "beat:b" for x in f.witness]
    assert "S1" in _codes(gone, "beat:b") and wit


def test_17_restaged_only_located(w):
    arc = _arc([_req("beat:loc", Located("person:x", "place:far"))])
    assert _codes(_run(w, arc), "beat:loc") == ["S1"]
    assert _codes(_run(w, arc, reshape=True), "beat:loc") == ["S12"]


def test_19_plot_only_atom(w):
    ghost_clock = Clock("clock:never", StateIs("person:x", "is", "nowhere"),
                        effects=(), bound_to="arc:main", rung=Rung.SURFACE)
    ghost = Beat("beat:ghost", Phase.RISING, Weight.OPTIONAL,
                 achievable_via=ClockFired("clock:never"))
    arc = _arc([_req("beat:main", BeatAchieved("beat:ghost")), ghost], clocks=[ghost_clock])
    # P10 could write the StateIs the clock waits on, so with reshape the chain is miracle-only;
    # without reshape it is unproducible.
    assert _codes(_run(w, arc), "beat:main") == ["S1"]
    plot_only = _arc([_req("beat:main", ClockFired("clock:missing"))])
    assert _codes(_run(w, plot_only, reshape=True), "beat:main") == ["S1"]


def test_20_non_knows_inframe_stays_s1(w):
    arc = _arc([_req("beat:sess", InFrame("session:main", "x", "a", "v"))])
    assert _codes(_run(w, arc, reshape=True), "beat:sess") == ["S1"]


def test_21_closed_event_window(w):
    closed = _arc([_req("beat:late", Occurred("signal", until=int(H) - 5))])
    assert _codes(_run(w, closed, reshape=True), "beat:late") == ["S1"]
    open_ = _arc([_req("beat:late", AllOf((Occurred("signal_two"),)))])
    assert _codes(_run(w, open_, reshape=True), "beat:late") == ["S12"]


def test_9_detector_beat_is_produced(w):
    """The over-approximation holds for the generator's ordinary shape: a bare
    protagonist-only Occurred beat (the detector's candidate) is produced."""
    arc = _arc([_req("beat:ok", Occurred("door_opened"))])
    rep = _run(w, arc)
    assert not [f for f in rep.findings if f.subject in ("beat:ok", "world_condition")]


def test_12_revival_is_miracle_only(w):
    arc = _arc([_req("beat:rise", StateIs("person:dead", "alive", "true"))])
    assert _codes(_run(w, arc), "beat:rise") == ["S1"]
    assert _codes(_run(w, arc, reshape=True), "beat:rise") == ["S12"]


def test_13_revived_holder_then_delivers(w):
    """cr's oracle: a dead holder, revived through the shipped reshape path, makes the
    required clue deliverable — no S1/S2 before (S3 advisory, S12 at most) or after."""
    from construct.reshape import ReshapePlan, reshape_canon
    arc = _arc([_req("beat:learn", InFrame(PF, "fact:secret", "is", "out"))])
    cast = (_clue("clue:d", ("fact:secret", "is", "out"), holder="person:dead"),)
    before = _run(w, arc, cast, reshape=True)
    assert not {"S1", "S2"} & set(before.codes())
    assert "S3" in _codes(before, "beat:learn")
    from construct.arc import executor
    tok = executor.set_entry_epoch(STEP + 1000.0)   # play turns sit after the death row
    try:
        reshape_canon(w, ReshapePlan(slug="revive", state_rows=[
            {"entity": "person:dead", "attribute": "alive", "value": "true"}]), turn=5)
    finally:
        executor._ENTRY_EPOCH.reset(tok)
    after = analyse(arc, cast, PROT, PorcelainWorldReads(w), reshape=True)
    assert not [f for f in after.findings if f.subject in ("beat:learn", "world_condition")]


def test_14_refusal_clock_is_not_a_per_arc_finding(w):
    arc = _arc([_req("beat:ok", Occurred("door_opened"))])
    rep = _run(w, arc, reshape=True)
    assert not any("abandoned" in f.line() or f.subject == "clock:refusal"
                   for f in rep.findings)


def test_18_consequence_only_occurred(w):
    arc = _arc([_req("beat:sig", AllOf((Occurred("signal"),)))])
    assert _codes(_run(w, arc), "beat:sig") == ["S1"]
    assert _codes(_run(w, arc, reshape=True), "beat:sig") == ["S12"]


# --------------------------------------------------------------- wiring: report only

def test_10_fresh_build_reports_and_still_builds(tmp_path, caplog):
    import logging
    from construct import game
    from tests.test_world_polish import _ArcProvider, _GOOD_ARC, _bare_world
    caplog.set_level(logging.INFO, logger="construct.arc.soundness")
    world = _bare_world(tmp_path)
    spath = tmp_path / "bw_scenario.world"
    game._finalize_scenario(world, "bw", "Bare World", _ArcProvider([_GOOD_ARC]), spath,
                            endless=False, play_as="person a")
    try:
        assert spath.with_suffix(".meta.json").exists()             # published regardless
        lines = [r.getMessage() for r in caplog.records if "soundness [build]" in
                 r.getMessage()]
        assert any("beat:learn" in m and ("S1" in m or "S12" in m) for m in lines)
    finally:
        world.close()


def test_11_continuation_reports_with_the_play_cast(tmp_path, monkeypatch, caplog):
    import json
    import logging
    from construct import game, reshape
    from tests.test_reads_at_horizon import _make_horizon_slot
    from tests.test_reads_at_horizon import PROT as HPROT
    from tests.test_world_polish import _ContProvider
    caplog.set_level(logging.INFO, logger="construct.arc.soundness")
    monkeypatch.setattr(reshape, "reshape_enabled", lambda: False)
    name = _make_horizon_slot(tmp_path, monkeypatch)
    mpath = tmp_path / "worlds" / f"{name}.meta.json"
    meta = json.loads(mpath.read_text())
    meta["cast"] = {"cast": [{"id": "person:witness", "presence": "at_scene",
                              "location": "place:street",
                              "clues": [{"clue_id": "clue:c", "pillar_id": "pillar:p",
                                         "fact": {"entity": "fact:carried",
                                                  "attribute": "is", "value": "known"}}]}]}
    mpath.write_text(json.dumps(meta))
    proposal = {
        "protagonist": HPROT, "delta_type": "desire_at_cost",
        "tension": [HPROT, "drive:duty", "drive:fear"], "title": "Second",
        "hook": "A stranger waits under the lamp.",
        "beats": [{"id": "beat:carried", "phase": "rising", "weight": "required",
                   "kind": "player_learns", "entity": "fact:carried", "attribute": "is",
                   "value": "known"},
                  {"id": "beat:uncarried", "phase": "climax", "weight": "required",
                   "kind": "player_learns", "entity": "fact:loose", "attribute": "is",
                   "value": "new"}]}
    game.continue_episode(name, _ContProvider([proposal]), player_id="u1")
    lines = [r.getMessage() for r in caplog.records
             if "soundness [continuation]" in r.getMessage()]
    assert any("S1" in m and "uncarried" in m for m in lines), lines
    assert not any("beat:carried" in m and " S1 " in f" {m} " for m in lines)


def test_7b_s7_calibration_rules(w):
    """Calibration: S7 is skipped for a continuation (chapter 1's clues), and a clue that
    names another cast member is a discovery edge, not an orphan."""
    arc = _arc([_req("beat:k", Occurred("k"))])
    loose = (_clue("clue:o", ("fact:secret", "is", "loose")),)
    assert "S7" not in _codes(_run(w, arc, loose, kind="continuation"))
    naming = (_clue("clue:n", ("person:x", "seen_at", "place:far")),
              CastNode("person:x", presence="nearby", location="place:far"))
    assert "S7" not in _codes(_run(w, arc, naming))


def test_6b_clueless_cast_and_hook_ids_are_checked(w):
    """cr code review: a future-only cast member with no clues, or a future-only hook-cast
    id, is S4 at a continuation and S9 at a fresh build."""
    arc = _arc([_req("beat:ok", Occurred("door_opened"))])
    cast = (CastNode("person:future", holds_clues=()),)
    assert "S4" in _codes(_run(w, arc, cast, kind="continuation"), "person:future")
    assert "S9" in _codes(_run(w, arc, cast, kind="fresh"), "person:future")
    v = HorizonView(w, H)
    rep = analyse(arc, (), PROT, PorcelainWorldReads(v), horizon=H, world=v,
                  kind="continuation", reshape=False, hook_ids=("person:future",))
    assert "S4" in _codes(rep, "person:future")
