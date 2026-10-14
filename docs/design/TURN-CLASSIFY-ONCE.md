# Classify a turn's new facts once, not per ingest

**Status:** spec r1, 2026-10-13, for cr review. Not built.
**Source:** R20 run 10's timing log (eval/12): the engine's lifetime classifier ("Classify the lifetime") made **109 calls in 20 turns, 566 s in all** (mean 5.2 s), all serial within each turn. Kabe (2026-10-13): literal categorization "can be handled by literally the fastest model in probably a process that can mass group work in a single turn batch". pattern-buffer's guidance: m151ce5.

## The facts

- **`ingest_structured(..., classify="batch")` is one classifier model call per ingest call,** over that call's rows (pattern-buffer, m151ce5). `turnloop.py` passes `classify="batch"` at 21 sites, and a turn makes several ingests (player input, movement, NPC actions, prose extraction, settle rows), so about 5 classifier calls a turn.
- **pattern-buffer already has the turn-scoped deferral:** BUILD-SESSION-V1.
  - `p.begin_build()`, then ingests with the default classify (or `"defer"`), then `p.seal_build(model=True)`: one `classify_rows` pass over the session's rows, which is **one** batched model call.
  - Inside a session, an explicit `classify="batch"` or `"rules"` still classifies locally, so those sites drop the argument.
  - Guardrail rows (names, events, containment) are classified immediately with zero calls even inside a session. Only the ambiguous remainder waits for the seal.
- **The caveat:** until the seal, the session's ambiguous rows have no durability class, and durability decides which row a fold serves. A read inside the session, about a key that got a new non-guardrail row in that session, can serve differently than it will after the seal.

## The rule

Two sessions per turn, each sealed **before** the reads that depend on its rows:

1. **The pre-send session**
   - **Opens** at the start of `run_turn`, after the classify cohort.
   - **Covers** the player-input ingest, movement and growth writes, and NPC-action extraction.
   - **Seals** (`seal_build(model=True)`) immediately before the scene snapshot that feeds the briefing (`cp_scene_snapshot_done`), so the narrator's reads see classified rows.
   - **Writes after the snapshot,** before send, run outside any session with today's `classify="batch"`.
2. **The settle session**
   - **Opens** at the start of the deferred settle (`_settle_prose_facts`).
   - **Covers** prose extraction, promote and memory rows.
   - **Seals** at the settle's end. The settle's own reads of rows it wrote earlier in the same settle are listed in the build note, and each is either sealed-before or shown class-independent.

Expected: about 5 classifier calls a turn become 2.

**Fail-safe.** The pair is `try/finally`: an exception inside a session still seals it (`model=True`), so no row is left unclassified. If `seal_build` itself fails, the rows fall back to the engine's documented default for unsealed rows, and the turn logs it (fail-open, as `_FailOpenIngest` does).

**A trace.** `TurnTrace.timings` gains `seal_presend` and `seal_settle`, and the timing log shows one "Classify the lifetime" call per session.

## Not in scope

- **Effort for the classifier** ("minimal" in place of "low"). This is a separate, measured change: classify a sample of rows from run 10's world at both settings, compare verdicts (a wrong CONSTITUTIVE on a movable object is the costly error), then route the `Classify the lifetime` prefix if they agree.
- **The build path,** which already uses `begin_build`/`seal_build`.

## Tests

1. **Call count.** In a scripted turn with player input, a move, an NPC action and prose, the stub model sees exactly two classifier calls (pre-send and settle), down from today's per-ingest count. Assert both counts.
2. **Reads after the seal.** A turn writes a new, non-guardrail state row (`obj:door · state · open`, superseding `shut`), and the briefing's scene snapshot reads it. The briefing shows `open`, so the seal ran before the snapshot.
3. **Exception safety.** An exception raised inside the pre-send session still seals it, and the rows have classes after the turn.
4. **Guardrails unchanged.** Containment rows written in the session are classified immediately, with zero calls. A move's `in` row is served by the next read inside the session.
5. **The golden.** The turntrace golden moves only by the new timing keys and the classifier call counts, explained in the build note.
6. **The full suite.**
