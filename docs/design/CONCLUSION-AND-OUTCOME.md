# The Destination that buttons up the story (design direction)

**Status:** DIRECTION (founder, 2026-06-19) — banked, not yet built. Replaces the
brittle `world_condition → won/lost` programmatic check.

## The framing (founder, sharpened)
Don't compute a win/loss verdict. **Author the interesting DESTINATION that buttons
up THIS kind of story** — the narrative endpoint where, *if the player has arrived
here, the story is complete.* On arrival, **improvise and deliver the epilogue.**
Win/loss is NOT a separate computed label — it is just the *tone* the epilogue takes,
improvised from what actually happened. The dragon battle resolves (destination
reached) → the epilogue improvises triumph, a heroic death, or a hollow victory.
Same destination, many-colored endings. This folds the whole "outcome" question back
into the movie-epilogue that already exists — far less machinery.

## The problem with the current model
`ConclusionShape.world_condition` (an `Expr`, usually `AtLeast(k, climax beats)`)
is evaluated by `arc_outcome` into `won | lost | None`. One boolean is forced to
answer two different questions at once — *is the story over?* and *did the player
win?* — and rigid semantics get the second one wrong:
- The villain *technically* completes the evil act (`detonated == true`), but the
  player cleverly made it ineffective and peace is restored. A boolean says **loss**;
  the narrative is a **win**.
- A climax beat that is really a *premise* ("the investigator was summoned") is true
  almost immediately → the story "wins" on turn 1 (the anchor / dragon failures).
- Authoring requires a fiddly `world_condition` + `failure_when` + climax-sufficiency
  set, and it still misses narrative reality.

## The reframe — two separate things
1. **CONCLUSION = a conclusive EVENT (the ender), identified at ingest.** The
   genre-defining climactic act that ENDS this kind of story *regardless of who
   wins*: the detective makes the accusation; the dragon is fought; the ring reaches
   the fire; the confession is made; the vault record is challenged. It is about
   **shape, not success** — mostly deterministic ("the decisive act occurred"), and
   it **cannot be true at genesis** (kills born-won and the shallow-beat bug).
2. **OUTCOME = an LLM JUDGMENT, in context, when the conclusion fires.** A judge
   cohort reads what ACTUALLY happened (world-state, recent beats, the player's
   choices) and rules: won / lost / bittersweet / pyrrhic, with a grounded reason —
   "the aim was met in spirit" even if the mechanics went sideways. This is where
   judgment belongs; not a boolean.

## The climax is a THIRD-ACT phenomenon (founder, from D&D)
The destination is NOT fixed/known at genesis — in a real campaign the climax is
"only noticed right before the third act, as tension mounts." So:
- **Reachable only after escalation.** A story you can't button up until it has
  built up — the conclusion is gated behind the arc reaching its third act
  (crisis/climax), never a genesis boolean. This is the structural reason anchor's
  turn-1 win was wrong: no rising action had occurred, yet a conclusion fired.
- **Crystallizes with play.** The destination is authored as a *direction* at
  ingest; its exact final shape sharpens from what the player and the living world
  actually did, recognized as tension peaks.
- **We already have the ramp.** Arc phases (setup→rising→crisis→climax→falling), the
  pacing rungs, and the clocks that mount pressure over quiet turns model the
  escalation. The conclusion is recognized at the TOP of that ramp — and "are we now
  at the climactic destination?" can itself be an LLM read as tension crests, not a
  flat check. (Existing `climax_ready_k`/`climax_ready_beats` are the seed of this.)

## Why it's better
- One thing to author ("what is the conclusive act of this story") vs a brittle Expr
  triad.
- Honors the host/engine wall (Jarvis litmus): the ENGINE detects the conclusive
  event occurred (`Occurred`/state read); the HOST's LLM judges what it MEANT.
- Nuanced endings become natural (subverted villainy → win; pyrrhic victory → win-
  at-cost), which the rigid check can't express.
- Fixes born-won + shallow-climax structurally (the ender is a real climactic act).

## The one risk + mitigation
LLM outcome judgment is non-deterministic. Keep **when** it ends crisp (the
conclusive event is a clean, mostly-deterministic trigger), and have the judge
return a **structured, grounded verdict** (read concrete world-state + a confidence),
so won/lost isn't a coin flip. The refusal/timeout clock still backstops the case
where the conclusive act never happens ("the chance passed" — its own ending).

## Shape of the change (when built)
- `ConclusionShape`: replace/augment `world_condition` with a **conclusive-event**
  condition (the ender). Keep `tension`/`delta_type` (they feed the judge + fallout).
- New cohort `judge_outcome(world_state, recent, aim) → {outcome, reason, confidence}`
  — fires when the conclusive event is detected; outcome ∈ won|lost|bittersweet|…
- `arc_outcome` / `arc_lifecycle`: "concluded" = conclusive event fired (or refusal
  timeout); "outcome" = the judge's verdict (not the Expr). Won-first ties dissolve.
- Arc authoring (`game._build_arc` + the arc-author prompt): author the **conclusive
  act**, not a sufficiency set. Insist it be a real climactic act (already half-done
  via the interesting-win insistence).
- Turn loop / win-loss termination: terminate on conclusion + judged outcome; the
  born-won viability guard is subsumed (a conclusive event can't be genesis-true).
- Living-world P1/P2: fallout/regeneration unchanged (a concluded arc still emits
  fallout); the judged outcome flavors the diegetic acknowledgment + epilogue.

## SHIPPED — the conclusion clock (founder ruling 2026-06-25; Cx 141–187)

The "is the story over?" question is now answered the way the founder sharpened it: **"IT"
closes the story — the narrative's own DECISIVE event — and the fiction authors that trigger,
always. Never a mechanic bolted on top, and NEVER the turn count.**

**Turns are free.** Nothing about how many turns a player takes ever forces a conclusion. A
detective can contemplate a clue for 300 turns; 30 one-sentence exchanges might be 5 in-world
minutes. The old turn-count terminals are RETIRED: `K_POSTCLIMAX` (post-climax expiry) and the
`TurnsQuiet(15)` refusal clock no longer end anything. The refusal clock is now an
**explicit-abandonment** `Occurred(event:abandoned_<arc>)` — it fires only when the player
decisively walks away, never on quiet turns (and a runtime guard in `clock_pass` suppresses any
counter-based refusal so no fabricated `refusal_conclusion` can enter canon — the mesh invariant).

**A story concludes only on its decisive event, authored per-story from what the story is about:**
- **Player commitment** (commitment-owned shapes — deduction/bond/…): the accusation, the
  confession, the choice. `world_condition` being met is READINESS, not the close; readiness only
  surfaces the "decisive moment is within reach" narrator nudge (tone-agnostic, gated to win_loss).
- **An authored failure** (`Arc.failure_when`): a decisive loss EVENT (the bodyguard's protectee
  killed, the alarm raised → `Occurred`), or a **time deadline** *when time is genuinely part of
  this story's thread* (the bomb, the King's dinner → `Quantity("time:elapsed","elapsed_minutes",
  ">=",N)`). A leisurely investigation authors NO deadline — time there is pedantic. The diegetic
  clock advances by what each action consumes (contemplation ≈ minutes; "I wait three hours" ≈
  hours), and for a deadline arc it is committed BEFORE the terminal check so a big-jump wait
  crosses the deadline the SAME turn.
- **Explicit abandonment** (the refusal clock) — the player walking away as an in-world act.
- **World-event-owned shapes** (endurance/farce) still close directly on their `world_condition`.

**Two independent time concepts:** PRESSURE (a deadline — opt-in per story) vs TEXTURE (time-of-day
governs appropriateness/availability — always on; 9 PM means the witness waits for morning). See
DIEGETIC-TIME.md. A no-deadline story "takes exactly as long as it takes to become thorough &
complete" — coverage (CONCLUSION-AS-EFFECT) is "thoroughness"; the player concludes when ready.

**Story-agnostic:** a casual/endless/sandbox card (idle family dynamics, open romance, slice-of-
life) is untouched — it runs `endless`, never force-concludes, never gets a dramatic nudge.

Implementation: `turnloop.run_turn` (`_has_time_deadline`/`_advance_diegetic_time`,
`_authored_failure`), `game._failure_expr` (the `time_deadline` → Quantity lowering + ARC_SCHEMA),
`game._build_arc`/`io._synth_refusal` (abandonment refusal), `arc/lint.py` check 4. Connects to:
GAUGE-PRIMITIVE (a deadline IS a Quantity over the clock), CONVERGENCE-TO-CONCLUSION,
WIN-LOSS-CONDITIONS, LIVING-WORLD-GENERATOR.
