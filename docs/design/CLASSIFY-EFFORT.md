# The engine classifier at effort "none"

**Status:** spec r1, 2026-10-13, for cr review. Not built. It replaces TURN-CLASSIFY-ONCE r1 (c718141), which is parked: cr RED, and see "Why not batching" below.
**Source:** R20 run 10's timing log (eval/12), and two measurements on run 10's played world, archived at `/media/k/Blank/construct-scratch/effort-probe/`.

## The facts

- **The engine's lifetime classifier** (prompts starting "Classify the lifetime") is routed to construct's cheap tier (`_CHEAP_ENGINE_PREFIXES`, provider.py:198). On this account the cheap tier is `gpt-5.5` at effort `low`, set through `HOLODECK_CODEX_CHEAP_MODEL`, because `gpt-5.4-mini` is refused (eval/12).
- **Run 10 made 109 classifier calls in 20 turns:**
  - 69 inside turns, while the player waits: 247 s, 16% of the 1,551 s of turn time;
  - 40 in the deferred settle, while the player reads: 319 s.
- **`gpt-5.5` rejects `minimal`** ("Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'").
- **Measured "low" vs "none"** on real engine prompts captured from run 10's world (rows written during play, guardrail attributes excluded):

| Path | Rows | Agreement | Median latency, low → none | Mean latency, low → none |
|---|---|---|---|---|
| Per-row prompts | 45 | 39 (86.7%) | 2.65 s → 1.37 s | 4.20 s → 1.60 s (low's max was 65 s) |
| **Batched prompts** (the path play uses, 3–8 rows each) | 51 | **48 (94.1%)** | 4.36 s → 2.31 s | 4.25 s → 2.64 s |

- **Every disagreement leans away from the costly error:**
  - On the batched path, the verdict mix is identical in both arms (STATE 39, CONSTITUTIVE 9, DISPOSITIONAL 3). Of the 3 disagreements, "none" says CONSTITUTIVE once, for a pouch listed as its own instrument, which is not a movable fact.
  - On the per-row path, all 6 disagreements are low CONSTITUTIVE → none STATE.
  - "None" never called a location, a state or a held object permanent. A wrong CONSTITUTIVE on a movable fact is the costly error; a wrong STATE only means a later row can supersede the fact.
- **All 20 batched responses at both efforts were schema-valid,** with a complete index set.

## The rule

- **Classifier calls only.** An engine prompt starting `Classify the lifetime`, on the cheap tier, on a model in `_NONE_EFFORT_MODELS = {"gpt-5.5"}`, uses effort `"none"`.
- **Everything else is unchanged:**
  - extraction ("Extract world-state") stays on the cheap tier's effort;
  - a model not in the set keeps the tier's effort;
  - "none" is applied only where it was measured.
- **One knob,** `HOLODECK_CODEX_CLASSIFY_EFFORT` (default `none`), reverts it without code (`low`). The legacy global override env (`_reasoning_override_env`) still wins over everything, as today. The narrator's high-effort floor is untouched.
- **`_EFFORT_RANK`** gains `"none": -1`, so rank comparisons stay total.
- **Where:** the gpt-5 effort branch (provider.py, around line 478), as one table lookup keyed by the prompt prefix the router already uses. There's no second dispatch mechanism.

## Why not batching (TURN-CLASSIFY-ONCE)

- **The settle half saves nothing a player feels:** it runs while they read.
- **The in-turn half needs an engine capability that doesn't exist:** immediate guardrail classification inside a BUILD-SESSION-V1 session (cr P1 on r1). pattern-buffer has been asked.
- **Effort is independent of call count,** so the two stack if batching returns.

## Expected

About 1.3 to 2 s less per classifier call. Over run 10's 69 in-turn calls that's roughly 1.5 to 2.5 minutes across 20 turns, plus the removal of low's long-tail stalls (65 s once). Settle time shrinks by about as much, out of the player's sight.

## Tests

1. **Classifier routing:** a "Classify the lifetime" prompt on the cheap tier with model `gpt-5.5` sends `reasoning.effort = "none"`. The test inspects the request body with a stub transport.
2. **Extraction unchanged:** an "Extract world-state" prompt on the same provider sends the cheap tier's effort (`low`).
3. **Other models:** the classifier prompt with cheap model `gpt-5.4-mini` sends `low`.
4. **The knob:** `HOLODECK_CODEX_CLASSIFY_EFFORT=low` sends `low`; the legacy global override env wins over both.
5. **Floors untouched:** a narrator prompt still floors at `high`, and a `deliberate` main call still floors at `medium`.
6. **The full suite.**

## Acceptance in play

The next R20 run, when Kabe or the monitor approves one, checks two things (the second read from its played world afterwards, as the probes did):
- each classifier call's latency, against run 10's;
- the play-time verdict mix (STATE / CONSTITUTIVE / DISPOSITIONAL), against the measured baseline.

A rise in CONSTITUTIVE on movable attributes (on, in-like, held, state) reverts the knob.
