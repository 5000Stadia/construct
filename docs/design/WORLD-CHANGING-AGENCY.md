# World-Changing Agency — when an earned act reshapes canon

**Status:** spec, awaiting Cx protocol review (letter C-197). Founder ruling 2026-06-26.
**Relates to:** `ACTION-RESOLUTION.md`, `ARC-LAYER.md`, `LIVING-WORLD-GENERATOR.md`,
`CONVERGENCE-TO-CONCLUSION.md`, and the improv/authority discipline.

## The ruling

> "I would like the system to be able to change this. The miraculous adventure that the
> player engages with should be able to shape the world, however it lands." — founder

An earned, miraculous player act should be able to **reshape canon** — including
overturning a foundational fact (reviving the dead, undoing a loss, breaking what the
story assumed fixed) — and the world genuinely changes, **however it lands**. The authored
destination then **adapts** to the new world; it is not protected from the player.

This evolves the prior `improv-serves-the-destination` ruling: improv no longer either
"serves the destination or is curtailed before creation." The **destination itself** is now
reshapeable by miraculous earned agency — the arc re-plans to serve a *new* destination.

## What this is NOT (the authority boundary stays)

The narrator and the player **still cannot mint canon by fiat.** Today the contradiction
gate (`turnloop.py` post-render promotion) correctly **quarantines** any narrator row that
overwrites established canon — that is what kept the lighthouse victim dead, and it stays
the default. World-changing agency is a *sanctioned, host-committed* path layered over that
gate, never a loosening of it for free-text assertion.

## The three things that must be true for a change to land

1. **Earned.** The act was classified uncertain (`needs_test = true`) and drew a
   sanctioning resolution tier. Mapping (proposed, Cx to confirm):
   - `complete_success` → the miraculous outcome lands in full (the victim lives).
   - `success_cost` → it lands *with a cost/twist* (he lives, but maimed / amnesiac /
     only briefly lucid).
   - `failure_opportunity` / `terrible_failure` → it does **not** land, but still **shapes
     the world** its own way (the attempt is now a known event; a new complication or
     fallout is committed). "However it lands" = every tier writes a real consequence.
2. **Plausible / sanctioned.** A coherence + plausibility check (reuse the existing
   improv grant test) — a reshape that the fiction can support, not arbitrary fiat. Pure
   physics-breaking by assertion alone is still refused unless the genre/tone sanctions it.
3. **Host-committed upstream, PRE-render.** The narrator never writes it, and the decision
   happens *before* narration — not by mining the prose afterward. The host commits the change
   through the ingest doorway (as `emit_fallout` writes canon world-events, `executor.py:586`),
   then the narrator renders committed truth. (Cx 198 #1: the post-render contradiction list is
   too late and too lossy to be the trigger — it's kept only as the enforcement backstop.)

## Mechanism (host-side; zero engine primitive)

The substrate already supports it: pattern-buffer is append-only with folding, so
`alive → dead → alive` is just more events, and an as-of query at any coordinate returns the
right state.

**The trigger is a PRE-render `ReshapePlan`** (Cx 198 #1), assembled after classify +
resolution draw + plausibility, on a turn whose uncertain action targets a foundational fact:
classify flags a world-changing attempt → one resolution tier is drawn → plausibility sanctions
the target + magnitude → the host builds a typed `ReshapePlan` and **commits it before beat
evaluation and narration.** The existing post-render contradiction gate stays as the
**backstop**: rows that match the sanctioned plan are already-written/allowed; any *other*
narrator overwrite of canon stays quarantined exactly as today (default-deny off-plan).

`reshape_canon(world, plan, *, turn) -> ReshapeResult` (new, mirrors `emit_fallout`). It
writes ONLY structured rows from the plan — it never mines prose:
1. **Append the new current state** at `valid_from = turn_time(turn)` under the same functional
   key (Cx 198 #2 — do NOT retract lived canon: retraction hides a row even for historical
   `as_of` reads, which is wrong for a fact that was *true in lived play*). E.g.
   `person:angus.alive = true` (or the inverse of the Boolean the world used). Historical reads
   before the turn still serve *dead*; current reads after serve *alive*. Retraction is reserved
   for `plot:` supersession and rows that should never have been true.
2. **Commit a canon reshape event** `event:reshaped_<slug>.kind = canon_reshape` with explicit
   `caused_by = event:action_<n>`.
3. **Re-stage, scoped** (Cx 198 #4): a revived NPC gets a current location and a `knows:<npc>`
   frame seeded with ONLY justified knowledge — own state, immediate sensory experience, and any
   **sanctioned witness fact named in the plan** (e.g. "Angus can name who attacked him" is a
   *planned* row, never a narrator side effect). No blanket mirror of hidden truth.

Then **the arc re-plans** via a new mid-episode `replan_main_arc` (Cx 198 #3) — a *sibling* of
`continue_episode`, NOT that whole machine: it supersedes the visible `plot:` main-arc/portfolio
control rows that can't survive (these `plot:` rows *are* retracted/closed — control rows, not
lived canon), appends the reshaped main arc at `valid_from = turn_time(turn)`, and leaves
delivered player knowledge + lived canon intact. **No `episode_start`, no checkpoint, no
terminal reset.**

**The re-plan finds the BEST story, it doesn't mechanically pivot** (founder, 2026-06-26):
*"there is still a story there no matter how miraculous the thing is — it should be waiting for
the player in whatever form it naturally becomes after the miracle. If the miracle draws a more
engaging story elsewhere, rule of cool, go whatever direction coherently makes sense with the
player's direction. The agent that has the wheel should guide the story to where the best story
is."* So `replan_main_arc` is an **authoring** step (like `continue_episode` authors a new arc),
seeded from the reshaped world + the player's coherent direction, choosing the most engaging
coherent continuation — the lighthouse case might pivot to "who tried to kill Angus," or follow
the player somewhere better entirely. The destination *adapts to serve the best story*; it is
never railroaded back.

## "However it lands" — the consequence is always real

| Tier (uncertain act) | How the world changes |
|---|---|
| complete_success | the miraculous outcome lands in full |
| success_cost | it lands, but at a cost / with a twist |
| failure_opportunity | it fails, and the failure opens a new thread (committed) |
| terrible_failure | it fails hard, with a committed adverse consequence |

No tier yields a flat refusal. The narrator may *frame* a low tier as the world resisting,
but a consequence is committed either way.

## Guardrails

- **Flag-gated** (default off) so shipped mysteries play byte-for-byte as today until the
  gate change is reviewed; the contradiction-quarantine default is unchanged when the flag
  is off. (Likely promote to genre/tone-aware default once proven.)
- **No fiat.** Requires the earned + plausible + host-committed trinity above.
- **Coherence preserved.** Lived-canon state changes are **appended** (never retracted), so
  as-of queries before/after stay correct. Only `plot:`/control rows are superseded by
  retract-then-append (the EP2 portfolio lesson) — that discipline applies to the arc manifest
  in `replan_main_arc`, NOT to lived canon. The membrane stays clean (derived tension is never stored).
- **Narrator stays leashed** — no new durable-write authority; it only *renders* the
  host-committed change.

## Resolved (founder + Cx 198)

1. **Genre/tone — RESOLVED (founder + Cx):** capability is **universal**; tone modulates the
   *realization, plausibility, cost, and framing*, never the existence of the capability. Gritty
   realism doesn't veto — it picks a grounded landing (misdiagnosed death, a pulse after
   cold-water shock, brief lucidity before a second collapse, testimony at terrible cost); pulp/
   supernatural can store a literal durable resurrection. **Hard rule: prose and canon must match
   the actual landing.**
2. **Tier→magnitude — CONFIRMED (Cx):** `complete_success` lands cleanly + durably;
   `success_cost` lands *with* a concrete cost/instability/injury/liability (NOT a refusal — else
   the 55% tier becomes a hidden failure and breaks `ACTION-RESOLUTION.md`); `failure_opportunity`
   doesn't land but opens a real thread; `terrible_failure` doesn't land + a concrete adverse
   consequence. No tier is a flat refusal.
3. **Always-still-a-story (founder):** the re-plan is authoring, not a broken-arc risk — it finds
   the best coherent continuation from the reshaped world. Safety net: a reshape that can't yield a
   coherent arc degrades to the `incompletable`/fallout pathway, never a dead end.

## Build order (all behind the flag; Cx 198 "build shape I would green")

1. **DONE / Cx-GREEN (202):** Typed `ReshapePlan`/`ReshapeResult` + pure `reshape_canon` — appended
   current-state rows, explicit `caused_by` event, fail-closed scoped frames; `plan_from_proposal`
   bridge; never mines prose.
2. **DONE / Cx-GREEN (202):** `propose_reshape` cohort (rule-of-cool judge) + `apply_reshape`
   orchestration + the `CONSTRUCT_WORLD_RESHAPE` flag (default off, fail-open).
3. **DONE / Cx-GREEN (207):** `run_turn` trigger wiring — pre-`beat_pass` commit; `canon_table`
   patched from the committed rows; exact `(entity,attribute,value)` license on `licensed_strict`
   so a reshaped PROTECTED key promotes while private witness frames stay unlicensed; narrator
   briefed with the summary. Integration tests: protected-key commit+promote, failure-tier
   consequence-without-flip, flag-off inert.
4. **NEXT — `replan_main_arc`** mid-episode op: supersede `plot:` control rows, AUTHOR the best new
   arc from the reshaped world + the player's direction (founder's "the agent guides it to where the
   best story is"), **no** `episode_start`, no checkpoint, no terminal reset. Safety net: a reshape
   that can't yield a coherent arc degrades to the `incompletable`/fallout pathway, never a dead end.
5. Live proof: the lighthouse revive lands, Angus becomes a questionable witness, the story finds
   its best next shape — logged transcript to the founder.

### Open item for step 4 / live proof (Cx 207 note #2)
The trigger patches `canon_table` but does NOT expand `snap_scope`. Fine today (the narrator is driven
by `trace.reshape` and the gate uses an exact license), but if a reshape **introduces or restages an
entity that was outside the original scene scope** (a revived NPC who wasn't staged), ordinary scene
listing / name resolution may need an explicit `snap_scope` refresh. Handle in `replan_main_arc` (it
re-stages) or as a scope-refresh after a non-None reshape.
