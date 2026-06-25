# event_occurs beat firing — make "do X" beats real (the arc-stall root cause)

**Status:** SPEC for Cx [DECISION] + founder review. Found 2026-06-25 via the per-genre live
richness work (endurance probe stalled in Act I). Root-causes the recurring "arc stays Act I"
symptom. Unblocks arc progression — and therefore the conclusion-as-effect, the suspense build-up,
and commitment-as-effect — for EVERY shape, not just deduction.

## The bug

Arc beats come in two kinds (both the session-zero arc author `game.py` and the living-world
generator emit them):
- **`player_learns`** → an `InFrame(knows:<prot>, e, a, v)` condition. Fires reliably: cast-clue
  delivery / the commitment writes the fact into the player frame, `beat_pass` achieves it.
- **`event_occurs`** → an `Occurred(kind=X)` condition. Requires a **canon event of kind X**.
  **Nothing in play ever writes those events** — not the prose extraction, not the action/
  resolution path, not the commitment. `X` is a string the model invented
  (`cargo_abandoned_to_keep_party_together`, `alarm_raised`, `wreck_inventory_completed`).

So **every required `event_occurs` beat is structurally dead** — it can never achieve. The arc
stalls in the phase that requires it and never reaches the climax/conclusion. The arc-author prompt
actively *prefers* `event_occurs` ("Prefer kind `event_occurs` with a plausible event kind"), so
this hits any action/heist/survival arc whose milestones are ACTS, not learnings. (Deduction
survives because its beats are `player_learns` + the commitment.)

Live evidence: the generated endurance arc ("The Red Cord at Howse Pass") had `inventory_the_living`
(RISING/REQUIRED) and `choose_red_cord_over_ore` (CLIMAX/REQUIRED) both as `event_occurs` → both
dead → the arc sat in Act I through the whole probe despite rich scene-level play.

## Why fix (not ban)

`event_occurs` is the RIGHT shape for the genres whose climax is an act: abandon the cargo to keep
the party on the cord, raise the alarm, spring the heist, win the bout, make the sacrifice. Banning
it (forcing every required beat to `player_learns`) would cripple every non-deduction climax into an
unnatural "learn a fact." So the fix is to MAKE `event_occurs` fire when the act happens.

## The mechanism

A per-turn check that writes the authored event when the player's action makes it happen, so
`beat_pass` (unchanged) achieves the beat:

1. **Gather** the arc's PENDING `event_occurs` beats — `Occurred(kind=X)` conditions on beats not
   yet achieved, in reachable phases (skip already-achieved). For most deduction arcs this is empty
   → the check is skipped (no added latency where it isn't needed).
2. **Detect** (cheap, one call, ONLY when the pending set is non-empty): given the player's action +
   its resolved outcome + the just-rendered beat, ask "did any of THESE authored events just
   happen?" The candidate kinds come from the pending set (a constrained classification, not open-
   ended invention). Returns the kind(s) that genuinely occurred this turn (often none).
3. **Write** a canon event of each occurred kind, `caused_by` the turn's action event, so
   `Occurred(kind=X)` evaluates true. `beat_pass` then achieves the beat and the arc advances.

**Placement (Cx 115 #1 — resolution must bind FIRST):** today the resolution deck is drawn LATE
(briefing assembly), AFTER `beat_pass`. The detector must see the RESOLVED OUTCOME, not the
attempt — else it could canonize `Occurred` on a FAILED uncertain action and the narrator then
renders failure against canon. So:
- Draw the resolution outcome EARLY (after classify): `assured` when `needs_test == false`,
  otherwise the drawn tier; persist/trace it ONCE.
- The detector runs after that, BEFORE `beat_pass`, and fires an authored event only when the act
  ACTUALLY happened — normally `assured`, `success_cost`, or `complete_success` (never on a
  failure tier).
- The narrator briefing REUSES the stored tier/directive (no second draw) AND includes the
  fired-event result as a BINDING world fact for the turn, so prose cannot contradict the canon row.
Fail-open: a miss just doesn't advance the beat that turn (same as today), never sinks the turn.

**The `caused_by` anchor (Cx 115 #2):** there is not always a canonical action event today
(`event:turn_N` is session bookkeeping written after render; movement/take are deterministic state
writes). So mint a canon `event:action_<turn>` row (entity-typed `agent=protagonist`, provenance,
valid time) and anchor the authored event's `caused_by` to it — never to a session-only marker.

**Guards:**
- Candidate kinds are ONLY the arc's pending authored `event_occurs` kinds — never arbitrary
  model-invented events into canon.
- The event fires only when the act genuinely occurred (the detector defaults to "no" when unsure —
  a beat should not achieve on a near-miss) AND the resolution tier is a success/cost tier (never a
  failure tier — Cx 115 #1).
- One canon event row per occurred kind, with `caused_by` the minted action event; no derived labels.
- **Dedupe by beat status** (Cx 115): already-achieved beats offer no candidates and produce no
  duplicate event rows.
- **Global-kind collision (Cx 115):** event `kind` is global, so a generic slug could satisfy a
  DIFFERENT arc's beat or a `failure_when`. Mitigate: require generated `event_occurs` kinds to be
  arc/beat-specific (slug carries the arc/beat), and/or include `agent`/participants; +a collision
  test. The detector only offers the CURRENT pending set, but the WRITTEN kind must be specific.
- **Side arcs (Cx 115):** include active side arcs' pending `event_occurs` kinds in the sweep, else
  side-act beats stay dead.
- Convergence still pulls the player toward the pending beats (so they're reachable, not just
  fireable) — this fix makes them FIRE; convergence makes them REACHED.

## Acceptance

- Unit: an arc with a pending `event_occurs` beat + a player action the detector flags as occurred →
  the canon event is written, `beat_pass` achieves the beat, the arc advances a phase. A near-miss
  action → no event, beat stays pending.
- Live: re-run the endurance probe with inputs that engage the cargo-vs-cord choice → the climax
  `event_occurs` beat fires, the arc reaches Act II/CLIMAX, the suspense amplifier engages, and the
  conclusion-as-effect lands. (The thing the first endurance probe couldn't reach.)

## Scope / boundary
- This is the SESSION-ZERO arc's beats + the live generator's beats — both use `event_occurs`.
- It does NOT touch `player_learns` (works), the commitment path, or `failure_when` (its own clock).
- The detector is genre-agnostic (it reads the arc's own pending kinds), so it fixes ALL shapes.
