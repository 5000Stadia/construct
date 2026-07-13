# Turn-latency decomposition — first instrumented probe (2026-07-13)

Watch-item from the WORLD-GROWTH program: Ironhold live turns ran
400-615s. Two instrumented turns on ironhold/critic_displaced
(CONSTRUCT_MECHANICS_LOG on; trace.timings):

| turn | wall | classify | npc_action | narrate | post_extract | promote | timed total | UNTIMED |
|---|---|---|---|---|---|---|---|---|
| 1 (take stock) | 615s | 6.5 | 180.1 | 80.0 | 32.2 | 35.3 | ~334s | **~281s** |
| 2 (ask person) | 422s | 8.6 | 7.0 | 13.1 | 16.6 | 37.3 | ~85s | **~337s** |

Findings:
1. **The instrumentation itself is the first gap** — 45-80% of wall time
   falls OUTSIDE any `_phase()` section (drift pass, staging snapshot,
   cast-moves, salience, weave/detect cohorts, imagery, settle are all
   untimed). Widening `_phase` coverage is the prerequisite to any real
   optimization.
2. `npc_action` hit 180s on a turn with NO npc_turn receipts — whatever
   runs inside that phase besides the npc futures needs a look once the
   coverage lands.
3. Codex-side variance is large (narrate 80s vs 13s for similar-size
   briefings) — floors/tiers can't fix tail variance; concurrency and
   fewer serial cohorts can.

NEXT: (a) widen _phase coverage to every section between classify and
send; (b) re-probe; (c) then decide the optimization (the dumbfire settle
already moved the tail — the pre-send serial chain is the target).

## Second probe (2026-07-13, with cp_* checkpoints — cr-GREEN d07548e)

Two live turns, cumulative stamps (seconds):

| stamp | turn 1 (419s) | turn 2 (317s) |
|---|---|---|
| cp_classified | 10.1 | 9.1 |
| cp_movement_done | 10.3 | 9.3 |
| cp_scene_snapshot_done | 45.8 | 47.6 |
| cp_salience_done | **173.5** | **186.0** |
| cp_drift_lifecycle_done | 219.7 | 242.5 |
| cp_generator_done | 220.1 | 243.0 |
| narrate (section) | 40.1 | 15.3 |
| settle tail (post_extract+promote) | ~95 | ~19 |

THE FINDING: the snapshot→salience window costs **128-138s on both
turns** while its only timed members are tiny (npc_action ≤5.5s) — the
cost is the SERIAL chain of "cheap" cohort calls (weave_pick,
detect_events, and friends) at ~40-60s wall each on Codex. Cheap-tier ≠
cheap wall time. Second cost: the scene snapshot window (~36s), third:
drift+lifecycle (~46-56s, again serial cheap calls).

NEXT (the optimization program, when scheduled): CONCURRENCY over the
independent cheap cohorts (weave_pick / detect_events / npc_turn /
memory already run concurrent internally — lift the pattern to the
whole pre-narrate chain), not tier tuning; player-felt latency is
roughly cp_generator + narrate ≈ 260s today.
