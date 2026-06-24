# Story-Shapes Catalog — all nine engines at depth parity

Companion to `STORY-SHAPES.md`. §8 of that doc brought **Deduction** to full richness
(the populated cast: cast_node over `knows:<npc>`, clue→pillar distribution, solvability,
cross-suspicion in one synthesis call). This catalog brings the **other eight engines** to
the same depth — each with its populated surface, its pillars (causes with `genuine_via`/
`false_via` coverage over the player frame), its richness/variety mechanics, and a worked
fiction card. **155 game-type flavors ride these 9 structural engines** (`FAMILY_SHAPE`);
enriching an engine enriches every flavor on it. Zero new engine primitive anywhere.

Source: eight grounded design passes, 2026-06-22. Full per-shape specs archived in the
session transcript; this is the consolidated, buildable digest.

---

## 0. Cross-cutting findings (these UPGRADE §8 and the grammar)

The eight passes independently converged on five refinements that generalize the §8
Deduction model. **These are the load-bearing architecture changes; honor them in the
build.**

1. **ONE generic `cast_node` schema; labels change by shape — never fork the node type.**
   (§8.3, reconfirmed by all 8 — separate node types fight blends like Deduction+Gambit.)
   The §8 fields map per shape: `holds_clues`→(beats/fuses/lessons/moral-data),
   `alibi`→(guard/theory/cover/pull/reads_as), `suspects`→(relational-reads/rivalry/
   cross-purposes/disputes/reads_you).

2. **`cast_node.frame` may point at WORLD/CANON state, not only `knows:<npc>`.** The
   "hybrid" shapes need non-person nodes: Endurance's threat/resource/refuge nodes,
   Discovery's site/phenomenon nodes, Mastery's material/system nodes, all read off
   world/canon; Farce/Bond/Contest/Gambit/Transformation stay people-on-`knows:<npc>`.
   Either way the **learned fact lands in `knows:<protagonist>` and coverage is a host-side
   read of that one frame** — the node's source frame is irrelevant to the coverage read.
   No primitive: a site/material node is a cast_node whose `frame` names world/region state
   and whose reveal verbs are `seen|examined|returned-to|measured|practiced` instead of
   `pressed|traded`.

3. **`cost_disposition` flips how coverage is READ — the conclusion selector must consult
   it.** Deduction (`peril_redemption`): desired coverage = `genuine`; `false` darkens.
   **Farce (`fail_forward`): desired coverage = `false`** — a "false-filled" pillar means
   the comic engine is LIVE; `genuine` (defused) is the anticlimax; all-`unfilled` is the
   damp squib (comedy's only real failure). Same tri-state machinery, sign read off
   `cost_disposition`. (Headline case: Farce. Also bond=`repair`, endurance=`sacrifice`.)

4. **`ConclusionShape.delta_type` should be DERIVED from pillar coverage, not declared in
   parallel.** (Transformation.) The arc already carries both `pillars` and a
   `ConclusionShape` with `delta_type`+`tension`. `executor.arc_coverage` maps coverage →
   `delta_type` (all-genuine→`drive_inverted`, etc.); the `tension` triple `(entity,
   stronger_drive, weaker_drive)` IS the old-self/changed-self axis a Transformation
   `change_proven` pillar references — one source of truth, no contradiction risk.

5. **Some conclusions read a WORLD EVENT alongside coverage.** (Contest.) The scoreboard
   (win/lose the match) is an `Occurred` world event read SEPARATELY and combined with
   pillar coverage — that is how "proved himself, lost the decision" (Rocky) is
   representable: `standard_internalized` genuine + scoreboard-loss = the story win. Fix:
   rename Contest's `judgment_type` `score-vs-objective`→`proof-vs-standard` (the old value
   re-couples win to scoreboard and breaks the case).

**Net grammar/build deltas:** encode per-shape `conclusion_trigger`/`cost_disposition`/
`pacing` defaults on `SHAPES`; add a `SHAPE_CONCLUSION` coverage→effect-phrasing table;
`cast_node` gains `frame: canon|world|knows:<npc>`, a `reliability`/status axis, and the
shape-specific reveal-verb enums; the conclusion selector reads `cost_disposition` (finding
3), `delta_type`-from-coverage (finding 4), and an optional world-event (finding 5).

---

## 1. BOND — *Pride & Prejudice* (`repair`, pillars+commitment, untimed)

**Surface — the relationship circle** (cast_node, `knows:<npc>`): bond_target / rival /
confidant / gatekeeper / foil(-pair) / self. `holds_clues`→**relational beats**;
`alibi`→**guard** (the wall: pride/duty/wound, with a `crack`); `suspects`→**reads**
(relational opinion: social-pressure + foil-pair + misread-propagation edges).

**Pillars:** `mutual_vulnerability` (a wound shown AND met — genuine needs both facts;
false = infatuation/flattery), `obstacle_confronted` (the social wall faced; false =
denied), `trust_tested_held` (rupture-risk met by staying; false = trust on an uncorrected
misread), `misread_corrected` (the first impression undone; false = declaring while still
believing the slander). Optional: `slow_build_earned`.
**Coverage→effect:** all genuine → earned union; a required false → rupture/rebuff (the
premature declaration "rings hollow"); partial → bittersweet/open.

**Richness:** misreads (=red herrings, with `corrected_by`), guards (=alibis with a crack),
relational-opinion edges (=cross-suspicion), rival suitors (a real false-fill route).
**Card proof:** the refused FIRST proposal IS a false-coverage commit (`misread_corrected`+
`obstacle_confronted` unfilled, a Wickham-misread held); the second lands when all genuine.

---

## 2. ENDURANCE — *The Road* (`sacrifice`, event_deadline, hard/soft clock)

**Surface — the survival SYSTEM** (nodes on world/canon + companions on `knows:<npc>`):
threat / resource / companion / refuge_route. Adds `cost_to_engage` (the spend),
`reads_as` (apparent vs true nature — the §8 alibi for non-people), `couples_with` (the
compounding-pressure edges, realized as coupled `Clock`s — cold×fuel). The dwindling ledger
IS a `repeat`-rearm Clock spending a resource per tick.

**Pillars:** `route` (a viable refuge; false = a trap "safe" place — the larder house),
`means` (the sustaining resource; false = tainted cache), `vulnerable` (kept the vulnerable
one alive/with-you; false = believed-fine while failing), `humanity` (paid the necessary
cost without the unnecessary one; false = an atrocity reframed as necessity).
**Coverage→effect:** all genuine → outlast (cost-colored); `route` false → the trap springs;
`humanity` false → survived as something else; required pair COMPETES for one resource (the
trade-off with no clean answer is structural).

**Richness:** false refuge, tainted resource, the companion who breaks, escalating scarcity
(coupled clocks). **Card proof:** the house (false `route`, debunk = the bones/the cellar);
the thief (the `means`-vs-`humanity` trade-off); the boy as moral mirror holding `humanity`.

---

## 3. CONTEST — *Rocky* (`peril_redemption`, proof-vs-standard)

**Surface** (cast_node, `knows:<npc>`): rivals / allies / mentor / standard_bearer / crowd.
`holds_clues`→scoutable tells & absorbable lessons; `alibi`→apparent invincibility (with a
`flaw`=the real opening); `suspects`→rivalry/doubt web (contempt↔respect = the standard
externalized).

**Pillars (decoupled from the scoreboard):** `competence_earned` (through setback; false =
bravado/luck), `rival_understood` (the real tell + the flaw; false = the feint),
`standard_internalized` (the PERSONAL bar met, NOT the trophy; false = trophy-as-standard).
Optional `cost_paid`. **Coverage→effect combines with the SCOREBOARD world event** (finding
5): all-genuine + loss = **"went the distance," proved himself** (the Rocky case);
`standard_internalized` false + win = hollow win; `rival_understood` false = cheap/fluke.

**Richness:** overconfidence trap, the rival's feint (with `debunked_by`), the shortcut that
hollows the win, the ally who doubts. **Card proof:** train through Mickey + survive the
rib-break round + reject Gazzo's payday = all genuine; scoreboard=loss → proved himself.

---

## 4. GAMBIT — *Ocean's Eleven* (lands WITH the how-reveal) — anchor's secondary

**Surface** (cast_node, `knows:<npc>`): crew (specialties that gate moves) / mark &
defenders (defense layers) / faction & leverage-holders (swing pieces). `coverage_effect`
genuine=real capability/defense/leverage, false=plant/decoy/compromised.

**Pillars:** `defense_mapped` (AtLeast(2) real layers; false = a decoy panel), `crew_aligned`
(false = a compromised man), `leverage_secured` (false = planted kompromat), `contingency_set`
(the answer to the wrench AND the twist's anchor; false = rests on a misread defense).
Optional `factions_handled` (→required in the coup/intrigue register — relevant to anchor).
**The twist** = a reveal `Beat(correlates=...)` (the SWAT team ≡ the crew) fired at the
conclusory scene, gated on genuine `contingency_set`, foreshadowed via `Pin(escalates=True)`.
**Coverage→effect:** all genuine → lands with the how-reveal; one false → lands at cost/
pyrrhic (the twist turns partly against you); required unfilled → collapses.

**Richness:** the plant, the double-cross, the defense-that-isn't, the complication/pivot (a
`Clock` wrench answered by `contingency_set`), the faction switch. Replay = re-roll which
slot is the plant/decoy/hidden-move at one synthesis call. **Card proof:** Zerga deposit =
leverage; SWAT-exfil = contingency/hidden move; the responding SWAT team IS the crew.

---

## 5. DISCOVERY — *Arrival* (`sacrifice`/embrace-the-cost, untimed)

**Surface — hybrid:** guide/informant nodes (`knows:<npc>`, each with a SLANT) + site/
phenomenon nodes (world/canon — strata, signs). `alibi`→**theory** (a claim with a `flaw`);
`reliability` axis (trusted/partial/mistaken/self-serving/plain/ambiguous/misleading);
`suspects`→**disputes** (who reads the meaning differently). Depth-gating: a site with
`reveal_condition: prior_site|returned-to` only yields once an earlier stratum is known —
the engine of *gradual unfolding* and the *return-and-reframe*.

**Pillars:** `place_mapped` (≥2 strata; false = surface mistaken for totality),
`explanations_weighed` (≥2 rival theories + a debunk seen; false = one adopted wholesale),
`true_meaning_grasped` (the reframe, gated on place_mapped; false = the seductive wrong
meaning), `cost_accepted` (understanding's price embraced; false = grasped but evaded).
**Coverage→effect:** all genuine → awe + true understanding embraced at its price (the
arrival); meaning false → a false epiphany (truth festers); meaning genuine but cost denied
→ understanding refused.

**Richness:** competing explanations (with `debunked_by`), the unreliable guide (slant not
tell), the seductive wrong pattern (real data over-read), the site that misleads (corrected
by going deeper). **Card proof:** the-shell+the-glass+logogram-tense+return-to-the-visions =
the visions are foreknowledge not memory; she chooses Hannah anyway.

---

## 6. MASTERY — *Whiplash* (Mastery+Transformation cost)

**Surface — hybrid:** material/system node (world/canon — `difficulty_axes` with a
standard, `setbacks[]` whose lessons accrete to `knows:player`, resists on its OWN terms) +
people (mentor / rival / judge / the-one-you-do-it-for; mentor & judge are often one brutal
node). Numeric `difficulty_axis` comparison **defaults to an ordinal `status` enum**
(`unmet|partial|met_brittle|met_genuine`) — only escalates to the parked numeric-quantities
adoption via a [DECISION] letter; nothing blocked.

**Pillars:** `fundamentals` (earned through setback; false = flashy shortcut/backing-track),
`standard_met` (the material's resistance cleared AND the judge's withheld bar reached;
false = met_brittle / gamed), `cost_reckoned` (the price of excellence SEEN, accepted or
refused; false = denied). Optional `own_voice`, `taught_it_forward`.
**Coverage→effect:** all genuine → transcendent achievement knowingly costed; cost denied →
**greatness-at-the-cost-of-self** (the Whiplash pyrrhic — proved, humanity unseen); brittle
→ fails under load; shortcut → hollow flash exposed.

**Richness:** the shortcut that fakes it, the plateau/setback, the judge's MOVING standard
(approval re-gated as you climb), the gifted rival, the cost denied (an alibi-with-a-flaw on
the relationship). **Card proof:** bloody-hands + dropped-tempo reckoned with + the final
solo clearing the chart + Fletcher's nod, but Nicole gone and unreckoned → greatness at cost.

---

## 7. FARCE — "the King comes to dinner" / *The Hangover* (`fail_forward`)

**THE INVERSION (finding 3):** things going WRONG is the fuel. A pillar filling `false`
means the comic engine is LIVE — desired. Coverage rank: **`false` (glorious blowup) >
`genuine` (defused, tame) > `unfilled` (damp squib — comedy's only real failure).**

**Surface — the comedy ensemble** (cast_node, `knows:<npc>`): `holds_clues`→**lit fuses** +
excuse-material (adds host fields `fuse_length` short/med/long, `collides_with`);
`alibi`→**cover story** (with a `flaw`=the joke); `suspects`→**cross-PURPOSES** (who
misunderstands whom). People are anxious & sincere, not zany — precision panic.

**Pillars:** `mistaken-identity` (the wrong belief established; false-desired = the cast acts
on it), `fuses-lit` (≥2 active; ≥3 fragments thread-wide so the engine survives a snuff),
`cover-compounds` (opt — the lie needs more lies), `deadline-met` (the clock forces
simultaneous collision), `landing`. **Coverage→effect** (read via `fail_forward`): engine
`false` + low collateral → warm comic triumph; + a cruel schemer → comeuppance (lands on the
deserving); engine `genuine` (player defused all) → the anticlimax; the world must RESIST
tidy fixes (premature honesty bounces).

**Richness:** mistaken-identity chain, lie-needs-more-lies, object-that-must-be-hidden (pin
escalates), timing collision, blame-chain, decoy fuse. **Card proof:** let the Herald believe
you're the lord, hide the pig, invent the musicians → all fuses collide at sundown → the King
delighted, the pig knighted in jest, everyone drunk. The disasters WERE the payoff.

---

## 8. TRANSFORMATION — *A Christmas Carol* (`choice` trigger) — the common SECONDARY

**Surface — the moral pressure FIELD** (cast_node, `knows:<npc>`): catalyst/mirror /
temptation-back / the-one-saved-by-change / cost-embodiment. `alibi`→**pull** (a
temptation with `offer_fact` + `cost_of_refusing`, status pending/refused/yielded);
`suspects`→**reads_you** (the field reads the protagonist's old vs changed self; a
`witnessed_act` flips it). The change is **reversible until a costly deed proves it.**

**Pillars:** `old_self_seen` (confronted + owned; false = saw, rationalized),
`temptation_refused` (a back-to-old pull refused AT A COST; false = yielded later, or refused
only costless), `change_proven` (a COSTLY ACT, never words; false = cheap-grace declaration),
`wrong_made_right` (the one-saved actually saved at the old self's expense; false = words/
someone else). Reconciles with `ConclusionShape` (finding 4): coverage → `delta_type`
(all-genuine→`drive_inverted`); the `tension` triple = the drive axis `change_proven`
references. **Coverage→effect:** all genuine → genuine redemption; `change_proven` false →
hollow relapse; partial → partial change (redemption seed); `old_self_seen` false / timeout →
the **unmourned fall** (the cost-embodiment's warning fulfilled).

**Richness:** the cheap-grace shortcut (=red herring, with `debunked_by`=a later pull it
yields to), the relapse temptation, the rationalization, the climactic test (the choice
trigger). **Card proof:** Past+Marley owned + turkey bought + Bob's wage raised + Tim's
doctor paid (Tim lives) → drive_inverted, the on-the-money redemption; rationalize through →
the unmourned grave.

---

## 9. Build implication

The §8 build order now covers all 9 engines, not just Deduction. The cast_node authoring +
clue→pillar distribution + solvability CI + interview/engagement delivery + cross-edge
synthesis + conclusion-as-effect are **shape-agnostic with shape-specific labels/pillars/
validation-weights** — so the build is ONE engine parameterized by a per-shape profile
(surface labels, pillar pack, reveal verbs, `cost_disposition` polarity, conclusion phrasing),
not nine builds. The five cross-cutting findings (§0) are the additions to the §8 plan.
