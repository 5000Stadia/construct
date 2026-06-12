"""Atom evaluation over fixture folds — the §2.3 semantics, including
the three-valued rules (Codex r1 finding 2) and frame-fold membership
(finding 3)."""

from holodeck.arc.conditions import (
    UNRESOLVED,
    AllOf,
    AnyOf,
    AtLeast,
    BeatAchieved,
    ClockFired,
    EventRow,
    InFrame,
    Located,
    Not,
    Occurred,
    PacingCounters,
    StateIs,
    TurnsElapsed,
    TurnsQuiet,
    evaluate,
)
from holodeck.arc.truth import Truth

from tests.fixtureworld import FixtureWorld

T, F, I = Truth.TRUE, Truth.FALSE, Truth.INDETERMINATE


def make_world() -> FixtureWorld:
    return FixtureWorld(
        entities={"person:vance", "obj:ledger", "place:wellhead", "place:office",
                  "obj:drawer", "person:clerk"},
        states={
            ("canon", "obj:ledger", "condition"): "burned",
            ("canon", "obj:drawer", "contents"): UNRESOLVED,
            ("plot:main", "beat:discovery", "status"): "achieved",
            ("plot:main", "beat:confrontation", "status"): "pending",
        },
        chains={
            "obj:ledger": ["place:office", "place:anchor"],
            "person:vance": ["place:wellhead", "place:anchor"],
        },
        frames={
            "knows:player": {("person:vance", "visited", "place:wellhead")},
        },
        event_log={
            "canon": [
                EventRow("event:badge_entry", "badge_entry",
                         agents=("person:vance",), at=2340),
            ],
            "plot:main": [
                EventRow("event:clock_cover_up_fired_1", "clock_fired",
                         agents=("clock:cover_up",), at=10),
            ],
        },
    )


def test_state_resolved_true_false():
    w = make_world()
    assert evaluate(StateIs("obj:ledger", "condition", "burned"), w) is T
    assert evaluate(StateIs("obj:ledger", "condition", "pristine"), w) is F


def test_state_unresolved_is_indeterminate_and_negation_keeps_it():
    w = make_world()
    atom = StateIs("obj:drawer", "contents", "obj:pipe")
    assert evaluate(atom, w) is I
    assert evaluate(Not(atom), w) is I  # unknown never collapses to false


def test_state_unknown_entity_indeterminate():
    w = make_world()
    assert evaluate(StateIs("obj:ghost", "color", "red"), w) is I


def test_located():
    w = make_world()
    assert evaluate(Located("obj:ledger", "place:office"), w) is T
    assert evaluate(Located("obj:ledger", "place:wellhead"), w) is F
    assert evaluate(Located("obj:ghost", "place:office"), w) is I


def test_in_frame_definite_both_ways():
    w = make_world()
    known = InFrame("knows:player", "person:vance", "visited", "place:wellhead")
    unknown = InFrame("knows:player", "person:clerk", "hid", "obj:core")
    assert evaluate(known, w) is T
    assert evaluate(unknown, w) is F
    assert evaluate(Not(unknown), w) is T  # frame folds are enumerable


def test_occurred_log_closure():
    w = make_world()
    happened = Occurred("badge_entry", participants=("person:vance",))
    never = Occurred("confession")
    assert evaluate(happened, w) is T
    assert evaluate(never, w) is F          # closed under the log (fiction)
    assert evaluate(Not(never), w) is T


def test_occurred_window():
    w = make_world()
    assert evaluate(Occurred("badge_entry", since=2000, until=2400), w) is T
    assert evaluate(Occurred("badge_entry", since=2400), w) is F


def test_beat_and_clock_atoms():
    w = make_world()
    assert evaluate(BeatAchieved("beat:discovery"), w) is T
    assert evaluate(BeatAchieved("beat:confrontation"), w) is F
    assert evaluate(ClockFired("clock:cover_up"), w) is T
    assert evaluate(ClockFired("clock:cover_up", n=2), w) is F


def test_counters():
    w = make_world()
    counters = PacingCounters(turns_elapsed=12, turns_quiet=5)
    assert evaluate(TurnsQuiet(5), w, counters) is T
    assert evaluate(TurnsQuiet(6), w, counters) is F
    assert evaluate(TurnsElapsed(10), w, counters) is T
    assert evaluate(TurnsQuiet(5), w, None) is I  # no session frame yet


def test_combinators_propagate_indeterminate():
    w = make_world()
    resolved = StateIs("obj:ledger", "condition", "burned")
    frontier = StateIs("obj:drawer", "contents", "obj:pipe")
    assert evaluate(AllOf((resolved, frontier)), w) is I
    assert evaluate(AnyOf((resolved, frontier)), w) is T
    assert evaluate(AtLeast(2, (resolved, frontier, Not(resolved))), w) is I
