# Gated Ingest Cohort — the next slice (round-robin synthesis)

**Status:** DRAFT (spec). Synthesis of the K→Cx→PB round-robin on TURN-LOOP-IMPROV.
The leash→license flip is endorsed (PB GREEN, probe-validated) and rides on the
now-shipped engine read-completeness guarantee (PB `4df78e1`,
CLASSIFIER-EVENT-SAFETY-V1). This spec is the **output guard** Cx required — role 3
of the three-role loop, host-owned, over EXISTING engine hooks (PB 067: no new
engine primitive).

## 1. The shape (recap)
Three roles per turn: **retrieval cohort** (scoped, player-frame-only — the
concealment boundary) → **narrator** (improvises within grounding, unprivileged) →
**ingest cohort** (this spec — decides what the narrator's response and the
player's action may write to canon, before the next turn). Two structural
boundaries sandwich an unprivileged narrator: input scoping (done) + output gate
(this).

## 2. What the gate must do (Cx's three blocking items + PB's hooks)

### 2a. Player-attempt normalization (Cx #3) — BEFORE the render
Today player input is ingested to canon *before* the narrator runs (`turnloop`
~319), so fiat ("I'm carrying my pistol", "Mara hands me the key", "I already
unlocked it", "I find the clue / I kill him") commits before adjudication. Fix:
the pre-render player-input ingest stores assertions as **attempted claims**, not
canon facts — world-state and outcome are decided by the narrator (adjudication)
and only then canonized by the post gate. Player authors their *attempt*; the
world authors the *result*.

### 2b. Pre-commit fold-comparison (Cx #1) — catch contradictions
Before canonizing a narrator-originated row, read the established fold value +
provenance (`state`/`confidence` give both — PB) and compare to the proposed
value+origin. A narrator row that **changes an existing key** (not just a new
entity/attribute) to a different value is a contradiction → quarantine, don't
silently supersede. (The current concealment audit is post-commit/diagnostic;
this is the pre-commit gate.)

### 2c. Momentous quarantine via frames (Cx #2) — structural, not prompt-hope
The narrator can't know what's plot-significant (hidden by design). So instead of
trusting the directive alone: ingest momentous-suspect narrator facts into a
**`proposed:`/`quarantine:` frame**, NOT `canon`. The **arc layer** (which *does*
hold the hidden licenses) reviews and either promotes (re-ingest to canon) or
drops. Frame-absence keeps unlicensed fabrications out of canon reads
*structurally* — the shipped frame mechanism IS the quarantine (PB 067). What's
"momentous-suspect": new weapons/keys/clues, secret/reveal facts, NPC
motives/actions, identity or location changes for arc entities, irreversible
outcomes — unless arising from an authorized reveal/beat/nudge.

### 2d. Origin labeling (the spine of 2a–2c)
Stamp narrator-originated rows with a `source` meta (the provenance channel
`_source_class` already reads for `doc:`/`person:` chains — PB). The gate branches
on origin: player-attempt vs narrator-improv vs arc-authorized. No new engine
primitive; a thin `source` convention over the existing channel. (PB: only if
lived use proves the host needs *native* narrator-vs-player tagging does that
become a thin additive engine convention — not speculatively now.)

## 3. Engine contract (settled)
- **Read-completeness:** guaranteed — the model can no longer assign EVENT, so no
  standing player-visible fact silently vanishes from retrieval (PB `4df78e1`,
  frame-agnostic). Host keeps the `structural` declarations as belt.
- **Host owns the rest:** scope-exhaustiveness (the retrieval cohort must enumerate
  every player-visible scene entity), the origin/quarantine/fold-compare gate, and
  the attempt-normalization. The engine provides `source` provenance, frames
  (quarantine), and `state`/`confidence` (fold-compare) — all shipped.

## 4. Build order (proposed)
1. **Player-attempt normalization** (2a) — smallest, highest-safety; stops fiat at
   the source. Move/relabel the pre-render player ingest.
2. **Origin stamping** (2d) — the `source` meta on narrator/player rows.
3. **Pre-commit fold-compare + quarantine frame** (2b/2c) — the gate proper, over
   the post-render ingest (`turnloop` ~605), replacing the trusting
   `p.ingest(prose)`→canon with stage→compare→(canon | quarantine).
4. **Arc review of the quarantine frame** (promote/drop) — the arc-layer hook.

## 5. Open / dependencies
- Kernos's turn-loop leg has not yet reached C's inbox (PB asserts concurrence on
  concealment-via-scoping); fold in K's markup when it lands.
- The leash→license flip is implemented but **uncommitted** pending the founder's
  go; this gate is the slice that makes the license fully safe (Cx's RED → GREEN).
- Coreference/extraction-completeness (the `cray`-aliased-to-"anchor" seam) is a
  separate ingestion-fidelity track, not this gate.
