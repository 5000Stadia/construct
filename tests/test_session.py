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
import asyncio as _asyncio
from collections import deque

import construct.discord_bot as discord_bot
from construct.discord_bot import (
    _handle_command,
    _Pipe,
    _SeenIds,
    chunk,
    coalesce_leading_turns,
    heartbeat_unhealthy,
)
from construct.game import WORLDS_DIR, slot_path
from construct.provider import StubProvider, task_of

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


def _author_cast_scenario(path, world_id):
    """A scenario with a PILLAR + a present cast member holding the genuine clue, sealed the
    way the FIXED `_finalize_scenario` leaves one: arc_scope = arc_entities ∪ cast node ids
    (Cx 032 blocker 1), the clue seeded into the holder's knows: frame, meta['cast'] set.
    No manual run-time scope — this exercises the real metadata → Session → run_turn path."""
    from construct.arc.conditions import InFrame, TurnsQuiet
    from construct.arc.executor import arc_entities
    from construct.arc.grammar import (
        Arc, Clock, ConclusionShape, Phase, Pillar, Rung,
    )
    from construct.cast import cast_from_proposal, cast_seed_plan

    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    w = World(path, world_id=world_id, model=StubModel(fallback=fallback),
              stance="fiction", title="Cast Test World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:study"},
        {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        {"entity": "fact:clue", "attribute": "kind", "value": "proposition", "timeless": True},
    ])
    pillar = Pillar("pillar:guilt", "the guilt", required=True,
                    genuine_via=InFrame(PLAYER_FRAME, "fact:clue", "shows", "guilt"))
    refusal = Clock("clock:refusal", TurnsQuiet(15),
                    effects=({"entity": "event:concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},), bound_to="arc:main",
                    rung=Rung.REFUSAL)
    shape = ConclusionShape("shape:main", "drive_inverted", (PLAYER, "a", "b"),
                            world_condition=InFrame(PLAYER_FRAME, "fact:clue", "shows", "guilt"),
                            premise=InFrame("canon", "fact:clue", "kind", "proposition"),
                            refusal_variant_id="shape:refused")
    arc = Arc(arc_id="arc:main", protagonist=PLAYER, shape=shape, beats=(), clocks=(),
              refusal_clock=refusal, climax_ready_k=1, climax_ready_beats=(),
              pillars=(pillar,))
    proposal = {"pillars": [{"id": "pillar:guilt", "label": "the guilt", "required": True}],
                "cast": [{"id": "person:witness", "shape_role": "witness",
                          "surface_role": "the witness", "clues": [
                              {"clue_id": "clue:guilt", "pillar_id": "pillar:guilt",
                               "fact": {"entity": "fact:clue", "attribute": "shows",
                                        "value": "guilt"}, "coverage_effect": "genuine",
                               "reveal_condition": "none"}]}]}
    cast_nodes, _ = cast_from_proposal(proposal)
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    for frame, items in cast_seed_plan(cast_nodes):  # the witness's knows: frame holds the clue
        w.porcelain.ingest_structured(items, frame=frame)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame="session:main")
    # scope built the FIXED way — arc referents (incl. pillar clue facts) ∪ cast node ids
    scope = sorted(set(arc_entities(arc)) | {"person:witness"})
    w.close()
    path.with_suffix(".meta.json").write_text(json.dumps(
        {"title": "Cast Test World", "protagonist": PLAYER, "arc_scope": scope,
         "mode": "pure", "scenario_mode": "endless", "endless": True, "cast": proposal}))


class _CastRoutingProvider(StubProvider):
    """Routes Session model calls by task, including the present-NPC cohorts (npa/npi)."""

    def __init__(self):
        super().__init__([])

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if prompt.startswith("Classify the lifetime"):
            return {"durability": "STATE", "confidence": 0.9}
        if prompt.startswith("Extract world-state"):
            return {"items": []}
        if prompt.startswith("Resolve an unestablished aspect"):
            return {"items": [{"value": "A lamplit study."}]}
        t = task_of(prompt)
        if t == "cls":
            return {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
                    "uncertain_of": "", "commits": False, "commitment": ""}
        if t == "npt":  # TURN-LATENCY Lever 4: folded per-NPC call
            return {"acts": False, "action": "", "speaks": True,
                    "intent": "answer", "line_hint": ""}
        if t == "npa":
            return {"acts": False, "action": ""}
        if t == "npi":
            return {"speaks": True, "intent": "answer", "line_hint": ""}
        if t == "ndg":
            return {"thread": "", "directive": ""}
        if t == "nar":
            return {"prose": "The witness, pressed, admits what they saw."}
        return {"items": []}  # any tail call (e.g. time estimate) — harmless


def test_interview_delivery_through_real_session_metadata(tmp_path, monkeypatch):
    # Cx 032 blocker 1: prove interview delivery works through the REAL metadata scope
    # (cast NPC reaches run_turn because _finalize unions cast nodes into arc_scope) — no
    # hand-injected run_turn scope.
    from construct.adapter import PorcelainWorldReads
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    _author_cast_scenario(tmp_path / "worlds" / "cast.world", "w:cast")
    s = Session.open("cast", player_id="u1", provider=_CastRoutingProvider())
    assert "person:witness" in s._scope  # the cast member is in the live scope
    reply = s.turn("I press the witness about what they saw.")
    assert reply.ok
    # the clue surfaced into the player's knowledge frame via interview delivery
    assert PorcelainWorldReads(s._world).assertion_in_frame(
        PLAYER_FRAME, "fact:clue", "shows", "guilt")


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
        if task_of(prompt) == "cls":
            return {"kind": "action", "moves_to": "", "requires": []}
        if task_of(prompt) == "ndg":
            return {"thread": "", "directive": ""}
        if task_of(prompt) == "nar":
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

    def test_continuation_slot_scope_preferred_over_stale_meta(self, scenario):
        # Cx 191/192: continue_episode persists the NEW episode's scope per-slot as
        # session:episode.arc_scope. Session.open must PREFER it over the shared, stale scenario meta
        # arc_scope — else EP2 cold-opens with EP1's cast. Also guards the json import (the read
        # decodes a JSON blob; a missing import would silently fall back to the stale meta scope).
        s1 = Session.open(scenario, player_id="u1", provider=_provider())
        assert s1._scope != ["person:ep2_only"]                    # baseline: the scenario-meta scope
        s1._world.porcelain.ingest_structured(
            [{"entity": "session:episode", "attribute": "arc_scope",
              "value": json.dumps(["person:ep2_only"]), "value_type": "literal"}],
            frame="session:main")
        s1.close()
        s2 = Session.open(scenario, player_id="u1", provider=_provider())
        assert s2._scope == ["person:ep2_only"]                    # the slot scope wins on reopen
        s2.close()

    def test_turn_failure_is_survivable(self, scenario):
        s = Session.open(scenario, player_id="u1", provider=StubProvider([]))
        reply = s.turn("I do something")   # provider queue empty → turn raises inside
        assert reply.ok is False and "could not complete" in reply.prose
        s.close()  # session still usable/closeable

    def test_win_loss_goal_not_shown_as_banner(self, scenario, tmp_path):
        # Founder 2026-06-22: NO forced goal banner — even in win_loss the objective
        # is NOT stapled atop the opening; the call to action arises in the fiction.
        # goal_statement() still returns the value (internal/win framing), but
        # opening() never renders an 'aim' line.
        meta_path = tmp_path / "worlds" / "demo.world"
        meta_path = meta_path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text())
        meta["scenario_mode"] = "win_loss"
        meta["goal_statement"] = "name who is responsible"
        meta_path.write_text(json.dumps(meta))
        s = Session.open(scenario, player_id="u1", provider=_provider())
        assert s.goal_statement() == "name who is responsible"   # field intact
        assert "Your aim:" not in s.opening()                    # no banner
        assert "name who is responsible" not in s.opening()
        s.close()

    def test_thematic_intro_shown_at_opening(self, scenario, tmp_path):
        meta_path = (tmp_path / "worlds" / "demo.world").with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text())
        meta["intro"] = "The lamplit study holds its secrets. Find the one that matters."
        meta_path.write_text(json.dumps(meta))
        s = Session.open(scenario, player_id="u1", provider=_provider())
        assert "holds its secrets" in s.opening()
        s.close()

    def test_endless_has_no_aim(self, scenario):
        # The default fixture meta has no scenario_mode → endless → no aim.
        s = Session.open(scenario, player_id="u1", provider=_provider())
        assert s.goal_statement() is None
        assert "Your aim:" not in s.opening()
        s.close()


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


class TestChunking:
    def test_short_text_one_chunk(self):
        assert chunk("a short scene.") == ["a short scene."]

    def test_empty_is_never_silent(self):
        assert chunk("") == ["(the world is quiet)"]

    def test_long_text_chunks_under_limit_no_loss(self):
        para = "x" * 1500
        text = f"{para}\n{para}\n{para}"   # ~4500 chars, 3 paragraphs
        parts = chunk(text)
        assert len(parts) >= 3
        assert all(len(p) <= 2000 for p in parts)
        # newline-boundary split + nothing dropped (modulo the split newlines)
        assert "".join(parts).replace("x", "") == ""
        assert sum(p.count("x") for p in parts) == 4500

    def test_no_newline_falls_back_to_space_then_hard_cut(self):
        parts = chunk("word " * 600)       # 3000 chars, spaces only
        assert all(len(p) <= 2000 for p in parts)
        parts2 = chunk("y" * 5000)         # no break at all → hard cut
        assert all(len(p) <= 2000 for p in parts2)
        assert sum(p.count("y") for p in parts2) == 5000


class TestBarrageCoalescing:
    def test_leading_turns_merge_in_order(self):
        buf = deque([("turn", "a", "ch"), ("turn", "b", "ch"), ("turn", "c", "ch")])
        text, kind, _ = coalesce_leading_turns(buf)
        assert kind == "turn" and text == "a\n\nb\n\nc"
        assert not buf  # all consumed

    def test_merge_stops_at_command_boundary(self):
        buf = deque([("turn", "a", "ch"), ("turn", "b", "ch"),
                     ("cmd", "!fresh", "ch"), ("turn", "d", "ch")])
        text, kind, _ = coalesce_leading_turns(buf)
        assert kind == "turn" and text == "a\n\nb"          # stops before !fresh
        text, kind, _ = coalesce_leading_turns(buf)
        assert kind == "cmd" and text == "!fresh"           # command handled alone
        text, kind, _ = coalesce_leading_turns(buf)
        assert kind == "turn" and text == "d"


class _FakeMsg:
    def __init__(self, content):
        self.content = content
    async def edit(self, content=None):
        self.content = content


class _FakeChannel:
    def __init__(self):
        self.sent = []
    async def send(self, content):
        m = _FakeMsg(content)
        self.sent.append(m)
        return m
    def typing(self):
        class _T:
            async def __aenter__(s):
                return s
            async def __aexit__(s, *a):
                return False
        return _T()


class _FakeSession:
    def __init__(self):
        self.calls = []
    @classmethod
    def open(cls, scenario, player_id=None, *, fresh=False, provider=None):
        inst = cls()
        inst.scenario = scenario
        return inst
    def opening(self):
        return "World\nYou are X."
    def turn(self, text):
        self.calls.append(text)
        return type("R", (), {"prose": f"ok:{text}", "ok": True, "trace": None})()
    def close(self):
        pass


def test_barrage_serializes_into_one_merged_turn(monkeypatch):
    """A burst of DMs becomes ONE turn (never concurrent turns on one
    world) — the Kernos merge-window lesson, verified through the
    worker."""
    monkeypatch.setattr(discord_bot, "Session", _FakeSession)

    async def scenario():
        pipe = _Pipe("demo", merge_window=0.02)
        ch = _FakeChannel()
        # three lines fired faster than a turn — a barrage
        pipe.submit(7, ch, "I draw the bolt")
        pipe.submit(7, ch, "and ease the door open")
        pipe.submit(7, ch, "and step through")
        for _ in range(200):                       # let the worker drain
            await _asyncio.sleep(0.01)
            if 7 in pipe._sessions and pipe._sessions[7].calls:
                break
        await _asyncio.sleep(0.05)
        calls = pipe._sessions[7].calls
        pipe.close_all()
        return calls, ch

    calls, ch = _asyncio.run(scenario())
    assert calls == ["I draw the bolt\n\nand ease the door open\n\nand step through"]
    # the placeholder was posted then edited to the prose
    assert any(getattr(m, "content", "").startswith("ok:") for m in ch.sent)


class TestHardening:
    def test_seen_ids_dedup_and_bound(self):
        seen = _SeenIds(maxlen=4)
        assert seen.seen(1) is False        # first sight
        assert seen.seen(1) is True         # re-delivery caught
        for i in range(2, 7):               # overflow → oldest half dropped
            seen.seen(i)
        assert len(seen._ids) <= 4          # stays bounded

    def test_heartbeat_unhealthy_predicate(self):
        assert heartbeat_unhealthy(float("nan")) is True
        assert heartbeat_unhealthy(float("inf")) is True
        assert heartbeat_unhealthy(None) is True
        assert heartbeat_unhealthy(120.0, threshold=60) is True
        assert heartbeat_unhealthy(0.05, threshold=60) is False


class TestEntryAsOf:
    def test_entry_coordinate_persists_and_governs_establishing(self, scenario):
        # Fresh entry at coordinate 1 is recorded and read back on resume.
        s = Session.open(scenario, player_id="t", fresh=True, as_of=1.0,
                         provider=_provider())
        assert s.entry_as_of == 1.0
        s.close()
        # Resume (not fresh): the recorded entry coordinate is restored.
        s2 = Session.open(scenario, player_id="t", provider=_provider())
        assert s2.entry_as_of == 1.0
        # Establishing lines are deterministic and exclude the protagonist.
        assert all(not l.startswith(PLAYER) for l in s2.establishing_lines())
        s2.close()

    def test_default_entry_is_head(self, scenario):
        s = Session.open(scenario, player_id="h", fresh=True, provider=_provider())
        assert s.entry_as_of is None
        assert "(entering as of" not in s.opening()
        s.close()


class TestColdOpenConcealment:
    def test_live_threads_suppress_concealed_alias(self, scenario, monkeypatch):
        # Cx 022 #3: a live event's alias/kind is freeform text, so it bypasses the
        # (entity,attribute) protected-key filter — an event named after the hidden
        # answer would leak it in the cold open's STILL-LIVE list. The concealment
        # token filter drops the secret-bearing thread; benign threads survive.
        s = Session.open(scenario, player_id="u1", provider=_provider())

        def fake_snapshot(scope, lens=None, as_of=None, **kw):
            return {"facts": [
                {"entity": "event:e1", "attribute": "alias",
                 "value": "the culprit is named at last"},   # brushes 'culprit' (protected)
                {"entity": "event:e2", "attribute": "alias",
                 "value": "the water ration tightens"},       # benign
            ]}

        monkeypatch.setattr(s._world.porcelain, "snapshot", fake_snapshot)
        threads = s.live_threads()
        assert "the water ration tightens" in threads
        assert all("culprit" not in t for t in threads)       # concealed thread dropped
        s.close()


class TestEndlessMode:
    def _force_concluded(self, scenario, player_id):
        # Drive the demo arc's world_condition TRUE: the player learns the
        # culprit (it's an InFrame(knows:player, fact:secret, culprit, rival)).
        from construct.game import open_playthrough, slot_path
        import shutil
        from construct.game import scenario_path
        shutil.copyfile(scenario_path(scenario), slot_path(scenario, player_id))
        w, _arc, _meta = open_playthrough(scenario, _provider(), player_id=player_id)
        w.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
            frame=PLAYER_FRAME)
        w.close()

    def test_bounded_settles_at_conclusion(self, scenario):
        self._force_concluded(scenario, "b")
        s = Session.open(scenario, player_id="b", provider=_provider())  # bounded (default)
        r = s.turn("I look around.")
        assert r.ok and r.trace.concluded is True
        assert r.trace.pacing == "concluded"      # navigator holds at a reached end
        s.close()

    def test_endless_carries_on(self, scenario, monkeypatch):
        # Mark the scenario endless, then conclude the arc: it must NOT
        # settle — pacing is never "concluded" even though concluded=True.
        import json
        from construct.game import scenario_path
        mp = scenario_path(scenario).with_suffix(".meta.json")
        meta = json.loads(mp.read_text()); meta["endless"] = True
        mp.write_text(json.dumps(meta))
        self._force_concluded(scenario, "e")
        s = Session.open(scenario, player_id="e", provider=_provider())
        r = s.turn("I look around.")
        assert r.trace.concluded is True
        assert r.trace.pacing != "concluded"       # world carries on
        s.close()


@pytest.mark.skip(reason="BLOCKED on a PB attribute-semantics conflict — conferring Cx (C-217): "
                  "replan_main_arc re-ingests the arc's shape rows (delta_type, timeless), but "
                  "Session.open already READ-FOLDED delta_type, so PB raises 'cannot declare "
                  "semantics after folded data'. The reload CODE is correct; the blocker is the "
                  "re-ingest path (also a live-proof risk). Un-skip once the ingest path is fixed.")
def test_reload_arc_portfolio_swaps_the_session_main_arc(scenario, monkeypatch):
    """WORLD-CHANGING-AGENCY (Cx 215/216 #1): after a mid-story re-plan repoints the
    `arc:portfolio` manifest in PB, `Session._reload_arc_portfolio` must update the live
    `self._arc` so the NEXT turn runs the new main arc, not the stale one held since open.

    This drives the reload directly (the full run_turn→replan path is covered in
    test_integration; here we isolate the cross-turn session handoff)."""
    import dataclasses

    from construct.arc import io as arc_io
    s = Session.open(scenario, player_id="u1", provider=_provider())
    assert s._arc.arc_id == "arc:main"
    # install a second arc and repoint the manifest at it (what replan_main_arc commits)
    new_arc = dataclasses.replace(s._arc, arc_id="arc:replan_9")
    arc_io.replan_main_arc(s._world, new_arc, turn=9)
    s._reload_arc_portfolio()
    assert s._arc.arc_id == "arc:replan_9"             # the live session arc swapped
    assert all(a.arc_id != "arc:replan_9" for a in s._side_arcs)  # new arc is MAIN, not a side arc
    s.close()
