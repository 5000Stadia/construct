# Narrative Flavor & Style — ingest cohort + terminal epilogue (spec)

**Status:** GREENLIT (founder, 2026-06). Crystallized from the design thread.
Host-side; engine stays genre-agnostic (Jarvis litmus). Construct is the fiction
plugin; narrative lives as ordinary facts + host directives over the vanilla shape.

## 1. The ingest cohort (session-zero, ONE-TIME)
A new cohort runs once at scenario creation, after the arc is authored, reading the
world digest. It distills the fiction's concentrated genre/style juice into the
shape. **Three destinations** (one cohort, where each goes):

1. **World-level STYLE/TONE → the overlay (HOW everything is written).**
   Genre, era, geography, culture, narrative voice/register → a single render
   directive. Stored on the **scenario meta** (`meta["style"]`), fed to the
   narrator EVERY turn as a voice directive. **Guardrail: style shapes VOICE,
   never FACTS** — it tells the narrator *how* to render the grounded world, not
   to add to it (stays inside the render leash + the gate).
2. **Per-entity FEEL → attributes on the entity (vanilla PB).**
   `person:clerk · feel = "evasive; flinches at the word audit"`;
   `place:vault · feel = "too quiet; tastes of old paper and worse"`. The PB
   object holds it; the narrator already reads scene entities' facts, so the feel
   surfaces automatically when that person/place is in scene. This carries the
   "what makes them suspicious" clue layer.
3. **Foreshadowing PINS → the conditional/escalating layer.** *(v2 — deferred.)*
   Arc-linked clue-trail pins whose salience rises toward the reveal. Rides the
   shipped pin channel; this is the long-promised pinned-awareness authoring pass.
   v1 ships style + feel (feel already carries the static clue); escalation later.

## 2. Delivery
- **Style:** `meta["style"]` → `Session.turn` passes it to `run_turn` → a STYLE
  section in the narrate briefing, every turn. One-time extraction, no per-turn
  model cost; the source prose is never re-touched (the ingest→projection
  showcase — voice without live-referencing the fiction).
- **Feel:** ordinary canon attributes (mirrored to the player frame) — surfaced by
  the existing scene read.

## 3. Win/loss + the terminal epilogue
- **Who referees:** the HOST, deterministically — `arc_outcome(reads, arc)` runs
  each turn AFTER the ingest commits, reading the committed world (a precise Expr
  eval, not a model verdict). The model writes the world; the host reads the
  score. Already built; stays deterministic (precision + correct ordering;
  near-free, same-turn).
- **The epilogue (enrichment):** in `win_loss`, on a terminal outcome the narrator
  gets a **movie-epilogue** directive — feed the CAST (protagonist + key
  characters) and direct a per-character fate (where each ends up, what the
  outcome cost/won them), plus an **end-reveal** (the arc's resolution dropped at
  the curtain — the one place a knowing narrator is right; concealment is *meant*
  to lift when the story's over). Fates are improvised at the curtain from the
  final world-state + each character's feel/arc.

## 4. Build order
1. `cohorts.author_flavor(provider, digest, entities)` → `{style, feels}`.
2. `_finalize_scenario`: new stage — store `meta["style"]`; ingest `feels` as entity
   attributes (canon + player-frame mirror).
3. `run_turn(style=…)` + `Session` passes `meta["style"]`; STYLE section in briefing.
4. Terminal epilogue: enrich the aftermath directive (cast + fates + end-reveal).
5. Tests + a re-seal + a live probe (narrator renders in-style; epilogue covers the cast).
6. *(v2)* foreshadowing pins (arc-linked, escalating).
