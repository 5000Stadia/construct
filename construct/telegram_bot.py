"""The Telegram transport — a dumb pipe over `TransportCore`.

Mirrors the Discord bot's shape (per-user serialization, coalesce-free V1 =
one update → one turn, chunked replies) and the loopback adapter's exactly-once
bookkeeping, but its IO is Telegram `getUpdates`/`sendMessage`.

Exactly-once discipline (Codex spec review):
- the update offset is PERSISTED and advanced only AFTER an update is durably
  recorded — a redelivery after a crash never re-runs `Session.turn()`;
- a completed turn's reply is persisted to the outbox BEFORE sending, so a
  send failure/429 retries the SEND, not the turn;
- on startup any unsent outbox chunks are flushed first;
- the bot token is embedded in request URLs, so it is REDACTED from every log.
- only private chats are served; identity is the sender `from.id`, never a
  username and never a group `chat.id`.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from construct import registry
from construct.transport_core import InboundEvent, TransportCore

logger = logging.getLogger(__name__)

PLATFORM = "telegram"
MSG_LIMIT = 4096          # Telegram's hard per-message limit
LONG_POLL_SECONDS = 25    # getUpdates long-poll window


class TelegramClient:
    """Thin httpx wrapper. Redacts the token from any raised error."""

    def __init__(self, token: str, *, http=None) -> None:
        self._token = token
        self._base = f"https://api.telegram.org/bot{token}"
        if http is None:
            import httpx
            http = httpx.Client(timeout=LONG_POLL_SECONDS + 10)
        self._http = http

    def _redact(self, msg: str) -> str:
        return msg.replace(self._token, "***")

    def get_updates(self, offset: int) -> list[dict]:
        try:
            resp = self._http.get(f"{self._base}/getUpdates",
                                  params={"offset": offset, "timeout": LONG_POLL_SECONDS})
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(self._redact(str(exc))) from None
        if not data.get("ok"):
            raise RuntimeError(f"getUpdates not ok: {self._redact(str(data))}")
        return data.get("result", [])

    def send_message(self, chat_id: str, text: str) -> None:
        """Send one message; RAISE (redacted) on any non-ok response so the
        caller does NOT mark it sent — a 429/Bad Request must be retried, not
        silently dropped (Codex review)."""
        try:
            resp = self._http.get(f"{self._base}/sendMessage",
                                  params={"chat_id": chat_id, "text": text})
            ok = resp.json().get("ok", False)
            status = getattr(resp, "status_code", 200)
        except Exception as exc:
            raise RuntimeError(self._redact(str(exc))) from None
        if not ok or status >= 400:
            raise RuntimeError(self._redact(f"sendMessage failed (status={status})"))


def _event_from_update(update: dict) -> InboundEvent | None:
    """Normalize a Telegram update into an InboundEvent, or None to ignore
    (non-message updates, non-private chats, text-less messages)."""
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return None
    chat = msg.get("chat", {})
    if chat.get("type") != "private":  # serve DMs only (Codex)
        return None
    frm = msg.get("from", {})
    if "id" not in frm:
        return None
    return InboundEvent(
        platform=PLATFORM, external_id=str(frm["id"]),
        chat_id=str(chat.get("id", frm["id"])), text=str(msg["text"]),
        update_ids=(int(update["update_id"]),))


def flush_outbox(conn, client: TelegramClient) -> None:
    """Resend any reply chunks recorded but not yet confirmed sent (a restart
    resumes here — the turn is NOT re-run)."""
    for row in registry.pending_outbox(conn, PLATFORM):
        client.send_message(row["chat_id"], row["text"])
        registry.mark_sent(conn, PLATFORM, row["update_id"], row["seq"])


def process_updates(conn, core: TransportCore, client: TelegramClient,
                    updates: list[dict], *, now_fn: Callable[[], float] = time.time) -> int:
    """Handle a batch of raw Telegram updates; advance + persist the offset
    past each. Order per update: dedup-claim → run turn → record the reply
    DURABLY → send → mark sent → advance offset. A send failure raises before
    the offset advances, so the next poll resends from the outbox without
    re-running the turn (exactly-once turn, at-least-once send)."""
    flush_outbox(conn, client)  # resend anything left unsent by a prior failure
    offset = registry.get_offset(conn, PLATFORM)
    for update in updates:
        uid = int(update["update_id"])
        ev = _event_from_update(update)
        if ev is not None and registry.claim_update(conn, PLATFORM, uid):
            out = core.handle(ev, now=now_fn())
            registry.record_outbox(conn, PLATFORM, uid, out.chat_id, out.chunks)
        _send_pending(conn, client, uid)  # raises on failure → offset NOT advanced
        offset = max(offset, uid + 1)
        registry.set_offset(conn, PLATFORM, offset)
    return offset


def _send_pending(conn, client: TelegramClient, update_id: int) -> None:
    """Send (and mark sent) any unsent outbox chunks for one update, in order.
    A send that raises leaves the remaining chunks unsent for the next flush."""
    for row in registry.pending_outbox(conn, PLATFORM):
        if row["update_id"] != update_id:
            continue
        client.send_message(row["chat_id"], row["text"])
        registry.mark_sent(conn, PLATFORM, update_id, row["seq"])


def _drain_backlog(conn, client: TelegramClient) -> None:
    """First-ever poll: skip any pre-existing backlog (the bot starts fresh,
    not replaying yesterday's messages) by advancing the offset past it
    without processing. Idempotent: only runs while the offset is still 0."""
    if registry.get_offset(conn, PLATFORM) != 0:
        return
    updates = client.get_updates(0)
    if updates:
        last = max(int(u["update_id"]) for u in updates)
        registry.set_offset(conn, PLATFORM, last + 1)
        logger.info("telegram: skipped %d backlog updates on first start", len(updates))


def serve(registry_path, token: str, *, session_factory=None, client: TelegramClient | None = None,
          poll_iterations: int | None = None) -> None:
    """Run the Telegram transport loop. `poll_iterations` bounds the loop for
    tests/one-shot use; None = run forever (Ctrl-C to stop)."""
    conn = registry.connect(registry_path)
    client = client or TelegramClient(token)

    def _notify(chat_id: str, text: str) -> None:
        # Interim progress sends DURING a build (the Atrium pings) — outside the
        # exactly-once outbox, best-effort: a dropped ping must not sink the build.
        try:
            client.send_message(chat_id, text)
        except Exception:
            logger.exception("telegram notify failed")

    core = TransportCore(conn, platform=PLATFORM, msg_limit=MSG_LIMIT,
                         session_factory=session_factory, notify=_notify)
    for uid in registry.interrupted_updates(conn, PLATFORM):
        logger.error("telegram: update %s was interrupted mid-turn; its reply was "
                     "never produced (the player may retry) — not re-running", uid)
    flush_outbox(conn, client)
    _drain_backlog(conn, client)
    i = 0
    while poll_iterations is None or i < poll_iterations:
        try:
            updates = client.get_updates(registry.get_offset(conn, PLATFORM))
            process_updates(conn, core, client, updates)
        except Exception:  # a bad poll/turn must not kill the transport
            logger.exception("telegram poll error")
            time.sleep(2)
        i += 1
