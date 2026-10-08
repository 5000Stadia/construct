"""Regression tests for the transport polish batch (audit/transport.md BUG 1, 2, 4).

BUG 1 — leaving a world (/exit, /wipe, /disconnect, entering another world) must
        clear EVERY pending prompt, notably the chapter-end "continue?" arm.
BUG 2 — a permanently failing Telegram chat must not wedge every other player's
        outbox; transient failures still retry.
BUG 4 — the destructive /restart confirm steps match exact choices as whole
        words, re-ask (state stays armed) on anything ambiguous, and let
        commands pass through without taking them as answers.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from construct import registry, telegram_bot
from construct.transport_core import (
    PENDING_CONTINUE, PENDING_EXIT, PENDING_RESTART_CHARACTER, PENDING_RESTART_DEPTH,
    PENDING_RESTART_NOTES)
from tests.test_telegram import (NOW, _core, _Factory, _FakeSession, _ev, _msg)


@pytest.fixture
def conn(tmp_path):
    return registry.connect(tmp_path / "reg.sqlite")


def _admit_started(conn, ext, scenario="anchor"):
    code = registry.mint_invite(conn, "telegram", scenario, now=NOW)
    registry.claim_invite(conn, code, "telegram", ext, now=NOW)
    registry.mark_started(conn, "telegram", ext)
    return f"telegram:{ext}"


# ---- BUG 1: pending continue survives leaving the world -------------------

class _EndingSession(_FakeSession):
    def turn(self, text):
        return SimpleNamespace(prose="p", ok=True, ended=True, can_continue=True,
                               exit_requested=False)


class _EndingFactory(_Factory):
    def __call__(self, *, scenario, player_id, fresh, mode_override=None):
        s = _EndingSession(scenario, player_id, fresh, mode_override, setup=self.setup)
        self.calls.append((scenario, player_id, fresh, mode_override))
        self.sessions[player_id] = s
        return s


class TestPendingContinueCleared:
    @pytest.mark.parametrize("leave", ["/exit", "/wipe", "/disconnect"])
    def test_leaving_the_world_disarms_continue(self, conn, monkeypatch, leave):
        pid = _admit_started(conn, "x1", "bodycase")
        core = _core(conn, _EndingFactory())
        core.handle(_ev("telegram", "x1", "I accuse him"), now=NOW)
        assert core._peek(pid, PENDING_CONTINUE)          # chapter ended: continue armed
        core.handle(_ev("telegram", "x1", leave), now=NOW)
        assert not core._peek(pid, PENDING_CONTINUE)
        called = []
        monkeypatch.setattr(core, "_do_continue",
                            lambda p, ev: called.append(p) or core._reply(ev, "CONT"))
        if leave == "/disconnect":
            return  # un-claimed: the next message goes to the claim gate, not a chapter
        core.handle(_ev("telegram", "x1", "list"), now=NOW)
        assert called == [], "a start-menu message must not build a new chapter"

    def test_entering_a_world_disarms_continue(self, conn):
        pid = _admit_started(conn, "x2")
        core = _core(conn, _Factory())
        core._arm(pid, PENDING_CONTINUE)
        core._enter_world(pid, _ev("telegram", "x2", "go"), scenario="anchor",
                          mode=None, preamble="", fresh=False)
        assert not core._peek(pid, PENDING_CONTINUE)

    def test_clear_pending_covers_every_prompt(self, conn):
        pid = _admit_started(conn, "x3")
        core = _core(conn, _Factory())
        core._arm(pid, PENDING_EXIT)
        core._arm(pid, PENDING_RESTART_NOTES, keep_character=True)
        core._arm(pid, PENDING_CONTINUE)
        core._clear_pending(pid)
        assert not core._pending
        for kind in (PENDING_EXIT, PENDING_RESTART_DEPTH, PENDING_RESTART_CHARACTER,
                     PENDING_RESTART_NOTES, PENDING_CONTINUE):
            assert core._peek(pid, kind) is None


class TestPendingState:
    def test_arm_peek_disarm_roundtrip_with_data(self, conn):
        pid = _admit_started(conn, "p1")
        core = _core(conn, _Factory())
        core._arm(pid, PENDING_RESTART_NOTES, keep_character=True)
        assert core._peek(pid, PENDING_RESTART_NOTES).data == {"keep_character": True}
        taken = core._disarm(pid, PENDING_RESTART_NOTES)
        assert taken.kind == PENDING_RESTART_NOTES and taken.data["keep_character"]
        assert core._disarm(pid, PENDING_RESTART_NOTES) is None
        assert pid not in core._pending

    def test_restart_steps_are_one_wizard(self, conn):
        pid = _admit_started(conn, "p2")
        core = _core(conn, _Factory())
        core._arm(pid, PENDING_RESTART_DEPTH)
        core._arm(pid, PENDING_RESTART_CHARACTER)
        assert core._peek(pid, PENDING_RESTART_DEPTH) is None
        core._arm(pid, PENDING_RESTART_NOTES)
        assert core._peek(pid, PENDING_RESTART_CHARACTER) is None

    def test_different_kinds_coexist(self, conn):
        """A command passes through an armed prompt, so prompts of different kinds
        can be armed together; cancelling a restart must not lose the chapter-end
        continue (this is why the state is a per-kind map, not one slot)."""
        pid = _admit_started(conn, "p3", "bodycase")
        core = _core(conn, _EndingFactory())
        core.handle(_ev("telegram", "p3", "I accuse him"), now=NOW)
        assert core._peek(pid, PENDING_CONTINUE)
        core.handle(_ev("telegram", "p3", "/restart"), now=NOW)
        assert core._peek(pid, PENDING_RESTART_CHARACTER)
        assert core._peek(pid, PENDING_CONTINUE)       # both armed
        out = core.handle(_ev("telegram", "p3", "cancel"), now=NOW)
        assert "carry on" in out.chunks[0].lower()
        assert core._peek(pid, PENDING_RESTART_CHARACTER) is None
        assert core._peek(pid, PENDING_CONTINUE)       # still offered


# ---- BUG 4: restart-confirm answers --------------------------------------

class TestRestartAnswers:
    def _to_notes_step(self, conn, ext="rs"):
        """/restart -> redo -> (has notes) the step-3 keep/wipe question."""
        pid = _admit_started(conn, ext)
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", ext, "/note an old clue"), now=NOW)
        core.handle(_ev("telegram", ext, "/restart"), now=NOW)
        out = core.handle(_ev("telegram", ext, "redo"), now=NOW)
        assert "notes" in out.chunks[0].lower()
        assert core._peek(pid, PENDING_RESTART_NOTES)
        return pid, f, core

    def _notes(self, conn, ext):
        return registry.list_notes(conn, "telegram", ext, "anchor")

    @pytest.mark.parametrize("cmd", ["/help", "/feedback it broke", "/status"])
    def test_step3_command_passes_through_and_does_not_restart(self, conn, cmd):
        pid, f, core = self._to_notes_step(conn)
        calls_before = len(f.calls)
        core.handle(_ev("telegram", "rs", cmd), now=NOW)
        assert not any(c[2] for c in f.calls[calls_before:])  # no fresh (restart) open
        assert core._peek(pid, PENDING_RESTART_NOTES)     # still armed
        assert self._notes(conn, "rs")                # notes untouched
        out = core.handle(_ev("telegram", "rs", "keep"), now=NOW)  # the real answer works
        assert "OPENING" in out.chunks[0]
        assert self._notes(conn, "rs")

    @pytest.mark.parametrize("answer", ["maybe", "yes", "hmm not sure", "keep or wipe"])
    def test_step3_ambiguous_reasks_and_keeps_state(self, conn, answer):
        pid, f, core = self._to_notes_step(conn)
        calls_before = len(f.calls)
        out = core.handle(_ev("telegram", "rs", answer), now=NOW)
        assert len(f.calls) == calls_before
        assert core._peek(pid, PENDING_RESTART_NOTES)
        assert self._notes(conn, "rs")
        body = out.chunks[0].lower()
        assert "keep" in body and "wipe" in body      # re-asked

    def test_step3_yes_keep_them_keeps_notes(self, conn):
        # "yes, keep them" used to WIPE the notes (substring "yes").
        pid, f, core = self._to_notes_step(conn)
        out = core.handle(_ev("telegram", "rs", "yes, keep them"), now=NOW)
        assert "OPENING" in out.chunks[0]
        assert [n["text"] for n in self._notes(conn, "rs")] == ["an old clue"]

    def test_step3_wipe_and_cancel_still_work(self, conn):
        pid, f, core = self._to_notes_step(conn)
        core.handle(_ev("telegram", "rs", "Wipe."), now=NOW)
        assert self._notes(conn, "rs") == []
        pid, f, core = self._to_notes_step(conn, "rs2")
        out = core.handle(_ev("telegram", "rs2", "cancel"), now=NOW)
        assert "carry on" in out.chunks[0].lower()
        assert not core._peek(pid, PENDING_RESTART_NOTES)
        assert registry.list_notes(conn, "telegram", "rs2", "anchor")

    def test_step2_keep_my_character_new_name_does_not_redo(self, conn):
        # "new" used to be a redo keyword and was checked first -> discarded the character.
        pid = _admit_started(conn, "k2")
        registry.set_character(conn, "telegram", "k2", {"name": "Ilsa Renn"})
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "k2", "/restart"), now=NOW)
        out = core.handle(_ev("telegram", "k2", "keep my character, new name"), now=NOW)
        assert "OPENING" in out.chunks[0]
        assert f.sessions[pid].applied is not None    # the saved character was re-applied

    @pytest.mark.parametrize("answer", ["hmm", "new name please", "keep and redo"])
    def test_step2_ambiguous_reasks_and_keeps_state(self, conn, answer):
        pid = _admit_started(conn, "k3")
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "k3", "/restart"), now=NOW)
        out = core.handle(_ev("telegram", "k3", answer), now=NOW)
        assert f.calls == []
        assert core._peek(pid, PENDING_RESTART_CHARACTER)
        assert "keep" in out.chunks[0].lower() and "redo" in out.chunks[0].lower()

    def test_step2_command_passes_through(self, conn):
        pid = _admit_started(conn, "k4")
        f = _Factory()
        core = _core(conn, f)
        core.handle(_ev("telegram", "k4", "/restart"), now=NOW)
        core.handle(_ev("telegram", "k4", "/help"), now=NOW)
        assert f.calls == [] and core._peek(pid, PENDING_RESTART_CHARACTER)

    def test_step1_ambiguous_and_command_keep_state(self, conn):
        pid = _admit_started(conn, "k1")
        f = _Factory()
        core = _core(conn, f)
        core._arm(pid, PENDING_RESTART_DEPTH)            # multi-episode path (hook is off today)
        core.handle(_ev("telegram", "k1", "/help"), now=NOW)
        assert core._peek(pid, PENDING_RESTART_DEPTH)
        out = core.handle(_ev("telegram", "k1", "this or that, I forget"), now=NOW)
        assert core._peek(pid, PENDING_RESTART_DEPTH) and f.calls == []
        assert "episode" in out.chunks[0].lower() and "original" in out.chunks[0].lower()

    def test_new_restart_resets_a_half_answered_restart(self, conn):
        pid, f, core = self._to_notes_step(conn)
        core.handle(_ev("telegram", "rs", "/restart"), now=NOW)
        assert not core._peek(pid, PENDING_RESTART_NOTES)
        assert core._peek(pid, PENDING_RESTART_CHARACTER)   # back at the first question


# ---- BUG 2: Telegram outbox head-of-line wedge ---------------------------

class _HTTP:
    """Fake httpx: sendMessage fails per chat_id with the mapped status/exception."""

    def __init__(self, failures=None):
        self.failures = failures or {}
        self.sent = []

    def get(self, url, params=None):
        if url.endswith("/sendMessage"):
            fail = self.failures.get(str(params["chat_id"]))
            if isinstance(fail, Exception):
                raise fail
            if fail:
                return SimpleNamespace(status_code=fail, json=lambda: {"ok": False})
            self.sent.append((str(params["chat_id"]), params["text"]))
        return SimpleNamespace(status_code=200, json=lambda: {"ok": True, "result": []})


def _outbox_states(conn):
    return {(r["update_id"], r["seq"]): r["sent"]
            for r in conn.execute("SELECT update_id, seq, sent FROM outbox")}


class TestOutboxDeadLetter:
    def _core_with_players(self, conn):
        for ext in ("1", "2"):
            _admit_started(conn, ext)
        return _core(conn, _Factory())

    def test_blocked_chat_does_not_silence_the_others(self, conn):
        core = self._core_with_players(conn)
        http = _HTTP({"1001": 403})                     # player 1 blocked the bot
        client = telegram_bot.TelegramClient("123:TOK", http=http)
        telegram_bot.process_updates(conn, core, client, [_msg(1, 1, "hi")],
                                     now_fn=lambda: NOW)        # must not raise
        telegram_bot.process_updates(conn, core, client, [_msg(2, 2, "hello")],
                                     now_fn=lambda: NOW)
        assert any(chat == "1002" for chat, _ in http.sent)     # healthy player answered
        assert registry.get_offset(conn, "telegram") == 3       # offset advanced
        assert registry.pending_outbox(conn, "telegram") == []  # nothing left to retry
        assert telegram_bot.OUTBOX_FAILED in _outbox_states(conn).values()

    def test_dead_letter_is_not_resent(self, conn):
        core = self._core_with_players(conn)
        http = _HTTP({"1001": 400})
        client = telegram_bot.TelegramClient("123:TOK", http=http)
        telegram_bot.process_updates(conn, core, client, [_msg(1, 1, "hi")],
                                     now_fn=lambda: NOW)
        http.failures.clear()                                   # even if it would now work
        telegram_bot.flush_outbox(conn, client)
        assert http.sent == []

    @pytest.mark.parametrize("fail", [429, 500, 502, RuntimeError("connection reset")])
    def test_transient_failures_still_retry(self, conn, fail):
        core = self._core_with_players(conn)
        http = _HTTP({"1001": fail})
        client = telegram_bot.TelegramClient("123:TOK", http=http)
        with pytest.raises(RuntimeError):
            telegram_bot.process_updates(conn, core, client, [_msg(1, 1, "hi")],
                                         now_fn=lambda: NOW)
        assert registry.pending_outbox(conn, "telegram")        # still queued
        assert registry.get_offset(conn, "telegram") == 0       # offset not advanced
        http.failures.clear()                                   # recovered
        telegram_bot.process_updates(conn, core, client, [], now_fn=lambda: NOW)
        assert registry.pending_outbox(conn, "telegram") == []
        assert [c for c, _ in http.sent] == ["1001"]            # delivered, not dead-lettered
        assert telegram_bot.OUTBOX_FAILED not in _outbox_states(conn).values()

    @pytest.mark.parametrize("status,permanent", [
        (400, True), (401, True), (403, True), (404, True),
        (429, False), (500, False), (503, False)])
    def test_client_classifies_status(self, status, permanent):
        client = telegram_bot.TelegramClient(
            "123:SECRET", http=_HTTP({"7": status}))
        with pytest.raises(telegram_bot.TelegramSendError) as exc:
            client.send_message("7", "x")
        assert exc.value.permanent is permanent
        assert "SECRET" not in str(exc.value)

    def test_client_network_error_is_transient(self):
        client = telegram_bot.TelegramClient(
            "123:SECRET", http=_HTTP({"7": OSError("boom 123:SECRET")}))
        with pytest.raises(telegram_bot.TelegramSendError) as exc:
            client.send_message("7", "x")
        assert exc.value.permanent is False
        assert "SECRET" not in str(exc.value)
