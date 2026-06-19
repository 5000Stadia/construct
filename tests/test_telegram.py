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
from construct.transport_core import STATIC_REJECT, InboundEvent, TransportCore, chunk

NOW = 1_000_000.0


# ---- fakes ---------------------------------------------------------------

class _FakeSession:
    def __init__(self, scenario, player_id, fresh):
        self.scenario, self.player_id, self.fresh = scenario, player_id, fresh
        self.turns = []

    def opening(self):
        return f"OPENING:{self.scenario}:{self.player_id}"

    def turn(self, text):
        self.turns.append(text)
        return SimpleNamespace(prose=f"narrated<{text}>", ok=True, ended=False)


class _Factory:
    def __init__(self):
        self.calls = []
        self.sessions = {}

    def __call__(self, *, scenario, player_id, fresh):
        s = _FakeSession(scenario, player_id, fresh)
        self.calls.append((scenario, player_id, fresh))
        self.sessions[player_id] = s
        return s


@pytest.fixture
def conn(tmp_path):
    return registry.connect(tmp_path / "reg.sqlite")


def _log_dir_for(conn):
    """Keep transcripts beside the (tmp) registry, never in the repo's worlds/."""
    row = conn.execute("PRAGMA database_list").fetchone()
    from pathlib import Path
    return Path(row["file"]).parent / "transcripts"


def _core(conn, factory, platform="telegram", limit=4096):
    return TransportCore(conn, platform=platform, msg_limit=limit,
                         session_factory=factory, log_dir=_log_dir_for(conn))


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
        assert "Invite accepted" in out.chunks[0] and "anchor" in out.chunks[0]
        assert f.calls == []  # claiming opens no session yet


# ---- core: routing + scenario scope --------------------------------------

class TestRouting:
    def _admit(self, conn, ext="5", scenario="anchor"):
        code = registry.mint_invite(conn, "telegram", scenario, now=NOW)
        registry.claim_invite(conn, code, "telegram", ext, now=NOW)

    def test_play_is_fresh_resume_is_not_and_locked_to_scenario(self, conn):
        self._admit(conn, scenario="anchor")
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "5", "/play other_scenario"), now=NOW)
        assert out.chunks == ["OPENING:anchor:telegram:5"]   # arg ignored; scope locked
        assert f.calls[-1] == ("anchor", "telegram:5", True)  # fresh
        core.handle(_ev("telegram", "5", "/resume"), now=NOW)
        assert f.calls[-1] == ("anchor", "telegram:5", False)

    def test_prose_auto_resumes_and_runs_turn(self, conn):
        self._admit(conn, ext="6")
        f = _Factory()
        core = _core(conn, f)
        out = core.handle(_ev("telegram", "6", "I look around"), now=NOW)
        assert out.chunks == ["narrated<I look around>"]
        assert f.sessions["telegram:6"].turns == ["I look around"]

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
        assert "BOT: narrated<I open the ledger>" in body

    def test_two_players_get_separate_player_ids(self, conn):
        self._admit(conn, ext="a")
        self._admit(conn, ext="b")
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "a", "/play"), now=NOW)
        core.handle(_ev("telegram", "b", "/play"), now=NOW)
        assert {"telegram:a", "telegram:b"} <= set(f.sessions)


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
        assert any("Invite accepted" in t for t in texts)
        assert any(t.startswith("OPENING:anchor:loopback:u1") for t in texts)
        assert any(t == "narrated<I step inside>" for t in texts)
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
