# The EXAMINE Channel — physical clue inspection as an earned clue economy

**Status:** SPEC for Cx review. Founder-directed ("physical clues need further inspection to
determine details that can be correlated"; examination is genre-core — think Clue/Sherlock) +
Cx 065 fiction-improvement #2 (the live baseline's physical examination was atmospheric, not
evidentiary — it trained the player that inspection yields "nothing definite"). Targets the
lowest baseline dimensions: Fair-play (6.7), Genre-faithfulness (7.3), Spine (7.2). Host-side
over the read-only pattern-buffer engine; mirrors the already-shipped ASK channel.

## 1. Why
The investigation shape today delivers clues through ASK only (question a present person →
`learn_clue_items` into `knows:<protagonist>`). But a real investigation is half physical:
examine the body, the tea tray, the doctor's bag, the ledger — and *correlate* what you find.
The live baseline (`logs/harness-1782277324.md`) showed the player examining the saucer, hearth,
cellar, footprints, papers — all yielding atmosphere but NO earned evidence, because there is no
delivery channel for inspection. This builds it: EXAMINE is to objects/sites what ASK is to
people.

## 2. Principles (founder)
- **Earned, not spoon-fed.** A physical clue surfaces only when the player INSPECTS the object
  with intent (looks closely / searches / examines), not from a passing glance. Surface/ambient
  detail is free; the *evidentiary* detail is earned (mirrors ASK's `pressure`).
- **Correlatable detail.** An examine-clue yields a concrete particular (a missing vial slot in
  the doctor's bag, carbolic residue on a cuff, an altered figure in the ledger, a torn
  appointment leaf) that COMBINES with testimonial clues to fill a pillar — the player connects
  them; the narrator's deduction weaves the correlation.
- **Narration is ground truth; objects serve the ledger.** What the prose presents is accurate
  and comes first. A CLUE-bearing object yields its authored evidence on inspection; a plain
  object yields plausible improvised/atmospheric detail (resolve-and-commit,
  [[improv-and-authority-model]]) that does NOT fill a pillar. Objects gate solvability ONLY
  when the scene explicitly made them clue-bearing. Never fabricate evidence.
- **Lazy player earns little.** Don't inspect → don't find. Correct.

## 3. Model — objects/sites as clue holders (the hybrid-node work)
A `Clue` can be held by an OBJECT or SITE, not just a person (the hybrid-node gap flagged in
`SHAPE-STRUCTURES.md` / Cx 032/036). Minimal v1:
- The clue's HOLDER id may be an `obj:*` or `place:*` (e.g. `obj:doctors_bag`,
  `place:study_desk`), in addition to `person:*`.
- Its `surface_fact` is the evidentiary particular (e.g. `obj:doctors_bag · vial_slot ·
  empty (a digitalis vial is missing)`).
- Reveal gating: a new/used condition `examined` (or reuse `object_seen`, currently gated OUT
  of solvability) becomes LIVE-reachable through this channel. A clue may require close
  inspection (`scrutiny`, the EXAMINE analogue of `pressure`) vs. a glance (`none`).
- The object must be PRESENT/reachable (in the scene, or a reachable site) — the same presence
  rule as NPCs (a clue on an unreachable object can't be examined → the staging gate must treat
  object reachability like holder reachability).

## 4. Delivery — mirror of the ASK interview block
In `turnloop.run_turn`, alongside the interview-delivery block:
1. **Detect an EXAMINE action.** `classify` already extracts a target for actions; add/confirm
   an `examines` target (or detect via verb + `world.refer` of the object: inspect/examine/
   search/look closely/study/check). Scrutiny = the EXAMINE analogue of `_is_pressing` (close
   inspection vs. glance).
2. **Resolve + presence-gate the target object/site** (must be present/reachable, like an NPC).
3. **Surface its revealable clue(s)** via `revealable_clues`-analogue gated on `examined`/
   `scrutiny`, written with `learn_clue_items` into `knows:<protagonist>` — EXACTLY the ASK
   write, just triggered by inspection. Genuine-first ordering + one-fresh-per-turn trickle
   carry over.
4. **Discovery also applies:** an examined object can NAME an off-scene suspect/place (the
   missing-vial points at the doctor's surgery) → the same `whereabouts` discovery write.
5. **Plain (non-clue) objects:** no pillar fill — the narrator improvises atmospheric detail
   (resolve-and-commit), honestly "nothing decisive here," never fabricated evidence.

## 5. Authoring — `author_cast` emits object/site clues
Per the per-fiction shape (NOT a formula): some clues live on people (ASK), some on objects/
sites (EXAMINE). `author_cast` authors physical evidence cards with: holder = `obj:*`/`place:*`,
the evidentiary `surface_fact`, the `examined`/`scrutiny` condition, a non-spoiling `hook_text`
("the doctor's bag sits open, one loop conspicuously empty"), and optional `names`-an-off-scene-
suspect for the discovery chain. The juicy-card mandate + don't-spoon-feed balance apply
(evidentiary detail = scrutiny; ambient = none).

## 6. Solvability — object reachability + examine-liveness
Extend `check_solvability` (and `_reachable_nodes`) so:
- `examined`/`scrutiny` are LIVE reveal conditions (so an object-sourced genuine clue COUNTS).
- An object/site holder is reachable iff it is at_scene, in a reachable site, or named-and-
  reachable (the same presence/discovery logic as people — generalize the holder check from
  `person:` to any holder id).
- The culprit-converges + every-required-holder-reachable gates apply to object holders too.

## 7. Correlation in the conclusion
Coverage already combines distributed clues into pillar coverage (correlation is structural).
The CONCLUSION's deduction briefing should explicitly WEAVE the physical + testimonial clues
("the missing vial in his own bag, the carbolic on his cuff, and the butler placing him alone
at the study — together they close on the doctor") so the correlation is FELT, not just tallied.

## 8. Acceptance (the castjuicy method) + re-score
Hand-author a demo where a REQUIRED pillar (e.g. `means`) is covered genuine ONLY by a PHYSICAL
clue earned through EXAMINE (examine the doctor's bag → the missing digitalis vial), reachable
only after discovering+visiting the surgery. Drive it live: confirm (a) inspecting the bag
surfaces the evidence, (b) a glance does not (scrutiny-gated), (c) plain objects yield atmosphere
not evidence, (d) the conclusion correlates physical + testimonial. Route the transcript to Cx
for a RE-SCORE against the 7.2 baseline — fair-play and genre-faithfulness should rise.

## 9. Build order
1. Object/site clue holders in `cast.py` (Clue holder may be obj/place; `examined`/`scrutiny`
   conditions; `_live_reachable` + reachability generalized from `person:` to any holder).
2. EXAMINE delivery block in `turnloop.py` (mirror the ASK block; scrutiny detector; presence
   gate; discovery write).
3. `author_cast` object-clue authoring + the solvability extension.
4. A hand-authored demo + live validation + Cx re-score.
Coordinates with the in-flight turn-latency Levers (touches `turnloop.py`/`cohorts.py`/`cast.py`)
— integrate after Lever 4 lands to avoid stepping on it.

## 10. Out of scope
ACT/RELATE/CHOOSE channels (other shapes' delivery — the per-genre rounds); a full typed-Card
refactor (this does the minimal obj/site-holder generalization, not the whole taxonomy).
