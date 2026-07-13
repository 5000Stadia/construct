"""WORLD-GROWTH G-A piece A — the pending-adoption state machine."""

import pytest

from construct.tangent import (EXPIRY_TURNS, PENDING, cancel_rows,
                               declaration, may_confirm, pending_rows,
                               read_pending)


def test_declaration_reads_fail_closed():
    ok = {"declares_tangent_aim": True,
          "tangent_aim": "  build a life  aboard the Gullwing "}
    assert declaration(ok, kind="action") == \
        "build a life aboard the Gullwing"
    # every non-affirmed shape reads NO declaration
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


def test_pending_rows_shape_and_host_bugs():
    rows = pending_rows("a life aboard", turn=7,
                        action="I sign on with the Gullwing.", at=5007.0)
    by = {(r["entity"], r["attribute"]): r["value"] for r in rows}
    assert by[(PENDING, "aim")] == "a life aboard"
    assert by[(PENDING, "declared_turn")] == "7"
    assert by[(PENDING, "source_action")] == "I sign on with the Gullwing."
    assert all(r["valid_from"] == 5007.0 for r in rows)
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            pending_rows(bad, turn=7, action="x", at=5007.0)
    for bad in (True, -1, 1.5, "7"):
        with pytest.raises(ValueError):
            pending_rows("aim", turn=bad, action="x", at=5007.0)


class _Reads:
    def __init__(self, table):
        self.table = table

    def state(self, entity, attribute, frame=None):
        assert frame == "session:main"
        return self.table.get((entity, attribute))


def test_read_pending_expiry_and_supersession_semantics():
    live = _Reads({(PENDING, "aim"): "a life aboard",
                   (PENDING, "declared_turn"): "7",
                   (PENDING, "source_action"): "I sign on."})
    p = read_pending(live, turn=10)
    assert p == {"aim": "a life aboard", "declared_turn": 7,
                 "source_action": "I sign on."}
    # the expiry boundary: EXPIRY_TURNS quiet turns still live; one more
    # lapses it structurally
    assert read_pending(live, turn=7 + EXPIRY_TURNS) is not None
    assert read_pending(live, turn=7 + EXPIRY_TURNS + 1) is None
    # an explicit cancel (aim superseded to "") reads as NO candidate
    cancelled = _Reads({(PENDING, "aim"): "",
                        (PENDING, "declared_turn"): "7"})
    assert read_pending(cancelled, turn=8) is None
    assert cancel_rows(at=5008.0)[0]["value"] == ""
    # malformed persisted state fails toward the ordinary story
    assert read_pending(_Reads({(PENDING, "aim"): "x",
                                (PENDING, "declared_turn"): "soon"}),
                        turn=8) is None
    assert read_pending(_Reads({}), turn=8) is None

    class _Boom:
        def state(self, *a, **k):
            raise RuntimeError("session down")
    assert read_pending(_Boom(), turn=8) is None


def test_may_confirm_is_host_structure():
    pending = {"aim": "a life aboard", "declared_turn": 7,
               "source_action": "I sign on."}
    assert may_confirm(pending, turn=8, committed=True) is True
    # a single line of enthusiasm adopts nothing: same-turn, uncommitted,
    # or absent pending all refuse
    assert may_confirm(pending, turn=7, committed=True) is False
    assert may_confirm(pending, turn=8, committed=False) is False
    assert may_confirm(pending, turn=8, committed="true") is False
    assert may_confirm(None, turn=8, committed=True) is False
    assert may_confirm({"aim": "x", "declared_turn": "7"},
                       turn=8, committed=True) is False
