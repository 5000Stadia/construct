"""The arc string vocabularies are StrEnums (audit 2026-10 arc F7): every member's value is
the EXACT string the plot rows / JSON / prompts already carry, so persistence is
byte-identical and bare-string comparisons elsewhere keep working."""
import json

import pytest

from construct.arc import conditions as C
from construct.arc import io as arc_io
from construct.arc.grammar import (
    LIFECYCLE_TERMINALS, Arc, Beat, BeatStatus, Clock, ClockStatus, ConclusionShape,
    CostDisposition, Coverage, DeltaType, Gauge, Lifecycle, Outcome, OutcomeShape, Phase,
    Pillar, Pin, PinScope, Rearm, Rung, TerminalOwner, Weight, WorldEvent,
)
from construct.arc.adapt import AdaptLane
from construct.story_shapes import SHAPE_CONCLUSION, SHAPE_SIGNATURE, SHAPES, Shape

#: The stored spellings, pinned independently of the enums under test.
_VOCAB = {
    Phase: ["setup", "rising", "crisis", "climax", "falling"],
    Weight: ["required", "optional", "flavor"],
    Rung: ["surface", "draw", "converge", "confront", "refusal"],
    BeatStatus: ["pending", "achieved", "closed"],
    ClockStatus: ["armed", "fired"],
    Rearm: ["once", "repeat"],
    Lifecycle: ["active", "won", "lost", "cancelled", "incompletable"],
    Outcome: ["won", "lost"],
    Coverage: ["genuine", "false", "unfilled"],
    OutcomeShape: ["triumph", "costly_victory", "bittersweet", "partial", "failure",
                   "quiet_failure"],
    WorldEvent: ["win", "loss"],
    DeltaType: ["drive_inverted", "desire_at_cost", "desire_renounced", "identity_accepted",
                "homecoming_changed"],
    CostDisposition: ["peril_redemption", "repair", "sacrifice", "fail_forward"],
    TerminalOwner: ["commitment", "world_event"],
    PinScope: ["region", "temporal", "social"],
    Shape: ["deduction", "bond", "endurance", "contest", "gambit", "discovery", "mastery",
            "farce", "transformation"],
}


@pytest.mark.parametrize("enum_cls", list(_VOCAB), ids=lambda c: c.__name__)
def test_enum_values_are_the_stored_strings(enum_cls):
    assert [m.value for m in enum_cls] == _VOCAB[enum_cls]
    for m in enum_cls:
        assert m == m.value and hash(m) == hash(m.value)
        assert json.dumps(m) == json.dumps(m.value)
        assert f"{m}" == m.value and str(m) == m.value
        assert enum_cls(m.value) is m


def test_adapt_lanes_and_lifecycle_terminals():
    assert {"genuine", "red_herring", "plot_supersede", "decline"} <= {m.value for m in AdaptLane}
    assert "rejected_unknown_lane" in AdaptLane._value2member_map_
    assert LIFECYCLE_TERMINALS == ("won", "lost", "cancelled", "incompletable")


def test_story_shape_tables_are_keyed_by_the_nine_shapes():
    for table in (SHAPES, SHAPE_CONCLUSION, SHAPE_SIGNATURE):
        assert set(table) == {m.value for m in Shape}
    assert SHAPE_CONCLUSION["farce"]["cost_disposition"] == "fail_forward"
    assert SHAPE_CONCLUSION["farce"]["terminal_owner"] == "world_event"


def test_bool_codec_round_trips_the_stored_strings():
    assert arc_io.encode_bool(True) == "true" and arc_io.encode_bool(False) == "false"
    assert arc_io.decode_bool("true") is True and arc_io.decode_bool("false") is False
    assert arc_io.decode_bool(None) is True and arc_io.decode_bool("") is True
    assert arc_io.is_yes("yes") and not arc_io.is_yes(None) and not arc_io.is_yes("no")


def _arc(required, terminal_on_floor, escalates, rearm):
    x = C.Occurred("event:x")
    return Arc(
        "arc:t", "person:p",
        ConclusionShape("shape:t", DeltaType.DRIVE_INVERTED, ("person:p", "a", "b"), x, x, "v:t"),
        (Beat("beat:1", Phase.RISING, Weight.REQUIRED, x, unreachable_if=x),),
        (Clock("clock:a", x, (), bound_to="beat:1", rung=Rung.DRAW, rearm=rearm),),
        Clock("clock:refusal", x, (), bound_to="arc:t", rung=Rung.REFUSAL),
        1, ("beat:1",), {Phase.SETUP: 3},
        pins=(Pin("pin:1", PinScope.REGION, "e:1", "d", escalates=escalates),),
        pillars=(Pillar("pillar:1", "L", required=required, genuine_via=x),),
        gauges=(Gauge("gauge:o", "oxygen", 10.0, 0.0, -1.0,
                      terminal_on_floor=terminal_on_floor),))


@pytest.mark.parametrize("required", [True, False])
@pytest.mark.parametrize("terminal_on_floor", [True, False])
@pytest.mark.parametrize("escalates", [True, False])
@pytest.mark.parametrize("rearm", [Rearm.ONCE, "repeat"])
def test_rows_round_trip_is_byte_identical_and_plain_typed(
        required, terminal_on_floor, escalates, rearm):
    arc = _arc(required, terminal_on_floor, escalates, rearm)
    items = arc_io.arc_to_items(arc) + arc_io.index_items(arc)
    # no enum member leaks into a row value: plain str / int / float only
    assert all(type(i["value"]) in (str, int, float) for i in items)
    table = {(i["entity"], i["attribute"]): i["value"] for i in items}

    class Reads:
        def state(self, entity, attribute, frame=None):
            return table.get((entity, attribute))

    back = arc_io.arc_from_frame(Reads(), "arc:t")
    assert json.dumps(arc_io.arc_to_items(back) + arc_io.index_items(back), sort_keys=True) == \
        json.dumps(items, sort_keys=True)
    cached = arc_io.arc_from_cache(json.loads(json.dumps(arc_io.arc_to_cache(arc))))
    assert json.dumps(arc_io.arc_to_items(cached), sort_keys=True) == \
        json.dumps(arc_io.arc_to_items(arc), sort_keys=True)
