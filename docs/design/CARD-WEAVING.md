# Card-Weaving Governance — the genre-agnostic mentality for serving story cards

The governing principle for how Construct weaves pre-built story elements (pillars, clues,
NPCs — "cards") into dynamic, player-led play. Founder principle, 2026-06-23
(memory `card-weaving-governance`). This SUPERSEDES the mechanical "detect dryness → force
the next card" model and the passive "PEOPLE WORTH PRESSING" briefing nudge.

## 0. The master judgment (constant, per-turn)

> **Does the improvised/embellished path make a RICHER, more interesting story in this
> setting than the pre-constructed elements would?**

A *quality* judgment, not an "are-we-on-the-rails" judgment. Serve whichever is more
interesting HERE. Sometimes the player's invention is the better story (let it run);
sometimes the pre-built card is what's missing (weave it).

## 1. The genre-agnostic invariant

Three mechanics are constant across EVERY genre; only the content varies:
1. **The master judgment** (§0) — identical everywhere.
2. **Relocatable cards woven at SEAMS** — a card's trigger is not fixed to a scripted spot;
   it is re-situated into the player's CURRENT scene at a natural seam, never by interruption.
   Cards are packages to *deliver / pepper / relocate*.
3. **The proposal FLOOR** — always pepper each card's HOOK over the run so the player's
   choices are INFORMED (genre proposes, player disposes). Only "what counts as a hook" changes.

Genre-agnosticism = the **card content** and the **shape of the floor** change per genre; the
governance does not. Two canonical instances of the SAME pattern: the D&D **tavern boxing**
tangent (serve the fun; relocate the NPC recognition to the post-fight seam — "aren't you
that person such-and-such?") and the **Sherlock suspects** (pepper each suspect's why-suspect
hook; the player may ignore a cleared suspect, but every suspect must be *presented* as one).

## 2. The invariant across all nine shapes (Cards / Floor / worked tangent→seam)

| Shape | Cards | Proposal floor (the hooks we MUST pepper) | Worked tangent → seam |
|---|---|---|---|
| **Deduction** | clues, suspects, alibis, red herrings | every suspect presented in their suspicious light | player fixates on the library's architecture → the butler, dusting nearby, lets slip "the master never let Lady Ashe near that drawer — she asked twice" |
| **Bond** | the relationship circle, vulnerability beats, the obstacle, rivals | each relationship's stakes/tension surfaced | player wins a village dance contest → after, the love-interest admits "I've never seen you let go like that" (a vulnerability beat, not a forced balcony scene) |
| **Endurance** | threats, dwindling resources, companions, refuges | each looming danger + scarcity made FELT | player detours to salvage a music box → as they dig, the companion's cough worsens and the light dies (failing-companion + night-threat raise the detour's stakes) |
| **Contest** | rivals, mentor, the standard, the personal cost | each rival's edge + the standard surfaced | player helps a kid in the gym → the champion strolls past, sneers at "the charity case" (rivalry established through the tangent) |
| **Gambit** | crew specialties, the mark's defenses, leverage, the twist | each obstacle + each turnable asset surfaced | player chats up a bartender → the bartender lets slip the mark's bodyguard has gambling debts (a leverage card, relocated) |
| **Discovery** | sites/strata, guides, competing explanations | each deeper layer + each rival theory teased | player lingers painting the alien vista → the xenolinguist murmurs the patterns they're painting *are the script* |
| **Mastery** | the material's resistances, mentor/rival/judge, the cost | the standard + each setback's lesson surfaced | player busks for coin → an old maestro notes their hands betray one untrained habit (the flaw to master) |
| **Farce** | the ensemble's cross-purposes, lit fuses, the misunderstanding | each fuse + each mistaken belief made visible and ticking | player schemes to impress a baker → the baker mistakes them for the health inspector (a fuse woven INTO the scheme, compounding it) |
| **Transformation** | catalyst/mirror, temptation-back, the one-saved, the cost-embodiment | each moral pressure surfaced; the old self's cost made felt | player indulges in a drinking contest → the one they'd save watches from the doorway, disappointed (the moral mirror, so it lands as a choice) |

Every row is the same three moves; only the cards and the floor differ. The per-genre
authoring already exists in the cast-authoring layer (it produces the cards + each card's hook).

## 3. The build shape (supersedes the dryness-trigger / passive nudge)

1. **Per-turn interestingness judgment** — is the live path richer than weaving a card now?
   (a cheap model signal, or folded into classify / a judge call). Governs let-run vs. weave.
2. **Cards as mobile packages** — pillars/clues/NPCs as typed cards carrying their HOOK (the
   "why interesting / why suspect" framing), relocatable (no fixed trigger), with state
   (un-played / hook-proposed / delivered).
3. **Never interrupt a good tangent** — weave at natural SEAMS; a flagging scene invites a
   card, a thriving one does not.
4. **Genre-proposal floor** — track each key card's hook; ensure all get peppered over the
   run so the player's choices are informed; none silently dropped. Player still disposes.
   Satisfied by LIGHT hooks at seams, not forced interrogations — so it never fights "serve
   the tangent."

## 4. Builds on existing machinery

Nudge/Rungs/threads (`navigate`/`nudge_pick`), pins (esp. escalating clue pins), the
Living-World opportunistic-DM, the STORY-SHAPES card model, narrative-framing-convergence,
and the cast-authoring layer (which authors the cards + hooks). Conclusion stays effect-of-
coverage. NEXT: Cx protocol review of this spec → build (supersede the passive `cast_threads`
nudge in `turnloop.py`).
