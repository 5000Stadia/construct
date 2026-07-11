# Drift Handling — when the player leaves the road (spec)

**Status:** **GREEN r4 (cr `<4e9e05ea…>`, 2026-07-11, commit 25a85dc) —
phased build AUTHORIZED.** Review chain: cx r1 RED folded in r2
(`<d645fd14…>`); cr r2 RED folded in r3 (`<13680dcb…>`); cr r3 RED folded
in r4 (`<9f215bcb…>`: runtime consumer sweep + Session-scope refresh,
additive `beat_to_items`/`beat_from_reads`, literal-typed callback
`affected`, BeatAchieved `part_of` arc context, deterministic
`ClockFired(n)` causal firing). cr phasing ruling: **D1 independent, may
start** (serialized behind the #80 turnloop landing — one integration
owner); D2 spec-ready; slice cadence kept (build → cr review → live test
per slice); D3 code review checks the consumer sweep call-site-by-call-site.
The founder's captured
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
needs does not exist yet and is built in D2; precision per cr r2 point 5):**
today `beat_pass` (executor.py:201-209) writes only `status=closed`;
`justified_by` is written on ACHIEVEMENT only and holds only `{turn}`. D2
adds: on closing a beat, `beat_pass` also writes a **closure witness** row
(`plot:` frame, `beat:<id>` / `closure_witness`,
`valid_from=turn_time(turn)` — horizon-safe) recording the EVALUATED
witness of the closing evaluation:
- the set of leaf atoms of `unreachable_if` that evaluated TRUE, with kinds
  and ids — atom *presence* in the expression is never proof;
- **for each TRUE `ClockFired` leaf, the exact causal clock-firing EVENT id
  captured at evaluation time** (not just the atom's clock id) — so
  `moment_missed.caused_by` can never select the wrong firing of a
  repeated/multiple clock. For `ClockFired(n)` (threshold shapes), the
  causal firing is DEFINED as the horizon-visible event that made the
  threshold true, ordered by event time then id — never an arbitrary
  matching event (cr r3 point 4);
- per-shape semantics, pinned by unit test: `AnyOf` records the TRUE
  branch leaves; `AllOf` records all leaves; `AtLeast(n)` records the
  satisfied leaves; `Not` records the negated subtree's evaluation;
  UNKNOWN/INDETERMINATE atoms are recorded as UNKNOWN — **absence from the
  true-leaf set means evaluated-not-TRUE (FALSE or UNKNOWN), and any
  UNKNOWN on the deciding path drops the classification to D-HARD** (the
  conservative default).
The authored `on_expiry` occurrence annotation has an exact home: a
`plot:` row `clock:<clock_id>` / `on_expiry` (the CLOCK is the expiry
carrier — never "beat or clock"), written by the session-zero/authoring
path; readers are the D-MISSED classifier and the `absence_consequence`
cohort.

**Classifier (conservative, witness-based):** D-MISSED iff the witness
proves the closure CLOCK-CAUSED — at least one `ClockFired` leaf evaluated
TRUE, AND the expression with all clock leaves forced FALSE evaluates
not-TRUE (the clock was NECESSARY, not incidental to a mixed condition).
**The necessity verdict is computed AT CLOSE TIME against the same reads
that closed the beat and CAPTURED in the witness** — later classification
is a pure witness read and never re-evaluates a moved world (cr-confirmed
as the horizon-coherent reading). Anything else — no witness (pre-contract closures), mixed
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
   `read_clock(world).minutes` the ambient trigger uses. **Two constants,
   deliberately distinct (cr r2 oracle gap 7):** `NUDGE_QUIET_MIN` bounds
   R1's own cadence (default 60.0 — at most one nudge per in-world hour);
   `RELOCATE_QUIET_MIN` (default 240.0) gates the R2/R3/R4 drift responses.
   The 30-contemplation-turns oracle (five in-world minutes) asserts
   PRECISELY: zero R2/R3/R4 responses AND R1 fires at most once across the
   sequence — distinguishing turn-count leakage from allowed R1 behavior.
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
   surface with an EXPLICIT policy (cx r1 finding 6; policy split per cr r2
   blocker 4 — world-tick hard-requires destination != current scene while
   R2 exists to move a carrier INTO it; one undifferentiated signature
   conflates incompatible rules).** `_world_tick` is a whole autonomous
   cohort policy — never called to force a selected relocation. D1 extracts
   TWO layers:
   - `validate_carrier_move(reads, person, dest, policy)` — the COMMON
     guards (never the protagonist, never a bound companion, never an id in
     `policy.anchored` — the anchored set is a required policy input, not
     an implied read; destination binds and folds to place as-of `_h`) plus
     the POLICY destination rule: `mode="world_tick"` REQUIRES
     `dest != current_scene`; `mode="relocate"` REQUIRES
     `dest == current_scene`. The policy object carries `mode`, `scene`,
     `protagonist`, `companions`, `anchored`, `horizon`.
   - `commit_carrier_move(world, person, dest, turn, policy)` — validate,
     then the canon `in`-row commit, then **receipt CONFIRMATION under the
     `confirmed_batch` discipline: the move is confirmed only when its
     exact entity/attribute key appears in the ingest receipt — never
     merely because `ingest_structured` returned** (fail-open ingest turns
     a failed commit into an empty receipt).
   Both callers consume the same two layers; world-tick's low-level move is
   refactored onto them. R2 calls commit BEFORE the narrator stages the
   arrival — presence truth moves first, so the narrated arrival matches
   canon and the #80 lane (or the promote gate) sees no contradiction. An
   INVALID or UNCONFIRMED move (guard-rejected, failed, or structurally
   skipped) produces NO briefing directive and NO relocation receipt — the
   response declines whole. Tests: the same person/destination ACCEPTED
   under `relocate` and REJECTED under `world_tick`; anchored rejection;
   companion rejection; future-horizon destination rejection;
   failed/skipped commit → no directive, no receipt. If the delivery
   re-homes to an already-present carrier, no move is needed — only the
   directive.
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
2. **Consequence rows AND the callback directive — HOST-CONSTRUCTED
   closed predicates (cr D2 review, twice: a schema label is model
   self-classification, and free callback prose is the same bypass in a
   player-facing channel — the boundary must be structural in BOTH).** The
   `absence_consequence` cohort's whole authority is WHO (1-2 subjects
   from exactly the staged cast + present NPCs, protagonist excluded — a
   place, proposition, or delivery target is never a "who") and a
   confidence. The HOST writes everything: per subject a closed lapse
   predicate (`noted_absence` = "the appointed moment at <staged place>
   passed unmet (turn N)"); ONLY under an authored `on_expiry` annotation
   (§2) additionally exactly one occurrence row — the authored note
   VERBATIM (`missed_moment_outcome` on the staged scene), appended so a
   licensed note never displaces a subject's predicate (≤3 rows total);
   and the deferred callback DIRECTIVE, host-built from the same closed
   predicate (+ the verbatim note when licensed, else an explicit
   never-assert-what-happened clause). Model text can reach neither canon
   nor the briefing. Committed via `ingest_structured` to canon **with
   item-level `caused_by` = `event:moment_missed_<slug>`** — the
   situation-lens linkage PB verified for the CAST-MOVES departure lever.
3. **Surfacing, two channels, both real:** (a) re-entry/standing briefings —
   the item-level `caused_by` lights the consequence in
   `snapshot(lens="situation")` while it is served truth; (b) the
   consequence-callback, now a **durable pending/consumed contract** (cr r2
   blocker 3 — a transient `drift_pass` return survives neither restart nor
   delay, and a bare event encodes no target matching or once-only rule):
   `drift_pass` persists a callback row set in `session:` —
   `callback:moment_missed_<slug>` with `affected` (JSON id list: the
   staged scene + its cast, **pinned `value_type="literal"`** — cr r3
   blocker 3: untyped JSON is identity-classified/reconciled by arc IO and
   can be silently dropped at scale, leaving status/directive alive but the
   target match gone; the read side is an all-or-empty validated parse),
   `directive` (sanitized), `status=pending`, `caused_by` = the
   moment_missed event, `valid_from=turn_time(turn)`.
   Briefing assembly scans PENDING callbacks each turn (horizon-safe
   `frame_facts` read as-of `_h`); when the current scene or present cast
   intersects `affected`, the directive surfaces THAT turn
   (newspaper-front-page ruling: minor is fine, FELT is the point — never
   an announcement) and `status` is superseded to `surfaced` — once-only by
   construction. Tests: delayed touch AFTER restart surfaces exactly once —
   through the REAL ingestor and read adapter, not a fake fold (cr r3);
   unrelated scenes stay silent; a surfaced callback never re-fires. There
   is NO reliance on a caused_by reader over fact rows — none exists.
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
2. **Repair = the HOST RE-MINTS the dead beat's own mechanic (cr D3 code
   round, blockers 2+4 — supersedes the earlier model-authored-replacement
   shape).** Beats are frozen; statuses are rows. The route died, never the
   destination: the replacement beat carries the dead beat's `achievable_via`
   VERBATIM — same phase, same weight, fresh `_rN` beat_id — with the
   foreclosure trigger stripped (`unreachable_if=None`, so a still-true
   trigger cannot re-close it next `beat_pass`). No model authors, relabels,
   or repoints any part of the condition; the `repair_arc` cohort's whole
   authority is the HOOK (one diegetic line for how the new road opens) plus
   a confidence — its schema has no condition fields at all (the same
   structural-authority discipline as R3's subjects-only schema). The
   same-destination invariant is therefore enforced by construction, and
   `lint_post_repair` (lint.py:188 — the §7 novelty check) still gates the
   re-mint: where the surviving mechanic's referents died with the world's
   turn, the repair declines honestly and the budget survives toward
   `incompletable` — a genuinely-new-route authoring pass is deliberately
   NOT attempted (it would reopen the model-authored-condition surface).
   **WALKABILITY (cr re-review blocker 2):** an InFrame delivery beat
   re-mints ONLY when a live delivery channel exists — some cast member
   holds the clue (the authorized delivery write travels through carriers;
   the route IS the carrier, so a surviving holder is a genuine alternative
   road even when the dead trigger named another). No holder →
   `no_delivery_channel` decline; the refusal clock is the designed
   backstop for a story that cannot move — an unwalkable re-mint would be
   an IMMORTAL PENDING beat no machinery could ever close, so it is never
   minted. `Occurred` beats stay walkable by the player act itself.
   **THE TRIGGER RULE:** a CLOSED beat's re-mint strips `unreachable_if`
   (the trigger fired; copying a still-true trigger re-closes instantly); a
   PENDING beat escalated from repeated D-SOFT keeps its trigger — the
   deadline is live and stays honest — and its fresh id re-arms the
   one-relocation-per-beat allowance (which IS the escalation's material
   change: a new staging chance behind a narrated new road).
3. **Commit — the append-safe beat-membership model (cx r1 finding 3; made
   a COMPLETE graph-membership contract per cr r2 blockers 1-2).** The
   monotonic-membership shape that fixed the portfolio (#111) applied to
   beats:
   - the replacement beat commits via a NEW additive per-beat pair (cr r3
     blocker 2 — today `arc_to_items(arc)` emits the WHOLE arc and
     `index_items(arc)` REWRITES the whole `beat_index`; no per-beat
     serializer exists, so citing them contradicted the never-rewrite
     rule): `beat_to_items(replacement, arc_id)` emits ONLY the new beat's
     rows into `plot:`, and `beat_from_reads(reads, beat_id)` materializes
     a `Beat` from them. The supersession row's target id is the DISCOVERY
     pointer; the sealed `beat_index` is never written. `active_beats`
     materializes replacements through `beat_from_reads` on BOTH load paths
     (frame reconstruction and legacy `arc_cache`), including same-turn
     use. Pinned: committing a replacement re-emits NO unrelated
     beat/status/index rows;
   - one **supersession row** — `arc:<arc_id>` /
     `beat_superseded_<old_beat_slug>` = `<new_beat_id>`,
     `valid_from=turn_time(turn)` — the durable pointer. The sealed
     `beat_index` is never rewritten; the closure row stands (append-only).
   - **ONE canonical supersession resolver** (cr blocker 1 — returning the
     replacement from a membership accessor alone cannot redirect
     structural references): `resolve_beat_id(reads, arc_id, beat_id,
     as_of=_h)` follows supersession rows to the terminal id. Chain:
     old→new1→new2 follows to new2. Cycle: stop at the first repeated id,
     log loudly, treat as unsuperseded (fail-safe). Collision: one
     attribute key per old beat, so a re-asserted row supersedes by
     `valid_from` — the engine's ordinary latest-wins. EVERY structural
     reference resolves through it:
     * `active_beats(arc, reads)` — membership (beat_pass,
       `_required_unreachable`, coverage);
     * `climax_ready`/`climax_ready_beats` — the sealed id TUPLE is
       resolved element-wise at read time (the tuple itself is never
       rewritten);
     * **`BeatAchieved` evaluation** — the condition evaluator resolves the
       referenced id before reading status, so a downstream
       `achievable_via=BeatAchieved(old)` observes the replacement. **Arc
       context (cr r3 point 4):** `BeatAchieved` carries no arc_id and
       `evaluate()` has no arc context — the evaluator derives the arc from
       the referenced beat's persisted `part_of` row (a defined lookup, not
       an ad-hoc global scan), threaded via the resolver parameter.
   - **The FULL runtime consumer sweep (cr r3 blocker 1 — the three
     enumerated consumers were not enough; direct `arc.beats` reads exist
     across the host).** D3 classifies EVERY `arc.beats` reader and routes
     the RUNTIME ones through `active_beats`/the resolver:
     * runtime, must resolve: `current_phase` (reads-aware),
       `arc_protected_keys`, `arc_entities`, the turnloop pin-progress
       read, `_world_tick` protected expressions, generator preflight,
       Session concealment/scope assembly, the remembrancer's beat reads,
       cast delivery-target assembly (`beat_delivery_targets`);
     * authoring-only (sealed reads stay): build/seal-time serialization
       and lint over the authored arc.
     **Live `Session` scope refreshes after a committed repair** (shape
     settled in the cr re-review, blocker 5): the Session tracks its
     beat-DERIVED scope subset separately; on a repaired turn it subtracts
     that subset, adds the live beat set (at the play horizon), and keeps
     independently-played scope untouched — so replacement-only referents
     ENTER and superseded-only referents LEAVE persistent scope, while an
     entity the story put in play through scenes/canon stays visible.
     Within the repairing turn itself, protection/concealment surfaces are
     already live (every reader threads reads), and the re-mint carries
     the dead beat's own condition, so the in-turn render needs no scope
     mutation; the refresh lands before the next turn assembles. Oracles:
     replacement-only referents become scoped AND protected;
     superseded-only (beat-only) referents stop driving phase, protection,
     and scope; shape-derived referents remain.
   - **Cache/restart coherence (cr blocker 2):** supersessions are NEVER
     baked into an `Arc` object — the sealed arc stays immutable and the
     overlay is READS-BACKED at the resolver/accessor layer. That makes the
     legacy `open_playthrough` `arc_cache` path coherent by construction
     (a cached sealed Arc + the reads-backed resolver see the same
     replacement a frame-reconstructed one does), and it is also how the
     LIVE in-memory Arc sees a same-turn replacement: `drift_pass` writes
     the row; every subsequent consumer this turn already reads through the
     resolver. The restart oracle exercises BOTH load paths (frame
     reconstruction and legacy meta `arc_cache`). Horizon-safe: a
     future-stamped supersession row is invisible at `_h`.
   - **Re-open (the D-MISSED relocate pairing)** is the SAME re-mint (cr D3
     code round, blocker 2 — a bare status-flip back to `pending` dies at
     the very next `beat_pass`, because the fired clock's `unreachable_if`
     is still TRUE): the mechanic-travels case commits the identical
     replacement shape (same condition, trigger stripped, `_rN` id,
     supersession row), silently — no hook directive; the ordinary D-SOFT
     relocation machinery re-stages it on later turns. `mode="reopen"` in
     the receipt is telemetry, not a second commit path.
   A briefing directive seeds the new route diegetically (sanitized hook).
4. **`repair_budget`:** default `REPAIR_BUDGET = 2` per arc, and the spend
   truth is THE PERSISTED REPAIR GRAPH ITSELF (cr re-review blocker 1 — a
   batch plus a complete-receipt check is not a transaction; rows can land
   partially, so any separate charge artifact can tear from the repair it
   charges): a repair is spent iff its supersession pointer has a
   MATERIALIZABLE replacement (`beat_from_reads` succeeds). An orphan
   replacement beat without its pointer is harmless and free; a pointer
   without a materializable replacement is a torn commit — retryable,
   free; an ACTIVE supersession can never be free. Latest-wins per pointer
   key, restart-safe by construction; `_rN` ids probe past any stranded
   orphan beat so a torn batch can never collide a retry. `repair_spent`
   carries a caller-chosen error bias: the budget GATE fails closed (an
   unreadable ledger grants no free repairs) while the incompletable rule
   fails open (a read glitch never flips an arc terminal). The
   `repair_committed` session event is telemetry only. `_repair_exhausted`
   becomes: *refusal clock fired OR the graph count reaches the budget* —
   the incompletable rule finally has its active half.
5. **Right-of-way:** repair of the MAIN arc's own beat is allowed at peak
   (it serves the peak — same logic as the convergence relocate directive);
   repair of a SIDE arc defers while `main_at_peak` OR while the turn's one
   drift response is already spent (silent, no receipt — the right-of-way
   contract). **Deferred means DEFERRED (cr re-review blocker 4):** a side
   arc whose drift pass was skipped for peak/quota while it still holds a
   RESCUABLE closure (a closed REQUIRED beat, budget remaining, refusal
   NOT fired) has its lifecycle/fallout transition HELD that same turn —
   silently — so the skip can never race the closure to a terminal the
   deferred repair would have prevented. A win is never held; a
   refusal-fired side arc is never held (the verdict doctrine — its
   conclusion proceeds); a pass that RAN and declined releases the hold
   (the decline was the honest attempt).

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
turn). **Pinned by SEPARATE ordering tests for main and side — and the
behavioral test alone is insufficient (cr r2 oracle gap 6: with budget
remaining, neither order necessarily emits a terminal, so a passing
behavior test proves nothing about order). D3 adds an explicit CALL-ORDER
oracle:** a spy over `drift_pass` / `arc_lifecycle` / `emit_fallout`
asserting invocation order within `run_turn`, for main and side separately,
alongside the behavioral no-terminal-no-fallout test. Inputs shared with
the adjacent generator step:

1. `drift_state(...)` — pure classifier, no model calls.
2. Right-of-way check (R3/R4-side, per §3 rules).
3. Response selection: the lightest applicable response not already
   receipted; at most one per turn (across the WHOLE portfolio — main
   drift responding forecloses side responses that turn). Order on a
   D-MISSED beat across turns: R3 (consequence) → R2 (relocate+re-open)
   or R4 (replace).
3b. **The developing-turn refinement + THE VERDICT DOCTRINE (cr D3 code
   rounds 1-2):** the development suppression (D1 finding 2) defers
   PRESSURE, never the closure ledger — closures of REQUIRED beats always
   classify. What defers on a developing turn: the R3 consequence SCENE
   (it lands as its own quiet-turn beat), the repair of an unreceipted
   D-MISSED (consequence-first), and all D-SOFT pressure. The
   closure/lifecycle race is closed by construction, not by rescue: a
   refusal-UNFIRED closure with budget remaining can never terminalize
   (`incompletable` requires repair-exhausted). And once an arc's OWN
   refusal clock HAS fired, the story is concluding — `arc_outcome` reads
   "lost" on a fired refusal REGARDLESS of any repair, so a rescue could
   only spend budget to relabel one terminal as another. Repair therefore
   steps aside on a fired refusal (`refusal_concluded` decline at the
   gate; the drift loop skips the attempt): the verdict outranks repair,
   for main and side arcs alike.
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
  closures yet) + the `validate_carrier_move`/`commit_carrier_move`
  extraction with the explicit policy object + the diegetic-quiet drift
  gate + the R1 nudge tuning (two distinct constants) + `drift_state` +
  receipts/trace. Oracles: 30 free contemplation turns → zero R2/R3/R4 and
  AT MOST ONE R1 nudge; the same person/destination ACCEPTED under
  `mode="relocate"` and REJECTED under `mode="world_tick"`; anchored /
  companion / future-horizon-destination rejections; an INVALID or
  UNCONFIRMED move (guard-rejected, failed, structurally skipped) → no
  directive, no receipt; a successful move receipt-CONFIRMED before the
  briefing stages it. Live test: dodge a staged clue-holder, wander to the
  tavern, watch the mechanic arrive.
- **D2 — Absence-consequence** (the closure-witness contract in `beat_pass`
  + the witness-based classifier + the occurrence rule + `moment_missed` +
  consequence commit + the durable callback contract). Oracles: a COMPOUND
  `unreachable_if` (clock OR world-state) where the world-state half
  sufficed → D-HARD, not D-MISSED; per-shape witness pins (`AnyOf`,
  `AllOf`, `AtLeast`, `Not`, UNKNOWN atoms → D-HARD on the deciding path);
  the witness carries the exact clock-firing EVENT id (repeated-clock
  disambiguation); clock expiry WITHOUT an authored `clock:<id>/on_expiry`
  row → lapse-facts only, no occurrence claim; the routine `moment_missed`
  event wakes no salience signal by itself; the callback: delayed touch
  AFTER restart surfaces exactly once, unrelated scenes silent, no
  re-fire after `surfaced`. Live test: skip the meeting with a deadline
  clock; find the window closed without you.
- **D3 — Alternative-path repair** (R4 + the supersession RESOLVER +
  `active_beats` accessor + `repair_budget` + the completed incompletable
  rule + D-MISSED re-open pairing). Oracles: same-turn
  close-before-lifecycle repair (main AND side) — the CALL-ORDER spy over
  `drift_pass`/`arc_lifecycle`/`emit_fallout` PLUS the behavioral
  no-terminal-no-fallout test; RESTART reconstruction yields the
  replacement active set on BOTH load paths (frame reconstruction AND
  legacy meta `arc_cache`); `climax_ready` sees a replacement climax beat
  through the resolved id tuple; a downstream beat whose `achievable_via`
  is `BeatAchieved(old)` fires when the REPLACEMENT achieves; supersession
  chain follows to terminal, cycle fails safe; a future-stamped
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
