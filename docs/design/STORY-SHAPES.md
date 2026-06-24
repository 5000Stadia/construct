# Story Shapes & the Tension-Thread (Card) Model

**Status:** design-first, **mesh-reviewed** (Cx 024/025 YELLOW→GREEN-able with the two
corrections below folded in; no PB primitive). This is the **genre layer** the win-model
(`STORY-SHAPE-AND-RESOLUTION.md`), convergence, and reveal system sit on. It **supersedes
the structural-absence concealment approach** in that doc's §4–§6 (see "Why cards beat
the vault").

**Origin:** an 18-turn cold-play harness on the fixed anchor world was *coherent but
dramatically inert* — 18 turns of procedure, no convergent trail, a baseless climax. The
engine had texture and no **story engine**. The fix is a known destination + a woven
trail — generalized across genres.

---

## 0. The governing tenet (above all the mechanics)

**Be adaptable; serve macro-level, genre-appropriate engagement.** Every rule below —
pillars, the cost-ledger, grading, triggers — is *scaffolding for the experience, not
law.* When a genre's fun demands bending or overriding a mechanic (comedy's fail-forward,
a cozy game that never wants peril, a tragedy that *wants* the fall), the engine bends.
The macro question — *is this engaging and interesting for THIS story?* — overrides any
single rule. (Founder, the recurring north star.)

## 0a. The conclusion model — effect, not verdict (founder, deepened)

The conclusive scene is **not a success/fail check**. It is the **narrated consequence of
the causes the player put in place.** We never ask "did you win?"; we ask "**what do the
established causes produce?**"

- **Pillars are the *causes*** — a set of causal elements (motive, means, the connection;
  shared vulnerability, the obstacle confronted; shelter, route, threat). They are
  **fillable** (established through open-ended play), **changeable** (the living-world can
  invalidate or relocate one), and tri-state: **genuinely filled / falsely filled (a red
  herring held as true) / unfilled.**
- **The conclusive scene is the *effect*** of those causes, narrated. A sound case → the
  culprit is brought to justice; a case built on a red herring → the *wrong* person goes
  down and the truth festers (the epilogue twist reveals why). Both flow causally; neither
  is "you lose."
- **Premature/baseless commitment = a *consequence*, not a solution.** "You did it" with
  the pillars unfilled is dismissed, backfires, tips off the culprit — the world pushes
  back; the story does not conclude.
- **The conclusion's character is the *integral of the whole run* —** the accumulated cost
  (botched draws, falsely-filled pillars, collateral, ruptured bonds) colors it. A right
  answer dragged through wreckage comes out **pyrrhic/perilous**; a clean run, triumphant.
  **A perilous conclusion is a feature** — the richest seed for the next episode
  (**redemption**), handed to the Series engine as the next arc's pillars.
- **The climax weaves in the emergent** — the improvised side-thread, the relocated beat,
  the thing the player+world made up together. The conclusion reads the *actual woven
  story* (narrative memory, living-world developments), not a pre-authored room.

### The three per-shape conclusion dimensions (composable, under the governor)
| Field | Values | Notes |
|---|---|---|
| `conclusion_trigger` | `pillars` · `commitment` · `event_deadline` · `choice` | mystery/bond = pillars+commitment; farce/endurance often = event/deadline (the king arrives, the storm hits — the climax is *forced*); transformation = the moment of choice. |
| `cost_disposition` | `peril_redemption` · `fail_forward` · `repair` · `sacrifice` | how the cost-ledger colors the ending: drama accrues peril→redemption; **comedy fails *forward*** (cost is the comic fuel); bond ruptures-and-repairs; endurance pays in sacrifice. |
| `pacing` / `clock` | `none` (untimed) · `soft` · `hard` (+ a deadline in turns/story-time) | **nestable** — a hard-clock bomb sequence inside an untimed investigation; a soft clock as the king's dinner nears. Leverages the existing diegetic-clock + refusal-timeout machinery. |

### Worked conclusions
- **Leisurely whodunnit:** `pillars/commitment` + `peril_redemption` + `untimed` (soft
  refusal backstop). Build the case; a wreckage-strewn solve → a redemption next episode.
- **"King comes to dinner" farce:** `event_deadline` + `fail_forward` + `soft` clock — the
  king arrives regardless; the pile of catastrophes pays off as a warm, drunken, ridiculous
  triumph (he had you confused for someone else; everyone laughs).
- **Batman, 10 minutes:** `event_deadline` + `hard` clock **nested** at the climax of an
  otherwise-untimed detective arc — at zero the bomb fires; defuse or fail.
- **Romance:** `pillars` (vulnerability, obstacle, trust) + `repair` + `untimed` — the
  declaration's withheld until the relationship pillars are met; the rupture-repair is the path.

## 0b. The render-craft floor (founder, from live harness 1782183453)

The pillar mechanics produce a spine; these keep the *narration* human. Binding on
every render (`cohorts.PROTAGONIST_COMPETENCE`, `WORLD_IS_PEOPLED`, and the hold-mode
`NEUTRAL ON THE ANSWER` directive).

1. **Volunteer the protagonist's competence.** The character knows their own trade,
   routines, customs and layout. The narrator states that knowledge directly in second
   person ("You know the drill: night transfers go through the duty register first") — it
   must **never** make an NPC recite, out of character, what the protagonist would already
   know. Competence is already seeded into `knows:<protagonist>` (minus the protected
   answer): **competence seeded, secret withheld.**
2. **A peopled, emotional world.** Characters are people, not policy-machines. They react
   with proportionate emotion — above all when something *lands* on someone (an accusation
   stings/enrages; a kindness softens) — and their stance toward the player shifts and
   carries forward. Bureaucratic texture never substitutes for a human response.
3. **Neutrality is *epistemic*, not affective.** The hold-mode discipline keeps the
   narrator neutral about the *answer* (don't weight the evidence/verdict, don't give it
   away) — it is **not** a flattening of feeling. (Root cause of the robot-world in the
   harness: the old "present FLATLY" wording bled "flat" into character affect.)
4. **A real cast is the surface pillars fill through.** A whodunit needs 5–10 people who
   each hold a piece of the crime's detail, carry their own alibi/innocence evidence,
   cross-suspect one another, and drop clues (some true, some red herrings). Generalized:
   the cast is *how you cover pillars* — you interview people to establish causes.
   Cast-node shape + clue→pillar distribution + the cross-suspicion web → conferring with
   Cx; folds into session-zero world-population for the pillar build.

## 1. The card model (replaces the vault)

A secret/tension is a **story-element card** the narrator *works with*, not a fact hidden
behind a gate. The narrator-as-DM **knows the destination**, lays a **trail** toward it,
and is simply told *"don't blurt the unearned payoff."* The one hard guard is against
**brute-force** ("who did it — tell me!") → deflect.

**Why cards beat structural absence (overturns Cx-022/Kernos-Q2):**
1. **The leak was the SEED, not a blurting DM.** The original anchor leak was the
   build pre-loading the answer into `knows:player`; the narrator faithfully reported what
   the player was *seeded knowing*. Fixed at the seed (`seed_character_frames` strips the
   protected answer from the protagonist). So the "told-DM-blurts" failure was never
   actually observed.
2. **You cannot foreshadow a destination you don't know.** A clue-trail is *backward-
   designed* from the reveal; a narrator kept ignorant of the answer can only emit
   atmosphere, not clues that converge. (The Joker-bomb test: you can't pepper in clues
   pointing at "bomb at the gala in 2h" if the narrator doesn't know it's coming.)
So: the DM knows the cards; "don't blurt the unearned" + brute-force deflection are the
guard; the old strict promotion gate demotes to an optional silent backstop.

## 2. The universal tension-thread + principles

A story = a few live **tension threads**. Each thread has: a **source**, a **path** the
player engages, **escalation**, and an **earned payoff**. The "clue-trail card" is the
*Deduction* instance; every shape is a thread with a different medium.

**Universal principles (true for every active story thread):**
1. **A known destination per active story/opportunity thread.** *(Cx correction #1:
   NOT every world — sandbox/freeplay has no global terminal; it runs ambient until a
   thread worth concluding is minted. `contract == "story"` gates a terminal, per
   `CONCLUSIVE-OUTCOME-SPEC.md`.)*
2. **Threads are the unit:** source → path → escalation → earned payoff.
3. **Earn the payoff — never hand it.** The universal that "don't blurt the secret" was
   one case of: *the player does not get a thread's terminal value before its genre
   condition is satisfied.* Deduction withholds the answer; Bond the unearned intimacy;
   Endurance relief; Contest the victory; Gambit the plan landing; Discovery the
   wonder; Mastery the made thing; Farce the blowup; Transformation the changed self.
4. **Escalation** toward the payoff (each type's directive already names its shape).
5. **Adaptive placement** — weave the next beat where the player actually is.
6. **Convergence to a conclusory scene** — threads bend to the genre's climactic moment;
   the player commits; they may FAIL.
7. **Dwell / compress** — per-type (already authored in the 155 directives).
8. **The player drives & may fail their way there** (wrong accusation / blown romance /
   death / botched heist / refused change).

## 3. The nine shapes (engine behaviors)

Build ~9 **behavior modules**; *compose* them per card (Cx correction #2 — shapes are
**blendable**, type-level, NOT a family→one-shape map).

| Shape | Families (primary) | Path medium | Withheld | Commitment kind (capture) | Judgment | Payoff |
|---|---|---|---|---|---|---|
| **Deduction** | Investigation; Puzzle/Decoding; Communication/Interpretation | clues, evidence, contradictions | the answer | accusation/solution (`claim:`) | claim-vs-fact + support | the reveal/twist |
| **Bond** | Social/Relationship/Intimacy | emotional beats: vulnerability, friction, gesture | unearned intimacy/rupture | declaration/refusal (relational **state**) | relationship/consent-vs-consequence | earned connection or rupture |
| **Endurance** | Survival/Scarcity; (Horror w/ Discovery) | mounting threat + clock | relief/safety | stand/route/sacrifice (achieved **state** `survived`) | action-vs-threat/resource | outlast / escape / fall |
| **Contest** | Action/Combat/Pursuit; Competition/Status | escalating challenges, opponents | the victory | decisive move / completed contest | score/objective (genre-victory ≠ scoreboard) | win / loss / proved |
| **Gambit** | Politics/Factions; Schemes/Infiltration; Transgression/Power | leverage, maneuver, complications | your hand + the twist | execute plan / reveal hand (`plan_executed`) | plan-vs-board | lands / collapses / power shifts |
| **Discovery** | Exploration/Wonder/Place; (Time/Reality w/ care) | unfolding of place/cosmos/meaning | the wonder/understanding | cross threshold / choose meaning (`understood`+`chose`) | arrival/understanding/cost | awe / understanding |
| **Mastery** | Creativity/Craft/Performance; Stewardship/Building; Professional/Procedural | incremental competence + setbacks | the achievement | perform/deliver/stabilize (`performed`/`delivered`) | artifact/job/**system** state (subtype it) | the made thing / run system |
| **Farce** | Comedy/Farce/Chaos | compounding complications | the blowup | confess/cover/final-improv (comic-resolution) | comic order / harm / exposure timing | punchline / comeuppance |
| **Transformation / Trial** | Mythic/Spiritual/Symbolic; Moral/Psych/Literary Drama | ordeal / choice / identity | the changed self (proven, not claimed) | value-choice / act of identity (`transformed`/`chose`, **demonstrated**) | identity-vs-ordeal, proven by act | who you become — redemption or fall |

**Blends are first-class** (a card has `primary_shape` + `secondary_shapes`): Horror =
Endurance+Discovery; Mythic = Transformation+Discovery; Whiplash = Mastery+Transformation;
anchor = Deduction+Gambit (mystery+political intrigue).

## 4. The card / thread profile schema

Per card (host-side control data — never canon; lives on the game-type/profile layer):
```
primary_shape    : one of the 9
secondary_shapes : [..]                 # blends
withheld_kind    : answer | intimacy | relief | victory | hand | wonder |
                   achievement | blowup | changed_self | (none, for low-tension)
commitment_kind  : claim | relational_state | achieved_state | executed_action |
                   choice_identity | comic_resolution | understanding   # capture FORM
                   #  (Cx: NOT every commitment is a claim: fact)
judgment_type    : claim-vs-fact | relationship-vs-consequence | action-vs-resistance |
                   score-vs-objective | plan-vs-board | arrival-vs-cost |
                   artifact/system-state | comic-order | identity-vs-ordeal
payoff_kind      : the earned terminal value (per shape)
contract_scope   : story_thread | opportunity_thread | sandbox_ambient   # Cx #1
clue_trail / beats : the path (Deduction: clues; Bond: emotional beats; etc.) — backward-
                     designed from the payoff; ≥3 redundant fragments (three-clue rule);
                     escalating; adaptively placed.
```

## 5. Worked examples (the reference — keeps each shape honest)

| Shape | Fiction | Withheld | Commitment (capture) | Payoff |
|---|---|---|---|---|
| Deduction | *Knives Out* | who/how | accusation (`claim:`) | reveal + twist; wrong→framed party, epilogue reveals misread clue |
| Bond | *Pride & Prejudice* | unearned union (1st proposal *refused* — premature) | declaration met (relational state) | earned union / rupture |
| Endurance | *The Road* | relief/safety | stand/route/sacrifice (state `survived`) | outlast at cost |
| Contest | *Rocky* | the victory | go the distance (completed contest) | **proved himself** (loses decision, wins story) |
| Gambit | *Ocean's Eleven* | the hand + twist | pull the job (`plan_executed`) | lands, *with* the how-reveal |
| Discovery | *Arrival* (+Transformation) | the meaning | cross threshold / choose (`understood`+`chose`) | revelation + embrace the cost |
| Mastery | *Whiplash* (+Transformation cost) | the achievement | perform (`performed`+quality) | transcendent set, at a cost |
| Farce | *The Hangover* | the blowup | confess/recover (comic-resolution) | punchline; **blowup IS the payoff** |
| Transformation | *A Christmas Carol* | the changed self | choose + act (`transformed`, demonstrated) | redemption / unmourned fall |

**What the examples prove:** commitment-capture form genuinely differs per shape;
blends are real; genre-victory ≠ literal win (Rocky) and failure-can-be-payoff (Farce);
Transformation needs its own slot.

## 6. Revised build sequence (each its own pass + review)

1. **Shape/profile layer (data)** — add the schema (§4) to the game-type layer
   (`play_styles_data.py` / a profiles module); declare `primary/secondary_shape`,
   `commitment_kind`, `judgment_type`, `withheld_kind`, `payoff_kind`, `contract_scope`.
   Author the test profiles: Deduction (mystery), Bond (romance — the no-clues check),
   Endurance (survival). **The romance profile is the falsifier: it must carry no
   clue-trail and still resolve.**
2. **Card model in the briefing** — the narrator gets the active cards (it *knows* the
   destination), with "weave the trail, don't blurt the unearned payoff" + brute-force
   deflect; demote the strict gate to a silent backstop.
3. **Win-model swap** — commitment→graded, with `commitment_kind` as the declared
   capture form (claim / state / action / choice…), terminal on *convergence*, grade is
   epilogue flavor (per `STORY-SHAPE-AND-RESOLUTION.md` Appendix A).
4. **Convergence** (Phase-1 act directive shipped; re-aim at the conclusory scene).
5. **Epilogue** — irony-delta mining + the twist + the missed fragments.
6. **Drop the player-input extraction** (now safe).
7. **Verify live** against Deduction + Bond + Endurance (the zombie-vs-Hogwarts-vs-romance
   test).

## 7. PB / Kernos boundary
No PB primitive (Cx 025). Host/profile/arc orchestration over PB facts, frames,
`frame_diff`, session receipts, deterministic arc reads. Invariant: tension profiles,
grades, briefing directives are host-side control data; durable consequences enter canon
only through explicit committed facts.

Related: `STORY-SHAPE-AND-RESOLUTION.md` (win-model/convergence/epilogue),
`CONCLUSIVE-OUTCOME-SPEC.md` (story|sandbox contract), `GAME-TYPE-TAXONOMY.md` (the 155
types), the Cx review at `codex-inbox/025-from-cx-story-shapes-genre-review.md`.

## 8. The populated cast — the surface pillars fill through (Cx shape, 2026-06-22)

The pillars are *causes*; the **cast is the surface you fill them through** — you
interview people to establish causes. A whodunit needs 5–10 people who each hold a
piece of the detail, carry their own innocence evidence, cross-suspect one another,
and drop clues (some true, some red herrings). Cx's shape — **zero new engine
primitive**; host-side profile data over the existing `knows:<npc>` frames.

### 8.1 `cast_node` (host-side profile, NOT canon)
One record per important NPC. Diegetic facts live in `knows:<npc>`; the clue/pillar
metadata stays host-side (hidden `plot:main` control layer):
```yaml
cast_node:
  id: person:clerk
  frame: knows:person:clerk
  surface_role: "night clerk";  shape_role: "witness/suspect"
  knows: [{fact_ref:{e,a,v}, purpose: self|world|clue|about_other}]
  holds_clues:
    - {clue_id, pillar_id, surface_fact:{e,a,v},
       coverage_effect: genuine|false|context, is_red_herring: bool,
       reveal_mode: volunteered|pressed|traded|contradicted,
       reveal_condition: none|trust|pressure|object_seen,
       debunked_by: clue:...}        # required for a STRONG red herring
  alibi: {claim_fact:{e,a,v}, support_clue_ids:[], status: true|false|partial|untested,
          exculpates:[pillar:...], flaw: "..."}
  suspects: [{target, reason_fact:{e,a,v}, pillar_id, truth_status: true|false|ambiguous,
              is_red_herring: bool, confidence: low|med|high}]
```
- `surface_fact`/`claim_fact`/`reason_fact`/`knows[]` → ordinary facts in `knows:<npc>`.
- `clue_id`/`pillar_id`/`coverage_effect`/`is_red_herring`/`debunked_by` → host-side card
  metadata, never canon, never the NPC's diegetic knowledge.
- On interview: host picks the `cast_node`, reads `knows:<npc>`, the NPC surfaces
  authorized facts; a *learned* clue is written as an ordinary fact into
  `knows:<protagonist>`. **Pillar coverage is computed HOST-SIDE** from clues/facts in
  the player frame — PB never infers "pillar filled" (that would be a new primitive).

### 8.2 Fair clue→pillar distribution (session-zero) + validation
Author from the card's `required_pillars`: every required pillar gets ≥1 reachable
`genuine` clue; keep the three-clue redundancy (≥3 genuine fragments thread-wide, core
pillars get 2 routes when the cast is large); add red herrings only *after* genuine
coverage exists (false pressure/suspicion/cost, never on the minimum solvable path);
every non-culprit gets reachable innocence evidence; the culprit's apparent alibi has a
reachable flaw. **Solvability check (CI):**
```
∀ required pillar P: genuine_reachable(P) ≥ 1
After removing every is_red_herring AND every coverage_effect≠genuine clue:
  all required pillars STILL reachable
No genuine required clue gated solely behind a red herring / unreachable NPC / answer-first
Every strong red herring has a reachable debunked_by, OR is context-only (can't false-fill alone)
```
Coverage states (genuine / false / unfilled per pillar) map to the conclusory scene as
*effect* (sound case / wrong accusation / partial / pyrrhic) — never win/loss.

### 8.3 One generic schema, shape-specific semantics
ONE `cast_node` schema across all nine shapes; only the *labels* + authoring prompts +
validation weights change by `primary_shape`/`secondary_shapes` (separate node types
would fight blends). Deduction = witnesses/evidence/innocence/cross-suspicion; Bond =
relationship circle / vulnerability / boundary / interpretations; Contest =
rivals-allies / weakness-stakes / standing / scouting; Discovery = guides-informants /
map-history / reliability / competing explanations; Farce = ensemble / timing-fuse /
excuse / blame-chain.

### 8.4 Cross-suspicion web — sparse graph + ONE synthesis call (no N²)
Compact cast table (role/faction/location_at_event/relationship/secret_pressure/
reliability/clue_ids) → assign genuine holders to pillars → build a **deterministic
sparse directed edge plan** (ring edges connect the cast; pillar edges point each clue
holder at a relevant person/place/contradiction; a few alibi corroborate/contradict
edges; capped red-herring edges; `out_degree≤2–3`, `in_degree≤3`) → **one cheap "cast
web realization" call** over the whole table + edge plan producing edge reasons / gossip
lines / fact triples → mechanical validation (ids exist, every edge has a plausible
`reason_fact`, solvability still passes) → seed each edge reason into the *source's*
`knows:<source>` frame as ordinary knowledge; edge metadata stays host-side.

**All nine engines at this depth:** §8 is the Deduction worked example; the other eight
shapes (Bond/Endurance/Contest/Gambit/Discovery/Mastery/Farce/Transformation) are brought to
the same richness — populated surface, pillars, mechanics, worked fiction card — in
`STORY-SHAPES-CATALOG.md`. That catalog's §0 holds five CROSS-CUTTING findings that upgrade
this section: one generic cast_node (labels change by shape); `frame` may be world/canon not
just `knows:<npc>` (hybrid shapes); `cost_disposition` flips how coverage is read (Farce:
`false`=engine-live); `delta_type` derives from coverage (Transformation); some conclusions
read a world event alongside coverage (Contest's scoreboard). The build is ONE engine
parameterized by a per-shape profile, not nine builds.

**Build order (folds into §6):** cast_node profile + authoring (extends step 1) →
clue→pillar distribution + CI solvability check → host-side coverage computation (the
conclusion_trigger=`pillars` engine) → interview delivery in the turn loop → cross-
suspicion synthesis call → conclusion-as-effect (replaces the win/loss terminal) →
unified episodic hook. (Full Cx shape: agent reply 2026-06-22; this section is the spec.)
