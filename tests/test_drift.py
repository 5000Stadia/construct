"""DRIFT-HANDLING D1 (docs/design/DRIFT-HANDLING.md) — relocate-the-beat.

Three layers of coverage, matching the split test_cast_moves.py established for
the sibling #80 lane:

- PURE unit tests over `drift_state`/`rung_from_counters` and the SESSION-frame
  receipt helpers (construct/arc/drift.py) against tiny fakes — no world needed
  (the `salient_moments` discipline: explicit inputs, unit-testable in isolation).
- PURE unit tests over `validate_carrier_move`/`commit_carrier_move`
  (construct/turnloop.py) against a fake porcelain — the shared carrier-move
  surface `_world_tick` and R2's `_relocate_beat` both commit through.
- A smaller set of true end-to-end tests over `_drift_pass`/`_relocate_beat`
  (reusing tests/test_integration.py's `world`/`make_arc`/`seed_arc` fixtures)
  proving the seam wiring: pick -> commit -> confirm -> receipt -> directive.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from construct.adapter import PorcelainWorldReads
from construct.arc import drift
from construct.arc.conditions import Occurred, PacingCounters
from construct.arc.generator import _mark_development
from construct.arc.grammar import Beat, Phase, Rung, Weight
from construct.cast import CastNode, Clue
from construct.provider import StubProvider
from construct.turnloop import (
    CarrierMovePolicy,
    TurnTrace,
    _drift_pass,
    _world_tick,
    commit_carrier_move,
    confirm_carrier_moves,
    prepare_carrier_move,
    validate_carrier_move,
)

from tests.test_integration import PLAYER, make_arc, run_turn, seed_arc, world  # noqa: F401

PROTAGONIST = "person:player"
SCENE = "place:study"


# ============================================================================
# 1. Pure unit tests — construct/arc/drift.py
# ============================================================================

def test_drift_state_empty_without_pending_required():
    assert drift.drift_state([], Rung.CONFRONT, 999.0) == []


def test_drift_state_empty_below_relocate_rung():
    for r in (None, Rung.SURFACE, Rung.DRAW, Rung.CONVERGE):
        assert drift.drift_state(["beat:discover"], r, 999.0) == []


def test_drift_state_empty_below_quiet_gate():
    assert drift.drift_state(["beat:discover"], Rung.CONFRONT,
                             drift.RELOCATE_QUIET_MIN - 1.0) == []


def test_drift_state_d_soft_when_rung_and_quiet_both_satisfied():
    out = drift.drift_state(["beat:discover", "beat:other"], Rung.CONFRONT,
                            drift.RELOCATE_QUIET_MIN)
    assert out == [drift.Drift("beat:discover", "D-SOFT"),
                   drift.Drift("beat:other", "D-SOFT")]


def test_drift_state_refusal_rung_also_satisfies_the_floor():
    # REFUSAL sits ABOVE CONFRONT in the ladder — the floor is "at least
    # CONFRONT", not "exactly CONFRONT".
    out = drift.drift_state(["beat:discover"], Rung.REFUSAL, drift.RELOCATE_QUIET_MIN)
    assert out == [drift.Drift("beat:discover", "D-SOFT")]


@pytest.mark.parametrize("turns_quiet,expected", [
    (0, None), (2, None), (3, Rung.SURFACE), (4, Rung.SURFACE),
    (5, Rung.DRAW), (7, Rung.CONVERGE), (9, Rung.CONFRONT), (50, Rung.CONFRONT),
])
def test_rung_from_counters_matches_the_shared_threshold_ladder(turns_quiet, expected):
    counters = PacingCounters(turns_elapsed=turns_quiet, turns_quiet=turns_quiet)
    assert drift.rung_from_counters(counters) is expected


class _FakeReads:
    def __init__(self):
        self.rows: dict[tuple[str, str], object] = {}

    def state(self, entity, attribute, *, frame="canon"):
        return self.rows.get((entity, attribute))


class _FakeWorld:
    """`world.porcelain.ingest_structured(rows, frame=...)` -> folds straight
    into a `_FakeReads`-shared table (a session-frame round trip stand-in)."""

    def __init__(self, reads: _FakeReads):
        self._reads = reads
        self.porcelain = self

    def ingest_structured(self, rows, frame=None, **_kw):
        for r in rows:
            self._reads.rows[(r["entity"], r["attribute"])] = r["value"]
        return {"rows": [{"entity": r["entity"], "attribute": r["attribute"]} for r in rows]}


def test_nudge_receipts_round_trip_and_no_re_preach_signal():
    reads = _FakeReads()
    world = _FakeWorld(reads)
    assert drift.last_nudge_thread(reads) is None
    assert drift.last_nudge_min(reads) is None
    drift.mark_nudge(world, "thread-a", 100.0, turn=3)
    assert drift.last_nudge_thread(reads) == "thread-a"
    assert drift.last_nudge_min(reads) == 100.0


def test_nudge_suppressed_two_distinct_constants():
    reads = _FakeReads()
    world = _FakeWorld(reads)
    # No diegetic clock, or no prior nudge yet: never suppressed.
    assert drift.nudge_suppressed(reads, None) is False
    assert drift.nudge_suppressed(reads, 10.0) is False
    drift.mark_nudge(world, "thread-a", 100.0, turn=1)
    # Within NUDGE_QUIET_MIN (60.0) of the last nudge: suppressed.
    assert drift.nudge_suppressed(reads, 100.0 + drift.NUDGE_QUIET_MIN - 1) is True
    # At/after the boundary: no longer suppressed.
    assert drift.nudge_suppressed(reads, 100.0 + drift.NUDGE_QUIET_MIN) is False
    # RELOCATE_QUIET_MIN is a DIFFERENT constant (§3 R1 point 2, cr r2 oracle gap 7).
    assert drift.NUDGE_QUIET_MIN != drift.RELOCATE_QUIET_MIN


def test_relocation_receipt_round_trip_and_idempotency_signal():
    reads = _FakeReads()
    world = _FakeWorld(reads)
    assert drift.relocation_receipt(reads, "beat:discover") is None
    drift.mark_relocation(world, "beat:discover", "place:flat", "place:study", turn=5)
    receipt = drift.relocation_receipt(reads, "beat:discover")
    assert receipt == {"beat_id": "beat:discover", "old_staging": "place:flat",
                       "new_staging": "place:study"}


def test_record_relocate_declined_never_writes_a_relocation_receipt():
    reads = _FakeReads()
    world = _FakeWorld(reads)
    drift.record_relocate_declined(world, turn=1, beat_id="beat:discover", reason="low_confidence")
    assert drift.relocation_receipt(reads, "beat:discover") is None


def test_thirty_contemplation_turns_yield_zero_relocate_and_at_most_one_nudge():
    """§3 R1 point 2 / §7 D1's oracle: 30 turns spanning only FIVE diegetic
    minutes total (turns are free — contemplation burns near-zero diegetic
    time) must yield zero R2 responses (the 240-minute quiet gate never
    opens) and AT MOST ONE R1 nudge (NUDGE_QUIET_MIN=60 outlasts the whole
    5-minute span once the first nudge fires — the two-constant guarantee)."""
    reads = _FakeReads()
    world = _FakeWorld(reads)
    development_baseline = 0.0
    nudges_fired = 0
    for i in range(30):
        minutes_now = i * (5.0 / 29)  # 30 samples spanning exactly 5 diegetic minutes
        # R1: fire iff not suppressed by the diegetic cadence gate.
        if not drift.nudge_suppressed(reads, minutes_now):
            drift.mark_nudge(world, "the-one-unwalked-thread", minutes_now, turn=i)
            nudges_fired += 1
        # R2: the diegetic quiet gate, off the SAME development baseline.
        quiet_minutes = minutes_now - development_baseline
        assert drift.drift_state(["beat:discover"], Rung.CONFRONT, quiet_minutes) == []
    assert nudges_fired == 1


# ============================================================================
# 2. Pure unit tests — validate_carrier_move / commit_carrier_move
# ============================================================================

@dataclass
class _Receipt:
    rows: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"rows": self.rows}


class _FakePorcelain:
    """Mirrors tests/test_cast_moves.py's `_FakeP` shape (entities/facts/locate/
    ingest_structured) — the porcelain surface `validate_carrier_move`'s
    place-fold read and `commit_carrier_move`'s commit both need."""

    def __init__(self, *, place_heads=("place:study", "place:flat"),
                 closures: dict | None = None, raise_on_ingest: bool = False):
        self.calls: list[tuple[list[dict], str]] = []
        self.receipt_queue: list[_Receipt] = []
        self.place_heads = list(place_heads)
        self.closures = dict(closures or {})
        self.raise_on_ingest = raise_on_ingest

    def ingest_structured(self, rows, classify: str = "inline", **_kw):
        if self.raise_on_ingest:
            raise RuntimeError("boom")
        rows = list(rows)
        self.calls.append((rows, classify))
        if self.receipt_queue:
            return self.receipt_queue.pop(0)
        return _Receipt([{"entity": r["entity"], "attribute": r["attribute"]} for r in rows])

    def entities(self, frame: str, prefix: str | None = None, as_of=None) -> list[str]:
        return [e for e in self.place_heads if prefix is None or e.startswith(prefix)]

    def facts(self, frame: str, entity: str | None = None, as_of=None, **_kw) -> list[dict]:
        return [{"entity": e} for e in self.closures.get(entity, [entity])]


class _FakeWorldP:
    def __init__(self, porcelain: _FakePorcelain):
        self.porcelain = porcelain


def _policy(mode: str, **overrides) -> CarrierMovePolicy:
    base = dict(mode=mode, scene=SCENE, protagonist=PROTAGONIST)
    base.update(overrides)
    return CarrierMovePolicy(**base)


def test_same_person_destination_accepted_relocate_rejected_world_tick():
    reads = _FakePorcelain()
    v_relocate = validate_carrier_move(reads, "person:rival", SCENE, _policy("relocate"))
    v_tick = validate_carrier_move(reads, "person:rival", SCENE, _policy("world_tick"))
    assert v_relocate.ok is True
    assert v_tick.ok is False and v_tick.reason == "world_tick_into_scene"


def test_same_person_destination_accepted_world_tick_rejected_relocate():
    reads = _FakePorcelain()
    v_tick = validate_carrier_move(reads, "person:rival", "place:flat", _policy("world_tick"))
    v_relocate = validate_carrier_move(reads, "person:rival", "place:flat", _policy("relocate"))
    assert v_tick.ok is True
    assert v_relocate.ok is False and v_relocate.reason == "relocate_off_scene"


def test_validate_carrier_move_rejects_protagonist():
    reads = _FakePorcelain()
    v = validate_carrier_move(reads, PROTAGONIST, "place:flat", _policy("world_tick"))
    assert v.ok is False and v.reason == "protagonist"


def test_validate_carrier_move_rejects_anchored():
    reads = _FakePorcelain()
    policy = _policy("world_tick", anchored=frozenset({"person:rival"}))
    v = validate_carrier_move(reads, "person:rival", "place:flat", policy)
    assert v.ok is False and v.reason == "anchored"


def test_validate_carrier_move_rejects_companion():
    reads = _FakePorcelain()
    policy = _policy("relocate", companions=frozenset({"person:rival"}))
    v = validate_carrier_move(reads, "person:rival", SCENE, policy)
    assert v.ok is False and v.reason == "companion"


def test_validate_carrier_move_rejects_future_horizon_destination():
    # "place:unseen" is not in the canon place roster at all — no head at `_h`.
    reads = _FakePorcelain(place_heads=("place:study", "place:flat"))
    v = validate_carrier_move(reads, "person:rival", "place:unseen", _policy("world_tick"))
    assert v.ok is False and v.reason == "future_horizon_destination"


def test_commit_carrier_move_confirmed():
    world = _FakeWorldP(_FakePorcelain())
    result = commit_carrier_move(world, "person:rival", SCENE, turn=1, policy=_policy("relocate"))
    assert result.ok is True and result.confirmed is True
    assert world.porcelain.calls  # the commit actually happened


def test_commit_carrier_move_guard_rejected_never_ingests():
    porcelain = _FakePorcelain()
    world = _FakeWorldP(porcelain)
    policy = _policy("relocate", anchored=frozenset({"person:rival"}))
    result = commit_carrier_move(world, "person:rival", SCENE, turn=1, policy=policy)
    assert result.ok is False and result.confirmed is False
    assert porcelain.calls == []  # guard-rejected — never even attempted an ingest


def test_commit_carrier_move_structurally_skipped_unconfirmed():
    porcelain = _FakePorcelain()
    porcelain.receipt_queue = [_Receipt([])]  # fail-open ingest: empty receipt, no raise
    world = _FakeWorldP(porcelain)
    result = commit_carrier_move(world, "person:rival", SCENE, turn=1, policy=_policy("relocate"))
    assert result.ok is True and result.confirmed is False and result.reason == "unconfirmed"


def test_commit_carrier_move_failed_ingest_never_propagates():
    porcelain = _FakePorcelain(raise_on_ingest=True)
    world = _FakeWorldP(porcelain)
    result = commit_carrier_move(world, "person:rival", SCENE, turn=1, policy=_policy("relocate"))
    assert result.ok is True and result.confirmed is False and result.reason == "ingest_failed"


# ============================================================================
# 3. End-to-end — _drift_pass / _relocate_beat over a real world
# ============================================================================

def _rival_cast() -> dict:
    return {
        "person:rival": CastNode(
            node_id="person:rival",
            holds_clues=(Clue(clue_id="clue:culprit", pillar_id="pillar:main",
                              surface_fact=("fact:secret", "culprit", "person:rival")),),
            location="place:flat",
        ),
    }


def test_relocate_moves_carrier_confirms_before_directive_and_writes_receipt(world):
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)  # the quiet baseline: development at t=0
    trace = TurnTrace(turn=1)
    provider = StubProvider([
        {"carrier": "person:rival", "staging_line": "Rival turns up at your door, edgy.",
         "confidence": 0.9},
    ])
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    # The carrier actually moved, in canon, INTO the player's scene.
    assert p.locate("person:rival")[0] == SCENE
    assert trace.relocations == [("beat:discover", SCENE)]
    assert trace.drift == [("beat:discover", "D-SOFT")]
    assert "Rival turns up at your door, edgy." in trace.relocate_directive
    receipt = drift.relocation_receipt(live_reads, "beat:discover")
    assert receipt is not None and receipt["new_staging"] == SCENE


def test_relocate_declines_on_low_confidence_no_directive_no_receipt(world):
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([
        {"carrier": "person:rival", "staging_line": "Rival turns up.", "confidence": 0.1},
    ])
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    # trace.drift means CLASSIFICATION (cr finding 4): the beat was classified
    # D-SOFT even though the response declined; relocations stays success-only.
    assert trace.drift == [("beat:discover", "D-SOFT")]
    assert trace.relocations == []
    assert trace.relocate_directive == ""
    assert drift.relocation_receipt(live_reads, "beat:discover") is None
    # And the carrier never actually moved.
    assert p.locate("person:rival")[0] == "place:flat"


def test_relocate_no_op_without_diegetic_quiet_or_high_rung(world):
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([])  # must never be called
    # Rung too low: no D-SOFT drift regardless of quiet minutes.
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.DRAW)
    assert trace.relocations == []
    assert provider.calls == []
    # Quiet gate not yet open: no D-SOFT drift regardless of rung.
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=2, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=10.0, rung=Rung.CONFRONT)
    assert trace.relocations == []
    assert provider.calls == []


def test_relocate_declines_without_a_clue_holder_for_the_target(world):
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([])  # must never be called — declined before the cohort
    empty_cast = {"person:rival": CastNode(node_id="person:rival", holds_clues=(),
                                           location="place:flat")}
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=empty_cast, scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    assert trace.drift == [("beat:discover", "D-SOFT")]  # classified (finding 4)
    assert trace.relocations == []
    assert provider.calls == []
    assert drift.relocation_receipt(live_reads, "beat:discover") is None


def test_one_relocation_per_beat_blocks_a_second_attempt(world):
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace1 = TurnTrace(turn=1)
    provider1 = StubProvider([
        {"carrier": "person:rival", "staging_line": "Rival turns up at your door, edgy.",
         "confidence": 0.9},
    ])
    _drift_pass(world, p, live_reads=live_reads, trace=trace1, provider=provider1,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    assert trace1.relocations == [("beat:discover", SCENE)]

    # Second attempt, later turn, same beat still pending (never achieved): the
    # existing receipt must block it BEFORE any cohort call is attempted.
    trace2 = TurnTrace(turn=2)
    provider2 = StubProvider([])  # queue exhausted -> would raise if ever called
    _drift_pass(world, p, live_reads=live_reads, trace=trace2, provider=provider2,
               turn=2, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=600.0, rung=Rung.CONFRONT)
    assert trace2.drift == [("beat:discover", "D-SOFT")]  # still CLASSIFIED (finding 4)
    assert trace2.relocations == []
    assert provider2.calls == []


def test_relocate_pick_cohort_failure_is_fail_open(world):
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([])  # exhausted queue -> ProviderTransportError inside relocate_pick
    # Must not raise out of `_drift_pass` — fail-open, the turn survives quiet.
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    assert trace.drift == [("beat:discover", "D-SOFT")]  # classified (finding 4)
    assert trace.relocations == []
    assert trace.relocate_directive == ""


# ============================================================================
# 4. cr RED round fixes (findings 1-5)
# ============================================================================

SESSION = "session:main"


def _two_node_cast() -> dict:
    """The rival (off-screen original holder) + a present witness equivalent."""
    cast = _rival_cast()
    cast["person:witness"] = CastNode(node_id="person:witness",
                                      surface_role="the gossiping porter")
    return cast


# ---- finding 1: the conjured-carrier guard + the informed prompt --------------------

def test_relocate_rejects_a_conjured_carrier_whole(world):
    # cr finding 1 (reproduced): a model-returned carrier OUTSIDE the licensed set
    # (matched holders + present cast equivalents) must never reach canon — no
    # ingest, no directive, no relocation receipt; only the decline telemetry.
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([
        {"carrier": "person:invented", "staging_line": "A stranger arrives.",
         "confidence": 0.95},
    ])
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    assert trace.drift == [("beat:discover", "D-SOFT")]  # classified, declined
    assert trace.relocations == []
    assert trace.relocate_directive == ""
    assert drift.relocation_receipt(live_reads, "beat:discover") is None
    assert not PorcelainWorldReads(world).has_entity("person:invented")  # never minted/moved
    assert "relocate_pick (unlicensed carrier)" in trace.dropped_cohorts
    # The decline telemetry landed (event-entity rows read via events()/frame_rows,
    # the `_last_try_turn` pattern — event: ids don't fold through state()).
    assert [e.event_id for e in live_reads.events(kind="relocate_declined",
                                                  frame=SESSION)] \
        == ["event:relocate_declined_discover_1"]
    assert any(r.attribute == "reason" and r.value == "unlicensed_carrier"
               for r in live_reads.frame_rows(
                   SESSION, entity="event:relocate_declined_discover_1"))


def test_relocate_prompt_names_offscreen_holder_spines_and_fuel(world):
    # cr finding 1 (prompt half) + 1b: the cohort is INFORMED — the off-screen
    # original holder is named (id + handle + whereabouts), present cast carry
    # their spines, and the turn's real salience fuel rides along.
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([
        # Re-home onto the PRESENT witness — licensed, no move needed.
        {"carrier": "person:witness", "staging_line": "The porter leans in with it.",
         "confidence": 0.9},
    ])
    fuel = ["the player's action touched 'person:witness', who has a standing drive"]
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_two_node_cast(), scene=SCENE,
               npcs=["person:witness"], horizon=None, minutes_now=300.0,
               rung=Rung.CONFRONT, fuel=fuel,
               spines={"person:witness": "drive: gossip; fear: irrelevance"})
    prompt = provider.calls[0][0]
    assert "person:rival" in prompt                      # the original holder, NAMED
    assert "OFF-SCREEN" in prompt                        # ...and marked off-screen
    assert "place:flat" in prompt                        # ...with whereabouts
    assert "drive: gossip; fear: irrelevance" in prompt  # present spines
    assert fuel[0] in prompt                             # real salience fuel
    # The re-home committed: directive + receipt, and the holder never traveled.
    assert trace.relocations == [("beat:discover", SCENE)]
    assert "The porter leans in with it." in trace.relocate_directive
    assert drift.relocation_receipt(live_reads, "beat:discover") is not None
    assert p.locate("person:rival")[0] == "place:flat"


# ---- finding 2: a turn that just developed is never drift ---------------------------

def test_drift_pass_suppressed_when_turn_already_developed(world):
    # cr finding 2 (reproduced): the ledger write for this turn's clock/beat
    # developments lands AFTER drift — the trace is the honest same-turn signal.
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    provider = StubProvider([])  # must never be called
    for field_name, value in (("clocks_fired", ["clock:escalate"]),
                              ("beats_achieved", ["beat:other"]),
                              ("reveals", [("a", "b")])):
        trace = TurnTrace(turn=1)
        setattr(trace, field_name, value)
        _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
                   turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
                   horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
        assert trace.drift == []          # suppressed BEFORE classification
        assert trace.relocations == []
        assert provider.calls == []


def test_run_turn_clock_firing_suppresses_same_turn_drift(world):
    # cr finding 2 oracle: a REAL turn where a clock fires while a required
    # delivery beat is pending and every other drift condition is favorable
    # (rung CONFRONT, 300 quiet diegetic minutes) → no D-SOFT response.
    from construct.arc.executor import turn_time
    from construct.clock import commit_elapsed
    arc = make_arc()
    seed_arc(world, arc)
    # 10 quiet turns: turns_quiet >= 9 (drift rung CONFRONT) AND TurnsQuiet(4)
    # makes clock:escalate fire THIS turn.
    world.porcelain.ingest_structured([
        {"entity": f"event:turn_{i}", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(i)} for i in range(1, 11)
    ], frame=SESSION)
    commit_elapsed(world, 300)          # diegetic quiet gate WOULD be open...
    _mark_development(world, 0.0, 0)    # ...against the old baseline
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""},
        {"prose": "The pressure builds; nothing else moves."},
    ])
    result = run_turn(world, arc, provider, "I wait and think.", turn=11,
                      cast=_rival_cast())
    assert "clock:escalate" in result.trace.clocks_fired   # the development happened
    assert result.trace.drift == []                        # ...and suppressed drift
    assert result.trace.relocations == []
    assert world.porcelain.locate("person:rival")[0] == "place:flat"


# ---- finding 3: confirmed move → directive unconditional; bookkeeping fail-open -----

def test_mark_relocation_failure_never_suppresses_the_directive(world, monkeypatch):
    # cr finding 3 (reproduced): a bookkeeping failure AFTER the confirmed canon
    # move must not erase the licensed directive (the carrier has already moved —
    # a silent arrival is the unacceptable state; a missing receipt is the
    # acceptable one).
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([
        {"carrier": "person:rival", "staging_line": "Rival turns up, edgy.",
         "confidence": 0.9},
    ])
    def _boom(*_a, **_kw):
        raise RuntimeError("session write lost")
    monkeypatch.setattr(drift, "mark_relocation", _boom)
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    assert p.locate("person:rival")[0] == SCENE            # the move stands
    assert "Rival turns up, edgy." in trace.relocate_directive  # the directive SURVIVES
    assert trace.relocations == [("beat:discover", SCENE)]
    assert "mark_relocation failed" in trace.dropped_cohorts
    # The honest partial state: no receipt (a rare re-relocation is acceptable).
    assert drift.relocation_receipt(live_reads, "beat:discover") is None


def test_mark_development_failure_never_suppresses_the_directive(world, monkeypatch):
    import construct.turnloop as turnloop_mod
    arc = make_arc()
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([
        {"carrier": "person:rival", "staging_line": "Rival turns up, edgy.",
         "confidence": 0.9},
    ])
    def _boom(*_a, **_kw):
        raise RuntimeError("ledger write lost")
    monkeypatch.setattr(turnloop_mod, "_mark_development", _boom)
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    assert "Rival turns up, edgy." in trace.relocate_directive  # the directive SURVIVES
    assert trace.relocations == [("beat:discover", SCENE)]
    # Here the receipt DID land (mark_relocation ran before the ledger failure).
    assert drift.relocation_receipt(live_reads, "beat:discover") is not None
    assert "_mark_development (relocation) failed" in trace.dropped_cohorts


def test_mark_nudge_failure_never_sinks_the_turn(world, monkeypatch):
    # cr finding 3 (R1 half): the nudge's session bookkeeping write is fail-open —
    # its failure costs only next-turn cadence/exclusion, never this turn.
    from construct.arc.executor import turn_time
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": f"event:turn_{i}", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(i)} for i in range(1, 6)
    ], frame=SESSION)  # quiet >= 3 → a rung; the canon/player diff supplies threads
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""},
        {"thread": "fact:secret · culprit · person:rival",
         "directive": "A runner arrives with word from the archive."},
        {"prose": "A runner slips through the door with a sealed note."},
    ])
    def _boom(*_a, **_kw):
        raise RuntimeError("session write lost")
    monkeypatch.setattr(drift, "mark_nudge", _boom)
    result = run_turn(world, arc, provider, "I keep to my desk.", turn=6)
    assert result.prose                                     # the turn SURVIVED
    assert result.trace.nudge == "A runner arrives with word from the archive."
    assert "mark_nudge failed" in result.trace.dropped_cohorts


# ---- finding 4: trace.drift means classification --------------------------------

def test_non_inframe_pending_beat_classified_but_never_relocated(world):
    # A pending REQUIRED beat with no delivery target (Occurred, not InFrame) is
    # CLASSIFIED — trace.drift records it — but R2 has nothing to relocate: no
    # cohort call, no relocation, no receipt.
    occ = Beat("beat:confront", Phase.CLIMAX, Weight.REQUIRED,
               achievable_via=Occurred("event:confront"))
    arc = replace(make_arc(), beats=(occ,), climax_ready_beats=("beat:confront",))
    seed_arc(world, arc)
    live_reads = PorcelainWorldReads(world)
    p = world.porcelain
    _mark_development(world, 0.0, 0)
    trace = TurnTrace(turn=1)
    provider = StubProvider([])  # must never be called
    _drift_pass(world, p, live_reads=live_reads, trace=trace, provider=provider,
               turn=1, arc=arc, cast=_rival_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=300.0, rung=Rung.CONFRONT)
    assert trace.drift == [("beat:confront", "D-SOFT")]
    assert trace.relocations == []
    assert provider.calls == []


# ---- finding 5: world-tick consumes BOTH layers, one batch ----------------------

def test_prepare_carrier_move_returns_row_or_rejection():
    reads = _FakePorcelain()
    row, verdict = prepare_carrier_move(reads, "person:rival", SCENE, 3,
                                        _policy("relocate"))
    assert verdict.ok is True
    assert row == {"entity": "person:rival", "attribute": "in", "value": SCENE,
                   "value_type": "entity", "valid_from": row["valid_from"]}
    row2, verdict2 = prepare_carrier_move(
        reads, "person:rival", SCENE, 3,
        _policy("relocate", anchored=frozenset({"person:rival"})))
    assert row2 is None and verdict2.reason == "anchored"


def test_confirm_carrier_moves_per_person_over_a_mixed_receipt():
    rows = [{"entity": "person:maud", "attribute": "in", "value": "place:market"},
            {"entity": "person:cray", "attribute": "in", "value": "place:market"}]
    receipt = [
        {"entity": "person:maud", "attribute": "in"},
        # cray's move skipped by the engine — absent from the receipt
        {"entity": "event:tick_x_3", "attribute": "kind"},   # other-batch rows never interfere
        {"entity": "event:tick_x_3", "attribute": "agent"},
    ]
    assert confirm_carrier_moves(rows, receipt) == frozenset({"person:maud"})
    assert confirm_carrier_moves([], receipt) == frozenset()


class _TickProxy:
    """Wraps a real porcelain for `_world_tick`'s `p` argument: counts
    `ingest_structured` calls and optionally doctors the returned receipt."""

    def __init__(self, inner, doctor=None):
        self._inner = inner
        self._doctor = doctor
        self.ingests = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def ingest_structured(self, rows, **kw):
        self.ingests += 1
        receipt = self._inner.ingest_structured(rows, **kw)
        return self._doctor(receipt) if self._doctor else receipt


def _tick_world(world) -> dict:
    """The world-tick fixture shape (mirrors test_integration's `_tick_setup`)."""
    from construct.arc.executor import turn_time
    world.porcelain.ingest_structured([
        {"entity": "place:market", "attribute": "kind", "value": "market", "timeless": True},
        {"entity": "place:lane", "attribute": "kind", "value": "lane", "timeless": True},
        {"entity": "person:maud", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:maud", "attribute": "in", "value": "place:lane"},
        {"entity": "person:cray", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:cray", "attribute": "in", "value": "place:lane"},
    ])
    world.porcelain.ingest_structured([
        {"entity": "person:maud", "attribute": "last_seen_min", "value": 100.0,
         "valid_from": turn_time(1)},
        {"entity": "person:cray", "attribute": "last_seen_min", "value": 100.0,
         "valid_from": turn_time(1)},
    ], frame=SESSION)
    return {
        "person:maud": CastNode("person:maud", surface_role="coster"),
        "person:cray": CastNode("person:cray", surface_role="foreman"),
    }


_TICKS = [{"ticks": [
    {"member": "person:maud", "kind": "moved",
     "detail": "wheeled her barrow across to the market", "moves_to": "place:market",
     "with_member": ""},
    {"member": "person:cray", "kind": "sent_word",
     "detail": "sent a boy round with a note", "moves_to": "", "with_member": ""},
]}]


def test_world_tick_one_ingest_and_confirmed_move_reported(world):
    # cr finding 5 oracle 1: the mixed batch (a move + an event) stays ONE ingest
    # call; the confirmed move is reported through the shared confirm layer.
    arc = make_arc()
    seed_arc(world, arc)
    cast = _tick_world(world)
    trace = TurnTrace(turn=3)
    trace.movement_status = "clear"
    proxy = _TickProxy(world.porcelain)
    _world_tick(world, proxy, arc, trace, StubProvider(list(_TICKS)), 3, cast=cast,
                npcs=[], entry_scene="place:lane", scene="place:study",
                live_reads=PorcelainWorldReads(world), minutes_now=200.0)
    assert proxy.ingests == 1                              # never split (finding 5)
    assert trace.world_tick == ["person:maud:moved", "person:cray:sent_word"]
    assert world.porcelain.locate("person:maud")[0] == "place:market"


def test_world_tick_skipped_move_row_not_reported_as_moved(world):
    # cr finding 5 oracle 2: a move row the engine skipped (absent from the
    # receipt) is NOT reported as moved; the batch's other ticks still report.
    from construct.turnloop import _receipt_rows
    arc = make_arc()
    seed_arc(world, arc)
    cast = _tick_world(world)
    trace = TurnTrace(turn=3)
    trace.movement_status = "clear"
    def _drop_move(receipt):
        rows = [r for r in _receipt_rows(receipt)
                if not (r.get("entity") == "person:maud" and r.get("attribute") == "in")]
        return {"rows": rows}
    proxy = _TickProxy(world.porcelain, doctor=_drop_move)
    _world_tick(world, proxy, arc, trace, StubProvider(list(_TICKS)), 3, cast=cast,
                npcs=[], entry_scene="place:lane", scene="place:study",
                live_reads=PorcelainWorldReads(world), minutes_now=200.0)
    assert "person:maud:moved" not in trace.world_tick     # unconfirmed → not reported
    assert trace.world_tick == ["person:cray:sent_word"]
