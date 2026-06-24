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

## Not built
Direction only. Likely a mesh round-robin (it touches the arc layer + the engine
boundary for conclusive-event detection) before building. Connects to:
WIN-LOSS-CONDITIONS, LIVING-WORLD-GENERATOR, the born-won guard (model-tiers memory).
