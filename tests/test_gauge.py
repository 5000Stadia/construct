"""Gauges — numeric quantities as live dramatic constraints (GAUGE-PRIMITIVE.md).

The foundation: a gauge is an `accrue` attribute that folds a baseline plus
signed deltas into a running total, and a `conditions.Quantity` atom triggers
on that total crossing a threshold — the continuous-constraint register (oxygen
at 0, speed below 50). No new engine surface: the number is read straight off
`state()`, exactly as diegetic time reads `elapsed_minutes`.
"""

import dataclasses

from construct.arc import io as arc_io
from construct.arc.conditions import (
    AtLeast, BeatAchieved, Quantity, Truth, TurnsQuiet, evaluate,
)
from construct.arc.executor import turn_time
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.arc.executor import arc_outcome
from construct.arc.grammar import Gauge
from construct.arc.io import expr_from_obj, expr_to_obj
from construct.adapter import PorcelainWorldReads
from construct.game import _world
from construct.gauge import (
    apply_gauge_terminals, commit_gauge, gauge_coloring, gauge_delta_for,
    gauge_lines, gauge_pass, gauge_urgency, read_gauge, seed_gauge,
)
from construct.semantics import ACCRUE_ATTRS, attribute_default

_OXY = Gauge("gauge:oxygen", "oxygen reserve", baseline=100.0, floor=0.0,
             base_delta=-8.0, costly_band=0.25,
             action_modifiers=(("run", -20.0), ("rest", +10.0)))


def _stub_arc(*, gauges=(), failure_when=None):
    """A minimal Arc whose world_condition (escape) is unmet, so terminal state
    comes only from the gauge floor under test."""
    shape = ConclusionShape("shape:main", "drive_inverted",
                            ("person:p", "drive:fear", "drive:resolve"),
                            world_condition=BeatAchieved("beat:escape"),
                            premise=BeatAchieved("beat:escape"),
                            refusal_variant_id="shape:refused")
    return Arc(arc_id="arc:main", protagonist="person:p", shape=shape,
               beats=(Beat("beat:escape", Phase.CLIMAX, Weight.REQUIRED,
                           achievable_via=BeatAchieved("beat:escape")),),
               clocks=(),
               refusal_clock=Clock("clock:refusal", TurnsQuiet(15), effects=(),
                                   bound_to="arc:main", rung=Rung.REFUSAL),
               climax_ready_k=1, climax_ready_beats=("beat:escape",),
               phase_budget={Phase.SETUP: 3, Phase.CLIMAX: 2},
               failure_when=failure_when, gauges=tuple(gauges))


def test_gauge_level_declared_accrue():
    assert "gauge_level" in ACCRUE_ATTRS
    assert attribute_default("gauge_level") == {"fold_policy": "accrue"}


def test_gauge_accrue_folds_signed_deltas(tmp_path):
    # Oxygen drains both turns; the accrue fold = baseline + signed deltas.
    w = _world(tmp_path / "g.world", "g", model=None)
    try:
        seed_gauge(w, "oxygen", 100.0, label="oxygen reserve")
        assert read_gauge(w, "oxygen") == 100.0
        commit_gauge(w, "oxygen", -30.0)
        commit_gauge(w, "oxygen", -25.0)
        assert read_gauge(w, "oxygen") == 45.0
        commit_gauge(w, "oxygen", +10.0)          # a sealed vent buys some back
        assert read_gauge(w, "oxygen") == 55.0
    finally:
        w.close()


def test_quantity_fires_on_threshold_crossing(tmp_path):
    w = _world(tmp_path / "q.world", "q", model=None)
    try:
        seed_gauge(w, "oxygen", 100.0)
        reads = PorcelainWorldReads(w)
        crit = Quantity("gauge:oxygen", "gauge_level", "<=", 10.0)
        assert evaluate(crit, reads) is Truth.FALSE          # 100 > 10
        commit_gauge(w, "oxygen", -92.0)                     # down to 8
        assert evaluate(crit, reads) is Truth.TRUE           # 8 <= 10 — the line is crossed
    finally:
        w.close()


def test_quantity_all_operators(tmp_path):
    w = _world(tmp_path / "ops.world", "ops", model=None)
    try:
        seed_gauge(w, "speed", 50.0)
        reads = PorcelainWorldReads(w)
        e = lambda op, v: evaluate(Quantity("gauge:speed", "gauge_level", op, v), reads)
        assert e("<", 50.0) is Truth.FALSE
        assert e("<=", 50.0) is Truth.TRUE
        assert e(">=", 50.0) is Truth.TRUE
        assert e(">", 49.0) is Truth.TRUE
        assert e("==", 50.0) is Truth.TRUE
        assert e("!=", 50.0) is Truth.FALSE
    finally:
        w.close()


def test_quantity_expr_io_roundtrip():
    # Cx 149 blocker 1: the atom must survive arc IO, not just direct evaluation.
    # The field is `cmp` (not `op`) precisely so it doesn't collide with the
    # serialization envelope's own "op" key — assert the comparator round-trips.
    q = Quantity("gauge:oxygen", "gauge_level", "<=", 0.0)
    obj = expr_to_obj(q)
    assert obj["op"] == "quantity" and obj["cmp"] == "<="     # envelope vs comparator, distinct
    assert expr_from_obj(obj) == q
    # nested inside a boolean combinator (how a real world_condition/failure_when holds it)
    nested = AtLeast(1, (q, BeatAchieved("beat:x")))
    assert expr_from_obj(expr_to_obj(nested)) == nested


def test_quantity_survives_full_arc_io(tmp_path):
    # The path real stored arcs take: a gauge floor in `failure_when` must persist
    # through arc_to_items -> ingest -> arc_from_frame (Cx 149: prove the cache path).
    floor = Quantity("gauge:oxygen", "gauge_level", "<=", 0.0)
    shape = ConclusionShape("shape:main", "drive_inverted",
                            ("person:p", "drive:fear", "drive:resolve"),
                            world_condition=BeatAchieved("beat:escape"),
                            premise=BeatAchieved("beat:escape"),
                            refusal_variant_id="shape:refused")
    arc = Arc(arc_id="arc:main", protagonist="person:p", shape=shape,
              beats=(Beat("beat:escape", Phase.CLIMAX, Weight.REQUIRED,
                          achievable_via=BeatAchieved("beat:escape")),),
              clocks=(),
              refusal_clock=Clock("clock:refusal", TurnsQuiet(15),
                                  effects=(), bound_to="arc:main", rung=Rung.REFUSAL),
              climax_ready_k=1, climax_ready_beats=("beat:escape",),
              phase_budget={Phase.SETUP: 3, Phase.CLIMAX: 2},
              failure_when=floor)
    w = _world(tmp_path / "arc.world", "arc", model=None)
    try:
        w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
        w.porcelain.ingest_structured(
            [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
              "valid_from": turn_time(0)}], frame="session:main")
        rebuilt = arc_io.arc_from_frame(PorcelainWorldReads(w))
        assert rebuilt.failure_when == floor          # the gauge floor survived the cache path
    finally:
        w.close()


def test_gauge_delta_action_modifiers():
    assert gauge_delta_for(_OXY, "I walk to the door") == -8.0          # base only
    assert gauge_delta_for(_OXY, "I RUN for the bay") == -28.0          # base + run
    assert gauge_delta_for(_OXY, "I rest a moment") == 2.0              # base + rest


def test_gauge_pass_drains_before_eval(tmp_path):
    w = _world(tmp_path / "gp.world", "gp", model=None)
    try:
        seed_gauge(w, "oxygen", 100.0)
        arc = _stub_arc(gauges=(_OXY,))
        lvl = gauge_pass(w, arc, "I run for the evac bay")
        assert lvl["gauge:oxygen"] == 72.0                             # 100 - 28
        gauge_pass(w, arc, "I keep moving")                            # base -8 -> 64
        assert read_gauge(w, "oxygen") == 64.0
    finally:
        w.close()


def test_gauge_folds_across_build_reopen(tmp_path):
    # REGRESSION (the false-green trap): an accrue baseline written at BUILD (under a
    # model) loses fold_policy across close/reopen, so deltas silently stop folding.
    # gauge_pass/ensure_gauges seed at RUNTIME instead, re-establishing accrue on the
    # reopened world — the clock.commit_elapsed pattern. A model=None build hides this,
    # so this test builds WITH a model (as production does).
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    rule = rule_classifier_fallback()

    def fb(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    path = tmp_path / "reopen.world"
    w = _world(path, "reopen", model=StubModel(fallback=fb))
    w.ingest_structured([{"entity": "place:x", "attribute": "kind", "value": "room",
                          "timeless": True}])
    w.close()                                                          # built + closed (no gauge seed)
    w2 = _world(path, "reopen", model=None)                            # reopen — the world that plays
    try:
        arc = _stub_arc(gauges=(_OXY,))
        gauge_pass(w2, arc, "walk")                                    # seeds 100 at runtime, -8 -> 92
        assert read_gauge(w2, "oxygen") == 92.0
        gauge_pass(w2, arc, "run")                                     # -28 -> 64 (folds across the reopen)
        assert read_gauge(w2, "oxygen") == 64.0
    finally:
        w2.close()


def test_gauge_floor_classifies_as_lost(tmp_path):
    # Cx's "right next test row": drain commits, the failure_when floor flips, and
    # arc_outcome classifies the turn LOST — not won, not None.
    w = _world(tmp_path / "lost.world", "lost", model=None)
    try:
        seed_gauge(w, "oxygen", 100.0)
        arc = apply_gauge_terminals(_stub_arc(gauges=(_OXY,)))
        assert arc.failure_when is not None                           # floor folded in
        reads = PorcelainWorldReads(w)
        # not yet terminal while the world_condition (escape) is unmet and oxygen holds
        assert arc_outcome(reads, arc) is None
        for _ in range(13):                                           # 13 * -8 = -104 -> below 0
            gauge_pass(w, arc, "hold position")
        assert read_gauge(w, "oxygen") <= 0.0
        assert arc_outcome(reads, arc) == "lost"                      # the floor draws the curtain
    finally:
        w.close()


def test_gauge_coloring_costly_only_when_low(tmp_path):
    w = _world(tmp_path / "color.world", "color", model=None)
    try:
        seed_gauge(w, "oxygen", 100.0)
        arc = _stub_arc(gauges=(_OXY,))
        assert gauge_coloring(arc, w) is None                         # 100% — clean
        commit_gauge(w, "oxygen", -80.0)                              # 20% — within costly band (25%)
        assert round(gauge_urgency(_OXY, read_gauge(w, "oxygen")), 2) == 0.20
        assert gauge_coloring(arc, w) == "costly"
    finally:
        w.close()


def test_gauge_lines_surface_level_and_urgency(tmp_path):
    w = _world(tmp_path / "lines.world", "lines", model=None)
    try:
        seed_gauge(w, "oxygen", 100.0)
        commit_gauge(w, "oxygen", -50.0)
        arc = _stub_arc(gauges=(_OXY,))
        lines = gauge_lines(arc, w)
        assert len(lines) == 1
        g, lvl, urg = lines[0]
        assert g.label == "oxygen reserve" and lvl == 50.0 and urg == 0.5
    finally:
        w.close()


def test_commit_elapsed_backfills_kind_for_old_world(tmp_path):
    # Cx 182 #2: an OLD world that already has elapsed minutes but NO `kind` row on time:elapsed
    # must be BACKFILLED so an authored time-deadline Quantity can fire (else has_entity is false →
    # INDETERMINATE → the deadline never fires). commit_elapsed seeds kind independently of baseline.
    from construct.arc.conditions import Quantity, Truth, evaluate
    from construct.clock import commit_elapsed
    w = _world(tmp_path / "old.world", "old", model=None)
    try:
        # old-shape: elapsed present, NO kind row (pre-fix build)
        w.porcelain.ingest_structured(
            [{"entity": "time:elapsed", "attribute": "elapsed_minutes", "value": 30,
              "value_type": "literal"}])
        reads = PorcelainWorldReads(w)
        assert not reads.has_entity("time:elapsed")           # the bug condition: kindless
        commit_elapsed(w, 40)                                  # backfills kind + folds to 70
        reads2 = PorcelainWorldReads(w)
        assert reads2.has_entity("time:elapsed")               # repaired
        assert evaluate(Quantity("time:elapsed", "elapsed_minutes", ">=", 60.0),
                        reads2) is Truth.TRUE                  # 70 >= 60 — the deadline can now fire
    finally:
        w.close()


def test_quantity_indeterminate_when_unseeded(tmp_path):
    # A gauge that was never seeded must NOT spuriously trip a terminal — it is
    # INDETERMINATE, not FALSE/TRUE (the never-fires-by-accident guarantee).
    w = _world(tmp_path / "u.world", "u", model=None)
    try:
        reads = PorcelainWorldReads(w)
        crit = Quantity("gauge:nonexistent", "gauge_level", "<=", 10.0)
        assert evaluate(crit, reads) is Truth.INDETERMINATE
    finally:
        w.close()
