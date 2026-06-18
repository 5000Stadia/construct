"""The transport-agnostic core — the dumb pipe shared by every chat
transport (Telegram, the offline loopback, any future adapter).

It consumes a NORMALIZED `InboundEvent` and returns an `Outbound` (chat id +
already-chunked reply). It owns exactly what is transport-independent:
- the **invite gate** (unknown senders get a static rejection with ZERO model
  or `Session` allocation — the gate sits before any session is opened);
- **command routing** (`/help /play /resume /scenarios`) and in-world turns;
- **scenario scope** (a claimed player is locked to the scenario their invite
  granted — `/play other` cannot escape it);
- **session routing** via an injectable factory (so offline tests use a fake
  `Session`, never `CodexProvider`);
- **reply chunking** at the adapter-provided message limit.

IO (`getUpdates`/`sendMessage`, file queues) and exactly-once persistence
(offset/dedup/outbox) live in the adapters, not here (Codex spec review).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from construct import registry

logger = logging.getLogger(__name__)

#: Where per-player transcripts and /dump snapshots are written. Under the
#: already-gitignored `worlds/`, so chat logs never enter version control.
DEFAULT_LOG_DIR = Path("worlds/.construct/transcripts")

STATIC_REJECT = (
    "This Construct bot is invite-only. Send the CONS- invite code the operator "
    "gave you to begin.")
HELP = ("Commands: /play (begin), /resume (continue), /scenarios (your world), "
        "/dump (save this chat to a log), /help. Anything else is what you do "
        "in the story.")


@dataclass(frozen=True)
class InboundEvent:
    """A transport-neutral inbound message. `update_ids` are the source
    update ids this event covers (one normally; several when an adapter
    coalesces a burst) — the adapter uses them for exactly-once bookkeeping."""

    platform: str
    external_id: str
    chat_id: str
    text: str
    update_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Outbound:
    chat_id: str
    chunks: list[str] = field(default_factory=list)


def chunk(text: str, limit: int) -> list[str]:
    """Split `text` into ≤`limit` pieces, never silently truncating (the
    Kernos-bot lesson). Prefers a newline boundary, then a hard cut. Always
    returns ≥1 chunk (empty text → one empty string, so a turn always
    answers)."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks or [""]


class TransportCore:
    """One per running transport. Holds the open sessions keyed by player_id;
    routing is synchronous (the adapter serializes per-player by handing
    events one at a time)."""

    def __init__(self, conn, *, platform: str, msg_limit: int,
                 session_factory: Callable[..., Any] | None = None,
                 log_dir: Path | str | None = None) -> None:
        self._conn = conn
        self._platform = platform
        self._limit = msg_limit
        self._sessions: dict[str, Any] = {}
        self._session_factory = session_factory or _default_session_factory
        self._log_dir = Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR

    def handle(self, ev: InboundEvent, *, now: float) -> Outbound:
        """Route one inbound event to a reply. Never raises for an in-world
        failure — a transport must survive every turn."""
        text = ev.text.strip()
        pid = registry.player_for(self._conn, ev.platform, ev.external_id)
        if pid is None:
            return self._gate(ev, text, now=now)
        # A live, readable transcript per player (USER/BOT lines) — written to
        # the gitignored log dir. /dump snapshots it on demand (operator ask).
        self._log(ev, "USER", ev.text)
        if text.lower().startswith("/dump"):
            out = self._reply(ev, self._dump(ev))
        elif text.startswith("/"):
            out = self._reply(ev, self._command(pid, ev, text))
        else:
            out = self._turn(pid, ev, text)
        self._log(ev, "BOT", "\n".join(out.chunks))
        return out

    # -- gate: the only thing an un-claimed sender can do is present a code --
    def _gate(self, ev: InboundEvent, text: str, *, now: float) -> Outbound:
        code = _extract_code(text)
        if code:
            pid = registry.claim_invite(self._conn, code, ev.platform,
                                        ev.external_id, now=now)
            if pid:
                scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
                return self._reply(ev, f"Invite accepted — welcome. Send /play to "
                                       f"begin {scenario}, or /help.")
        return self._reply(ev, STATIC_REJECT)  # uniform; never leaks the reason

    def _command(self, pid: str, ev: InboundEvent, text: str) -> str:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if cmd == "/help":
            return HELP
        if cmd == "/scenarios":
            return f"Your world: {scenario}."
        if cmd in ("/play", "/resume"):
            # Scenario scope is locked to the invite (Codex): the argument, if
            # any, is ignored — a player cannot reach an ungranted scenario.
            fresh = cmd == "/play"
            try:
                self._sessions[pid] = self._session_factory(
                    scenario=scenario, player_id=pid, fresh=fresh)
            except Exception as exc:
                logger.exception("session open failed for %s", pid)
                return f"(could not open {scenario}: {exc})"
            return self._sessions[pid].opening()
        return f"Unknown command. {HELP}"

    def _turn(self, pid: str, ev: InboundEvent, text: str) -> Outbound:
        session = self._sessions.get(pid)
        if session is None:  # auto-resume the granted scenario on first prose
            scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
            try:
                session = self._sessions[pid] = self._session_factory(
                    scenario=scenario, player_id=pid, fresh=False)
            except Exception as exc:
                logger.exception("auto-resume failed for %s", pid)
                return self._reply(ev, f"(could not open your world: {exc})")
        reply = session.turn(text)
        return self._reply(ev, reply.prose)

    def _reply(self, ev: InboundEvent, text: str) -> Outbound:
        return Outbound(chat_id=ev.chat_id, chunks=chunk(text, self._limit))

    # -- transcript + /dump ------------------------------------------------
    def _transcript_path(self, ev: InboundEvent) -> Path:
        import re
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", ev.external_id).strip("_") or "player"
        return self._log_dir / f"{ev.platform}_{safe}.log"

    def _log(self, ev: InboundEvent, role: str, text: str) -> None:
        """Append one line to the player's live transcript. Best-effort — a
        logging failure must never sink a turn."""
        try:
            path = self._transcript_path(ev)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as fh:
                fh.write(f"{role}: {text}\n\n")
        except Exception:
            logger.exception("transcript write failed for %s", ev.external_id)

    def _dump(self, ev: InboundEvent) -> str:
        """`/dump`: report the on-disk transcript (the running chat history,
        in a gitignored location) so the operator can read it."""
        path = self._transcript_path(ev)
        exchanges = 0
        if path.exists():
            exchanges = sum(1 for ln in path.read_text().splitlines() if ln.startswith("USER:"))
        return f"Transcript: {path.resolve()} ({exchanges} exchanges so far)."


def _extract_code(text: str) -> str | None:
    """Pull a `CONS-…` code out of a message (case-insensitive, first token
    that looks like one). Returns the canonical upper-cased code or None."""
    for tok in text.replace("\n", " ").split():
        if tok.upper().startswith("CONS-") and len(tok) > 6:
            return tok.upper()
    return None


def _default_session_factory(*, scenario: str, player_id: str, fresh: bool):
    from construct import Session
    return Session.open(scenario, player_id=player_id, fresh=fresh)
