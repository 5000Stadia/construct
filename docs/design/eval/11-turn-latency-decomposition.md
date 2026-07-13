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
