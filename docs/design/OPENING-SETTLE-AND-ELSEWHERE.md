# The opening's settle and the "not here" line (R20 criterion 5)

Status: **spec r3, cr GREEN; built on `fix/opening-settle-elsewhere`, for code review.** r2 was RED on one point: "here" was defined by shared ancestry, and r3 makes it directional. r1 was RED (cr, <1c53e718>). There were two corrections:
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

**Where it is computed.** In `run_turn`, beside the scene-line loop that builds `_here`. An emission rests only on `player_snap`, the player-frame snapshot already read for the briefing. The scene's ancestor chain, used only to suppress, comes from the containment read the turn already makes for the scene (no new engine read, if one exists there; otherwise one bounded `part_of` walk).

**What fires it: `known_elsewhere`, from the player frame alone.** The existing `_here` set is NOT used to decide absence: it calls `_present()`, which consults canon (`canon_table` / `p.locate()`). A "not here" decided by `_here` would leak a negative whereabouts fact (cr r1 P1).

An entity E is known elsewhere when all of these hold:
- E is not `person:*`, because people keep their own path.
- E's display name or any alias from `player_snap` appears in the player's line. The match is case-insensitive and whole-word. Aliases shorter than 3 characters do not count, and deixis does not count (`is_deixis`).
- **E's known path** is walked upward from E through its player-frame `in` and `part_of` rows, at most 4 hops and cycle-safe. Its **nearest place** is the first `place:*` on that path.
- **The here-set** is the current scene, the YOU ARE AT place the briefing already names (the player is always shown where they stand, so it reveals nothing), together with the scene's features contained by it.
- **Directional, not shared-ancestor (cr r2 P1).** E is known-here when its path reaches a node of the here-set. A shared ancestor proves nothing: a cell and a warrant room that are both `part_of` the fortress are siblings, not one place.
- **Known elsewhere, emitted:** E is not known-here, and its nearest place is a distinct location. It is neither in the here-set nor an ancestor of the scene.
- **Underdetermined, no line:** E's nearest place is an ancestor of the scene. For example, the sack is known only to be "in Ironhold" while the player stands in a room of Ironhold. The player frame has not shown it is somewhere else.

**Canon may only suppress.** Emitting a line rests on the player frame alone: E's path and its nearest place. Canon may only *suppress* a line. The scene's features (`scene_features`) and the scene's ancestor chain are read as `_here` reads them today, and they are used only to find known-here or underdetermined cases. A suppression asserts nothing to the narrator, so it leaks nothing.

With no player-frame `in` evidence for E, **no line is emitted**. Nothing canon alone holds can produce a line, so the line never asserts an absence the player has not learned.

**The place.** The place in the line is E's nearest place on its known path, the warrant room in run 7, given by display name.

**The briefing block.** At most 4 entities, in the order they are named. It is emitted only for entities that pass `known_elsewhere`. The block:

> NAMED BUT NOT HERE (binding): the player named <name>, which is not in this place: it is in <place>. Render that honestly. Someone present may fetch or carry it if that is plausible and they are willing. If it is in sight from here, the player may look across at it. Otherwise the room answers with its absence. Never place it here, and never move this scene to it.

The block goes beside CALLED FOR SOMEONE NOT HERE in `build_briefing`, through a new `BriefingInputs` field.

**Telemetry.** `TurnTrace.named_elsewhere: list[str]`, holding `"<entity> · <nearest place>"`, and a line in the mechanics log. The turntrace golden is regenerated; its only diff is the new key.

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

## Found while building (after the r3 GREEN; for the code review)

1. **The labels come from one bounded player-frame read, not from `player_snap`.** `player_snap` covers only the arc's scope. A thing the opening or play grew (the hearth) is never in it, so a `player_snap`-only Part A could not fire in run 7. The read is still the player frame only (`frame_facts` on `knows:<protagonist>`), so the secrecy rule is unchanged.
2. **A prose-read object matches by its own words.** In run 7 the sack carried no name or alias, only `kind "object"`, and the player said "the sack". So the labels are:
   - names and aliases;
   - a non-generic kind;
   - the id's own words (`obj:torn_laundry_sack` gives "torn laundry sack", and its head noun "sack").

   **A label that names more than one entity names none**, so an ambiguous word asserts nothing.
3. **Places get their own line** (cr RED on `cdf79d0`). The build had left places out, but movement sees only a classified move. A question about a remote room ("what happened in the warrant room?") would reach the narrator with nothing saying the room is elsewhere.
   - A named place is here when it is the scene, one of the scene's features, or an ancestor of the scene.
   - Otherwise the line reads: "<label>, a different place from where they stand (it lies within <its player-known parent>). Unless they travel there, render it from here … never as the room around them."
   - A place matches only by its name, alias or full id words, never by its head noun or kind. "The room" must not name the warrant room.
4. **The carried case is here.** The here-set includes the protagonist, so a thing in the player's hands is never "not here".
5. **The place's display name is player-frame too.** It is the player-frame `name`, else the id's own words, never canon's name.
6. **Part B's turn stamp.** `settle_opening` stamps positional rows at the last turn already played: 0 at a fresh start, later for a resumed session's re-entry opening. The session's existing deferred-settle slot carries it, so the transport's post-send flush runs it and `turn()` joins it.

## Tests

**Part A:**
- the line fires for an object the player frame places elsewhere and the player names;
- no line when the object's path reaches the here-set: it is on a table here, or in a feature contained by this room (the directed descendant case);
- **sibling rooms**: cell and warrant room are both `part_of` Ironhold, and the player frame places the sack in the warrant room. "sack" gives NAMED BUT NOT HERE, warrant room;
- coarse ancestor: the player frame places the object only "in" Ironhold while the player is in the cell. No line is emitted;
- no line when the player frame lacks the object;
- no line when the player frame lacks the object's `in` row;
- the line still fires when the player frame lacks the protagonist's `in` row (the scene anchors the player's chain);
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
