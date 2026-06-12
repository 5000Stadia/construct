# The Arc Layer — design (paper draft, pre-build)

**Status:** Reviewed design, build-ready pending porcelain freeze. No
code. Kernos review GREEN (letter 006, notes folded); Codex pass r1
complete — all 16 findings folded or resolved (markers "Codex r1 finding
N" inline). Pressure-tested on paper against the three hard cases named
in CONCEPT §5. Standing rulings: frame writes via
`ingest_structured(items, frame=)` only (letter 005); clocks host-side
(letter 004); concealment behavioral / progress structural (letter 004);
irony delta host-side (letter 004); host-authored `generated` into
host-owned frames with resolver authority composed at the gate (PB 029,
letter 007); `deny`/`reserve` LIVE (letter 007).

**One sentence:** the arc layer turns improvisation into navigation by
authoring a hidden destination as ordinary world assertions in a `plot:`
frame, evaluating progress structurally against canon, and pacing the world
with clocks and an epistemic instrument — all patterns over existing engine
primitives, no new ones.

---

## 1. Position in the architecture

The engine owns truth. The arc layer is host orchestration that:

1. **authors** the arc at session zero into frame `plot:main` via
   `ingest_structured(arc_items, frame="plot:main")` — the sanctioned
   doorway; never a raw frame poke;
2. **evaluates** beat progress after each turn (structural graph checks +
   one Quiet-Cohort judgment for marginal cases);
3. **moves the world** via clocks — the §12.1 deterministic executor,
   host-side per ruling: pre-authored `fires_when` effects committed
   through the engine's write gate;
4. **paces** via the arc-weighted dramatic-irony delta, computed host-side
   as a diff over two materializations (canon vs `knows:player`);
5. **briefs the narrator** with a GM lane composed per turn — Cognitive
   UI discipline: what is surfaced is the narrator's control set. **The
   briefing carries NO `plot:` content** (letter 012): the GM lane is
   the `knows:player` scene + NPC intents + ONE pacing directive +
   resonances. Navigation toward the destination is done by the SYSTEM
   (clocks, nudges, the navigator's rung choice), never by narrator
   intent.

The concealment/progress split (ruled letter 004, **strengthened by
letter 012**): arc *progress* (what enters `knows:player`, which beats
count achieved) is gated structurally by the arc graph — unchanged. Arc
*concealment* is now ALSO structural at the narrator: the narrator never
sees `plot:` (the whitepaper §14 GM soft spot closed at the narrator
level). The residual behavioral surface shrinks to the nudge-content
pick — one cheap, plot-aware call distilling ONE directive, its output
logged to `session:main` like every pacing decision. Timing rests on
judgment; content goes through the gate.

---

## 2. The arc grammar

Everything below is assertions over entities (the two primitives), written
to `plot:main` with ordinary provenance. No new engine concepts.

### 2.1 The arc

```
(arc:main · kind · arc)
(arc:main · protagonist · person:<pc>)
(arc:main · conclusion_shape · shape:<id>)        # §6 — the destination
(arc:main · climax_ready · any_2_of{beat:a, beat:b, beat:c})
                                                  # sufficiency set, same
                                                  # grammar as mystery
                                                  # solution sets
(arc:main · phase_budget · {setup: 12, rising: 25, crisis: 10, …})
                                                  # soft turn budgets,
                                                  # genre-set at session zero
```

### 2.2 Beats

A beat is a *world-state condition with narrative weight*, not a scripted
scene. Path-independence is definitional: any trajectory that satisfies
the condition achieves the beat.

```
(beat:x · kind · beat)
(beat:x · part_of · arc:main)
(beat:x · phase · setup | rising | crisis | climax | falling)
(beat:x · weight · required | optional | flavor)
(beat:x · achievable_via · <condition expr>)       # §2.3
(beat:x · unreachable_if · <condition expr>)       # early repair trigger
(beat:x · status · pending)                        # STATE in plot:, folds
                                                   # by supersession:
                                                   # pending → achieved | closed
(beat:x · justified_by · {assertion_ids})          # written with status:
                                                   # the assertions whose
                                                   # truth satisfied the
                                                   # condition — EVENT rows
                                                   # when events satisfied
                                                   # it, STATE/containment/
                                                   # frame rows otherwise
                                                   # (assertions are
                                                   # addressable entities;
                                                   # Codex r1 finding 4)
```

Provenance mapping (the engine's own vocabulary, unmodified):
session-zero authoring = `stated` (authored canon of the hidden frame);
beat achievement = `inferred` with justification pointing at the canon
events that satisfied it; repair-authored beats (§7) = `generated`
(resolver-style invention under canon constraints). "Was that always the
plan?" stays answerable forever — the engine's provenance does the work.

### 2.3 The precondition atom grammar

```
expr  := atom | all_of{expr…} | any_of{expr…} | any_k_of(k){expr…} | not_(atom)
atom  := in_frame(frame, entity·attr·value)   # "player knows F" =
                                              # in_frame(knows:player, …)
       | state(entity, attr, value)           # canon current-state fold
       | located(entity, place)               # containment walk
       | occurred(event_kind, participants?, within?)  # event-spine match
       | beat_achieved(beat:id)
       | clock_fired(clock:id)
```

Rules:
- Atoms reference **canon and `knows:` frames only** — plus `plot:`
  strictly via `beat_achieved`/`clock_fired`. A beat never gates on raw
  `plot:` facts: the arc is achieved from world truth, not from its own
  bookkeeping.
- **`in_frame` evaluates the current fold** of the target frame —
  non-superseded, non-retracted assertions, `as_of` now by default. Stale
  superseded knowledge and retracted beliefs do not satisfy "the player
  knows F" (Codex r1 finding 3).
- **Evaluation is three-valued: true / false / indeterminate.** An atom
  whose referent is an unresolved thunk, below the resolution floor, or an
  underdetermined identity evaluates *indeterminate* — and indeterminate
  never satisfies `achievable_via` AND never satisfies `unreachable_if`
  (conservative in both directions; Codex r1 finding 2). `not_` over an
  `occurred` atom is honest log-closure (fiction stance: an event absent
  from canon did not happen — in tracking stance this atom would be
  illegitimate); `not_` over `state`/`located`/`in_frame` is definite only
  where the aspect is resolved, indeterminate otherwise — negation never
  collapses *unknown* into *false*.
- `occurred()` composes deterministically from
  `materialize(lens="what_happened", since=, as_of=, scope=)`, which
  returns structured rows with kind / agent / patient / `caused_by`
  (shipped, Kernos letter 007). **Authoring convention, binding on
  session-zero and the turn loop:** `agent` and `patient` are emitted as
  entity-valued attributes on `event:` entities — the engine stores and
  serves them structurally, never interprets.
- Every atom is a deterministic engine read (state folds, containment
  walks, `what_happened` event matches, frame membership). **Beat
  evaluation is structurally decidable**; the cohort (§4.1) only proposes
  *candidates*, never verdicts.

### 2.4 Clocks (host-side deterministic executor — ruled)

```
(clock:c · kind · clock)
(clock:c · bound_to · beat:x | arc:main)
(clock:c · fires_when · <condition expr + turns_quiet(n) | turns_elapsed(n)>)
(clock:c · rung · surface | draw | converge | confront)   # §5, nudge clocks
(clock:c · effects · <pre-authored structured items>)
(clock:c · rearm · once | repeat)
(clock:c · status · armed)                  # armed → fired | disarmed
```

The host evaluates `fires_when` each turn after ingest; firing commits
`effects` through `ingest_structured` — pre-authored judgment, deferred
ingestor writes, no new authority (P8). **Every clock effect must carry a
`caused_by` chain into existing canon** (the conspiracy's own logic, not
GM whim) — this is the diegetic-motivation invariant, and it is auditable
(§9d).

**Firing semantics (Codex r1 finding 7):** every firing is logged as an
event row in `plot:main` (`event:clock_c_fired_<n>`, with the turn and the
satisfied condition as justification). `clock_fired(clock:c, n=1)` is
defined as *at least n logged firings exist* — unambiguous for `repeat`
clocks; `status` folds to armed/disarmed separately and is never the
firing test. Turn counters (`turns_quiet`, `turns_elapsed`) fold from the
session frame (§2.5), never from host memory.

### 2.5 The session frame (the host's own ledger)

"Turn" and "quiet" are host concepts the engine deliberately does not own
(Codex r1 finding 5). They live in a **host-owned named frame,
`session:main`** — the same mechanism as `plot:`, the same sanctioned
doorway (`ingest_structured(frame="session:main")`), structurally absent
from canon and `knows:*` payloads:

- one turn-boundary row per turn (`event:turn_<n>`, with scene cursor);
- every pacing decision: each nudge directive issued (rung, thread,
  turn), each rung-availability refusal, each policy verdict — the
  receipts culture applied to drama management (Codex r1 finding 6);
- repair events and their lineage chains (§7).

Definitions that fold from it: `turns_elapsed` = turn rows since arming;
`turns_quiet` = turns since the last beat achievement **and** the last
player interaction with any arc-referenced entity (so high-action but
arc-irrelevant play counts as quiet — the precise definition the refusal
clock needs, §8). Everything the pacing layer knows is rebuildable from
the buffer; the host stores nothing.

---

## 3. The navigation loop (per turn)

After the player's action ingests as canon, the **world tick** runs in
the founder's serial order (letter 012; full turn DAG in TURN-LOOP.md):

1. **Clock pass**: evaluate `fires_when` over all armed clocks; fire
   through the gate, `caused_by`-chained. Clocks read the *previous*
   turn's beat state (beats evaluate at step 3) — one turn of latency
   between a beat achievement and a clock's reaction, by construction.
2. **NPC world-actions** (turn-loop concern; decisions parallel,
   commits serialized — TURN-LOOP §2).
3. **Beat evaluation, LAST in the tick** so it sees all of this turn's
   mutations (§4): **all pending beats are re-evaluated every turn** —
   the spec'd default (letter 006, note 1). The atoms are deterministic
   reads and fiction-scale arcs hold a few dozen beats; a dirty-tracking
   dependency index is permitted only as a *measured* optimization with
   re-eval-all as its fallback, because a dirty-index bug silently fails
   to fire a beat — the worst failure class: the story stalls invisibly.
   Achievements are written to `plot:main` as `inferred` with
   justification.

Then the read-side (parallel fan-out, TURN-LOOP §2):

4. **Instrument read** (§4.2): recompute the arc-weighted irony delta and
   progress trend.
5. **Pacing policy** (§5): a deterministic table maps (phase, progress
   trend, delta trend, rungs used, phase budget) → {hold, surface, draw,
   converge, confront}.
6. **Briefing composition**: the `knows:player` scene + NPC intents +
   at most one nudge directive + loop-closure resonances (PB letter
   013), surfaced into the briefing, never left to narrator memory.
   **No `plot:` rows, ever** (§1; auditable per turn — TURN-LOOP §6b).

Deterministic spine, model judgment only at the boundaries (beat-candidate
spotting, nudge content selection, rendering) — the Kernos cohort
discipline applied to drama management.

## 4. Instruments

### 4.1 The beat-evaluator cohort

Quiet Cohort shape: selectively invoked (only when the turn's ingested
events touch entities referenced by pending beats' atoms — a deterministic
relevance filter), fail-open (a broken evaluator never blocks the turn;
beats simply wait), silent. It proposes which beats to re-check; the
**verdict is the structural evaluation** of §2.3 atoms. Narration-audited
completion transposed: a beat is never achieved because the prose sounded
conclusive.

### 4.2 The arc-weighted irony delta (host-side — ruled)

The raw dramatic-irony delta is canon minus `knows:player`. **Computation
spec (Codex r1 finding 12):** both sides materialize with
`lens="current_state"`, `budget=None` (unbudgeted — never compare
budget-shaped projections), `default`-provenance fills excluded (render
coherence, not facts); the diff is assertion-level on (entity, attribute,
value) keys. This *uses* the projection; it does not reimplement frame
semantics — and it is replaced wholesale by the engine's queued sixth
read (frame-diff; HD is its first named consumer, letter 007) if that
ships.

The arc weighting, defined precisely (Codex r1 finding 11): **the count
of distinct undelivered canon assertions — deduplicated by assertion id —
referenced by pending `required` beats' preconditions and the conclusion
shape's `world_condition`.** It is a *proxy* for story-remaining, not a
measure: stakes unreferenced by any precondition are invisible to it (by
design — the arc cares about its own preconditions), and it is therefore
never read alone: the pacing table consumes it only alongside the
progress trend.

**Honest limit (Codex r1 finding 13):** the delta bounds what the player
has been *given*, not what they have *inferred*. A player can run ahead
of their frame (inference, genre savvy); they can never be behind it,
because the turn loop's discovery gating writes narrated facts into
`knows:player` as they are delivered. The delta is thus an upper bound on
story-remaining, and the policy reads *trends*, which a constant
inference-lead does not flip.

### 4.3 Signal derivations (all fold from the buffer; Codex r1 finding 6)

- **phase** — STATE on `arc:main` in `plot:`, advanced by a phase clock
  (required-beat completion or budget exhaustion), superseded normally.
- **progress trend** — beat achievements over the last K turn rows
  (`plot:` folds joined to the §2.5 turn ledger).
- **delta trend** — the §4.2 value recomputed each turn; each reading is
  logged to `session:main`, so the trend is itself rebuildable.
- **rungs used** — folds from the logged nudge directives in
  `session:main`.

## 5. The nudge ladder (anti-railroading by construction)

Escalation is proportional and diegetic. Four rungs:

| Rung | Mechanism | Example (meter conspiracy vs bakery player) |
|---|---|---|
| **surface** | Briefing directive only: the world *mentions* an unwalked thread | Customers gossip about the dark meters |
| **draw** | A *fact* delivered into an NPC's `knows:` frame through the gate; the NPC engine decides per its own pre-existing dispositions | The clerk learns the baker asks questions; *chooses* to visit |
| **converge** | A clock fires; plot consequences arrive in the player's chosen domain, `caused_by`-chained | The bakery street's meters go dark — the conspiracy's own logic |
| **confront** | The crisis arrives uninvited (phase-budget exhaustion) | The blackout reaches the whole quarter |

Hard guards, in order of importance:

1. **No intervention, ever.** The arc layer never blocks, undoes, or
   reinterprets a player action to protect the plot. Accommodation only
   (§7). (Riedl & Young's mediation taxonomy, with the intervention half
   deliberately amputated.)
2. **NPCs cannot be puppeted.** A draw-rung nudge may only add **facts**
   (knowledge-frame rows) to an NPC's frame through the gate — **never
   motives**: DISPOSITIONAL rows are who the NPC *is*, and writing one
   would be character editing, puppeting by another name (Codex r1
   finding 10). The character engine acts on its own pre-existing
   dispositions; if no NPC's existing dispositions would plausibly act on
   any deliverable fact, the draw rung is *unavailable* — the same
   availability discipline as converge's coincidence budget.
3. **Coincidence budget.** Converge effects must trace `caused_by` into
   pre-existing canon processes. If no plausible chain exists, the rung is
   unavailable — the policy holds instead.
4. **Timing on the leash, content through the gate.** *When* to escalate
   is GM judgment; *what* an escalation does is pre-authored or
   resolver-invented under canon constraints, with receipts.

**The ladder is monotone, not mandatory-sequential.** A rung whose guards
make it unavailable (no plausible recipient for draw, no causal chain for
converge) is *skipped*, and unavailability is logged to `session:main`.

**The anti-contact attack, answered (Codex r1 finding 9).** A player can
break every contact-dependent rung: kill the messengers, relocate away
from each affected domain, fill every turn with arc-irrelevant action.
The design terminates anyway, by construction: (a) `turns_quiet` counts
arc-irrelevant action as quiet (§2.5), so high-action evasion still
advances the refusal clock; (b) the confront rung's effects must be
world-scale — arc lint forbids them from depending on any specific NPC's
survival or the player's location (§9); (c) the refusal clock (§8) is
**contact-independent by construction** — its `fires_when` references
only turn counters, which no in-world behavior can starve. The ladder can
be fully evaded; the *ending* cannot. Engagement remains invited, never
forced — the §8 limit stands.

## 6. The conclusion shape (session-zero output, summarized)

The destination is a **state-shape plus a character delta**, never a
scripted scene:

```
(shape:s · kind · conclusion_shape)
(shape:s · delta_type · drive_inverted | desire_at_cost | desire_renounced
                       | identity_accepted | homecoming_changed)
(shape:s · tension · (person:pc · drive · A > B))   # the mined pair
(shape:s · world_condition · <condition expr>)       # final-state predicate
(shape:s · premise · <condition expr>)               # what must remain true
                                                     # for the shape to be
                                                     # pursuable (tension
                                                     # unresolved, key
                                                     # entities extant)
(shape:s · refusal_variant · shape:s_refused)        # MANDATORY (§8)
```

**The shape is evaluated continuously, like a beat** (Codex r1 finding
15). Three outcomes each turn, replacing any binary "premise destroyed"
test: (i) `premise` holds → navigation continues; (ii) the character
delta *occurs through authentic play* before the authored climax — the
tension pair inverts or is paid for in canon — and `world_condition` is
satisfiable: the arc **concludes early as a success**, moving to
denouement. A player who grows ahead of the story is the arc *working*,
not refusing; (iii) `premise` entities are destroyed without the delta →
arc repair (§7) if budget remains, else the refusal variant. Authentic
growth, premise destruction, and refusal are three different things and
are never conflated.

Generation, given an arbitrary character: mine the character's
DISPOSITIONAL rows for the strongest *ordered tension pair* (conflicting
drives, a fear crossing a drive, a `breaks_if`); the conclusion is the
event-shape that forces the ranking to invert or be paid for. The clerk
who hid the core (`drive · prevent_panic > truth`) gets the circumstance
where concealment causes the panic.

**Theme consent:** the player is pitched the *theme* ("a story about the
cost of mercy"), never the *plot*. Consent and hiddenness coexist: the
pitch is the delta type; `plot:main` holds the instantiation.

**Session-zero invariant (new spec rule):** no playable character without
a minimum dispositional spine — two ranked drives plus one fear or
`breaks_if`. Thin characters (the arbitrary charcoal burner) get their
spine authored in the interview's character section before arc generation
runs. This makes "book-like conclusion for an arbitrary character"
*computable* rather than aspirational.

## 7. Arc repair (accommodation as supersession)

Trigger: a `required` beat's **authored** `unreachable_if` fires — and
that is the *only* impossibility detector (Codex r1 finding 16). There is
no host-side reachability reasoner: unreachability the author did not
anticipate goes undetected until the refusal clock catches the stall,
which is acceptable because the refusal clock is the universal backstop
for every undetected failure mode. Repair is **lazy** — only on flagged
impossibility, never speculative replanning.

Mechanism: one main-tier call, handed canon + the conclusion shape +
the closed beats, proposes replacement beats preserving the **shape** (the
thematic destination is stable; its instantiation is replannable).
Committed to `plot:main` as `generated`, superseding the closed beats,
with a repair event whose justification names the player action that
forced it. **Authority: RESOLVED (PB 029, letter 007).** The host writes
`generated` rows via `ingest_structured(frame="plot:…")`; the gate
composes resolver authority underneath for those appends, and **refuses
`generated` into canon or `knows:*`** with an explicit error — the role
matrix intact at the buffer layer, the design structurally protected.
Whitepaper §12.1 already blessed the shape: arc repair IS "improvised
off-screen development routed through the resolver." The story's history
of bending is itself auditable — "the story changed here because the
player did X."

**Termination and novelty (Codex r1 finding 14):**

- **Repair budget:** at most R repairs per beat *lineage* (the
  supersession chain, tracked via the repair events in `session:main`).
  Budget exhausted → fall through to the §6 shape evaluation (early
  conclusion or refusal variant — never an R+1th repair).
- **Novelty check in post-repair lint:** every replacement beat's atoms
  are evaluated against *current* canon at lint time; any atom already
  false-or-indeterminate-forever (its referent destroyed) fails the lint
  — a repair may not reintroduce the impossibility that forced it under
  a new name.
- **Cascade damper:** a repair triggered within K turns of a prior repair
  on the same lineage escalates directly to the shape evaluation instead
  of repairing in place.

Premise destruction, authentic early growth, and refusal route through
the §6 three-outcome shape evaluation — there is no state from which the
arc has no authored exit.

## 8. The refusal branch (pressure test 1, resolved by construction)

A player who refuses the arc is not an error; refusal is **a path through
the arc**. Required machinery:

- Every conclusion shape carries a `refusal_variant` (arc lint enforces
  it): the world's story concludes *around* an absent protagonist —
  the conspiracy completes, the town suffers, the denouement evaluates
  what the player's absence meant. Tragedy of absence is an authored
  ending, not a soft-lock.
- **The refusal clock is a formal grammar object, not prose** (Codex r1
  finding 8): every arc carries exactly one
  `(clock:refusal · fires_when · turns_quiet(N))` whose effects conclude
  via the refusal variant. Its `fires_when` may reference **turn counters
  only** (always-evaluable, three-valued-proof, contact-independent — no
  in-world behavior can starve it), with `turns_quiet` as defined in
  §2.5. Arc lint checks its existence, its counter-only condition, and
  that N is reachable from every phase's budget — machine-checkable, not
  aspirational.
- The nudge ladder makes the player's chosen activity the *medium* of the
  story, never an obstacle: gossip in the bakery, the clerk as customer,
  the meters on the bakery street. The arc comes to where the player is.
- Honest limit, stated: a player who refuses every thread gets a coherent
  world that concludes without them. Boredom is not a failure of
  coherence; the layer guarantees the second, only invites the first.
  **This limit is a deliberate stance, to be defended in review** (letter
  006, note 3): any machinery that *forces* engagement would be the
  railroading the §5 ladder exists to prevent. Do not engineer it away.

Walked through (meter conspiracy / bakery player): stall detected after
K1 quiet turns → gossip (surface) → the clerk visits (draw) → bakery-street
meters dark (converge — conspiracy logic, caused_by intact) → phase budget
exhausts → quarter blackout (confront) → still refused → refusal ending
fires by final clock. Five rungs, all diegetic, no action ever blocked,
ending authored. The arc survives.

## 9. Arc lint + eval criteria

**Arc lint** (deterministic, run at session zero and after every repair):

1. Every atom references existing entities/frames (or thunks at the known
   resolution floor).
2. ≥ 2 disjoint precondition paths into the climax sufficiency set
   (path-independence, mirroring the mystery two-traversal criterion).
3. Every `required` beat has a bound escalation clock.
4. The refusal clock exists, its `fires_when` is counter-only, and its
   threshold is reachable from every phase's budget (§8 — machine-
   checkable).
5. No beat gates on raw `plot:` facts (only `beat_achieved`/`clock_fired`).
6. Phase budgets sum to the session-length intent from session zero.
7. Confront-rung clock effects are world-scale: they reference no
   specific NPC's survival and no player location (§5 anti-contact
   guarantee).
8. **Post-repair only:** every replacement beat's atoms evaluate against
   current canon as satisfiable-or-pending — never already-impossible
   (the §7 novelty check).

**Play-graded eval** (the arc layer's §19.2 analogue):

- (a) the arc concludes via ≥ 2 distinct player strategies;
- (b) a refusal run reaches the authored refusal ending — no soft-lock;
- (c) **concealment audit:** every plot-relevant fact in rendered prose is
  present in `knows:player` ∪ the turn's briefing. This is a **post-hoc
  audit over the log** (the render is ingested as canon; the audit checks
  whether any fact entered via render unlicensed by `knows:player` ∪
  briefing) — explicitly NOT a render-time gate; it adds zero latency to
  the turn (letter 006, note 2). The leash made diffable from receipts;
- (d) **diegesis audit:** every fired clock effect carries a `caused_by`
  chain into pre-existing canon;
- (e) **no narration-fiat progress:** every achieved beat's justification
  points at canon events;
- (f) post-repair arcs still lint; conclusion shape preserved.

## 10. Prior art and the bounded claim

Method: desk pass over the drama-management literature plus two live
sweeps (2026-06-12); PB's prior-art survey covers the world-state lineage
(Versu, Ceptre, CiF, storylets, lorebooks) and is incorporated by
reference. Full citation verification before any public claim.

**Destination-directed management:** Oz search-based drama management
(Weyhrauch 1997); declarative optimization-based DM (Nelson & Mateas
2005); narrative mediation with accommodation/intervention (Riedl & Young
2006–2010) — our repair is their accommodation, with intervention
deliberately removed and the replan stored as auditable supersession.
**Beat/precondition grammars:** Façade's beats (Mateas & Stern 2003);
storylets / quality-based narrative (Failbetter; Kreminski &
Wardrip-Fruin 2018) — `achievable_via`'s folk twin, over an
overwritten-current quality vector. **Pacing instruments:** Left 4 Dead's
AI Director (Valve 2008) — affective intensity estimation; ours is
epistemic (a knowledge-gap measure), which no surveyed director uses.
**Player-adaptive selection:** PaSSAGE (Thue et al. 2007). **Author-goal
ancestry:** Universe (Lebowitz 1985). **LLM-era neighbors (2024–26):**
Drama Llama — LLM storylets with natural-language preconditions (arXiv
2501.09099); Dramamancer (UIST 2025 adjunct); StoryVerse (arXiv
2405.13042); STORY2GAME — LLM-generated preconditions/effects as
executable code; playwriting-guided generation + plot-based reflection
(ACL 2025, arXiv 2502.17878); DiaryPlay's branch-and-bottleneck.

**Bounded novelty claim** (per letter-024 discipline): beat preconditions,
destination-directed management, and pacing instruments are all
individually precedented above. Found in no surveyed system: (1) the arc
stored as first-class assertions **inside the same persistent,
provenance-bearing, perspective-scoped world store it manages**, concealed
by the identical structural mechanism that scopes NPC knowledge —
destiny-as-a-frame; (2) an **epistemic pacing instrument** computed as a
frame diff (canon minus player knowledge) over a queryable log; (3) arc
repair as **auditable supersession with provenance** — "was that always
the plan?" permanently answerable. Claims bounded to systems surveyed;
never absolute.

## 11. What the engine's §14 must support (distilled for PB)

The arc layer runs **entirely host-side** on the shipped porcelain. The
complete requirement set (companion [DECISION] letter carries this):

- **Shipped, sufficient:** `ingest_structured(items, frame=)` with
  per-item frames (PB 028); `materialize(frame=, as_of=, lens=)`;
  deterministic state/containment/event reads; `caused_by` as fixed
  predicate.
- **CONFIRMED + shipped (PB 029, letter 007):**
  `materialize(lens="what_happened", since=, as_of=, scope=)` bounds both
  time ends and returns structured kind / agent / patient / `caused_by`
  rows — `occurred()` atoms ride on it, under the §2.3 agent/patient
  authoring convention. **`deny`/`reserve` is LIVE** (the spike-stub note
  was stale): per-thunk `?{"policy": "deny"}` raises `ResolutionDenied`
  on force — usable at first-playable today for player-reserved entrances
  and sealed revelations. Host-authored `generated` into host-owned named
  frames is sanctioned with resolver authority composed at the gate (§7).
- **Soft ask, queued:** the scoped assertion-level frame-diff read (canon
  minus `knows:<id>`) is logged as the porcelain's sixth-read candidate
  with HD as first named consumer; until/unless it ships, the §4.2
  double-materialize-and-diff stands.
- **Explicitly NOT needed engine-side:** clocks (ruled mine), beat
  evaluation, sufficiency-set evaluation, pacing policy, nudge selection,
  drama metrics. §14.2/14.3 can stay thin in the engine; the vocabulary
  (`discoverable_via`, `fires_when`) is just assertions, and Holodeck
  evaluates it as orchestration. Mystery discovery-gating (what enters
  `knows:player` on inspect/press) likewise runs host-side through
  `ingest_structured(frame="knows:player")`.

## 12. Open questions (tracked, none blocking)

1. Multi-arc worlds (a main arc + character subplots as separate `plot:*`
   frames) — deferred; grammar already namespaces (`plot:main`).
2. Beat *granularity* heuristics for the session-zero author (how many
   beats per phase per session-length) — empirical; tune at first
   playable.
3. Whether the irony-delta enumeration should exclude `generated`-
   provenance canon (resolver inventions the player "hasn't earned") —
   leaning no; provenance-blind delta is simpler and the weighting already
   filters. Revisit with play data.
4. ~~Repair-write authority~~ **RESOLVED** (PB 029, letter 007): see §7 —
   `generated` via `ingest_structured` into host-owned frames, resolver
   authority composed at the gate, canon/`knows:*` refused.
5. Calibration constants — R (repair budget per lineage), K (cascade-
   damper window), the pacing table's quiet thresholds, N (refusal
   clock) — all empirical; set provisional values at first playable and
   tune with play data.
