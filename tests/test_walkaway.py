"""WALK-AWAY-DECLARED (docs/design/WALK-AWAY-DECLARED.md r3, R40; ruleset IR-16).

Abandonment is never inferred: a declaration opens ONE in-world question; only an explicit yes
to it reaches the refusal clock — the same turn, on any input kind."""
import json
import pathlib
import re

from construct.adapter import PorcelainWorldReads, frame_facts
from construct.arc.executor import turn_time
from construct.clock import ELAPSED_ATTR, ELAPSED_ENTITY
from construct.intent import TurnIntent
from construct.provider import _SILENT_DEFAULTS, task_of
from construct.provider import StubProvider as _Stub
from construct.turnloop import WALKAWAY_RETRY_MIN, _walkaway_state, _walkaway_transition
from tests.test_integration import (  # noqa: F401
    PLAYER, _narrate_prompt, make_arc, run_turn, seed_arc, world,
)

SCOPE = [PLAYER, "place:study"]
_BASE = {"kind": "action", "claims_are": "act", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""}
GOAL = "find who falsified the ledger"


def StubProvider(responses):  # noqa: N802 — also answers pacing nudges silently
    return _Stub(responses, silent_defaults={
        **_SILENT_DEFAULTS, "ndg": ("directive", {"thread": "", "directive": ""})})


def _record(world):
    raw = PorcelainWorldReads(world).state("session:walkaway", "record", frame="session:main")
    return json.loads(raw) if raw else None


def _abandon_events(world):
    return PorcelainWorldReads(world).events(kind="event:abandoned")


def _refusal_firings(world):
    return [e for e in PorcelainWorldReads(world).events(kind="clock_fired", frame="plot:main")
            if "clock:refusal" in (e.agents or ())]


def _classify_prompt(provider):
    return next(p for (p, _s, _t) in provider.calls if task_of(p) == "cls")


def _ask(world, arc, turn=5):
    world._extractions.extend([{"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE, "declares_giving_up": True},
                         {"prose": "Reginald looks up. 'You're truly done with it?'"}])
    r = run_turn(world, arc, prov, "I'm done with this case. I'm leaving town.", turn=turn,
                 scenario_mode="win_loss", scope=SCOPE, goal=GOAL)
    return r, prov


# ------------------------------------------------------------------ 1. declaring asks

def test_declaring_opens_a_question_never_an_ending(world):
    arc = make_arc()
    seed_arc(world, arc)
    r, prov = _ask(world, arc)
    assert GOAL in _classify_prompt(prov)
    rec = _record(world)
    assert rec["status"] == "asked" and rec["asked_turn"] == 5
    assert not _abandon_events(world) and not _refusal_firings(world)
    assert not r.trace.terminal
    assert "MAY BE WALKING AWAY" in _narrate_prompt(prov)


# ---------------------------------------- 2. an explicit yes ends it, the same turn, once

def _confirm(world, arc, verdict, text, mode="pure", turn=6):
    world._extractions.extend([{"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE, **verdict, "confirms_walkaway": True},
                         {"prose": "You walk away; behind you the case goes cold."}])
    return run_turn(world, arc, prov, text, turn=turn, scenario_mode="win_loss", mode=mode,
                    scope=SCOPE, goal=GOAL), prov


def _assert_one_refusal(world):
    assert len(_abandon_events(world)) == 1
    assert len(_refusal_firings(world)) == 1
    assert _record(world)["status"] == "confirmed"


def test_explicit_yes_fires_the_refusal_this_turn(world):
    arc = make_arc()
    seed_arc(world, arc)
    _ask(world, arc)
    r, prov = _confirm(world, arc, {}, "Yes. I'm done with it.")
    _assert_one_refusal(world)
    assert r.trace.terminal
    cats = [str(x.value) for x in frame_facts(world, "session:main", attribute="outcome_category")]
    assert cats and cats[-1] == "abandoned"
    assert "CONFIRMS" not in _classify_prompt(prov) and "QUESTION IS STANDING" in \
        _classify_prompt(prov)


import pytest  # noqa: E402


@pytest.mark.parametrize("kind,text", [
    ("exit", "Yes, I'm done with it. Quit."),
    ("question", "Done? Yes. Isn't it obvious?"),
    ("declaration", "I am finished with this case."),
])
def test_confirmation_on_every_early_return_kind(world, kind, text):
    """2b: exit, question and a pure-mode declaration are played as an action when confirmed:
    the refusal fires this turn, once, and no early return swallows it."""
    arc = make_arc()
    seed_arc(world, arc)
    _ask(world, arc)
    r, _prov = _confirm(world, arc, {"kind": kind}, text)
    _assert_one_refusal(world)
    assert r.trace.terminal and not r.exit_requested
    assert "canon-strict" not in (r.prose or "")


def test_confirmation_alongside_an_authored_event(world):
    """2c: a confirmed turn on which an authored Occurred beat also fires gives two distinct
    events (the authored one with its action anchor), and the refusal fires once."""
    import dataclasses
    from construct.arc.conditions import Occurred
    from construct.arc.grammar import Beat, Phase, Weight
    base = make_arc()
    arc = dataclasses.replace(base, beats=(*base.beats, Beat(
        "beat:door", Phase.RISING, Weight.OPTIONAL, achievable_via=Occurred("door_slammed"))))
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    run_turn(world, arc, StubProvider([{**_BASE, "declares_giving_up": True},
                                       {"occurred": []},     # the detector: nothing yet
                                       {"prose": "'Truly done?' Reginald asks."}]),
             "I'm done with this case.", turn=5, scenario_mode="win_loss", scope=SCOPE,
             goal=GOAL)
    assert _record(world)["status"] == "asked"
    world._extractions.extend([{"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE, "confirms_walkaway": True},
                         {"occurred": ["door_slammed"]},
                         {"prose": "The door slams behind you; you do not look back."}])
    run_turn(world, arc, prov, "Yes. I slam the door and go.", turn=6,
             scenario_mode="win_loss", scope=SCOPE, goal=GOAL)
    R = PorcelainWorldReads(world)
    _assert_one_refusal(world)
    assert R.events(kind="door_slammed")
    assert {e.event_id for e in R.events(kind="door_slammed")}.isdisjoint(
        {e.event_id for e in _abandon_events(world)})


# ------------------------------------------ 3. every other next submission declines

def test_anything_else_declines(world):
    arc = make_arc()
    seed_arc(world, arc)
    _ask(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    prov = StubProvider([{**_BASE}, {"prose": "Reginald frowns at the question."}])
    run_turn(world, arc, prov, "One last question for Reginald: where was he at nine?",
             turn=6, scenario_mode="win_loss", scope=SCOPE, goal=GOAL)
    assert _record(world)["status"] == "declined"
    assert not _abandon_events(world) and not _refusal_firings(world)
    # the next turn: no standing question, and the walk-away is withheld (suppressed)
    world._extractions.extend([{"items": []}, {"items": []}])
    prov2 = StubProvider([{**_BASE}, {"prose": "…"}])
    run_turn(world, arc, prov2, "I look out of the window.", turn=7,
             scenario_mode="win_loss", scope=SCOPE, goal=GOAL)
    assert GOAL not in _classify_prompt(prov2)


def test_exit_and_denied_declaration_decline(world):
    arc = make_arc()
    seed_arc(world, arc)
    _ask(world, arc)
    prov = StubProvider([{**_BASE, "kind": "exit"}])
    r = run_turn(world, arc, prov, "quit", turn=6, scenario_mode="win_loss", scope=SCOPE,
                 goal=GOAL)
    assert r.exit_requested and _record(world)["status"] == "declined"
    assert not _abandon_events(world)


# ----------------------------------------- 4-6. the record: boundary, episode, no clock

def _intent(**kw):
    return TurnIntent.from_verdict({**_BASE, **kw}, "x")


def _set_clock(world, minutes, at):
    world.porcelain.ingest_structured([
        {"entity": ELAPSED_ENTITY, "attribute": "kind", "value": "clock", "timeless": True},
        {"entity": ELAPSED_ENTITY, "attribute": ELAPSED_ATTR, "value": minutes,
         "value_type": "literal", "valid_from": at}])


def test_retry_boundary_is_exactly_one_story_day(world):
    arc = make_arc()
    seed_arc(world, arc)
    _set_clock(world, 100, turn_time(1))
    p, R = world.porcelain, PorcelainWorldReads(world)
    wa = _walkaway_state(world, p, R, arc, GOAL)
    _walkaway_transition(p, _intent(declares_giving_up=True), wa, 2, arc)        # asked
    wa = _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)
    _walkaway_transition(p, _intent(), wa, 3, arc)                               # declined @100
    _set_clock(world, 100 + WALKAWAY_RETRY_MIN - 1, turn_time(4))
    assert not _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)["eligible"]
    _set_clock(world, 100 + WALKAWAY_RETRY_MIN, turn_time(5))
    assert _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)["eligible"]


def test_record_from_another_episode_is_ignored(world):
    arc = make_arc()
    seed_arc(world, arc)
    p = world.porcelain
    wa = _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)
    _walkaway_transition(p, _intent(declares_giving_up=True), wa, 2, arc)        # asked, ch1
    p.ingest_structured([{"entity": "event:episode_start_4", "attribute": "kind",
                          "value": "episode_start", "valid_from": turn_time(4)}],
                        frame="session:main")
    wa2 = _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)
    assert wa2["standing"] is False and wa2["eligible"] is True


def test_no_clock_suppresses_for_the_episode(world):
    arc = make_arc()
    seed_arc(world, arc)
    p = world.porcelain
    wa = _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)
    assert wa["minutes"] is None                                  # no elapsed row at all
    _walkaway_transition(p, _intent(declares_giving_up=True), wa, 2, arc)
    wa = _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)
    _walkaway_transition(p, _intent(), wa, 3, arc)                # declined, no clock
    assert not _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)["eligible"]
    _set_clock(world, 0, turn_time(4))                            # a row reading 0 = clocked
    assert _walkaway_state(world, p, PorcelainWorldReads(world), arc, GOAL)["minutes"] == 0


# ----------------------------------------------- 6b. reserved kinds, 8-9. no inference

def test_generic_detector_never_writes_an_abandonment(world):
    import dataclasses
    from construct.arc.conditions import Occurred
    from construct.arc.grammar import Beat, Phase, Weight
    from construct.turnloop import TurnTrace, _fire_event_occurs
    base = make_arc()
    arc = dataclasses.replace(base, beats=(*base.beats, Beat(
        "beat:quit", Phase.CLIMAX, Weight.OPTIONAL, achievable_via=Occurred("event:abandoned"))))
    seed_arc(world, arc)
    prov = StubProvider([{"occurred": ["event:abandoned"]}])
    fired = _fire_event_occurs(world, world.porcelain, PorcelainWorldReads(world), [arc], prov,
                               "I give up", "success", 3, TurnTrace(turn=3), PLAYER)
    assert fired == [] and not prov.calls and not _abandon_events(world)


def test_travel_never_infers_abandonment(world):
    arc = make_arc()
    seed_arc(world, arc)
    for t in range(5, 12):
        world._extractions.extend([{"items": []}, {"items": []}])
        prov = StubProvider([{**_BASE}, {"prose": "The road runs on."}])
        run_turn(world, arc, prov, "I keep walking south, far from the city.", turn=t,
                 scenario_mode="win_loss", scope=SCOPE, goal=GOAL)
    assert _record(world) is None and not _abandon_events(world)


def test_the_transition_is_the_sole_abandonment_writer():
    src = pathlib.Path("construct").rglob("*.py")
    writers = []
    for f in src:
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if re.search(r'["\']event:abandoned_main_', line):
                writers.append(f"{f}:{i}")
    assert len(writers) == 1 and "turnloop.py" in writers[0], writers


def test_a_replanned_main_arc_starts_clean(world):
    """cr code review: a question asked about the PRIOR main arc can neither stand nor be
    confirmed after a same-episode replan swaps the main arc."""
    import dataclasses
    old = make_arc()
    seed_arc(world, old)
    p = world.porcelain
    wa = _walkaway_state(world, p, PorcelainWorldReads(world), old, GOAL)
    _walkaway_transition(p, _intent(declares_giving_up=True), wa, 2, old)       # asked, old
    new = dataclasses.replace(old, arc_id="arc:replanned")
    wa2 = _walkaway_state(world, p, PorcelainWorldReads(world), new, GOAL)
    assert wa2["standing"] is False and wa2["eligible"] is True                 # stale prompt gone
    confirmed, _line = _walkaway_transition(p, _intent(confirms_walkaway=True), wa2, 3, new)
    assert confirmed is False and not _abandon_events(world)
