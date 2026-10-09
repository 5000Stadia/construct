"""The one `adapter.state_value` helper (audit 2026-10 F1 / July §5): as_of binding,
collapse_state policy + telemetry, raise-reads-absent, and the foyer re-export."""

import logging

from construct import adapter, foyer
from construct.adapter import state_value


class _Porc:
    """Records each state() call's kwargs; serves canned results by (entity, attr)."""

    def __init__(self, rows, strict_signature=False):
        self.rows, self.calls, self.strict = rows, [], strict_signature

    def state(self, entity, attribute, **kw):
        if self.strict and kw:
            raise TypeError("no kwargs accepted")
        self.calls.append(kw)
        res = self.rows[(entity, attribute)]
        if isinstance(res, Exception):
            raise res
        return res


def _known(v):
    return {"status": "known", "fact": {"value": v}}


def test_known_unknown_and_raising_porcelain():
    p = _Porc({("person:x", "name"): _known("Xander"),
               ("person:x", "gone"): {"status": "unknown"},
               ("person:x", "boom"): RuntimeError("frontier")})
    assert state_value(p, "person:x", "name") == "Xander"
    assert state_value(p, "person:x", "gone") is None
    assert state_value(p, "person:x", "boom") is None


def test_as_of_is_passed_only_when_bound():
    p = _Porc({("person:x", "name"): _known("X")})
    state_value(p, "person:x", "name")
    state_value(p, "person:x", "name", as_of=12.5)
    state_value(p, "person:x", "name", as_of=0.0)   # 0.0 is a real horizon, not "unbound"
    assert p.calls == [{}, {"as_of": 12.5}, {"as_of": 0.0}]


def test_unbound_read_works_on_a_porcelain_without_as_of():
    p = _Porc({("time:elapsed", "kind"): _known("clock")}, strict_signature=True)
    assert state_value(p, "time:elapsed", "kind") == "clock"


def test_conflicted_serves_holding_value_and_warns_only_on_host_control(caplog):
    conflicted = {"status": "conflicted", "fact": {"value": "holding"}}
    p = _Porc({("arc:main", "main_arc"): conflicted, ("gauge:o2", "gauge_level"): conflicted})
    with caplog.at_level(logging.WARNING):
        assert state_value(p, "gauge:o2", "gauge_level") == "holding"
        assert not caplog.records
        assert state_value(p, "arc:main", "main_arc") == "holding"
    assert any("CONFLICTED read on host-control" in r.message for r in caplog.records)


def test_foyer_reexport_is_the_same_helper():
    assert foyer.state_value is adapter.state_value


def test_an_event_with_no_kind_reads_as_untyped():
    # pattern-buffer's events() one-reader (R22) surfaces story events the extractor wrote with
    # no kind row (event:runner_arrival); the adapter hands every reader a string
    from types import SimpleNamespace
    from construct.adapter import PorcelainWorldReads

    class _Ev:
        def events(self, **kw):
            return [{"id": "event:runner_arrival", "kind": None},
                    {"id": "event:summons", "kind": "summons", "t": 3.0}]

    rows = PorcelainWorldReads(SimpleNamespace(porcelain=_Ev())).events()
    assert [(r.event_id, r.kind) for r in rows] == [("event:runner_arrival", ""),
                                                     ("event:summons", "summons")]
