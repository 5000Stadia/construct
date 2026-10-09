# R20 acceptance: the displaced-Ironhold probe (2026-10-08)

The WORLD-GROWTH acceptance pass the roadmap left open (`NEXT-UP.md`, "WORLD-GROWTH acceptance + latency"). Script: `scripts/displaced_ch2_probe.py`, on the subscription wire (CodexProvider). No metered calls. The build is fresh, so the probe exercises today's main (bce91b2). Logs are on `/media/k/Blank/construct-scratch/`.

## Pass mark, set before the run

The probe passes only if every one of these holds:

1. **Chapter 1 lands a conclusion** within its 11-turn schedule (`concluded=True`).
2. **The world grew where the player walked.** Chapter 1 ends in a place that did not exist in the pristine Ironhold world, a place minted in play, not one of the prison's built places.
3. **Chapter 2 opens where chapter 1 ended.** `CH2 OPEN STATE` equals `CH1 END STATE`, with no snap-back to Ironhold.
4. **No broken turns.** No chapter-2 `ENGINE ERROR`, and no turn returns empty prose.
5. **No critic breaker on the WHERE bar.** No filed note reports a teleport or snap-back. Notes on the goal-pivot and style bars are recorded as fiction-quality findings, not failures.

It fails if any of 1–4 fails, or if 5 does. If it fails, the fix goes on a branch and merges when green, and the probe re-runs.

Latency is recorded, not judged: the per-turn wall time and the `cp_*` checkpoints from `CONSTRUCT_MECHANICS_LOG` feed the R23 breakdown below.

## Result

(to be filled in after the run)
