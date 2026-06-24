# SPEC — Player Notes (`/note`, `/notes`) (v1, for review)

**Status:** SPEC for review (founder + Cx), per the pipeline. A small, self-contained
player-facing feature — independent of the episodic/contract work. Founder ask: *"/note
(note to take for player future reference) /notes returns all notes."*

Seams: `construct/transport_core.py` (command routing, `status_line`), `construct/registry.py`
(durable per-player storage). No engine/PB involvement (notes are player annotations,
**never canon, never narrator-fed** in v1).

---

## 0b. Founder revision (2026-06-20, post-ship) — folded in
- **Notes are per MAIN CHARACTER = per (player, scenario)** (founder: "notes are per main
  character"). A different adventure (different scenario/world/character) starts a CLEAN
  journal; the SAME character into book 2 (episode 2 plays over the same scenario/world)
  CARRIES the notes forward — just as the PB nuance carries (the locket in the drawer).
  `list/clear/delete` key on `(player, scenario)`. (Briefly mis-built per-player-global,
  then reverted on this clarification.)
- **`/del #`** deletes the #-th note as listed; `/notes` footer advertises it.
- **Tasteful emoji** in the notes UI (📝/🗑️/🕂) — "this is kind of a text UI thing 📝".
- **`/restart` asks about notes:** `episode` keeps them silently; `original` (factory-fresh)
  ASKS "keep or wipe?" (skips when none; ambiguous → keep); `/wipe` clears all.
- Implementation kept the table PK as-is; numbering + `/del` are POSITIONAL over
  `list_notes` order (`created_at, rowid`), so no schema migration was needed.

## 1. Behavior

- **`/note <text>`** — append a note for the player's own future reference. Confirms
  briefly (*"Noted. (3 notes — /notes to see them.)"*). Captures lightweight context at
  write time (§3).
- **`/note`** (no text) — usage hint: *"Add a note with `/note <your note>`. `/notes` shows
  them all."* (No multi-step prompt — keep it one-shot, like the other commands.)
- **`/notes`** — return all the player's notes for the current scenario, newest-or-oldest
  order (lean: chronological, oldest→newest, numbered), each with its captured context:
  ```
  Your notes for The Last Honest Meter:
  1. [Day 1, evening · the meter office] the clerk's alibi doesn't hold
  2. [Day 2, dawn · the harbor] Cray was seen near the docks
  ```
  Empty → *"No notes yet — jot one with `/note <your note>`."*
- **`/notes clear`** — drop all the player's notes for this scenario, with a one-line
  confirm. (Cheap; included so a player isn't stuck with stale notes. No per-note delete in
  v1.)

All three are **zero-turn / zero-time** — like `/status` and `/ooc`, they never run a turn,
advance the diegetic clock, or touch the arc. They're handled in the command path before
the turn dispatch.

## 2. Storage

A dedicated `notes` table (matches the project's table style — `invites`/`offsets`/`outbox`),
keyed per-player + per-scenario so notes belong to the playthrough/series:

```sql
CREATE TABLE IF NOT EXISTS notes (
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    scenario    TEXT NOT NULL,
    seq         INTEGER NOT NULL,      -- per (player, scenario), 1-based
    text        TEXT NOT NULL,
    context     TEXT,                  -- captured status line at write time (nullable)
    created_at  REAL NOT NULL,
    PRIMARY KEY (platform, external_id, scenario, seq)
);
```

Registry helpers (mirroring the existing `get_/set_` style):
- `add_note(...) -> int` — **transactional** (`BEGIN IMMEDIATE`; `seq = COALESCE(MAX(seq),0)+1`),
  matching the registry's atomic style so a future second transport can't collide on seq (Cx).
- `list_notes(conn, platform, external_id, scenario) -> list[dict]` (ordered by seq).
- `clear_notes(conn, platform, external_id, scenario) -> int` (returns count cleared).

## 3. Captured context

At `/note` time, capture the player's current **`status_line`** (the `time | location`
string the Session already produces — DIEGETIC-TIME) as `context`, so `/notes` reads like a
dated journal. Best-effort: if no live session / status unavailable, store `context=NULL`
and render the note without a bracket. No model call, no clock advance.

## 4. Persistence semantics

- **Survive `/restart`** (both "episode" and "original") — notes are the *player's own
  memory of the series*, not game state; replaying a story shouldn't wipe what you learned.
  *(Open Q-N1 — founder may prefer "original" to clear them.)*
- **Cleared by `/wipe`** — the operator self-reset wipes all the player's data, including
  notes — delete notes **before** `registry.forget_player()` (Cx) so the rows are gone.
- Scoped per-scenario: switching worlds (`/exit` → Atrium → another world) shows only that
  world's notes. A built/live world's notes follow its scenario name.

## 5. Transport wiring (`transport_core.py`)

**Route in `_command()`, not the top-level `handle()` ladder (Cx).** `handle()` already
sends unknown slash-commands to `_command()`, so no top-level prefix change is needed —
add exact-match parsing there (alongside the other `/` commands):
```
# inside _command(), exact parse so /note never misroutes /notes:
cmd, _, rest = text.partition(" ")
if cmd == "/notes":  return self._notes(pid, ev, rest.strip())   # "" | "clear"
if cmd == "/note":   return self._note(pid, ev, rest.strip())    # text | "" → usage
```
`_note`/`_notes` read the current scenario via `registry.scenario_for`, the context via the
cached session's `status_line()` (guarded), and call the registry helpers. Add `/note`,
`/notes` to HELP.

## 6. Files / tests

- `registry.py`: `notes` table in `_SCHEMA` + idempotent `CREATE TABLE` in `connect` (new
  table, so no `ALTER`); `add_note`/`list_notes`/`clear_notes`.
- `transport_core.py`: `_note`, `_notes`; routing; `_wipe` clears notes; HELP line.
- `tests/test_telegram.py::TestNotes`: add→list round-trip with seq ordering; `/note` empty →
  usage; `/notes` empty → hint; context captured from `status_line`; `/notes clear` empties;
  notes scoped per-scenario (player with notes in A sees none in B); `/note`/`/notes` run no
  turn (session.turns untouched) and don't advance time; `/wipe` drops notes.

## 7. Open questions

- **Q-N1:** Should `/restart → original` (factory-fresh) clear notes, or keep them? (Lean:
  keep — they're the player's memory; `/wipe` is the clear-everything path.)
- **Q-N2:** v1 is player-only retrieval. Later option: optionally surface notes to the
  narrator as soft player-intent (like OOC wishes) — *out of scope for v1*, flag only.
- **Q-N3:** Per-note delete (`/note delete N`)? (Lean: defer; `/notes clear` covers v1.)
