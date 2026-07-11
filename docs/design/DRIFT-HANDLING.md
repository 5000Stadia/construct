# Drift Handling — when the player leaves the road (spec)

**Status:** SPEC r2 — cx review r1 RED (`<d645fd14…>`, six persistence/
ordering contract gaps) FOLDED: the closure-witness contract (§2), drift_pass
ordering pinned before lifecycle (§4), the append-safe beat-replacement
membership model (§3 R4), the diegetic-minute drift gate replacing the false
turns-are-free claim (§3 R2 / §2), the R3 event graph made real (routine
moment_missed; situation-lens + directive surfacing; the causal-ripple claim
retracted), and the shared carrier-move commit surface extracted from
world-tick (§3 R2). For cr review, then phased build (task number TBD; the
headline design item after LWG P2). The founder's captured
4-part design (2026-06-22, extended 2026-06-24 with relocate-the-beat): *"If
the player ignores the established call to action, GENTLE nudges back to the
primary narrative help — nothing heavy-handed. If I skip the important meeting
and go to the pub the next day, the engine should (a) IMPROVISE the very real
effect of my absence AND (b) provide an improvised ALTERNATIVE PATH to any
predetermined plot points."* Plus the classic D&D move: re-stage the dodged
beat's mechanic wherever the player actually went.

Builds ONLY on shipped surfaces: the LWG P1/P2 machinery (fallout doorway,
generator guards, right-of-way, the development ledger), the `salient_moments`
reader (designed with this spec as its second consumer — P2 spec §A: "one
reader, several consumers"), the fact-source v3 `narrator_promote` handoff
(retained per Cx 567 *for future drift-handling readers*), the arc grammar
(`Beat.achievable_via` path-independence), and the convergence Phase-1
relocate directive. No engine change of any kind.

## 1. Problem

Today, when the player walks away from the authored road:

- **The nudge ladder** (`navigate` rungs → `nudge_pick`, cohorts.py:2972;
  `weave_pick` subsumes it in cast worlds) surfaces an unwalked thread — the
  only *active* pressure, and it can only point, never adapt.
- **The refusal clock** eventually fires and the arc dies `lost` — a timeout,
  not a story.
- **`unreachable_if`** closes a foreclosed beat (executor `beat_pass`) — and
  repair is explicitly post-v1: a closed REQUIRED beat today just waits for
  the refusal clock, because `_repair_exhausted` (executor.py:558) is
  operationalized as "the refusal clock fired" — the `repair_budget` named in
  its docstring is a reserved word with no counter behind it.
- **The convergence directive** (STORY-SHAPE-AND-RESOLUTION.md, Phase 1
  shipped) tells the narrator *in prose* to bring the climax to the player —
  but nothing re-stages a specific dodged beat *mechanically*: the clue-holder
  stays where the cast blob put her, presence truth never moves, and the
  "relocation" is only as durable as one turn's prose.
- **Skipping costs nothing.** The world does not move at the skipped site; the
  meeting the player dodged is eternally about to happen. This violates both
  the consequence-callbacks ruling (the world presents your consequences back
  to you) and world-moves-without-you (#84) in spirit — #84 ticks the world's
  own business off-screen, but no machinery turns *the player's absence* into
  a felt world-fact.

The sealed rulings this spec must not violate: **turns are free** (only
diegetic time is the clock — contemplation is never drift); **no puppetry**
(the world moves *at* the player, never *as* them); **convergence, not
coercion** (converge the *scene*, never the *verdict*); **incompletable =
repair-EXHAUSTED, never first-unreachable**; **the membrane** (derived
notions are never canon; consequences are concrete world-facts through the
ingestor doorway).

## 2. What drift IS (three classes, structurally detected)

Drift is never inferred from prose or from turn counts. Three classes, each
keyed to a shipped structural signal:

- **D-SOFT — wandering.** Pending REQUIRED beats exist, the escalation rungs
  are rising, AND the world has been development-quiet for
  `RELOCATE_QUIET_MIN` **diegetic minutes** (read from the LWG development
  ledger, `session:ambient` / `last_development_min`). **Correction (cx r1
  finding 4):** the shipped rung ladder counts TURNS (`counters.turns_quiet`,
  executor.py; `counters_from_session` counts turn events) — it does NOT
  respect diegetic time, and this spec no longer claims it does. Every NEW
  drift trigger here keys on the story clock, honoring the sealed
  turns-are-free ruling: 30 contemplation turns = five in-world minutes = no
  drift. The rung is a NECESSARY co-signal (story pressure is rising), the
  diegetic quiet gate is the license. *Flagged for the founder (open item):
  the pre-existing rung ladder itself remains turn-counted — outside this
  spec's scope, noted for a future ruling.*
- **D-MISSED — the skipped moment.** A REQUIRED beat was closed by a
  CLOCK-CAUSED foreclosure, proven by the closure witness (below). The
  window passed; the player was at the pub. Distinct from D-HARD because
  there is an ABSENCE to narrate — though see the occurrence rule: a fired
  deadline proves only that the window closed, never that the staged moment
  happened.
- **D-HARD — foreclosure.** A REQUIRED beat closed by a WORLD-STATE
  foreclosure (the witness died, the ledger burned) — or ANY closure whose
  witness is absent, mixed-undecidable, or pre-contract. Nothing "happened
  without" the player; the path itself is gone. D-HARD is the CONSERVATIVE
  default.

**The closure-witness contract (cx r1 finding 1 — the provenance this spec
needs does not exist yet and is built in D2):** today `beat_pass`
(executor.py:201-209) writes only `status=closed`; `justified_by` is written
on ACHIEVEMENT only and holds only `{turn}`. D2 adds: on closing a beat,
`beat_pass` also writes a **closure witness** row (`plot:` frame,
`beat:<id>` / `closure_witness`, `valid_from=turn_time(turn)` — horizon-safe)
recording the EVALUATED witness of the closing evaluation: the set of leaf
atoms of `unreachable_if` that evaluated TRUE, with their kinds and ids.
Atom *presence* in the expression is never proof — for compound
`AnyOf`/`AllOf`/`AtLeast`/`Not` shapes the witness records what actually
evaluated TRUE at close time.

**Classifier (conservative, witness-based):** D-MISSED iff the witness
proves the closure CLOCK-CAUSED — at least one `ClockFired` leaf evaluated
TRUE, AND re-evaluating the expression with all clock leaves forced FALSE
yields not-TRUE (the clock was NECESSARY, not incidental to a mixed
condition). Anything else — no witness (pre-contract closures), mixed
compound where the world-state half sufficed, undecidable — classifies
D-HARD. `drift_state(pending_required, closures_with_witnesses, rung,
quiet_minutes, …) -> list[Drift]` stays a pure reader in the
`salient_moments` discipline: explicit inputs, no hidden reads,
unit-testable without a world.

**The occurrence rule (cx r1 finding 1, second half):** a fired deadline
never establishes that the staged moment OCCURRED — only that its window
closed. R3 consequences are therefore LAPSE-facts by default ("the window
closed", "your seat was noted empty") grounded in the beat's staging
context. Asserting the moment happened ("the vote landed 4-1") requires an
AUTHORED occurrence: an optional build-time annotation on the beat/clock
(`on_expiry` occurrence note) that licenses occurrence-facts. No
annotation → no occurrence claim, ever.

## 3. The four responses (lightest first — the founder's order of preference)

| | Response | Drift class | Weight |
|---|---|---|---|
| R1 | Gentle nudge-back | D-SOFT | shipped; tuning only |
| R2 | Relocate the beat | D-SOFT (rung high), D-MISSED | new; **preferred whenever the mechanic can travel** |
| R3 | Absence-consequence | D-MISSED | new |
| R4 | Alternative-path repair | D-HARD, or D-MISSED where the mechanic cannot travel | new; heaviest |

At most ONE drift response per turn (the same structural rule as the
generator's one-mint-per-turn). R3 pairs *with* R2 or R4 on the same D-MISSED
beat but across turns: the consequence lands first (the world moved), the
re-staged or repaired path follows (the story adapts).

### R1 — Gentle nudge-back (tuning, per the founder's "nothing heavy-handed")

`nudge_pick` stays the mechanism. Three tuning rules, all host-side:

1. **No re-preach:** never surface the SAME thread on consecutive nudges — a
   `session:` receipt of the last surfaced thread; `nudge_pick` gets the
   exclusion. (Proportion ruling: an unchanged situation does not earn a fresh
   tableau.)
2. **Diegetic cadence:** a nudge fired within the last `NUDGE_QUIET_MIN`
   diegetic minutes suppresses the next — read off the same
   `read_clock(world).minutes` the ambient trigger uses. Thirty contemplation
   turns = five in-world minutes = at most one nudge.
3. **Escalation stays diegetic:** the rung ladder escalates *pressure in the
   fiction* (a runner arrives; the deadline talk sharpens), never meta
   urgency. Already the `nudge_pick` prompt's contract; restated as a test
   oracle, not a new rule.

### R2 — Relocate the beat (the new mechanical core)

**Principle (founder):** a beat IS its plot MECHANIC (deliver this clue /
force this choice / reveal this fact), DECOUPLED from its STAGING (where /
who / when). `Beat.achievable_via` is an Expr over world-state —
path-independent by definition (grammar.py:39) — so the SAME beat fires via
re-staged events at the current scene: no new beat, no dead-end, no rebuilt
route.

**What relocation concretely is:** re-staging the beat's *delivery*.
`beat_delivery_targets` (cast.py:254) already names the fact each InFrame
beat needs delivered; the cast blob names who holds it. Relocation moves the
carrier — or re-homes the delivery onto a present, fiction-plausible channel:

1. **Detect:** a D-MISSED beat, or a D-SOFT beat whose rung has reached the
   relocation threshold (below SURFACE→…→REFUSAL's terminal rung — relocate
   BEFORE the refusal clock is in sight) AND whose diegetic quiet gate is
   open (§2 D-SOFT: `RELOCATE_QUIET_MIN` story-clock minutes since the last
   development).
2. **Pick the staging:** a cheap-tier cohort (`relocate_pick`, the
   `nudge_pick` shape) receives the beat's mechanic (its delivery target,
   NEVER the hidden answer beyond what the carrier may say), the player's
   current scene, the present cast + spined set, and the turn's
   `salient_moments` fuel — "what just changed + who is positioned to care,"
   the exact read the P2 spec reserved for this consumer. It returns: the
   carrier (the original holder, moved; or a present equivalent the fiction
   licenses), the staging line (how the mechanic arrives HERE), and a
   confidence. Decline on low confidence — relocation must feel inevitable,
   not conjured (unveil-intelligently, not script).
3. **Move the carrier in CANON, not in prose — through a SHARED commit
   surface (cx r1 finding 6).** `_world_tick` is a whole autonomous cohort
   policy (elapsed-floor, discovery gating, anchoring, roster, current-scene
   exclusions) — it is never called to force a selected relocation. D1
   instead EXTRACTS the host-owned carrier-move surface both paths use:
   `commit_carrier_move(world, person, dest, turn, *, scene, protagonist,
   companions, horizon)` — the validator + commit half (never-the-player /
   never-a-bound-companion / anchor / scene / horizon guards, then the canon
   `in`-row commit with receipt audit), factored from world-tick's low-level
   move and re-consumed by it. R2 calls this surface *before* the narrator
   stages the arrival — presence truth moves first, so the narrated arrival
   matches canon and the #80 cast-moves lane (or the promote gate) sees no
   contradiction. An INVALID carrier move (guard-rejected) produces NO
   briefing directive and NO relocation receipt — the response declines
   whole. The narrator gets the staging directive only after a confirmed
   commit. If the delivery re-homes to an already-present carrier, no move
   is needed — only the directive.
4. **Relocation receipt** (`session:` frame, per-beat): beat_id, old staging,
   new staging, turn. One relocation per beat until its staging is
   invalidated again (no re-relocate thrash — the Phase-2 note in
   CONVERGENCE-TO-CONCLUSION.md, now real). A beat that drifts AGAIN after
   one relocation escalates to R4, not to a second relocation.
5. **The beat itself is untouched.** Same beat_id, same `achievable_via`,
   same phase/weight. For a D-MISSED beat (status=closed), relocation is
   paired with the R4 mechanism's re-open (below) — the mechanic travels, the
   closure is repaired; the repair budget is charged.

**Concealment guard:** the relocated carrier brings the MOMENT, not the
answer. The directive inherits the concealment block; `relocate_pick`'s
output is sanitized like generator hooks (`_sanitize_hook` — no id tokens, no
system-speak).

### R3 — Absence-consequence (the world moved without you)

On D-MISSED, the lapse becomes TRUE canon — the same doorway discipline as
`emit_fallout` (executor.py:608), which is the membrane's proven shape. The
event graph, made exact (cx r1 finding 5 — the r1 text was internally
contradictory and promised a salience path that does not exist):

1. **Event row set:** `event:moment_missed_<beat_slug>` — `kind` =
   `moment_missed`, `patient` = the staged scene, all stamped
   `valid_from=turn_time(turn)`; PLUS an **explicit event-entity `caused_by`
   ROW** pointing at the arc's fired clock event when one exists (item-level
   `caused_by` metadata is NOT surfaced by `events().caused_by` — the
   explicit-row rule, Cx 117, same as `_fire_event_occurs`).
2. **Consequence rows:** 1-2 concrete world-facts — LAPSE-facts by default,
   occurrence-facts only under an authored `on_expiry` annotation (§2, the
   occurrence rule) — proposed by a cheap-tier cohort
   (`absence_consequence`) from the beat's staging context + present-cast
   spines, constrained to the `known_ids` allowlist, validated like the
   generator preflight (referents must exist), committed via
   `ingest_structured` to canon **with item-level `caused_by` =
   `event:moment_missed_<slug>`** — the situation-lens linkage PB verified
   for the CAST-MOVES departure lever. NEVER a derived notion ("tension
   rose") — only facts a camera at the staged scene could have recorded.
3. **Surfacing, two channels, both real:** (a) re-entry/standing briefings —
   the item-level `caused_by` lights the consequence in
   `snapshot(lens="situation")` while it is served truth; (b) the
   consequence-callback directive — `drift_pass` itself writes the briefing
   directive (newspaper-front-page ruling: minor is fine, FELT is the
   point), surfaced when the player next touches the affected people/places,
   never as an announcement. There is NO reliance on a caused_by reader over
   fact rows — none exists.
4. **`moment_missed` IS routine.** It joins `ROUTINE_EVENT_KINDS` (host
   bookkeeping, the `arc_terminal` reasoning) and is thereby excluded from
   BOTH the first-time-kind and causal-ripple salience signals — the shipped
   exclusions apply to ripple too (generator.py). **The r1 "zero new
   plumbing" generator-feedback claim is RETRACTED:** consequence FACT rows
   never enter `salient_moments` on their own (its fact input is the current
   player-action batch). Generator feedback is INDIRECT and honest: when the
   player later acts on an affected spined NPC, spine-touch qualifies that
   turn. Pinned by test: the moment_missed event wakes nothing by itself.
5. `_FALLOUT`-style phrasing is NOT reused — absence consequences are
   situational, not delta_type-keyed.

### R4 — Alternative-path repair (activating `repair_budget`)

The reserved name becomes a counter, and "incompletable = repair-exhausted"
becomes literally true:

1. **Trigger:** a D-HARD closure of a REQUIRED beat; or a D-MISSED closure
   where `relocate_pick` declined (the mechanic cannot travel).
2. **Repair = a replacement route, authored, not patched.** Beats are frozen;
   statuses are rows. The repair generator proposes a REPLACEMENT beat —
   same phase, same weight, same narrative destination, NEW beat_id and a new
   `achievable_via` grounded in surviving entities — via a `repair_arc`
   cohort in the `generate_arc` mold (known_ids allowlist, compact proposal).
   The existing `lint_post_repair` (lint.py:188 — the §7 novelty check,
   shipped and waiting for exactly this) gates it: the new route must be
   genuinely walkable and not a re-skin of the dead one. Full generator-style
   preflight: referents exist, premise reachable, `lint_arc` on the amended
   arc.
3. **Commit — the append-safe beat-membership model (cx r1 finding 3: the r1
   `repaired_from` row had NO reader; the sealed `beat_index` JSON list is
   what `arc_from_frame` reconstructs beats from, so nothing would have
   changed the arc).** The monotonic-membership shape that fixed the
   portfolio (#111) applied to beats:
   - the replacement beat's items + index rows commit into `plot:` (the
     `arc_to_items`/`index_items` per-beat shapes);
   - one **supersession row** — `arc:<arc_id>` /
     `beat_superseded_<old_beat_slug>` = `<new_beat_id>`,
     `valid_from=turn_time(turn)` — the durable pointer;
   - **`arc_from_frame` reconstruction is EXTENDED** (this is the reader):
     after materializing beats from the sealed `beat_index`, apply
     supersession rows — the old beat leaves the ACTIVE set, the replacement
     (read from its own indexed rows) joins it. The sealed index is never
     rewritten; the closure row stands (append-only).
   - **Every active-set consumer routes through one accessor** —
     `active_beats(arc, reads)` — so `beat_pass`, `_required_unreachable`,
     `climax_ready`/`climax_ready_beats`, and coverage all see the
     replacement identically. Reconstruction is horizon-safe: a
     future-stamped supersession row is invisible at `_h`.
   - **Re-open (the D-MISSED relocate pairing)** is the degenerate case of
     the same model: the closed beat's `status` row is superseded back to
     `pending` (`valid_from`-stamped, latest-wins — the engine's ordinary
     supersession), with the relocation receipt as provenance; no
     replacement beat, no index touch. Restart/reopen reconstruction reads
     the latest status exactly as it reads any status.
   A briefing directive seeds the new route diegetically (sanitized hook).
4. **`repair_budget`:** a per-arc `session:` counter, default
   `REPAIR_BUDGET = 2`, decremented per committed repair (relocations of
   closed beats charge it too — R2 step 5). `_repair_exhausted` becomes:
   *refusal clock fired OR (a required beat is closed AND the budget is
   spent AND no repair is in flight)* — the incompletable rule finally has
   its active half.
5. **Right-of-way:** repair of the MAIN arc's own beat is allowed at peak
   (it serves the peak — same logic as the convergence relocate directive);
   repair of a SIDE arc defers while `main_at_peak` (silent, no receipt —
   the right-of-way contract).

## 4. Where it runs (ordering corrected — cx r1 finding 2)

A `drift_pass` step in `run_turn`, placed **AFTER `beat_pass` (this turn's
closures are known) but BEFORE lifecycle classification, persistence, and
fallout** — for the MAIN arc that means before the `arc_lifecycle` read and
its terminal effects (turnloop.py:3844 onward), and for SIDE arcs before the
side-arc lifecycle/fallout loop (turnloop.py:4011-4029). The r1 "after the
lifecycle passes" placement was wrong: a same-turn closure of a required
beat must get its repair BEFORE `_required_unreachable` can feed a terminal
— otherwise the terminal receipt and fallout escape first and the repair
arrives at a corpse. Directive assembly still follows (directives land this
turn). **Pinned by SEPARATE ordering tests for main and side:** a required
beat closing this turn, repaired this turn, produces NO terminal receipt and
NO fallout. Inputs shared with the adjacent generator step:

1. `drift_state(...)` — pure classifier, no model calls.
2. Right-of-way check (R3/R4-side, per §3 rules).
3. Response selection: the lightest applicable response not already
   receipted; at most one per turn. Order on a D-MISSED beat across turns:
   R3 (consequence) → R2 (relocate+re-open) or R4 (replace).
4. All model-calling steps fail-open: a cohort miss logs, receipts a decline,
   and leaves the world quiet — never breaks the turn.

The development LEDGER (`_mark_development`) gains two update points: a
committed relocation and a committed repair are developments (they must not
read as world-silence to the ambient trigger).

## 5. Telemetry

New TurnTrace fields alongside `lifecycle`/`arc_fallout`/`generated`
(turnloop.py:675-677): `drift` (classified beats + class), `relocations`
(beat_id + new staging), `absence_consequences` (event id + row count),
`repairs` (old→new beat_id). Session receipts: `relocation_receipt`,
`moment_missed`, `repair_attempt`/`repair_declined` (the generator receipt
discipline). All bookkeeping in `plot:`/`session:` — membrane-clean.

## 6. Guards (the standing invariants, restated as binding here)

- **No puppetry:** every response moves the WORLD (a carrier, a consequence,
  a route) — never the player, never the player's protagonist. The R2 carrier
  move is subject to the #80 stagecraft rules where they overlap (never the
  protagonist, never a bound companion as carrier-by-force).
- **Concealment:** no response ever reveals the hidden answer; relocation
  delivers the *moment*; sanitizer on every model-authored surface.
- **Converge the scene, not the verdict:** relocation and repair route to the
  DECISION POINT; they never bias which conclusion the player reaches.
- **Turns are free:** every cadence THIS SPEC INTRODUCES (nudge suppression,
  the D-SOFT quiet gate, missed-moment detection) keys on diegetic time or
  structural closures — never on turn counts. The pre-existing rung ladder
  co-signal is turn-counted (§2, flagged founder item); no new trigger fires
  on it alone.
- **Membrane:** consequences and repairs are concrete world-facts/plot rows
  through the ingestor doorway; `drift_state` output is derived and lives
  only in the trace.
- **Fail-open everywhere;** a quiet world is always an acceptable outcome.

## 7. Phasing (each slice: build → cr review → live test, logged)

- **D1 — Relocate-the-beat** (R2 for D-SOFT high-rung beats only — no
  closures yet) + the `commit_carrier_move` extraction from world-tick +
  the diegetic-quiet drift gate + the R1 nudge tuning + `drift_state` +
  receipts/trace. Oracles: 30 free contemplation turns → NO drift response
  (five in-world minutes); an INVALID carrier move (guard-rejected) → no
  directive, no receipt; a successful move committed BEFORE the briefing
  stages it. Live test: dodge a staged clue-holder, wander to the tavern,
  watch the mechanic arrive.
- **D2 — Absence-consequence** (the closure-witness contract in `beat_pass`
  + the witness-based classifier + the occurrence rule + `moment_missed` +
  consequence commit + callback surfacing). Oracles: a COMPOUND
  `unreachable_if` (clock OR world-state) where the world-state half
  sufficed → D-HARD, not D-MISSED; clock expiry WITHOUT an authored
  `on_expiry` → lapse-facts only, no occurrence claim; the routine
  `moment_missed` event wakes no salience signal by itself. Live test: skip
  the meeting with a deadline clock; find the window closed without you.
- **D3 — Alternative-path repair** (R4 + the beat-membership supersession
  model + `active_beats` accessor + `repair_budget` + the completed
  incompletable rule + D-MISSED re-open pairing). Oracles: same-turn
  close-before-lifecycle repair (main AND side — no terminal receipt, no
  fallout); RESTART reconstruction yields the replacement active set;
  `climax_ready` sees a replacement climax beat; a future-stamped
  supersession row is invisible at `_h`. Live test: burn the ledger a
  required beat needs; watch a new route appear; exhaust the budget; watch
  the arc go incompletable, not zombie.

## 8. Open questions for the mesh (raise only if they bite)

- Whether `relocate_pick`/`absence_consequence` share one cohort schema
  (both are "stage this mechanic HERE" reads) — decide at D1 build time.
- The relocation threshold rung (proposal: the rung immediately below the
  refusal-warning rung) — tune in live test.
- The D-MISSED re-open is now specified as ordinary status supersession
  (§3 R4 — latest-wins, relocation receipt as provenance); PB gets a
  confirmation ask at D3 build time that status-row supersession semantics
  carry no surprises (fold ordering, as-of reads).

Related: LIVING-WORLD-GENERATOR-P2.md (§A one-reader-several-consumers, §B
right-of-way), STORY-SHAPE-AND-RESOLUTION.md (converge the scene),
CONVERGENCE-TO-CONCLUSION.md (Phase-2 items this spec absorbs), CAST-MOVES.md
(#80 — the licensed narration-seam lane; R2 moves ride world-tick instead),
WORLD-TICK.md (#84), the consequence-callbacks + player-avoidance +
proportion + improv-serves-the-destination rulings.
