"""The transport registry — invite gate, player mapping, and exactly-once
delivery bookkeeping for the Telegram (and any future) transport.

A small SQLite file at `worlds/.construct/registry.sqlite` (under the
already-gitignored `worlds/`). It holds NO secrets — the bot token never
touches this file (Cx 065 review). Everything here is local, host-side, and
needs no pattern-buffer engine surface.

Design (per Codex spec review of 2026-06):
- **Invite codes are bearer credentials**: a long random token (not a 4-char
  code), single-use, platform-locked, time-boxed.
- **Atomic claim**: one conditional `UPDATE` consumes the invite only if it is
  still open, matches the platform, is unclaimed, and unexpired — SQLite
  serializes writers, so two racing claimers yield exactly one winner.
- **Idempotent for an existing player**: a Telegram user who already has a
  mapping never burns a second invite or switches scenario.
- **Exactly-once turns**: `processed`/`offset`/`outbox` tables let the Telegram
  poller advance its update offset only after durable storage, dedupe updates
  across restarts (no double `Session.turn()`), and retry *sending* a reply
  without re-running the turn.
- All time is an injected UTC epoch (`now`) so expiry is deterministic in tests.
"""

from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

INVITE_TTL_SECONDS = 72 * 3600  # default 72h (Cx 065)
_CODE_BYTES = 8  # → a 13-char base32 body; ample against brute force

_SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    code        TEXT PRIMARY KEY,
    platform    TEXT NOT NULL,
    scenario    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',   -- open | claimed
    expires_at  REAL NOT NULL,
    claimed_by  TEXT
);
CREATE TABLE IF NOT EXISTS players (
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    player_id   TEXT NOT NULL,
    scenario    TEXT NOT NULL,
    created_at  REAL NOT NULL,
    PRIMARY KEY (platform, external_id)
);
CREATE TABLE IF NOT EXISTS offsets (
    platform    TEXT PRIMARY KEY,
    next_offset INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS processed (
    platform    TEXT NOT NULL,
    update_id   INTEGER NOT NULL,
    PRIMARY KEY (platform, update_id)
);
CREATE TABLE IF NOT EXISTS outbox (
    platform    TEXT NOT NULL,
    update_id   INTEGER NOT NULL,
    seq         INTEGER NOT NULL,
    chat_id     TEXT NOT NULL,
    text        TEXT NOT NULL,
    sent        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, update_id, seq)
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (creating parent dirs + schema) the registry. WAL mode so a
    reader never blocks the poller's writes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit; we BEGIN explicitly
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def player_id_for(platform: str, external_id: str) -> str:
    """The canonical Construct player id for a transport identity — the key
    `Session.open(..., player_id=)` isolates a private `.world` slot by."""
    return f"{platform}:{external_id}"


def mint_invite(conn: sqlite3.Connection, platform: str, scenario: str, *,
                now: float, ttl_seconds: int = INVITE_TTL_SECONDS) -> str:
    """Create a single-use, platform-locked, time-boxed invite; return its
    code. The code is a long random bearer token — `CONS-<base32>`."""
    code = "CONS-" + secrets.token_hex(_CODE_BYTES).upper()
    conn.execute(
        "INSERT INTO invites (code, platform, scenario, status, expires_at) "
        "VALUES (?, ?, ?, 'open', ?)",
        (code, platform, scenario, now + ttl_seconds))
    return code


def claim_invite(conn: sqlite3.Connection, code: str, platform: str,
                 external_id: str, *, now: float) -> str | None:
    """Atomically claim `code` for (platform, external_id). Returns the
    player_id on success, else None (expired / wrong-platform / already
    claimed / unknown — the caller surfaces ONE uniform rejection, never the
    reason, to avoid leaking invite state).

    Idempotent for an already-mapped player: if this identity already has a
    mapping, return it WITHOUT consuming another invite or switching scenario.
    The platform is supplied by the adapter (never trusted from the message),
    so a Telegram code can only be claimed over Telegram."""
    existing = player_for(conn, platform, external_id)
    if existing is not None:
        return existing
    pid = player_id_for(platform, external_id)
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "UPDATE invites SET status='claimed', claimed_by=? "
            "WHERE code=? AND platform=? AND status='open' "
            "AND claimed_by IS NULL AND ? < expires_at",
            (pid, code, platform, now))
        if cur.rowcount != 1:
            conn.execute("ROLLBACK")
            return None
        row = conn.execute("SELECT scenario FROM invites WHERE code=?", (code,)).fetchone()
        conn.execute(
            "INSERT INTO players (platform, external_id, player_id, scenario, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (platform, external_id, pid, row["scenario"], now))
        conn.execute("COMMIT")
        return pid
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def player_for(conn: sqlite3.Connection, platform: str, external_id: str) -> str | None:
    row = conn.execute(
        "SELECT player_id FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    return row["player_id"] if row else None


def scenario_for(conn: sqlite3.Connection, platform: str, external_id: str) -> str | None:
    """The scenario this player's invite granted — `/play` is locked to it."""
    row = conn.execute(
        "SELECT scenario FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    return row["scenario"] if row else None


# ---- exactly-once delivery bookkeeping (Telegram poller) ------------------

def get_offset(conn: sqlite3.Connection, platform: str) -> int:
    row = conn.execute(
        "SELECT next_offset FROM offsets WHERE platform=?", (platform,)).fetchone()
    return int(row["next_offset"]) if row else 0


def set_offset(conn: sqlite3.Connection, platform: str, next_offset: int) -> None:
    conn.execute(
        "INSERT INTO offsets (platform, next_offset) VALUES (?, ?) "
        "ON CONFLICT(platform) DO UPDATE SET next_offset=excluded.next_offset",
        (platform, next_offset))


def claim_update(conn: sqlite3.Connection, platform: str, update_id: int) -> bool:
    """Record an update as being processed. Returns True if this is the FIRST
    time (the caller should run the turn); False if already seen (skip — a
    redelivery after a restart must not re-run `Session.turn()`)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO processed (platform, update_id) VALUES (?, ?)",
        (platform, update_id))
    return cur.rowcount == 1


def record_outbox(conn: sqlite3.Connection, platform: str, update_id: int,
                  chat_id: str, chunks: list[str]) -> None:
    """Persist a completed turn's reply chunks BEFORE sending, so a send
    failure/crash retries the SEND, never the turn."""
    conn.executemany(
        "INSERT OR IGNORE INTO outbox (platform, update_id, seq, chat_id, text, sent) "
        "VALUES (?, ?, ?, ?, ?, 0)",
        [(platform, update_id, seq, chat_id, text)
         for seq, text in enumerate(chunks)])


def pending_outbox(conn: sqlite3.Connection, platform: str) -> list[sqlite3.Row]:
    """Unsent reply chunks (a restart resumes sending these)."""
    return conn.execute(
        "SELECT update_id, seq, chat_id, text FROM outbox "
        "WHERE platform=? AND sent=0 ORDER BY update_id, seq", (platform,)).fetchall()


def mark_sent(conn: sqlite3.Connection, platform: str, update_id: int, seq: int) -> None:
    conn.execute(
        "UPDATE outbox SET sent=1 WHERE platform=? AND update_id=? AND seq=?",
        (platform, update_id, seq))


def interrupted_updates(conn: sqlite3.Connection, platform: str) -> list[int]:
    """Updates marked processed that produced NO outbox reply — i.e. a crash
    struck between claiming the update and recording its reply (mid-turn). Every
    handled event records ≥1 chunk, so an empty outbox here means the turn never
    completed. These are surfaced LOUDLY (not silently skipped); they are not
    re-run, since `Session.turn` already mutated the slot and is not idempotent —
    at-most-once on a mid-turn crash, by design, the player simply retries."""
    rows = conn.execute(
        "SELECT update_id FROM processed p WHERE platform=? AND NOT EXISTS "
        "(SELECT 1 FROM outbox o WHERE o.platform=p.platform AND o.update_id=p.update_id)",
        (platform,)).fetchall()
    return [r["update_id"] for r in rows]
