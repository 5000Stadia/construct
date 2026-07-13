"""WORLD-GROWTH G1 — the activation adaptor under cr's build boundary.

The safety gate is a PASSING test (the fail-closed path on today's
engine); the happy path runs against a FAKE atomic backend; the STRICT
xfail probes the REAL engine for the envelope's arrival — it flips (and
must be replaced by the real fault matrix) exactly when PB ships.
"""
from __future__ import annotations

import pytest

from construct.growth import (ActivationResult, activate_chunk,
                              atomic_capable, ordered_chunk_items)


class _NonAtomicP:
    """Today's PB 0.2.0 shape: ingest_structured without `atomic`."""

    def __init__(self):
        self.calls = []

    def ingest_structured(self, items, frame="canon", classify="inline"):
        self.calls.append(items)
        return {"rows": [{"entity": i["entity"]} for i in items]}


class _FakeAtomicP:
    """The FAKE atomic backend for the passing happy-path tests (the strict xfail probes the REAL engine)."""

    def __init__(self, abort=False):
        self.calls = []
        self.abort = abort

    def ingest_structured(self, items, atomic=False, frame="canon",
                          classify="inline"):
        self.calls.append((list(items), atomic))
        if self.abort:
            raise RuntimeError("set aborted: gate rejected edge 3")
        return {"rows": [{"entity": i["entity"]} for i in items]}


_CHUNK = [{"entity": "place:waypost", "attribute": "kind", "value": "place"},
          {"entity": "place:waypost", "attribute": "in", "value": "place:region",
           "value_type": "entity"}]


def test_fail_closed_on_todays_engine_nothing_written():
    # THE SAFETY GATE (passing, not xfail): capability absent → refuse
    # BEFORE writing; zero calls reach the engine; the receipt is a return
    # value naming activation_unavailable.
    p = _NonAtomicP()
    r = activate_chunk(p, list(_CHUNK))
    assert r == ActivationResult(ok=False, reason="activation_unavailable")
    assert p.calls == []                      # nothing written, no torn prefix
    assert not atomic_capable(p)


def test_empty_chunk_refuses_without_engine_contact():
    p = _NonAtomicP()
    assert activate_chunk(p, []).reason == "empty_chunk"
    assert p.calls == []


def test_engine_abort_is_a_clean_refusal():
    p = _FakeAtomicP(abort=True)
    r = activate_chunk(p, list(_CHUNK))
    assert not r.ok and r.reason.startswith("engine_abort:")
    # the envelope's own contract keeps canon untouched on abort; the host
    # records only the refusal (receipts stay return values)


@pytest.mark.xfail(strict=True,
                   reason="ATOMIC-ACTIVATION-V1 not shipped: the real "
                          "fault/skip/reopen matrix replaces this pin when "
                          "PB's primitive lands with pbr GREEN")
def test_atomic_integration_pin_real_engine():
    # STRICT xfail: this intentionally imports the REAL engine surface and
    # requires the atomic parameter to exist there — it flips to passing
    # (and must then be replaced by the real matrix) exactly when PB ships.
    import inspect as _i
    from patternbuffer import World  # noqa: F401
    from construct.adapter import PorcelainWorldReads  # noqa: F401
    import patternbuffer
    sig = _i.signature(patternbuffer.World.__init__)
    # the pin: today's engine has no atomic envelope anywhere we can see
    porcelain_cls = None
    for name in dir(patternbuffer):
        obj = getattr(patternbuffer, name)
        if hasattr(obj, "ingest_structured"):
            porcelain_cls = obj
            break
    assert porcelain_cls is not None
    assert "atomic" in _i.signature(porcelain_cls.ingest_structured).parameters


def test_fake_atomic_backend_happy_path():
    # against the FAKE backend the adaptor passes the set through in one
    # call with atomic=True and returns the engine receipts
    p = _FakeAtomicP()
    r = activate_chunk(p, list(_CHUNK))
    assert r.ok and len(r.receipts) == 2
    assert p.calls == [(list(_CHUNK), True)]  # ONE call, atomic flagged


def test_ordered_chunk_items_is_contractual():
    # declarations/parents strictly before references/children — the order
    # the staged-prefix gate makes semantic
    items = ordered_chunk_items(
        texture=[{"entity": "t"}], place=[{"entity": "p"}],
        moves=[{"entity": "m"}], containment=[{"entity": "c"}],
        passage=[{"entity": "x"}], encounter=[{"entity": "e"}])
    assert [i["entity"] for i in items] == ["p", "c", "x", "m", "e", "t"]


def test_typed_abort_return_is_not_success():
    # cr: the r2 envelope permits TYPED failure returns — success must be
    # affirmative; {outcome: aborted, rows: []} must never read ok
    class _TypedAbortP(_FakeAtomicP):
        def ingest_structured(self, items, atomic=False, **kw):
            return {"outcome": "aborted", "rows": [],
                    "skipped": [{"op": 3, "reason": "gate"}]}
    r = activate_chunk(_TypedAbortP(), list(_CHUNK))
    assert not r.ok and r.reason.startswith("engine_outcome:aborted")
    # skipped ops alone also refuse
    class _SkippedP(_FakeAtomicP):
        def ingest_structured(self, items, atomic=False, **kw):
            return {"rows": [{"entity": "x"}], "skipped": [{"op": 1}]}
    r2 = activate_chunk(_SkippedP(), list(_CHUNK))
    assert not r2.ok and r2.reason == "engine_skipped_ops"
    # empty rows for a nonempty chunk = ambiguous, refused
    class _EmptyP(_FakeAtomicP):
        def ingest_structured(self, items, atomic=False, **kw):
            return {"rows": []}
    r3 = activate_chunk(_EmptyP(), list(_CHUNK))
    assert not r3.ok and r3.reason == "ambiguous_receipt:no_rows"


def test_commit_set_branch_never_touches_a_broad_kwargs_ingest():
    # cr: never infer safety from one surface and invoke another — a
    # backend with commit_set plus a broad **kwargs legacy ingest must be
    # served through commit_set ONLY (the kwargs ingest would silently
    # swallow atomic=True and tear).
    class _CommitSetP:
        def __init__(self):
            self.set_calls, self.ingest_calls = [], []
        def commit_set(self, ops):
            self.set_calls.append(list(ops))
            return {"outcome": "ok",
                    "rows": [{"entity": o["item"]["entity"]} for o in ops]}
        def ingest_structured(self, items, **kwargs):  # broad legacy surface
            self.ingest_calls.append((list(items), kwargs))
            return {"rows": [{"entity": i["entity"]} for i in items]}
    p = _CommitSetP()
    r = activate_chunk(p, list(_CHUNK))
    assert r.ok and len(r.receipts) == 2
    assert p.ingest_calls == []                      # the legacy door untouched
    assert [o["op"] for o in p.set_calls[0]] == ["assert", "assert"]


def test_broad_kwargs_ingest_alone_is_not_capable():
    # a **kwargs-only ingest (no named atomic param, no commit_set) would
    # swallow the flag — it is NOT capable; the adaptor fails closed.
    class _BroadP:
        def __init__(self):
            self.calls = []
        def ingest_structured(self, items, **kwargs):
            self.calls.append(items)
            return {"rows": [{"entity": i["entity"]} for i in items]}
    p = _BroadP()
    r = activate_chunk(p, list(_CHUNK))
    assert r.reason == "activation_unavailable"
    assert p.calls == []                             # nothing written
