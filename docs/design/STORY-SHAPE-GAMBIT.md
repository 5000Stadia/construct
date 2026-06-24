# Story Shape Deep Treatment — GAMBIT (the scheme/heist/intrigue shape)

**Status:** design-first, host-side only. Parallels the DEDUCTION treatment carried by
STORY-SHAPES §8/§8.x (witnesses/evidence/innocence/cross-suspicion). This brings GAMBIT —
the heist / con / coup / infiltration / power-play shape — up to the same richness, depth,
and variety. Canonical exemplar *Ocean's Eleven*; family map (`story_shapes.FAMILY_SHAPE`):
Politics/Factions, Schemes/Infiltration, Transgression/Power → `gambit`.

**Why it matters now:** the anchor world is mystery + political intrigue = `deduction +
gambit`. GAMBIT is live in the demo and currently carries only a one-phrase medium
(`"leverage, maneuver, complications, misdirection"`) and a single discipline line. This
spec fills it out.

**Hard constraints honored:** host-side over existing `knows:<npc>` + PLAYER frames, **zero
new engine primitive**; pillars are `genuine_via`/`false_via` `Expr` conditions over the
player's knowledge frame (`construct.arc.grammar.Pillar`, `construct.arc.conditions`);
the conclusion is the **EFFECT** of coverage, never a win/loss verdict (§0a); redundancy
(three-clue rule) preserved; the narrator-knows-the-hand-and-the-twist concealment
discipline (§1, the card model) is respected and **extended** to GAMBIT's second concealed
layer. No code edits — §6 names the gaps.

---

## 1. What richness means for GAMBIT

The **genre promise** (FICTION_CRAFT): *we are going to get away with something difficult,
and the pleasure is the plan — assembled, threatened, and then revealed to have been
cleverer than we were shown.* GAMBIT's distinct pleasures, none of which a thin treatment
delivers:

- **The crew** — a team of specialists, each indispensable for one move. The joy is
  *casting*: who do you need, what do they cost, what do they bring. (Heist) Or, in the
  political register, the *coalition*: who you align, whip, or buy.
- **The mark & their defenses** — a worthy obstacle with real, *mapped* protections (the
  vault's three independent systems; the rival's loyal lieutenants; the institution's
  procedures). The mark is not a lock to pick once; it is a system to be *understood and
  subverted*.
- **The plan + complications** — a plan is stated (often partially), then the board
  *moves against it*: a guard rotation changes, a crew member is made, leverage evaporates.
  The pleasure is the **pivot** — improvising under pressure without abandoning the goal.
- **Leverage** — the currency of GAMBIT. Kompromat, a debt, a secret, a key, an inside
  man, a faction's self-interest. Leverage is *secured* (a pillar), and leverage can be a
  *plant* (false-fill).
- **The reveal of how-it-was-done** — GAMBIT's signature payoff. The job lands AND the
  audience is shown the **hand** they were never fully dealt: the move that was set up
  three scenes ago, the thing that was *already* true while we watched the apparent plan
  fail. *Ocean's* shows you the SWAT team WAS the crew. This is the concealed **twist** —
  the plan's hidden move — and it is concealed **from the player too**, not only from the
  mark (the SPECIAL constraint).

**Thin GAMBIT (what we have):** one obstacle, one maneuver. "Get into the vault." Player
tries; it works or it doesn't. No crew to assemble, no defenses to map, no leverage to
trade, no complication forcing a pivot, no hand to reveal. It plays as a single skill
check wearing a tuxedo — Contest in disguise.

**Rich GAMBIT (the target):**
1. a **crew** with distinct specialties the player must recruit/align, each gating a move;
2. a **mark** whose defenses are *mapped* through play (multiple independent protections,
   each a thing to learn and beat);
3. **factions / leverage-holders** — swing pieces with their own self-interest, who can be
   turned, bought, or who turn on you;
4. **complications** authored to fire mid-run and force a *pivot* (the inevitable
   wrench — see §4);
5. a **concealed twist** — the plan's hidden move — that the narrator knows, foreshadows,
   and *never blurts*, paid off at the conclusory scene as the how-reveal.

Richness = the player feels they *built and ran a machine of people and pressure*, and the
ending shows them the machine had a gear they never saw.

---

## 2. The populated surface (adapt §8 `cast_node` to GAMBIT)

ONE generic `cast_node` schema across all nine shapes (§8.3) — only labels, authoring
prompts, and validation weights change by shape. Diegetic facts live in `knows:<npc>`;
the clue/pillar metadata stays host-side (`plot:main` control layer, never canon). For
GAMBIT the cast splits into **three functional classes** (vs. DEDUCTION's
witness/suspect):

- **Crew (allies)** — specialists you recruit/align. Each *carries a capability*: engaging
  them genuine-fills the pillar their specialty serves. They can also be *compromised*
  (a crew member who is a plant / gets made → a false-fill or a complication source).
- **Mark & defenders (obstacles)** — the target and the people/systems guarding them. Each
  defender *holds a piece of the mark's defense map*: learning it (casing, social-
  engineering, observation) is how the "defense mapped" pillar fills. A defense can be
  **not what it seems** (false-fill: the player maps a decoy).
- **Factions / leverage-holders (swing pieces)** — players with their own self-interest who
  can be turned, bought, or who *switch*. They carry **leverage** (a secret, a debt, a key,
  a vote). Securing it genuine-fills "leverage secured"; a faction can hand you a **plant**
  (false-fill) or **switch sides** mid-run (complication).

### 2.1 `cast_node` — GAMBIT semantics (same schema, GAMBIT labels)

```yaml
cast_node:
  id: person:rusty
  frame: knows:person:rusty
  surface_role: "the recruiter"          # diegetic role
  shape_role: crew | mark | defender | faction | leverage_holder   # GAMBIT class
  specialty: grift | tech | inside | muscle | money | face | none  # crew only
  knows: [{fact_ref:{e,a,v}, purpose: self|world|capability|about_other}]
  holds_clues:                            # GAMBIT: "holds_intel" — pieces toward a pillar
    - {clue_id, pillar_id, surface_fact:{e,a,v},
       coverage_effect: genuine|false|context, is_red_herring: bool,
       # GAMBIT semantics of coverage_effect:
       #   genuine = real capability secured / real defense mapped / real leverage held
       #   false   = a plant / a misread defense / leverage that's a trap
       #   context = colour; cannot fill a pillar alone
       reveal_mode: volunteered|pressed|traded|contradicted,
       reveal_condition: none|trust|pressure|object_seen|leverage_held,  # +GAMBIT: leverage_held
       debunked_by: clue:...}             # required for a STRONG plant/decoy (see §4)
  alibi:                                  # GAMBIT: "cover" — the loyalty/security claim
    {claim_fact:{e,a,v}, support_clue_ids:[], status: true|false|partial|untested,
     exculpates:[pillar:...], flaw: "..."}   # flaw = the seam in the mark's defense / the crew's tell
  suspects: [{target, reason_fact:{e,a,v}, pillar_id, truth_status: true|false|ambiguous,
              is_red_herring: bool, confidence: low|med|high}]   # GAMBIT: "leans"/"distrusts" web
```

Mapping (identical to §8.1 — no new mechanism): `surface_fact`/`claim_fact`/`reason_fact`/
`knows[]` are ordinary facts in `knows:<npc>`; `clue_id`/`pillar_id`/`coverage_effect`/
`is_red_herring`/`debunked_by` are host-side card metadata, never canon. On engaging an
NPC, the host picks the `cast_node`, reads `knows:<npc>`, the NPC surfaces authorized
facts; a *learned* piece of intel is written as an ordinary fact into
`knows:<protagonist>`. **Pillar coverage is computed HOST-SIDE** from the player frame
(`executor.arc_coverage`) — PB never infers "pillar filled."

### 2.2 What each class carries, and how engaging it advances coverage

| Class | Surface role | Carries | Engaging it does | Coverage effect |
|---|---|---|---|---|
| **Crew** | recruiter, hacker, grease-man, inside man, financier, the face | a `specialty` that unlocks one move; their price; their tell | recruit/align → write `crew_aligned(<who>)` fact into player frame | genuine-fills `crew_aligned`; if compromised, false-fills or sources a complication |
| **Mark** | the target (casino boss, rival senator, the institution) | the prize; their habits; their paranoia | observe/provoke → learn a defense piece | context + sets the stakes |
| **Defender** | head of security, loyal lieutenant, the auditor | one layer of the defense (a system, a routine, a person's loyalty) | case/social-engineer → write `defense_mapped(<layer>)` | genuine-fills `defense_mapped`; a decoy layer false-fills |
| **Faction** | a rival crew, a voting bloc, a watching agency | self-interest; a switch-condition | court/buy/threaten → write `faction_secured(<bloc>)` | genuine-fills `factions_handled`; can switch → complication |
| **Leverage-holder** | the blackmailable clerk, the indebted official, the keyholder | a specific lever (secret/debt/key/vote) | secure → write `leverage_held(<lever>)` | genuine-fills `leverage_secured`; a plant false-fills |

A crew member is **how you cover the crew/contingency pillars**; a defender is **how you
cover the defense-mapped pillar**; a faction/leverage-holder is **how you cover the
leverage/factions pillars** — exactly the §8 "the cast is how you cover pillars," retargeted
to GAMBIT's allies/obstacles/swing-pieces split.

---

## 3. The pillars (the causes)

GAMBIT's conclusory scene is the **EFFECT** of which causes the player put in place (§0a).
Coverage is tri-state per pillar — **genuine / false / unfilled** — computed host-side from
the PLAYER frame via `genuine_via` / `false_via` `Expr` conditions (atoms from
`construct.arc.conditions`: `InFrame`, `StateIs`, `Occurred`, `BeatAchieved`, `AtLeast`,
`AllOf`, `AnyOf`, `Not`). Below, frame facts of the form `knows:protagonist` with
attributes `crew_aligned` / `defense_mapped` / `leverage_held` / `faction_secured` /
`contingency_set` are ordinary facts the host writes when the player surfaces the
corresponding intel (§2). `is_plant`/decoy facts are likewise ordinary facts the player
*holds as true* — that is the whole false-fill mechanism: a fact the player believes that
isn't load-bearing.

### 3.1 The four required GAMBIT pillars (+ optional enrichers)

| pillar_id | label | required | the cause it is |
|---|---|---|---|
| `defense_mapped` | The mark's defenses are understood | yes | you know what you are beating |
| `crew_aligned` | The crew is assembled & committed | yes | you have the people to run each move |
| `leverage_secured` | The decisive leverage is in hand | yes | the lever that actually moves the mark |
| `contingency_set` | The plan survives the inevitable complication | yes | the answer to the wrench (the hidden move's seed) |
| `factions_handled` | Swing players neutralized / turned | optional | the board won't flip on you mid-run |

Three to five required pillars (the prompt's range) — the four above are the GAMBIT core;
`factions_handled` is optional and promotes to required for the **political-intrigue /
coup** register (where the swing blocs *are* the game). Each is a `Pillar`:

```python
from construct.arc.grammar import Pillar
from construct.arc.conditions import InFrame, StateIs, Occurred, AtLeast, AllOf, Not

PF = "knows:protagonist"   # the player's knowledge frame

GAMBIT_PILLARS = (
    # --- defense_mapped: enough real layers learned (three-clue redundancy: ≥2 of ≥3) ---
    Pillar(
        pillar_id="defense_mapped",
        label="The mark's defenses are understood",
        required=True,
        genuine_via=AtLeast(2, (
            InFrame(PF, "protagonist", "defense_mapped", "vault_timer"),
            InFrame(PF, "protagonist", "defense_mapped", "guard_rotation"),
            InFrame(PF, "protagonist", "defense_mapped", "surveillance"),
        )),
        # false-fill: the player confidently maps a DECOY layer as the real one
        false_via=InFrame(PF, "protagonist", "defense_mapped", "decoy_panel"),
    ),
    # --- crew_aligned: the specialties the plan requires are all committed ---
    Pillar(
        pillar_id="crew_aligned",
        label="The crew is assembled and committed",
        required=True,
        genuine_via=AllOf((
            InFrame(PF, "protagonist", "crew_aligned", "inside"),
            InFrame(PF, "protagonist", "crew_aligned", "tech"),
            InFrame(PF, "protagonist", "crew_aligned", "face"),
        )),
        # false-fill: a "committed" crew member is actually compromised / a plant
        false_via=InFrame(PF, "protagonist", "crew_aligned", "compromised_man"),
    ),
    # --- leverage_secured: a real lever on the mark, not a plant ---
    Pillar(
        pillar_id="leverage_secured",
        label="The decisive leverage is in hand",
        required=True,
        genuine_via=Occurred("secure_leverage", participants=("protagonist",)),
        # false-fill: the leverage is a plant the mark fed you (a trap)
        false_via=InFrame(PF, "protagonist", "leverage_held", "planted_kompromat"),
    ),
    # --- contingency_set: there is an answer to the wrench (carries the hidden move) ---
    Pillar(
        pillar_id="contingency_set",
        label="The plan survives the inevitable complication",
        required=True,
        genuine_via=InFrame(PF, "protagonist", "contingency_set", "true"),
        # false-fill: the "contingency" rests on the misread defense / the plant
        false_via=AllOf((
            InFrame(PF, "protagonist", "contingency_set", "true"),
            Not(InFrame(PF, "protagonist", "defense_mapped", "guard_rotation")),
        )),
    ),
    # --- factions_handled (optional; required in coup/intrigue register) ---
    Pillar(
        pillar_id="factions_handled",
        label="Swing players neutralized or turned",
        required=False,
        genuine_via=AtLeast(1, (
            InFrame(PF, "protagonist", "faction_secured", "rival_crew"),
            InFrame(PF, "protagonist", "faction_secured", "the_agency"),
        )),
        false_via=InFrame(PF, "protagonist", "faction_secured", "double_agent_bloc"),
    ),
)
```

(Identifiers are illustrative; the session-zero authoring call fills the concrete `value`
strings from the generated fiction — §6. The *shapes* of the `Expr` are the contract.)

### 3.2 The twist, represented host-side (the SPECIAL constraint)

GAMBIT has **two concealed layers**: the **hand** (the plan, withheld until it lands) and
the **twist** (the plan's hidden move, concealed *from the player too*). We represent the
twist with **zero new primitive** by reusing the existing reveal-beat + pin machinery:

- The twist is authored as a **`Beat` with `correlates`** (grammar.py: a reveal beat that,
  when achieved, `correlate`s two entities — e.g. *the SWAT team* ≡ *the crew* — as facets
  of one identity, as-of that turn, without merging). Before the beat they read separate
  (the player, like the mark, sees two things); after, the union read links them. This is
  exactly the "shown-you-the-pieces, withheld-the-connection" structure of the how-reveal.
- The `contingency_set` pillar is the twist's **causal anchor**: genuine coverage of it is
  what makes the hidden move *true and earned* (the player set it up without knowing its
  full weight). When it is genuinely filled, the conclusory scene fires the
  `correlates` beat as the how-reveal. When it is false-filled, the hidden move misfires —
  the twist turns against the player.
- The narrator holds the twist as a **card** (§1) and seeds **escalating foreshadow pins**
  (`Pin(escalates=True)`): the recurring detail that *means* the hidden move, getting
  louder as `contingency_set` approaches coverage — foreshadowed, never blurted. The
  brute-force guard ("what's the catch? tell me the twist") deflects, same as the
  DEDUCTION answer.

### 3.3 Coverage → the conclusory scene (the EFFECT)

The host computes coverage (genuine/false/unfilled per pillar) over the player frame and
narrates the conclusion as its effect — **never** "you win/lose" (§0a). The
`conclusion_trigger` is `pillars` (+ `commitment` — the player *pulls the job*); `Ocean's`-
style heists often **nest a `hard` clock** at the execution (the window) inside an otherwise
`soft`/untimed prep. Mapping:

| Coverage state | Conclusory scene (the effect) — narrated WITH the how-reveal |
|---|---|
| **All required genuine** | **The job LANDS, and the hand is revealed** — the `correlates` twist beat fires: the move you set up (without seeing its full weight) IS what carries it. Clean → triumphant; the audience is shown the machine had a gear they never saw. |
| **One required false-filled** | **It lands at a COST / pyrrhic** — the plant or misread defense pays off as the complication you didn't fully cover; you get the prize but the leverage was a plant (the mark knew), or the crew loss bleeds into the next episode. The twist turns *partly* against you. |
| **Required unfilled** | **It COLLAPSES** — premature `pull_the_job` commitment with a required pillar unfilled is dismissed/backfires (you're made at the door; the vote fails on the floor). Not "you lose" — a *consequence*; the story doesn't conclude until pulled with cause, or the refusal clock backstops. |
| **Genuine but dragged through wreckage** | **Pyrrhic win** — right outcome, accumulated cost (burned crew, blown covers) colors it perilous → the richest **redemption** seed for the Series engine (§0a integral-of-the-run). |

---

## 4. Richness & variety mechanics

GAMBIT's equivalents of the DEDUCTION red-herring/alibi toolkit. Each is authored as
**host-side card metadata + ordinary `knows:<npc>` facts** — no new mechanism, just the
`cast_node` fields used with GAMBIT semantics. All obey §8.2 fairness: added only *after*
genuine coverage exists, never on the minimum solvable path, every strong one has a
reachable `debunked_by`.

1. **The plant (false leverage).** A leverage-holder hands the player kompromat/a key that
   is a *trap* fed by the mark. Authored as a `holds_clues` entry with
   `coverage_effect: false`, `is_red_herring: true`, and a reachable `debunked_by` (a
   second source contradicts it — the date on the photo is wrong). If held as true, it
   false-fills `leverage_secured`. **Variety:** which holder, what lever.
2. **The double-cross (compromised crew).** A crew member is a plant or gets *made* and
   flips. Authored on a crew `cast_node`: `cover.status: false`, `cover.flaw` is the
   reachable tell; `suspects`/`leans` edges let *another* crew member distrust them
   (cross-distrust web, §4.x below). If trusted, false-fills `crew_aligned` and **arms a
   complication** at execution. **Variety:** who flips, and whether the player catches it.
3. **The defense that isn't what it seems.** A defender presents a **decoy layer** as the
   real protection (`defense_mapped: decoy_panel`, `coverage_effect: false`). Mapping the
   decoy false-fills `defense_mapped`; the real layer is reachable elsewhere
   (`debunked_by`). **Variety:** which layer is the decoy.
4. **The complication that forces a pivot (the inevitable wrench).** Authored as a `Clock`
   (grammar.py) bound to the execution rung that *fires mid-run* (a guard rotation changes,
   an alarm trips, a vote is moved up): `fires_when` over canon, `effects` carry a
   `caused_by` chain. The player must **improvise** — the `contingency_set` pillar is the
   pre-authored answer; covering it genuinely means the pivot lands, false-filled means it
   doesn't. This is the engine of "adaptable improvisation while serving the plot."
5. **The faction that switches.** A swing piece with an authored **switch-condition**
   (`reveal_condition`/a `Clock` `fires_when`): if the player fails to secure it (or
   secures the `double_agent_bloc` false-fill), it turns at the worst moment. **Variety:**
   trivially re-rolled by which bloc, what self-interest, when it flips.

### 4.x Cross-distrust web (sparse graph + ONE synthesis call — mirror §8.4)

GAMBIT reuses §8.4 verbatim, retargeted: compact cast table (role/faction/
location/relationship/secret_pressure/reliability/intel_ids) → assign genuine holders to
pillars → **deterministic sparse directed edge plan** (ring edges connect the cast; pillar
edges point each intel-holder at a relevant person/defense layer/contradiction; a few
cover corroborate/contradict edges; capped plant/decoy edges; `out_degree≤2–3`,
`in_degree≤3`) → **one cheap "cast web realization" call** producing edge reasons / gossip
lines / fact triples → mechanical validation (ids exist, every edge has a plausible
`reason_fact`, solvability still passes) → seed each edge reason into the *source's*
`knows:<source>` frame; edge metadata stays host-side. GAMBIT's edges read as crew
distrust, faction leans, "who's really loyal to whom" — the texture of a scheme.

### 4.y Depth + replay variety, authored cheaply

Variety comes from **re-rolling slots in a fixed graph**, not new graphs: which crew member
is the plant, which defense layer is the decoy, which faction switches and when, which lever
is real vs. planted, and *what the hidden move is*. The sparse edge plan + one synthesis
call (§8.4) realizes a fresh, coherent web each build at the cost of a single cheap model
call — the same budget DEDUCTION pays. Solvability CI (§8.2) guarantees every roll is still
winnable on a genuine-only path.

---

## 5. Worked fiction exemplar — *Ocean's Eleven* (FILL THE CARD)

Proving the spec on the canonical GAMBIT. Mark: Terry Benedict; prize: the Bellagio vault
(serving three casinos on fight night). The hidden move (the twist): **the SWAT team that
responds to the "robbery" IS the crew** — the vault was emptied during the staged chaos;
what Benedict watched on the monitors was a decoy. Concealed from the audience until the
how-reveal.

### 5.1 The populated surface (filled)

| NPC | shape_role | specialty | carries | coverage it serves |
|---|---|---|---|---|
| **Rusty Ryan** | crew | face/recruiter | the roster, each member's price | `crew_aligned: face` |
| **Linus Caldwell** | crew | grift (pickpocket) | lifts Benedict's keycard/phone | `crew_aligned: inside` (the lift) |
| **Basher Tarr** | crew | tech (explosives) | the "pinch" that kills the grid | `defense_mapped: surveillance` beat |
| **Yen** | crew | muscle/acrobat | the man in the box, inside the vault | `crew_aligned` (the inside body) |
| **Saul Bloom** | crew | the face (long con) | poses as Zerga the arms dealer → deposits the "leverage" into the vault | seeds the inside man |
| **Terry Benedict** | mark | — | the vault, his paranoia, Tess | sets stakes; his defense map |
| **head of security** | defender | — | the three independent systems (timer / guards / cameras) | `defense_mapped` layers |
| **Reuben Tishkoff** | faction/money | — | financing + grudge against Benedict (self-interest) | `factions_handled` / motive |
| **The "SWAT" exfil** | (the twist) | — | the hidden move — responders ARE the crew | the how-reveal (`correlates` beat) |

### 5.2 The pillars (filled, concrete genuine/false)

- **`defense_mapped`** — *genuine_via:* `AtLeast(2, [defense_mapped:vault_timer,
  defense_mapped:guard_rotation, defense_mapped:surveillance])` — learned by casing
  Benedict's three systems (the cameras, the timer that locks the cash, the response
  protocol). *false_via:* `defense_mapped:decoy_panel` — believing the *monitored* vault
  feed is the real state (the feed Benedict is shown is, in fact, the decoy — mapping the
  feed-as-truth is the misread).
- **`crew_aligned`** — *genuine_via:* `AllOf(crew_aligned:inside, crew_aligned:tech,
  crew_aligned:face)` — Linus inside, Basher's pinch, Saul's Zerga cover all committed.
  *false_via:* `crew_aligned:compromised_man` — recruiting a member the house has already
  made (replay slot: in a re-roll, "Frank the dealer" is blown).
- **`leverage_secured`** — *genuine_via:* `Occurred("secure_leverage", ["protagonist"])` —
  Saul-as-Zerga deposits the "diamonds," giving the crew a *legitimate reason for a body
  and a case inside the vault*. *false_via:* `leverage_held:planted_kompromat` — the lever
  Benedict feeds back (he suspects, and lets you think you have him).
- **`contingency_set`** — *genuine_via:* `contingency_set:true` — the SWAT-exfil is rigged
  *before* the heist runs (the hidden move is set up). *false_via:* `AllOf(contingency_set,
  Not(defense_mapped:guard_rotation))` — a "contingency" that doesn't account for the real
  response protocol (rests on the decoy) → the exfil walks into actual police.
- **`factions_handled`** (optional → here, flavor) — Reuben's money + grudge secured.

### 5.3 Richness mechanics in *Ocean's*

- **Plant:** Benedict feeding back a false sense of control (he knows more than he lets on
  — the film's late "I know who you are" call). Held as true → `leverage_secured` false.
- **Double-cross:** Linus's loyalty wobble / the staged "betrayal" — authored as a `cover`
  with a reachable flaw; in *Ocean's* it's a **fake** double-cross (part of the hand), which
  is itself the genre's deepest move.
- **Defense-that-isn't:** the monitor feed Benedict watches **is the decoy** — the vault is
  already empty. The literal "defense that isn't what it seems."
- **Complication/pivot:** Benedict pulls the cash early / demands to see the vault — the
  `Clock` wrench; the crew's answer is the pre-rigged feed (the contingency).
- **Faction switch:** (replay slot) a rival crew or a tipped-off pit boss.

### 5.4 The conclusory scene as EFFECT of a sample coverage

**Sample coverage:** `defense_mapped` genuine (all three systems learned), `crew_aligned`
genuine, `leverage_secured` genuine (the Zerga deposit), `contingency_set` genuine
(SWAT-exfil rigged). All required pillars genuine.

**Effect (narrated, WITH the how-reveal):** the player pulls the job; Benedict watches the
vault get emptied on his monitors and calls in the response — and the `correlates` twist
beat fires: **the responding "SWAT team" is the crew**, walking out with the money in plain
sight; the monitor feed was the decoy, the vault emptied during the engineered blackout.
The hand the player was never fully dealt is laid on the table — the move they set up
(`contingency_set`) without seeing its full weight IS what carries it. Clean run →
triumphant; the fountain, the slow exit, the take. *That is the how-reveal as the EFFECT
of coverage* — not a "you win" banner.

**Contrast (one false-fill):** if `leverage_secured` were *false* (Benedict's plant held as
true), the same machine runs but lands **at a cost** — the money's recovered / Benedict
sees them at the door; pyrrhic, and a redemption seed for the next episode. The twist turns
partly against the crew.

---

## 6. Code gaps

What `story_shapes.py` / the authoring layer needs to bring GAMBIT to parity. **No new
engine primitive** — all host-side.

1. **`story_shapes.py` — enrich the SHAPES["gambit"] medium + discipline (data only).**
   The current one-phrase `medium` and single `_SHAPE_LINE` are thin. Match DEDUCTION's
   depth: extend `medium` to name the crew/mark/leverage/complication/how-reveal surface,
   and extend the `_SHAPE_LINE["gambit"]` to carry the **two-layer concealment** (the hand
   AND the twist) plus the foreshadow-don't-blurt + brute-force-deflect discipline.
   Suggested line: *"Let the scheme unfold through crew, leverage, and complication; keep
   BOTH your hand (the plan) and the twist (the plan's hidden move) concealed — foreshadow
   the hidden move with a recurring detail, never blurt it, deflect demands for the catch;
   reveal the HOW only when the job lands."*

2. **A GAMBIT pillar template** (parallels DEDUCTION's required-pillar set). Add a
   per-shape `required_pillars` template (the four GAMBIT pillars of §3.1, with optional
   `factions_handled` promoting to required in the political-intrigue register) that the
   session-zero authoring call instantiates with concrete `value` strings from the
   generated fiction. Likely lives beside SHAPES (e.g. a `SHAPE_PILLARS: dict[str,
   tuple[Pillar, ...]]`) or in the arc-authoring module. The `Pillar` dataclass and the
   `Expr` atoms already exist — **no grammar change**.

3. **`cast_node` GAMBIT label/prompt/validation profile.** The schema is unchanged (§8.3);
   add GAMBIT's `shape_role` enum (crew/mark/defender/faction/leverage_holder), the
   `specialty` field's GAMBIT vocabulary, the GAMBIT authoring prompt (crew/defense/
   leverage/complication framing), and GAMBIT validation weights (require ≥1 genuine
   capability per crew-served pillar; require a reachable real defense layer behind every
   decoy; the wrench `Clock` must have a reachable `contingency_set` genuine route).

4. **Twist representation = reuse, confirm wiring.** The twist uses an existing reveal
   `Beat(correlates=...)` + escalating `Pin(escalates=True)` + the `contingency_set`
   pillar as causal anchor. Confirm the authoring layer can: (a) author a `correlates` beat
   whose achievement is gated on the conclusory pull, and (b) seed escalating foreshadow
   pins for the hidden move. If the executor cannot currently *fire a reveal beat at the
   conclusory scene as a function of pillar coverage*, that wiring is the one integration
   point to verify — but it is host-side arc orchestration, **not** an engine primitive.

5. **Solvability CI for GAMBIT** (extends §8.2). Same invariants, GAMBIT reading: after
   removing every plant/decoy/compromised-crew (`is_red_herring` / `coverage_effect≠
   genuine`), all required pillars STILL reachable on a genuine path; every strong plant/
   decoy has a reachable `debunked_by`; the wrench `Clock` has a reachable genuine
   `contingency_set`; the twist's `correlates` beat is reachable only via genuine
   `contingency_set`.

**Flag:** none of the above requires a PB primitive. The single thing to *verify* (not
build new) is the executor firing a `correlates` reveal beat at the conclusory scene driven
by host-computed pillar coverage (gap #4) — if that path doesn't exist yet, it is a host
arc-executor addition, and if it turns out to want anything from the engine reads beyond the
`WorldReads` protocol, that is a `[DECISION]` letter to Kernos CC, never a stub-around.
