# Drift Handling — when the player leaves the road (spec)

**Status:** SPEC, for Cx review then phased build (task number TBD on the
founder's board; the headline design item after LWG P2). The founder's captured
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

- **D-SOFT — wandering.** Pending REQUIRED beats exist, and the escalation
  rungs are rising (`navigate(counters, …)` — the shipped idle measure, which
  already respects diegetic time via its counters). The player is engaged
  elsewhere; the road is unwalked, not foreclosed.
- **D-MISSED — the skipped moment.** A REQUIRED beat was closed by a
  TIME-anchored foreclosure: its `unreachable_if` went TRUE via a fired clock
  (`ClockFired` in the closure's `justified_by` — the classifier below). The
  meeting happened; the player was at the pub. Distinct from D-HARD because
  the world-moment *occurred without the player* — there is an absence to
  narrate.
- **D-HARD — foreclosure.** A REQUIRED beat closed by a WORLD-STATE
  foreclosure (its `unreachable_if` went TRUE via a non-clock condition — the
  witness died, the ledger burned). Nothing "happened without" the player;
  the path itself is gone.

**Classifier:** `beat_pass` already writes `status=closed` + `justified_by`.
The drift detector re-reads the closure's justification atoms: any
`ClockFired` present → D-MISSED, else D-HARD. D-SOFT needs no new detection
at all — it IS the shipped rung ladder. A pure reader
`drift_state(pending_required, closures, rung, …) -> list[Drift]` mirrors the
`salient_moments` discipline: explicit inputs, no hidden reads, unit-testable
without a world.

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
   BEFORE the refusal clock is in sight).
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
3. **Move the carrier in CANON, not in prose.** If the original holder
   travels, the host commits the move through the WORLD-TICK doorway (the
   deliberate off-screen mover) *before* the narrator stages the arrival —
   presence truth moves first, so the narrated arrival matches canon and the
   #80 cast-moves lane (or the promote gate) sees no contradiction. The
   narrator gets a briefing directive to stage the arrival diegetically. If
   the delivery re-homes to an already-present carrier, no move is needed —
   only the directive.
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

On D-MISSED, the missed moment becomes TRUE canon — the same doorway
discipline as `emit_fallout` (executor.py:608), which is the membrane's
proven shape:

1. **Event row:** `event:moment_missed_<beat_slug>` (kind `moment_missed`),
   stamped `valid_from=turn_time(turn)`.
2. **Consequence rows:** 1-2 concrete world-facts, `caused_by` the event —
   "the vote landed 4-1", "your seat was noted empty" — proposed by a
   cheap-tier cohort (`absence_consequence`) from the beat's context + the
   scene it was staged in + present-cast spines, constrained to the
   `known_ids` allowlist (the session-zero arc-authoring rule), validated
   like the generator preflight (referents must exist), committed via
   `ingest_structured` to canon. NEVER a derived notion ("tension rose") —
   only facts a camera at the missed scene could have recorded.
3. **Surfacing:** the `caused_by` linkage makes the consequence a live
   thread — the situation lens lights it exactly as PB verified for the
   `departed_scene` lever (CAST-MOVES §4), and it feeds back as generator
   fuel through the causal-ripple signal with zero new plumbing. The
   narrator briefs it as a consequence-callback (the newspaper-front-page
   ruling: minor is fine, FELT is the point) — when the player next touches
   the affected people/places, not as an announcement.
4. **`moment_missed` joins `ROUTINE_EVENT_KINDS`?** NO — deliberately: the
   consequence rows (not the bookkeeping event) are what carry salience, and
   they qualify via causal ripple. The event kind itself IS excluded from the
   first-time-kind signal (it is host bookkeeping, same reasoning as
   `arc_terminal`); pinned by test.
5. `ROUTINE_EVENT_KINDS` gains `"moment_missed"`; `_FALLOUT`-style phrasing
   is NOT reused — absence consequences are situational, not delta_type-keyed.

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
3. **Commit:** the replacement beat's items + indexes into `plot:` (the
   `arc_to_items`/`index_items` path), a `repaired_from=<old_beat_id>` row,
   and the old closure stands (append-only — the closed beat stays closed;
   the ARC's required set now points at the replacement via the repair row).
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

## 4. Where it runs

A `drift_pass` step in `run_turn`, placed AFTER the beat/lifecycle passes
(closures for THIS turn are known) and AFTER the committed-delta/salience
inputs are assembled, BEFORE briefing assembly (directives must land this
turn) — i.e., adjacent to the existing generator step, sharing its inputs:

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
- **Turns are free:** every cadence in this spec (nudge suppression, drift
  thresholds via rungs/clocks) keys on diegetic time or structural closures —
  never on turn counts.
- **Membrane:** consequences and repairs are concrete world-facts/plot rows
  through the ingestor doorway; `drift_state` output is derived and lives
  only in the trace.
- **Fail-open everywhere;** a quiet world is always an acceptable outcome.

## 7. Phasing (each slice: build → Cx review → live test, logged)

- **D1 — Relocate-the-beat** (R2 for D-SOFT high-rung beats only — no
  closures yet) + the R1 nudge tuning + `drift_state` + receipts/trace. The
  lightest, founder-preferred move, live-testable immediately: dodge a
  staged clue-holder, wander to the tavern, watch the mechanic arrive.
- **D2 — Absence-consequence** (D-MISSED classification + `moment_missed` +
  consequence commit + callback surfacing). Live test: skip the meeting
  with a deadline clock; find the vote landed without you.
- **D3 — Alternative-path repair** (R4 + `repair_budget` + the completed
  incompletable rule + D-MISSED re-open pairing). Live test: burn the
  ledger a required beat needs; watch a new route appear; exhaust the
  budget; watch the arc go incompletable, not zombie.

## 8. Open questions for the mesh (raise only if they bite)

- Whether `relocate_pick`/`absence_consequence` share one cohort schema
  (both are "stage this mechanic HERE" reads) — decide at D1 build time.
- The relocation threshold rung (proposal: the rung immediately below the
  refusal-warning rung) — tune in live test.
- Whether a D-MISSED beat's re-open should be a status supersession
  (`status=pending` row re-asserted) or always the R4 replacement path even
  when the mechanic travels — PB may have an opinion on status row
  supersession semantics; ask at D2 if the simple supersession looks wrong.

Related: LIVING-WORLD-GENERATOR-P2.md (§A one-reader-several-consumers, §B
right-of-way), STORY-SHAPE-AND-RESOLUTION.md (converge the scene),
CONVERGENCE-TO-CONCLUSION.md (Phase-2 items this spec absorbs), CAST-MOVES.md
(#80 — the licensed narration-seam lane; R2 moves ride world-tick instead),
WORLD-TICK.md (#84), the consequence-callbacks + player-avoidance +
proportion + improv-serves-the-destination rulings.
