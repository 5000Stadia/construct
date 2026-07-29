# The Resolution Fan — a chapter's authored, closed set of endings

> # ⏭️ THIS IS THE NEXT HEADLINE BUILD (see [NEXT-UP.md](NEXT-UP.md))
> §5b (chapter-boundary reshape) is the one large net-new build left after the
> 2026-07-29 button-up. **A broad design pass must settle the open forks BEFORE
> implementation is pieced out** — §5a tolerance-window + reshape randomness, the
> §5b register dial (G4 defer-vs-build), and composite game-type interplay. The
> audit ([STRUCTURE-VALIDATION-AUDIT.md](STRUCTURE-VALIDATION-AUDIT.md)) already
> narrowed the build to G1 + G2/G3 on existing blend machinery. Then: spec → cr →
> build → the `genreshift` probe as acceptance.

**Status:** DIRECTION (founder, 2026-07-14) — banked, host-side, not yet built.
Extends [CONCLUSION-AND-OUTCOME.md](CONCLUSION-AND-OUTCOME.md): where that doc has
ONE authored conclusive event + a free runtime OUTCOME judgment, this authors the
whole **fan** of endings at creation time and reduces the runtime judgment to a
**bounded selection** over that fan. Directly resolves the CONCLUSION-AND-OUTCOME
"one risk" (a non-deterministic LLM outcome verdict) by closing the outcome space.

Companion to [chapter ends on climax, not turn-count] (the Ruling-1 review, same
session): the fan is *what* an ending is; that ruling is *when* one fires.

## 1. The founder's frame

Author, at world/chapter creation, an **intriguing pivot question** — *"what will
happen when X?"* — whose resolution space is **closed**: a small set of logical
directions the setup can go, "with no cracks a player could fit outside of." For
each direction, a spectrum of **outcomes from positive to negative**, selected by
the player's choices, with the pre-rolled positive/negative deck folded in for the
unexpected swing. A player who sabotages every good outcome still lands a real,
authored ending — **never a "failure state"**, just the darker pole of the fan or a
dignified off-the-beaten-path direction.

Two decisions the founder made pinning the shape:
- **The fan is authored AT CREATION TIME** — a fixed, invisible build-time artifact,
  not reasoned up at conclusion. Runtime only *selects* and *renders*. (Keeps the
  engine thesis intact at the ending: the model is a voice, never the author of the
  resolution — even here it chooses among and voices authored outcomes.)
- **The roll is GATED on uncertainty, not automatic** (see §4). It fires ONLY for a
  resolving move that is *both* meaningfully impactful *and* genuinely unknown in
  outcome — the same assured-vs-test gate ACTION-RESOLUTION already uses. An assured
  resolution (the mystery cleanly solved) is guaranteed its choice-determined pole;
  no dice. The player's CHOICE always picks the direction; the roll only ever resolves
  a pole that is genuinely in doubt.
- **Start with discrete poles** (§3), reusing the coverage→outcome poles we already
  compute; go finer only if a genre demands it.

## 2. The object — `ResolutionFan` (authored on the hidden arc)

Laid down by the arc author (`game._build_arc` + arc-author cohort) at session-zero /
ingest, on the frame the player never sees. Per chapter/arc:

- **`pivot`** — the dramatic question in one line ("what becomes of the warehouse
  ring once the token surfaces?"). Never shown to the player; it shapes convergence
  pull, not a banner (see [narrative-framing-convergence]).
- **`directions: [Direction]`** — **1–4** genuinely divergent futures the setup can
  resolve into. This is the closed set: the deduction / suspect-web "no cracks"
  discipline ([bodycase-suspect-web]) generalized from *whodunit* to
  *what-becomes-of-it*. Every road converges onto one of these (§5).
- Each **`Direction`** carries:
  - **`ender`** — the conclusive EVENT that fires THIS direction (per
    CONCLUSION-AND-OUTCOME §"reframe": a real climactic act, cannot be genesis-true,
    reachable only after third-act escalation). The direction is entered when its
    ender fires as an in-world event — **never on standing state alone** (the
    Ruling-1 invariant; the bodycase bug was an ending tripping on accumulated facts).
  - **`register`** — how this direction resolves, per genre: `player_act`
    (accusation), `world_event` (the deed done), `quiet_completion` (the fair opens),
    `forced_terminal` (the fall). The genre-specificity lives HERE, authored — the
    engine stays genre-agnostic ([genre-signature-elements]).
  - **`poles: {pole → OutcomeShape}`** — the positive→negative spectrum for this
    direction (§3). Authored as **end-state shapes + trigger conditions**, NOT frozen
    prose (§6).
  - **`polarity_rule`** — the function from play → pole (§3): which coverage/choices
    land warm vs bitter. Reuses `pillar_coverage` / `coverage_summary`.

There is no separate "failure" object. A saboteur's ending is a pole (`hollow` /
`quiet_failure`) or a dedicated dark `Direction`, authored with the same care as the
triumph — dignified, story-worthy, conclusive.

## 3. The spectrum — reuse the poles we already compute

Do NOT invent a new outcome vocabulary. The discrete poles already exist in
`conclusion_from_coverage` (`construct/arc/executor.py`):

> `triumph` · `costly_victory` · `partial` · `hollow`/bittersweet · `quiet_failure`

driven by pillar coverage (`sound` = all required genuine; `complete` = all covered
either way; `unfilled`) × `cost_disposition` polarity (peril_redemption / repair /
sacrifice / fail_forward-inverts) × the `cost_weight` run-integral. The fan's
per-direction `polarity_rule` is exactly this mapping, scoped to the direction. So
the spectrum is **already built**; the fan's new work is (a) the closed *directions*
layer above it, and (b) authoring the poles as rendered-to-world shapes.

## 4. The roll — gated on uncertainty, never automatic (founder, 2026-07-14)

The outcome roll is NOT applied to every resolution. It fires under the SAME gate
ACTION-RESOLUTION already uses for actions ([ACTION-RESOLUTION.md] §1, assured-success
vs a test): a resolving move draws from the deck **only when it is both (a) meaningfully
impactful AND (b) its basic outcome is genuinely unknown.** Otherwise there is no roll —
the outcome is exactly the choice-determined pole, guaranteed.

- **Assured resolution → no roll → guaranteed pole.** A player who did the work and
  framed it right — the detective who correctly names the culprit — has EARNED a known
  outcome; the competent solve lands on its positive pole, deterministically. No dice
  cheapen a resolution the player has made certain.
- **Uncertain resolution → the deck fires → it resolves the uncertainty.** A player who
  meets the king expecting a quest and instead heists the crown and bolts has stepped
  into a genuinely unknown outcome — clean getaway or caught red-handed, no one (not even
  the world) knows yet. THAT draws the deck, and the drawn tier resolves where within the
  chosen direction's pole spectrum it lands (terrible-failure → the direction's worst
  pole … complete-success → its best).

This preserves the earlier "the roll never decides the DIRECTION" rule intact: the
player's CHOICE always picks which direction fires (choosing to heist IS choosing the
theft direction). The roll only ever resolves the POLE, and only when that pole is
genuinely in doubt. The player declares the risky act; the world rolls how it lands —
the tabletop contract. An assured act needs no roll because its landing was never in
doubt.

The assured-vs-uncertain determination is itself agency-sensitive, exactly as at
action time: preparation and competence can move a risky move TOWARD assured (a
meticulously set-up heist with contingencies covered lands closer to guaranteed; an
impulsive grab is pure test). So player skill still shapes even the uncertain endings —
it narrows the variance rather than being erased by it.

The deck (`session:resolution_deck` + cursor, 10 terrible / 20 fail→opportunity /
55 success→cost / 15 crit→boon) is the SAME pre-rolled bag ACTION-RESOLUTION §3 already
maintains; the conclusion draws from it exactly as an action test does. Bounds: the
draw is **narrated as an in-world event** (never a flat dice-reveal), it never overrides
a `forced_terminal`, and it never moves the fan to a different direction.

## 5. The reconciliation — freedom of path, boundedness of resolution

"No cracks a player could fit outside of" must NOT contradict the world-growth /
improv-north-star program (the world grows where the player walks;
[improvisation-north-star], [world-changing-agency]). The line:

> The player owns the **path** — wander anywhere, grow the map, take any tangent.
> The author owns the **resolution set** — every road converges onto one of the
> 1–4 directions.

This is [narrative-framing-convergence] ("all roads converge to conclusion") given
teeth. The saboteur who *tries* to escape the fan is caught by the dark direction /
negative pole — the "required off-the-beaten-path conclusion" the founder named — and
lands, gracefully, back inside the closed set. The refusal/avoidance backstop
([player-avoidance-and-refusal-conclusion]) still guarantees a conclusive close if
the player never drives any ender at all.

Interaction with world-growth: because poles are **shapes rendered to the world as it
actually stands** (§6), a player who reshaped the setup still gets an authored ending
that *fits* the world they made — same instinct as the arc regenerating under drift
([living-world-generator], DRIFT-HANDLING). If a player fundamentally invalidates the
premise the fan was authored against, that is a **regeneration** trigger, not a crack —
see §5a.

## 5a. The unexpected direction — tangent-absorbed vs fan-invalidated (founder, 2026-07-14)

Not every off-script move is equal. The line is ONE test: **are the fan's outcomes still
reachable given what the player just did?**

- **Tangent the fan ABSORBS** (Sherlock detours to a bar for a couple of drinks). Reachability
  is untouched; the outcomes just **defer**. The fan carries an implicit **engagement/time
  tolerance** — its outcomes "land in the next few days *as long as the protagonist re-engages*"
  (a diegetic-reachability window; [diegetic-time-is-the-only-clock] is the clock). The narrator
  may still gently converge. Normal improv-serves-the-destination.

- **Divergence that INVALIDATES the fan** (heist the crown and run; leave the country on
  vacation without notice). The player destroys the precondition every authored outcome depends
  on — the protagonist's continued engagement with THIS situation — so the outcomes literally
  cannot happen. Two consequences:
  1. **The narrator must NOT keep tipping toward the dead outcomes.** Steering toward the now-
     impossible is stonewalling toward dead ends (violates [improvisation-north-star]'s never-
     stonewall). Honesty over railroading.
  2. **Terminate the fan, end the chapter, open a NEW one with a RESHAPED genre** fit to what the
     player actually did (Sherlock-on-a-beach → travel-adventure / travel-romance / who knows).

**The "mandatory item for unexpected direction" — a REQUIRED escape valve on every fan.** Not a
5th authored ending: a guaranteed regeneration path so the player can ALWAYS blow up the story and
get a real new one, never a stonewall. Every fan authors its 1-4 directions AND this valve.

**Reuse the engine already built.** The tangent-adoption system (G-A, `construct/tangent.py`) does
exactly "player declares a new aim → build a new arc → adopt it, demote the old main." Fan-
invalidation reshape is that SAME machinery, triggered by **invalidation** instead of an explicit
declaration, plus one added step: **re-select the genre** (a new game-type card set from the 155,
[game-types], fit to the new trajectory). Not new construction — a new trigger + genre re-selection.

**Reshape policy:** fit-driven WITH variety, not pure randomness — read the player's actual
trajectory and pick a genre that fits, with room for surprise (fled to Marrakech → travel-thriller
or travel-romance, not farming-sim). The sabotage EARNS an unpredictable response; the surprise is
part of the contract.

OPEN forks (founder, not yet pinned): (1) invalidation detection is an assessor read — "are the
outcomes still reachable with plausible re-engagement?" — same family as the §4 assured-vs-test
gate; is the tolerance a FIXED diegetic window or a PER-FAN authored one? (2) how much surprise in
the reshape — fit-with-variety (proposed) vs genuinely randomized among fitting genres.

## 5b. The chapter-boundary structure-validation pass (founder, 2026-07-14)

§5a's reshape is the EXTREME case of a general principle: **the story structure for the next
chapter is chosen from how the player actually PLAYED the last one.** A quick check runs at every
chapter boundary, BEFORE the next chapter's arc/fan is authored, at three intensities:

| Intensity | Signal | Next chapter |
|-----------|--------|--------------|
| **Confirm** | played to type (clean Sherlock) | stays the same genre |
| **Blend**   | played to type + a PERSISTENT added dimension (Sherlock who keeps flirting) | genre **blend** (mystery + romance) |
| **Reshape** | invalidated the fan (§5a: heist / vacation) | full new genre |

Same mechanism, three settings. **The quick check** — a lightweight assessor at the doorway
(`continue_episode` / `_episode_doorway`) — is a **reflection on the WHOLE story so far** (not just
the last chapter; inherently cumulative — the structure converges on the story actually told). It
reads two signals, and pointedly NOT a third:

- ✅ **Tonal / thematic texture the player injects** → register + genre blend. Slapstick along the
  way → lighten (a comic mystery); persistent flirting → thread in romance; dread → darken. This
  can shift **register WITHIN a genre** (grim mystery → cozy/comic mystery) as readily as it blends
  a second genre — "same genre, lighter" is often the right move, not "add romance."
- ✅ **Premise engagement** (§5a) — still pursuing this situation, or gone to a new one.
- ❌ **NOT win/loss / skill / effectiveness.** A player who fails the mystery is NOT asking for a
  different genre — they had a hard time with the mystery; keep it. **Performance lives in the POLE
  (§4), never in the structure choice** — swapping genre because the player struggled would punish
  difficulty. This decoupling is load-bearing (founder, 2026-07-14).

The arc author then builds the next fan against the selected/blended/reshaped genre + register.

**The new input:** the player's demonstrated STYLE (tone + engagement, not competence) drives story
structure. This is "the world grows where the player walks" applied to the STORY SHAPE, and the
concrete delivery of "genre proposes, player disposes" ([episodic-and-play-contracts]) — the player
disposes the next genre by how they play, not by menu.

RESOLVED (founder, 2026-07-14):
- The pass reflects on the ENTIRE story (cumulative), is tone/engagement-driven, NOT
  performance-driven.
- **The pass's canonical question is simply: *"Is there a more appropriate SHAPE for where the
  player is?"*** A fit question, not drift-tracking — about where the player has ARRIVED (tonally,
  situationally), not a vector to chase. The default answer is almost always "no, the current shape
  fits" → do nothing.
- **Default = do little or nothing.** Strong inertia toward the current structure; the pass acts
  ONLY when a clearly better-fitting shape is evident — the player has "clearly turned" the romance
  into a romance-with-heist. A one-off beat is noise; a clear, sustained fit is signal. Conservative
  by default; hysteresis, not a hair-trigger.
- **A fit assessment, never a report card.** It asks whether a better shape fits the player's
  situation — so it structurally cannot punish a struggling player, because struggling is
  difficulty, not a mismatch of shape. (Reinforces the performance-decoupling above.)
- The pass is therefore mostly INVISIBLE — most boundaries change nothing; it earns its keep only
  on the rare clear pivot.

OPEN fork (founder, not yet pinned):
- **Composite game-types** — "mystery + romance" (and register shifts) need the 155-card taxonomy
  ([game-types], [genre-signature-elements]) to BLEND / re-register — layer a secondary genre's
  signature onto the primary, or dial its tonal register. This is the one load-bearing NEW
  capability here; the rest is wiring the adoption engine + the boundary assessor. Everything else
  in §5a/§5b reuses tangent-adoption + the continuation doorway.

## 6. Authored at creation, selected + rendered at conclusion

The split that keeps both guarantees:

- **At creation (build-time, once, by the author cohort):** the full fan — pivot,
  directions, enders, registers, poles-as-shapes, polarity rules — frozen as canon
  on the hidden frame. Compute cost at genesis, not human labor, not runtime improv.
- **At conclusion (runtime):** an ender fires (the Ruling-1 event gate) → **select**
  the direction (which ender) and the pole (polarity_rule over actual coverage/choices,
  ±1 from the roll) → **render** that authored OutcomeShape into prose fit to the
  *actual* world (grown, drifted, whatever the player made of it). The model narrates
  an authored end-state; it never invents which ending happens.

Each `OutcomeShape` is therefore an **end-state + trigger conditions**, not a
pre-written page — the same reason the epilogue is improvised-from-truth in
CONCLUSION-AND-OUTCOME, but now the *shape* it renders is one of a closed authored set
rather than a free judge verdict.

## 7. Shape of the change (when built) — all host-side, clear of the pbr gate

- `ResolutionFan` / `Direction` / `OutcomeShape` dataclasses on the arc model; authored
  by an extended arc-author cohort (insist on 1–4 divergent directions + a dignified
  dark pole per direction; no fail-state framing).
- Selection: `select_resolution(reads, fan, deck_cursor) → (direction, pole, roll_tier)`
  — deterministic center from coverage, ±1 perturbation from the drawn tier.
- Conclusion render: feed the selected OutcomeShape (not a free verdict) to the
  epilogue/render cohort, rendered to current world truth.
- `arc_outcome` / lifecycle: "concluded" = a direction's ender fired (Ruling-1 event
  gate); "outcome" = the selected (direction, pole) — replaces the free judge verdict,
  dissolving the CONCLUSION-AND-OUTCOME non-determinism risk.
- Authoring insistence mirrors the interesting-win insistence already in `_build_arc`.

## 8. Resolved (founder, 2026-07-14) — who fires the resolution event

For `world_event` / `quiet_completion` directions the world MAY close the chapter on
the player when the direction's ender completes, giving the player a beat to react
into but not veto. `player_act` directions still wait for the player's decisive move.
`forced_terminal` fires on the world. (This is the baseline that was proposed; the
founder full-agreed it.)

## 9. Relationship to existing docs

- **Extends** CONCLUSION-AND-OUTCOME (fan = authored closed set of the OUTCOMEs that doc
  judged freely; ender = its conclusive event).
- **Consumes** ACTION-RESOLUTION (the roll deck) as §4 perturbation.
- **Reuses** `conclusion_from_coverage` poles (§3) and `pillar_coverage`.
- **Governed by** narrative-framing-convergence (§5), bounded by
  improvisation-north-star / world-changing-agency, backstopped by
  player-avoidance-and-refusal-conclusion, regenerates via DRIFT-HANDLING /
  living-world-generator.
- **Genre registers** author-side per genre-signature-elements / per-genre-experience-shapes.
