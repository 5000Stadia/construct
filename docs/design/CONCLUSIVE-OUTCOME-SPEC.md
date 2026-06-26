# SPEC — Conclusive Outcomes + Story Terminal State + Play Contracts (v1, unblocked slice)

**Status:** SPEC for review (Cx + founder), per the greenlit pipeline (design bounce ✓
→ **spec w/review** → implement w/review). Covers the THREE PB-unblocked components of
EPISODIC-CONTINUATION §14: **(1) Conclusive Outcome Core, (2) Story Terminal State
Machine, (5) Play-Contract Plumbing.** Components 3–4 (transition delta-ingest, episode
authoring) are held pending PB letter 078 (A–F). Component 6 (Sandbox) sequences after
LWG P2.

Design source: [[EPISODIC-CONTINUATION]]. Seams: `construct/turnloop.py`,
`construct/arc/executor.py`, `construct/session.py`, `construct/cohorts.py`,
`construct/registry.py`, `construct/transport_core.py`.

---

## 0. What changes, in one paragraph
Today: `scenario_mode ∈ {win_loss, endless, bounded}`; `arc_outcome` returns a **binary**
`won|lost`; `win_loss` writes a SESSION terminal receipt the first turn an outcome holds;
`endless` "settles" via `arc_concluded`. After this spec: the player picks a **contract**
(`story | sandbox`); a **Conclusive Outcome Core** decides *when* a Story has reached its
narratively-earned final page (a two-gate judgment, conservative) and *what shape* the
ending takes (a spectrum, not win/lose); a **Story Terminal State Machine** moves the
playthrough `active → concluded_pending_choice → finished | continuing` and drives the
"next episode or stop?" gate. Sandbox runs no `arc:main`.

---

## Component 1 — Conclusive Outcome Core

### 1.1 The two-gate conclusive-moment detector (Cx fix)
Replaces "is `arc_outcome` non-None → terminate". New `executor.conclusive_check(reads,
arc, *, contract, turn, post_climax_turns) -> ConclusiveVerdict`:

**Gate A — deterministic eligibility (cheap, no model).** Returns "not yet" unless ALL:
- `contract == "story"` (Sandbox never concludes; §C);
- arc phase ∈ {CRISIS, CLIMAX, FALLING} **or** a refusal/foreclosure path is live;
- minimum arc progress: `climax_ready` satisfied (reuses `Arc.climax_ready_k/beats`) OR a
  required beat is foreclosed (`_required_unreachable`) OR refusal clock fired;
- a **candidate conclusive event** exists this scene: a just-achieved climax beat, a fired
  refusal/deadline clock, or a foreclosure. (Reuses the trace lists `run_turn` already
  collects: achieved/closed/fired.)

Only if Gate A passes do we spend Gate B.

**Gate B — LLM final-page judge** (`cohorts.judge_final_page`, MAIN tier, tag `fpg`).
Inputs: the arc's `ConclusionShape` (premise/tension/delta), the candidate event, the
**Ledger** director's-brief ([[narrative-memory-ledger]]), the SCENE NOW digest, and the
last N turns. Output schema:
```
{ "is_final_page": bool,          # is THIS the concluding frame? bias toward false
  "why": str,                     # one line (debug/trace only)
  "outcome_shape": str,           # see 1.2 — only meaningful if is_final_page
  "outcome_gloss": str }          # one-line shaped summary for the epilogue seed
```
The judge is prompted **conservative**: "default `is_final_page=false` unless the central
tension is decisively resolved or foreclosed and continuing would be anticlimax." 

**Post-climax adjudication window — RETIRED (founder ruling 2026-06-25 / Cx 173-178).** Turns
NEVER force a close: a no-deadline story stays climax-ready indefinitely until the player
COMMITS. The old `K_POSTCLIMAX` turn-count window (which would force a `quiet_failure` after K
quiet post-climax turns) is gone — it was a mechanic on top of the narrative, exactly what the
founder rejects. Readiness still surfaces the **"THE RECKONING IS AT HAND" narrator nudge** every
ready turn (the narrator escalates the invitation to conclude), but it is a nudge, never a
countdown. A story concludes only on the narrative's DECISIVE event — a player commitment, an
AUTHORED diegetic deadline/loss (`failure_when` = `Quantity` over `time:elapsed.elapsed_minutes`,
or a loss event), or explicit abandonment. See `diegetic-time-is-the-only-clock` (memory).

### 1.2 Outcome shape (retire the binary)
`outcome_shape ∈` a small controlled vocabulary (host enum, not engine — Cx Q-S1):
`triumph | costly_victory | bittersweet | partial | failure | quiet_failure`
plus a free `outcome_gloss`. (`pyrrhic` collapsed into `costly_victory` — overlapping
labels destabilize the judge.) The arc's `win-state` and `failure_when` **inform** the shape
(they are evidence the judge weighs) but no longer **gate** a boolean. Stored as the
terminal receipt's attributes (§1.3), never as a `won/lost` flag.

### 1.3 Terminal receipt + epilogue (epilogue mints no canon — Cx fix)
On `is_final_page`:
1. Write ONE SESSION receipt event `event:conclusion_<turn>` with attributes
   `{kind: "conclusion", outcome_shape, outcome_gloss}` (replaces `arc_outcome_<turn>`
   `won/lost`). `terminal_outcome(reads)` is generalized to return the shape (or None).
2. **Any durable consequence** the ending implies (the culprit escaped, the heirloom is
   ash) is committed via the existing fallout/`emit_fallout` ingest path (canon rows,
   `caused_by=event:conclusion_<turn>`) — NOT narrated into existence.
3. The **epilogue** (`cohorts.narrate_epilogue`, MAIN, tag `epi`) renders the concluding
   frame from **committed facts only** + the shape/gloss + Ledger. It is prose over canon,
   authored after the consequence ingest, so it never invents durable state.

### 1.4 Files / tests (C1)
- `arc/executor.py`: `conclusive_check`, `ConclusiveVerdict`, `OUTCOME_SHAPES`; generalize
  `arc_outcome` callers (keep `arc_lifecycle` for side-arc fallout untouched).
- `cohorts.py`: `judge_final_page` (`fpg`), `narrate_epilogue` (`epi`) + schemas.
- `turnloop.py`: call `conclusive_check` in place of the `win_loss && outcome` branch
  (turnloop.py:608–625); thread `post_climax_turns`; `TurnTrace.conclusive` (shape) +
  `TurnTrace.post_climax_turns`.
- Tests: eligibility gate rejects a lull (Gate A false on a SETUP-phase turn); judge
  false-positive guard (canned "not yet" → no receipt); post-climax window fires repair
  after K; shaped receipt written with `outcome_shape`; epilogue prompt receives only
  committed facts (assert no ingest of new entities from epilogue path).

---

## Component 2 — Story Terminal State Machine

### 2.1 States (host-side, on `session:main`)
`active → concluded_pending_choice → finished | continuing`
- **active** — normal play.
- **concluded_pending_choice** — set the turn `conclusive_check` fires; the epilogue is
  rendered; the player is asked **"Start the next episode, or are we good?"** (§5 gate of
  the design). `Reply.ended` stays False here — the world isn't torn down; we await the
  answer (mirrors the `_pending_exit`/`_pending_restart` in-memory confirm pattern, but
  persisted on `session:main` so it survives a process bounce).
- **finished** — player said "we're good": graceful close; resumable as a finished series;
  `Reply.ended = True`.
- **continuing** — player said "next": hand off to episode-authoring (component 4, gated)
  + checkpoint. Until C4 lands, "continuing" returns a friendly "the next episode is
  coming soon" stub (feature-flagged) so C2 is testable/shippable independently.

### 2.2 Transport wiring
- A persisted `session:main` row `playthrough.stage` (one of the four). `terminal_outcome`
  / `Session.turn` read it: `concluded_pending_choice` → emit epilogue + the choice prompt,
  do NOT keep ticking the arc; `finished` → the existing ended-aftermath behavior.
- New in-memory `transport_core._pending_episode: set[str]` for the choice answer
  (`_affirmative` / "next" → continuing; "good"/"stop" → finished), same shape as
  `_pending_restart`.
- `/restart "episode"` already restores the episode-start checkpoint (shipped) — it
  composes: a finished/continuing playthrough can still roll back.

### 2.3 Files / tests (C2)
- `session.py`: read/advance `playthrough.stage`; generalize `ended` to `stage==finished`.
- `turnloop.py`: set `concluded_pending_choice` on conclusive turn.
- `transport_core.py`: `_pending_episode`, the choice prompt + handler; "continuing" stub.
- `registry.py`: none (stage lives in PB `session:main`, not the registry).
- Tests: conclusion turn → stage `concluded_pending_choice` + choice prompt, `ended False`;
  "good" → `finished` + `ended True`; "next" → `continuing` + checkpoint called + stub
  reply; re-entry after a process bounce re-reads the persisted stage.

---

## Component 5 — Play-Contract Plumbing

### 5.1 The contract value
- Registry `mode` column generalizes to carry the **contract**: values `story | sandbox`
  (legacy `win_loss → story`, `endless → sandbox`, `bounded → story`; migrate in
  `registry.connect`’s idempotent block — a one-shot `UPDATE` mapping old values).
- `Session._scenario_mode` → `_contract`; `_endless` derives `contract == "sandbox"`.
  Keep `mode_override` threading; `Session.aim()` shows the aim only in `story`.

### 5.2 Per-card `default_style` (Q9 = A)
- `play_styles_data.STYLE_CARDS` gains a `default_style: "story"|"sandbox"` per card;
  populated by `scripts/build_play_styles.py` from a new column/annotation in
  `docs/design/GAME-TYPE-TAXONOMY.md` (default `story` when unspecified — most cards).
  Sandbox-leaning cards (slice-of-life, world-sim, sandbox, cozy, tycoon, walking-sim…)
  tagged `sandbox`.
- `play_styles.default_contract(game_types) -> "story"|"sandbox"`: if ANY chosen card is
  `story` → `story` wins (a goal present dominates); all-sandbox → `sandbox`. Mixed worlds
  with any goal-bearing type default to a story.

### 5.3 The explicit ask (founder: ask straight up; genre leads)
- Architect/Atrium gains a `set_play_contract` action (ARCHITECT_SCHEMA), parallel to
  `set_game_type`. After the world is chosen/built and BEFORE the Foyer, the Construct asks
  the appetite question, **led by the genre default**: e.g. *"This one plays naturally as a
  case to crack — want a story with a real ending, or would you rather just explore, no
  pressure?"* Default pre-filled from `default_contract`; the player's natural answer is
  read by `cohorts` into `story|sandbox` (reuse/extend `interpret_mode`).
- Persist via `registry.set_mode` (now the contract). Replaces the win_loss/endless mode
  interview at that seam ([[STARTUP-ENTRY]], [[mode-interview-and-feedback]]).

### 5.4a Full reader inventory (self-verified 2026-06-20 — every site the contract touches)
The contract is NOT just the registry column; `win_loss|endless|bounded` is threaded
through five modules. Migration-safe approach: keep the **internal** `scenario_mode`
lineage working (`story` maps onto the `win_loss` path, `sandbox` onto `endless`), and make
the **player/registry-facing** value the contract. Sites to touch/verify:
- `architect.py:38,50,54,80,143` — `ArchitectState.mode` ("win_loss"|"endless") + `to_brief`
  `"mode"`/`win_direction`. Add `contract`; map mode→contract or carry both.
- `transport_core.py:814` (`endless=brief.get("mode")!="win_loss"`), `:947` sandbox synonyms,
  `:958` `_MODES`, `:970–978` `interpret_mode`. Generalize `interpret_mode` → contract.
- `session.py:75–76` (`_scenario_mode`/`_endless`), `:224` `aim` gate, `:384` turn gate,
  `:392–393` run_turn kwargs. `_contract`; `_endless ⟺ contract=="sandbox"`.
- `turnloop.py:274` `scenario_mode` param, `:334` briefing line, `:612` `terminal` gate.
  Replaced by the conclusive-check (C1) for `story`; `sandbox` never concludes.
- `game.py:429` `meta["scenario_mode"]="endless" if endless else "win_loss"`, `:434` `endless`
  flag, `:437`+ win_loss aim authoring. Author `contract` into meta; keep `scenario_mode`
  derived for back-comp.
**Implication:** C5 is wider than "a registry column" — it's a threaded rename with a
back-compat shim. Lands cleanly but must hit all five modules in one slice.

### 5.4 Files / tests (C5)
- `registry.py`: migration mapping old mode values → contract.
- `session.py`: `_contract`; `aim()` gate.
- `play_styles_data.py` + `play_styles.py` + `scripts/build_play_styles.py`: `default_style`
  + `default_contract`.
- `docs/design/GAME-TYPE-TAXONOMY.md`: per-card style annotation.
- `architect.py` + `cohorts.py`: `set_play_contract`; genre-led ask; `interpret_mode`→contract.
- `transport_core.py`: place the ask after world-pick / before Foyer; persist.
- Tests: `default_contract` precedence (any story-card → story; all sandbox → sandbox);
  legacy-mode migration; the ask fires once at the right seam; explicit answer overrides
  the genre default; `aim()` None in sandbox.

---

## Sequencing within this slice
C5 (contract) and C1 (conclusive core) are independent and can land in either order; C2
depends on C1 (it consumes the conclusive verdict). Suggested: **C1 → C2 → C5**, each with
its own review + green suite, then live-verify on the anchor world (a Story that reaches a
shaped conclusion + the "next episode?" prompt landing on the real climax, not a lull).

## Spec questions — RESOLVED (Cx 076)
- **Q-S1:** Host **enum** (not free string), `outcome_gloss` stays free. v1 enum =
  `triumph | costly_victory | bittersweet | partial | failure | quiet_failure` (pyrrhic
  dropped). §1.2 updated.
- **Q-S2:** `K_POSTCLIMAX = 4`, a constant with test override. **No** repair directive for
  Sandbox until opportunity arcs exist (later: applies to active opportunity arcs, never
  the sandbox contract itself).
- **Q-S3:** **Stay pending indefinitely — no idle timeout.** A gap is mid-session unless the
  player explicitly stops.

## Cx spec-review (076) — Go after these edits (folded in; implement-ready)
**Verdict:** C1/C2/C5 YELLOW (no blockers), Notes GREEN, **Go after edits.** Membrane
preserved (terminal shape/stage/contract/notes all host-side; canon only via ingest/fallout).

**C1 fixes:**
1. **Gate A needs a concrete phase source** — no `current_phase` exists today. Add a
   deterministic `executor.current_phase(reads, arc)` deriving phase from required-beat
   progress / latest achieved beat / lifecycle (NOT prose).
2. **`climax_ready` is fields, not a fn** — add `executor.climax_ready(reads, arc)` (uses
   `climax_ready_k`/`climax_ready_beats`); use in Gate A AND post-climax accounting so tests
   pin one interpretation.
3. **`conclusive_check` must take the candidate explicitly** — pass a `ConclusiveCandidate`
   (or `achieved, closed, fired` from `run_turn`), not just `reads` — preserves the
   "just this scene" distinction.
4. **Post-climax window must be eligible without a fresh event** — add a
   `post_climax_window_expired` candidate kind (else Gate-A's require-a-candidate conflicts
   with the quiet-turn repair).
5. **Epilogue no-canon = a SEPARATE branch** — on final page: run consequence/fallout
   ingest FIRST, then `narrate_epilogue`, archive the prose in `session:main`, and **skip
   the normal narrator-prose→canon promotion path entirely**.
6. **Receipt semantics** — write ONE `event:conclusion_N` (`kind=conclusion`,
   `outcome_shape`, `outcome_gloss`); generalize `terminal_outcome()` (today reads
   `arc_won/arc_lost`) to read it. **`arc_lifecycle`/side-arc fallout stay binary
   internally** — only the player-facing terminal receipt is shaped.

**C2 fixes:**
1. **Name the row:** `entity="playthrough:main", attribute="stage", frame="session:main"`;
   helpers `playthrough_stage(reads)` / `set_playthrough_stage(world, stage, turn)`.
2. **Persisted stage is the source of truth, `_pending_episode` is only a UX cache** — every
   incoming non-command must be able to discover `stage==concluded_pending_choice` from the
   slot and treat the message as the choice (survives a process bounce; no arc-tick after).
3. **Don't re-render epilogues on re-entry** — store the rendered prose/receipt; on return
   while pending show the stored epilogue/prompt, never re-call the model.
4. **`finished` short-circuits independent of legacy mode** — not gated on
   `_scenario_mode=="win_loss"`.
5. **Continuing stub needs an explicit reversible state story** — define + test what the
   NEXT message does while `continuing` (stay stubbed / return to pending / finished).
6. Restart composes: file-copy checkpoint restore clears stage naturally (active/pristine).

**C5 fixes — inventory additions + the staging correction:**
- Inventory ALSO: `game.py` viability/born-won gate (`meta["scenario_mode"]=="win_loss"`),
  `cli.py` (`--endless` + the interactive prompt — decide: legacy or rename this slice),
  `library.py` (`endless` passthrough); tests in test_architect/telegram/session/integration/
  startup/cli; docs STARTUP-ENTRY / WIN-LOSS-CONDITIONS (follow-up edits).
- **Migration:** keep the `mode` column NAME (low-risk), document value = contract now; map
  ONLY known legacy (`win_loss→story`, `bounded→story`, `endless→sandbox`; leave `NULL`/
  `__asking__`). **Runtime readers accept BOTH for ≥1 release** (`story|win_loss|bounded ⇒
  story`, `sandbox|endless ⇒ sandbox`). New meta writes `contract` + keeps derived
  `scenario_mode`/`endless` until old readers retire.
- **STAGING CORRECTION (important):** C5 maps `sandbox` to the EXISTING endless/freeplay
  behavior only — it must **NOT** claim true "Sandbox runs no `arc:main`" (build/finalize/
  open reconstruct a main arc unconditionally; `open_playthrough` ERRORS with no arc). True
  no-`arc:main` Sandbox is **C6** (after LWG P2), not C5. §2 table's "no arc:main" is the
  C6 end-state; C5 ships sandbox==endless-behavior.

**Must-update tests:** C1 — `test_integration.py::test_terminal_epilogue_names_cast_and_reveals`,
`test_win_loss_terminates_strictly`, `test_endless_never_terminates`; + Gate-A-false-on-lull,
judge-false-positive, post-climax candidate/repair, shaped-receipt readback, epilogue-no-ingest,
side-arc-lifecycle-unaffected. C2 — conclusion stage/prompt/`ended False`, good→finished, next→
continuing+checkpoint/stub, process-bounce pending, finished short-circuit. C5 — update the
win_loss/endless naming across the 6 test files; + migration idempotence, legacy-read compat,
`default_contract` precedence, explicit-override, `aim()` hidden in sandbox.
