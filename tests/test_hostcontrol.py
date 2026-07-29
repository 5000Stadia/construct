"""Host-control conflicted-read policy (pbeo review 2026-07-28, Item 1).

The `arc:` namespace is host-control bookkeeping; a *conflicted* read there is
the EP2/Cx-167 stale-arc serve (a mid-play writer appended without retracting).
The original telemetry guard warned for the literal `arc:portfolio` ONLY — these
tests pin the class-wide sweep: every `arc:` key warns, ordinary facts stay
silent, and the four collapse sites share one policy via `hostcontrol`.
"""

import logging

from construct import hostcontrol
from construct.adapter import PorcelainWorldReads


def test_is_host_control_names_the_arc_class():
    for e in ("arc:portfolio", "arc:main", "arc:cheap", "arc:tangent_7",
              "arc:replan_2", "arc:ep_3", "arc:gen_1"):
        assert hostcontrol.is_host_control(e), e
    for e in ("place:hall", "person:rival", "time:calendar", "arcane", "", None):
        assert not hostcontrol.is_host_control(e), e


def test_collapse_returns_value_for_known_and_conflicted_none_for_unknown():
    known = {"status": "known", "fact": {"value": "v1"}}
    conflicted = {"status": "conflicted", "fact": {"value": "holding"}}
    unknown = {"status": "unknown"}
    assert hostcontrol.collapse_state(known, "person:x", "name") == "v1"
    # conflicted still serves the engine's holding value — telemetry, not a fix
    assert hostcontrol.collapse_state(conflicted, "arc:main", "main_arc") == "holding"
    assert hostcontrol.collapse_state(unknown, "person:x", "name") is None
    assert hostcontrol.collapse_state("not-a-dict", "arc:main", "x") is None


def test_conflicted_host_control_warns_for_the_whole_class(caplog):
    """The regression: before the sweep, only `arc:portfolio` warned. Now every
    host-control key does, and ordinary facts stay silent."""
    conflicted = {"status": "conflicted", "fact": {"value": "stale"}}

    for entity in ("arc:portfolio", "arc:main", "arc:tangent_9", "arc:replan_1"):
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="construct.hostcontrol"):
            assert hostcontrol.collapse_state(conflicted, entity, "attr") == "stale"
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, f"expected a conflicted-read warning for {entity}"
        assert entity in warnings[0].getMessage()

    # a conflicted ORDINARY fact (place kind, person field) is collapsed silently
    for entity in ("place:hall", "person:rival"):
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="construct.hostcontrol"):
            assert hostcontrol.collapse_state(conflicted, entity, "kind") == "stale"
        assert not [r for r in caplog.records if r.levelno == logging.WARNING], entity


class _FakePorcelain:
    """Minimal `world.porcelain` stand-in: returns a scripted state dict and
    records the as_of it was called with (proving the horizon is preserved)."""

    def __init__(self, st):
        self._st = st
        self.calls = []

    def state(self, entity, attribute, *, frame="canon", as_of=None):
        self.calls.append((entity, attribute, frame, as_of))
        return self._st


class _FakeWorld:
    def __init__(self, porcelain):
        self.porcelain = porcelain


def test_adapter_state_routes_a_conflicted_arc_read_through_the_policy(caplog):
    conflicted = {"status": "conflicted", "fact": {"value": "stale-arc"}}
    reads = PorcelainWorldReads(_FakeWorld(_FakePorcelain(conflicted)), horizon=5.0)
    with caplog.at_level(logging.WARNING, logger="construct.hostcontrol"):
        value = reads.state("arc:main", "main_arc")
    assert value == "stale-arc"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings and "arc:main" in warnings[0].getMessage()
    # horizon is still threaded through — the policy takes the fetched dict, not the call
    assert reads._p.calls[-1][3] == 5.0
