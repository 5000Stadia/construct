"""Session API (letter 034) — real coverage with the StubProvider and a
real engine World, plus the Discord bot's pure routing logic (no
discord.py needed)."""

import json
import shutil

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct import Session
from construct.arc import io as arc_io
from construct.arc.executor import turn_time
from construct.discord_bot import _handle_command, _Pipe
from construct.game import WORLDS_DIR, slot_path
from construct.provider import StubProvider

PLAYER = "person:player"
PLAYER_FRAME = f"knows:{PLAYER}"


def _author_scenario(path, world_id):
    """Build a tiny pristine scenario .world with an arc + meta, the way
    session-zero would leave one."""
    extractions = []
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id=world_id, model=StubModel(fallback=fallback),
              stance="fiction", title="Session Test World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:study"},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
        {"entity": "person:rival", "attribute": "kind", "value": "person", "timeless": True},
    ])
    from construct.arc.conditions import InFrame, TurnsQuiet
    from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
    beat = Beat("beat:discover", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"))
    refusal = Clock("clock:refusal", TurnsQuiet(15),
                    effects=({"entity": "event:concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape("shape:main", "drive_inverted",
                            (PLAYER, "drive:comfort", "drive:truth"),
                            world_condition=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"),
                            premise=InFrame("canon", "fact:secret", "culprit", "person:rival"),
                            refusal_variant_id="shape:refused")
    arc = Arc(arc_id="arc:main", protagonist=PLAYER, shape=shape, beats=(beat,),
              clocks=(), refusal_clock=refusal, climax_ready_k=1,
              climax_ready_beats=("beat:discover",),
              phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                            Phase.CLIMAX: 2, Phase.FALLING: 2})
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame="session:main")
    w.close()
    path.with_suffix(".meta.json").write_text(json.dumps(
        {"title": "Session Test World", "protagonist": PLAYER,
         "arc_scope": [PLAYER, "fact:secret", "person:rival"], "mode": "pure"}))


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    _author_scenario(tmp_path / "worlds" / "demo.world", "w:demo")
    return "demo"


class _RoutingProvider(StubProvider):
    """One provider serves BOTH the engine model calls (extraction,
    classification, resolution) and the host cohorts — as the real
    CodexProvider does — by routing on prompt shape instead of a flat
    queue."""

    def __init__(self):
        super().__init__([])

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if prompt.startswith("Classify the lifetime"):
            return {"durability": "STATE", "confidence": 0.9}
        if prompt.startswith("Extract world-state"):
            return {"items": []}
        if prompt.startswith("Resolve an unestablished aspect"):
            return {"items": [{"value": "A lamplit study, certain at its edges."}]}
        if prompt.startswith("Classify this player input"):
            return {"kind": "action", "moves_to": "", "requires": []}
        if prompt.startswith("You are a story navigator"):
            return {"thread": "", "directive": ""}
        if prompt.startswith("You are the narrator"):
            return {"prose": "The study holds around you, lamplit and certain."}
        raise AssertionError(f"unrouted prompt: {prompt[:60]!r}")


def _provider():
    return _RoutingProvider()


class TestSession:
    def test_open_turn_close(self, scenario):
        s = Session.open(scenario, player_id="u1", provider=_provider())
        assert s.protagonist == PLAYER
        assert "Session Test World" in s.opening()
        reply = s.turn("I look around the study.")
        assert reply.ok and "lamplit" in reply.prose
        s.close()

    def test_per_player_slots_dont_collide(self, scenario):
        Session.open(scenario, player_id="alice", provider=_provider()).close()
        Session.open(scenario, player_id="bob", provider=_provider()).close()
        assert slot_path(scenario, "alice").exists()
        assert slot_path(scenario, "bob").exists()
        assert slot_path(scenario, "alice") != slot_path(scenario, "bob")

    def test_default_slot_is_unkeyed(self, scenario):
        # The solo CLI (no player_id) keeps the original slot name.
        Session.open(scenario, provider=_provider()).close()
        assert slot_path(scenario).name == "demo.play.world"

    def test_resume_persists_across_sessions(self, scenario):
        s1 = Session.open(scenario, player_id="u1", provider=_provider())
        s1.turn("I look around.")
        s1.close()
        # A second open resumes the SAME slot at its head (turn count grew).
        from construct.game import next_turn_number, open_playthrough
        w, _arc, _meta = open_playthrough(scenario, _provider(), player_id="u1")
        assert next_turn_number(w) >= 2  # turn_0 + the played turn
        w.close()

    def test_turn_failure_is_survivable(self, scenario):
        s = Session.open(scenario, player_id="u1", provider=StubProvider([]))
        reply = s.turn("I do something")   # provider queue empty → turn raises inside
        assert reply.ok is False and "could not complete" in reply.prose
        s.close()  # session still usable/closeable


class TestDiscordRouting:
    def test_help_and_scenarios_are_commands(self, scenario):
        pipe = _Pipe(scenario)
        assert "play by DM" in _handle_command(pipe, 1, "!help")
        assert "demo" in _handle_command(pipe, 1, "!scenarios")
        pipe.close_all()

    def test_non_command_returns_none(self):
        pipe = _Pipe("demo")
        assert _handle_command(pipe, 1, "I open the door") is None
        pipe.close_all()

    def test_unknown_command(self):
        pipe = _Pipe("demo")
        assert "Unknown command" in _handle_command(pipe, 1, "!frobnicate")
        pipe.close_all()

    def test_play_unknown_scenario(self, scenario):
        pipe = _Pipe(scenario)
        assert "No scenario" in _handle_command(pipe, 1, "!play nope")
        pipe.close_all()
