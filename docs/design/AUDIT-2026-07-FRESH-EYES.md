# Fresh-Eyes Design Audit — 2026-07-01

**Commissioned by the founder** on the model change: "identify the intention of the design
elements, determine the effectiveness of the shape, and where ineffective identify the
improvement." Evidence gathered by five parallel read-agents over the full `construct/` tree
(~14,000 LoC surveyed); the judgments below are mine (HD, Opus), measured against the founder's
standing tenets — agent-prompt-elegance, unveil-don't-script, improv-serves-the-destination,
map-governs, the membrane (derived is never stored).

## Verdict in one paragraph

The architecture is **conceptually sound and unusually principled** — the five-verb porcelain
boundary, three-valued truth, host-side arc layer, Entity Authority, and the membrane discipline
are all *right* and worth keeping exactly as intended. The dominant pathology is not design error
but **accretion**: ~40 live incidents were each fixed correctly *in the small* (with Cx review),
and the sum is rule-stacking the founder's own elegance tenet warns against — a 2,242-line
`run_turn`, 10 sequential movement guards, 40 conditional briefing blocks, three tokenizers,
three `_state_value` clones, three chunkers, and a prompt budget squeezed to 99.6%. The system
now needs the *consolidation pass* its incident-driven history never had room for. Second-order
finding: several defensive layers exist only because trust in a component was never revisited
after the component was fixed (band-aids outliving their wounds — the verified-then-strip rule
applied half-way).

## Element-by-element

### 1. The turn pipeline (`turnloop.run_turn`) — intention right, shape strained
**Intention:** one serial mutation spine, then assembly fan-out, then render, then post-audit.
Correct — turns must be atomic and auditable.
**Shape:** 2,242 lines, 15 phases inline, 53 broad try/excepts, movement alone stacked with 10
sequential guards that mutate shared `status`/`target` state. Each guard is individually
justified (each has a Cx letter); together they are a decision *sediment*, not a decision
*structure*. The zero-candidate mint path just produced the phantom-scene incident precisely
because bind-authority logic is spread across guards rather than being one resolver step.
**Improvement (high value, staged):**
- Extract each phase into a named function with an explicit contract (`classify_phase`,
  `movement_phase`, …) — no behavior change, pure mechanical extraction, testable in isolation.
- Collapse the movement guards into ONE ordered decision table in `resolve.py` (the Entity
  Authority home): `resolve_move(dest, ctx) -> Bound|InScene|Blocked|Undiscovered|Mint|Deny`.
  The semantic destination bind (task #78 A) already points this direction; finish the shape.
- Unify the three tokenizers (`_words`, `_secret_word_set`, inline splits) into one.

### 2. The prompt surface (`cohorts.py`) — the best-disciplined file, with three real debts
**Intention:** every model call in one place, task-tagged, tiered, schema-enforced. Effective —
this file is the project's cleanest idea and mostly its cleanest execution.
**Debts:**
- **The 4,500-char budget is full (4,484).** The elegance guard works, but it now *prevents*
  improvements rather than shaping them. The right fix is not raising the number: RENDER_LEASH
  and RENDER_STYLE contain overlapping instructions (second-person voice stated 3×; briefing-is-
  truth stated 2×). A single consolidation edit should recover 15-20% headroom.
- **Dead classify fields** (`uses_protagonist_knowledge` is consumed; but `asserts_or_reveals`
  default-true handling and `reshape_attempt` deserve a consumption audit) — every unconsumed
  schema field is model effort spent on nothing, every turn.
- **`open_scene` stacks all directives unconditionally** while `narrate` earned conditional
  injection. Apply the same conditional discipline to the open (no cast present → no
  WORLD_IS_PEOPLED).

### 3. The arc layer (`arc/*`) — the intellectual core; sound, with quiet hazards
**Intention:** the project's contribution — destination/beats/clocks/pillars as host-side data
over engine truth, three-valued evaluation, coverage-as-effect. **This is the right design.**
**Hazards found (none currently misfiring, all latent):**
- **Booleans serialized as strings** with absence-defaults-TRUE (`required`, `terminal_on_floor`)
  — an intentional FALSE is indistinguishable from a missing row. Fix at write (store explicit
  always) + read (log on absence).
- **Expr JSON has no version marker** — adding an atom type breaks old worlds silently. One
  `"v": 1` field and a tolerant reader closes it.
- **Dropped beats stay in `beat_index`** (fail-open reconstruction leaves dangling references) —
  a dropped REQUIRED beat silently forecloses an arc. The load path should reconcile index vs
  loaded set and surface the delta loudly.
- **Dead fields:** `phase_budget` (persisted, never read), `refusal_variant_id`, the
  `rearm="repeat"` branch. Delete or document as reserved.
- **`_FALLOUT` keyed on free-string delta_type** with a silent default — validate at Arc
  construction.

### 4. Session/build lifecycle (`session/game/foyer`) — right split, duplicated bookkeeping
**Intention:** pristine scenario + per-player slot; session-zero stages; foyer as agent-with-
tools. All correct.
**Improvements:**
- **meta.json vs slot double-bookkeeping** (entry_epoch, arc_scope both places with asymmetric
  read-preference) — document the precedence in ONE place and funnel reads through one accessor.
- `_finalize_scenario` (520 lines) and `_opening_narration` (149) deserve the same phase
  extraction as run_turn.
- Foyer's magic tool-name strings → an enum shared with the cohort schema.

### 5. Support modules — the clone farm
- **Three `_state_value` implementations** (foyer canonical, clock lacking `as_of`, gauge with) —
  one shared helper in `adapter.py`; the clock variant's missing `as_of` is a live horizon bug
  waiting for a horizon world with a calendar.
- **Three chunkers** (transport_core/telegram/discord, subtly different) — one exported `chunk()`.
- **Discord bypasses TransportCore entirely** — no invite gate, no scenario scope lock; two scope
  bypasses flagged. Either route Discord through TransportCore or explicitly deprecate the
  Discord path (Telegram is the live transport).
- **imagery.py re-implements Codex auth/SSE** already owned by provider.py — extract the shared
  client.
- **Config sprawl:** four env-var prefixes, no startup validation — one config module.

### 6. The render directives — where the founder's tenets live
The GROUND-THE-PLAYER / UNVEIL-INTELLIGENTLY / presence-truth work of the last week is the
correct *pattern* for this whole layer: state engine truth + one principle, delete scripts.
Remaining scripts to re-examine under the same lens: the fixture head-noun block-list
(`_FIXTURE_HEADS` — lexical guessing where the semantic destination bind could now rule), the
hardcoded deterministic-time verb map, and the momentum heuristic in weave (magic `<=2` turns).

## Priority order (my recommendation)
1. **P0 — consolidation with zero behavior change** (mechanical, low-risk, immediately compounding):
   shared `_state_value` + tokenizer + chunker; delete dead schema fields/grammar fields; phase
   extraction of run_turn. Full suite is the safety net (659 tests).
2. **P1 — the movement decision table** in resolve.py (finishes Entity Authority's shape; the
   phantom-scene class dies structurally rather than guard-by-guard).
3. **P2 — serialization hardening** (bool-as-string, expr versioning, index reconciliation) —
   quiet, but these are the bugs that will someday eat a live world.
4. **P3 — prompt-surface consolidation** (LEASH/STYLE dedup for headroom; conditional open).
5. **P4 — transport unification** (Discord through TransportCore or retirement; config module).

Regression-risky items (P1, P3) go spec-first with Cx review per the house method; P0 can proceed
as mechanical batches, suite-gated.

## What I would NOT change
The porcelain five-verb boundary; three-valued truth; the membrane; coverage-as-effect;
conclusion-bounce; the pre-rolled resolution deck; task-tagging; the fail-open-per-frame build
discipline; the ledger two-store split. These are better than what I would have designed from
scratch, and several (the deck, the membrane) are genuinely elegant.
