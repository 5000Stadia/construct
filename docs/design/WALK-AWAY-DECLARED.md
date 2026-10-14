# The walk-away as a declared decision (R40)

**Status:** spec r1, 2026-10-13, for cr review. Not built. It replaces CHAPTER-BRIDGE-B1 change 1, which was never built.
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

**1. Only a thread the player knows can be walked away from** (IR-15). R40 applies to the MAIN arc only:
- the player was given its aim (the opening and `goal_statement`);
- a side arc the player may never have heard of keeps lapsing on its own clocks, as today, and is never "abandoned".

**2. A detection opens a question, never an ending.** While the main arc's refusal clock is armed and no walk-away question stands:
- **The candidate:** the detector gets one more candidate, `{kind: "walkaway:main", what: "the player DECLARES they are giving up <the main aim> for good: walking away from it, not just going somewhere or doing something else first"}`.
- **What a positive does:** it writes `session:walkaway` · `asked` = `{turn, minutes}`, and nothing else.
- **What it never does:** fire the refusal clock, or write any canon.

**3. The question is asked in the story, once, with the stakes plain.** On the turn of the detection, the narrator's briefing carries:

> THE PLAYER MAY BE WALKING AWAY from {aim}. Make what they would leave behind concrete and immediate, and let a present character, or the scene itself if no one is there, ask plainly whether they are truly done with it. Never decide for them, and never block them.

- **The form is fixed and medium-tempo:** an in-world conversational beat. The ruleset's tempo-selected form (I8) is deferred to R46, with a written reason: one fixed form adds no model call.

**4. Only an explicit yes ends it.** On the turn after a question stands:
- **The candidate:** the detector gets `{kind: "walkaway_confirmed:main", what: "the player answers YES, explicitly: they are giving up <aim> for good"}`, and the `walkaway:main` candidate is withheld.
- **On a yes:** it writes `event:abandoned_main_<turn>` with `kind` = the main refusal clock's kind (`event:abandoned`), plus `agent` and `caused_by` rows. `clock_pass` then fires the refusal clock as designed, and B1 records `abandoned`.
- **On anything else** (a no, a deflection, silence, another action, or "one more question for Reginald"): it's the literal reading (IR-22). The question is cleared (`asked` → `answered_no` at that turn), and play goes on.

**5. Never ask twice about the same thread in one stretch.** After a `no`, the walk-away candidate for the main arc is withheld until **one full story day** (1,440 diegetic minutes) has passed. It's measured on the story clock, since turns are free. That's the ruleset's "at most one clarification per thread per stretch of story time".

**6. Nothing else infers abandonment:** no movement, distance, idle time, or turn count. The refusal clock stays guarded against counter atoms, as today.

## Not in scope

- **Walk-away questions for side arcs.** Side arcs lapse.
- **The tempo-selected form** (R46).
- **A private-channel answer** (R41).
- **Recording the walk-away as an intent-frame stance** (R41/R44). The `session:walkaway` record is the minimal state until the intent frame exists.

## Tests

1. **Detection asks, never ends:**
   - **Setup:** a stub detector reports `walkaway:main` on turn 5.
   - `session:walkaway` is set, with no `event:abandoned*` row, and the refusal clock hasn't fired.
   - The turn-5 briefing carries the walk-away question directive.
2. **An explicit yes ends it:**
   - **Setup:** a stub detector reports `walkaway_confirmed:main` on turn 6.
   - `event:abandoned_main_6` is written with kind `event:abandoned`.
   - The refusal clock fires, and the receipt's `outcome_category` is `abandoned`.
3. **Reginald (anything but yes):** on turn 6 the player asks Reginald one last question (no confirm detected). Then:
   - there's no abandonment;
   - the question is cleared;
   - on turn 7 the confirm candidate is gone and the walk-away candidate is withheld.
4. **Not twice in a stretch:**
   - **Setup:** after a no at story minute m.
   - A walk-away candidate isn't offered before m + 1,440.
   - After it, it is offered again.
5. **Main arc only:** a side arc's refusal clock never gets a walk-away candidate.
6. **No inference from movement:** 30 turns of travel far from the case, with no declaration detected, give no `session:walkaway` and no abandonment.
7. **The guard stands:** a counter-based refusal clock is still suppressed (the existing test).
8. **The full suite.**
