# World-Moves-Without-You — the off-screen tick (#84)

**Status: BUILT** (2026-07-02, per Cx 395/396 YELLOW→build; founder-endorsed direction;
eval finding: "the world has no initiative" — every plateau in 90 evaluated turns).
As-built notes vs. this spec:
- Cx constraint 1 (discovery gating beyond frame writes): `event:tick_*` rows ride the
  irony `frame_diff` threads ONLY when their agent is physically present; an absent
  person's `in` row is never thread text; `Session.live_threads` skips tick events. Test
  pair: `test_tick_consequences_discovered_not_narrated` (elsewhere = silent; going there
  = presence renders the change).
- Cx constraint 2 (persisted last-seen): `last_seen_min` session rows written in settle
  for every NPC actually present; eligibility = diegetic clock minus marker ≥ 30 min.
- Cx constraint 3 (detail leak vocabulary): `value_leaks` over concealed tokens PLUS the
  protected condition atoms' literal VALUES.
- Settle placement after the time advance, before the mechanics log (`_world_tick` in
  `construct/turnloop.py`; cohort `world_tick`/"wtk" in cohorts.py); `TurnTrace.world_tick`
  debug field; culprit + genuine-required-clue holders never `moved` (drop, never repair);
  closed kind set; grounding-runway/terminal suppressed; fail-open throughout.

## The problem, in evidence

- anchor: the promised morning meeting never arrives; the world waits for the player (eval/01).
- emberroad: a pool of witnesses abandoned mid-interview never reacts, resents, or disperses (eval/02).
- thedeep: the captain who should be radioing in never does (eval/03).
- bodycase probe: Liddell hears the inquiry at his door and… nothing follows on its own.

The engine renders a world that is perfectly consistent and perfectly inert. Every NPC acts
only in the player's presence (`npc_turn` is presence-gated). Nothing happens *while you're
away* — so returning anywhere feels like unpausing a video, not re-entering a place.

## The shape (founder-endorsed): one cheap tick at scene changes

When the player's move COMMITS to a new scene, the world gets one small heartbeat:

1. **Eligibility (deterministic, host-side):** up to 2 off-screen cast members with live
   dispositions — scoped to the arc's cast, not the whole world; prefer those the player has
   MET (their absence is felt) and those whose drives touch the current live threads.
2. **One cheap LM call** (`world_tick` cohort): each eligible member's character sheet +
   where they are + the diegetic time elapsed since last seen → "what did they plausibly DO
   meanwhile?" Output: per member, at most 2 small canon deltas — a move (`in`), a state
   change on an owned object/place, or ONE event row (`kind` = a plain occurred-kind, agent =
   the NPC). Nothing else.
3. **Commit through the ingest doorway** (ordinary sourced rows, `valid_from = turn_time(turn)`).
   The membrane holds: consequences are world-facts; no `dramatic_tension`, no derived rows.
4. **Discovery, not narration:** the tick writes CANON ONLY — never `knows:<protagonist>`.
   The player learns the change the honest way: they return, and the presence briefing +
   scene reads render the world as it now is ("the barrow is gone; a constable holds the
   corner"). Off-screen motion must never leak into narration the player couldn't witness.

## Hard constraints (the teeth)

- **Protected keys:** a tick delta may not touch `arc_protected_keys(arc)` and its values are
  screened by `value_leaks` — the world moves, the answer does not hand itself over.
- **Reachability invariant:** the tick may not move the culprit (or any required-clue holder
  whose clue is undelivered) into an unreachable/undiscovered tier — the staging gate's
  promise survives every tick. Deterministic post-check on the proposed deltas; a violating
  delta is dropped, never repaired by a second model call.
- **Presence truth:** a tick never moves anyone INTO the player's current scene (no teleport
  jump-scares; arrivals on-screen remain the narration seam's job, #80). It moves people
  between OFF-screen places only, or changes off-screen state.
- **Caps:** ≤2 members, ≤2 rows each, per tick; at most one tick per committed scene change;
  none while the episode is in its grounding runway (turn 1-2) or terminal flow.
- **Fail-open:** any error → no tick, logged; the turn never degrades.

## Placement: inside `settle` (the post-send tail)

The tick's effects only matter from the NEXT turn (discovery on return), so it belongs in the
deferred `settle` closure (TURN-LATENCY dumbfire) — zero added latency on the move turn, and
the scene-change signal (`trace.movement_status` clear + new scene) is already on the trace by
then. Session-serial execution keeps canon order deterministic.

## What this is NOT

- Not a scheduler/simulation: no per-NPC clocks, no routines table (parked with diegetic-time
  follow-ons). One opportunistic beat, not a world model.
- Not the generator (P2 living-world): it never mints arcs, cast, or places — existing people,
  small true deltas.
- Not narration: the renderer discovers the rows; the tick writes none of its own prose.

## Surfaces touched

- `construct/cohorts.py`: `WORLD_TICK_SCHEMA` + `world_tick(provider, members, elapsed, threads)`
  (cheap tier).
- `construct/turnloop.py`: eligibility + post-check + commit, appended to the settle closure;
  `TurnTrace.world_tick: list[str]` for the debug surface.
- Tests: eligibility scoping; protected-key/reachability/into-scene drops; discovery-on-return
  (the changed `in` renders in the next presence briefing); the runway/terminal suppressions.

## Open questions for Cx

1. Settle placement vs. an explicit post-movement phase — settle is my call (zero latency,
   next-turn semantics); confirm no ordering hazard with the deferred promote/mirror writes.
2. Should elapsed diegetic time gate eligibility (no tick when minutes-since-last-seen ≈ 0,
   e.g. stepping next door and back)? My lean: yes, a small floor (≥ one phase-fraction or
   ≥30 diegetic minutes) so ping-pong movement doesn't churn the world.
3. Event kinds: free-form occurred-kinds from the model vs. a small closed set (moved,
   met_with, sent_word, finished_task, closed_up)? My lean: closed set + free-form detail
   attr — classifier-safe, still expressive.
