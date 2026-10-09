"""TurnTrace's typed control fields (audit 2026-10, turnloop finding 5).

The trace's string receipts (`growth`, `distance_unknown`, `deliberating`, `movement_status`)
are logged, shown by --debug and persisted, so they stay byte-identical. Their READERS use
typed siblings (`growth_outcome`, `distance_unknown_route`, `deliberation`) and a
`MovementStatus` StrEnum instead of parsing the string back.

Two proofs, over eight fixture turns:
  * RECEIPTS: the whole `trace.to_dict()` (every receipt, plus the assembled briefing) must
    equal tests/golden/turntrace/receipts.json, captured from the turn loop BEFORE the typed
    fields existed. A change to any receipt string, or a typed field leaking into the
    --debug dump, fails here. Regenerate (and review the diff) with

        CONSTRUCT_REGEN_TURNTRACE_GOLDEN=1 python -m pytest tests/test_turntrace_typed.py

  * AGREEMENT: on those same turns every typed field agrees with its string form.
"""

import json
import os
from pathlib import Path

import pytest

from construct.provider import StubProvider
from tests.test_integration import (PLAYER, _deadline_arc, _hall_world, make_arc,  # noqa: F401
                                    run_turn, seed_arc, world)

GOLDEN = Path(__file__).parent / "golden" / "turntrace" / "receipts.json"
REGEN = os.environ.get("CONSTRUCT_REGEN_TURNTRACE_GOLDEN") == "1"

_CLASSIFY = {"requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
             "commitment": ""}


def _receipts(trace) -> dict:
    """Every receipt of the turn as plain data, minus the wall-clock timings."""
    d = trace.to_dict()
    d.pop("timings", None)
    return json.loads(json.dumps(d, sort_keys=True))


def _check_agreement(trace) -> None:
    from construct.turnloop import GrowthOutcome, MovementStatus
    # movement_status: an enum whose value IS the receipt string
    assert isinstance(trace.movement_status, MovementStatus)
    assert str(trace.movement_status) == trace.movement_status.value
    assert repr(trace.movement_status) == repr(trace.movement_status.value)
    # growth: the typed outcome renders to exactly the receipt, and `activated` agrees
    assert isinstance(trace.growth_outcome, GrowthOutcome)
    assert str(trace.growth_outcome) == trace.growth
    assert trace.growth_outcome.activated == trace.growth.startswith("activated:")
    # distance_unknown: the (origin, dest) pair renders to the receipt
    route = trace.distance_unknown_route
    if trace.distance_unknown:
        o, _, d = trace.distance_unknown.partition("->")
        assert route == (o, d)
        assert f"{route[0]}->{route[1]}" == trace.distance_unknown
    else:
        assert route is None
    # deliberating: the typed hold renders to the receipt and splits as the briefing used to
    delib = trace.deliberation
    if trace.deliberating:
        assert delib is not None and str(delib) == trace.deliberating
        assert delib.label == trace.deliberating.split(" — ")[0]
        assert delib.weighing == trace.deliberating.split(" — ", 1)[-1]
        assert trace.movement_status == "deliberating"
    else:
        assert delib is None


def _distance_unknown(world, tmp_path, monkeypatch):
    arc = make_arc()
    seed_arc(world, arc)
    _hall_world(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_CLASSIFY, kind="action", moves_to="the consulting room in the village"),
        {"verdict": "new", "match": ""},
        {"prose": "The storm walks you down the long dark lane to the village."},
        {"advance_minutes": 75, "jump_to_phase": "", "jump_days": 0, "reason": "a night walk"},
    ])
    r = run_turn(world, arc, provider, "I go to the consulting room in the village.",
                 turn=2, scope=[PLAYER, "place:parlor"])
    return {"distance_unknown": r.trace}


def _deliberation(world, tmp_path, monkeypatch):
    arc = _deadline_arc(threshold=100.0)
    seed_arc(world, arc)
    _hall_world(world)
    world._extractions.extend([{"items": []}] * 4)
    move = dict(_CLASSIFY, kind="action", moves_to="the consulting room in the village")
    provider = StubProvider([
        move, {"verdict": "new", "match": ""},
        {"advance_minutes": 120, "jump_to_phase": "", "jump_days": 0, "reason": "a ride"},
        {"prose": "You pause at the door, weighing the road against the hour."},
        move, {"verdict": "new", "match": ""},
        {"prose": "You take the road anyway; the night takes its due."},
    ])
    r1 = run_turn(world, arc, provider, "I ride to the consulting room in the village.",
                  turn=2, scope=[PLAYER, "place:parlor"])
    r2 = run_turn(world, arc, provider, "I ride to the consulting room in the village.",
                  turn=3, scope=[PLAYER, "place:parlor"])
    return {"deliberation_hold": r1.trace, "deliberation_committed": r2.trace}


def _blocked(world, tmp_path, monkeypatch):
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:bluegate_yard", "attribute": "kind",
         "value": "murder scene yard", "timeless": True},
        {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    import construct.turnloop as tl
    monkeypatch.setattr(tl, "_route_obstruction", lambda *a, **k: {
        "status": "blocked", "via": "obj:door1",
        "evidence": [{"entity": "obj:door1", "attribute": "state", "value": "shut"}]})
    provider = StubProvider([
        dict(_CLASSIFY, kind="action", moves_to="the scene of the crime",
             npcs_dismissed=[], moved_with=[]),
        {"verdict": "existing", "match": "place:bluegate_yard"},
        {"prose": "The door will not give."},
    ])
    r = run_turn(world, arc, provider, "I go to the scene of the crime.", turn=2,
                 scope=[PLAYER, "place:study"])
    return {"blocked": r.trace}


def _ambiguous(world, tmp_path, monkeypatch):
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:north_cellar", "attribute": "kind", "value": "cellar",
         "timeless": True},
        {"entity": "place:north_cellar", "attribute": "name", "value": "the north cellar"},
        {"entity": "place:south_cellar", "attribute": "kind", "value": "cellar",
         "timeless": True},
        {"entity": "place:south_cellar", "attribute": "name", "value": "the south cellar"},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_CLASSIFY, kind="action", moves_to="the basement"),
        {"verdict": "ambiguous", "match": ""},
        {"prose": "“Which cellar do you mean, sir — north or south?”"},
    ])
    r = run_turn(world, arc, provider, "I head down to the basement.", turn=2,
                 scope=[PLAYER, "place:study", "place:north_cellar", "place:south_cellar"])
    return {"ambiguous": r.trace}


def _plain_question(world, tmp_path, monkeypatch):
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_CLASSIFY, kind="question", moves_to=""),
        {"prose": "The study is quiet."},
    ])
    r = run_turn(world, arc, provider, "What do I see?", turn=1,
                 scope=[PLAYER, "place:study"])
    return {"plain_question": r.trace}


def _growth_case(name, queue, tmp_path, monkeypatch, *, unavailable=False):
    import construct.growth as growth_mod
    from construct.turnloop import run_turn as raw_run_turn
    from tests.test_growth import _wired_arc, _wired_world
    if unavailable:
        monkeypatch.setattr(growth_mod, "_capability", lambda p: "")
    w = _wired_world(tmp_path)
    try:
        r = raw_run_turn(w, _wired_arc(), StubProvider(queue), "I keep moving away.", turn=1)
        return {name: r.trace}
    finally:
        try:
            w.close()
        except Exception:  # noqa: BLE001
            pass


def _growth_activated(world, tmp_path, monkeypatch):
    from tests.test_growth import _classify, _good
    npt = {"acts": True, "action": "waters his team at the trough", "speaks": True,
           "intent": "size up the newcomer", "line_hint": ""}
    queue = ([_classify(), _good(), dict(npt), dict(npt)]
             + [{"prose": "The waypost, and a farmer at it."}] * 4)
    return _growth_case("growth_activated", queue, tmp_path / "g", monkeypatch)


def _growth_declined(world, tmp_path, monkeypatch):
    from tests.test_growth import _classify, _good
    queue = [_classify(), dict(_good(), confidence=0.1)]
    return _growth_case("growth_declined", queue, tmp_path / "g", monkeypatch)


def _growth_unavailable(world, tmp_path, monkeypatch):
    from tests.test_growth import _classify, _good
    return _growth_case("growth_unavailable", [_classify(), _good()], tmp_path / "g",
                        monkeypatch, unavailable=True)


SCENARIOS = [_distance_unknown, _deliberation, _blocked, _ambiguous, _plain_question,
             _growth_activated, _growth_declined, _growth_unavailable]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda f: f.__name__.lstrip("_"))
def test_receipts_are_byte_identical_and_typed_fields_agree(scenario, world, tmp_path,
                                                            monkeypatch):
    traces = scenario(world, tmp_path, monkeypatch)
    got = {name: _receipts(t) for name, t in traces.items()}
    if REGEN:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        golden = json.loads(GOLDEN.read_text("utf-8")) if GOLDEN.exists() else {}
        golden.update(got)
        GOLDEN.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n", "utf-8")
        pytest.skip("golden regenerated")
    golden = json.loads(GOLDEN.read_text("utf-8"))
    for name, receipts in got.items():
        assert receipts == golden[name], f"{name}: receipts drifted from the golden"
    for trace in traces.values():
        _check_agreement(trace)
    # a vacuous pass would prove nothing: each scenario must exercise what it is named for
    t = next(iter(traces.values()))
    if scenario is _distance_unknown:
        assert t.distance_unknown_route is not None and t.movement_status == "clear"
    elif scenario is _deliberation:
        assert traces["deliberation_hold"].deliberation is not None
        assert traces["deliberation_committed"].deliberation is None
        assert "YOUR OWN MIND WEIGHS IT" in traces["deliberation_hold"].briefing
    elif scenario is _blocked:
        assert t.movement_status == "blocked"
    elif scenario is _ambiguous:
        assert t.movement_status == "ambiguous"
    elif scenario is _growth_activated:
        assert t.growth_outcome.activated
    elif scenario is _growth_declined:
        assert t.growth_outcome.kind == "declined"
    elif scenario is _growth_unavailable:
        assert t.growth_outcome.kind == "failed" and t.growth == "activation_unavailable"


def test_growth_outcome_renders_every_kind():
    from construct.turnloop import GrowthOutcome
    assert str(GrowthOutcome()) == ""
    assert str(GrowthOutcome("denied", "no_growth_here")) == "denied:no_growth_here"
    assert str(GrowthOutcome("declined", "unlicensed:place.name_concealed")) \
        == "declined:unlicensed:place.name_concealed"
    assert str(GrowthOutcome("failed", "engine_abort:boom")) == "engine_abort:boom"
    assert GrowthOutcome("activated", "place:x").activated
    assert not GrowthOutcome("declined", "activated:").activated


def test_movement_status_values_are_the_historic_strings():
    from construct.turnloop import MovementStatus
    assert {m.value for m in MovementStatus} == {
        "", "clear", "blocked", "obscured", "deliberating", "undiscovered", "in_scene",
        "ambiguous"}
    assert MovementStatus.NONE == "" and not MovementStatus.NONE
    assert json.dumps({"s": MovementStatus.CLEAR}) == '{"s": "clear"}'
    assert f"{MovementStatus.IN_SCENE}" == "in_scene"
