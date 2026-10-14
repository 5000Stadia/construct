# Hedge versus condition: a deferred conclusion is a pending decision (R38)

**Status:** spec r1, 2026-10-13, for cr review. Not built.
**Source:** ruleset slice I1 / IR-18 (Kabe's intent ruleset, adopted 2026-10-13; `INTENT-RULESET.md`), and the verified F3 defect.

## The facts

- **Classify's `commits`** (cohorts.py:140-148) is set for a conclusory move. The prompt (cohorts.py:2721-2729) says: "A TENTATIVE or HEDGED naming STILL counts ('I think it was X', …) — reaching for the answer IS the commitment; the hedge is tone." That rule is right for hedges (COMMITMENT-AS-EFFECT; memory: hedged-commitment-conclusion).
- **It has no notion of a condition,** so "I'm fairly sure it's Ellis, but first I need Quincy on the clock" most likely sets `commits=true`. The move then lands, or bounces on coverage, although the player said not yet.
- **The only counter-text is `decisive_note`** ("A move that only prepares, asks, or lingers is not a commitment", cohorts.py:2634-2640). It is injected only near the climax (turnloop.py:2528-2532), where it conflicts with the hedge rule.
- **`commits` flows into:**
  - the stage gate (turnloop.py:6666);
  - the coverage bounce (6700);
  - the judgment and terminal path (6714);
  - the loss result-event (6272);
  - the pure-mode declaration exemption (4631: a conclusory declaration is not denied as fact-by-fiat).

## The rule

**1. Classify reports the shape; the host decides.** CLASSIFY_SCHEMA gains:
- `commit_condition`: one of
  - `none`: plain ("It was Ellis. Arrest him.");
  - `hedge`: tone only ("I think it was Ellis");
  - `precondition`: the player will commit after doing something first ("…but first I'll ask Quincy about the clock");
  - `conditional`: commit if something proves true ("If Quincy confirms the clock, it's Ellis").
- `commit_precondition`: the condition as one short clause, for precondition or conditional; otherwise empty.

**The prompt's hedge sentence gains one sentence:** "But a conclusion the player DEFERS ('but first…', 'once I've…', 'if X confirms…, then…') is not a commitment yet: still set `commits` and `commitment`, and set `commit_condition` to precondition or conditional, with the condition in `commit_precondition`." `decisive_note`'s "only prepares" sentence then agrees with it.

**2. The host gate** (intent.py, where `commits` is parsed):
- `Intent.commits` (the effective flag) is true only when the model's `commits` is true **and** `commit_condition` is `none` or `hedge`. An unknown or missing value counts as `none`, so today's behaviour holds for any old or stub response.
- `Intent.conclusory` keeps the model's raw flag for the one place that needs it: the pure-mode declaration exemption (turnloop.py:4631). A conditioned accusation phrased as a declaration is still not denied as fact-by-fiat.

**3. A conditioned commitment becomes a pending decision.** On a turn where the model said `commits` with a precondition or conditional:
- the turn writes `session:pending_decision` · `record`, a JSON literal `{commitment, condition, turn}`, at `turn_time(turn)`. The latest wins; there is one pending decision at a time.
- **Nothing else happens:** no stage gate, no bounce, no judgment, no receipt, no loss event.

**4. The briefing carries it, so the world can bring it back.** While a pending decision stands (written at or after the episode start), the narrator's briefing carries:

> PENDING DECISION: the player means to {commitment} once {condition}. Never decide it for them. When the condition is settled in the fiction, a present character may invite them to say it.

That is the ruleset's "a resolved precondition surfaces the decision, never fires it". The surfacing is the narrator's in-world invitation, with no extra call.

**5. It clears** when a later turn's effective commitment goes through the gates (lands or bounces), or when a newer pending decision replaces it. A new chapter's briefing ignores one written before its episode start (`_episode_since`).

## Not in scope

- **Recording the condition as a question in an intent frame** (R41, I3).
- **Detecting when the condition is satisfied.** The narrator's invitation is enough for now, and a model judging "is the precondition met" would add a call and a misread risk.

## Tests

1. **Parse:** a verdict with `commits=true` and `commit_condition=precondition` gives effective `commits` False and `conclusory` True. With `hedge` or `none` it gives True. Missing or garbage gives True (legacy).
2. **The Quincy turn** (stub classify, required-pillar arc with coverage complete): "fairly sure it's Ellis, but first Quincy on the clock" makes no stage-gate call, no bounce, no judgment and no receipt. `session:pending_decision` holds the commitment and the condition.
3. **The briefing:** the next turn's briefing contains the PENDING DECISION line, with the commitment and the condition.
4. **The later commit:** a later plain "It was Ellis" lands as today, and the pending decision no longer appears in the briefing.
5. **Pure-mode declaration:** "It was Ellis — but first I'll check the clock", classified as a declaration with a precondition, isn't denied as fact-by-fiat, and becomes a pending decision.
6. **The hedge is unchanged:** "I think it was Ellis" (hedge) commits exactly as today (the existing hedged-commitment tests pass unchanged).
7. **Episode scope:** a pending decision from before the episode start isn't in a new chapter's briefing.
8. **The full suite.**
