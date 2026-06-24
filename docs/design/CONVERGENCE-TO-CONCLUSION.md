# Convergence to the Conclusion

> **Folded into `STORY-SHAPE-AND-RESOLUTION.md`** (the unified, genre-parametric spec).
> Phase 1 here is shipped; the unified doc re-aims convergence at the *conclusory
> scene*, not the verdict. Read the unified spec for the whole picture.


**Founder direction (2026-06-22):** "All roads should try to lead to the conclusion
scene — gentle nudges along the story, or when appropriate relocating the conclusive
scene to the new location the story has woven, reinventing it all the same. However
the narrative agent does it, we want it to seem like good live fiction. Maybe
collapsing it into a three-part act might be helpful. But whatever it takes for
masterful game narration and story creation."

## The principle

A good live-fiction GM never lets the story stall and never railroads. Wherever the
player wanders, the GM bends the road back toward the climax — and when the players
have clearly gone elsewhere, the GM **relocates the prepared scene to where they
are** and re-weaves it to fit. The convergence is invisible: it should feel like the
story was always heading here. Two tools, used by feel:

1. **Gentle nudge** — surface an unwalked thread diegetically; let it pull the player
   toward the central tension. (We already have this: `navigate`/rung escalation +
   `nudge_pick`.)
2. **Relocate the climax** — bring the pivotal beat to the player's *current* place,
   re-staged to fit, rather than stalling or marching them back to an authored room.

## What already supports this (no engine change)

- **Beats are path-independent CONDITIONS, not places.** `achievable_via` is an Expr
  over world-state; the climax fires when its condition holds, *wherever the player
  is*. Relocation is therefore a NARRATIVE-STAGING problem (render the beat here),
  not an arc-grammar one — the condition doesn't care about location.
- **`current_phase(reads, arc)`** derives the dramatic phase from world state
  (SETUP → RISING → CRISIS → CLIMAX → FALLING); **`climax_ready`** says the arc is
  primed to converge.
- **`navigate` + rungs (SURFACE … REFUSAL)** already escalate pressure and pick a
  thread to surface when the story idles.

## The 3-act overlay (founder's "three-part act")

Map the five dramatic phases onto three acts — a coarse convergence frame the
narrator can always orient by:

| Act | Phases | Narrative posture |
|---|---|---|
| **I — Setup** | SETUP, RISING | Ground the world; seed hooks; let threads pull toward the central tension. Low pressure. |
| **II — Confrontation** | CRISIS, CLIMAX | Converge. Every road bends toward the pivotal beat; if the player has wandered, RELOCATE it to where they are. |
| **III — Resolution** | FALLING | The world settles in the wake; close threads, no new pressure. |

`climax_ready` inside Act II = "the conclusion is at hand — steer every road into it
now, and bring it to the player's current location if needed."

## Implementation

### Phase 1 (this pass) — the convergence/relocation directive (briefing-level)
Host-side, no engine change, concealment-safe (converges DRAMATICALLY, never reveals
the answer). In `run_turn`, derive `current_phase` and append a `_convergence_directive`
to the narrator briefing:
- **Always:** this is live fiction with a destination; bend every road gently and
  diegetically toward the climax; never stall, never railroad.
- **Act-aware:** the posture from the table above.
- **Relocate (Act II / climax_ready):** if the player has drifted from where the
  pivotal beat was imagined, bring the confrontation/discovery TO them, re-woven to
  fit this place — the beat's condition is location-independent, so it can land
  anywhere.
- Defers to the existing terminal-epilogue / "arc resolved" directives in Act III.

`TurnTrace.act` for the debug surface + tests.

### Phase 2 (later, design-first) — deeper convergence
- Pacing tuned per act (escalation curve steeper in Act II).
- A "relocation receipt" so a relocated beat's staging is remembered (no re-relocate
  thrash).
- Author-time: ensure the climax beat's `achievable_via` is genuinely place-agnostic
  (lint for a climax gated on a fixed location → flag).
- Possible: a light **act counter** surfaced to the player as scene-feel (never a
  game-y "ACT II" banner — the no-forced-goal rule applies).

## Guardrails
- **Concealment:** convergence is dramatic pull + staging, NEVER informational. The
  directive never names the hidden answer; the concealment block still governs.
- **No railroad, no puppetry:** the directive moves the WORLD toward the player
  (relocate the beat, surface a thread), never scripts the player (player-boundary
  constraint still binds).
- **No forced banner:** consistent with the no-goal-banner ruling — acts are an
  internal convergence frame, not player-facing UI.

Related: `LIVING-WORLD-GENERATOR.md` (drift/relocate-beat), `IMPROV-AND-AUTHORITY`,
the improvisation north star, `NARRATOR-GM-STYLE`.
