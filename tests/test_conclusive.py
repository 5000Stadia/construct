"""C1 — Conclusive Outcome Core, Gate A (deterministic eligibility + phase/shape).

Pure-logic unit tests over a minimal hand-built Arc + a fake WorldReads — no
world/ingest machinery — exercising executor.climax_ready / current_phase /
conclusive_eligible (CONCLUSIVE-OUTCOME-SPEC C1.1)."""
from types import SimpleNamespace

from construct.arc.conditions import StateIs
from construct.arc.grammar import (Arc, Beat, Clock, ConclusionShape, Phase, Weight)
from construct.arc.executor import (
    OUTCOME_SHAPES, ConclusiveCandidate, climax_ready, conclusive_eligible,
    current_phase)


class FakeReads:
    """Just the surface evaluate()/the helpers touch: state, has_entity, events."""
    def __init__(self):
        self.s: dict[tuple, str] = {}
        self.fired: set[str] = set()

    def set_beat(self, bid: str, status: str):
        self.s[(bid, "status")] = status

    def state(self, entity, attribute, frame=None):
        return self.s.get((entity, attribute))

    def has_entity(self, entity):
        return any(e == entity for (e, _) in self.s)

    def events(self, kind=None, participant=None, frame=None, since=None, until=None):
        if kind == "clock_fired":
            return [SimpleNamespace(agents=[c], patients=[]) for c in self.fired]
        return []


def _beat(bid, phase, weight=Weight.OPTIONAL):
    return Beat(beat_id=bid, phase=phase, weight=weight,
                achievable_via=StateIs(bid, "x", "y"))


def _arc(beats=()):
    refusal = Clock(clock_id="clock:refusal",
                    fires_when=StateIs("z", "z", "z"), effects=())
    shape = ConclusionShape(
        shape_id="shape:main", delta_type="desire_at_cost",
        tension=("hero", "want", "fear"),
        world_condition=StateIs("fact:case", "solved", "yes"),
        premise=StateIs("p", "q", "r"), refusal_variant_id="rv")
    return Arc(arc_id="arc:main", protagonist="hero", shape=shape,
               beats=tuple(beats), clocks=(), refusal_clock=refusal,
               climax_ready_k=2, climax_ready_beats=("beat:c1", "beat:c2"))


# ---- climax_ready --------------------------------------------------------

def test_climax_ready_counts_to_k():
    arc, r = _arc(), FakeReads()
    assert climax_ready(r, arc) is False
    r.set_beat("beat:c1", "achieved")
    assert climax_ready(r, arc) is False          # 1 of k=2
    r.set_beat("beat:c2", "achieved")
    assert climax_ready(r, arc) is True           # 2 of 2


# ---- current_phase -------------------------------------------------------

def test_phase_defaults_setup_with_nothing_achieved():
    assert current_phase(FakeReads(), _arc()) is Phase.SETUP


def test_phase_tracks_furthest_achieved_beat():
    arc = _arc([_beat("beat:s1", Phase.SETUP), _beat("beat:cr1", Phase.CRISIS)])
    r = FakeReads()
    r.set_beat("beat:s1", "achieved")
    assert current_phase(r, arc) is Phase.SETUP
    r.set_beat("beat:cr1", "achieved")
    assert current_phase(r, arc) is Phase.CRISIS


def test_phase_climax_when_ready():
    arc, r = _arc(), FakeReads()
    r.set_beat("beat:c1", "achieved"); r.set_beat("beat:c2", "achieved")
    assert current_phase(r, arc) is Phase.CLIMAX


def test_phase_falling_when_concluded():
    arc, r = _arc(), FakeReads()
    r.s[("fact:case", "solved")] = "yes"          # world_condition holds
    assert current_phase(r, arc) is Phase.FALLING


# ---- conclusive_eligible (Gate A) ----------------------------------------

def _ready_reads():
    r = FakeReads()
    r.set_beat("beat:c1", "achieved"); r.set_beat("beat:c2", "achieved")
    return r


def test_eligible_true_at_climax_with_candidate():
    arc = _arc()
    cand = ConclusiveCandidate(climax_beat_achieved=True)
    assert conclusive_eligible(_ready_reads(), arc, contract="story", candidate=cand)


def test_eligible_false_on_a_setup_lull():
    # Nothing achieved, no clock — a quiet early turn must NOT be eligible.
    cand = ConclusiveCandidate(climax_beat_achieved=True)  # even with a (stale) flag
    assert not conclusive_eligible(FakeReads(), _arc(), contract="story", candidate=cand)


def test_eligible_false_for_sandbox_contract():
    cand = ConclusiveCandidate(climax_beat_achieved=True)
    assert not conclusive_eligible(_ready_reads(), _arc(), contract="sandbox",
                                   candidate=cand)


def test_eligible_requires_a_candidate_event():
    # Climax-ready but nothing happened THIS turn → not eligible (don't spend the judge).
    assert not conclusive_eligible(_ready_reads(), _arc(), contract="story",
                                   candidate=ConclusiveCandidate())


def test_post_climax_window_is_a_candidate_without_a_fresh_event():
    # C1#4: the quiet-window expiry alone makes it eligible (no new event needed).
    cand = ConclusiveCandidate(post_climax_window_expired=True)
    assert conclusive_eligible(_ready_reads(), _arc(), contract="story", candidate=cand)


def test_refusal_fired_path_is_eligible():
    arc, r = _arc(), FakeReads()
    r.fired.add("clock:refusal")                  # the tragedy-of-absence path
    cand = ConclusiveCandidate(refusal_or_deadline_fired=True)
    assert conclusive_eligible(r, arc, contract="story", candidate=cand)


def test_outcome_shapes_vocabulary():
    assert "pyrrhic" not in OUTCOME_SHAPES        # collapsed into costly_victory
    assert {"triumph", "costly_victory", "failure"} <= set(OUTCOME_SHAPES)
