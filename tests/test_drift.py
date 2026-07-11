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


# ============================================================================
# 4. D2 — the closure-witness contract, classifier, occurrence rule, R3
# ============================================================================

from construct.arc.conditions import (  # noqa: E402
    AllOf, AnyOf, AtLeast, BeatAchieved, ClockFired, EventRow, Not, StateIs,
)
from construct.arc.drift import (  # noqa: E402
    classify_closure, closure_witness_of, on_expiry_items, read_closure_witness,
    read_on_expiry,
)
from construct.arc.executor import PLOT, beat_pass, turn_time  # noqa: E402
from construct.turnloop import _absence_beat  # noqa: E402


class _WitnessReads:
    """Just enough WorldReads for witness-walk unit tests: StateIs (entities +
    state), ClockFired (clock_fired events), BeatAchieved (plot status)."""

    def __init__(self, *, entities=(), state=None, firings=()):
        self._entities = set(entities)
        self._state = dict(state or {})
        self._firings = list(firings)  # (clock_id, at, event_id)

    def has_entity(self, eid):
        return eid in self._entities

    def state(self, entity, attribute, *, frame="canon"):
        return self._state.get((entity, attribute))

    def events(self, *, kind=None, frame="canon", **_kw):
        return [EventRow(event_id=e, kind="clock_fired", agents=(c,), at=at)
                for (c, at, e) in self._firings]


def _fired(clock="clock:deadline", at=5, eid="event:clock_deadline_5"):
    return (clock, at, eid)


def test_witness_anyof_clock_only_branch_is_clock_caused():
    # AnyOf(clock TRUE, state FALSE): the clock branch alone decided — forcing
    # clocks FALSE flips the whole expr -> clock_caused, firing event captured.
    reads = _WitnessReads(entities={"person:x"},
                          state={("person:x", "role"): "librarian"},
                          firings=[_fired()])
    expr = AnyOf((ClockFired("clock:deadline"), StateIs("person:x", "role", "dead")))
    w = closure_witness_of(expr, reads, turn=7)
    assert w["clock_caused"] is True
    assert w["firing_events"] == ["event:clock_deadline_5"]
    assert [l["kind"] for l in w["true_leaves"]] == ["ClockFired"]
    assert w["unknown_leaves"] == []
    assert classify_closure(w) == "D-MISSED"


def test_witness_mixed_anyof_world_state_sufficed_is_not_clock_caused():
    # AnyOf(clock TRUE, state TRUE): with clocks forced FALSE the state half
    # still closes it — the clock was incidental -> D-HARD (cr/spec: mixed
    # compound where the world-state half sufficed).
    reads = _WitnessReads(entities={"person:x"},
                          state={("person:x", "role"): "dead"},
                          firings=[_fired()])
    expr = AnyOf((ClockFired("clock:deadline"), StateIs("person:x", "role", "dead")))
    w = closure_witness_of(expr, reads, turn=7)
    assert {l["kind"] for l in w["true_leaves"]} == {"ClockFired", "StateIs"}
    assert w["clock_caused"] is False
    assert classify_closure(w) == "D-HARD"


def test_witness_allof_records_all_leaves_and_clock_is_necessary():
    reads = _WitnessReads(entities={"person:x"},
                          state={("person:x", "role"): "dead"},
                          firings=[_fired()])
    expr = AllOf((ClockFired("clock:deadline"), StateIs("person:x", "role", "dead")))
    w = closure_witness_of(expr, reads, turn=7)
    assert len(w["true_leaves"]) == 2          # AllOf: all leaves
    assert w["clock_caused"] is True           # remove the clock -> AllOf fails
    assert classify_closure(w) == "D-MISSED"


def test_witness_atleast_records_satisfied_leaves():
    reads = _WitnessReads(entities={"person:x", "person:y"},
                          state={("person:x", "role"): "dead",
                                 ("person:y", "role"): "alive"},
                          firings=[_fired()])
    expr = AtLeast(2, (ClockFired("clock:deadline"),
                       StateIs("person:x", "role", "dead"),
                       StateIs("person:y", "role", "dead")))
    w = closure_witness_of(expr, reads, turn=7)
    assert len(w["true_leaves"]) == 2          # the satisfied pair, not the FALSE leaf
    assert w["clock_caused"] is True           # without the clock only 1 of 2
    assert classify_closure(w) == "D-MISSED"


def test_witness_not_and_unknown_atoms():
    # Not(BeatAchieved FALSE) is TRUE: the child leaf records under its OWN
    # truth (FALSE -> in neither bucket). An UNKNOWN StateIs (missing entity)
    # lands in unknown_leaves and drops classification to D-HARD.
    reads = _WitnessReads(entities=set(), state={}, firings=[_fired()])
    expr = AllOf((Not(BeatAchieved("beat:x")),
                  ClockFired("clock:deadline"),
                  StateIs("person:ghost", "role", "dead")))
    w = closure_witness_of(expr, reads, turn=7)
    assert [l["kind"] for l in w["unknown_leaves"]] == ["StateIs"]
    assert classify_closure(w) == "D-HARD"     # UNKNOWN on the path -> conservative


def test_witness_repeated_clock_selects_threshold_crossing_firing():
    # ClockFired(n=2) with three firings: the CAUSAL event is the 2nd by
    # (time, id) — never an arbitrary match (cr r3 point 4).
    reads = _WitnessReads(firings=[
        ("clock:deadline", 9, "event:f3"),
        ("clock:deadline", 3, "event:f1"),
        ("clock:deadline", 5, "event:f2"),
    ])
    expr = ClockFired("clock:deadline", n=2)
    w = closure_witness_of(expr, reads, turn=7)
    assert w["firing_events"] == ["event:f2"]
    assert classify_closure(w) == "D-MISSED"


def test_classifier_conservative_defaults():
    assert classify_closure(None) == "D-HARD"                     # pre-contract
    assert classify_closure({}) == "D-HARD"
    assert classify_closure({"true_leaves": [], "unknown_leaves": [],
                             "clock_caused": False, "firing_events": []}) == "D-HARD"
    assert classify_closure({"true_leaves": [{"kind": "ClockFired"}],
                             "unknown_leaves": [], "clock_caused": True,
                             "firing_events": []}) == "D-HARD"    # no captured firing


def test_beat_pass_writes_the_witness_on_closure(world):
    # The REAL beat_pass: a required beat whose unreachable_if is a fired clock
    # closes AND persists a parseable witness (clock-caused, firing captured).
    arc = make_arc()
    beat = replace(arc.beats[0], unreachable_if=ClockFired("clock:escalate"))
    arc = replace(arc, beats=(beat,))
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "event:clock_escalate_3", "attribute": "kind",
         "value": "clock_fired", "valid_from": turn_time(3)},
        {"entity": "event:clock_escalate_3", "attribute": "agent",
         "value": "clock:escalate", "value_type": "entity",
         "valid_from": turn_time(3)},
    ], frame=PLOT)
    reads = PorcelainWorldReads(world)
    _achieved, closed, _rev = beat_pass(world, arc, reads, turn=4)
    assert closed == ["beat:discover"]
    w = read_closure_witness(reads, "beat:discover")
    assert w is not None and w["clock_caused"] is True
    assert w["firing_events"] == ["event:clock_escalate_3"]
    assert classify_closure(w) == "D-MISSED"


def test_on_expiry_round_trip(world):
    world.porcelain.ingest_structured(on_expiry_items(
        "clock:deadline", "the vote proceeded without you"), frame=PLOT)
    reads = PorcelainWorldReads(world)
    assert read_on_expiry(reads, "clock:deadline") == "the vote proceeded without you"
    assert read_on_expiry(reads, "clock:other") is None


def test_moment_receipt_and_callback_row_contracts():
    reads = _FakeReads()
    w = _FakeWorld(reads)
    assert drift.moment_receipt(reads, "beat:discover") is False
    drift.mark_moment(w, "beat:discover", "event:moment_missed_discover", turn=5)
    assert drift.moment_receipt(reads, "beat:discover") is True
    rows = drift.callback_rows("beat:discover", ["place:mill", "person:aldous"],
                               "the ledgers went unread", "event:moment_missed_discover",
                               turn=5)
    affected = next(r for r in rows if r["attribute"] == "affected")
    assert affected["value_type"] == "literal"      # cr: pinned literal typing
    assert next(r for r in rows if r["attribute"] == "status")["value"] == "pending"


def test_pending_callbacks_all_or_empty_parse(world):
    from construct.arc.executor import SESSION
    reads_turn = turn_time(3)
    world.porcelain.ingest_structured(
        drift.callback_rows("beat:good", ["place:mill"], "felt line",
                            "event:moment_missed_good", 3), frame=SESSION)
    # a malformed sibling: affected is not JSON — must be SKIPPED, never crash
    world.porcelain.ingest_structured([
        {"entity": "callback:moment_missed_bad", "attribute": "affected",
         "value": "not json", "value_type": "literal", "valid_from": reads_turn},
        {"entity": "callback:moment_missed_bad", "attribute": "directive",
         "value": "x", "valid_from": reads_turn},
        {"entity": "callback:moment_missed_bad", "attribute": "status",
         "value": "pending", "valid_from": reads_turn},
    ], frame=SESSION)
    cbs = drift.pending_callbacks(world)
    assert [c["entity"] for c in cbs] == ["callback:moment_missed_good"]
    assert cbs[0]["affected"] == ["place:mill"]
    drift.mark_callback_surfaced(world, "callback:moment_missed_good", 4)
    assert drift.pending_callbacks(world) == []     # once-only by supersession


def _closed_with_witness(world, arc):
    """Close the required beat via the REAL beat_pass under a fired clock."""
    world.porcelain.ingest_structured([
        {"entity": "event:clock_escalate_3", "attribute": "kind",
         "value": "clock_fired", "valid_from": turn_time(3)},
        {"entity": "event:clock_escalate_3", "attribute": "agent",
         "value": "clock:escalate", "value_type": "entity",
         "valid_from": turn_time(3)},
    ], frame=PLOT)
    reads = PorcelainWorldReads(world)
    _a, closed, _r = beat_pass(world, arc, reads, turn=4)
    assert closed == [arc.beats[0].beat_id]
    return reads


def _absence_arc():
    arc = make_arc()
    beat = replace(arc.beats[0], unreachable_if=ClockFired("clock:escalate"))
    return replace(arc, beats=(beat,))


def _absence_cast() -> dict:
    return {
        "person:aldous": CastNode(
            node_id="person:aldous",
            holds_clues=(Clue(clue_id="clue:ledger", pillar_id="pillar:main",
                              surface_fact=("fact:secret", "culprit", "person:rival")),),
            location="place:flat",
        ),
    }


def test_absence_beat_commits_event_consequences_and_callback(world):
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.9},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert ("beat:discover", "D-MISSED") in trace.drift
    assert trace.absence_consequences and trace.absence_consequences[0][1] == 1
    # the moment event is durable, with the explicit caused_by ROW to the firing
    evs = PorcelainWorldReads(world).events(kind="moment_missed")
    assert len(evs) == 1 and "event:clock_escalate_3" in evs[0].caused_by
    # the consequence row landed with item-level caused_by (served truth) —
    # and its VALUE is the HOST's closed lapse predicate, never model text.
    val = world.porcelain.state("person:aldous", "noted_absence")
    assert val["status"] == "known"
    assert "passed unmet" in str(val["fact"]["value"])
    # the callback is pending and target-matched to the staged scene + holder
    cbs = drift.pending_callbacks(world)
    assert cbs and set(cbs[0]["affected"]) >= {"person:aldous"}
    # once per beat: a second pass classifies nothing and re-fires nothing
    trace2 = TurnTrace(turn=6)
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace2,
               provider=StubProvider([]), turn=6, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace2.drift == [] and trace2.absence_consequences == []


def test_absence_all_unauthorized_subjects_decline_whole(world):
    # No conjuring, HOST-side (defense in depth beneath the schema cap): a
    # conjured id and the protagonist are both rejected by the host filter;
    # with no authorized subject left the response declines whole, nothing
    # persists, and the beat stays retryable.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:invented", PLAYER], "confidence": 0.9},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences == []
    assert not PorcelainWorldReads(world).has_entity("person:invented")
    assert world.porcelain.state(PLAYER, "noted_absence")["status"] != "known"
    assert not PorcelainWorldReads(world).events(kind="moment_missed")
    assert any("unauthorized" in d for d in trace.dropped_cohorts)
    assert drift.moment_receipt(reads, "beat:discover") is False   # retryable


def test_absence_low_confidence_declines_whole(world):
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.1},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert any("low confidence" in d for d in trace.dropped_cohorts)  # THE gate
    assert ("beat:discover", "D-MISSED") in trace.drift  # classified…
    assert trace.absence_consequences == []              # …but no response
    assert not PorcelainWorldReads(world).events(kind="moment_missed")
    assert drift.pending_callbacks(world) == []
    # a decline is telemetry, not a lock: the beat retries next turn
    assert drift.moment_receipt(reads, "beat:discover") is False


def test_absence_occurrence_rule_in_the_prompt(world):
    # §2: without an authored on_expiry the prompt FORBIDS occurrence claims;
    # with one, the note (and only it) is licensed.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    provider = StubProvider([
        {"subjects": [], "confidence": 0.9},
    ])
    trace = TurnTrace(turn=5)
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    prompt = provider.calls[0][0]
    assert "NO authored outcome exists" in prompt
    # now with the annotation (fresh world state: new beat id via a fresh arc
    # is overkill — a second closed beat isn't needed; assert the WITH-note
    # branch at the cohort layer directly)
    p2 = StubProvider([{"subjects": [], "confidence": 0.9}])
    import construct.cohorts as cohorts
    cohorts.absence_consequence(p2, {"entity": "fact:x", "attribute": "culprit"},
                                "place:mill", ["place:mill"], [],
                                "the vote proceeded without you", PROTAGONIST)
    assert "AUTHORED OUTCOME" in p2.calls[0][0]
    assert "the vote proceeded without you" in p2.calls[0][0]


def test_moment_missed_is_routine_for_salience():
    from construct.arc.generator import ROUTINE_EVENT_KINDS, salient_moments
    assert "moment_missed" in ROUTINE_EVENT_KINDS
    assert "absence_declined" in ROUTINE_EVENT_KINDS
    ev = EventRow(event_id="event:moment_missed_x", kind="moment_missed",
                  caused_by=("event:clock_fired_x",), at=9)
    assert salient_moments([], [ev], set(), set()) == []   # wakes nothing alone


def test_run_turn_missed_moment_full_arc_suppress_classify_surface_once(world):
    # The D2 spec oracle end-to-end through REAL turns: (A) the deadline clock
    # fires and closes the beat — that turn is SUPPRESSED (no classification);
    # (B) the next quiet turn classifies D-MISSED and commits the moment event,
    # consequence row, and pending callback; (C) the turn the player is among
    # the affected, the callback SURFACES into the briefing, once; (D) never
    # again.
    from construct.arc.executor import SESSION as _SESSION, turn_time
    arc = make_arc()
    beat = replace(arc.beats[0], unreachable_if=ClockFired("clock:escalate"))
    arc = replace(arc, beats=(beat,))
    seed_arc(world, arc)
    # four quiet turns banked: TurnsQuiet(4) fires clock:escalate on turn 5.
    world.porcelain.ingest_structured([
        {"entity": f"event:turn_{i}", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(i)} for i in range(1, 5)
    ], frame=_SESSION)
    world._extractions.extend([{"items": []}] * 8)
    # ---- (A) the firing/closing turn: suppressed.
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""},
        {"prose": "The hour slips past; somewhere a door goes unknocked."},
    ])
    rA = run_turn(world, arc, provider, "I wait and think.", turn=5,
                  cast=_absence_cast())
    assert "clock:escalate" in rA.trace.clocks_fired
    assert "beat:discover" in rA.trace.beats_closed
    assert rA.trace.drift == []                            # suppression precedes classification
    # ---- (B) the next quiet turn: classify D-MISSED, commit the response.
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""},
        {"subjects": ["person:aldous"], "confidence": 0.9},
        {"prose": "The evening settles."},
    ])
    rB = run_turn(world, arc, provider, "I sit with my notes.", turn=6,
                  cast=_absence_cast())
    assert ("beat:discover", "D-MISSED") in rB.trace.drift
    assert rB.trace.absence_consequences
    assert rB.trace.callbacks == []                        # nobody affected is here yet
    # ---- (C) the touch turn: Aldous arrives in the scene — the callback surfaces.
    world.porcelain.ingest_structured([
        {"entity": "person:aldous", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:aldous", "attribute": "name", "value": "Aldous"},
        {"entity": "person:aldous", "attribute": "in", "value": SCENE,
         "value_type": "entity", "valid_from": turn_time(6)},
    ])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""},
        {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
        {"prose": "Aldous is here, and something unsaid hangs about him."},
    ])
    import construct.turnloop as tl
    mp = pytest.MonkeyPatch()
    mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])
    try:
        rC = run_turn(world, arc, provider, "I look about the room.", turn=7,
                      cast=_absence_cast())
    finally:
        mp.undo()
    assert rC.trace.callbacks == ["callback:moment_missed_discover"]
    assert "CONSEQUENCE CALLBACK" in rC.trace.briefing
    assert "passed unmet" in rC.trace.briefing        # the HOST-built directive
    # ---- (D) once-only: the same touch never re-surfaces it.
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""},
        {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
        {"prose": "The room holds its quiet."},
    ])
    mp = pytest.MonkeyPatch()
    mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])
    try:
        rD = run_turn(world, arc, provider, "I look about once more.", turn=8,
                      cast=_absence_cast())
    finally:
        mp.undo()
    assert rD.trace.callbacks == []
    assert "CONSEQUENCE CALLBACK" not in rD.trace.briefing


# ---- cr D2 RED oracles: authority, partial receipts, completeness, restart --

class _ReceiptDoctor:
    """Proxy porcelain: passes everything through, but for batches matching
    `match` (a predicate over the rows) DOCTORS the returned receipt through
    `doctor(receipt_rows) -> receipt_rows`. The underlying ingest still lands
    (the fail-open shape: durable-or-not is decided by the receipt contract)."""

    def __init__(self, real, match, doctor):
        self._real, self._match, self._doctor = real, match, doctor

    def __getattr__(self, name):
        return getattr(self._real, name)

    def ingest_structured(self, rows, **kw):
        rows = list(rows)
        receipt = self._real.ingest_structured(rows, **kw)
        if self._match(rows):
            from construct.turnloop import _receipt_rows
            doctored = self._doctor(list(_receipt_rows(receipt)))
            return {"rows": doctored}
        return receipt


def test_absence_model_semantics_can_never_become_facts(world):
    # cr r3 blocker 1 (the relabel reproduction): the model has NO channel to
    # author fact semantics — the schema carries only SUBJECTS; every canon
    # row is a HOST-built closed lapse predicate. Even a hostile provider
    # cannot land "the vote passed 4-1" without the authored license: there
    # is no rows field, and unlicensed occurrence attributes never exist.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous"],
         "callback_line": "the vote passed 4-1 while you were away",  # a HOSTILE
         # extra key: schema-ignored, host-ignored — a DEAD channel (cr r4)
         "confidence": 0.9},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences and trace.absence_consequences[0][1] == 1
    # the ONLY committed fact is the host predicate; no occurrence-shaped
    # attribute exists anywhere without the authored note.
    val = world.porcelain.state("person:aldous", "noted_absence")
    assert val["status"] == "known" and "passed unmet" in str(val["fact"]["value"])
    assert world.porcelain.state("place:flat", "missed_moment_outcome")["status"] != "known"
    assert world.porcelain.state(PLAYER, "noted_absence")["status"] != "known"
    # and the PENDING callback directive is HOST text — the hostile string
    # never reaches the player-facing channel (cr r4 blocker 1).
    cbs = drift.pending_callbacks(world)
    assert cbs and "vote passed" not in cbs[0]["directive"]
    assert "passed unmet" in cbs[0]["directive"]
    assert "never assert what happened instead" in cbs[0]["directive"]


def test_absence_occurrence_licensed_only_with_the_causal_leaf_note(world):
    # the occurrence license binds to the causal witness leaf's clock: with
    # the authored on_expiry present, EXACTLY one occurrence row commits —
    # the note VERBATIM on the staged scene, never model text.
    arc = _absence_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured(on_expiry_items(
        "clock:escalate", "the ledgers were sealed unread"), frame=PLOT)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.9},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences and trace.absence_consequences[0][1] == 2
    out = world.porcelain.state("place:flat", "missed_moment_outcome")
    assert out["status"] == "known"
    assert str(out["fact"]["value"]) == "the ledgers were sealed unread"  # VERBATIM
    prompt = provider.calls[0][0]
    assert "the ledgers were sealed unread" in prompt   # the bound note, in-prompt
    cbs = drift.pending_callbacks(world)
    assert cbs and "What became of it (authored): the ledgers were sealed unread" \
        in cbs[0]["directive"]                          # licensed, verbatim, host-framed


def test_absence_two_subjects_plus_license_keeps_all_three_rows(world):
    # cr r4 blocker 3: two licensed subjects + on_expiry = BOTH noted_absence
    # predicates AND the occurrence row (3 rows) — never trade a subject's
    # fact for the note.
    arc = _absence_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured(on_expiry_items(
        "clock:escalate", "the ledgers were sealed unread"), frame=PLOT)
    world.porcelain.ingest_structured([
        {"entity": "person:witness", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:witness", "attribute": "in", "value": "place:flat",
         "value_type": "entity"},
    ])
    reads = _closed_with_witness(world, arc)
    cast = dict(_absence_cast())
    cast["person:witness"] = CastNode(node_id="person:witness", holds_clues=(),
                                      location="place:flat")
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous", "person:witness"], "confidence": 0.9},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=cast,
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences and trace.absence_consequences[0][1] == 3
    assert world.porcelain.state("person:aldous", "noted_absence")["status"] == "known"
    assert world.porcelain.state("person:witness", "noted_absence")["status"] == "known"
    assert world.porcelain.state("place:flat", "missed_moment_outcome")["status"] == "known"


def test_absence_nonperson_subjects_rejected(world):
    # cr r4 blocker 2 (reproduced): the delivery target entity, the staged
    # place, and the current place are never a "who" — subjects filter to the
    # staged cast + present NPCs only; nothing else commits a lapse predicate.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["fact:secret", "place:flat"], "confidence": 0.9},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences == []
    assert world.porcelain.state("fact:secret", "noted_absence")["status"] != "known"
    assert world.porcelain.state("place:flat", "noted_absence")["status"] != "known"
    assert world.porcelain.state(SCENE, "noted_absence")["status"] != "known"
    assert any("unauthorized" in d for d in trace.dropped_cohorts)
    assert drift.moment_receipt(reads, "beat:discover") is False


def test_absence_partial_event_receipt_declines_and_stays_retryable(world):
    # cr finding 2 (reproduced): the moment event's ROW SET must confirm —
    # a receipt missing patient/caused_by is not the contracted anchor.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    doctored = _ReceiptDoctor(
        world.porcelain,
        match=lambda rows: any(r.get("attribute") == "kind"
                               and r.get("value") == "moment_missed" for r in rows),
        doctor=lambda rr: [r for r in rr
                           if r.get("attribute") not in ("patient", "caused_by")])
    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.9},
    ])
    _drift_pass(world, doctored, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences == []
    assert drift.moment_receipt(reads, "beat:discover") is False   # NOT locked
    assert drift.pending_callbacks(world) == []
    assert any("event (unconfirmed)" in d for d in trace.dropped_cohorts)


def test_absence_empty_subjects_decline_whole(world):
    # completeness: no authorized subject -> decline whole (telemetry, not a
    # lock); the callback is host-built so subjects are the ONLY model input.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=StubProvider([{"subjects": [], "confidence": 0.9}]),
               turn=5, arc=arc, cast=_absence_cast(), scene=SCENE, npcs=[],
               horizon=None, minutes_now=None, rung=None, fuel=[], spines={})
    assert trace.absence_consequences == []
    assert drift.moment_receipt(reads, "beat:discover") is False


def test_absence_callback_partial_receipt_declines_not_locked(world):
    # cr finding 3 (reproduced): a callback batch missing its load-bearing
    # `affected` row is silent forever — the COMPLETE set must confirm, else
    # decline and stay retryable.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)

    class _WorldProxy:
        def __init__(self, real):
            self._real = real
            self.porcelain = _ReceiptDoctor(
                real.porcelain,
                match=lambda rows: any(str(r.get("entity", "")).startswith("callback:")
                                       for r in rows),
                doctor=lambda rr: [r for r in rr if r.get("attribute") != "affected"])

        def __getattr__(self, name):
            return getattr(self._real, name)

    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.9},
    ])
    _drift_pass(_WorldProxy(world), world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences == []
    assert drift.moment_receipt(reads, "beat:discover") is False   # retryable
    assert any("callback (unconfirmed)" in d for d in trace.dropped_cohorts)


def test_witness_not_closure_persists_the_negated_subtree(world):
    # cr finding 5: a TRUE Not closure must carry WHAT made it true — the
    # FALSE operand leaf persists in false_leaves. Real beat_pass close.
    arc = make_arc()
    beat = replace(arc.beats[0],
                   unreachable_if=Not(StateIs("person:rival", "role", "dead")))
    arc = replace(arc, beats=(beat,))
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "person:rival", "attribute": "role", "value": "alive"},
    ])
    reads = PorcelainWorldReads(world)
    _a, closed, _r = beat_pass(world, arc, reads, turn=4)
    assert closed == ["beat:discover"]
    w = read_closure_witness(reads, "beat:discover")
    assert w is not None
    assert [l["kind"] for l in w.get("false_leaves", [])] == ["StateIs"]
    assert classify_closure(w) == "D-HARD"       # no clock — repair's province


def test_absence_holderless_beat_declines_never_fabricates_staging(world):
    # cr finding 6: a D-MISSED beat with NO provable staging (no holder, no
    # authored location) declines no_staged_scene — the current scene is not
    # provenance and must never become the moment's patient.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    empty_cast = {"person:aldous": CastNode(node_id="person:aldous",
                                            holds_clues=(), location="")}
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=StubProvider([]), turn=5, arc=arc, cast=empty_cast,
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert ("beat:discover", "D-MISSED") in trace.drift   # classified…
    assert trace.absence_consequences == []               # …declined, nothing staged
    assert not PorcelainWorldReads(world).events(kind="moment_missed")
    assert drift.pending_callbacks(world) == []


def test_absence_affected_includes_staged_scene_cast(world):
    # cr finding 4: the affected set = the staged scene + EVERY staged cast
    # member (a witness at place:flat), not clue holders alone.
    arc = _absence_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "person:witness", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:witness", "attribute": "in", "value": "place:flat",
         "value_type": "entity"},
    ])
    reads = _closed_with_witness(world, arc)
    cast = dict(_absence_cast())
    cast["person:witness"] = CastNode(node_id="person:witness", holds_clues=(),
                                      location="place:flat")
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.9},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=cast,
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    cbs = drift.pending_callbacks(world)
    assert cbs and set(cbs[0]["affected"]) >= {"place:flat", "person:aldous",
                                               "person:witness"}


def test_absence_offscene_secondary_holder_excluded_from_affected(world):
    # cr r3 blocker 2 (reproduced): a SECOND holder of the same delivery staged
    # ELSEWHERE (Bess at place:mill) was never positioned to witness the flat's
    # moment — she must NOT target-match; the staged scene's own holder stays.
    arc = _absence_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:mill", "attribute": "kind", "value": "room", "timeless": True},
    ])
    reads = _closed_with_witness(world, arc)
    cast = dict(_absence_cast())
    cast["person:bess"] = CastNode(
        node_id="person:bess",
        holds_clues=(Clue(clue_id="clue:ledger2", pillar_id="pillar:main",
                          surface_fact=("fact:secret", "culprit", "person:rival")),),
        location="place:mill")
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.9},
    ])
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=cast,
               scene=SCENE, npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    cbs = drift.pending_callbacks(world)
    assert cbs
    assert "person:bess" not in cbs[0]["affected"]
    assert set(cbs[0]["affected"]) >= {"place:flat", "person:aldous"}


def test_absence_restart_oracle_surfaces_after_reopen_once(tmp_path):
    # cr r3 finding 3: the BEHAVIORAL restart oracle — commit the response,
    # CLOSE the world, REOPEN, then run REAL turns: an unrelated turn stays
    # silent; the affected turn surfaces the directive into the briefing;
    # a further turn never re-fires it.
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from construct.arc.executor import turn_time as _tt

    rule = rule_classifier_fallback()

    def _mk(path, extractions):
        def fallback(prompt: str, schema: dict):
            if prompt.startswith("Classify the lifetime"):
                return rule(prompt, schema)
            if extractions:
                return extractions.pop(0)
            return {"items": []}
        w = World(path, world_id="w:restart", model=StubModel(fallback=fallback),
                  stance="fiction", title="Restart Oracle World")
        w._extractions = extractions
        return w

    path = tmp_path / "restart.world"
    ex1: list = []
    w1 = _mk(path, ex1)
    w1.ingestor.cursor.advance(1.0)
    w1.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:study"},
        {"entity": "place:flat", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition",
         "timeless": True},
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
        {"entity": "person:rival", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:rival", "attribute": "in", "value": "place:flat"},
        {"entity": "person:aldous", "attribute": "kind", "value": "person",
         "timeless": True},
        {"entity": "person:aldous", "attribute": "name", "value": "Aldous"},
        {"entity": "person:aldous", "attribute": "in", "value": "place:flat",
         "value_type": "entity"},
    ])
    arc = _absence_arc()
    seed_arc(w1, arc)
    reads1 = _closed_with_witness(w1, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.9},
    ])
    _drift_pass(w1, w1.porcelain, live_reads=PorcelainWorldReads(w1), trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene="place:study", npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences
    w1.close()
    # ---- REOPEN and play REAL turns through the reopened adapter.
    ex2: list = []
    w2 = _mk(path, ex2)
    try:
        # (i) unrelated turn: the player is at the study, no affected entity
        # present — the briefing carries NO callback.
        ex2.extend([{"items": []}, {"items": []}])
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "The study keeps its quiet."},
        ])
        r1 = run_turn(w2, arc, provider, "I read over my notes.", turn=6,
                      cast=_absence_cast())
        assert r1.trace.callbacks == []
        assert "CONSEQUENCE CALLBACK" not in r1.trace.briefing
        # (ii) the affected turn: Aldous arrives in the scene — it surfaces.
        w2.porcelain.ingest_structured([
            {"entity": "person:aldous", "attribute": "in", "value": "place:study",
             "value_type": "entity", "valid_from": _tt(6)},
        ])
        ex2.extend([{"items": []}, {"items": []}])
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Aldous stands near the shelves, waiting to be noticed."},
        ])
        import construct.turnloop as tl
        mp = pytest.MonkeyPatch()
        mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])
        try:
            r2 = run_turn(w2, arc, provider, "I look up.", turn=7,
                          cast=_absence_cast())
        finally:
            mp.undo()
        assert r2.trace.callbacks == ["callback:moment_missed_discover"]
        assert "CONSEQUENCE CALLBACK" in r2.trace.briefing
        assert "passed unmet" in r2.trace.briefing    # the HOST-built directive
        # (iii) never again.
        ex2.extend([{"items": []}, {"items": []}])
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Nothing more hangs in the air."},
        ])
        mp = pytest.MonkeyPatch()
        mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])
        try:
            r3 = run_turn(w2, arc, provider, "I glance about once more.",
                          turn=8, cast=_absence_cast())
        finally:
            mp.undo()
        assert r3.trace.callbacks == []
        assert "CONSEQUENCE CALLBACK" not in r3.trace.briefing
    finally:
        w2.close()


def test_absence_partial_fact_receipt_declines_and_stays_retryable(world):
    # cr r5 blocker 1 (reproduced): the fact set confirms COMPLETE or not at
    # all — (a) a dropped subject row and (b) a dropped licensed outcome each
    # decline whole, unlocked, retryable.
    from construct.arc.executor import PLOT as _PLOT
    for drop_attr in ("noted_absence", "missed_moment_outcome"):
        arc = _absence_arc()
        # fresh world per case: build inline (the fixture is function-scoped)
        import tempfile, pathlib
        from patternbuffer import World
        from patternbuffer.testing import StubModel, rule_classifier_fallback
        rule = rule_classifier_fallback()
        w = World(pathlib.Path(tempfile.mkdtemp()) / "t.world", world_id="w:t",
                  model=StubModel(fallback=lambda pr, sc: rule(pr, sc)
                                  if pr.startswith("Classify the lifetime")
                                  else {"items": []}),
                  stance="fiction", title="T")
        w.ingestor.cursor.advance(1.0)
        w.ingest_structured([
            {"entity": "place:flat", "attribute": "kind", "value": "room",
             "timeless": True},
            {"entity": PLAYER, "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:witness", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
        ])
        seed_arc(w, arc)
        w.porcelain.ingest_structured(on_expiry_items(
            "clock:escalate", "the ledgers were sealed unread"), frame=PLOT)
        reads = _closed_with_witness(w, arc)
        cast = dict(_absence_cast())
        cast["person:witness"] = CastNode(node_id="person:witness",
                                          holds_clues=(), location="place:flat")
        # doctor: genuinely strip ONE row kind from the fact batch's receipt
        doctored = _ReceiptDoctor(
            w.porcelain,
            match=lambda rows: any(r.get("attribute") in
                                   ("noted_absence", "missed_moment_outcome")
                                   for r in rows),
            doctor=lambda rr, _d=drop_attr: [
                r for r in rr if r.get("attribute") != _d][:2])
        trace = TurnTrace(turn=5)
        provider = StubProvider([
            {"subjects": ["person:aldous", "person:witness"], "confidence": 0.9},
        ])
        _drift_pass(w, doctored, live_reads=reads, trace=trace,
                   provider=provider, turn=5, arc=arc, cast=cast,
                   scene=SCENE, npcs=[], horizon=None, minutes_now=None,
                   rung=None, fuel=[], spines={})
        assert trace.absence_consequences == [], drop_attr
        assert drift.moment_receipt(reads, "beat:discover") is False, drop_attr
        assert any("consequences (unconfirmed)" in d
                   for d in trace.dropped_cohorts), drop_attr
        w.close()


def test_absence_same_scene_closure_never_claims_player_was_elsewhere(world):
    # cr r5 blocker 2 (reproduced): the player may have stood IN the staged
    # scene as the window expired — the directive and predicates carry NO
    # location claim about the player.
    arc = _absence_arc()
    seed_arc(world, arc)
    reads = _closed_with_witness(world, arc)
    trace = TurnTrace(turn=5)
    provider = StubProvider([
        {"subjects": ["person:aldous"], "confidence": 0.9},
    ])
    # scene == staged_scene: the player is AT place:flat when it classifies.
    _drift_pass(world, world.porcelain, live_reads=reads, trace=trace,
               provider=provider, turn=5, arc=arc, cast=_absence_cast(),
               scene="place:flat", npcs=[], horizon=None, minutes_now=None,
               rung=None, fuel=[], spines={})
    assert trace.absence_consequences
    cbs = drift.pending_callbacks(world)
    assert cbs
    assert "elsewhere" not in cbs[0]["directive"]
    assert "passed unmet" in cbs[0]["directive"]
    val = world.porcelain.state("person:aldous", "noted_absence")
    assert "elsewhere" not in str(val["fact"]["value"])


# ============================================================================
# 5. D3 stage 1 — the supersession resolver, per-beat IO, consumer redirects
# ============================================================================

from construct.arc.conditions import evaluate as _evaluate  # noqa: E402
from construct.arc.executor import (  # noqa: E402
    active_beats, climax_ready, current_phase, resolve_beat_id,
)
from construct.arc.io import beat_from_reads, beat_to_items  # noqa: E402


def _supersede(world, arc_id: str, old_slug: str, new_id: str, turn: int = 5):
    world.porcelain.ingest_structured([
        {"entity": arc_id, "attribute": f"beat_superseded_{old_slug}",
         "value": new_id, "valid_from": turn_time(turn)},
    ], frame=PLOT)


def _replacement_beat(new_id="beat:discover_r1"):
    from construct.arc.conditions import InFrame
    return Beat(new_id, Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame("knows:person:player", "fact:secret",
                                       "culprit", "person:rival"))


def test_beat_to_items_emits_only_the_one_beat(world):
    rows = beat_to_items(_replacement_beat(), "arc:main")
    assert {r["entity"] for r in rows} == {"beat:discover_r1"}
    assert not any(r["attribute"] == "beat_index" for r in rows)  # sealed index untouched
    world.porcelain.ingest_structured(rows)
    rb = beat_from_reads(PorcelainWorldReads(world), "beat:discover_r1")
    assert rb is not None and rb.weight is Weight.REQUIRED
    assert beat_from_reads(PorcelainWorldReads(world), "beat:never_written") is None


def test_resolver_chain_cycle_and_collision(world):
    arc = make_arc()
    seed_arc(world, arc)
    reads = PorcelainWorldReads(world)
    # unsuperseded → identity
    assert resolve_beat_id(reads, "beat:discover") == "beat:discover"
    # chain old → r1 → r2 follows to the terminal (each hop needs part_of rows)
    world.porcelain.ingest_structured(beat_to_items(_replacement_beat("beat:discover_r1"),
                                                    "arc:main"))
    world.porcelain.ingest_structured(beat_to_items(_replacement_beat("beat:discover_r2"),
                                                    "arc:main"))
    _supersede(world, "arc:main", "discover", "beat:discover_r1", 5)
    _supersede(world, "arc:main", "discover_r1", "beat:discover_r2", 6)
    assert resolve_beat_id(reads, "beat:discover") == "beat:discover_r2"
    # collision: one attribute key — a re-assert supersedes by valid_from
    world.porcelain.ingest_structured(beat_to_items(_replacement_beat("beat:discover_r3"),
                                                    "arc:main"))
    _supersede(world, "arc:main", "discover_r1", "beat:discover_r3", 7)
    assert resolve_beat_id(reads, "beat:discover") == "beat:discover_r3"
    # cycle fails safe to the ORIGINAL id
    _supersede(world, "arc:main", "discover_r3", "beat:discover", 8)
    assert resolve_beat_id(reads, "beat:discover") == "beat:discover"


def test_beat_achieved_and_climax_tuple_observe_the_replacement(world):
    # a downstream BeatAchieved(old) + the sealed climax id tuple both fire
    # when the REPLACEMENT achieves (§3 R4 — the resolver redirects both).
    from construct.arc.conditions import BeatAchieved
    arc = make_arc()
    seed_arc(world, arc)
    reads = PorcelainWorldReads(world)
    world.porcelain.ingest_structured(beat_to_items(_replacement_beat(), "arc:main"))
    _supersede(world, "arc:main", "discover", "beat:discover_r1")
    assert _evaluate(BeatAchieved("beat:discover"), reads) is not None  # evaluable
    assert not climax_ready(reads, arc)
    world.porcelain.ingest_structured([
        {"entity": "beat:discover_r1", "attribute": "status", "value": "achieved",
         "valid_from": turn_time(6)},
    ], frame=PLOT)
    from construct.arc.truth import Truth as _T
    assert _evaluate(BeatAchieved("beat:discover"), reads) is _T.TRUE
    assert climax_ready(reads, arc)                       # the tuple, redirected
    assert current_phase(reads, arc) is Phase.CLIMAX


def test_active_beats_overlay_survives_restart_both_load_paths(tmp_path):
    # reads-backed overlay: the SEALED arc object (frame-loaded or cached) is
    # irrelevant — a reopened world's reads still serve the replacement.
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    rule = rule_classifier_fallback()

    def _mk(path):
        return World(path, world_id="w:d3", model=StubModel(
            fallback=lambda pr, sc: rule(pr, sc)
            if pr.startswith("Classify the lifetime") else {"items": []}),
            stance="fiction", title="D3")

    path = tmp_path / "d3.world"
    w1 = _mk(path)
    w1.ingestor.cursor.advance(1.0)
    arc = make_arc()
    seed_arc(w1, arc)
    w1.porcelain.ingest_structured(beat_to_items(_replacement_beat(), "arc:main"))
    _supersede(w1, "arc:main", "discover", "beat:discover_r1")
    live1 = [b.beat_id for b in active_beats(PorcelainWorldReads(w1), arc)]
    assert live1 == ["beat:discover_r1"]                  # same-turn, live arc object
    w1.close()
    w2 = _mk(path)
    try:
        # the same SEALED arc object (the arc_cache shape) against reopened reads
        live2 = [b.beat_id for b in active_beats(PorcelainWorldReads(w2), arc)]
        assert live2 == ["beat:discover_r1"]
        # frame reconstruction path: arc_from_frame yields the sealed set; the
        # overlay still swaps at read time
        from construct.arc import io as arc_io
        arc2 = arc_io.arc_from_frame(PorcelainWorldReads(w2))
        live3 = [b.beat_id for b in active_beats(PorcelainWorldReads(w2), arc2)]
        assert live3 == ["beat:discover_r1"]
    finally:
        w2.close()


def test_future_stamped_supersession_invisible_at_horizon(world):
    from construct.arc.executor import turn_time as _tt
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured(beat_to_items(_replacement_beat(), "arc:main"))
    _supersede(world, "arc:main", "discover", "beat:discover_r1", turn=999)
    bounded = PorcelainWorldReads(world, horizon=_tt(5))
    assert resolve_beat_id(bounded, "beat:discover") == "beat:discover"
    assert [b.beat_id for b in active_beats(bounded, arc)] == ["beat:discover"]


def test_unmaterializable_replacement_fails_open_to_the_sealed_beat(world):
    arc = make_arc()
    seed_arc(world, arc)
    _supersede(world, "arc:main", "discover", "beat:ghost")  # no rows for beat:ghost
    live = [b.beat_id for b in active_beats(PorcelainWorldReads(world), arc)]
    assert live == ["beat:discover"]                       # never crash, never vanish
