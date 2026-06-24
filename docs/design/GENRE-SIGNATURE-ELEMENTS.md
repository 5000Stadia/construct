# Genre Signature Elements — embody the spirit, don't engine it

**Status:** SPEC for Cx review (design round). Founder steer, 2026-06-24
([[genre-signature-elements]]). Supersedes the §8.4 cross-suspicion *engine* and the
red-herring *generation lane engine* — both retired as overbuilding.

## The principle

When something is so fundamental to a genre that you reach for a system to manufacture it
(red herrings, cross-suspicion for mystery), that is the tell that it is the **spirit of the
genre** — and the spirit is **embodied**, not engineered. So, for every genre: identify its
**signature elements** (the handful of things that *are* the genre), and emphasize them through
two channels the **shape** already carries — never a bespoke per-element builder.

1. **Author-insist (build time).** The shape demands these elements already EXIST in the
   authored fiction. A generated mystery isn't "solvable + correct + done" — it must *have*
   cross-suspecting suspects, conflicting alibis, and planted red herrings. This is a directive
   on the authoring cohorts (`author_cast`, world-build), not a new generator.
2. **Narrator-emphasize (runtime).** The shape's signature is handed to the narrator so live
   improv leans into it. Red herrings and "live corollary details" are *ideal* improv material —
   the narrator plants and plays them in the moment.

Both channels are governed by what we already shipped: authoring fairness/solvability checks,
and the [[improv-serves-the-destination]] doctrine at runtime (an improvised thread either
serves the destination or is curtailed before creation).

## Why this dissolves the two "engines"

- **Red herrings → narrator-emphasize (live improv).** The engine's whole problem was the
  reachable-debunker contract (a false lead the player can't disprove is a dead-end). That
  problem *vanishes* when the narrator improvises the red herring: it owns both ends — plants it
  AND lets the player see through it (resolve-and-commit). make-it-real already governs it: a red
  herring that pays off *serves*; a dead-end one is *curtailed before creation*. No contract, no
  engine. (Authored red herrings — see Deduction below — are the author-insist half.)
- **Cross-suspicion → author-insist + narrator-emphasize.** Instead of a deterministic
  sparse-graph synthesis call, `author_cast` is told "suspects must point at each other, carry
  alibis, some misleading," and the narrator is told to *play* that web. The richness lands as
  fiction, not as graph metadata. The cast already lives in `knows:<npc>` frames — a suspect's
  suspicion of another is just ordinary knowledge that surfaces when they're questioned.

## The model

A per-shape `signature_elements` list on the 9 shapes in `construct/story_shapes.py`. Each
element:

```
{ "name": <short id>,
  "element": <one-line description of the genre-true element>,
  "channels": ["author-insist" | "narrator-emphasize" | both] }
```

- **Home = the 9 SHAPES, not the 155 cards, not a new layer.** 155 flavors ride 9 engines;
  enrich an engine → all flavors inherit. Tone/diction/setting stay on the flavor card; the
  *structural spirit* attaches to the shape. The seams already exist (`_SHAPE_LINE`,
  `shape_directive()`, `SHAPES[...]["medium"]`).
- Blended worlds (primary + secondary shapes) union their signature elements, same as
  `shape_directive` already unions `_SHAPE_LINE`.

## The nine shapes' signature elements

Drawn from each shape's `medium`/`payoff` (story_shapes.py) + STORY-SHAPES-CATALOG richness.
`A` = author-insist, `N` = narrator-emphasize.

### deduction (mystery / investigation)
- **red_herrings** (A+N) — at least one planted false lead with a tell; the narrator may improvise
  more live, each debunkable in play (never a dead-end).
- **cross_suspicion** (A+N) — suspects point at one another; the narrator plays the web so
  testimony must be weighed.
- **alibis_and_contradictions** (A) — suspects carry alibis that corroborate or conflict; the
  contradictions are the trail.
- **the_culprit_present_and_surfaceable** (A) — the answer is reachable in play, never offstage.
- **the_earned_reveal** (N) — already in `_SHAPE_LINE`; reveal only when assembled.

### bond (relationship / intimacy)
- **earned_intimacy_beats** (N) — connection built through vulnerability/gesture, never declared.
- **real_friction_that_tests** (A+N) — a genuine source of conflict between the parties, pressed live.
- **the_costly_gesture** (N) — connection is proven by a choice that costs something.
- **a_two_sided_other** (A) — the other party has their own wants and wounds, not a mirror.

### endurance (survival / horror)
- **mounting_threat** (N) — pressure escalates; relief is never freely granted.
- **scarcity_and_resource_pressure** (A+N) — real constraints authored, spent and felt live.
- **the_clock** (A) — a deadline/closing window (the shape's soft conclusion clock).
- **isolation** (A+N) — help is far; the protagonist is thrown on their own resources.
- **the_glimpsed_dread** (N, horror blend) — the threat is felt before it is seen.

### contest (competition / combat / proving)
- **escalating_rounds** (N) — each challenge harder than the last; victory fought for.
- **the_worthy_rival** (A) — an opponent with their own arc and credibility, not a punching bag.
- **preparation_pays** (A+N) — scouting/training authored and made to matter.
- **scoreboard_vs_meaning** (N) — the meaningful win may differ from the literal result (Rocky).

### gambit (schemes / politics / heist)
- **factions_with_competing_agendas** (A) — real players whose interests cross.
- **the_plan_and_its_execution** (A+N) — a scheme with moving parts that the player works.
- **complications_force_adaptation** (N) — the board shifts; improvise around the break.
- **the_concealed_twist_or_betrayal** (A+N) — planted, kept hidden until it lands.

### discovery (exploration / wonder / cosmos)
- **gradual_unfolding** (N) — place and meaning revealed in layers, never front-loaded.
- **the_sense_of_wonder** (N) — awe is the payoff; let it breathe.
- **the_place_as_character** (A) — a richly-layered, internally-coherent place authored to explore.
- **the_cost_of_knowing** (A+N) — understanding has a price; arrival is not free.

### mastery (craft / building / procedure)
- **incremental_competence** (N) — skill accrues through practice; never granted.
- **setbacks_that_teach** (A+N) — authored failure points that advance understanding.
- **a_clear_standard** (A) — an explicit bar/benchmark the work is measured against.
- **the_made_thing_or_run_system** (A) — a concrete artifact or system as the payoff.

### farce (comedy / chaos)
- **mistaken_identity_or_cross_purposes** (A+N) — a misunderstanding engine seeded and stoked.
- **compounding_complications** (N) — each fix makes it worse; the snowball is the point.
- **comic_timing_and_the_blowup** (N) — escalate toward the set-piece blowup; don't resolve early.
- **false_coverage_is_engine_live** (A) — the comic premise running (`fail_forward`) is the
  desired state, not a failure (already in `cost_disposition`).

### transformation (moral / identity / mythic)
- **the_defining_choice** (A+N) — a real dilemma with stakes, pressed live.
- **the_ordeal** (N) — change is forced through hardship, not comfort.
- **the_cost_of_change** (N) — becoming someone new costs the old self something.
- **proven_by_action_not_declared** (N) — the changed self is shown, never merely stated
  (already in `_SHAPE_LINE`).

## Wiring (minimal — no new engine)

1. `construct/story_shapes.py`: add `SHAPE_SIGNATURE: dict[str, list[dict]]` (the catalog above).
2. **Narrator-emphasize:** extend `shape_directive(game_types)` to append the primary+secondary
   shapes' `narrator-emphasize` elements as briefing lines (they ride the existing STORY SHAPE
   block the narrator already gets every turn).
3. **Author-insist:** new `author_signature_directive(game_types) -> str` listing the
   `author-insist` elements; fed into `cohorts.author_cast` (and the world-build authoring
   prompt) so generated fiction is required to establish them. The existing solvability/viability
   gates remain the safety net.
4. No `CastNode`/schema/grammar changes required for v1 (cross-suspicion rides existing
   `knows:<npc>` seeding via the author directive; a structured field is a *possible* later
   refinement, not needed to embody the spirit).

## Acceptance (per the make-it-real method)

Per genre, a live run shows the signature elements (a) **present** because authoring established
them and (b) **emphasized** because the narrator played them — judged by the live transcript +
a Cx fiction score per shape, against each genre's own bar. Deduction first (it has the live
baseline), then the other eight. The win is "the genre feels embodied," not "a system produced
the element."

## Out of scope (retired)
- The deterministic cross-suspicion synthesis engine (§8.4 sparse-graph + one synthesis call).
- The red-herring *generation lane* engine (the reachable-debunker contract).
Both are replaced by author-insist + narrator-emphasize above.
