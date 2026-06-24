# Action Resolution — assured success vs the 4-tier fail-forward check (design)

**Status:** DESIGN-FIRST, founder-spec'd (2026-06-22). Awaiting greenlight before build.
A core mechanic — how EVERY player action resolves. Serves the [[improvisation-north-star]]
(adaptable improv) by deciding *when* the world resists and *how* uncertain outcomes land.

## 1. The principle — assured vs uncertain
- **ASSURED → NO test, just succeed.** If the outcome is commonplace/assured for a character
  of that nature — especially if their DESCRIPTION makes them proficient — they simply do it.
  No luck/skill roll. A reasonable action that would only fail *surprisingly* just succeeds
  (a custodian files the form; a long-time resident walks to a known place; a trained guard
  climbs a low wall). **Proficiency overrides uncertainty:** if the character should be able
  to do it, no test even when it'd be dicey for someone else.
- **UNCERTAIN → a test.** When the action meets real RESISTANCE in the world or a notable
  UNKNOWN about success — combat; a leap over a pit that may be just out of reach; a lie that
  may not convince — resolve it with a draw. Framed simply, this covers ALL cases: *the player
  attempts something with resistance or a genuine unknown.*

## 2. The 4-tier outcome (only when a test fires) — fail-forward, never flat
Drawn from a fixed distribution; every result carries a twist (the engine's "yes/no, AND…").
**Skewed to success (founder, 2026-06-22): a character who even gets a test should usually
achieve their narratively-unique thing — just with texture.**
| % | Tier | Shape |
|---|---|---|
| 10% | **terrible failure** | fails + a NEGATIVE CONSEQUENCE |
| 20% | **failure** | fails + a NEW UNEXPECTED OPPORTUNITY |
| 55% | **success** | succeeds + an UNEXPECTED NEGATIVE COST |
| 15% | **complete success** | succeeds + an ADDITIONAL BOON |
(70% lands "success-ish", 30% "failure-ish" — but never a clean nothing; always a complication.)

## 3. No extra roll-call: the pre-rolled outcome deck (founder, latency-conscious)
The "roll" must NOT cost a per-check model call. So:
- At game start (and whenever exhausted), build a **shuffled bag of 100 tiers** honoring the
  ratio exactly: 10 terrible · 20 fail-opportunity · 55 success-cost · 15 crit-boon, shuffled.
- Persist it on the **session frame** (`session:resolution_deck` + a cursor) — so it's
  deterministic/replayable and survives re-entry.
- Each test **pops the NEXT tier** in order. When the bag runs out, generate a fresh shuffled
  bag. Pure host-side draw — zero model calls, exact distribution over each 100.

## 4. Who decides assured-vs-test — fold into `classify` (no extra call)
`cohorts.classify` already runs every turn (cheap). Extend its ACTION verdict with:
- `needs_test: bool` — does this attempt have real resistance/uncertainty, given the
  character's proficiency (role/description) + the world's pushback?
- `uncertain_of: str` — one line: what's at stake / what resists (for the narrator).
The judgment reads the protagonist's role/sheet so PROFICIENCY can wave off a test. No
separate cohort, no added latency.

## 5. Tier → narration
- `needs_test=false` → narrate the assured outcome (today's path).
- `needs_test=true` → pop a tier → add a RESOLUTION directive to the narrator briefing:
  "the attempt resolves as **<tier>** — render it: <tier gloss>, re: `uncertain_of`." The
  narrator improvises HOW; the tier dictates WHAT (succeed/fail + the twist). The outcome
  commits to canon via the existing render mirror (so the cost/boon/opportunity becomes real).
- `TurnTrace.adjudication` records `assured` | `test:<tier>` for the debug/audit surface.

## 6. Fits all situations
- **Combat / extended challenges** = a sequence of uncertain attempts, one draw each, unfolding
  over turns (an exchange at a time) — not one roll for a whole fight.
- **Social** (a lie), **physical** (a jump), **mental** (a deduction under pressure) — same one
  mechanism; the difference is only `uncertain_of`.

## 7. Open questions (for sign-off)
- **Visible dice or pure narrative?** Lean: PURE NARRATIVE — the player never sees percentages
  or "you rolled a 12"; the outcome arrives as prose (the success-with-cost simply *happens*).
  Matches the prose-first ethos. (Confirm — some players love seeing the dice.)
- **Deck size 100** (founder's number) — keep; refill on exhaust. Reasonable.
- **Granularity:** one draw per *meaningful* uncertain attempt (not per trivial sub-action) —
  the `needs_test` judgment gates that. Agree?
- **Tuning the bias:** the 15/35/35/15 is symmetric-ish; is it global, or could a very-proficient
  character shift the odds (e.g. drop the terrible-failure share)? v1: flat for everyone who
  gets a test at all (proficiency already decides *whether* to test). Revisit later.

## Build sketch (on greenlight)
1. `resolution.py` — the deck: build/shuffle (seeded, persisted), `draw_tier(session)` →
   tier, refill-on-empty. Pure, unit-testable.
2. `cohorts.classify` schema += `needs_test` + `uncertain_of` (+ feed it the protagonist
   role/proficiency).
3. `turnloop.run_turn` — on an action with `needs_test`, draw a tier → RESOLUTION briefing
   directive; else assured. Trace it.
4. Tests: distribution holds over 100 draws; refill; proficiency→no-test; tier→directive wiring.
