# The walk-away as a declared decision (R40)

**Status:** spec r2, 2026-10-13, for cr review. Not built. It replaces CHAPTER-BRIDGE-B1 change 1, which was never built.

**r2 (cr RED on r1):** the event detector is the wrong carrier.
- `clock_pass` (turnloop.py:5714) runs before it (6248-6285), so a confirmation couldn't fire the refusal clock the same turn.
- It runs only on successful `action` turns, so an `exit`, an answerable `question` (4594-4611) or a denied pure-mode declaration (4631-4645) returns before it.
- r1's record had no durable schema.

r2 carries both signals on **classify** instead. Classify already runs on every turn, before every early return and before `clock_pass`, so it adds no model call. A single typed session record holds the lifecycle.
**Source:**
- IR-16 ("abandonment is never inferred; it requires a stated or clarified decision"), IR-21/22 (the limits on asking) and IR-15 (unaware is computed), from Kabe's intent ruleset (`INTENT-RULESET.md`).
- Kabe's note n54b973: "A player thinking to go ask Reginald one last question before the final showdown shouldn't accidentally be seen as abandonment."
- The founder's walk-away ending (2026-06-23).

## The facts

- **Every generated arc's refusal clock** fires on `Occurred("event:abandoned[_<arc>]")` (arc/build.py:144-149; arc/io.py:381-389). **Nothing writes that event,** so the walk-away ending is unreachable today.
- **The constrained event detector** (`_fire_event_occurs`) already judges which candidate events the player's resolved action committed. It writes `event:<kind>_<turn>`, with `agent` and `caused_by` rows.
- **CHAPTER-BRIDGE-B1** (merged) writes `outcome_category = abandoned` when the refusal clock fired, and chapter 2 answers it.
- **The founder's "endless flight" case** (the player keeps escaping) already concludes through the world's own clocks: `failure_when`, D2 missed moments, a quiet-failure close. That is the ruleset's "a refusal lapses into consequence" (IR-26). **It needs no walk-away inference, and R40 doesn't touch it.**

## The rule

**1. Only a thread the player knows can be walked away from** (IR-15). R40 applies to the MAIN arc only: the player was given its aim (the opening and `goal_statement`). A side arc the player may never have heard of keeps lapsing on its own clocks, as today.

**2. Two classify fields, read on every turn.** CLASSIFY_SCHEMA gains:
- `declares_giving_up` (boolean): "true ONLY when the player DECLARES their character is giving up {aim} for good: walking away from it. Going somewhere, doing something else first, resting, or asking one more question is NOT giving up." The aim (the scenario's `goal_statement`, else the main arc's tension label) is put into the classify prompt **only while the walk-away is eligible** (rule 4).
- `confirms_walkaway` (boolean): set only while a question stands. The prompt gets a note: "A QUESTION IS STANDING: whether the player is truly giving up {aim}. true ONLY for an explicit yes. A no, a deflection, another action, a question or silence is false."

Missing counts as false.

**3. The transition runs right after classify,** before every early return (`exit`, `question`, the pure-mode declaration denial) and before `clock_pass`. It's one deterministic step, `_walkaway_transition`, over the record in rule 4:
- **A question stands** (`status == asked`, in this episode):
  - `confirms_walkaway` true: write `event:abandoned_main_<turn>`, with `kind` = the main refusal clock's kind (`event:abandoned`), `agent` = the protagonist, `caused_by` = the turn's action anchor, in canon at `turn_time(turn)`. Set the record to `confirmed`. Because this lands **before** `clock_pass`, the refusal clock fires **this** turn, exactly once (it's `status=fired` afterwards, as for any non-repeat clock).
  - **Anything else, on whatever path** (no, deflection, a question, a denied declaration, `exit`, a failed action): set the record to `declined`, with `declined_minutes` = now. This is the literal reading (IR-22).
- **No question stands, the walk-away is eligible, and `declares_giving_up` is true:** set the record to `asked`, with `asked_turn` and `asked_minutes`. That turn's briefing carries the question directive (rule 5). Nothing else is written; it's never an ending.
- **Otherwise:** nothing.

**4. One typed session record, horizon-read, episode-scoped.** `session:walkaway` · `record` is a JSON literal, written latest-wins at `turn_time(turn)` in the session frame and read through the session's horizon view:
- **Fields:** `{status: "asked"|"declined"|"confirmed", arc_id, asked_turn, asked_minutes, declined_minutes, episode_since}`. `episode_since` is `_episode_since(reads)` (turnloop.py:3983) at write time; None for a first chapter.
- **A record from another episode is no record:** its `episode_since` differs from the current `_episode_since`. A continued chapter starts clean, and an old question or decline can neither be confirmed nor suppress.
- **Time** is `time:elapsed.elapsed_minutes` (`read_clock(world).minutes`), the diegetic clock, never a display time.
- **Eligible means all of these:**
  - the main arc's refusal clock is armed;
  - no record in this episode, or the record is `declined` **and** `minutes_now - declined_minutes >= 1440` (offered again at exactly 1,440; not at 1,439);
  - and the record isn't `confirmed`.
- **A world without a diegetic clock** (`minutes_now` None): a declined record suppresses for the rest of the episode. That fails closed: never re-ask without a clock.

**5. The question is asked in the story, once, with the stakes plain.** On the `asked` turn, the briefing carries:

> THE PLAYER MAY BE WALKING AWAY from {aim}. Make what they would leave behind concrete and immediate, and let a present character, or the scene itself if no one is there, ask plainly whether they are truly done with it. Never decide for them, and never block them.

The form is a fixed, medium-tempo in-world beat. Tempo-selected forms come with R46.

**6. Nothing else infers abandonment:** no movement, distance, idle time or turn count. `_walkaway_transition`'s confirm branch is the **sole** writer of `event:abandoned*`. The refusal clock's counter guard stays.

## Not in scope

- **Walk-away questions for side arcs.** Side arcs lapse.
- **The tempo-selected form** (R46).
- **A private-channel answer** (R41).
- **Recording the walk-away as an intent-frame stance** (R41/R44). The `session:walkaway` record is the minimal state until the intent frame exists.

## Tests

1. **Declaring asks, never ends:** `declares_giving_up` on turn 5 makes the record `asked` (`asked_turn` 5, `asked_minutes` m). There's no `event:abandoned*`, and the refusal clock hasn't fired. The turn-5 briefing carries the question.
2. **An explicit yes ends it, the same turn:** `confirms_walkaway` on turn 6 writes `event:abandoned_main_6` with kind `event:abandoned`. The refusal clock fires **on turn 6, exactly once**: one firing event, one `refusal_conclusion` effect. The receipt's `outcome_category` is `abandoned`.
3. **Every other next submission declines,** each with `declined_minutes` set and no abandonment:
   - (a) asking Reginald one last question as an action;
   - (b) an answerable `question` that returns early;
   - (c) a pure-mode declaration that's denied;
   - (d) `exit`;
   - (e) an action whose resolution fails.
4. **The suppression boundary:** declined at minute m. At m + 1439 there's no `declares_giving_up` prompt text and no `asked` transition. At m + 1440 it's eligible again.
5. **Episode reset:** a record `asked` (or `declined`) in chapter 1, then `continue_episode`. In chapter 2 the record is ignored: the question can't be confirmed, and there's no suppression.
6. **No clock:** in a world without `time:elapsed`, a decline suppresses for the rest of the episode.
7. **Main arc only:** a side arc never gets the walk-away prompt text or a record.
8. **No inference from movement:** 30 turns of travel with `declares_giving_up` false give no record and no abandonment.
9. **Sole writer:** a grep-style test finds no other code path writing an `event:abandoned` kind. The counter-refusal guard still holds (the existing test).
10. **The full suite.**
