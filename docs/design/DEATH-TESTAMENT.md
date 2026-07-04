# Death & the Testament (#95)

**Founder rulings (2026-07-02/03):**
1. "If I am in a scenario where death would be the end of the story, such as an action,
   adventure or a fantasy adventure then death should be the end. There should be a nice
   conclusive statement about the world and the player's effect on the world after their
   death as an epilogue testament."
2. "The scenario that mirrors Groundhog Day would obviously not end in death" — the
   premise transforms it.
3. **Permanence:** "the end of a rich world where we are playing a first person
   perspective should probably terminate at the death of the player" — no new-character
   continuation, no next chapter. Death is where the world's story ends for this player.

## Design principles

**Death is an EFFECT, never a draw.** The resolution deck is fail-FORWARD by design —
`terrible_failure` must never silently become "you die." Death enters only through a
deliberate, staged path where the player saw the mortal stakes and walked into them.

**Staged, never a gotcha** (the #88 lesson — clarify before consequence). Death never
arrives on a turn where the player couldn't see it coming. The first turn a move risks
the protagonist's life, the fiction makes the stakes UNMISTAKABLE and lands the move
short of death (the staging turn). Only persistence into staged peril can kill.

**Fiction-established peril only** (the diegetic-time analog: only a fiction-established
deadline forces a conclusion → only fiction-established mortal peril can kill). The
narrator cannot invent a lethal turn; the peril must stand in the scene.

**The genre decides whether death is on the table** — the founder's gate, resolved at
build, not per turn.

## Mechanics

### 1. `death_policy` (build-time meta)
One cheap build-time classification over (genre, game_types, premise, shape) → stored
`meta["death_policy"]` + one-clause `death_policy_reason`:

- **`mortal`** — death ends the story (action, adventure, fantasy, survival, thriller,
  war…). The full pipeline below is live.
- **`premise`** — the premise transforms death (time loop, ghost, resurrection
  mechanic). Death never terminates; when it lands, the narrator is DIRECTED to fold it
  into the premise mechanism (wake again, the loop resets) — the Groundhog case.
- **`shielded`** — on-screen player death is not in the genre's contract (cozy mystery,
  romance, drawing-room intrigue). Mortal risk never escalates past wounds, capture,
  ruin — the classic conventions.

Existing worlds without the field default to `shielded` (no behavior change until
rebuilt/backfilled).

### 2. Detection: `mortal_risk` (classify) + the staged-peril marker
- `CLASSIFY_SCHEMA` gains `mortal_risk: bool` — true only when the player's move risks
  the protagonist's LIFE given the established scene (not mere injury; not an NPC's
  life). Judgment folded into classify, same as `needs_test` — no extra call.
- Session marker `peril:staged` (SESSION literal, entity `session:peril`, turn-stamped):
  - First `mortal_risk` turn with NO standing marker → **staging turn**: briefing
    directive renders the lethal stakes unmistakably and lands the move SHORT of death
    (near-miss, wound, pinned); marker written.
  - `mortal_risk` turn WITH a standing marker (staged peril persists) → the deck
    decides: `terrible_failure` → **death**; every other tier → fail-forward as today
    (the skew already favors survival ~9:1).
  - A turn that leaves the peril (retreat, scene change, the danger resolved) clears
    the marker — peril doesn't stalk the player across scenes.

### 3. The death terminal
On death (policy `mortal`, staged, terrible_failure):
- SESSION receipt `event:player_death_<turn>` (`kind=player_death`, `cause` = one
  clause). `terminal_outcome()` learns the kind → returns `"died"`; the transport's
  ended gate fires exactly as for won/lost. Works in BOTH scenario modes — an endless
  world still ends at death (permanence is the point).
- The #96 consequence writer runs with a new `died` key in `_ENDING_CONSEQUENCES`
  (word of the death travels; what the player set in motion continues without them).

### 4. The Testament epilogue (a third BEAT-1 variant)
The terminal render branches three ways now (RECKONING / SETTLING / **THE FALL**):
- **BEAT 1 — THE FALL:** the death rendered honestly, in scene, at the pace of the
  moment — no rescue invented, no cutaway, no scolding. The world answers the player's
  last move truthfully.
- **BEAT 2 — THE TESTAMENT:** the world after them, and their effect on it — what they
  changed that STAYS changed (from canon consequences + the ledger), what they left
  undone, the personal threads (#96 S4) left forever open — named as testament, not
  bookkeeping ("she waited at the rail end after close; he never came"). Fates of the
  cast as touched by the player. Concealment lifts (the story is over): the truth they
  never learned, savored. Closes every thread; opens nothing.

### 5. Permanence (no continuation)
- `continue_episode` refuses when a `player_death` receipt exists: the offer never
  renders; a direct call returns the refusal ("the story ended at <name>'s death").
- No new-character re-entry into the dead player's world (founder ruling). The slot
  stays readable (notebook, transcript) — the world is a finished book, not a lobby.

## As built (Cx 422 constraints folded)

- **Terminal discriminator**: `terminal_outcome()` returns `"died"` from `player_death`
  SESSION receipts (checked FIRST — death outranks win/loss), episode-scoped.
  `TurnTrace.terminal_kind = "died"`; `Reply.can_continue = False`; `Session.turn`
  checks death regardless of `scenario_mode`; `transport_core` renders "The End" with
  NO `_pending_continue` arm; `continue_episode` refuses before any generator work.
- **Terminal precedence**: `died` is a separate terminal source — no arc_won/arc_lost
  shape receipt, `_conclusion_effect` skipped, and THE FALL/TESTAMENT branch is
  selected BEFORE the `_commitment_landed` reckoning/settling ternary.
- **Escalation gate** (guarded exactly as Cx specified): `death_possible = policy ==
  "mortal" and staged and mortal_risk and needs_test and tier == "terrible_failure"`.
  A no-draw turn stages or warns, never kills.
- **Marker**: `session:peril` (scene + cause, SESSION literal). Standing = same scene
  AND classify says mortal_risk again. Cleared on scene change or first non-risk turn.
- **Consequences**: the `died` key in `_ENDING_CONSEQUENCES`; consequence events
  `caused_by event:player_death_<turn>` via explicit event-entity rows (the 420 lesson).
- **Policy is per-chapter**: derived at `_finalize_scenario` (fail-open `shielded`),
  re-derived in `continue_episode` against the new chapter's hook.

## Test bar
1. First `mortal_risk` turn (no marker) → staging directive present, NO death receipt,
   marker written.
2. Staged + `mortal_risk` + forced `terrible_failure` (policy `mortal`) → death receipt
   + `terminal_outcome() == "died"` + THE FALL/TESTAMENT briefing (threads named, no
   new hooks) + consequence rows with `caused_by`.
3. Same turn under policy `shielded` → no receipt, fail-forward wound directive.
4. Same under policy `premise` → no terminal; the fold-into-premise directive present.
5. `continue_episode` after a death receipt → refusal, no generator call.
6. Marker clears when the player leaves the peril; a later lone `mortal_risk` turn
   stages again rather than killing.
