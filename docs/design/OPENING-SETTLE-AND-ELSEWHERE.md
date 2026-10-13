# The opening's settle and the "not here" line (R20 criterion 5)

Status: **spec r2, for cr review. Not built.** r1 was RED (cr, <1c53e718>). There were two corrections:
1. Part A's "not here" must be decided from the player frame alone.
2. Part B's settle must run exactly once and leave no hidden-turn artifacts.

r2 takes both, and answers (a)–(c) as cr ruled.

Source: R20 run 7, criterion 5, traced on paper in `eval/12-displaced-ironhold-acceptance.md` ("Criterion 5 traced").

## The failure

1. The opening showed the player, from their cell, a torn sack by a hearth in the warrant room ("past Dena's shoulder, through the open angle").
2. The player's first line asked to see "the sack and the hearth".
3. The narrator brought both into the cell. Canon then followed the prose.
4. The critic, reading the opening, flagged a WHERE breaker.

Two construct gaps let this happen. Both had to be open for it to happen.

- **Gap 1: the opening's prose is never read into canon.** `Session._opening_narration` renders and returns it. Only `run_turn`'s deferred `_settle` extracts prose: it extracts, resolves, stages to `proposed:main`, promotes, and mirrors into `knows:<protagonist>`. So nothing the opening shows exists anywhere: not the hearth, not the sightline, and not the player's view of the sack (only canon held the sack's place, from the build). This is first-mention permanence missing at the one render that is not a turn, the same class as the ch2-opening ghost hook.
- **Gap 2: a named thing that is elsewhere gets no line.** The briefing's location filter (`_here`) keeps elsewhere entities out of THE SCENE RIGHT NOW. That is correct: it is the "tape followed us everywhere" fix. But when the player's line names one of them, the narrator is told nothing about it, and "The scene is HERE and only here" pulls it into the room. People already have the honest beat for this case: CALLED FOR SOMEONE NOT HERE, in `briefing.py`. Objects and places have none.

## Part A: the "not here" line (gap 2)

**Where it is computed.** In `run_turn`, beside the scene-line loop that builds `_here`. It reads only `player_snap`, the player-frame snapshot already read for the briefing. There are no new engine reads.

**What fires it: `known_elsewhere`, from the player frame alone.** The existing `_here` set is NOT used to decide absence: it calls `_present()`, which consults canon (`canon_table` / `p.locate()`). A "not here" decided by `_here` would leak a negative whereabouts fact (cr r1 P1). The predicate reads only `player_snap`.

An entity E is known elsewhere when all of these hold:
- E is not `person:*`, because people keep their own path.
- E's display name or any alias from `player_snap` appears in the player's line. The match is case-insensitive and whole-word. Aliases shorter than 3 characters do not count, and deixis does not count (`is_deixis`).
- **E's known chain** reaches a place. Follow E's player-frame `in` and `part_of` rows (at most 4 hops, no cycles); the chain must end at a `place:*`.
- **The player's known chain** is the same walk from the protagonist's player-frame `in`, together with the scene's player-frame `part_of` features.
- The two chains share no entity. If E's chain ends anywhere in the player's chain, E is here (on a table in this room, in this room's alcove).

With no player-frame `in` evidence for E, or none for the protagonist, **no line is emitted**. The predicate never reads canon, so it never asserts an absence the player has not learned.

**The place.** The place in the line is the `place:*` that ends E's known chain, given by display name.

**The briefing block.** At most 4 entities, in the order they are named. It is emitted only for entities that pass `known_elsewhere`. The block:

> NAMED BUT NOT HERE (binding): the player named <name>, which is not in this place: it is in <place>. Render that honestly. Someone present may fetch or carry it if that is plausible and they are willing. If it is in sight from here, the player may look across at it. Otherwise the room answers with its absence. Never place it here, and never move this scene to it.

The block goes beside CALLED FOR SOMEONE NOT HERE in `build_briefing`, through a new `BriefingInputs` field.

**Telemetry.** `TurnTrace.named_elsewhere: list[str]`, holding `"<entity> · <place or ->"`, and a line in the mechanics log. The turntrace golden is regenerated; its only diff is the new key.

**A fetch, if the prose has one.** It is recorded the way run 7 recorded the sack (post_extract `in` row, then promote). That path is unchanged.

## Part B: the opening's settle (gap 1)

After the opening is rendered, its prose goes through the same settle tail a turn's prose does: extract, resolve, stage, promote, and the player-frame mirror. It runs as "turn 0", with `scene` set to the opening place. The tail is joined before turn 1 reads, as a turn's deferred settle is today (`Session._flush_settle`). The player reads the opening while it runs, so the opening feels no slower.

**How (decided at r1 review: the factor).** The narrow extract-to-promote pipeline in `_settle` becomes a module function: extract, frame partition, containment canonicalising, name reconstruction, resolve, stage to `proposed:main`, quarantine, promote, and the player-frame mirror. Its inputs are explicit: `world`, `arc`, `prose`, `scene`, the present set, `canon_table`/`live_reads`, the horizon, and a trace-like recorder. `_settle` calls it for a turn, and the session calls it once after the opening. The turntrace golden stays byte-identical, which proves the factor changes nothing. There is no `run_turn` prose mode, which would invite the turn effects listed below.

**Exactly once (cr r1 P1).** `opening_parts()` / `opening()` can be called more than once today.
- The session caches the rendered opening on first render; later calls return the cached text and render nothing.
- The settle for that prose is scheduled exactly once, guarded by a session flag set when it is scheduled, not when it finishes.
- `Session.turn` joins it before any turn-1 read, as `_flush_settle` joins a turn's settle today.
- A regression calls the opening twice and asserts one extract, one promote and one mirror.

**No hidden turn (cr r1).** The opening's settle runs the fact pipeline only. It writes none of these:
- an `event:turn_0` narrator-promote or concealment-audit handoff (`event:turn_0` already denotes the built entry state, and turn 1's readers use turn-0 slots);
- a transcript append;
- compact memory;
- a time advance;
- last-seen or world-tick rows;
- a cast-move lane run (opening prose stages the cast; it does not move them);
- turn-integrity or archive rows.

Its diagnostics are an in-memory opening trace on the session, plus logs.

**The risk, and what the test does and does not cover.** The extractor might place a distant vista in the opening scene, putting the hearth `in` the cell. That would make the failure worse. A recorded-extraction replay (the run 7 opening's rows, through a stub provider) proves that the pipeline keeps a correct payload correct: the raw rows say warrant room, and the promoted rows preserve it. **It cannot stop a fresh model extraction from asserting the hearth in the cell.** That residual risk stands. Removing it would need a separate extraction or placement policy, which is out of scope here; the next probe run's opening rows are where it would show.

**Fail-open.** If extraction fails, the opening stays shown, a warning is logged, the failure is recorded on the in-memory opening trace, and turn 1 proceeds as today.

## Tests

**Part A:**
- the line fires for an object the player frame places elsewhere and the player names;
- no line when the object's known chain ends in the player's chain (on a table here; in this room's feature);
- no line when the player frame lacks the object;
- no line when the player frame lacks the object's `in` row;
- no line when the player frame lacks the protagonist's `in` row;
- **canon-only placement emits no NAMED BUT NOT HERE block at all**: the object is placed elsewhere in canon and the player frame has no `in` for it;
- `_here` is not consulted: canon says "not colocated", but the player frame puts it here, and no line is emitted;
- people excluded;
- the 4 cap;
- whole-word matching ("sack" does not match "ransacked");
- the hop cap and a cycle in `in`/`part_of` terminate.

**Part B:**
- the factor keeps the turntrace golden byte-identical (non-regression only; it does not replace the tests below);
- the opening's rows reach `proposed:main`, then canon and `knows:<protagonist>`;
- **once only**: `opening()` called twice gives one render, one extract, one promote and one mirror;
- turn 1 joins the opening's settle before its first read;
- **no hidden turn**: after the opening's settle, none of these is written:
  - an `event:turn_0` narrator-promote or audit row,
  - a transcript entry,
  - compacted memory,
  - a clock change,
  - last-seen or world-tick rows,
  - a cast move,
  - turn-integrity or archive rows;
- fail-open on extractor error, with the failure on the in-memory opening trace;
- the run 7 replay: the raw rows say warrant room, and the promoted rows keep it (pipeline preservation only; see the residual risk above).

**Together:** a two-step test. With the run 7 opening settled, the turn-1 briefing for "Let me see the sack and the hearth" carries NAMED BUT NOT HERE for both.

## Out of scope

- Run 7's other findings: question-as-fact, and chapter-2 object permanence.
- Any change to the location filter itself.
- A run 8. It costs Codex time and waits for its own say-so.
