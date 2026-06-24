# Narration Discipline — improv may become THE PATH; dead-end clue-leads must not be minted

**Status:** SPEC for Cx review (design round). Founder-diagnosed across live runs (castdemo
bell-flag tangent; the EXAMINE acceptance run `examinewho`). The recurring blocker on live
SOLVES: the narrator's rich atmospheric improv manufactures *clue-shaped* investigative leads
that aren't authored clues, and the player chases the noise away from the authored spine. The
mechanisms (ASK/EXAMINE/discovery/conclusion-as-effect) are all built + correct; THIS is what
keeps cases from solving live. Tenet-sensitive — must NOT over-rein the improv the founder values.

## The evidence (examinewho, 2026-06-24)
`means` was coverable ONLY by examining the doctor's bag (an object scrutiny clue). The bag was
foregrounded perfectly ("a black leather doctor's bag, brass catches shut… Dr. Ames watches the
bag, one hand near it but not touching it") and its hook was peppered. Yet over 18 turns the
agent inspected a **wet ring**, a **missing glass**, a **back door**, a **hidden stair** — all
NARRATOR-IMPROVISED, none authored — and never the bag. Conclusion: `partial` (means never
delivered). The improvised details PRESENTED AS LEADS and out-competed the authored clue.

## The governing lens (founder, 2026-06-24 — NOT "rein the narrator")
Rule-of-cool + the most engaging experience, with the pre-written shape as the BASELINE, not a
rail ([[improv-serves-the-destination]]). Improv from narrator AND player is necessary and can
IMPROVE the story. The test for any improvised thread:
- **Serves / enhances the conclusive direction →** it's superior — EMBRACE it, let it BE the path
  even when it circumvents an authored clue, MAKE IT REAL (resolve-and-commit), and let it
  influence the (ambiguous) destination. Retroactively consider how it enhances the conclusion.
  NEVER railroad the player back to the pre-written clue.
- **Leads nowhere (a dead end) →** it should have been CURTAILED IMMEDIATELY, PRIOR TO CREATION.
  The failure is minting a dead-end, NOT the act of improvising.

So the examinewho wet-ring/hidden-stair miss reframes: the bug was the narrator creating threads
that led NOWHERE (and an implicit expectation that the player return to the bag) — NOT that it
improvised. The right behavior was either to make the wet ring SERVE the means/destination (the
player chose it — let it become a real lead) or not surface it as investigable at all.

## The THREE-LANE judgment (Cx 086 — the unifying model, keep it near the lens)
Every player move that goes off-script falls in one of three lanes:
1. **Exploratory / circumventing** (chases the wet ring, a back stair, an unexpected witness
   angle) → if it serves/can-enrich the conclusive direction, ADAPT it through the host/arc
   doorway (genuine lead · false lead + debunker · `plot:` repair · concrete world-consequence).
2. **Dead-end clue-shaped noise** (narrator minted an affordance the arc won't make pay) →
   CURTAIL before creation (the post gate stops canon pollution but can't un-show prose).
3. **Destructive / world-breaking** (Sherlock murders a witness, burns the evidence room, frames
   an innocent) → NOT a make-it-real candidate. If irreversible, a dramatic CONFIRMATION beat
   first; if the physical ATTEMPT is uncertain, the resolution deck adjudicates whether it
   SUCCEEDS — but once it lands the world reacts realistically (jail, horror, altered NPC
   knowledge, a compromised conclusion). This lane preserves causality; it is NOT railroading or
   punitive correction. Keep "does the murder SUCCEED?" (deck) separate from "does the story
   RESCUE Sherlock?" (never).

## The design — two coordinated mechanisms (Cx 085 GREEN-shape)
1. **MAKE-IT-REAL = a named HOST/ARC adaptation doorway, NOT narrator permission (Cx 085 #1).**
   The narrator NEVER self-promotes a clue-shaped invention into evidence or the hidden answer
   (the post-render gate + `arc_protected_keys` keep load-bearing facts protected; the narrator
   even holds the destination as a DM card in hold mode — "no self-promotion" is load-bearing).
   Instead a host op — **`adapt_pursued_improv_thread`** (host-side, fail-open, ≈ arc-repair +
   clue-delivery + the generator's pacing/provenance):
   - **Input:** the player pursued an un-authored clue-shaped detail + the active arc/pillars/
     cast/player frame.
   - **Decision:** map it to an EXISTING pillar as a genuine clue · or as a false/red-herring
     clue WITH a reachable debunker · or supersede/repair `plot:` structure · or DECLINE → treat
     as atmosphere.
   - **Writes:** generated/audit rows → `plot:`/`session:`; a learned clue fact →
     `knows:<protagonist>` ONLY through the same `learn_clue_items` shape; canon ONLY for concrete
     world-consequences with provenance/`caused_by`.
   - **Guards:** solvability lint/reachability, red-herring-debunker rule, an adaptation BUDGET,
     NO raw narrator prose as authority, NO hidden-answer fact unless structurally earned.
   This is NOT a new PB primitive — a host operation over the existing frame/write discipline.
2. **CURTAIL-BEFORE-CREATION = render-time affordance hygiene (Cx 085 #2).** The post gate can't
   stop the player chasing prose they already saw, so the discipline is at NARRATION time:
   sensory TEXTURE is free ("the wet ring catches the light"); but DISCREPANCY/CAUSALITY/SECRET/
   ROUTE language is a LEAD ("a fresh wet ring with no glass nearby") and must either pay toward
   the destination (via the adapt doorway) or not be minted that way. Atmosphere/incidentals/
   character-knowledge/player-tangents stay free.

### Influenceable destination — BOUNDS (Cx 085 #2/answer 3)
- **Flex FREELY:** the route to the conclusion, the clue trail, the interpretation, the location
  of the pivotal beat, the conclusion's emotional coloring. A `plot:` supersession that PRESERVES
  the conclusion shape + leaves an audit trail (like arc repair) is also fine.
- **GATED (auditable `plot:` supersession only, pre-terminal, with receipts/lint):** an improvised
  wet ring becoming a NEW means clue is fine; becoming a new REQUIRED pillar or CHANGING the
  culprit/answer is arc-repair-class — never a silent mutation.
- **NEVER:** silently add/re-weight required pillars or mutate the hidden answer AFTER the player
  has begun solving against it ("the answer moved because the player looked hard" breaks fair-play).

Both mechanisms governed by the card-weaving MASTER-JUDGMENT ([[card-weaving-governance]]), applied
INTUITIVELY and PER-STORY. **And the hard boundary ([[improv-serves-the-destination]] counterbalance):
make-it-real does NOT rescue DESTRUCTIVE choices — a player can ruin it; the world responds
realistically + the conclusion-as-effect reflects the wrecked state (Sherlock→jail).**
**Acceptance asserts STRUCTURE (Cx 085), not just transcript feel:** the adapted clue appears in
`trace.learned_clues` or an adaptation receipt; `coverage_summary` goes non-`partial` by genuine
or false coverage; `trace.quarantined` shows no protected leakage; generated/repair rows stay out
of canon/player-frame except via the authorized `learn_clue_items` write.

## Where it lives
The render leash / narrator briefing directive (runs every turn) — likely the same surface as
`RENDER_LEASH`/the narrator license in `cohorts.py`, + a briefing line foregrounding the authored
live threads. Coordinates with the gated-ingest momentous gate (a manufactured "lead" about an
arc-adjacent entity is already quarantine-eligible; this adds the NARRATION-side discipline so it
isn't surfaced as a lead in the first place).

## Acceptance
Re-run `examinewho` (and a staged whodunit): when the agent pursues an improvised detail (the
wet ring), it either RESOLVES into something that serves the means/destination (the chase pays
off) or was never surfaced as investigable; the case reaches a non-`partial` conclusion via
WHATEVER path the player took (not only the pre-written one); and the player is NEVER railroaded
back to the authored clue. Judge by the live transcript + a Cx fiction re-score vs the 7.2
baseline (fair-play + spine + immersion should rise). Risk-check: the prose stays rich and the
improv stays FREE — the win is "no dead-end trails / chosen path pays off," NOT "less improv."

**Second acceptance probe (Cx 086 — the destructive lane):** a staged whodunit where the player
CONFIRMS then does something ruinous (murders a witness / burns the evidence room). Expected:
NO original-case rescue; concrete fallout enters state (altered NPC knowledge, a procedure
failure, a `caused_by` consequence); the terminal/conclusive scene reflects the BROKEN case
(not the intended mystery). This proves the three-lane judgment, not just the embrace path.

## Build sequence
1. `adapt_pursued_improv_thread` host op (decision-application + lint/budget/writes) + unit tests.
2. The render-hygiene directive (texture-free / clue-shaped-affordance-needs-payoff).
3. Turn-loop detection (player pursued an un-authored clue-shaped detail) + the destructive-lane
   routing (confirmation beat / deck-for-attempt / world-reacts).
4. Live acceptance (examinewho embrace + the ruinous-choice probe) + a Cx fiction re-score.

## Out of scope
Suppressing PLAYER-volunteered off-story tangents (those stay served — the date with the
innkeeper's daughter is good improv, judged by the same master-judgment).
