# The engine classifier at effort "none"

**Status:** spec r3, 2026-10-13, for cr review. Not built.
- r2 (cr RED on r1): acceptance is row-level and comes before any user play; the knob ships defaulting to `low`.
- r3 (cr RED on r2): the movable set takes its containment part from the audited world's own semantics, and fails closed. It replaces TURN-CLASSIFY-ONCE r1 (c718141), which is parked: cr RED, and see "Why not batching" below.
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
- **One knob,** `HOLODECK_CODEX_CLASSIFY_EFFORT`. **r2: it ships defaulting to `low`, so merging this changes nothing.** `none` is switched on only for the disposable-world audit below. The default flips to `none` in a separate one-line commit, and only after that audit passes. The legacy global override env (`_reasoning_override_env`) still wins over everything, as today. The narrator's high-effort floor is untouched.
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

## Acceptance: row by row, before any user play (r2)

cr's point (RED on r1): an aggregate verdict mix can hide a wrong row behind an offsetting one. Worse, a movable fact wrongly made permanent is already in the world by the time a post-play check runs, and flipping the knob back can't repair that row. So the knob is **not** a protection. The protection is that `none` never reaches a user's playthrough until these steps pass:

1. **Corpus replay, row-level (done before this spec; repeatable).**
   - The 10 batched prompts (51 rows) and 45 per-row prompts captured from run 10's world are replayed at `low` and at `none`, with every (row, verdict) pair recorded.
   - The corpus holds play text, so it stays untracked at `/media/k/Blank/construct-scratch/effort-probe/`.
   - The replay script lands as `scripts/classify_effort_audit.py`. It takes a corpus path; no corpus is committed.
   - **Pass:** no row whose attribute is in the movable set gets `CONSTITUTIVE` at `none`.
   - **The movable set (r3)** is the union of two parts:
     - **The audited world's own containment family,** read from that world: `world.semantics.containment_family()`. These are the engine's built-ins plus every attribute declared `relation_family=containment` (patternbuffer semantics.py:340-363). A handwritten list would miss a declared containment attribute such as `stowed_at`.
     - **Construct's conservative extras:** `at`, `near`, `position`, `formerly_in`, `held*`, `carried*`, `state`, `condition`, `status`.
   - **Fail closed:** if the world's semantics can't be read, the script exits non-zero and reports no pass. It never falls back to the extras alone.
   - **For the corpus replay,** the corpus carries a manifest naming its source world, and the script opens that world (read-only, from the Blank drive) to resolve the family.
   - **This is a dev-tool coupling** to an engine object that isn't porcelain (`world.semantics`), documented in the script. No shipped code uses it; the pinned porcelain has no containment-family read. Every per-row delta from `low` is listed in the build note.
   - **Today's result:** pass. There were 3 batched deltas and 6 per-row deltas. The one `none`-CONSTITUTIVE delta is `obj:stamped_nail_pouch · instrument`, which is not in the movable set.
2. **A disposable-world turn trace.**
   - The next R20 probe run sets `HOLODECK_CODEX_CLASSIFY_EFFORT=none`. It needs Kabe's or the monitor's yes, as every run does. Its world is a probe world, never a user's.
   - Afterwards, `scripts/classify_effort_audit.py --world <played world>` lists **every** row written during play that was classified `CONSTITUTIVE`, with its entity, attribute, value, turn and confidence. Each one is audited by hand in the eval note.
   - **Pass:** no movable-set row is `CONSTITUTIVE`, and every other `CONSTITUTIVE` row is defensible on its own terms.
   - **Read path:** the world's per-row durability, through a porcelain read if the pinned engine exposes one. Otherwise through a read-only query of the engine's classification sidecar, documented in the script as a dev-tool coupling to the engine's file layout, never used by shipped code.
3. **Only then** a one-line commit flips the default to `none`, citing both reports.
4. **After the flip,** each later R20 run keeps the same row-level `CONSTITUTIVE` listing in its eval note. The aggregate mix is supplementary only.

A guard that prevents a wrong class before it is stored would need an engine boundary. That is not proposed here; the residual risk is model drift on future prompts, which the row-level listing in step 4 watches.

## Tests (r2 additions)

7. **The real routing prefix:** the existing real-PB routing test (the cheap-prefix dispatch) also asserts that the engine's actual classifier prompt, from the pinned engine, starts with the prefix this rule keys on. A change in the engine's wording fails it.
8. **The default:** with the knob unset, a classifier prompt on `gpt-5.5` sends `low` (the shipped default in r2). With it set to `none`, it sends `none`. The global override still wins, and the narrator's high floor applies after it.
9. **The audit script** on a synthetic world fixture:
   - a movable `in` row stored as CONSTITUTIVE is reported;
   - a `kind` row is not flagged;
   - **(r3)** the fixture declares `attr:stowed_at · relation_family · containment`, and a CONSTITUTIVE `stowed_at` row makes the script fail;
   - **(r3)** a world whose semantics read raises makes the script exit non-zero, never pass.
