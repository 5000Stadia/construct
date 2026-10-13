# The opening's settle and the "not here" line (R20 criterion 5)

Status: **spec r1, for cr review. Not built.**

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

**What fires it.** An entity E fires the line when all of these hold:
- E is in `player_snap`;
- E is not in `_here`;
- E is not `person:*` (people keep their own path);
- E's display name or any alias from `player_snap` appears in the player's line. The match is case-insensitive and whole-word. Aliases shorter than 3 characters do not count, and deixis does not count (`is_deixis`).

**The place.** The place comes from E's `in` row in `player_snap` (the player frame), resolved to a display name. If the player frame has no `in` row for E, the line says "not here" and gives no place. It never reads canon whereabouts the player has not learned. This is the same presence-truth rule as the discovery gating of the irony delta.

**The briefing block.** At most 4 entities, in the order they are named. The block:

> NAMED BUT NOT HERE (binding): the player named <name>, which is not in this place: it is in <place>. Render that honestly. Someone present may fetch or carry it if that is plausible and they are willing. If it is in sight from here, the player may look across at it. Otherwise the room answers with its absence. Never place it here, and never move this scene to it.

The block goes beside CALLED FOR SOMEONE NOT HERE in `build_briefing`, through a new `BriefingInputs` field.

**Telemetry.** `TurnTrace.named_elsewhere: list[str]`, holding `"<entity> · <place or ->"`, and a line in the mechanics log. The turntrace golden is regenerated; its only diff is the new key.

**A fetch, if the prose has one.** It is recorded the way run 7 recorded the sack (post_extract `in` row, then promote). That path is unchanged.

## Part B: the opening's settle (gap 1)

After the opening is rendered, its prose goes through the same settle tail a turn's prose does: extract, resolve, stage, promote, and the player-frame mirror. It runs as "turn 0", with `scene` set to the opening place. The tail is joined before turn 1 reads, as a turn's deferred settle is today (`Session._flush_settle`). The player reads the opening while it runs, so the opening feels no slower.

**How, two options for cr:**

1. **(Recommended.) Factor the extract-to-promote part of `_settle` into a module function.** Its inputs are explicit: `world`, `arc`, `prose`, `scene`, `turn`, the present set, `canon_table`/`live_reads`, the horizon, and `trace`. `_settle` calls it, and so does the session after the opening.
   - What stays in `_settle`: the turn-only parts (transcript append, memory compaction, the clock advance, the cast-moves lane's engaged-this-turn rule).
   - Golden: the turn's golden must stay byte-identical, which proves the factor is behaviour-free.
2. **A `run_turn` mode that takes prose instead of narrating.** It is smaller to write, but `run_turn` gains a second personality. I do not recommend it.

**What the opening's settle must not do.** It must not advance the clock, append a transcript turn, count as a turn for the arc, or run the cast-moves lane. Opening prose stages the cast; it does not move them.

**The risk to test.** The extractor might place a distant vista in the opening scene, putting the hearth `in` the cell. That would make the failure worse. The resolver places by the prose, as it does every turn. The test pins this case with a recorded extraction: the run 7 opening's rows, replayed through a stub provider, must put the hearth and the sack in the warrant room, not the cell.

**Fail-open.** If extraction fails, the opening stays shown, a warning is logged, the failure is recorded on the session's opening trace, and turn 1 proceeds as today.

## Tests

**Part A:**
- the line fires for an object the player frame places elsewhere and the player names;
- no line when the object is here;
- no line when the player frame lacks the object;
- no place when the player frame lacks its `in` row;
- people excluded;
- the 4 cap;
- whole-word matching ("sack" does not match "ransacked");
- no canon read: a canon-only `in` row gives no place.

**Part B:**
- the factor keeps the turntrace golden byte-identical;
- the opening's rows reach `proposed:main`, then canon and `knows:<protagonist>`;
- no clock advance, no transcript turn, no cast move;
- fail-open on extractor error;
- the run 7 replay places the hearth and the sack in the warrant room.

**Together:** a two-step test. With the run 7 opening settled, the turn-1 briefing for "Let me see the sack and the hearth" carries NAMED BUT NOT HERE for both.

## Out of scope

- Run 7's other findings: question-as-fact, and chapter-2 object permanence.
- Any change to the location filter itself.
- A run 8. It costs Codex time and waits for its own say-so.
