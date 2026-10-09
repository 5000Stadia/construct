# Audit: the arc / destination layer

**Scope:** `construct/arc/` (grammar, truth, conditions, executor, io, generator, drift, lint, adapt), `story_shapes.py`, `cast.py`, `clock.py`, `gauge.py`, `laws.py`, `growth.py`, `reshape.py`, `tangent.py`, `resolve.py`, `resolution.py`, `hostcontrol.py`. That is about 8,000 lines.
**Method:** I read every file in scope in full, and grepped the callers in `turnloop.py` (7,969 lines), `game.py` (2,949), `session.py` and `cohorts.py`. I made no edits to the repo. The 499 tests that cover these modules all pass (`tests/test_{cast,clock,drift,gauge,generator,growth,hostcontrol,laws,portfolio,reshape,resolution,resolve,story_shapes,tangent}.py`, 200 s).

**Verdict in one paragraph.** The core ideas are still the right ones and are cleanly expressed at the bottom of the stack: three-valued `Truth`, frozen atom dataclasses, one `evaluate`, the arc as host-owned `plot:` rows, coverage-as-effect, and the pre-rolled deck. `truth.py`, `grammar.py`, `lint.py`, `resolution.py` and `hostcontrol.py` are small and good. The pathology is the one the July audit named: accretion. Since July it has grown in new directions rather than shrinking:
- **Arc lifecycle operations are implemented more than once.** The "is it over?" question has five overlapping predicates. The main-arc swap is written three times (two of them non-atomic). Arc construction lives as a private function in `game.py` and is cloned for refusal clocks and preflight.
- **The three-valued walker is re-implemented.** `drift.py` re-implements it three more times.
- **Serialization is hand-written several ways.** Each arc type has two or three hand-written codecs, and booleans are stored three different ways.
- **The vocabulary is stringly typed.** Statuses, lifecycles, lanes, dispositions and drift classes are bare strings.
- **The tokenizer/slug clone farm is worse than in July.**
- **Several July dead fields are still there.** New ones have joined them.

Most of the fixes below are mechanical and suite-gated.

---

## Suspected bugs (verify first)

Each entry carries a confidence label:
- **CONFIRMED:** read directly from the code path.
- **PLAUSIBLE:** follows from the code, but I did not reproduce it live.

1. **Main-arc swap can tear the portfolio manifest. (CONFIRMED window, PLAUSIBLE impact)**
   - **Where:** `arc/io.py:696-704` (`replan_main_arc`, called from `turnloop.py:5932`) and its inline clone in `game.py:2764-2769` (`continue_episode`).
   - **What happens:** both retract the visible `arc:portfolio` rows and then append the replacement as separate porcelain calls.
   - **Failure:** if the append raises, or the process dies, after the retracts, the manifest is gone. `main_arc_from_frame` (`io.py:752`) and `arc_ids_from_frame` (`io.py:722`) then fail open to `"arc:main"`, so a reopened world silently runs the *original* arc. That is the exact EP2 stale-arc symptom `hostcontrol.py` was written to catch.
   - **The third copy is already safe:** `tangent.adoption_ops`/`activate_adoption` (`tangent.py:417-542`) does the same swap atomically through `commit_set`. See F3.

2. **Reshape event id collides across turns. (CONFIRMED)**
   - **Where:** `reshape.py:208`, `event_id = f"event:reshaped_{plan.slug}"`, with no turn component. The slug defaults to `f"{e}_{a}"` (`reshape.py:131`).
   - **Failure:** a second reshape of the same target (revive, dies again, revive) writes its `kind` and `caused_by` rows onto the first event's entity. Consequences then chain to a merged event.
   - **Contrast:** every other host event id in the layer carries `_{turn}`.

3. **Pacing counters mix two bases across episodes. (PLAUSIBLE)**
   - **Where:** `executor.py:125-133`. `turns_elapsed = len(all turn events)` counts every episode, because `game.next_turn_number` is global. `last_mark_turn` only counts marks at or above `current_epoch()`. The epoch is raised for episode 2 (`game.py:2600`, `session.py:246-259`).
   - **Failure:** at the start of episode N+1, `turns_quiet` equals the whole prior play's turn count until the first beat or arc-touch. That means:
     - the new arc's `TurnsQuiet(4+2i)` escalation clocks (`game.py:2259-2266`) can fire on its first tick;
     - `navigate()` and `drift.rung_from_counters` start at CONFRONT.
   - **Fix:** count `turns` with `at >= epoch` too, so both terms share a base.

4. **Host bookkeeping events wake the opportunistic generator. (PLAUSIBLE)**
   - **Where:** `clock_pass` writes a canon `kind=clock_fired` event, plus effects such as `kind=pressure` (`executor.py:168-170`, `game.py:2262`). `_turn_salience` reads canon window events *after* `clock_pass` (`turnloop.py:5257` vs `5989`). `ROUTINE_EVENT_KINDS` (`generator.py:69-86`) lists neither `clock_fired` nor `pressure`.
   - **Failure:** the first escalation-clock firing produces "a new kind of event occurred this turn: 'clock_fired'". So P2b, which is specified as *player-caused*, wakes on the host's own pacing timer.

5. **A falsy-zero default makes frame-load and cache-load arcs disagree. (CONFIRMED, low impact)**
   - **Where:** `io.py:314` (`costly_band ... or 0.25`) and `io.py:330` (`severity ... or 1.0`).
   - **Failure:** an authored `0.0` becomes the default on the frame path, but survives on the cache path (`io.py:629`, `Pin(**p)`). The same world yields different arcs depending on which loader ran.

6. **`adapt.apply_adaptation` red-herring lane: the debunker is validated, then discarded. (CONFIRMED, latent)**
   - **Where:** `adapt.py:110-124`. The red-herring fact is written into `knows:<protagonist>`, but `debunker_fact` is never written or recorded. The module docstring says a red herring is "REQUIRING a reachable debunker".
   - **Why latent:** the only caller (`turnloop.py:5679`) passes `lane="genuine"`. See F1.

7. **Lexical substring matches. (latent)**
   - **Where:** `gauge.gauge_delta_for` (`gauge.py:178-180`) matches `kw in action`, so a "rest" modifier fires on "forest"/"arrest"/"interest". `clock._TEMPORAL_MARKERS` (`clock.py:248-275`) has the same flaw ("rest", "nap"⊂"snap", "doze"⊂"bulldozer").
   - **Impact today:** for the clock, these only force an unneeded model estimate, which costs latency. For the gauge it would mean a wrong drain, but no production builder authors `action_modifiers` today. See F11.

---

## July 2026 audit: status of findings that touch this part

| July finding | Status | Evidence |
|---|---|---|
| Booleans serialized as strings, absence defaults TRUE (`required`, `terminal_on_floor`) | **OPEN** | `io.py:245`, `289-290` still write `"true"/"false"`; `io.py:313`, `526` read `(... or "true") != "false"`. A third encoding has appeared: `escalates` = `"yes"`/absent (`io.py:266-268`), and `generated` = `"yes"` (`generator.py:394`). The cache path stores real bools. |
| Expr JSON has no version marker | **OPEN** | `io.expr_to_obj`/`expr_from_obj` (`io.py:68-101`): no `v`. An unknown `op` raises `KeyError` inside `_ATOM_TYPES[op]`. |
| Dropped beats stay in `beat_index` (dangling refs) | **OPEN** | `io.py:421-435` still logs and skips a beat with no `achievable_via`. There is no reconciliation against `climax_ready_beats` (`io.py:507`), so a dropped climax beat makes `climax_ready` and `world_condition` silently unreachable. Only the per-beat error log exists. |
| Dead fields: `phase_budget`, `refusal_variant_id`, `rearm="repeat"` | **OPEN, and the case is now provable** | `phase_budget` is read only by lint check 6, which needs `session_length_turns`. No caller passes it (`game.py:691`, `768`; `generator.py:415`; `tangent.py:288`). It is still hard-coded in `game.py:2282` and persisted. `refusal_variant_id`: written (`game.py:2253`, `io.py:138`, `548`), never read. `rearm`: no producer of `"repeat"`; the only reader is `executor.py:177`. |
| `_FALLOUT` keyed on free-string `delta_type` with a silent default | **OPEN (mitigated)** | Both cohort schemas enum it (`cohorts.py:2012`, `game.py:90`), so a bad value is unlikely. But the vocabulary now lives in three places (two schemas plus the `_FALLOUT` keys), and the default is still silent (`executor.py:718`). `delta_type_from_coverage` (`executor.py:419`), meant to *derive* it, has zero callers. |
| Three `_state_value` clones; the clock variant lacks `as_of` (horizon bug) | **PARTLY FIXED** | `hostcontrol.collapse_state` centralizes the collapse policy for clock, foyer, adapter and game. But `gauge._state_value` (`gauge.py:101-108`) still re-implements the collapse and bypasses it. `clock._state_value` (`clock.py:166-171`) still has **no `as_of`**, so `read_clock` and `governing_calendar` read at head, not at the play horizon. |
| Three tokenizers → unify | **WORSE** | In or next to this part: `executor.concealed_tokens`/`value_leaks` (`executor.py:795-817`), `cast._identity_tokens` (`cast.py:407`), `resolve._is_place_like`/`is_voice`/`_mention_text`, `clock.deterministic_elapsed`'s replace-split (`clock.py:277`), `turnloop._words` (imported by resolve), and `turnloop._secret_word_set`, `play_styles._tokens`, `game._toks`. Plus **seven** slug helpers (`laws._slug`, `reshape._slug`, `growth._slugify`, `generator._id_slug`, `game._slug`, `remembrancer._slug`, `imagery._slug`). |
| Movement decision table in `resolve.py` (`resolve_move → Bound/InScene/...`) | **OPEN** | There is no move resolver in `resolve.py` (`grep resolve_move` finds nothing). Worse, resolve's core matcher lives in `turnloop._names_entity` and is lazily imported twice (`resolve.py:206`, `445`). See F10. |

---

## Findings, ranked by value per unit of effort

### F1. Delete the dead and speculative surface (S · polish for code; proposal for stopping persisted writes)
**Evidence:**
- **Never read, or behind a dead branch:**
  - `Arc.phase_budget` plus lint check 6 (`grammar.py:207`, `lint.py:136-143`, `game.py:2282`).
  - `ConclusionShape.refusal_variant_id` (`grammar.py:129`, `io.py:138`, `548`).
  - `Clock.rearm` and its `"repeat"` branch (`executor.py:177`).
- **Zero production callers:**
  - `executor.COVERAGE` (`:297`)
  - `executor.delta_type_from_coverage` (`:419`)
  - `cast.is_solvable` (`:339`, docstring ref only)
  - `drift.on_expiry_items` (`:450`). Nothing in production authors the on_expiry note, so the D2 "occurrence rule" can only ever take the lapse branch outside tests.
  - `growth.atomic_capable` (`:60`)
  - `io.portfolio_add_items` (`:673`), a pass-through with an unused `reads` parameter.
  - `story_shapes.TYPE_SHAPE` (empty).
- **`adapt.py` lanes nobody calls:** `red_herring`, `plot_supersede` and `decline` (`adapt.py:93-115`); the only caller passes `"genuine"`. `red_herring` is the latent hole in bug #6.
- **Duplicates:** `generator.LIFECYCLE_TERMINALS` duplicates `executor.LIFECYCLE_TERMINALS`. `drift.rung_from_counters` duplicates the body of `executor.navigate` minus its first line.
- **Unused parameter:** `_mint_side_arc(side_arcs=...)` is never used (`generator.py:450`).

**Why it matters:** every dead field is a wire-format obligation and a reader's question. `phase_budget` budgets in *turns*, which contradicts the founder's "turns are free" ruling.

**Fix:**
- Delete the unused code paths. Make `navigate` call `rung_from_counters`. Collapse adapt to the genuine lane, or implement the debunker write.
- Stopping the *writes* of `phase_budget`, `refusal_variant` and `rearm` rows changes the plot-frame format. Readers already tolerate absence, but per the rules this half is a **proposal**.

### F2. Move arc construction into the arc layer (`arc/build.py`) (M · polish)
**Evidence:**
- `generator.py:479` and `tangent.py:318` both import the *private* `game._build_arc` (`game.py:2220`, inside a 2,949-line module). The generator has to defer the import to dodge a cycle.
- `io._synth_refusal` (`io.py:339-355`) says in its own docstring that it "mirrors `game._build_arc`"; it is a clone of `game.py:2274-2280`.
- The arc preflight is cloned: `generator._preflight` (`generator.py:402-425`) and `tangent._tangent_arc_problems` (`tangent.py:240-293`). Both check grounded protagonist and tension entity, run `lint_arc`, and treat `2-paths` as advisory.

**Why it matters:** the arc grammar's constructor lives outside the arc package. Three modules now hold separate copies of "what a valid arc is".

**Fix:** create `arc/build.py` with three functions, and point `game.py`, `generator.py`, `tangent.py` and `io.py` at them:
- `build_arc(proposal, arc_id)`
- `refusal_clock_for(arc_id)`
- `preflight(arc, reads, *, protagonist=None) -> list[str]`

This is a pure move, and the existing tests cover it.

### F3. One atomic main-arc swap (M · proposal, because it changes the porcelain call)
**Evidence:** bug #1. There are three swaps: `io.replan_main_arc` (non-atomic), `game.continue_episode` (`game.py:2751-2773`, non-atomic, an inline clone), and `tangent.adoption_ops` (atomic `commit_set`, with verified `PortfolioState` (`tangent.py:330-414`)). ATOMIC-ACTIVATION-V1 has been live since 2026-07-24 (`growth.py` header).

**Fix:** add `swap_main_arc(p, reads, new_arc, *, extra_ops=(), turn)` in `arc/io.py` (or `arc/portfolio.py`):
- build ops exactly as `adoption_ops` does: retract both verified control rows, then assert the arc rows, the index and the manifest;
- commit with `commit_set`;
- have all three call sites use it.

This closes bug #1 structurally and deletes the retract-then-append prose that is now repeated in three docstrings.

### F4. One annotated evaluator instead of four three-valued walkers (M · polish)
**Evidence:** `conditions.evaluate` (`:283-365`) is the canonical walk, built on `truth.t_all/t_any/t_at_least/t_not`. `drift.py` then re-implements the AllOf/AnyOf/AtLeast/Not truth tables three more times, inline, without using `truth.py`:
- `_true_leaves` (`drift.py:247-300`)
- `_evaluate_clocks_false` (`:303-336`)
- `_driving_entities` (`:339-379`)

`_driving_entities` also calls `evaluate(op)` on each operand at every level, which makes it quadratic in depth. And `closure_witness_of` walks the same expression three times against the same reads.

**Why it matters:** the D2 witness exists to record exactly what `evaluate` decided, but it re-derives that from four independent copies of the truth table. Every future atom or connective has to be added in four places, and any divergence is silent.

**Fix:**
- Add `explain(expr, reads, counters=None, *, leaf=None) -> Node(expr, verdict, children)` in `conditions.py`, built on `truth.t_*`.
- `evaluate(...) = explain(...).verdict`.
- The witness leaves, the driving entities and the clock-necessity probe become folds over one `Node` tree; the probe is `explain(expr, reads, leaf=lambda a: FALSE if ClockFired else None)`.
- Keep the witness JSON byte-identical; `test_drift.py` pins it.

### F5. Derive arc status once per tick (`ArcStatus`) (M · polish; unifying `failure_when` semantics is a proposal)
**Evidence:** "is this arc done?" has seven entry points in `executor.py`:
- `arc_concluded` (`:258`)
- `arc_outcome` (`:272`)
- `arc_lifecycle` (`:679`)
- `current_phase` (`:490`)
- `climax_ready` (`:476`)
- `conclusive_eligible` (`:520`)
- `_required_unreachable` (`:630`)

They disagree: `arc_concluded` ignores `failure_when`, while `arc_outcome` honors it. The turn loop patches `concluded` by terminal owner (`turnloop.py:6160-6169`). `current_phase` calls `arc_concluded`, `climax_ready` and `active_beats`; `conclusive_eligible` then calls `current_phase`, `climax_ready` and `_required_unreachable` again. Each `active_beats` call walks supersession chains with fresh reads, and each walk can call `io.beat_from_reads`, about six reads per hop.

**Fix:** add `arc_status(reads, arc) -> ArcStatus(outcome, lifecycle, phase, climax_ready, foreclosed, refusal_fired, active_beats)`. It is a frozen dataclass computed once per arc per tick, derived and never stored (membrane-clean). The existing functions become one-line accessors, which keeps the public API. Deciding whether `concluded` should include `failure_when` uniformly is a semantic call for the founder.

### F6. Split `executor.py` into what it actually holds (M · polish)
**Evidence:** `executor.py` (842 lines) holds seven unrelated things:
- **Timeline/epoch:** `TURN_EPOCH`, `SOURCE_STEP`, `horizon_metadata`, a contextvar and `compute_entry_epoch` (`:30-111`). This is consumed by `game.py` and everything that calls `turn_time`.
- **The tick passes.**
- **Terminal predicates.**
- **Coverage → outcome mapping:** `conclusion_from_coverage`, `OUTCOME_SHAPES`.
- **Fallout.**
- **The concealment/leak screen:** `concealed_tokens`, `value_leaks` (`:789-817`). It is used by session and remembrancer, and has nothing to do with execution.
- **A liveness predicate:** `person_can_act` (`:604-627`), used four times by turnloop for NPC eligibility. It does regex word matching over role/state strings.

Two layering problems sit alongside:
- **The evaluator imports the serializer:** `conditions.resolve_superseded_beat` (`conditions.py:247-280`) imports `arc.io` to call `beat_from_reads`, so the pure evaluator depends on serialization.
- **Private reach-in:** `executor.arc_entities` imports lint's private `_entity_referents` (`executor.py:824`).

**Fix:**
- Split the file into `arc/timeline.py`, `arc/conclusion.py`, `arc/concealment.py` and `arc/supersession.py`, the last holding `resolve_superseded_beat`, `active_beats` and `beat_from_reads`' strict reader.
- Make `entity_referents` public.
- Re-export from `executor` for compatibility.
- Also extract the duplicated "collect every arc expression" loop that `arc_protected_keys` and `arc_entities` both carry (`:767-781` and `:827-837`) into one `arc_exprs(arc, reads)`.

### F7. Make the state vocabularies types, not strings (M · polish, `StrEnum` keeps the wire format byte-identical)
**Evidence:** the state vocabularies are bare strings:
- **Beat status:** `"pending"/"achieved"/"closed"` (`executor.py:199`, `228`, `334`). Literals compared inline in at least five places.
- **Clock status:** `"armed"/"fired"`.
- **Lifecycle:** a tuple duplicated in two modules (`executor.py:26`, `generator.py:65`).
- **Drift class:** `"D-SOFT"/"D-HARD"/"D-MISSED"` (`drift.py:110`, `429-445`).
- **Coverage:** `"genuine"/"false"/"unfilled"`.
- **Outcome shapes; `cost_disposition`; `terminal_owner`; `delta_type`.**
- **Adapt lanes:** including synthesized result lanes such as `"rejected_unknown_lane"`.
- **Cast fields:** `Clue.coverage_effect`, `reveal_condition`, `CastNode.presence`.

`cast_from_proposal` validates `presence` and `pronouns`, but not `coverage_effect` or `reveal_condition` (`cast.py:488-496`). A model-supplied `"Pressure"` silently never reveals.

**Fix:** use `enum.StrEnum` (Python 3.11) for each vocabulary, and validate at the parse boundary (`cast_from_proposal`, `arc_from_frame`). Serialized values are unchanged.

### F8. Move the generator's trigger chain into the generator (M · polish)
**Evidence:**
- **The pacing guard runs in two places:** inside `generate_from_fallout` (`generator.py:520`), but in the turn loop for the opportunistic and ambient triggers (`turnloop.py:6567`, `6577`).
- **The turn loop imports private helpers:** `_pacing_ok`, `_last_development_min` and `_mark_development` (`turnloop.py:68`, `6574`, `6593`).
- **`main_protagonist` arrives two ways:** inside the untyped `ctx` dict for one trigger (`generator.py:534`) and as a parameter for the other two.
- **Coarse arc ids:** a generated arc gets `arc:gen_{turn}`, which is safe today only because the `GenerativeSlot` allows one mint per turn.

**Fix:**
- Add `generator.maybe_generate(world, reads, provider, *, fallouts, moments, spined, mode, minutes_now, slot, ctx: GenContext) -> Minted | None`. It owns right-of-way, then the fallout, opportunistic and ambient priority, then pacing, then `_mark_development`.
- `GenContext` is a small frozen dataclass.
- About 70 lines leave `turnloop.py`.

### F9. Consolidate `story_shapes.py` into one record per shape (S–M · polish for data; **proposal** for the prompt dedup)
**Evidence:**
- **Five parallel dicts keyed by the same shape strings:** `SHAPES`, `_SHAPE_LINE`, `SHAPE_CONCLUSION`, `SHAPE_SIGNATURE` and (indirectly) `FAMILY_SHAPE`. A typo in one silently drops behavior for that shape.
- **Dead fields:** `medium`, `withheld_kind`, `commitment_kind` and `payoff_kind` are never read outside the module, nor are `SHAPE_CONCLUSION["trigger"|"clock"|"has_literal_result"]`.
- **A mis-wired argument:** the shape's `commitment_kind` exists but is ignored, while `turnloop.py:6222` passes `judgment_type` into `commitment_stage_gate(..., commitment_kind)`. The name lies at the call site.
- **Prompt duplication, against the elegance tenet:** `shape_directive` emits `_SHAPE_LINE[s]` plus the narrator-channel signature elements, and these restate the same discipline almost word for word:
  - deduction: "reveal it ONLY when the player has assembled enough — never hand it over" (`:103`) vs `the_earned_reveal` (`:175`);
  - endurance: "never grant easy relief or safety" (`:107`) vs `mounting_threat` (`:198`);
  - mastery: "never granted" (`:116`) vs `:242`;
  - farce: "don't resolve it early" (`:118`) vs `:256`;
  - transformation: "PROVEN by action, never merely declared" (`:120`) vs `:270`;
  - contest: "never gifted" (`:110`) vs `:210`;
  - discovery: "never front-loaded" (`:114`) vs `:230`.

  So every shape tells the narrator its core rule twice. The bond `the_grounded_interior` element (`:188-194`, about 70 words) is an incident fix (room granularity) dressed as a genre signature.
- **Private reach-in:** the module imports `play_styles._norm`.

**Fix:**
- Add a `@dataclass(frozen=True) class Shape(name, line, conclusion: ShapeConclusion, signature: tuple[Element, ...])` with one `SHAPES: dict[str, Shape]`.
- Drop the dead fields, and wire `commitment_kind` properly or rename the parameter.
- Prompt dedup: keep `_SHAPE_LINE` as the one-line discipline, and drop the narrator-channel signature elements that restate it. This changes model input, so it needs a live fiction check; **proposal**.

### F10. Move the Entity Authority matcher home, and build the move table (S polish + L proposal)
**Evidence:**
- **The identity matcher lives in the turn loop:** `resolve._match_one` (`resolve.py:202-228`) and `resolve.bind_or_mint` (`:435-462`) both lazily import `turnloop._names_entity` (`turnloop.py:884-916`, with `_words`, `_NAME_NOISE`, `_ROLE_NOUNS`, `_ROLE_SYNONYMS`). So "the ONE coreference seam" depends on a 7,969-line module for its core identity test.
- **The match loop is cloned:** iterate, kind-filter, dedupe, count unique/ambiguous/none. The two copies use *different* kind-filter rules, and that difference is deliberate but undocumented at the second site.
- **Decision reasons are free strings** with two mapping dicts (`_SUBJECT_OUTCOME`, `_VALUE_OUTCOME`), and `resolve_rows` returns both legacy receipt triples and `ResolutionOutcome` records.

**Fix:**
- **Polish, S:** move `_names_entity` and its tables into `resolve.py`, and factor `_unique_match(mention, candidates, name_of, kind_ok)`.
- **Proposal, L:** the July P1 movement decision table, `resolve_move(dest, ctx) -> Bound|InScene|Blocked|Undiscovered|Mint|Deny`.

### F11. One text helper module: `slug()`, `words()`, `has_word()` (S–M · polish; switching substring matches to whole-word is a behavior change and a proposal)
**Evidence:** listed in the July table above (seven slug helpers, six or more tokenizers). Bug #7 is the concrete hazard.

**Fix:** add `construct/text.py`, and replace the clones whose output is identical. Where clones differ (character classes, length floors), document the difference as a parameter rather than a copy.

### F12. Serialization: one codec per type, plus explicit bools and a version (M · polish for the codec; **proposal** for the format)
**Evidence:**
- **Beats are deserialized three ways** (`io.beat_from_reads` strict at `:191-231`, the `arc_from_frame` loop lenient at `:421-445`, and the cache at `:606-611`), and every other type two ways (frame and cache).
- **Adding a field means about six edits:** grammar, `*_to_items`, `*_from_reads`, `arc_to_cache`, `arc_from_cache`, and sometimes `index_items`.
- **The paths already diverge:** bug #5 (falsy zero), and three boolean encodings. `_JSON_BLOB_ATTRS` (`io.py:30-36`) is a hand-maintained allow-list that must track every blob attribute, or the identity reconciler drops the row (its own comment records the beat loss this caused).
- **A stray comment:** the portfolio comment at `io.py:38-42` is attached to `logger =`.

**Fix:**
- Per-dataclass field specs (name, kind: `scalar|bool|expr|json|enum`) drive the frame rows, the strict and lenient readers, the cache dict, and `_JSON_BLOB_ATTRS`.
- If the generated rows and cache are byte-identical (golden test), this is polish.
- Writing bools explicitly, logging absence on read, and adding `{"v":1}` to Expr JSON with a tolerant reader closes the July P2 items. These change the world-file format: **proposal**.

### F13. Host-control rows ride the engine's durability classifier (proposal → PB request)
**Evidence:**
- **Mutable arc and session attributes go through the durability classifier:** `semantics.ARC_STRUCTURAL_ENUMS` (`semantics.py:46-50`) deliberately excludes mutable attributes (`status`, `phase`, `lifecycle`, `cursor`, `last_nudge_min`, ...). That classifier has already been a source of silent loss ("an EVENT verdict ERASES the row", PB 066).
- **The constitutive-fold trap forced workarounds:** "a constitutive fold serves the EARLIEST visible row" (`io.py:644-649`, Cx 167) forced the retract-then-append idiom (F3) and the whole `hostcontrol.py` conflicted-read telemetry.

**Why it matters:** `plot:`/`session:` state is host control data with clear last-write-wins semantics. Every new host-control attribute is exposed to model classification and the constitutive trap until someone notices.

**Fix:** do not work around this locally; the design law says engine gaps go to PB. Send a PB request for a frame-level declaration ("host-control frame: model-free, functional, recency-folded") or an attribute-family declaration. Then retire the retract-then-append workarounds.

### F14. Docstrings carry review history, not invariants; several are now false (M · polish)
**Evidence:**
- **Review history:** about 205 review/incident citations ("Cx 304 #3", "cr round-4 blocker 1", "PB 072 §5", "#98") across about 8,000 lines. Many docstrings narrate how a rule was argued rather than stating it, for example `io.beat_from_reads` (`:191-204`) and `tangent.may_confirm` (`:207-219`).
- **Stale statements:**
  - `conclusive_eligible` still documents "the post-climax window expiring is itself a candidate" (`executor.py:525-526`), which was removed (`:513`).
  - `beat_pass` logs "repair is post-v1" (`:224`), but D3 repair ships.
  - `drift.py`'s module docstring says "R4 … is D3's — goes no further here" (`:20-21`), but D3 lives in the same file (`:581-670`).
  - `Drift.cls` says D-MISSED/D-HARD are "reserved for D2" (`:110`), but D2 ships them as bare strings.
  - `pending_callbacks(reads, ...)` actually takes a *world* (`drift.py:502`, `509`; caller `turnloop.py:7351`).
- **Naming:** doc-section codes stand in for names in places (`R1..R4`, `P2a/b/c`, `G-A piece B`).

**Fix:** rewrite each public docstring as *invariant + why* in two to four lines, and leave the archaeology to git and `docs/design`. Fix the stale claims and rename the misnamed parameter.

### F15. Tangent: adversarial self-validation and id-grammar parsing (S–M · proposal)
**Evidence:**
- **Id-grammar parsing:** `read_pending` recovers the adoption turn by parsing the event id (`tangent.py:192-195`, `int(ev.event_id.rsplit("_",1)[-1])`), the id-grammar parse the project's own MOVED-EVENT doctrine forbids. The adoption set should carry a `turn` attribute.
- **Hardening against the host's own callers:** the module defends against forged or subclassed host values. `type(pending) is not Pending` blocks "subclass impersonation" (`:220-224`). `adoption_ops` re-runs the lint and re-reads the portfolio that its caller just verified (`:443-460`). `PortfolioState.__post_init__` is about 40 lines (`:330-374`).

**Why it matters:** this is reviewer ratchet. Each check was individually argued, but together they make a pure state machine read like a security boundary, and the threat (host code forging host values in one process) is not real.

**Fix:**
- Polish: write and read a `turn` attribute instead of parsing the id.
- Proposal: relax the exact-type and self-re-verification checks. The reviewer mandated them, so the founder decides.

---

## Also noted (small)
- **Broad excepts that hide defects:**
  - `drift.repair_spent` catches everything, including `AttributeError` from a reads object without `frame_rows`, and returns `on_error` (`drift.py:630`). The incompletable rule then sees 0 forever.
  - `clock._calendar_from`: `except Exception: pass` on a malformed calendar blob (`clock.py:194`).
  - `executor._cancelled` falls through silently (`:674`).

  Narrow these to the expected exception types, or at least log them.
- **A canon-truth question:** `clock_pass` writes a canon `event:<clock>_fired_<turn>` row (`executor.py:168-170`), and escalation clocks write canon `kind=pressure` events with no participants (`game.py:2262`). That is plot bookkeeping in canon, written because N turns passed quietly. It bears on truth-keeping and on "turns are free". Worth the founder's eye, together with bug #4.
- **`reshape.canonicalize_plan`** runs `world.refer` on *every* row value, including literals such as `"true"`/`"fading"` (`reshape.py:172-182`). If `refer` matches loosely, a literal could be rewritten into an entity id. Gate it on `resolve._entity_valued(row)`. (PLAUSIBLE.)
- **`reshape_canon`** commits canon rows and then each frame row in separate ingests (`:225-237`). Its docstring's "never partially write" is true only of validation. It is a natural fit for `commit_set` (proposal, with F3).
- **`laws`:** law objects are bare dicts that pass through lint and two renderers (about nine keys), and they are stored twice: `meta["laws"]` for runtime reads plus canon `law:*` rows. `law_rows` drops `embodiment` and `changed_consequence`, so canon is not the full truth that `laws_from_meta` says it is. A frozen `Law` dataclass would help.
- **`cast`:** the "genuine, not red herring, live-reachable" predicate is written four times (`cast.py:132-133`, `140-142`, `225-226`, plus `floor_clues` `:521-522`). Make it a `Clue.is_genuine_live` property. `is_red_herring` plus `coverage_effect=="false"` double-encodes "strong red herring", and contradictory combinations are representable.
- **Good modules to leave alone:** `truth.py`, `grammar.py` (apart from the dead fields), `lint.py`, `resolution.py`, `hostcontrol.py`, and `growth.GenerativeSlot`.
