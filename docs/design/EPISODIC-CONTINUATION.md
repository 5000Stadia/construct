# Play Contracts, Conclusive Outcomes & Episodic Continuation (design)

**Status:** DESIGN-FIRST, founder-confirmed end-to-end (2026-06-20). Greenlit for the
pipeline: **design bounce (Cx) → spec w/review → implement w/review.** This is the
source of truth for the Cx design bounce. Supersedes the binary `win_loss` / `endless`
framing of STARTUP-ENTRY and the binary outcome of WIN-LOSS-CONDITIONS.

Related: [[STARTUP-ENTRY]], [[LIVING-WORLD-GENERATOR]], [[CONCLUSION-AND-OUTCOME]],
[[WIN-LOSS-CONDITIONS]], [[GAME-TYPES]], [[CHARACTER-CREATION]], [[narrative-memory-ledger]].

---

## 1. The core decision: decouple the WORLD from the OBLIGATION

A rich world is worth inhabiting for its own sake; an authored goal is a *separate*
thing laid on top. The pattern-buffer already gives us a fully alive world with no
goal attached — object permanence, frame-scoped NPC knowledge, diegetic time, re-entry
coherence, the living-world ambient generator. The **arc layer** (destination, stakes,
conclusion) adds the *pressure*.

Therefore **"do you want a goal at all" is a play-time contract chosen per playthrough,
not baked into the genre.** The same Star Wars world serves the Death-Star-heist
thriller and the sip-blue-milk-in-Mos-Eisley tourist; the world doesn't change, only
the player's appetite does.

## 2. Two play contracts (Story collapsed Series into itself)

Originally three (Story / Series / Sandbox); the founder collapsed Story and Series:
because *every* conclusion offers "continue or stop?" (§5), a one-shot Story is just a
Series where the player stops after episode one. No mechanical difference. So **two**:

| Contract | Player-facing as | Shape | Arc behavior |
|---|---|---|---|
| **Story** | *"a story to play through — a goal, an ending"* | a goal-driven, conclusive arc that is inherently **serializable** (continue into the next episode, or stop) | the authored arc is the spine; reaches a conclusive ending; offers continuation |
| **Sandbox** | *"a world to just explore, no pressure"* | open exploration | **NO `arc:main`** — opportunity/side arcs only (dormant → offered → active-if-engaged → resolved/expired diegetically), never session-ended (Cx RED fix, §12) |

### Story (with pressure) vs. Sandbox (without) — the Sherlock test
The difference is **obligation, not content.** Same Holmesian world (Baker Street, the
fog, Mrs. Hudson, full deductive richness) either way. Story: one case, a destination
(*solve it*), a conclusive ending. Sandbox: cases are *available, not demanded* — an
inexhaustible opt-in supply; a case untaken is a road not taken. The hidden-truth
machinery still runs per case, so deduction stays *real* — you just aren't marched to
it or punished for sipping tea instead.

### The Sandbox guardrail (non-negotiable)
The failure mode: *"Sherlock unable to find a case"* — an empty room. **Sandbox leans
HARDEST on the living-world generator, not the least:** its job is to keep the world
*offering* (a client at the door, a notice in the *Times*, Lestrade stumped). Sandbox
= *"always something to investigate, never a penalty for not."* **Dependency:** Story
ships on the arc layer we have; **Sandbox is gated on the opportunistic generator**
([[LIVING-WORLD-GENERATOR]] P2) or it *is* the empty room.

## 3. Conclusive Outcomes — retire the binary win/loss

(Founder, the meatiest refinement.) An outcome is **not win/lose** — it is a
**narrative-shaped conclusion along a spectrum**: triumph, pyrrhic win,
*success-with-terrible-loss* (Sherlock finds the man but he slips the cuffs), quiet
failure, etc. The narrative shapes the result; the engine renders it. Two new jobs:

1. **Detect the conclusive moment** — the dramatically-right "final page," a *judgment*,
   not a flag flip. **Conservative: it only fires when the story has narratively earned
   its ending.** Biased toward *not yet* — never end prematurely. The engine reasons
   about which moment is the concluding frame.
2. **Render an epilogue** that narrates what happens *in that concluding frame* — the
   shaped outcome, whatever shade it landed on.

This reframes [[CONCLUSION-AND-OUTCOME]] / [[WIN-LOSS-CONDITIONS]]: from "win-cond met /
loss-cond met" to "the story reached its earned ending; here is the shape of it." (The
arc's `failure_when` / win-state still *inform* the shape — they no longer *gate* a
binary.)

## 4. Identifying the contract — ask straight up, genre-led suggestion

Settled **right after the world is chosen/built, before the Foyer** ([[CHARACTER-CREATION]]),
replacing the old mode interview at that seam. **Asked explicitly** (founder — not
silently inferred): *"Do you want a story to play through — a goal, an ending — or a
world to just explore, no pressure?"*

**Genre leads the question (Q9 = Option A):** each of the 155 game-type cards
([[game-types]]) carries a **`default_style`** field (`story` | `sandbox`). The
Construct uses it to lead with a genre-aware suggestion — *"This one plays naturally as
a case to crack — want that, or would you rather just explore?"* — while the player
still answers explicitly. Architect/Atrium agent gains a `set_play_contract` tool (same
shape as `set_game_type`). The contract persists on the registry (extends the `mode`
column / a `contract` value).

**Locked once chosen (Q3):** no mid-session switching — to change, restart. (Discretion
to expose a toggle only if it falls out for free; otherwise not worth the state.)

## 5. The continuation gate — a moment, not a branch

At an episode's conclusive ending (§3): acknowledge it's over, then ask **"Start the
next episode, or are we good?"** — the Harry-Potter-book-2 moment. Offered at **every**
conclusion regardless of the outcome's shape (a loss-shaded ending still offers the next
book — it's framed as *the story ended*, not *you failed*). On "good," the playthrough
closes gracefully (resumable as a finished series).

## 6. Authoring the next episode

### 6.1 Lived play is higher canon than the source (Q5)
Author episode N+1 the way a good series author would (HP / Percy Jackson / LOTR /
Matlock / Sherlock), building on **what actually happened in play** — the playthrough
(history overlay) is treated as *more canonical than the original fiction*, because the
player and engine exercised real creative agency. The source is the seed; the lived
story is the truth episode N+1 honors. The scenario-creation engine is handed the **full
Ledger** ([[narrative-memory-ledger]]) + the original fiction + the current world digest.

### 6.2 The transition delta-ingest (Q6 — corrected from "no re-ingest")
Episode N+1's **opening is authored prose** and may be a **time jump** ("two years
later"). That transition **changes some statuses and leaves others standing** — "that's
just how the story do." So:
- We **do ingest the transition deltas** — the status elements the opening prose
  establishes/changes get written into the PB.
- Facts that persist are **respected and carried** (not re-stated, not wiped).
- This rides the engine's append-only nature exactly: the transition ingest writes new
  rows; the resolver **supersedes the facts that changed**; everything unchanged persists
  by simply not being contradicted. A **layered delta**, not a full re-ingest, not a
  wipe — honoring the seam between episode N's end and N+1's beginning, and *especially*
  getting the changes right.
- Then a **new conclusive arc** for episode N+1 is authored over that updated world
  (beats/clocks/shape/pins on `plot:main`), referencing existing entities by real id.

## 7. The episode-start checkpoint (built this session; the rollback primitive)
- A slot is a **copy** of the pristine `<name>.world`; play writes only the slot. The
  pristine world is episode 1's pre-character checkpoint by construction.
- At a **playable episode start** (after the Foyer applies the character for ep1; at
  ep N+1's opening), `game.checkpoint_episode_start` copies slot → checkpoint. **One
  rolling checkpoint = the current episode's start (Q7); no stack.**
- `restore_episode_start` recopies checkpoint → slot (roll the *current* episode back to
  its opening, earlier episodes' canon intact). `restore_original` drops slot +
  checkpoint → next fresh entry recopies pristine `.world` (all the way to episode 1).
- No new engine primitive — host-side file copy (the slot is already a fork; consistent
  with PB's append-only membrane).

## 8. `/restart` (built this session — contract-aware front end)
```
/restart  →  "How far back?"
  • "episode"  → restore_episode_start (character carries over, no Foyer);
                 falls back to clean copy + re-applied saved character if no checkpoint.
  • "original" → "Keep the character you set up, or redo the interview?"
        • "keep" → restore_original + re-apply saved character (skip Foyer)
        • "redo" → restore_original + re-run the Foyer
  • "cancel"   → carry on.
```
Supporting (built): registry `character` column + `get/set_character`; `_checkpoint_episode`
at Foyer completion; `_wipe` drops checkpoints. Tests: `tests/test_telegram.py::TestRestart`.

## 9. How the two long-form engines compose
- **Within an episode:** the living-world generator ([[LIVING-WORLD-GENERATOR]]) provides
  texture / anti-stall — and *is* the engine of the Sandbox contract.
- **Between episodes:** the episode-authoring path writes the next *conclusive* installment.

Continuous fuel inside; structured payoff at the seams.

## 10. Build ordering
1. **Shipped:** `/restart` (episode vs original; keep-vs-redo) + checkpoint primitive +
   saved-character store. ✓
2. **Conclusive Outcomes (§3):** conclusive-moment detector (conservative) + shaped-outcome
   epilogue; retire binary win/loss in the conclusion path. (Reframes [[CONCLUSION-AND-OUTCOME]].)
3. **Play-contract plumbing (§2, §4):** Story/Sandbox; explicit ask + `default_style` per
   card + `set_play_contract`; persist contract. Gate the arc layer for Sandbox (no
   conclusion forced, clocks don't end, beats demote to optional). Arc *grammar* unchanged.
4. **Episode continuation (§5, §6):** conclusion → "continue?" gate → author next episode
   (ledger + source + world digest → transition delta-ingest → new arc) → checkpoint.
5. **Sandbox** depends on [[LIVING-WORLD-GENERATOR]] P2 — sequence after.

## 12. Cx design-bounce verdict (2026-06-20) & corrections folded in

Ratings: §6.2 transition-ingest **YELLOW**, conclusive detector **YELLOW**, Sandbox
arc-gating **RED**, Story/Series collapse **YELLOW**, scope **YELLOW**. Corrections:

- **(RED) Sandbox ≠ arc:main-with-flags-off.** "Demote required beats to optional"
  fights the arc grammar (refusal clocks, required beats, lint, terminal receipts are
  mandatory in [[ARC-LAYER]]). Fix: in Sandbox, **do not author or run `arc:main` as
  terminal pressure at all** — only **opportunity arcs** with a lifecycle
  `dormant → offered → active → resolved/expired`, never writing a SESSION terminal
  receipt. (§2 table updated.)
- **Conclusive detector = two gates, not one judgment.** (1) a **deterministic
  eligibility gate** first — Story contract, crisis/climax or refusal path, minimum
  arc progress, a candidate conclusive event/foreclosure present; only then (2) an
  **LLM final-page judge** over world-state + Ledger + recent turns. Plus a
  **post-climax adjudication window**: after K quiet post-climax turns, force a
  "final beat or conclude" repair so we never miss the natural end. (Refines §3.)
- **Epilogue mints no canon.** It may narrate only **committed facts**; any durable
  consequence is written through a terminal/transition **delta ingest**, not prose.
- **Transition needs a structured `TransitionPlan`, not just prose** (§6.2): `{time_jump,
  deltas, explicit_carries, retire/unknown candidates, frame_deltas, caused_by}`, plus a
  **volatility audit** over `current_state` (CONSTITUTIVE/DISPOSITIONAL carry by default;
  volatile STATE must be explicitly carried / superseded / retired — the "wound still
  open / clerk still at the desk after 2 years" trap), a **frame-delta pass** (who
  learned/forgot across the jump), a `event:episode_transition_N` (caused_by the terminal
  event) every delta links to, host **episode-boundary receipts** (`episode_end_seq`/
  `episode_start_seq`/diegetic time/terminal+transition event ids) so continuation reads
  pick an explicit `as_of`, an **unresolved-thunk frontier** preflight, and **staging-world
  copy+swap** for ingest atomicity. Gated on the PB decisions (§13).

## 13. PB engine rulings (letter 078 → PB 074-from-pb: ALL SIX GREEN, no new primitive)
Components 3–4 **unblocked**. The membrane holds throughout — **engine mechanism, host
judgment**:
- **[A] close a volatile STATE across a jump:** `valid_to`-**close** the interval at the
  seam (NOT retraction = "never true"; NOT revert-to-thunk = erases history). as-of-N stays
  true; the key reads empty/unknown at as-of-N+1 (RFC-002-clean *absence*). New current
  value → append a STATE `valid_from=seam`. **CONSTITUTIVE facts carry by not being
  contradicted** (no recency-supersede; persist until re-authored). The host **volatility
  audit** decides *which* STATE is too volatile to carry.
- **[B] cross-episode as-of axis = PB `valid_time`** (NOT `asserted_at` = audit axis; NOT
  diegetic `time:elapsed` = a story-value, never the coordinate). **Set an explicit
  valid-time epoch `T_{N+1}`** at the boundary, greater than every episode-N `valid_from`;
  stamp transition deltas + episode-N+1 rows at it; `valid_to`-close carried-out STATEs at
  `T_{N+1}`. Then `as_of(T_N)` serves episode N, `as_of(T_{N+1})` serves N+1. Host keeps
  the epoch monotonic. No new primitive.
- **[C] frame forgetting works TODAY:** `valid_to`-close the stale `knows:` row at the epoch
  (belief-updated = new `knows:` row `valid_from=seam`). `who_knows(... as_of=)` folds these
  correctly now (respects `valid_to`). **Softened dependency:** the RFC-002 *automation*
  isn't built, but the **manual close + who_knows-as-of composes today** — host orchestrates
  which beliefs to close. NOT hard-gated on RFC-002. ([[npc-learning-pattern]].)
- **[D] live-thread continuity:** `event:episode_transition_N` (caused_by the terminal/
  fallout event) is **sufficient** — `situation`/live-thread reads are frame/episode-
  agnostic (effects + caused_by). No new primitive; a PB-side episode convention is **not
  wanted** (would leak host meaning into the engine).
- **[E] pre-jump thunks:** engine forces under **then-current** policy at force-time (no
  original-context binding). Host **re-scopes/resolves past-scoped thunks AT the transition**
  (while episode-N context is current); era-neutral thunks resolve current when later forced.
- **[F] ingest atomicity:** `buffer.append` commits per-row → a multi-row delta can commit a
  prefix on a mid-inline timeout. **No transactional ingest today.** **DECISION (host, mine
  to make): use staging-world copy + swap** (the proven viability-gate/fork pattern — no
  engine change, abandons the copy cleanly on timeout). PB *offered* to build a transactional
  ingest boundary on request — **declined for now** (restraint; pull it later only if the
  staging copy-cost bites).

**Net: no new engine primitive for any of A–F. Components 1, 2, 5 AND 3, 4 are now all
spec-able; only the build sequencing (§14) orders them.**

## 14. Spec decomposition (Cx-recommended, the build order)
1. **Conclusive Outcome Core** — eligibility gate + final-page judge + terminal receipt
   + epilogue-from-committed-facts. (On existing arc reads — UNBLOCKED.)
2. **Story Terminal State Machine** — `active → concluded_pending_choice → finished |
   continuing`; restart/checkpoint semantics. (Depends 1 — UNBLOCKED.)
3. **Transition Delta Compiler + Preflight** — `TransitionPlan`, volatility audit, frame
   deltas, caused_by, staging/swap. (Depends PB A–F — GATED.)
4. **Episode N+1 Authoring** — Ledger/source/world-digest → transition prose + structured
   deltas → new-arc lint → checkpoint. (Depends 2–3 — partly GATED.)
5. **Play-Contract Plumbing** — explicit Story/Sandbox choice, per-card `default_style`,
   locked registry value, migration from old `mode`. (Depends 1 — UNBLOCKED.)
6. **Sandbox Contract** — no `arc:main`; opportunity arcs only. (Depends LWG P2 +
   plumbing — sequence last.)

## 11. Resolved decisions (was "open questions")
- Three contracts → **two** (Story absorbs Series). ✓
- Outcomes **non-binary** → conclusive, narrative-shaped, conservative timing. ✓
- Contract **locked** once chosen; change = restart. ✓
- Continuation offered at **every** conclusion (win- or loss-shaped). ✓
- Lived play **> source** as canon for the next episode. ✓
- Transition **delta-ingest**, not no-re-ingest. ✓
- **One rolling** checkpoint. ✓
- Contract **explicitly asked**, genre-led via per-card `default_style` (Option A). ✓
