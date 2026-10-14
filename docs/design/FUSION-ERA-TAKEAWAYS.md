# Construct's read of "Building Into the Fusion Era" (2026-10-14)

**Source:** Kabe's doc, rev 21, read in full from the local copy `~/.config/colony/monitor/fusion-era.md`. This is Construct's reading. Anything that would change scope, order or what gets built is Kabe's call; nothing here is started.

## Where the doc's picture of Construct is out of date

- **Tests:** the doc says 1,100+ and 1,200+. Main is at 1,913 passing (272920e, today).
- **C1 is wider than porcelain v0.1.** Construct also consumes pattern-buffer's BUILD-LIBRARY (r1.9.1, pinned at c4a8eba), the beats vocabulary and the condition grammar. The condition-schema round-trip test is already owed at the next pin. That is exactly the doc's golden-file seam test, not yet written.
- **C3/C4 aren't brand new.** HOLO-EMITTER-BRIDGE slice 1 was built and is held (gate ga11d4a). Holo Emitter has built an `occurred_kinds` mapping from Construct's run 12 events.
- **The intent ruleset's first slices have largely landed.** Hedge versus condition (R38) and the walk-away question (R40) are built. I2, the knowledge check, was folded into R40 and R44, because no standalone defect needed it (`INTENT-RULESET.md`).
- **The provider.** The shipped default is the metered API key; the Codex subscription is opt-in for development. Today shows the doc's risks 4 and 5 are already live: at about 08:01 the Codex subscription began refusing gpt-5.5, the model every R20 run used. Run 14 is held on it (gate g353107).
- **Cost tracing is half there.** The timing log (`CONSTRUCT_TIMING_LOG`, `scripts/timing_report.py`) already records every model call: step, model, seconds and prompt size. It doesn't record tokens or cost.

## Takeaways, each with a recommendation

1. **"Propose the answer key before the work" is the lesson of today's run 13.** The event detector had no key and misfired, so a false climax ended chapter 1. It was found by reading the world, and the fix was measured by replaying the call (3 of 3 misfires before, 0 of 3 after, the real escape still firing). *Rec:* make replay keys standard. Each detector or classifier cohort gets a small set of recorded calls with known answers, rerun at every model or prompt change. That also answers the doc's model-drift risk; today's gpt-5.5 to gpt-6-astra switch is the first case.
2. **Felt quality has no key except Kabe.** The fiction ledger (`eval/10`) is graded by the operator, which is me. *Rec:* turn the ledger into the doc's "founder-graded transcripts as durable verdicts": Kabe grades a few R20 transcripts once, and the grades are stored where builders can't edit them. Needs his time, so it's his call.
3. **Cost per turn: directive 2 is cheap now.** *Rec:* add input and output tokens and a price to each call in the existing timing log. One small spec; no run is needed to build it, and the next run fills in the number.
4. **Cohort routing (directive 3).** The tiers already split cheap from main, and the effort study showed effort "none" kept 94% agreement at 2× the speed. *Rec:* classify each cohort by its contract test, then by size; local models wait on the gateway.
5. **C6 gateway (directive 4) and the artifact channel.** This is the doc's biggest lever and a large change to the provider layer. *Rec:* Kabe decides when. It reorders the roadmap ahead of more R20 polishing.
6. **Decompose run_turn (directive 6).** `turnloop.py` is 8,007 lines. The answer key exists: the suite plus byte-identical turn traces. *Rec:* a good Codex job under this week's token limit, but it reshapes code under review and the order is Kabe's.
7. **Risk 9, the research loop, is visible in R20.** Thirteen runs, each finding a deeper layer: twins, the detector, the seam. *Rec:* give R20 an explicit closing gate (five criteria plus "the conclusion is genuine") and stop adding criteria. The remaining twin fixes belong to pattern-buffer's R55, so R20 can close without them if Kabe agrees.
8. **The ten-second proof for Construct is continuity:** the drawer still open, the lie still believed. Today's object-permanence breaks (the chain, the hold) attack that proof directly. *Rec:* rank R55 adoption and the chapter seam (carried state, time jump) above new features.

## Open for Kabe (from the doc, as they touch Construct)

- Whether the C6 gateway and the published-artifact port move ahead of further R20 work.
- The flagship world for the first public build (the doc suggests The Rain in Bluegate Yard).
- Whether he'll grade a founder transcript set, and when.
- Which model Construct uses on the subscription now (gate g353107).
