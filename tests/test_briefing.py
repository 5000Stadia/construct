"""The narrator briefing (construct/briefing.py), pinned byte for byte.

GOLDEN BRIEFINGS: five fixture turns run through `run_turn`; each turn's full briefing
(`trace.briefing`) must equal its file under tests/golden/briefing/. Those files were
produced by the turn loop BEFORE the briefing moved out of `run_turn` (audit 2026-10,
turnloop finding 2(a)), so they pin the move as byte-identical. They also make any later
prompt edit visible: regenerate with

    CONSTRUCT_REGEN_BRIEFING_GOLDEN=1 python -m pytest tests/test_briefing.py

and the diff of the golden files is the prompt change under review.

READ-ONLY: the two briefing halves must not write to the world (the one briefing block that
writes, the consequence callback, stays in `run_turn`).
"""

import copy
import dataclasses
import json
import os
from pathlib import Path

from construct.provider import StubProvider
from tests.test_integration import PLAYER, make_arc, run_turn, seed_arc, world  # noqa: F401

GOLDEN = Path(__file__).parent / "golden" / "briefing"
REGEN = os.environ.get("CONSTRUCT_REGEN_BRIEFING_GOLDEN") == "1"

_SCOPE = ["fact:secret", "person:rival", PLAYER, "place:study"]
_ACTION = {"kind": "action", "claims_are": "act", "moves_to": "", "requires": [], "needs_test": False,
           "uncertain_of": ""}
_QUESTION = dict(_ACTION, kind="question")


def _matches_golden(name: str, briefing: str) -> bool:
    path = GOLDEN / f"{name}.txt"
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(briefing.encode("utf-8"))
    assert path.exists(), f"no golden {path} (CONSTRUCT_REGEN_BRIEFING_GOLDEN=1 writes it)"
    return briefing.encode("utf-8") == path.read_bytes()


def _live_turn(world, provider):
    """A first-turn action that discovers the culprit, with every world-level overlay the
    briefing carries: game type, style, reality register, laws (one understood, one
    undiscovered) and two /ooc wishes."""
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "session:wishes", "attribute": "list", "value_type": "literal",
         "value": json.dumps(["a thunderstorm breaks", "the cat comes back"])},
    ], frame="session:main")
    world._extractions.append({"items": [
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
    ]})
    world._extractions.append({"items": []})
    laws = [
        {"name": "Ink remembers", "register": "uncanny", "disclosure": "understood",
         "rule": "written words outlast their writers", "cost_limit": "a page a day",
         "embodiment": "the ledger", "texture": "ink that will not dry"},
        {"name": "The bell binds", "register": "uncanny", "disclosure": "discovered",
         "rule": "an oath sworn under the bell cannot be broken", "cost_limit": "a voice",
         "embodiment": "the chapel bell", "texture": "a hum at noon"},
    ]
    return run_turn(world, arc, provider, "I examine the ledger closely.", turn=1,
                    style="spare, wry, close third",
                    play_style="GAME TYPE: whodunit — dramatize the deduction.",
                    laws=laws, reality="alternate")


def test_golden_live_turn(world):
    provider = StubProvider([_ACTION, {"prose": "The ledger tells you: the rival did it."}])
    result = _live_turn(world, provider)
    assert _matches_golden("live_turn", result.trace.briefing)


def test_golden_deflected_question(world):
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"refer_targets": [], "keys": [], "wants_location": False})
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([_QUESTION, {"prose": "The record is silent on that."}])
    result = run_turn(world, arc, provider, "Who is the culprit, really?", turn=1,
                      scope=_SCOPE)
    assert result.trace.adjudication.startswith("deflect")
    assert _matches_golden("deflected_question", result.trace.briefing)


def test_golden_improvised_question(world):
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"refer_targets": [], "keys": [], "wants_location": False})
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([_QUESTION, {"prose": "The canteen is two corridors over."}])
    result = run_turn(world, arc, provider, "Where's the closest place to eat?", turn=1,
                      scope=["fact:secret", PLAYER, "place:study"])
    assert _matches_golden("improvised_question", result.trace.briefing)


def test_golden_interview_with_a_present_witness(world):
    from construct.cast import CastNode, Clue
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:witness", "attribute": "in", "value": "place:study"},
    ])
    cast = {"person:witness": CastNode("person:witness", "witness", "the witness",
            holds_clues=(Clue("clue:motive", "pillar:motive", ("fact:motive", "is", "debt"),
                              coverage_effect="genuine", reveal_condition="none"),))}
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        dict(_ACTION, commits=False, commitment=""),
        {"acts": False, "action": "", "speaks": True, "intent": "deflect",
         "line_hint": "clipped"},
        {"prose": "The witness hesitates, then admits the debt."},
    ])
    result = run_turn(world, arc, provider, "I press the witness about money.", turn=2,
                      cast=cast, scope=["person:witness", PLAYER, "place:study"])
    assert "clue:motive" in result.trace.learned_clues
    assert _matches_golden("interview_present_witness", result.trace.briefing)


def test_golden_wrong_accusation_ending(world):
    from construct.arc.executor import turn_time
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured(
        [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
          "valid_from": turn_time(3)}], frame="plot:main")
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        dict(_ACTION, commits=True, commitment="accuses the clerk"),
        {"grade": "wrong", "rationale": "the clerk is not the culprit"},
        {"prose": "You name the clerk; the order is signed."},
    ])
    result = run_turn(world, arc, provider, "I accuse the clerk.", turn=5,
                      scenario_mode="win_loss", scope=_SCOPE)
    assert result.trace.terminal is True and result.trace.outcome == "lost"
    assert _matches_golden("wrong_accusation_ending", result.trace.briefing)


class _NoWrites:
    """A world/porcelain stand-in that serves reads and fails any write verb."""

    _WRITES = {"ingest", "ingest_structured", "materialize", "resolve", "retract"}

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        if name in self._WRITES:
            raise AssertionError(f"the briefing tried to write: {name}")
        value = getattr(self._inner, name)
        return _NoWrites(value) if name == "porcelain" else value


def test_briefing_halves_only_read(world, monkeypatch):
    """Mid-turn, each half is re-run on the turn's own inputs through a world and porcelain
    that refuse writes (and a copy of the trace): same parts, and no write attempted."""
    import construct.turnloop as tl

    probes = {}
    real = {"build_briefing": tl.build_briefing,
            "build_briefing_rulings": tl.build_briefing_rulings}

    def spy(name):
        def run(inp, trace):
            guarded = dataclasses.replace(inp, world=_NoWrites(inp.world), p=_NoWrites(inp.p))
            probes[name] = (real[name](guarded, copy.deepcopy(trace)), real[name](inp, trace))
            return probes[name][1]
        return run

    for name in real:
        monkeypatch.setattr(tl, name, spy(name))
    provider = StubProvider([_ACTION, {"prose": "The ledger tells you: the rival did it."}])
    result = _live_turn(world, provider)
    assert set(probes) == set(real)
    for name, (guarded_parts, parts) in probes.items():
        assert guarded_parts == parts, name
    head, rulings = probes["build_briefing"][1], probes["build_briefing_rulings"][1]
    assert result.trace.briefing == "\n".join(head + rulings)  # no callback was pending
