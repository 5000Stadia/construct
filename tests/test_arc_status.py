"""Equivalence + read-count tests for `ArcStatus` (audit-2026-10 arc F5).

Before the refactor "is this arc done?" had seven entry points that each re-derived
their pieces (`arc_concluded`, `arc_outcome`, `arc_lifecycle`, `current_phase`,
`climax_ready`, `conclusive_eligible`, `_required_unreachable`, plus the lifecycle
helpers `_cancelled` / `_repair_exhausted`). They are now one-line accessors over a
lazily-memoized `ArcStatus`. The OLD bodies are kept here VERBATIM (renamed `_ref_*`,
calling each other) as the reference; randomized arcs over randomized fake reads --
including supersession chains (valid, torn, cyclic), authored `failure_when`, cancelled
events and injected read FAILURES -- run through each old entry point and the new
accessor, and must agree exactly: the same value, or the same exception type and
arguments. Also pins the deliberate `arc_concluded` / `arc_outcome` `failure_when`
disagreement, laziness (a `concluded` question reads no beat), and that sharing one
status never costs MORE reads than the old per-entry-point derivations.
"""

from __future__ import annotations

import json
import random
from types import SimpleNamespace
from typing import Any

import pytest

from construct.arc import conclusion, executor
from construct.arc.conditions import (
    AllOf, AnyOf, BeatAchieved, ClockFired, EventRow, Not, StateIs, Truth, evaluate,
)
from construct.arc.executor import (
    ConclusiveCandidate, arc_concluded, arc_lifecycle, arc_outcome, arc_status,
    climax_ready, conclusive_eligible, current_phase,
)
from construct.arc.grammar import (
    Arc, Beat, BeatStatus, Clock, ConclusionShape, Phase, Weight,
)
from construct.arc.io import expr_to_obj
from construct.arc.supersession import active_beats, resolve_beat_id
from construct.arc.timeline import PLOT, SESSION
from tests.test_evaluator_property import _CLOCKS, _FakeReads, _rand_expr

# ---------------------------------------------------------------------------
# REFERENCE: the pre-refactor bodies (conclusion.py / executor.py at HEAD before
# the F5 refactor), verbatim apart from the `_ref_` rename of the entry points.
# ---------------------------------------------------------------------------

_PHASE_ORDER = conclusion._PHASE_ORDER


def _ref_arc_concluded(reads: Any, arc: Arc) -> bool:
    from construct.arc.conditions import ClockFired

    if evaluate(arc.shape.world_condition, reads) is Truth.TRUE:
        return True
    refusal = arc.refusal_clock.clock_id
    return evaluate(ClockFired(refusal), reads) is Truth.TRUE


def _ref_arc_outcome(reads: Any, arc: Arc):
    from construct.arc.conditions import ClockFired

    if evaluate(arc.shape.world_condition, reads) is Truth.TRUE:
        return "won"
    if evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE:
        return "lost"
    if arc.failure_when is not None and evaluate(arc.failure_when, reads) is Truth.TRUE:
        return "lost"
    return None


def _ref_climax_ready(reads: Any, arc: Arc) -> bool:
    if not arc.climax_ready_beats:
        return False
    got = sum(1 for bid in arc.climax_ready_beats
              if reads.state(resolve_beat_id(reads, bid), "status",
                             frame=PLOT) == BeatStatus.ACHIEVED)
    return got >= arc.climax_ready_k


def _ref_current_phase(reads: Any, arc: Arc) -> Phase:
    if _ref_arc_concluded(reads, arc):
        return Phase.FALLING
    if _ref_climax_ready(reads, arc):
        return Phase.CLIMAX
    achieved = [b.phase for b in active_beats(reads, arc)
                if reads.state(b.beat_id, "status", frame=PLOT) == BeatStatus.ACHIEVED]
    if not achieved:
        return Phase.SETUP
    return max(achieved, key=lambda p: _PHASE_ORDER[p])


def _ref_required_unreachable(reads: Any, arc: Arc) -> bool:
    for beat in active_beats(reads, arc):
        if beat.weight is Weight.REQUIRED and \
                reads.state(beat.beat_id, "status", frame=PLOT) == "closed":
            return True
    return False


def _ref_repair_exhausted(reads: Any, arc: Arc) -> bool:
    from construct.arc.conditions import ClockFired
    if evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE:
        return True
    from construct.arc.drift import REPAIR_BUDGET, repair_spent
    return repair_spent(reads, arc.arc_id) >= REPAIR_BUDGET


def _ref_cancelled(reads: Any, arc: Arc) -> bool:
    slug = arc.arc_id.split(":", 1)[1]
    eid = f"event:arc_cancelled_{slug}"
    try:
        if any(e.event_id == eid
               for e in reads.events(kind="arc_cancelled", frame=SESSION)):
            return True
    except Exception:  # noqa: BLE001 -- fall through to the legacy read
        pass
    return reads.state(eid, "kind", frame=SESSION) == "arc_cancelled"


def _ref_arc_lifecycle(reads: Any, arc: Arc) -> str:
    outcome = _ref_arc_outcome(reads, arc)
    if outcome == "won":
        return "won"
    if _ref_cancelled(reads, arc):
        return "cancelled"
    if _ref_required_unreachable(reads, arc) and _ref_repair_exhausted(reads, arc):
        return "incompletable"
    if outcome == "lost":
        return "lost"
    return "active"


def _ref_conclusive_eligible(reads: Any, arc: Arc, *, contract: str,
                             candidate: ConclusiveCandidate) -> bool:
    from construct.arc.conditions import ClockFired
    if contract != "story":
        return False
    refusal_fired = evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE
    foreclosed = _ref_required_unreachable(reads, arc)
    phase = _ref_current_phase(reads, arc)
    if not (phase in (Phase.CRISIS, Phase.CLIMAX, Phase.FALLING)
            or refusal_fired or foreclosed):
        return False
    if not (_ref_climax_ready(reads, arc) or foreclosed or refusal_fired):
        return False
    return candidate.any()


# ---------------------------------------------------------------------------
# Randomized arcs and worlds
# ---------------------------------------------------------------------------

_ARC_ID = "arc:main"
_BEAT_IDS = tuple(f"beat:s{i}" for i in range(5))
_REPLACEMENTS = tuple(f"beat:r{i}" for i in range(4))
_PHASES = tuple(Phase)
_WEIGHTS = tuple(Weight)
_STATUSES = ("pending", "achieved", "closed", None)


class _StatusReads(_FakeReads):
    """`_FakeReads` plus what the arc-status paths touch: beat status/part_of/
    supersession rows, `frame_rows` (repair spend), `arc_cancelled` events, per-key
    injected read failures, and a read counter."""

    def __init__(self, rng: random.Random) -> None:
        super().__init__(rng)
        self.faults: set[tuple[str, str]] = set()
        self.events_fault_kinds: set[str] = set()
        self.reads = 0
        for bid in _BEAT_IDS:
            if rng.random() < 0.8:
                self._state[(bid, "status")] = rng.choice(_STATUSES)
            if rng.random() < 0.5:           # serialized -> supersedable
                self._state[(bid, "part_of")] = _ARC_ID
        for rid in _REPLACEMENTS:
            if rng.random() < 0.7:
                self._state[(rid, "status")] = rng.choice(_STATUSES)
        self._materialize_replacements(rng)
        if rng.random() < 0.25:
            self._events.append(EventRow(
                event_id="event:arc_cancelled_main", kind="arc_cancelled",
                agents=(_ARC_ID,), at=1))
        if rng.random() < 0.08:              # the legacy non-event-classified row
            self._state[("event:arc_cancelled_main", "kind")] = "arc_cancelled"
        if rng.random() < 0.35:
            pool = [k for k in self._state if k[1] in ("status", "part_of")] + [
                (e, "role") for e in ("person:a", "item:c")]
            self.faults = set(rng.sample(pool, min(len(pool), rng.randint(1, 2))))
        if rng.random() < 0.1:
            self.events_fault_kinds.add("arc_cancelled")
        if rng.random() < 0.05:
            self.events_fault_kinds.add("clock_fired")

    def _materialize_replacements(self, rng: random.Random) -> None:
        """Wire supersession pointers old -> replacement(s): fully valid, torn, or
        cyclic chains, so `active_beats` / `repair_spent` walk real hops."""
        pool = list(_REPLACEMENTS)
        rng.shuffle(pool)
        for old in rng.sample(_BEAT_IDS, rng.randint(0, 3)):
            if not pool or (old, "part_of") not in self._state:
                continue
            chain = [old] + [pool.pop() for _ in range(min(len(pool), rng.randint(1, 2)))]
            for src, dst in zip(chain, chain[1:]):
                slug = src.split(":", 1)[-1]
                self._state[(_ARC_ID, f"beat_superseded_{slug}")] = dst
                self._state[(dst, "part_of")] = _ARC_ID
                if rng.random() < 0.85:      # else: torn -- not materializable
                    self._state[(dst, "kind")] = "beat"
                    self._state[(dst, "achievable_via")] = json.dumps(
                        expr_to_obj(StateIs("fact:q", "v", "y")))
                    self._state[(dst, "beat_phase")] = rng.choice(_PHASES).value
                    self._state[(dst, "weight")] = rng.choice(_WEIGHTS).value
            if rng.random() < 0.1:           # a cycle back to the root
                last = chain[-1].split(":", 1)[-1]
                self._state[(_ARC_ID, f"beat_superseded_{last}")] = chain[0]

    def state(self, entity, attribute, *, frame="canon"):
        self.reads += 1
        if (entity, attribute) in self.faults:
            raise RuntimeError(f"boom state {entity}.{attribute}")
        return super().state(entity, attribute, frame=frame)

    def events(self, *, kind=None, participant=None, since=None, until=None,
               frame="canon"):
        self.reads += 1
        if kind in self.events_fault_kinds:
            raise RuntimeError(f"boom events {kind}")
        return super().events(kind=kind, participant=participant, since=since,
                              until=until, frame=frame)

    def frame_rows(self, frame, *, entity=None):
        self.reads += 1
        return [SimpleNamespace(entity=e, attribute=a, value=v)
                for (e, a), v in self._state.items()
                if e == entity and a.startswith("beat_superseded_")]


def _rand_world_expr(rng: random.Random):
    """A world_condition / failure_when mixing the property test's atoms with simple
    fact atoms, so every Truth value (and the won/lost tie) is reachable."""
    if rng.random() < 0.5:
        return _rand_expr(rng, rng.randint(0, 3))
    atoms = [StateIs("fact:case", "solved", "yes"),
             StateIs("fact:case", "solved", "no"),
             ClockFired(rng.choice(_CLOCKS)),
             BeatAchieved(rng.choice(_BEAT_IDS))]
    pick = rng.sample(atoms, rng.randint(1, 3))
    return rng.choice((AllOf, AnyOf))(tuple(pick)) if len(pick) > 1 else Not(pick[0]) \
        if rng.random() < 0.3 else pick[0]


def _case(seed: int) -> tuple[Arc, _StatusReads, str, ConclusiveCandidate]:
    rng = random.Random(seed)
    reads = _StatusReads(rng)
    if rng.random() < 0.6:
        reads._state[("fact:case", "solved")] = rng.choice(("yes", "no", None))
    reads._state.setdefault(("fact:case", "solved"), None)
    beats = tuple(
        Beat(beat_id=bid, phase=rng.choice(_PHASES), weight=rng.choice(_WEIGHTS),
             achievable_via=StateIs(bid, "x", "y"))
        for bid in rng.sample(_BEAT_IDS, rng.randint(0, len(_BEAT_IDS))))
    climax_pool = list(_BEAT_IDS) + ["beat:ghost"]
    climax = tuple(rng.sample(climax_pool, rng.randint(0, 3)))
    arc = Arc(
        arc_id=_ARC_ID, protagonist="hero",
        shape=ConclusionShape(
            shape_id="shape:main", delta_type="desire_at_cost",
            tension=("hero", "want", "fear"),
            world_condition=_rand_world_expr(rng),
            premise=StateIs("p", "q", "r"), refusal_variant_id="rv"),
        beats=beats, clocks=(),
        refusal_clock=Clock(clock_id=rng.choice(_CLOCKS),
                            fires_when=StateIs("z", "z", "z"), effects=()),
        climax_ready_k=rng.randint(0, 3), climax_ready_beats=climax,
        failure_when=None if rng.random() < 0.4 else _rand_world_expr(rng))
    contract = rng.choice(("story", "story", "story", "sandbox"))
    cand = ConclusiveCandidate(
        climax_beat_achieved=rng.random() < 0.4,
        refusal_or_deadline_fired=rng.random() < 0.2,
        required_beat_foreclosed=rng.random() < 0.2)
    return arc, reads, contract, cand


def _run(fn, *args, **kw):
    """(value, None) or (None, (exception type, args)) -- exceptions are part of the
    contract the accessors must keep."""
    try:
        return fn(*args, **kw), None
    except Exception as exc:  # noqa: BLE001
        return None, (type(exc), exc.args)


_N_CASES = 4000

#: (name, old reference, new accessor) -- each called as f(reads, arc).
_PAIRS = (
    ("arc_concluded", _ref_arc_concluded, arc_concluded),
    ("arc_outcome", _ref_arc_outcome, arc_outcome),
    ("climax_ready", _ref_climax_ready, climax_ready),
    ("current_phase", _ref_current_phase, current_phase),
    ("arc_lifecycle", _ref_arc_lifecycle, arc_lifecycle),
    ("_required_unreachable", _ref_required_unreachable, executor._required_unreachable),
    ("_repair_exhausted", _ref_repair_exhausted, executor._repair_exhausted),
    ("_cancelled", _ref_cancelled, executor._cancelled),
)


def test_every_old_entry_point_equals_its_accessor():
    seen: dict[str, set] = {name: set() for name, _o, _n in _PAIRS}
    seen["raised"] = set()
    checks = 0
    for seed in range(_N_CASES):
        arc, reads, contract, cand = _case(seed)
        ctx = f"seed={seed}"
        for name, old, new in _PAIRS:
            got_old = _run(old, reads, arc)
            got_new = _run(new, reads, arc)
            assert got_new == got_old, (ctx, name, got_old, got_new)
            seen[name].add(repr(got_old[0]) if got_old[1] is None else "raised")
            seen["raised"].add(got_old[1] is not None)
            checks += 1
        got_old = _run(_ref_conclusive_eligible, reads, arc, contract=contract,
                       candidate=cand)
        got_new = _run(conclusive_eligible, reads, arc, contract=contract,
                       candidate=cand)
        assert got_new == got_old, (ctx, "conclusive_eligible", got_old, got_new)
        checks += 1
    # the generator genuinely covered the space (else the equivalence is hollow)
    assert seen["arc_lifecycle"] >= {"'won'", "'lost'", "'cancelled'", "'incompletable'",
                                     "'active'", "raised"}
    assert seen["current_phase"] >= {repr(p) for p in Phase} | {"raised"}
    assert seen["arc_outcome"] >= {"'won'", "'lost'", "None"}
    assert seen["_required_unreachable"] >= {"True", "False"}
    assert seen["climax_ready"] >= {"True", "False"}
    assert seen["raised"] == {True, False}
    assert checks == _N_CASES * (len(_PAIRS) + 1)


def test_status_fields_equal_old_entry_points_when_read_off_one_status():
    """One shared status answers every question the same as the seven fresh derivations
    (no field is poisoned by another's memo) -- on worlds where nothing raises."""
    compared = 0
    for seed in range(_N_CASES):
        arc, reads, _contract, _cand = _case(seed)
        reads.faults.clear()
        reads.events_fault_kinds.clear()
        st = arc_status(reads, arc)
        assert st.concluded == _ref_arc_concluded(reads, arc), seed
        assert st.outcome == _ref_arc_outcome(reads, arc), seed
        assert st.lifecycle == _ref_arc_lifecycle(reads, arc), seed
        assert st.phase == _ref_current_phase(reads, arc), seed
        assert st.climax_ready == _ref_climax_ready(reads, arc), seed
        assert st.foreclosed == _ref_required_unreachable(reads, arc), seed
        assert st.refusal_fired == (
            evaluate(ClockFired(arc.refusal_clock.clock_id), reads) is Truth.TRUE), seed
        assert st.active_beats == active_beats(reads, arc), seed
        compared += 1
    assert compared == _N_CASES


def test_concluded_ignores_failure_when_but_outcome_honours_it():
    """The kept inconsistency (founder's call, audit arc F5): an authored failure marks
    the outcome LOST while the arc is NOT `concluded`."""
    reads = _StatusReads(random.Random(0))
    reads.faults.clear()
    reads._state[("fact:case", "solved")] = None
    reads._state[("fact:doom", "now")] = "yes"
    reads._entities |= {"fact:doom", "fact:case"}
    reads._events = []
    arc = Arc(
        arc_id=_ARC_ID, protagonist="hero",
        shape=ConclusionShape(
            shape_id="s", delta_type="desire_at_cost", tension=("h", "w", "f"),
            world_condition=StateIs("fact:case", "solved", "yes"),
            premise=StateIs("p", "q", "r"), refusal_variant_id="rv"),
        beats=(), clocks=(),
        refusal_clock=Clock(clock_id="clock:c0", fires_when=StateIs("z", "z", "z"),
                            effects=()),
        climax_ready_k=0, climax_ready_beats=(),
        failure_when=StateIs("fact:doom", "now", "yes"))
    assert arc_concluded(reads, arc) is False
    assert arc_outcome(reads, arc) == "lost"
    st = arc_status(reads, arc)
    assert (st.concluded, st.outcome, st.failure_holds) == (False, "lost", True)
    assert arc_lifecycle(reads, arc) == "lost"


def test_status_is_frozen_and_building_it_reads_nothing():
    arc, reads, _c, _k = _case(7)
    st = arc_status(reads, arc)
    with pytest.raises(Exception):
        st.reads = None  # frozen
    assert reads.reads == 0


def test_concluded_reads_no_beat_rows():
    arc, reads, _c, _k = _case(11)
    touched: list[tuple[str, str]] = []
    orig = reads.state

    def spy(entity, attribute, *, frame="canon"):
        touched.append((entity, attribute))
        return orig(entity, attribute, frame=frame)

    reads.state = spy
    reads.faults.clear()
    arc_concluded(reads, arc)
    assert not [t for t in touched if t[1] in ("status", "part_of")]


# ---------------------------------------------------------------------------
# Read reduction
# ---------------------------------------------------------------------------

def _reads_used(fn, arc, reads) -> int:
    reads.reads = 0
    _run(fn, reads, arc)
    return reads.reads


def test_shared_status_never_costs_more_reads_and_saves_in_aggregate():
    """`conclusive_eligible` + `arc_lifecycle` (the two composite entry points) read
    strictly no more than before on EVERY case, and strictly less in aggregate."""
    old_total = new_total = strict = 0
    for seed in range(_N_CASES):
        arc, reads, _contract, cand = _case(seed)
        reads.faults.clear()
        reads.events_fault_kinds.clear()
        for old, new in (
                (_ref_arc_lifecycle, arc_lifecycle),
                (lambda r, a: _ref_conclusive_eligible(r, a, contract="story",
                                                       candidate=cand),
                 lambda r, a: conclusive_eligible(r, a, contract="story",
                                                  candidate=cand))):
            o = _reads_used(old, arc, reads)
            n = _reads_used(new, arc, reads)
            assert n <= o, (seed, o, n)
            old_total += o
            new_total += n
            strict += n < o
    assert new_total < old_total
    assert strict > 0
