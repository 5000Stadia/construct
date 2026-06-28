# Commitment as Effect — the climactic act is a consequence, not a grade

**Status:** SPEC for founder review, then Cx. Founder design, 2026-06-24
([[commitment-as-effect]]). Retires the vindicated/wrong commitment GRADE binary across ALL 9
shapes. Builds on conclusion-as-effect ([[pillar-conclusion-build]]), the living-world generator
([[living-world-generator]]), and [[improv-serves-the-destination]].

## The principle

The player's climactic decisive act — accuse the culprit, declare the love, execute the heist,
make the defining choice — is not graded win/loss. It produces an **effect** in the world that the
player *feels as the consequence of their choice*, ripples forward, and may carry on into the next
episode. Conclusions are effects, not verdicts.

This is **genre-agnostic**: the accuse→convict→just/unjust framing is the DEDUCTION instance of one
pattern that runs across all nine shapes. The mechanism rests entirely on machinery that is already
shape-generic (pillars, coverage, `conclusion_from_coverage`, `cost_disposition`, `_SHAPE_LINE`,
the generator), so this is wiring, not new engines.

## The four moves (every shape)

**1. GATE — lands or bounces.** You cannot land a payoff you have not earned. A commitment
terminates into a conclusion only when the shape's coverage is **complete enough to make the
payoff real**; otherwise it **bounces — non-terminal** — and the story continues ("you haven't
proven it / earned it — keep going"). This generalizes the existing `climax_ready`/`_MIN_COMMIT_TURN`
gate with a coverage-completeness requirement, and it generalizes each shape's existing "earn it"
discipline in `_SHAPE_LINE`:
- Deduction: no/insufficient proof → the constable won't arrest → back to the clues.
- Bond: a premature declaration "rings hollow and is rebuffed" → keep building.
- Contest: enter the final unprepared → crushed (or a rematch) — "victory never gifted."
- Gambit/heist: a hole in the plan → it collapses, you're caught.
- Transformation: claim the change unproven → it does not hold.

**2. EFFECT — sound or hollow.** Once it lands, the effect is the EFFECT-shape of the coverage,
which `conclusion_from_coverage` already computes per shape (flipped correctly by `cost_disposition`):
- landed on GENUINE coverage → sound (triumph / earned connection / just conviction / proven self).
- landed COMPLETE-but-UNSOUND (a red herring believed, an unrepaired misread, a betrayal, a faked
  change) → hollow (`wrong_case` / `bittersweet` / `costly_victory`).
- "Named the wrong culprit" is the deduction flavor of *landed-hollow*; "succeeded via betrayal"
  is the heist flavor; "declared on a misread" is the romance flavor.

**3. RIPPLE — persisted fallout, rule-of-cool, seeds the next episode.** A hollow/unjust landing
writes a **canon consequence** (`caused_by` the conclusion event) — the real culprit still free,
the betrayed partner, the wronged innocent, the old self resurfacing. The narrator/generator then
picks the most exemplary forward fiction from that situation (rule-of-cool): the wrongly-accused is
freed, the real culprit escalates to a **serial killer**, and the next episode opens on hunting the
new killer — who turns out to be the same man. The first mistake's repercussions running deeper
than expected — earned by the player's choice. This is the living-world generator's fallout-as-fuel
([[episodic-and-play-contracts]]); P1 already persists the consequence, P2/continuation consumes it.

**4. IRONY — the protagonist may not know.** The effect can be held from `knows:<protagonist>`
(the protagonist believes he succeeded — congratulated, the bond solid, the heist clean) while
canon holds the flaw. It surfaces now, later, or never. The belief-vs-truth gap is real (the engine
already separates the protagonist frame from canon); it is dramatic irony the system holds, not a
failure screen.

## The LLM / algorithmic split (honors [[lm-vs-algorithmic-guardrail]])

- **LLM (linguistic/creative):** extract WHAT the commitment targeted/claimed (who they accused,
  who they declared to, what they executed); render the effect epilogue + the forward hook.
- **Algorithm (rigid criteria):** the GATE (is coverage complete enough to land?), the EFFECT
  (coverage sound vs hollow; for deduction, does the extracted target match the real culprit?), and
  the just/hollow determination. These are deterministic facts we already compute.
- This **retires the vindicated/wrong grade**: the LLM `judge_commitment` shrinks from "grade the
  outcome" (which it did wrong live — graded a correct accusation "wrong" on sound coverage) to
  "extract the target." Neither side does the other's job.

## Reuses what's built
`coverage_summary` (complete/sound), `conclusion_from_coverage` (the per-shape effect shapes incl.
`wrong_case`/`bittersweet`/`costly_victory`/`triumph`), `cost_disposition` per shape, the
protagonist knowledge frame vs canon, and the generator's `caused_by` fallout. New wiring only:
1. **Proof-gate on the commitment** — land iff coverage complete; else a non-terminal "not yet
   proven/earned" bounce (with a nudge), the story continues.
2. **Target extraction + match** — extract the commitment's target (LLM), compare to the genuine
   answer (algorithmic) to set sound-vs-hollow precisely (deduction culprit; generalizes per shape).
3. **Persist the hollow/unjust landing as canon fallout** the next episode consumes, with the
   protagonist-knowledge gap for held irony.

## The careful seam (regression risk)
Move 1 changes today's "a climax commitment ALWAYS terminates" into "lands or bounces on
coverage-completeness." That touches the win/loss termination path (`terminal_outcome`, the
`arc_won`/`arc_lost` receipt) and the existing commitment tests. Mitigations: gate carefully; the
bounce is strictly non-terminal (`ended` stays False, a nudge fires); **legacy pillar-less arcs are
unchanged** (no coverage → the existing judge/terminate path). Build behind tests; do NOT retire
the win/loss receipt wholesale.

## Acceptance (per the make-it-real / per-genre method)
Per genre, live: a commitment on INCOMPLETE coverage **bounces** (story continues, nudge fires, no
terminal receipt); on COMPLETE-SOUND coverage **lands** sound (triumph/earned); on COMPLETE-HOLLOW
coverage **lands** hollow (unjust/bittersweet) AND persists a canon fallout fact (`caused_by` the
conclusion) that a next-episode build can consume. Deduction worked example: wrong-culprit
conviction → innocent freed + real culprit seeded as the next antagonist. Judge by the live
transcript + a Cx fiction read; the win is "the ending feels like the consequence of the choice."

## Build sequence
1. The proof-GATE (lands-or-bounces) + tests — the careful seam, first and alone.
2. Target extraction + sound/hollow refinement (LLM extract → algorithmic match) + tests.
3. Persist hollow/unjust as canon fallout + the protagonist-knowledge gap (held irony) + tests.
4. Per-genre live acceptance (deduction first, then out), + the next-episode seed consumption.

## Out of scope (for now)
The full forward-ripple authoring (the generator elaborating the serial-killer arc) is the
living-world generator's P2/continuation job — this spec only PERSISTS the fallout it consumes.

## #2 — a HEDGED accusation fires the conclusion (2026-06-27, live-confirmed)
A tentative resolve ("I think it was X… that's my read") used to STALL — no conclusion, no
payoff. Two-layer cause, both fixed:
1. `classify` required a DECISIVE move for `commits`; a hedged naming read as non-decisive →
   broadened so a tentative naming counts (the hedge is tone). The `kind`-gate still protects
   pure questions ("could it be X?" → kind=question → commits forced False).
2. THE REAL CAUSE (only surfaced via the LIVE run): a conclusory accusation that parses as
   `kind="declaration"` hit the canon-strict DECLARATION-DENIAL ("you can't author facts")
   BEFORE the commitment path. Fix: `if kind=="declaration" and mode=="pure" and not commits` —
   a conclusory commitment is the player NAMING their conclusion, not fact-authoring by fiat.
Downstream was already correct (complete coverage → judge+conclude; incomplete → BOUNCE
non-terminal "not yet proven"; turn-1 → not earned). Live-confirmed on the Brackenmere pillar
whodunit: hedged accusation → graded TRIUMPH epilogue. INVARIANT: the declaration-denial guard
and the commitment path both key on `kind=="declaration"`; keep the `not commits` exemption.
