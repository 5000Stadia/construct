# Build timing baseline (2026-10-13)

The first build measured with the timing log (`CONSTRUCT_TIMING_LOG`, merged at 86b27e8). Approved by the monitor (n732fcb): one build-only world build, no play, Codex subscription only.

- **Seed:** R20's Ironhold seed, built under the scratch name `timingprofile` with `scripts/`-equivalent arguments.
- **Main:** at 11540f9, engine pattern-buffer 9e0620f.
- **Models:** `CONSTRUCT_PROVIDER=codex`, both tiers on `gpt-5.5`; this account refuses `gpt-5.4-mini`.
- **Result:** viable, published in **474 s** with 27 model calls.
- **Archive:** `/media/k/Blank/construct-scratch/profile1` (timing.jsonl, build.out, report.md and the world). One complete run: per the reporting rule, figures are this run's, not a distribution.

## What the build spends its time on

- **Fact extraction (Stage 1): 104 s wall.**
  - 8 chunks run in parallel, 8 in flight. Each averages 51.5 s (p90 65.9 s); the slowest took 101.5 s including one schema re-ask.
  - The stage waits for the slowest chunk.
  - All 8 calls run on the "cheap" tier, which is gpt-5.5 here.
- **Story authoring: 120 s.** One main-tier call (`sty`).
- **Hidden arc (Stage 4): 96 s, serial.** The cast author (`cas`) takes 57 s with a 23k-character prompt; the arc (`arc`) takes 16 s.
- **Back-of-the-book premise: 45 s** (`prm`, 42 s).
- **World laws: 29 s** (`law`) plus a 5 s critic (`lwc`).
- **Character knowledge (Stage 5): 22 s wall** for 33 s of calls (`skn` ×5, 3 in flight; `rel`).
- **Flavor: 20 s. Introduction: 9 s.**
- **Identity reconcile (Stage 2): 11 s, with no model calls.** No merge-gate pair arose in this build. The identity checks run as code inside other stages.
- **Literal categorization: about 9 s in all** (`gnr`, `gty`, `dpl`).

The Stage 0 rows read "story 0 s, laws 154 s" because the story's progress line is printed before the laws are authored. Both calls (`law` 29 s and `sty` 120 s) land under the laws row. This is a label-order quirk, not a cost.

## Findings

1. **Build time is not in identity repair or literal categorization here.** Together they cost about 20 s. The registry-first redesign (SEEDING-REGISTRY-FIRST.md) is justified by correctness: fused and split characters, the `_2` remaps, the Rex test. It is not justified by build speed. Its speed effect is limited to extraction output.
2. **The levers, largest first:**
   - **Extraction model and effort.** Each chunk spends about 50 s on a large model at low effort; latency follows output and thinking tokens (pattern-buffer's profile). A faster model for extraction, if the account allows one, plus smaller chunks for more parallelism, targets the 104 s.
   - **Parallelize the stages after the arc.** Premise (45 s), introduction (12 s), flavor (21 s) and character knowledge (22 s) run one after another, but none needs another's output. Run concurrently, roughly 100 s of wall time becomes about 45 s.
   - **Effort per stage.** The premise (a blurb) spends 42 s; flavor 20 s. These are chore-class judgments run at main-tier deliberate effort.
   - **Story authoring (120 s).** Only effort or model choice moves it.
3. **A rough target:** about 250 s with the first three levers. Each change is measured with the same log before any claim.
