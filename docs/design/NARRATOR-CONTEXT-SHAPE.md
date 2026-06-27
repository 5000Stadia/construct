# Narrator context-window shape — audit + consolidation (DRAFT for Cx/K review)

Founder directive (2026-06-27): agent-facing prompts should be clear straightforward
directives + a clean presentation of the SITUATION, not stacks of rules. Kernos advisory
(letter 078): invert the ratio (situation foreground), consolidate clauses → principles,
bound the simultaneous imperative count (~≤12), scope rules like we scope pins, and
*relocate* operator-knowledge to a test rubric rather than deleting it.

## Today (the problem)

The narrate call concatenates, every turn, the standing union of:
`RENDER_STYLE` (~27 clauses) + `RENDER_LEASH` (~25) +
`PROTAGONIST_COMPETENCE` (~8) + `WORLD_IS_PEOPLED` (~7) + ~per-turn directives →
**>60 simultaneous imperatives.** (`FICTION_CRAFT` is NOT in the live narrate call — it's
authoring/session-zero only, Cx 245 — so it's not narrator bloat.) Past ~10–12, compliance goes lossy and the model
services the list instead of reading the scene. The situation is a small island in a
sea of rules.

## Target shape (three layers by lifetime; ordering exploits attention)

1. **Voice contract** — RESIDENT, top/system, ≤7 principles, written as a *character*.
2. **The situation** — INJECTED, prominent, the bulk of the window (the star).
3. **This-turn asks** — INJECTED, ≤3–5, at the very bottom (freshest = most-followed),
   only what THIS turn triggers.

## The voice contract (DRAFT — 6 principles, replacing the ~100 clauses)

> You are the game-master narrating this world to one player. Hold to these:
>
> 1. **THE BRIEFING IS YOUR TRUTH.** Everything you narrate is grounded in it; never
>    contradict it, and never reveal what it doesn't give you — a secret you weren't told
>    is one you can't expose. The cast are distinct people; never merge them or invent
>    that one is secretly another.
> 2. **GROUND, THEN FLAVOR.** Lead with the concrete — what the player senses, who is
>    here, the ways out — and answer what they just did, now. Clarity is the cake; style
>    is the cherry. Never a sentence that's all mood and no information.
> 3. **THE PLAYER ATTEMPTS; THE WORLD ANSWERS.** Their words are an attempt, not the
>    world's compliance. Improvise the ordinary freely (a desk holds papers), but invent
>    no momentous discovery, plot object, or out-of-world thing — only the briefing's
>    threads carry real weight. Incidental texture stays texture; never dress it as a lead.
> 4. **THE WORLD IS PEOPLED.** The cast feel and react in proportion to what lands on
>    them, and carry it forward; never answer a charged human moment with procedure alone.
> 5. **THE PLAYER KNOWS THEIR OWN LIFE.** Volunteer what their character would plainly
>    know — their trade, routines, the place; never make an NPC recite it for them
>    (commonplace knowledge only, never a withheld answer).
> 6. **PERSPECTIVE & VOICE.** State the world's plain facts plainly; render the player's
>    presence, perception, and relationships in second person ("you notice…"). Second
>    person, present tense, in the world's voice — always.

Six principles ≈ the inviolable identity. Each is a stance to reason *from*, not a clause
to comply *with*.

## Where the dropped clauses go (relocate, don't delete — Kernos)

- **Operator rubric / test assertions** (verify the narrator, not instruct it): the
  clue-shaped-affordance phrasing examples, the world-fit examples, "answer-this-turn,
  don't re-establish", "one image per paragraph", the specific don't-merge examples, the
  FICTION_CRAFT genre-promise catalogue. These become how we *test* behavior, kept in this
  doc + `tests/`, out of the attention budget.
- **Conditional injections** (scoped by the pin machinery, surfaced only when triggered):
  - peopled/emotion emphasis → only when NPCs are present in the scene;
  - protagonist-competence rule → only when the action implies the character's own knowledge;
  - hold-mode vs reveal-mode → per turn (never both);
  - the genre craft note → the active genre only;
  - improv/reshape/fallout/pins/clue-delivery → already conditional.

## Inventory (always / conditional / redundant / dead) — drives the staged cuts

Synthesized from Cx 243 + Kernos 078. "ALWAYS" = resident in the voice contract;
"COND" = inject only when the trigger fires (scoped like pins); "RUBRIC" = move to
test assertions; "DROP" = literal redundancy a model re-derives; "REWORD" = keep but fix.

| source clause | disposition | note |
|---|---|---|
| briefing is truth; never contradict / reveal beyond | ALWAYS | principle 1; stated ~5× across blocks → keep ONCE, DROP repeats |
| distinct cast; no merge / secret-identity | ALWAYS | principle 1/6 |
| player's words = attempt, not compliance | ALWAYS | principle 5 |
| ordinary improv is free | ALWAYS | principle 5 |
| lead with the literal / GM grounding | ALWAYS | principle 2 |
| style serves clarity (restated ~6×) | ALWAYS once / DROP repeats | principle 4 |
| answer-this-turn, don't re-establish | ALWAYS (merge) | collapse w/ "lead literal" → "ground on entry/move/look; else answer the move" (fix the contradiction Cx flagged) |
| never all-vibe-no-info | ALWAYS | principle 4 |
| perspective (world plain / player 2nd-person) | ALWAYS | principle 3/6 |
| second person present (in RENDER_STYLE AND player_constraint) | ALWAYS once / DROP dup | principle 3 |
| no player puppetry (player_constraint) | ALWAYS | principle 3 |
| FORBID_TASK_MARKERS | ALWAYS | tiny; keep |
| clue-shaped-affordance hygiene (long, w/ examples) | COND + RUBRIC | inject on search/read/examine in clue-bearing arcs; examples → tests |
| world-fit / anachronism (2 long examples) | COND | inject on off-world/underdetermined questions (also overlaps turnloop:2419) |
| WORLD_IS_PEOPLED | COND | inject when NPCs present in scene |
| PROTAGONIST_COMPETENCE | COND | inject when the move implies the character's own knowledge |
| "what you make real becomes part of the world" | REWORD | overstates narrator authority — "ordinary details may be remembered by the host; never alter established/protected facts" |
| hidden-destination / neutral-on-answer / the-player-just-did (turnloop) | COND (already) | keep specific; reword per Cx 243 §3 to stop suppressing briefed consequences |

## Implementation plan (regression-risky — behind tests, reviewed first)

1. Cx + K review THIS draft principle set (Kernos offered).
2. Build `NARRATOR_VOICE` (the ≤7-principle contract) + a scoped-directive injector that
   reuses the pin scope-resolution to decide which conditional directives are in frame.
3. Move the relocated clauses into test assertions (the narrator must still DO them on the
   triggering turn — verified on less prompt).
4. Implement behind the suite; live-verify clarity/coherence/character/fidelity hold on the
   leaner window (the real test is behavior, not green unit tests).
5. Keep the prune standing — adding a clause is a regression unless it earns its place.
