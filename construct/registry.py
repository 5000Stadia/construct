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
    started     INTEGER NOT NULL DEFAULT 0,
    mode        TEXT,                            -- player's chosen experience: win_loss | endless
    creation    TEXT,                            -- JSON: the in-progress Construct-dialogue brief (Atrium)
    chargen     TEXT,                            -- JSON: the in-progress character sheet (the Foyer)
    character   TEXT,                            -- JSON: the LAST completed character sheet (for /restart "keep")
    status_pin  INTEGER NOT NULL DEFAULT 1,      -- show the time|location header atop each reply
    last_status TEXT,                            -- last time|location header SHOWN (header appears only on change)
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
CREATE TABLE IF NOT EXISTS notes (
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    scenario    TEXT NOT NULL,
    seq         INTEGER NOT NULL,            -- per (player, scenario), 1-based
    text        TEXT NOT NULL,
    context     TEXT,                        -- captured status line (time|place) at write
    created_at  REAL NOT NULL,
    PRIMARY KEY (platform, external_id, scenario, seq)
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
    # Idempotent migrations for registries created before these columns existed.
    for ddl in (
        "ALTER TABLE players ADD COLUMN started INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN mode TEXT",
        "ALTER TABLE players ADD COLUMN creation TEXT",
        "ALTER TABLE players ADD COLUMN chargen TEXT",
        "ALTER TABLE players ADD COLUMN character TEXT",
        "ALTER TABLE players ADD COLUMN status_pin INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE players ADD COLUMN last_status TEXT",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already present
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


def forget_player(conn: sqlite3.Connection, platform: str, external_id: str) -> None:
    """Delete a player's mapping entirely — they become an UNCLAIMED sender again
    (needs a fresh invite to return). For an operator self-wipe to replay the
    brand-new-user flow. Leaves invites/offsets/outbox alone."""
    conn.execute("DELETE FROM players WHERE platform=? AND external_id=?",
                 (platform, external_id))


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


def is_started(conn: sqlite3.Connection, platform: str, external_id: str) -> bool:
    """Has this player begun play (seen the cold open) at least once? Lets the
    transport show the opening on a brand-new player's first prose, then continue
    (auto-resume) ever after — no /play command needed."""
    row = conn.execute(
        "SELECT started FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    return bool(row and row["started"])


def mark_started(conn: sqlite3.Connection, platform: str, external_id: str) -> None:
    conn.execute("UPDATE players SET started=1 WHERE platform=? AND external_id=?",
                 (platform, external_id))


def get_mode(conn: sqlite3.Connection, platform: str, external_id: str) -> str | None:
    """The player's chosen experience ("win_loss" | "endless"), set at the
    session-zero mode interview on first contact. None until they answer."""
    row = conn.execute(
        "SELECT mode FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    return row["mode"] if row and row["mode"] else None


def set_mode(conn: sqlite3.Connection, platform: str, external_id: str, mode: str) -> None:
    conn.execute("UPDATE players SET mode=? WHERE platform=? AND external_id=?",
                 (mode, platform, external_id))


def set_scenario(conn: sqlite3.Connection, platform: str, external_id: str,
                 scenario: str) -> None:
    """Repoint a player at a scenario they now own — e.g. after the Construct
    dialogue BUILDS them a fresh world, so `scenario_for` (resume) finds it."""
    conn.execute("UPDATE players SET scenario=? WHERE platform=? AND external_id=?",
                 (scenario, platform, external_id))


def get_creation(conn: sqlite3.Connection, platform: str, external_id: str) -> dict | None:
    """The in-progress Construct-dialogue state (the Atrium brief + history),
    or None if the player isn't mid-creation. JSON blob, host-side only."""
    import json
    row = conn.execute(
        "SELECT creation FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    if not (row and row["creation"]):
        return None
    try:
        return json.loads(row["creation"])
    except (ValueError, TypeError):
        return None  # corrupt blob → start the dialogue fresh (fail-open)


def set_creation(conn: sqlite3.Connection, platform: str, external_id: str,
                 blob: dict) -> None:
    import json
    conn.execute("UPDATE players SET creation=? WHERE platform=? AND external_id=?",
                 (json.dumps(blob), platform, external_id))


def clear_creation(conn: sqlite3.Connection, platform: str, external_id: str) -> None:
    """Drop the Atrium state once a world has been built/loaded (or to restart)."""
    conn.execute("UPDATE players SET creation=NULL WHERE platform=? AND external_id=?",
                 (platform, external_id))


def get_chargen(conn: sqlite3.Connection, platform: str, external_id: str) -> dict | None:
    """The in-progress Foyer character sheet + history, or None if not mid-Foyer."""
    import json
    row = conn.execute(
        "SELECT chargen FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    if not (row and row["chargen"]):
        return None
    try:
        return json.loads(row["chargen"])
    except (ValueError, TypeError):
        return None


def set_chargen(conn: sqlite3.Connection, platform: str, external_id: str,
                blob: dict) -> None:
    import json
    conn.execute("UPDATE players SET chargen=? WHERE platform=? AND external_id=?",
                 (json.dumps(blob), platform, external_id))


def clear_chargen(conn: sqlite3.Connection, platform: str, external_id: str) -> None:
    """Drop the Foyer state once the character is ingested and the story begins."""
    conn.execute("UPDATE players SET chargen=NULL WHERE platform=? AND external_id=?",
                 (platform, external_id))


def get_character(conn: sqlite3.Connection, platform: str, external_id: str) -> dict | None:
    """The LAST completed character sheet (saved when the Foyer finished), so a
    `/restart` "keep my character" can re-apply it without re-running the interview.
    None if the player has never finished the Foyer."""
    import json
    row = conn.execute(
        "SELECT character FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    if not (row and row["character"]):
        return None
    try:
        return json.loads(row["character"])
    except (ValueError, TypeError):
        return None


def set_character(conn: sqlite3.Connection, platform: str, external_id: str,
                  sheet: dict) -> None:
    """Persist the completed character sheet durably (survives a slot wipe)."""
    import json
    conn.execute("UPDATE players SET character=? WHERE platform=? AND external_id=?",
                 (json.dumps(sheet), platform, external_id))


# ---- player notes (`/note` / `/notes`) — player annotations, never PB canon ----

def add_note(conn: sqlite3.Connection, platform: str, external_id: str,
             scenario: str, text: str, context: str | None, now: float) -> int:
    """Append a player note for this player+scenario; returns its 1-based seq.
    Transactional (BEGIN IMMEDIATE + COALESCE(MAX(seq),0)+1) — matches the registry's
    atomic style so a second transport can't collide on seq."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM notes "
            "WHERE platform=? AND external_id=? AND scenario=?",
            (platform, external_id, scenario)).fetchone()
        seq = int(row["n"])
        conn.execute(
            "INSERT INTO notes (platform, external_id, scenario, seq, text, context, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (platform, external_id, scenario, seq, text, context, now))
        conn.execute("COMMIT")
        return seq
    except Exception:
        conn.execute("ROLLBACK")
        raise


def list_notes(conn: sqlite3.Connection, platform: str, external_id: str,
               scenario: str) -> list[dict]:
    """This player's notes for ONE scenario, oldest→newest. Scoped to the scenario
    (= the playthrough/series): notes carry across EPISODES of the same scenario
    (continue → episode two plays over the same world) but NOT to a different
    adventure (founder)."""
    rows = conn.execute(
        "SELECT scenario, seq, text, context, created_at FROM notes "
        "WHERE platform=? AND external_id=? AND scenario=? ORDER BY created_at, rowid",
        (platform, external_id, scenario)).fetchall()
    return [{"scenario": r["scenario"], "seq": r["seq"], "text": r["text"],
             "context": r["context"], "created_at": r["created_at"]} for r in rows]


def delete_note(conn: sqlite3.Connection, platform: str, external_id: str,
                scenario: str, position: int) -> dict | None:
    """Delete the `position`-th note (1-based, as listed) for this player+scenario.
    Returns the deleted note dict, or None if the position is out of range."""
    notes = list_notes(conn, platform, external_id, scenario)
    if position < 1 or position > len(notes):
        return None
    n = notes[position - 1]
    conn.execute(
        "DELETE FROM notes WHERE platform=? AND external_id=? AND scenario=? AND seq=?",
        (platform, external_id, n["scenario"], n["seq"]))
    return n


def clear_notes(conn: sqlite3.Connection, platform: str, external_id: str,
                scenario: str | None = None) -> int:
    """Drop notes for this player. `scenario` → just that scenario's notes (a fresh
    factory restart, or `/notes clear`); `None` → ALL the player's notes (a `/wipe`).
    Returns the count cleared."""
    if scenario is None:
        cur = conn.execute(
            "DELETE FROM notes WHERE platform=? AND external_id=?",
            (platform, external_id))
    else:
        cur = conn.execute(
            "DELETE FROM notes WHERE platform=? AND external_id=? AND scenario=?",
            (platform, external_id, scenario))
    return cur.rowcount


def get_status_pin(conn: sqlite3.Connection, platform: str, external_id: str) -> bool:
    """Whether the time|location header rides atop each reply (default ON)."""
    row = conn.execute(
        "SELECT status_pin FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    return True if row is None else bool(row["status_pin"])


def set_status_pin(conn: sqlite3.Connection, platform: str, external_id: str,
                   on: bool) -> None:
    conn.execute("UPDATE players SET status_pin=? WHERE platform=? AND external_id=?",
                 (1 if on else 0, platform, external_id))


def get_last_status(conn: sqlite3.Connection, platform: str, external_id: str) -> str | None:
    """The last `time | location` header actually SHOWN to this player — the
    auto-header rides atop a reply only when the current line DIFFERS from this
    (so it reads as a 'time/place changed' indicator, not wallpaper)."""
    row = conn.execute(
        "SELECT last_status FROM players WHERE platform=? AND external_id=?",
        (platform, external_id)).fetchone()
    return row["last_status"] if row is not None else None


def set_last_status(conn: sqlite3.Connection, platform: str, external_id: str,
                    line: str) -> None:
    conn.execute("UPDATE players SET last_status=? WHERE platform=? AND external_id=?",
                 (line, platform, external_id))


# ---- exit (back to the start menu) ----------------------------------------

def set_started(conn: sqlite3.Connection, platform: str, external_id: str,
                on: bool) -> None:
    """Flip the started flag — `False` sends the player back to the Atrium (exit to
    the start menu) without touching their saved slot (so they can resume later)."""
    conn.execute("UPDATE players SET started=? WHERE platform=? AND external_id=?",
                 (1 if on else 0, platform, external_id))


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
