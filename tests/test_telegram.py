"""Telegram transport + registry + loopback self-test + setup wizard.

Covers the Codex spec-review acceptance list: atomic single-use invites,
expiry boundary, platform lock, existing-player idempotence, the zero-model
invite gate, scenario scope, chunking boundaries, exactly-once delivery
across redelivery, secrets discipline (0600 + redaction), and the full
offline loopback flow — all with a fake Session and no network.
"""

import json
import os
import stat
from types import SimpleNamespace

import pytest

from construct import loopback, registry, setup, telegram_bot
from construct.provider import StubProvider
from construct.transport_core import (
    BUILD_HEADS_UP, GREETING, STATIC_REJECT, InboundEvent, TransportCore,
    _humanize_stage, _interpret_mode, chunk)


def _aturn(reply, *actions):
    """An ARCHITECT_SCHEMA-shaped cohort turn for the stub provider."""
    return {"reply": reply, "actions": list(actions)}


def _aact(tool, detail="", mode=""):
    return {"tool": tool, "detail": detail, "mode": mode}

NOW = 1_000_000.0


# ---- fakes ---------------------------------------------------------------

class _FakeSession:
    def __init__(self, scenario, player_id, fresh, mode_override=None, setup=None):
        self.scenario, self.player_id, self.fresh = scenario, player_id, fresh
        self.mode_override = mode_override
        self._setup = setup        # None → transport skips the Foyer
        self.applied = None        # the character sheet apply_character received
        self.turns = []

    def opening(self):
        return f"OPENING:{self.scenario}:{self.player_id}"

    def status_line(self):
        return "Day 1, night | the office"

    def character_setup(self):
        return self._setup

    def apply_character(self, sheet):
        self.applied = sheet

    def note_wish(self, text):
        self.wishes = getattr(self, "wishes", []) + [text]

    def concealed_truths(self):
        return "REVEAL twist: the rival is secretly the brother"

    def turn(self, text):
        self.turns.append(text)
        # "new story" → the player asked (OOC) to leave; the real run_turn sets this
        # from the classifier's `exit` kind.
        return SimpleNamespace(prose=f"narrated<{text}>", ok=True, ended=False,
                               exit_requested="new story" in text.lower())


class _Factory:
    def __init__(self, setup=None):
        self.calls = []
        self.sessions = {}
        self.setup = setup          # character_setup() the fake sessions return

    def __call__(self, *, scenario, player_id, fresh, mode_override=None):
        s = _FakeSession(scenario, player_id, fresh, mode_override, setup=self.setup)
        self.calls.append((scenario, player_id, fresh, mode_override))
        self.sessions[player_id] = s
        return s


def _fturn(reply, *actions):
    return {"reply": reply, "actions": list(actions)}


def _fact(tool, field="", value=""):
    return {"tool": tool, "field": field, "value": value}


@pytest.fixture
def conn(tmp_path):
    return registry.connect(tmp_path / "reg.sqlite")


def _log_dir_for(conn):
    """Keep transcripts beside the (tmp) registry, never in the repo's worlds/."""
    row = conn.execute("PRAGMA database_list").fetchone()
    from pathlib import Path
    return Path(row["file"]).parent / "transcripts"


def _core(conn, factory, platform="telegram", limit=4096, **kw):
    return TransportCore(conn, platform=platform, msg_limit=limit,
                         session_factory=factory, log_dir=_log_dir_for(conn), **kw)


def _ev(platform, ext, text, uid=1):
    return InboundEvent(platform=platform, external_id=ext, chat_id=ext, text=text,
                        update_ids=(uid,))


# ---- registry: invites ---------------------------------------------------

class TestRegistry:
    def test_claim_success_then_idempotent(self, conn):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        pid = registry.claim_invite(conn, code, "telegram", "42", now=NOW)
        assert pid == "telegram:42"
        # a second message from the same player needs no code and burns nothing
        assert registry.player_for(conn, "telegram", "42") == "telegram:42"
        another = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        # already-mapped identity claiming again is idempotent, doesn't consume
        assert registry.claim_invite(conn, another, "telegram", "42", now=NOW) == "telegram:42"
        row = conn.execute("SELECT status FROM invites WHERE code=?", (another,)).fetchone()
        assert row["status"] == "open"  # not burned

    def test_single_use_second_claimer_loses(self, conn):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        assert registry.claim_invite(conn, code, "telegram", "1", now=NOW) == "telegram:1"
        assert registry.claim_invite(conn, code, "telegram", "2", now=NOW) is None

    def test_wrong_platform_rejected(self, conn):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        assert registry.claim_invite(conn, code, "loopback", "1", now=NOW) is None

    def test_expiry_boundary(self, conn):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW, ttl_seconds=100)
        assert registry.claim_invite(conn, code, "telegram", "1", now=NOW + 100) is None  # >= expiry
        assert registry.claim_invite(conn, code, "telegram", "2", now=NOW + 99) == "telegram:2"

    def test_unknown_code_rejected(self, conn):
        assert registry.claim_invite(conn, "CONS-NOPE", "telegram", "1", now=NOW) is None

    def test_codes_are_long_and_unique(self, conn):
        codes = {registry.mint_invite(conn, "telegram", "anchor", now=NOW) for _ in range(50)}
        assert len(codes) == 50
        assert all(len(c) > 12 for c in codes)


# ---- core: the invite gate (zero model/session for unknown senders) ------

class TestGate:
    def test_unknown_sender_static_reject_no_session(self, conn):
        f = _Factory()
        core = _core(conn, f)
        for text in ["/help", "/play", "/scenarios", "I open the door"]:
            out = core.handle(_ev("telegram", "99", text), now=NOW)
            assert out.chunks == [STATIC_REJECT]
        assert f.calls == []  # the gate never allocated a session

    def test_code_claims_then_admits(self, conn):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "7", f"here is my code {code}"), now=NOW)
        # The Construct greets (opens the Atrium dialogue); not the reject; no
        # session opened yet; an empty creation blob is seeded for the next message.
        assert out.chunks[0].startswith(GREETING) and out.chunks[0] != STATIC_REJECT
        assert f.calls == []  # claiming opens no session yet
        assert registry.get_creation(conn, "telegram", "7") == {"history": [], "state": {}}


# ---- core: routing + scenario scope --------------------------------------

class TestRouting:
    def _admit(self, conn, ext="5", scenario="anchor", started=True):
        """Claim an invite. `started=True` (default) marks the player as a RETURNING
        player so plain prose auto-resumes and runs a turn; started=False is a
        brand-new player who has been ASKED the mode question (mirroring the gate)
        and whose next message is the answer + cold open."""
        code = registry.mint_invite(conn, "telegram", scenario, now=NOW)
        registry.claim_invite(conn, code, "telegram", ext, now=NOW)
        if started:
            registry.mark_started(conn, "telegram", ext)
        else:
            # The gate seeds an empty creation blob when it greets a new player
            # into the Atrium (Construct dialogue).
            registry.set_creation(conn, "telegram", ext, {"history": [], "state": {}})

    def test_play_is_fresh_resume_is_not_and_locked_to_scenario(self, conn):
        self._admit(conn, scenario="anchor")
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "5", "/play other_scenario"), now=NOW)
        assert out.chunks == ["OPENING:anchor:telegram:5"]   # arg ignored; scope locked
        assert f.calls[-1] == ("anchor", "telegram:5", True, None)  # fresh; no mode chosen
        core.handle(_ev("telegram", "5", "/resume"), now=NOW)
        assert f.calls[-1] == ("anchor", "telegram:5", False, None)

    def test_prose_auto_resumes_and_runs_turn(self, conn):
        self._admit(conn, ext="6")
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "6", "I look around"), now=NOW)
        assert "narrated<I look around>" in out.chunks[0]  # header may prepend
        assert f.sessions["telegram:6"].turns == ["I look around"]

    def test_gate_greeting_is_a_simple_welcome(self, conn):
        # First contact is a SIMPLE welcome (founder) — NOT a wall of options;
        # the Construct cohort showcases the library only when asked.
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "g1", f"claim {code}"), now=NOW)
        assert out.chunks[0] == GREETING
        assert "Construct Projector" in out.chunks[0]
        assert "anchor" not in out.chunks[0]   # no world list dumped up front

    def test_classify_genre_cohort_shape(self):
        from construct import cohorts
        p = StubProvider([{"genre": "noir mystery"}])
        assert cohorts.classify_genre(p, "The Mary Rel Manifest",
                                      "a falsified manifest the night a ship went down") == "noir mystery"

    def test_library_presents_titles_not_raw_ids(self, conn):
        # The library the Construct sees maps raw ids → campaign titles, and a
        # world with no real title (an incomplete artifact) is excluded.
        f = _Factory()
        core = _core(conn, f)
        catalog = core._catalog()
        assert catalog.get("anchor", "").startswith("The Last Honest Meter")
        assert "anchor2" not in catalog        # retired (no meta/title)

    def test_atrium_show_library_renders_host_menu(self, conn):
        # The Construct emits show_library; the HOST renders a clean menu block
        # (one world per line + a genre emoji), so the agent's prose stays short.
        self._admit(conn, ext="lib", started=False)
        f = _Factory()
        provider = StubProvider([_aturn("Here's what's ready —", _aact("show_library"))])
        core = _core(conn, f, provider=provider)
        out = core.handle(_ev("telegram", "lib", "what can I play?"), now=NOW)
        body = out.chunks[0]
        assert body.startswith("Here's what's ready")          # short agent intro
        assert "ready-made worlds" in body.lower()             # host menu header
        assert "The Last Honest Meter" in body                 # a real title, listed
        assert "new world" in body                             # the build option line
        assert f.calls == []                                   # still in dialogue

    def test_atrium_continue_then_pick_existing_world(self, conn):
        # A not-started player converses with the Construct; on pick_world the
        # granted world opens fresh and the cold open follows the spoken line.
        self._admit(conn, ext="new", started=False)
        f = _Factory()
        provider = StubProvider([
            _aturn("I can make almost anything. Or open a ready-made.", _aact("chat")),
            _aturn("Opening the anchor world.", _aact("pick_world", "anchor"))])
        core = _core(conn, f, provider=provider)
        out = core.handle(_ev("telegram", "new", "what can you do?"), now=NOW)
        assert out.chunks[0].startswith("I can make")     # still in dialogue
        assert f.calls == []                               # no world opened yet
        out2 = core.handle(_ev("telegram", "new", "open the anchor one"), now=NOW)
        assert "Opening the anchor world." in out2.chunks[0]
        assert "OPENING:anchor:telegram:new" in out2.chunks[0]   # cold open follows
        assert f.calls[-1] == ("anchor", "telegram:new", True, None)
        assert registry.is_started(conn, "telegram", "new")
        assert registry.get_creation(conn, "telegram", "new") is None  # Atrium cleared
        out3 = core.handle(_ev("telegram", "new", "I read the ledger"), now=NOW)
        assert "narrated<I read the ledger>" in out3.chunks[0]   # now it plays (header may prepend)

    def test_fresh_entry_enters_the_foyer(self, conn):
        # A fresh entry whose session can describe its protagonist hands off to the
        # Foyer (character creation) instead of jumping to the cold open.
        self._admit(conn, ext="fy", started=False)
        setup = {"role": "a knight", "defaults": {},
                 "anchors": ["a rival (person)"], "protagonist": "person:knight"}
        f = _Factory(setup=setup)
        core = _core(conn, f, provider=StubProvider([
            _fturn("Well met, knight — who are you?", _fact("chat"))]))
        out = core._enter_world("telegram:fy", _ev("telegram", "fy", "x"),
                                scenario="anchor", mode=None, preamble="Loading.")
        assert "who are you" in out.chunks[0].lower()                 # the Foyer intro
        assert registry.get_chargen(conn, "telegram", "fy") is not None
        assert not registry.is_started(conn, "telegram", "fy")        # not playing yet

    def test_foyer_done_ingests_character_then_opens(self, conn):
        # In the Foyer: a turn that's not done persists the sheet; `done` ingests
        # the character as canon and opens the story.
        self._admit(conn, ext="fz", started=False)
        setup = {"role": "a clerk", "defaults": {}, "anchors": [],
                 "protagonist": "person:clerk"}
        f = _Factory(setup=setup)
        sess = _FakeSession("anchor", "telegram:fz", False, setup=setup)
        core = _core(conn, f, provider=StubProvider([
            _fturn("Mara — noted.", _fact("set_detail", "name", "Mara")),
            # The done turn also settles pronouns — the host gates done until the
            # required fields (name + pronouns) are present.
            _fturn("Then let's begin.", _fact("set_detail", "pronouns", "she/her"),
                   _fact("done"))]))
        core._sessions["telegram:fz"] = sess
        registry.set_chargen(conn, "telegram", "fz",
                             {"history": [], "sheet": {}, "setup": setup})
        out1 = core.handle(_ev("telegram", "fz", "call me Mara"), now=NOW)
        assert out1.chunks[0] == "Mara — noted."
        assert not registry.is_started(conn, "telegram", "fz")        # still in Foyer
        out2 = core.handle(_ev("telegram", "fz", "ready"), now=NOW)
        assert sess.applied is not None                               # ingested as canon
        assert sess.applied.details.get("name") == "Mara"
        assert "OPENING:anchor:telegram:fz" in out2.chunks[0]
        assert registry.is_started(conn, "telegram", "fz")
        assert registry.get_chargen(conn, "telegram", "fz") is None   # Foyer cleared

    def test_atrium_resume_reopens_saved_game_not_fresh(self, conn, tmp_path):
        # A guest with a saved game can resume it from the dialogue (fresh=False).
        self._admit(conn, ext="rs", started=False)
        # Simulate an existing play slot for their granted scenario.
        from construct.game import slot_path
        slot = slot_path("anchor", "telegram:rs")
        slot.parent.mkdir(parents=True, exist_ok=True)
        slot.write_text("{}")
        try:
            f = _Factory()
            provider = StubProvider([
                _aturn("Welcome back — resuming your game.", _aact("resume"))])
            core = _core(conn, f, provider=provider)
            out = core.handle(_ev("telegram", "rs", "continue where I left off"), now=NOW)
            assert "OPENING:anchor:telegram:rs" in out.chunks[0]
            assert f.calls[-1] == ("anchor", "telegram:rs", False, None)  # fresh=False
            assert registry.is_started(conn, "telegram", "rs")
        finally:
            if slot.exists():
                slot.unlink()

    def test_atrium_build_streams_pings_and_enters_built_world(self, conn):
        # begin_build runs the (faked) generator, streams humanized progress via
        # notify, repoints the player at the new world, and enters it.
        self._admit(conn, ext="bld", started=False)
        f = _Factory()
        builds, pings = [], []

        def fake_builder(*, name, provider, seed, endless, win_direction,
                         play_as, on_stage, game_types=None):
            builds.append({"name": name, "seed": seed, "endless": endless,
                           "win_direction": win_direction, "play_as": play_as})
            on_stage("Stage 1 · Ingesting prose → pattern-buffer · extraction")
            on_stage("   …chunk 2/5 extracted")
            return {}

        provider = StubProvider([
            _aturn("A noir station, you're the AI.",
                   _aact("add_element", "a space-station noir"),
                   _aact("set_role", "the station's AI")),
            _aturn("I'll cook now.",
                   _aact("set_ending", "catch the saboteur", "win_loss"),
                   _aact("begin_build"))])
        core = _core(conn, f, provider=provider, builder=fake_builder,
                     notify=lambda chat_id, text: pings.append(text))
        core.handle(_ev("telegram", "bld", "noir station and I'm the AI"), now=NOW)
        out = core.handle(_ev("telegram", "bld", "that's it, go"), now=NOW)

        assert len(builds) == 1
        assert builds[0]["play_as"] == "the station's AI"
        assert builds[0]["endless"] is False              # win_loss → not endless
        assert builds[0]["win_direction"] == "catch the saboteur"
        assert "a space-station noir" in builds[0]["seed"]
        # streamed progress: heads-up + a humanized stage line + a chunk counter
        assert BUILD_HEADS_UP in pings
        assert any("Bringing the world into being" in p for p in pings)
        assert any("Populating the world (2/5)" in p for p in pings)
        # entered the freshly-built per-player world; player repointed + started
        built = f"live_telegram_bld"
        assert registry.scenario_for(conn, "telegram", "bld") == built
        assert f.calls[-1] == (built, "telegram:bld", True, "win_loss")
        assert f"OPENING:{built}:telegram:bld" in out.chunks[0]
        assert registry.is_started(conn, "telegram", "bld")
        assert registry.get_creation(conn, "telegram", "bld") is None

    def test_dump_writes_gitignored_transcript(self, conn, tmp_path):
        self._admit(conn, ext="d")
        f = _Factory()
        core = TransportCore(conn, platform="telegram", msg_limit=4096,
                             session_factory=f, log_dir=tmp_path / "transcripts")
        core.handle(_ev("telegram", "d", "I open the ledger"), now=NOW)
        out = core.handle(_ev("telegram", "d", "/dump"), now=NOW)
        assert "Transcript:" in out.chunks[0]
        log = (tmp_path / "transcripts" / "telegram_d.log")
        assert log.exists()
        body = log.read_text()
        assert "USER: I open the ledger" in body
        assert "narrated<I open the ledger>" in body

    def test_legacy_player_never_greeted_gets_greeting_first(self, conn):
        # A player who claimed BEFORE the Atrium existed has no creation blob and
        # is not started. Their first message must be GREETED (the dialogue
        # opened), not silently consumed — no model call needed for that step.
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        registry.claim_invite(conn, code, "telegram", "leg", now=NOW)  # no blob
        assert registry.get_creation(conn, "telegram", "leg") is None
        f = _Factory()
        core = _core(conn, f)  # no provider — greeting must not call the model
        out = core.handle(_ev("telegram", "leg", "hello?"), now=NOW)
        assert out.chunks[0].startswith(GREETING)    # greeted, not consumed
        assert f.calls == []
        assert registry.get_creation(conn, "telegram", "leg") == {"history": [], "state": {}}

    def test_returning_player_resumes_in_chosen_mode(self, conn):
        # A started player resumes their world in the mode stored at build time.
        self._admit(conn, ext="r", started=True)
        registry.set_mode(conn, "telegram", "r", "win_loss")
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "r", "I look around"), now=NOW)
        assert f.calls[-1] == ("anchor", "telegram:r", False, "win_loss")  # resume, same mode

    def test_feedback_writes_note_with_transcript_snippet(self, conn, tmp_path):
        self._admit(conn, ext="fb")
        f = _Factory()
        core = TransportCore(conn, platform="telegram", msg_limit=4096,
                             session_factory=f, log_dir=tmp_path / "transcripts",
                             feedback_dir=tmp_path / "inbox")
        core.handle(_ev("telegram", "fb", "I open the vault"), now=NOW)
        out = core.handle(
            _ev("telegram", "fb", "/feedback the opening ignored my name"), now=NOW)
        assert "flagged" in out.chunks[0].lower()
        notes = list((tmp_path / "inbox").glob("feedback-*.md"))
        assert len(notes) == 1
        body = notes[0].read_text()
        assert "the opening ignored my name" in body      # the note
        assert "I open the vault" in body                 # transcript snippet bundled

    def test_feedback_without_note_prompts(self, conn):
        self._admit(conn, ext="fb2")
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "fb2", "/feedback"), now=NOW)
        assert "/feedback" in out.chunks[0]  # asks for a note, writes nothing

    def test_status_pin_toggles_off_and_on(self, conn):
        self._admit(conn, ext="sp")  # started; pin defaults ON
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "sp", "/status pin"), now=NOW)
        assert "OFF" in out.chunks[0]
        assert registry.get_status_pin(conn, "telegram", "sp") is False
        out2 = core.handle(_ev("telegram", "sp", "/status pin"), now=NOW)
        assert "ON" in out2.chunks[0]
        assert registry.get_status_pin(conn, "telegram", "sp") is True

    def test_status_header_prepended_when_pin_on(self, conn):
        self._admit(conn, ext="sh")  # started; pin ON by default
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "sh", "I look around"), now=NOW)
        assert out.chunks[0].startswith("Day 1, night | the office")
        assert "narrated<I look around>" in out.chunks[0]

    def test_status_header_absent_when_pin_off(self, conn):
        self._admit(conn, ext="so")
        registry.set_status_pin(conn, "telegram", "so", False)
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "so", "I look around"), now=NOW)
        assert out.chunks == ["narrated<I look around>"]  # no header

    def test_status_header_only_appears_on_change(self, conn):
        # Founder: the time|location header is a CHANGE indicator (moved / time
        # progressed), not wallpaper on every turn. It rides atop a reply only when
        # the line DIFFERS from the last one shown.
        self._admit(conn, ext="sx")
        holder = {"line": "Day 1, night | the office"}

        class _S(_FakeSession):
            def status_line(self):
                return holder["line"]

        class _F(_Factory):
            def __call__(self, *, scenario, player_id, fresh, mode_override=None):
                s = _S(scenario, player_id, fresh, mode_override, setup=self.setup)
                self.calls.append((scenario, player_id, fresh, mode_override))
                self.sessions[player_id] = s
                return s

        core = _core(conn, _F())
        # turn 1: nothing shown yet → the header establishes the anchor
        o1 = core.handle(_ev("telegram", "sx", "look"), now=NOW)
        assert o1.chunks[0].startswith("Day 1, night | the office")
        # turn 2: same time + place → header suppressed, reply only
        o2 = core.handle(_ev("telegram", "sx", "wait"), now=NOW)
        assert o2.chunks[0] == "narrated<wait>"
        # time/place changes → the header reappears as the movement/progression cue
        holder["line"] = "Day 2, dawn | the vault"
        o3 = core.handle(_ev("telegram", "sx", "go to the vault"), now=NOW)
        assert o3.chunks[0].startswith("Day 2, dawn | the vault")

    def test_status_command_is_a_one_liner_no_turn(self, conn):
        self._admit(conn, ext="sc")  # started
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "sc", "/status"), now=NOW)
        assert out.chunks == ["Day 1, night | the office"]
        assert f.sessions["telegram:sc"].turns == []   # no turn / no time progression

    def test_exit_command_returns_to_start_menu(self, conn):
        self._admit(conn, ext="x1")  # started
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "x1", "/exit"), now=NOW)
        assert GREETING in out.chunks[0]
        assert not registry.is_started(conn, "telegram", "x1")  # back to the Atrium

    def test_ooc_new_story_intent_confirms_then_exits(self, conn):
        # An out-of-character "can we do a new story" → the engine confirms, and a
        # "yes" steps out to the start menu (no idle monitoring involved).
        self._admit(conn, ext="ns")  # started
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "ns", "actually, can we do a new story?"), now=NOW)
        assert "yes" in out.chunks[0].lower() and "start" in out.chunks[0].lower()
        assert registry.is_started(conn, "telegram", "ns")     # not gone yet — confirming
        out2 = core.handle(_ev("telegram", "ns", "yes"), now=NOW)
        assert GREETING in out2.chunks[0]
        assert not registry.is_started(conn, "telegram", "ns")  # stepped out

    def test_exit_confirm_decline_keeps_playing(self, conn):
        self._admit(conn, ext="nd")
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "nd", "can we do a new story"), now=NOW)
        out = core.handle(_ev("telegram", "nd", "no, keep going"), now=NOW)
        assert "staying" in out.chunks[0].lower()
        assert registry.is_started(conn, "telegram", "nd")     # still in the story

    def test_ooc_command_answers_as_engine_without_a_turn(self, conn):
        self._admit(conn, ext="oc")
        f = _Factory()

        class _P:  # stub provider for conduit_reply
            def __init__(self): self.calls = []
            async def complete(self, prompt, schema, *, tier="main", deliberate=False):
                self.calls.append(prompt)
                return {"reply": "You can step into a ready-made world or build one.",
                        "weave": "", "protected": False, "offer_new": False}
            def describe(self): return "stub"

        core = _core(conn, f, provider=_P())
        out = core.handle(_ev("telegram", "oc", "/ooc what can I play?"), now=NOW)
        assert "ready-made" in out.chunks[0]
        assert f.sessions == {}            # no session opened, no turn, no time

    def test_ooc_creative_suggestion_is_recorded_to_weave(self, conn):
        # A fitting suggestion the engine agrees to try is recorded as a wish for
        # the narrator to weave in (only while a session is open).
        self._admit(conn, ext="ws")
        f = _Factory()

        class _P:
            async def complete(self, prompt, schema, *, tier="main", deliberate=False):
                return {"reply": "I'll see what I can do.",
                        "weave": "hint the rival is secretly the protagonist's brother",
                        "protected": False, "offer_new": False}
            def describe(self): return "stub"

        core = _core(conn, f, provider=_P())
        sess = _FakeSession("anchor", "telegram:ws", False)
        core._sessions["telegram:ws"] = sess
        out = core.handle(_ev("telegram", "ws", "/ooc what if it was his brother?"), now=NOW)
        assert "see what i can do" in out.chunks[0].lower()
        assert getattr(sess, "wishes", []) == [
            "hint the rival is secretly the protagonist's brother"]

    def test_ooc_press_escalates_to_new_scenario_offer_then_exits(self, conn):
        # Pressing past a plot-protective deflection → the engine offers a NEW
        # scenario; "yes" routes through the exit-confirm to the start menu.
        self._admit(conn, ext="pr")

        class _P:
            def __init__(self): self.seen_pressed = []
            async def complete(self, prompt, schema, *, tier="main", deliberate=False):
                pressed = "PRESSED: YES" in prompt
                self.seen_pressed.append(pressed)
                if pressed:
                    return {"reply": "That can't be done without breaking this "
                            "story — shall I spin up a new scenario for it?",
                            "weave": "", "protected": True, "offer_new": True}
                return {"reply": "Trust me on this one.", "weave": "",
                        "protected": True, "offer_new": False}
            def describe(self): return "stub"

        prov = _P()
        core = _core(conn, f := _Factory(), provider=prov)
        core.handle(_ev("telegram", "pr", "/ooc make the killer the butler"), now=NOW)
        assert "telegram:pr" in core._ooc_pressed                 # armed after first deflect
        out2 = core.handle(_ev("telegram", "pr", "/ooc no really, do it"), now=NOW)
        assert prov.seen_pressed[-1] is True             # escalated
        assert "new scenario" in out2.chunks[0].lower()
        assert "telegram:pr" in core._pending_exit                # a "yes" will exit
        out3 = core.handle(_ev("telegram", "pr", "yes"), now=NOW)
        assert GREETING in out3.chunks[0]
        assert not registry.is_started(conn, "telegram", "pr")

    def test_wipe_resets_but_keeps_the_claim(self, conn):
        # /wipe wipes data + saves and resets to the fresh greeting, but does NOT
        # kick the player out (founder): the claim stays, no new code needed, and
        # the bot never self-issues a code.
        self._admit(conn, ext="wp")  # claimed + started
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "wp", "/wipe"), now=NOW)
        assert "CONS-" not in out.chunks[0]                   # NO self-issued code
        assert registry.player_for(conn, "telegram", "wp") == "telegram:wp"  # still claimed
        assert not registry.is_started(conn, "telegram", "wp")  # reset to fresh
        # Still connected → the very next message lands on the greeting, no code.
        out2 = core.handle(_ev("telegram", "wp", "hi"), now=NOW)
        assert out2.chunks[0].startswith(GREETING)

    def test_disconnect_kicks_out_and_needs_a_cli_code(self, conn):
        # /disconnect is the full kick-out (un-claim) for testing the claim flow;
        # the bot points to the local CLI and never issues a code itself.
        self._admit(conn, ext="dc")
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "dc", "/disconnect"), now=NOW)
        assert "CONS-" not in out.chunks[0]                   # NO self-issued code
        assert "construct invite" in out.chunks[0]            # points to the CLI
        assert registry.player_for(conn, "telegram", "dc") is None   # un-claimed
        # An operator-minted code re-admits them as a brand-new user.
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        out2 = core.handle(_ev("telegram", "dc", code), now=NOW)
        assert out2.chunks[0].startswith(GREETING)

    def test_two_players_get_separate_player_ids(self, conn):
        self._admit(conn, ext="a")
        self._admit(conn, ext="b")
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "a", "/play"), now=NOW)
        core.handle(_ev("telegram", "b", "/play"), now=NOW)
        assert {"telegram:a", "telegram:b"} <= set(f.sessions)


# ---- /restart: the three-depth confirm -----------------------------------

class TestRestart:
    def _admit_started(self, conn, ext="rst"):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        registry.claim_invite(conn, code, "telegram", ext, now=NOW)
        registry.mark_started(conn, "telegram", ext)

    def test_restart_prompts_keep_or_redo_without_episode_options(self, conn):
        # No episodes yet → /restart is just a restart: keep/redo character + cancel.
        # The episode-vs-original depths must NOT appear (founder).
        self._admit_started(conn)
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "rst", "/restart"), now=NOW)
        body = out.chunks[0].lower()
        for word in ("keep", "redo", "cancel"):
            assert word in body
        assert "episode" not in body and "original" not in body
        assert f.calls == []  # the prompt opens no session

    def test_restart_cancel_keeps_game(self, conn):
        self._admit_started(conn)
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "rst", "/restart"), now=NOW)
        out = core.handle(_ev("telegram", "rst", "cancel"), now=NOW)
        assert "carry on" in out.chunks[0].lower()
        assert f.calls == []                      # no re-entry
        assert registry.is_started(conn, "telegram", "rst")

    def test_restart_keep_character(self, conn):
        # /restart → keep: clean copy + re-apply the saved character (no notes → no Q).
        self._admit_started(conn)
        registry.set_character(conn, "telegram", "rst", {"name": "Ilsa Renn"})
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "rst", "/restart"), now=NOW)
        out = core.handle(_ev("telegram", "rst", "keep"), now=NOW)
        assert "OPENING:anchor:telegram:rst" in out.chunks[0]
        assert f.calls[-1] == ("anchor", "telegram:rst", True, None)  # clean copy
        assert f.sessions["telegram:rst"].applied is not None         # same character

    def test_restart_redo_rebuilds_character(self, conn):
        self._admit_started(conn)
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "rst", "/restart"), now=NOW)
        out = core.handle(_ev("telegram", "rst", "redo"), now=NOW)
        assert "OPENING:anchor:telegram:rst" in out.chunks[0]
        assert f.calls[-1] == ("anchor", "telegram:rst", True, None)  # fresh=True


# ---- /note, /notes: the player journal -----------------------------------

class TestNotes:
    def _admit_started(self, conn, ext="nt"):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        registry.claim_invite(conn, code, "telegram", ext, now=NOW)
        registry.mark_started(conn, "telegram", ext)

    def test_note_add_and_list(self, conn):
        self._admit_started(conn)
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "nt", "/note the clerk lied"), now=NOW)
        assert "noted" in out.chunks[0].lower()
        out = core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert "the clerk lied" in out.chunks[0]
        assert "1." in out.chunks[0]

    def test_note_empty_gives_usage(self, conn):
        self._admit_started(conn)
        core = _core(conn, _Factory())
        out = core.handle(_ev("telegram", "nt", "/note"), now=NOW)
        assert "/note" in out.chunks[0] and "noted" not in out.chunks[0].lower()

    def test_notes_empty_hint(self, conn):
        self._admit_started(conn)
        core = _core(conn, _Factory())
        out = core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert "no notes yet" in out.chunks[0].lower()

    def test_note_captures_status_context(self, conn):
        # Run a prose turn first so a session is cached → /note stamps its status line.
        self._admit_started(conn)
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "nt", "I look around"), now=NOW)
        core.handle(_ev("telegram", "nt", "/note check the ledger"), now=NOW)
        out = core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert "[Day 1, night | the office]" in out.chunks[0]  # _FakeSession.status_line

    def test_notes_clear(self, conn):
        self._admit_started(conn)
        core = _core(conn, _Factory())
        core.handle(_ev("telegram", "nt", "/note a"), now=NOW)
        core.handle(_ev("telegram", "nt", "/note b"), now=NOW)
        out = core.handle(_ev("telegram", "nt", "/notes clear"), now=NOW)
        assert "cleared 2" in out.chunks[0].lower()
        out = core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert "no notes yet" in out.chunks[0].lower()

    def test_notes_lists_del_hint(self, conn):
        self._admit_started(conn)
        core = _core(conn, _Factory())
        core.handle(_ev("telegram", "nt", "/note a"), now=NOW)
        out = core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert "/del" in out.chunks[0]

    def test_del_removes_note_by_position(self, conn):
        self._admit_started(conn)
        core = _core(conn, _Factory())
        core.handle(_ev("telegram", "nt", "/note first"), now=NOW)
        core.handle(_ev("telegram", "nt", "/note second"), now=NOW)
        out = core.handle(_ev("telegram", "nt", "/del 1"), now=NOW)
        assert "deleted note 1" in out.chunks[0].lower() and "first" in out.chunks[0]
        out = core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert "second" in out.chunks[0] and "first" not in out.chunks[0]

    def test_del_out_of_range(self, conn):
        self._admit_started(conn)
        core = _core(conn, _Factory())
        out = core.handle(_ev("telegram", "nt", "/del 5"), now=NOW)
        assert "no note 5" in out.chunks[0].lower()

    def test_del_non_numeric(self, conn):
        self._admit_started(conn)
        core = _core(conn, _Factory())
        out = core.handle(_ev("telegram", "nt", "/del"), now=NOW)
        assert "which note" in out.chunks[0].lower()

    def test_notes_do_not_carry_to_a_different_adventure(self, conn):
        # Notes are per main character / scenario: a different adventure (different
        # scenario) starts with a clean journal.
        self._admit_started(conn)
        core = _core(conn, _Factory())
        core.handle(_ev("telegram", "nt", "/note remember Cray"), now=NOW)
        registry.set_scenario(conn, "telegram", "nt", "other_world")
        out = core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert "remember Cray" not in out.chunks[0]
        assert "no notes yet" in out.chunks[0].lower()
        # …but it still belongs to the original scenario (carries across its episodes).
        registry.set_scenario(conn, "telegram", "nt", "anchor")
        out = core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert "remember Cray" in out.chunks[0]

    def test_note_runs_no_turn(self, conn):
        self._admit_started(conn)
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "nt", "I look around"), now=NOW)
        before = list(f.sessions["telegram:nt"].turns)
        core.handle(_ev("telegram", "nt", "/note no turn please"), now=NOW)
        core.handle(_ev("telegram", "nt", "/notes"), now=NOW)
        assert f.sessions["telegram:nt"].turns == before  # neither command ran a turn

    def test_notes_registry_is_scoped_per_scenario(self, conn):
        # Each scenario (main character) has its own journal.
        registry.add_note(conn, "telegram", "nt", "anchor", "anchor note", None, NOW)
        registry.add_note(conn, "telegram", "nt", "other", "other note", None, NOW)
        assert [n["text"] for n in registry.list_notes(conn, "telegram", "nt", "anchor")] \
            == ["anchor note"]
        assert [n["text"] for n in registry.list_notes(conn, "telegram", "nt", "other")] \
            == ["other note"]

    def test_wipe_clears_all_notes(self, conn):
        # /wipe forgets the whole player → all notes across scenarios go.
        registry.add_note(conn, "telegram", "nt", "anchor", "a", None, NOW)
        registry.add_note(conn, "telegram", "nt", "other", "b", None, NOW)
        self._admit_started(conn)
        core = _core(conn, _Factory())
        core.handle(_ev("telegram", "nt", "/wipe"), now=NOW)
        assert registry.list_notes(conn, "telegram", "nt", "anchor") == []
        assert registry.list_notes(conn, "telegram", "nt", "other") == []

    def test_restart_asks_then_wipes_notes(self, conn):
        # /restart → redo (character) → asks keep/wipe notes; "wipe" clears them.
        self._admit_started(conn)
        core = _core(conn, _Factory())
        core.handle(_ev("telegram", "nt", "/note from the old run"), now=NOW)
        core.handle(_ev("telegram", "nt", "/restart"), now=NOW)
        out = core.handle(_ev("telegram", "nt", "redo"), now=NOW)
        assert "notes" in out.chunks[0].lower() and "wipe" in out.chunks[0].lower()
        core.handle(_ev("telegram", "nt", "wipe"), now=NOW)
        assert registry.list_notes(conn, "telegram", "nt", "anchor") == []

    def test_restart_keeps_notes_when_asked(self, conn):
        self._admit_started(conn)
        registry.set_character(conn, "telegram", "nt", {"name": "Ilsa"})
        core = _core(conn, _Factory())
        core.handle(_ev("telegram", "nt", "/note from the old run"), now=NOW)
        core.handle(_ev("telegram", "nt", "/restart"), now=NOW)
        core.handle(_ev("telegram", "nt", "keep"), now=NOW)        # keep character → notes question
        out = core.handle(_ev("telegram", "nt", "keep"), now=NOW)  # keep notes
        assert "OPENING:anchor:telegram:nt" in out.chunks[0]
        assert [n["text"] for n in registry.list_notes(conn, "telegram", "nt", "anchor")] \
            == ["from the old run"]

    def test_restart_no_notes_skips_question(self, conn):
        # With no notes, the restart acts immediately (no keep/wipe prompt).
        self._admit_started(conn)
        core = _core(conn, _Factory())
        core.handle(_ev("telegram", "nt", "/restart"), now=NOW)
        out = core.handle(_ev("telegram", "nt", "redo"), now=NOW)
        assert "OPENING:anchor:telegram:nt" in out.chunks[0]  # entered, no notes question


# ---- session-zero mode interview -----------------------------------------

class TestInterpretMode:
    @pytest.mark.parametrize("text", [
        "give me a story with a real ending",
        "I want stakes and a goal",
        "let me win or lose",
        "I want to finish the quest",
        "a conclusive story please",
    ])
    def test_ending_signals_choose_win_loss(self, text):
        assert _interpret_mode(text) == "win_loss"

    @pytest.mark.parametrize("text", [
        "let me roam",
        "freeplay",
        "I just want to explore the world",
        "sandbox, no win or lose",
        "begin",                 # neutral → safe default
        "",                      # empty → safe default
        "let's go",              # ambiguous → safe default
    ])
    def test_ambiguous_or_open_choose_endless(self, text):
        assert _interpret_mode(text) == "endless"

    def test_endless_cue_wins_an_explicit_tie(self):
        # Both an ending word and a roam word present → roam wins (never force stakes).
        assert _interpret_mode("I want to explore freely, no ending") == "endless"


class TestHumanizeStage:
    def test_maps_known_stages_to_warm_lines(self):
        assert "Dreaming up the story" in _humanize_stage(
            "Stage 0 · Authoring the hidden source story · prose-first")
        assert "Bringing the world into being" in _humanize_stage(
            "Stage 1 · Ingesting prose → pattern-buffer")
        assert "Final checks" in _humanize_stage("Stage 7 · Viability gate · …")

    def test_collapses_per_chunk_to_a_counter(self):
        assert _humanize_stage("   …chunk 3/7 extracted") == (
            "· Populating the world (3/7)…")

    def test_internal_lines_stay_silent(self):
        assert _humanize_stage("   …hidden bible saved → /tmp/x") is None
        assert _humanize_stage("Stage 6.2 · Classifying durability · BATCHED") is None
        assert _humanize_stage("") is None


# ---- chunking ------------------------------------------------------------

class TestChunk:
    def test_boundaries(self):
        assert chunk("", 10) == [""]              # empty still answers
        assert chunk("a" * 10, 10) == ["a" * 10]  # exact boundary, one piece
        parts = chunk("a" * 25, 10)
        assert parts == ["a" * 10, "a" * 10, "a" * 5]  # ordered, no truncation
        assert "".join(parts) == "a" * 25

    def test_prefers_newline(self):
        parts = chunk("hello\nworld", 8)
        assert parts == ["hello", "world"]


# ---- telegram adapter: exactly-once + ignore non-message -----------------

def _msg(uid, frm, text, chat_type="private"):
    return {"update_id": uid, "message": {"text": text,
            "chat": {"id": 1000 + frm, "type": chat_type}, "from": {"id": frm}}}


class _FakeTG:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


class TestTelegramAdapter:
    def test_duplicate_update_does_not_rerun_turn(self, conn):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        registry.claim_invite(conn, code, "telegram", "42", now=NOW)
        registry.mark_started(conn, "telegram", "42")  # returning player → prose runs
        f = _Factory()
        core = _core(conn, f)
        client = _FakeTG()
        upd = [_msg(10, 42, "I wait")]
        telegram_bot.process_updates(conn, core, client, upd, now_fn=lambda: NOW)
        telegram_bot.process_updates(conn, core, client, upd, now_fn=lambda: NOW)  # redelivery
        assert f.sessions["telegram:42"].turns == ["I wait"]   # ran exactly once
        assert registry.get_offset(conn, "telegram") == 11

    def test_non_message_and_group_updates_advance_without_session(self, conn):
        f = _Factory()
        core = _core(conn, f)
        client = _FakeTG()
        updates = [{"update_id": 5, "my_chat_member": {}},                 # non-message
                   _msg(6, 1, "hi", chat_type="group")]                    # group → ignored
        telegram_bot.process_updates(conn, core, client, updates, now_fn=lambda: NOW)
        assert f.calls == [] and client.sent == []
        assert registry.get_offset(conn, "telegram") == 7

    def test_send_failure_does_not_drop_reply_and_resends(self, conn):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        registry.claim_invite(conn, code, "telegram", "7", now=NOW)
        registry.mark_started(conn, "telegram", "7")  # returning player → prose runs
        f = _Factory()
        core = _core(conn, f)

        class _FlakyTG:
            def __init__(self):
                self.sent, self.fail = [], True

            def send_message(self, chat_id, text):
                if self.fail:
                    self.fail = False
                    raise RuntimeError("429 Too Many Requests")
                self.sent.append((chat_id, text))

        flaky = _FlakyTG()
        with pytest.raises(RuntimeError):  # first send fails → propagates
            telegram_bot.process_updates(conn, core, flaky, [_msg(3, 7, "hello")],
                                         now_fn=lambda: NOW)
        # the reply is durably recorded, unsent; the turn ran once; offset not advanced
        assert registry.pending_outbox(conn, "telegram")
        assert f.sessions["telegram:7"].turns == ["hello"]
        assert registry.get_offset(conn, "telegram") == 0
        # next poll drains the outbox (resend) without re-running the turn
        telegram_bot.process_updates(conn, core, flaky, [], now_fn=lambda: NOW)
        assert flaky.sent and registry.pending_outbox(conn, "telegram") == []
        assert f.sessions["telegram:7"].turns == ["hello"]  # still once

    def test_interrupted_update_is_detectable_not_silent(self, conn):
        # a crash between claim and record_outbox: claimed, but no reply
        registry.claim_update(conn, "telegram", 99)
        assert registry.interrupted_updates(conn, "telegram") == [99]
        registry.record_outbox(conn, "telegram", 99, "c", ["reply"])
        assert registry.interrupted_updates(conn, "telegram") == []

    def test_client_raises_redacted_on_not_ok(self):
        from types import SimpleNamespace as NS
        resp = NS(status_code=200, json=lambda: {"ok": False, "description": "bad"})
        client = telegram_bot.TelegramClient("123:SECRET",
                                             http=NS(get=lambda u, params=None: resp))
        with pytest.raises(RuntimeError) as exc:
            client.send_message("1", "hi")
        assert "SECRET" not in str(exc.value)

    def test_outbox_recorded_before_send_and_resends(self, conn):
        code = registry.mint_invite(conn, "telegram", "anchor", now=NOW)
        registry.claim_invite(conn, code, "telegram", "9", now=NOW)
        f = _Factory()
        core = _core(conn, f)
        # a turn whose reply spans two chunks
        f_session = None
        client = _FakeTG()
        telegram_bot.process_updates(conn, core, client,
                                     [_msg(3, 9, "x")], now_fn=lambda: NOW)
        assert client.sent  # sent
        # all outbox rows marked sent → nothing pending to resend
        assert registry.pending_outbox(conn, "telegram") == []


# ---- setup: secrets discipline -------------------------------------------

class TestSetup:
    @pytest.fixture(autouse=True)
    def _chdir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "worlds").mkdir()
        monkeypatch.delenv(setup.TOKEN_ENV, raising=False)

    def test_token_saved_0600_and_config_has_no_secret(self):
        setup.save_token("123:SECRET")
        mode = stat.S_IMODE(os.stat(setup.TOKEN_PATH).st_mode)
        assert mode == 0o600
        assert setup.read_token() == "123:SECRET"
        setup.save_config({"telegram_bot_username": "construct_demo_bot"})
        assert "SECRET" not in setup.CONFIG_PATH.read_text()

    def test_bad_token_raises_redacted(self):
        def _get(url):  # the URL embeds the token; the error must not leak it
            raise RuntimeError(f"connect fail to {url}")
        with pytest.raises(ValueError) as exc:
            setup.validate_token("123:SECRET", get=_get)
        assert "SECRET" not in str(exc.value)

    def test_telegram_rejection_is_loud(self):
        with pytest.raises(ValueError):
            setup.validate_token("bad", get=lambda u: SimpleNamespace(json=lambda: {"ok": False}))

    def test_setup_wizard_persists_username(self):
        ok = SimpleNamespace(json=lambda: {"ok": True, "result": {"username": "demo_bot"}})
        name = setup.setup_telegram(prompt=lambda _p: "123:SECRET",
                                    get=lambda u: ok, out=lambda *_a: None)
        assert name == "demo_bot"
        assert setup.load_config()["telegram_bot_username"] == "demo_bot"
        assert stat.S_IMODE(os.stat(setup.TOKEN_PATH).st_mode) == 0o600

    def test_first_load_menu_dismiss_writes_marker(self):
        assert setup.first_load_menu(input_fn=lambda _p: "s", out=lambda *_a: None) == "dismiss"
        assert setup.load_config()["telegram_dismissed"] is True
        # once dismissed, the menu no longer prompts
        assert setup.first_load_menu(input_fn=lambda _p: "t", out=lambda *_a: None) == "play"

    def test_first_load_menu_enter_is_play(self):
        assert setup.first_load_menu(input_fn=lambda _p: "", out=lambda *_a: None) == "play"

    def test_token_read_from_dotenv(self, monkeypatch):
        # drop the token in a .env (the operator's tomorrow-path) → read_token finds it
        from pathlib import Path
        Path(".env").write_text("# local secrets\nCONSTRUCT_TELEGRAM_TOKEN = \"123:ABCdef\"\n")
        assert setup.read_token() == "123:ABCdef"
        # env var still wins over .env
        monkeypatch.setenv(setup.TOKEN_ENV, "999:ENV")
        assert setup.read_token() == "999:ENV"


# ---- loopback: full offline flow -----------------------------------------

class TestLoopback:
    def test_full_offline_flow_claim_play_turn(self, tmp_path):
        reg = tmp_path / "reg.sqlite"
        conn = registry.connect(reg)
        code = registry.mint_invite(conn, "loopback", "anchor", now=NOW)
        inbound = tmp_path / "in.jsonl"
        outbox = tmp_path / "out.jsonl"
        lines = [
            {"external_id": "u1", "text": f"claim {code}", "update_id": 1},
            {"external_id": "u1", "text": "/play", "update_id": 2},
            {"external_id": "u1", "text": "I step inside", "update_id": 3},
        ]
        inbound.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
        f = _Factory()
        core = loopback.build_core(conn, session_factory=f,
                                   log_dir=tmp_path / "transcripts")
        ran = loopback.pump(conn, core, inbound, outbox, now_fn=lambda: NOW)
        assert ran == 3
        replies = [json.loads(l) for l in outbox.read_text().splitlines()]
        texts = [r["text"] for r in replies]
        assert any("construct projector" in t.lower() for t in texts)  # the welcome greeting
        assert any(t.startswith("OPENING:anchor:loopback:u1") for t in texts)
        assert any("narrated<I step inside>" in t for t in texts)
        # re-pumping the same inbound (restart) runs no new turns (exactly-once)
        assert loopback.pump(conn, core, inbound, outbox, now_fn=lambda: NOW) == 0

    def test_outbox_replayed_after_a_crash(self, tmp_path):
        # a reply recorded but not delivered (crash before append) is replayed
        conn = registry.connect(tmp_path / "reg.sqlite")
        registry.record_outbox(conn, "loopback", 5, "u1", ["recovered line"])
        outbox = tmp_path / "out.jsonl"
        inbound = tmp_path / "in.jsonl"
        inbound.write_text("")  # nothing new inbound
        core = loopback.build_core(conn, session_factory=_Factory(),
                                   log_dir=tmp_path / "t")
        loopback.pump(conn, core, inbound, outbox, now_fn=lambda: NOW)
        assert "recovered line" in outbox.read_text()
        assert registry.pending_outbox(conn, "loopback") == []
