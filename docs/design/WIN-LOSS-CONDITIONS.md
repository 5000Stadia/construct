# Win/Loss & Freeplay — host spec (DRAFT, under group review)

**Status:** initial draft, circulated to K / Cx / PB for full draft-then-review
before build. Construct-owned (arc layer + session-zero + turn-loop render).
Founder side-spec 2. **No engine dependency** — this is a reframe + completion of
the existing arc machinery.

## 1. What exists already (this is mostly a reframe)
The arc grammar already carries the bones: `ConclusionShape` (the hidden
destination + character delta, with a refusal variant), a **refusal clock** +
`refusal_conclusion`, `unreachable_if` beats, `arc_concluded()` (true when the
destination's `world_condition` holds **or** the refusal clock fires), the
turn-loop **aftermath render** on conclusion, and an `endless` flag. So "win"
(destination reached) and "loss" (refusal/unreachable) already half-exist —
what's missing is the **player-facing framing**, an **explicit mode choice**,
and **flavored termination**.

## 2. The three modes (session-zero choice)
At session-zero the player picks:
- **`win_loss`** — predetermined success *and* failure terminals. Reaching either
  ends the scenario with a flavored, buttoned-up aftermath. A non-spoiling goal is
  stated up front.
- **`endless`** — the arc still concludes, but the world carries on past the
  destination (existing behavior; no hard termination).
- **`freeplay`** — no win/loss framing and no stated goal. The arc may run as soft
  ambient pressure or be absent; the world simply persists. (Distinct from
  endless: endless *has* a destination it reaches-then-continues; freeplay frames
  no destination to the player at all.)

Stored in `meta.mode` (today: `"pure"` → becomes one of `win_loss`/`endless`/
`freeplay`). `endless` flag folds into `mode`.

## 3. The non-spoiling player-facing goal (the new surface)
The arc is fully hidden today. `win_loss` mode surfaces **one line** — the
*headline* of the destination, not its mechanism: "survive the journey to safer
ground for your clan," "solve the mystery and name the culprit," "hold the
settlement together through the winter." It is:
- **Authored by the arc-author model** from the destination it just wrote
  (a `goal_statement` minted alongside the `ConclusionShape`), phrased as an
  aim, never the solution.
- **Stored** (proposed) in `plot:main` (hidden-frame) as `arc:main · goal_statement`
  and shown at `Session.opening()` in `win_loss` mode.
- **Leak guard:** the goal statement must not name the hidden beats, the culprit,
  or the mechanism — only the aspiration. (A lint check + the same player-boundary
  discipline the narrator already uses.)

## 4. Win and loss terminals
- **Win** = the destination reached: `arc.shape.world_condition` satisfied (the
  climax sufficiency set) — the existing `arc_concluded` success branch.
- **Loss** = a failure terminal. Reuse the existing signals, promoted to enders:
  the **refusal clock fires**, *or* a `Weight.REQUIRED` beat goes **unreachable**
  (`unreachable_if`), *or* an explicit authored failure condition (a
  `failure_when` Expr on the arc — proposed, mirrors `world_condition`).
- In `win_loss` mode, on detecting either, the scenario **terminates** with a
  flavored aftermath; in `endless` mode the success carries on and there is no
  loss-termination; in `freeplay` neither terminates.

## 5. Detection + flavored aftermath
`arc_concluded()` already detects destination-or-refusal each turn. Extend to a
small `arc_outcome(reads, arc) -> "won" | "lost" | None`:
- `won` if `world_condition` holds.
- `lost` if a failure terminal holds (refusal fired / required-beat unreachable /
  `failure_when`).
- `None` otherwise.

The turn loop's existing aftermath branch (`concluded and not endless`) becomes
outcome-aware: on `won`, render a **success aftermath/denouement** ("you reach
the ridge; the clan breathes"); on `lost`, a **failure aftermath** ("the truth
never surfaces; the meter stays dark") — both buttoned-up, applying no new
pressure, then the scenario is **terminal** (the session reports `ended`, the slot
is complete). The narrator gets an outcome directive; the win/loss flavor is the
*only* new branch in the render.

## 6. Mode interactions
- `endless`: unchanged — concludes, carries on, never terminates.
- `freeplay`: `arc_outcome` is never consulted as a terminator; no goal shown.
  (The arc may still exist for soft nudging, or session-zero may skip arc
  authoring entirely — open question §8.)
- `win_loss`: the only mode that ends the scenario and shows a goal.

## 7. Explicitly out of scope
- No new arc *grammar* beyond `goal_statement` + (proposed) `failure_when` — both
  optional fields, defaulting to today's behavior when absent.
- No engine change. Win/loss are host-evaluated over existing reads (the same
  atoms `arc_concluded` already uses).
- Multi-ending trees / scoring / partial-credit — deferred (a third shape forces
  it, per discipline).

## 8. Open questions for the reviewers
- **K (host discipline / SESSION-ZERO):** does the mode live in session-zero as a
  player choice cleanly? Is `freeplay` "arc-absent" or "arc-present-but-unframed"
  — which fits the host's session-zero design? Is `goal_statement` in `plot:main`
  the right hidden-frame home?
- **Cx (shape / adversarial):** are `won`/`lost` detection conditions
  deterministic and mutually-exclusive (can a turn be both won *and* lost — e.g.
  destination reached the same tick the refusal clock fires — and what's the
  tie-break)? Can the `goal_statement` leak the hidden arc? Failure-terminal
  false-positives (a required beat flagged unreachable that later becomes
  reachable)?
- **PB (engine truth):** confirm **no engine dependency** — win/loss are host
  evaluations over existing reads; `goal_statement`/`failure_when` are ordinary
  `plot:` facts. Flag if anything assumed here isn't expressible.

## 9. Not built yet
Draft for review. On integrating the markup: add the mode choice to session-zero,
the `goal_statement` (+ leak lint) and optional `failure_when` to the arc author,
`arc_outcome` to the executor, and the outcome-flavored terminal aftermath to the
turn loop. Nothing ships before the review lands.

---

## 10. Integrated review decisions (build target) — K 063 / Cx 063 / PB 064

All three legs GREEN-on-architecture / zero-engine-dependency. Folded decisions
(this is what gets built):

- **`meta.scenario_mode`, NOT `meta.mode`** (Cx #1, load-bearing). `meta.mode`
  already drives turn-loop input authority (`pure` = declaration-denial guard) —
  overloading it would silently disable that. New field `scenario_mode ∈
  {win_loss, endless, freeplay}`; `mode` keeps pure/coauthor.
- **Modes are expression dials; never structurally omit the arc** (Kernos).
  Always author the arc; modes differ by *goal-shown* / *terminates* /
  *nudge-strength*. `freeplay` = no player-facing destination **and** `arc_outcome`
  is not a terminator (Cx) + nudge dialable toward zero (Kernos).
- **`arc_outcome(reads, arc) → won|lost|None`** evaluated once after the full tick,
  **total priority, won-first** (Cx #2 / Kernos / PB): `won` if `world_condition`;
  else `lost` if a failure terminal; else `None`. Won-wins-ties (destination
  reached the same tick the refusal clock fires → `won`; protects agency).
- **Loss terminals NARROWED** (Cx #3, load-bearing): `lost` = refusal clock fired
  **or** an authored `failure_when` Expr. **NOT** "any required beat unreachable" —
  that stays the repair trigger (refusal backstops), not an immediate loss.
  (First slice: `lost` = refusal-fired; `failure_when` added with the arc-author.)
- **`goal_statement` = player-frame derivative, structurally non-leaking**
  (Kernos + Cx #5 + PB): derive a sanitized aspiration from the hidden destination
  into a PLAYER-facing frame (keeps `plot:` hermetic — Kernos), with a
  **forbidden-token check** over hidden entities/values + **fail-closed** retry
  (Cx) — not lint-hope. PB confirms it's an opaque stored fact either way.
- **Terminal state = real transport, not just aftermath flavor** (Cx #4): on
  `arc_outcome != None` in `win_loss`, write a terminal receipt
  (`session:main` `event:arc_outcome` outcome=won|lost + terminal marker); after
  terminal, `Session.turn()` does NOT run a new tick / re-render aftermath — it
  returns the ended state. Replay = a fresh fork, not a re-open (Kernos). Define
  CLI + Discord post-terminal behavior.

Build order (slices): (1) `arc_outcome` + `scenario_mode` [safe/additive] →
(2) terminal transport in Session/turn-loop → (3) arc-author `goal_statement`
(+ forbidden-token/fail-closed) + `failure_when` → (4) the mode wiring
(session-zero choice, freeplay nudge dial, opening() goal display).
