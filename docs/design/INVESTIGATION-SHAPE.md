# Investigation Shape — the genre-faithful whodunit (Deduction depth)

**Status:** SPEC for Cx review (round 1). Founder-directed 2026-06-23; root cause from a live
castjuicy run + code recon; PB-invariant guardrails from Cx 055. Host-side orchestration over
the read-only pattern-buffer engine — **no engine fork, no new primitive** (presence,
knowledge, paths, briefings stay PB projections; PB stays the append-only sourced assertion log).

## 1. Why (the live failure)

A fully solvable castjuicy whodunit (deterministic proof: 7/7 holders lead genuine → full
interrogation → `triumph`) ended `quiet_failure` in live play. Root cause is NOT delivery
(that mechanism is fixed + Cx-GREEN). It is **staging**: only 3 of 7 suspects ever became
present (Orme/Firth/Ada); Parker/Celia/Mara/Bell were never in any scene, yet the cold open
foregrounded the absent Parker. The player questioned someone nobody-home → 0 clues.

**The concrete bug (recon):** `cast.cast_seed_plan` seeds each cast NPC's `knows:<npc>` clue
facts ONLY — it emits **no `in` (location) fact**. The engine rule is
`_colocated`/`_present`: *"a person with NO location is never present."* So a suspect becomes
present only if the ingested prose happened to place them — most never get a location, so they
are unreachable, while the cold open (rendered from establishing anchors) can still narrate an
unplaced suspect as "in the room." Logical `knows`-reachability passed the solvability gate;
**physical playable reachability was never staged.** (turnloop.py:287/850; cast.py:221;
game.py:485; session.py:358.)

## 2. The whodunit SHAPE (founder, genre-faithful)

The macro target: *whatever makes high-quality, engaging live fiction WITHIN this genre* —
a different answer per genre. For Deduction, drawn from how classic detective fiction works:

1. **The opening spoon-feeds the suspects.** The detective is informed → arrives at the crime
   scene → the cast IS there to interview. **The first witness introduces the cast of
   characters.**
2. **Context-driven initial presence:** some are present because they LIVE there; some because
   they REPORTED the incident.
3. **Discovery-driven expansion:** anyone outside the initial set is NAMED during interviews
   ("Mrs. McGillicuddy was near the scene an hour before") → the player asks around → learns
   where they are → **goes to visit** them (present on arrival).
4. **Culprit-converges:** it is non-traditional for the culprit to be someone who never shows
   up as involved by the end. The culprit must surface (at-scene or discoverable).
5. **Narration is ground truth; objects serve the ledger.** What the narrative presents must be
   accurate and come first. Object/ledger details serve accuracy when discussed; they do not
   gate the prose — the object is doing long-term ledger TRACKING.

## 3. The model (over PB, no engine fork)

### 3a. Per-suspect PRESENCE TIER (authoring data, resolves to ordinary `in` facts)
Each cast node gains an author-time `presence` ∈ `{at_scene, nearby, offscene}` and a
`location` (a place entity):
- **at_scene** — present at the crime scene from turn 1 (lives there / reported it). Seeded
  `in = <crime-scene place>` (co-located with the protagonist's start).
- **nearby** — not in the opening room but in the same site (the house/grounds); reachable by
  ordinary movement once the player explores or is directed. Seeded `in = <a place within the
  site>`.
- **offscene** — elsewhere entirely; **absence stays honest** (no route) UNTIL discovery opens
  one (§3c). Seeded `in = <a distant place>`.

These are ORDINARY sourced canon `in` facts (provenance = session-zero authoring), not a
derived "suspect roster" stored as truth (Cx 055). Presence each turn stays the existing
`_present`/`_colocated` projection — it now simply has locations to read.

### 3b. Scene-open in LOCKSTEP (the first-witness intro)
- The protagonist is seeded `in = <crime-scene place>` at build (today this is implicit; make
  it explicit so the opening room is canon).
- The cold open foregrounds EXACTLY the `at_scene` cast (the establishing/anchors read is
  already location-aware once §3a seeds locations). The narration must not present an unplaced
  suspect as in the room — engine-present set ↔ narrated-present set in lockstep.
- **The first witness** (an authored `at_scene` role, e.g. the one who found the body) is the
  fiction-facing affordance that NAMES the present cast and gestures at who else matters — a
  natural opening monologue. It resolves to the ordinary establishing facts (the `at_scene`
  suspects' presence + their hooks); no special structure.

### 3c. Discovery → reachability (off-scene suspects) — THREE LAYERS (Cx 057 #1)
A clue/hook may NAME an off-scene suspect (the existing cross-suspicion hook_text already does
this). When such a reference is surfaced into the player frame, "the route opens" — but that is
NOT one fact; it is three distinct layers, kept separate so we never fork engine truth or store
a derived reachability flag:

1. **Canon topology (engine truth, authored at build):** the suspect already lives somewhere
   referable — `person:bell in place:bell_cottage`, `place:bell_cottage kind place` +
   `name`/`alias`, plus any `connects_to`/containment the fiction establishes. This is ordinary
   sourced canon, written at session-zero (`cast_location_plan`, §4). The place must be a
   real, `world.refer`-able PLACE before any route is offered.
2. **Player entitlement (frame-scoped knowledge, written at turn-time):** on surfacing the
   naming clue, the host writes `person:bell whereabouts place:bell_cottage` into
   `knows:<protagonist>`, with provenance tied to the surfacing clue/witness. This records what
   the player has LEARNED and is now entitled to seek — it does not move them.
3. **Session affordance (bookkeeping/pacing, not engine truth):** the narrator brief may say
   "you may seek Bell at his cottage." A `session:main` event MAY be written for audit. There
   is **no `route_open=true` derived flag** anywhere.

Travel then uses the existing movement path (`moves_to` → `world.refer(place, frame=canon)` →
protagonist `in = place`); on arrival the suspect is `_present` because layer 1 gave them a
location. **Movement guard:** a route brief points to a PLACE; "go to Parker" must resolve to
Parker's place, never set the protagonist `in` to a person entity.
- Absence stays relational and honest: before discovery, asking for an off-scene suspect yields
  "not here — no one's seen them" (the good-DM, not a stonewall), never a phantom delivery.

### 3d. Culprit-converges — explicit deterministic subject (Cx 057 #2) + reachability gate
- The cast proposal carries an **explicit culprit subject** (`is_culprit` on the holder node /
  a `culprit_id` in the proposal) — without it `check_solvability` cannot prove the genre
  promise that the actual culprit surfaces. (A later option: bind deterministically to the
  arc's protected answer; v1 uses the explicit field.)
- **Physical-reachability gate (deterministic, NOT a soft note — Cx 057 answer #2):** extend
  `check_solvability` from "every required pillar has a genuine live-reachable clue" to ALSO
  require **"every required clue's HOLDER is physically reachable in play"** AND **"the culprit
  is reachable"**: reachable ⟺ `at_scene`, or `nearby` with a referable place, or `offscene`
  with a naming-clue from an already-reachable holder (a discovery chain rooted in the at_scene
  set). A culprit/holder stranded with no chain fails the gate → re-author. Same class as the
  existing live-reveal gate, extended from "surfaceable by delivery" to "reachable by staging."
- **Opening-promise gate (non-blocking → folded):** a generated Deduction cast must have ≥1
  `at_scene` member flagged `first_witness` and a minimum opening cast count (≥2 at_scene), or
  the gate fails — otherwise a proposal can stage people while breaking the genre opening.
- **`nearby` means reachable-NOW:** a `nearby` node with no referable place / route is treated
  as `offscene` for the gate (playability, not just "not at_scene").

### 3e. Narration-first objects
- Clue facts continue to ride the ledger for tracking/coverage, but the EXAMINE/EXPLORE
  delivery (still unbuilt) must treat the NARRATION as ground truth: if the narrated scene
  logically contains a clue-bearing object the player inspects, the host appeals to that
  narrative truth (resolve-and-commit upstream, per the improv model) rather than gating on a
  pre-listed object id. Objects gate solvability ONLY when the scene explicitly made them
  clue-bearing. (This dovetails with the separate EXAMINE-channel build; flagged, not built
  here.)

### 3f. Coherence doctrine (founder, 2026-06-23) — why we SEED rather than wall
The engine rule "a person with no location is never present" must not be a dead-end wall. The
general principle: **anything not in the original fiction / PB has its existence and details
(including location) IMPROVISED, and the PB ADAPTS** (commit upstream — the resolve-and-commit
loop, [[improv-and-authority-model]]). Two governing rules: (1) on a genuine conflict, RECENCY
wins; (2) but AVOID conflicts — if a thing is in the PB and is referenced, it should already be
in the narrator's AWARENESS with its details, presented ACCURATELY. A contradiction breaks
immersion two ways: by **contradicting** an established detail, or by **MIXING** details across
entities (one suspect's tell attributed to another). So:
- **Why this shape SEEDS suspect locations** (§3a) rather than relying on improv: putting each
  suspect's existence + location in the PB makes the narrator aware and lets it present them
  accurately — no improv, no contradiction, no mixing. This is the contradiction-AVOIDANCE
  path, and it's why seeding beats the "never present" wall.
- **For player-referenced entities NOT in the cast/PB** (a person/object the player invents or
  asks after): improvise existence/details and commit (PB adapts) — never stonewall with "not
  present." The off-scene discovery (§3c) is the authored case; this is the open-world tail.
- **Contradiction-REPAIR loop (cross-cutting, flagged not built here):** when the guard DOES
  detect a contradiction (or a detail-mix), it must come BACK to the narrator to self-correct
  in-fiction by creative means that keep ground truth + consistency — not a silent quarantine
  (today's gated-ingest behavior) and never a shipped immersion-break. This is a refinement to
  the gated-ingest cohort ([[improv-and-authority-model]]), tracked separately from this slice;
  noted here because the investigation's awareness/lockstep requirements feed it.

## 4. Implementation plan (host-side)

1. **`cast.py`** — `CastNode` += `presence` + `location`; `cast_from_proposal` parses them
   (fail-soft default `nearby`); new `cast_location_plan(cast, scene_place)` → `in` facts
   (at_scene → scene_place; nearby/offscene → their authored place). Keep `cast_seed_plan`
   (knowledge) as-is.
2. **`game.py` `_finalize_scenario`** — seed the protagonist's start `in = scene_place`
   (explicit); run `cast_location_plan` to ingest cast `in` facts as sourced canon; ensure
   the `at_scene` places sit on the protagonist's location chain.
3. **`cohorts.author_cast`** — author per-suspect `presence` + `location` + designate the
   FIRST WITNESS; bias: a handful `at_scene` (the genre's parlor), the rest nearby/offscene
   with a naming-clue from an at_scene suspect. Culprit `at_scene`/`nearby`/named-reachable.
4. **`check_solvability`** — add the physical-reachability gate (§3d): every required holder
   reachable via presence-tier + discovery chain; culprit not stranded.
5. **Cold open / `session._establishing_anchors`** — foreground `at_scene` cast; brief the
   first-witness intro; never narrate an unplaced suspect as present (lockstep).
6. **`turnloop.py`** — on surfacing a clue/hook that names an off-scene suspect, write the
   route-affordance (whereabouts into `knows:<protagonist>`) + brief "you may seek them"; the
   absent-suspect honest fallback in interview delivery.

## 5. Acceptance (the castjuicy method)
Hand-author a small whodunit with: 3-4 `at_scene` suspects (incl. the first witness), 2-3
discoverable off-scene suspects (each named by an at_scene clue), culprit reachable. Drive it
live: confirm (a) the opening presents the at_scene suspects and the first witness introduces
the cast; (b) the player can interrogate them and clues land; (c) an interview NAMES an
off-scene suspect, a route opens, the player travels and questions them; (d) coverage builds to
a genuine (non-`quiet_failure`) conclusion with the culprit surfaced. Log + surface to founder.

## 6. Out of scope (flagged)
- The EXAMINE/EXPLORE delivery channel build (separate SHAPE-STRUCTURES round) — §3e only
  states the narration-first PRINCIPLE it must honor.
- Non-Deduction shapes (Bond/Quest/etc.) — this is the Deduction investigation shape; the
  per-genre "what makes good live fiction here" answer differs (founder's macro).
- The appositive-`name` matcher hardening (Cx 053 non-blocking) — banked.
