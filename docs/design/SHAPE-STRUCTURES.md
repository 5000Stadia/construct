# Shape Structures — card types & delivery channels across all nine engines

## Shapes are composable LAYERS, not exclusive buckets (founder, 2026-06-23 — the reframe)

A story is NOT one shape. It is a STACK of shape-layers, each contributing its cards, delivery
channels, and pillars SIMULTANEOUSLY. A whodunit detective is also on a personal QUEST (an arc,
a reckoning); a knight's quest is full of MYSTERIES (the artifact's secret, the enemy's hidden
weakness). The nine "shapes" below are therefore a LIBRARY of layerable structures — a story
COMPOSES from several (a primary + secondaries), not picks one bucket.

This already matches the engine: `shapes_for()` returns a primary + secondary shapes (anchor =
deduction + gambit) and the narrator disciplines blend. The reframe extends that to the
card/structure level: a world's cards = the UNION of its active layers' card types; its pillars
= the union of their causes; its delivery = whichever channels those layers use.

THE SPAN THE MODEL MUST COVER (founder, 2026-06-23): a contained **Sherlock whodunit** (ONE
movement — investigate → name the killer → done; saga machinery dormant) ↔ a **there-and-back
epic** ("across the lands of X, over the seas of Y, to face the peril at Z, and home again").
The epic = a SAGA of four movements with an evolving trajectory toward a ROUND-TRIP grand
destination (face Z AND return changed): (1) lands of X — discovery/quest, wonder/rising hope;
(2) seas of Y — endurance, hardship/dread; (3) peril at Z — contest/transformation, the dark
crux; (4) home again — transformation payoff, bittersweet wisdom. The "return home" is the tell
it's a saga, not a single movement (the conclusive scene is the round trip, not just the
climax). PROPORTIONALITY HOLDS AT BOTH ENDS: the epic is MORE movements, each still a tight
handful (lands-of-X is a contained quest, not a sprawl) — never an inflated single arc. Same
atom throughout; the saga chains proportional movements with an evolving trajectory.

Worked: **whodunit + quest layer** = deduction cards (suspects/clues, ASK/EXAMINE — solve it)
PLUS a transformation layer (the detective's wound, a temptation, a costly choice, ACT/CHOOSE —
an arc): solve the murder AND be changed by it. **quest + mystery layer** = transformation/
contest cards (trials/allies/the dragon, ACT/CHOOSE) PLUS a deduction layer woven through (the
artifact's true nature, the enemy's secret weakness, EXAMINE/ASK): journey AND deduce.

BUILD CONSEQUENCE (cleaner, not harder): `author_cast` does NOT branch to one shape — it
COMPOSES cards from the active stack (primary + secondaries), drawing on the per-layer library
below. weave_pick / floor / conclusion are already generic over "whatever cards exist," so they
don't care the cards came from two layers. Even a "pure" whodunit gains depth from a light
character-arc layer. The conclusion-as-effect then weaves the LAYERED resolution (the case
solved + the detective changed).

---

The generalization plan for the card system (CARD-WEAVING.md) beyond investigation. The
governance (weave_pick / floor / master-judgment / conclusion-as-effect) is already shape-
blind. What's still investigation-shaped is **(a) the card TYPES** (today: people-with-clues
only) and **(b) the DELIVERY CHANNEL** (today: interview only — `revealable_clues` →
`learn_clue_items`). This doc pins both for each of the nine shapes (the structural categories
the 155 flavors ride), so the cast-authoring + delivery generalize. Founder-directed,
2026-06-23.

## The unifying insight: five delivery channels

A "card" is a unit of interest the narrator weaves; a "pillar" (cause) fills when its
condition holds in the player frame / world. Across all genres, pillars fill through a small
set of **delivery channels** — the player ACTION that converts a proposed hook into earned
coverage:

| Channel | The player… | Pillar condition (Expr) | Already in the turn loop? |
|---|---|---|---|
| **ASK** | questions a present person | `InFrame(knows:player, …)` via `learn_clue_items` | YES (interview delivery — the only one built) |
| **EXAMINE / EXPLORE** | inspects an object/site, reaches a place | `Located(...)` / `InFrame` from a look | mostly (movement + furnish; needs a "learn on examine" write) |
| **ACT** | overcomes a trial, performs, survives, executes | `Occurred(event)` / `StateIs(...)` | YES (action resolution → events/state; beat_pass reads it) |
| **RELATE** | shares a moment, meets/offers vulnerability, a gesture | `InFrame(knows:player, …)` from a relational beat | partial (dialogue exists; the beat-write is the gap) |
| **CHOOSE** | commits / compounds / refuses under pressure | `Occurred` / the conclusory commitment | YES (commitment + classify `commits`) |

**The crucial realization:** `Pillar.genuine_via` is an arbitrary `Expr`, and the turn loop
already fills beats/pillars through movement, action-resolution events, and the commitment. So
**most channels need NO new delivery code** — the pillar condition just reads the state the
normal turn already writes. The card-weaving's job for a non-people card is to **propose the
hook** (foreground the trial/place/temptation) and let the player ACT; coverage fills through
the existing channel. The only explicit delivery write is ASK (interview); EXAMINE and RELATE
need a small "learn on look / learn on relational beat" write analogous to `learn_clue_items`.

## Per-shape structure (card types · delivery · pillar-fill · floor)

| Shape | Card types | Delivery channel(s) | A pillar fills when… | Proposal floor (hooks) |
|---|---|---|---|---|
| **Deduction** | suspects, clues, alibis, red herrings | ASK + EXAMINE | a clue fact is in `knows:player` | each suspect's why-suspect |
| **Bond** | relationship circle (target/rival/confidant/gatekeeper), vulnerability beats, the obstacle | RELATE + CHOOSE | a mutual-vulnerability / obstacle-confronted / trust-held beat is in the player frame | each relationship's stake & tension |
| **Endurance** | threats, resources, companions, refuges *(hybrid: world/canon)* | ACT | a refuge reached / resource secured / companion kept / costly line held (state+event) | each looming danger & scarcity, felt |
| **Contest** | rivals, mentor, the standard, the cost | ACT (train/perform) + EXAMINE (scout) | competence-through-setback / rival-tell scouted / personal standard met | each rival's edge + the standard |
| **Gambit** | crew (specialties), mark's defenses, leverage, the twist | ASK + EXAMINE (case) + ACT (execute) | defense mapped / crew aligned / leverage secured / contingency set | each obstacle + each turnable asset |
| **Discovery** | sites/strata *(hybrid)*, guides, competing explanations | EXAMINE/EXPLORE + ASK | strata observed / theories weighed / the reframe grasped | each deeper layer + each rival theory |
| **Mastery** | the material/system *(hybrid: its resistances+standard)*, mentor/rival/judge | ACT (practice/perform) + JUDGE | fundamentals-through-setback / standard met / cost reckoned | the standard + each setback's lesson |
| **Farce** | the ensemble's cross-purposes, lit fuses, the misunderstanding | CHOOSE/ACT (compound or defuse) + the forced deadline | the comic engine is LIVE (false-coverage) at the blowup | each fuse + each mistaken belief, ticking |
| **Transformation** | catalyst/mirror, temptation-back, the one-saved, cost-embodiment | CHOOSE + ACT (a costly deed) | old-self-seen / temptation-refused / change-proven-by-deed / wrong-made-right | each moral pressure, made felt |

Quest = Transformation+Contest+Discovery in blend; its cards (trials/places/allies/
temptations) and ACT/CHOOSE delivery fall straight out of those rows.

## Implementation plan (what to build)

1. **Typed cards (the hybrid-node work).** Generalize the card from "clue on an NPC" to a
   typed `Card`: `person|clue|place|object|trial|threat|resource|companion|temptation|
   relationship_beat`. Each carries a `hook_text` (the weave proposes it) + a `fill_condition`
   (the `Pillar.genuine_via` atom it advances) + its delivery channel. People-cards keep
   today's `knows:<npc>` seeding; world/canon cards (place/threat/resource/site/material) ride
   canon state (Cx 032/036 hybrid-node gap — finally built here).
2. **Delivery generalization (mostly free).** ASK stays `learn_clue_items`. EXAMINE and RELATE
   get a small "learn on look / learn on beat" write (same shape: surface_fact → player frame,
   under the protected-key gate). ACT and CHOOSE need NO new delivery — the pillar's
   `Occurred`/`StateIs` condition reads what action-resolution / movement / the commitment
   already write. So `beat_pass`/`arc_coverage` fill them with zero new code.
3. **Shape-aware `author_cast`.** Branch the authoring by `primary_shape`: emit the right card
   TYPES + fill-conditions + delivery per the table above (a Bond authors a relationship
   circle with RELATE beats; an Endurance authors threats/resources/refuges with ACT
   conditions; a Mastery authors a resistant material with practice setbacks). The juicy-card
   mandate + the solvability gate generalize per shape.
4. **weave_pick + floor: already generic** — they work on any cards with hooks; no change.
5. **Conclusion-as-effect: already generic** — coverage over any pillar conditions.

So the generalization is concentrated in (1) typed cards + (3) shape-aware authoring; delivery
(2) is largely a read over existing turn-loop writes. Route to Cx as the next design round;
then build per shape and validate each with a small hand-authored world (the castjuicy method),
starting with a Bond (romance — the furthest from investigation) and a Quest.
