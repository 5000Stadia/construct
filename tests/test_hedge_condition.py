"""HEDGE-VS-CONDITION (docs/design/HEDGE-VS-CONDITION.md r2, R38; ruleset IR-18).

A hedged naming commits; a DEFERRED conclusion ("…but first Quincy on the clock") is a pending
decision the briefing carries — never fired by the host."""
import dataclasses
import json

from construct.adapter import PorcelainWorldReads
from construct.arc.conditions import InFrame
from construct.arc.grammar import Pillar
from construct.intent import TurnIntent
from construct.provider import _SILENT_DEFAULTS, task_of
from construct.provider import StubProvider as _Stub
from tests.test_integration import (  # noqa: F401
    PLAYER, PLAYER_FRAME, _narrate_prompt, make_arc, run_turn, seed_arc, world,
)

SCOPE = ["fact:secret", "person:rival", PLAYER, "place:study"]


def StubProvider(responses):  # noqa: N802 — a stub that also answers pacing nudges silently
    return _Stub(responses, silent_defaults={
        **_SILENT_DEFAULTS, "ndg": ("directive", {"thread": "", "directive": ""})})
_BASE = {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""}


def _covered_arc(world, *, covered=True):
    pillar = Pillar("pillar:culprit", "who did it", required=True,
                    genuine_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"))
    arc = dataclasses.replace(make_arc(), pillars=(pillar,))
    seed_arc(world, arc)
    if covered:
        world.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
            frame=PLAYER_FRAME)
    return arc


def _record(world):
    raw = PorcelainWorldReads(world).state("session:pending_decision", "record",
                                           frame="session:main")
    return json.loads(raw) if raw else None


def _deferred(**kw):
    return {**_BASE, "commits": True, "commitment": "accuses the rival",
            "commit_condition": "precondition",
            "commit_precondition": "Quincy confirms the clock", **kw}


# ---------------------------------------------------------------------------- 1. parse

def test_parse_gates_deferred_conclusions():
    pre = TurnIntent.from_verdict(_deferred(), "x")
    assert pre.commits is False and pre.conclusory is True
    for c in ("hedge", "none"):
        i = TurnIntent.from_verdict({**_deferred(), "commit_condition": c}, "x")
        assert i.commits is True and i.conclusory is True
    for legacy in ({**_BASE, "commits": True}, {**_deferred(), "commit_condition": "maybe"}):
        assert TurnIntent.from_verdict(legacy, "x").commits is True   # missing/garbage → none
    cond = TurnIntent.from_verdict({**_deferred(), "commit_condition": "conditional"}, "x")
    assert cond.commits is False


# -------------------------------------------------- 2-4. the Quincy turn, briefing, later commit

def test_quincy_turn_is_a_pending_decision(world):
    # coverage is completed only before the landing turn: a covered world_condition would end
    # the story on any turn by itself, masking what the deferred turn did
    arc = _covered_arc(world, covered=False)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([_deferred(), {"prose": "Quincy waits, clock in hand."}])
    r = run_turn(world, arc, provider,
                 "I'm fairly sure it's the rival, but first I need Quincy on the clock.",
                 turn=5, scenario_mode="win_loss", scope=SCOPE)
    assert not r.trace.terminal and not r.trace.commitment_grade
    assert r.trace.commitment_bounced is False and not r.trace.commitment
    assert "stage_gate:cheap" not in r.trace.cohort_calls
    assert not PorcelainWorldReads(world).events(kind="commitment", frame="session:main")
    rec = _record(world)
    assert rec["commitment"] == "accuses the rival"
    assert rec["condition"] == "Quincy confirms the clock"
    assert "PENDING DECISION" in _narrate_prompt(provider)

    # 3. the next turn's briefing still carries it
    world._extractions.extend([{"items": []}, {"items": []}])
    p2 = StubProvider([{**_BASE}, {"prose": "Quincy turns the clock over."}])
    run_turn(world, arc, p2, "I ask Quincy whether the clock was working.", turn=6,
             scenario_mode="win_loss", scope=SCOPE)
    assert "Quincy confirms the clock" in _narrate_prompt(p2)

    # 4. a later plain commit lands and clears it
    world.porcelain.ingest_structured(
        [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
        frame=PLAYER_FRAME)
    world._extractions.extend([{"items": []}, {"items": []}])
    p3 = StubProvider([{**_BASE, "commits": True, "commitment": "accuses the rival"},
                       {"prose": "You name the rival; it holds."}])
    r3 = run_turn(world, arc, p3, "It was the rival.", turn=7, scenario_mode="win_loss",
                  scope=SCOPE)
    assert r3.trace.commitment_grade
    assert _record(world) is None
    assert "PENDING DECISION" not in _narrate_prompt(p3)


# ------------------------------------------------------------ 5. the pure-mode declaration

def test_deferred_declaration_is_not_denied_in_pure_mode(world):
    arc = _covered_arc(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([{**_deferred(), "kind": "declaration"},
                             {"prose": "The words hang, unspent."}])
    r = run_turn(world, arc, provider, "It was the rival — but first I'll check the clock.",
                 turn=5, scenario_mode="win_loss", mode="pure", scope=SCOPE)
    assert "canon-strict" not in (r.prose or "")
    assert _record(world)["commitment"] == "accuses the rival"


# --------------------------------------------------------------------- 6. hedge unchanged

def test_hedge_commits_as_today(world):
    arc = _covered_arc(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([{**_deferred(), "commit_condition": "hedge"},
                             {"prose": "You name the rival; it holds."}])
    r = run_turn(world, arc, provider, "I think it was the rival.", turn=5,
                 scenario_mode="win_loss", scope=SCOPE)
    assert r.trace.commitment_grade and r.trace.terminal


# ---------------------------------------------------------------- 7. episode scope

def test_pending_decision_from_an_earlier_episode_is_ignored(world):
    from construct.arc.executor import turn_time
    from construct.turnloop import _pending_decision_pass
    world.porcelain.ingest_structured([
        {"entity": "session:pending_decision", "attribute": "record",
         "value": json.dumps({"commitment": "accuse the rival", "condition": "x",
                              "turn": 2, "at": turn_time(2)}),
         "value_type": "literal", "valid_from": turn_time(2)},
        {"entity": "event:episode_start_4", "attribute": "kind", "value": "episode_start",
         "valid_from": turn_time(4)}], frame="session:main")
    idle = TurnIntent.from_verdict({**_BASE}, "x")
    out = _pending_decision_pass(world.porcelain, PorcelainWorldReads(world), idle, "",
                                 "", False, 6)
    assert out == ""


# ------------------------------------------------- 7b. missing condition text never renders

def test_missing_condition_text_uses_the_generic_condition(world):
    from construct.turnloop import _GENERIC_CONDITION, _pending_decision_pass
    for bad in (None, "", 42):
        v = _deferred()
        if bad is None:
            v.pop("commit_precondition")
        else:
            v["commit_precondition"] = bad
        intent = TurnIntent.from_verdict(v, "fairly sure, but first the clock")
        assert intent.commits is False
        line = _pending_decision_pass(world.porcelain, PorcelainWorldReads(world), intent,
                                      intent.commitment, "", False, 3)
        assert _GENERIC_CONDITION in line and "once ." not in line
    blank = TurnIntent.from_verdict({**_deferred(), "commitment": ""}, "my own words")
    assert blank.commitment == "my own words"


# -------------------------------- 7c. clear on bounce / land, retain through the clarification

def test_bounce_clears_and_clarification_retains(world):
    arc = _covered_arc(world, covered=False)
    world._extractions.extend([{"items": []}, {"items": []}])
    run_turn(world, arc, StubProvider([_deferred(), {"prose": "…"}]),
             "Fairly sure it's the rival, but first the clock.", turn=5,
             scenario_mode="win_loss", scope=SCOPE)
    assert _record(world)
    # a plain commit held by the clarification gate: neither lands nor bounces → retained
    world._extractions.extend([{"items": []}, {"items": []}])
    held = StubProvider([{**_BASE, "commits": True, "commitment": "the rival did it"},
                         {"specified": False, "missing": ["audience"],
                          "clarification": "Say it to whom?"},
                         {"prose": "No one to hear it."}])
    r = run_turn(world, arc, held, "THE RIVAL DID IT", turn=6, scenario_mode="win_loss",
                 scope=[PLAYER, "place:study"])
    assert r.trace.commitment_clarified and _record(world)
    # a plain commit that bounces on incomplete coverage clears it
    world._extractions.extend([{"items": []}, {"items": []}])
    bounce = StubProvider([{**_BASE, "commits": True, "commitment": "accuses the rival"},
                           {"prose": "Not yet."}])
    r2 = run_turn(world, arc, bounce, "I accuse the rival.", turn=7,
                  scenario_mode="win_loss", scope=SCOPE)
    assert r2.trace.commitment_bounced and _record(world) is None


# --------------------------------------------- 7d. a deferred conclusion mints no loss event

def test_deferred_conclusion_mints_no_loss_result(world, monkeypatch):
    """6272 reads the EFFECTIVE commits: at a failure tier in SETUP, a raw-conclusory but
    deferred move must not open the result moment (it would have, on the raw flag)."""
    from construct import resolution
    from construct.arc.conditions import Occurred
    from construct.arc.grammar import Beat, Phase, Weight
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    base = make_arc()
    arc = dataclasses.replace(base, beats=(*base.beats, Beat(
        "beat:loss", Phase.CLIMAX, Weight.OPTIONAL, achievable_via=Occurred("bout_lost_main"))))
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([                 # NO detect_events stub: the gate must block it
        {**_deferred(), "needs_test": True, "uncertain_of": "risky",
         "commitment": "concedes the bout"},
        {"prose": "You hold back; it isn't settled yet."}])
    r = run_turn(world, arc, provider, "I'm ready to throw it, but first I'll test his guard.",
                 turn=2, result_events={"win": ("bout_won_main",), "loss": ("bout_lost_main",)},
                 scope=[PLAYER, "place:study"])
    assert r.trace.adjudication == "test:terrible_failure"
    assert "bout_lost_main" not in (r.trace.events_fired or [])
    assert not PorcelainWorldReads(world).events(kind="bout_lost_main")
