# Game types — the play-style contract (design)

**Status:** DESIGN / founder direction (2026-06-20). Awaiting the founder's
**curated shortlist** before building — the list itself is the founder's call.

## The problem (founder)
Without a nudge, the agent is "willy-nilly" about what the EXPERIENCE is — it
improvises off genre alone, and the genre under-determines the play. The same
setting supports wildly different games, and each wants different handling:
- **Mystery / Sherlock:** the juice is clues, locations, interrogating witnesses,
  sifting stories for the truth through motive, history, red herrings. The
  connective logistics should be HAND-WAVED — "I go to Mrs. McIntosh's for
  questioning" → *"You catch a horse-trolley across the city and ring the bell at
  her green Victorian"* — getting there isn't the game.
- **Escape (Riddick) / Heist (Ocean's Eleven):** the OPPOSITE — the minutia IS the
  game. A literal escape-room chain of narrative puzzles; an intricate, high-stakes
  heist with growing tension. Hand-waving the heist would gut it.
- **Combat adventure (slay the dragon):** confrontation and set-pieces matter; may
  want unexpected combat beats (we have no combat system yet — that, and an
  optional stats/modifier layer, is explicitly a LATER idea, banked).

So the game type is a **resolution lens**: it tells the narrator what is
hand-wave-able connective tissue vs. what is the actual GAME substance to slow down
and dramatize — plus the tension shape and pacing.

## The load-bearing consequence: type ⇒ win/loss
The game type largely **determines the win/loss condition**, which is why it's
chosen at session-zero **right before the ending question** (it frames that
question). Founder's example: a fantasy **combat adventure** wins by *slaying the
dragon*; a fantasy **romance/dating-sim** in the same world wins when, *after
slaying the dragon for the king, the hard-to-get maiden finally swoons and accepts
the picnic in yonder meadow.* Same world, different type, different destination.

## WHERE the type is set — derived at ingest vs. an input to generation (founder)
The game type is NOT free paint over any world — it must be SUPPORTED by the
world's actual substance. Founder's test: ingest *The Hobbit*, then pick "dating
sim" / "espionage" — **it doesn't work**, because the ingested world (Bilbo, the
Ring, Smaug, the road east) carries no romance/spy substance. *The Hobbit* is a
quest-adventure (with survival/puzzle stretches — Mirkwood, the riddles); it is not
those other things. So the type is set where the substance is determined, and that
differs by path:

- **Ingested fiction (Path A — a book):** the type is **DERIVED FROM THE SOURCE and
  LOCKED at ingest** — the most appropriate lens for what the fiction *is*. The
  ingest classifies it (the same place the `genre` tag is derived). The Construct
  does NOT offer arbitrary types for it; it states the nature ("this is a
  quest-adventure"), optionally surfacing a few COMPATIBLE alternates the text
  genuinely supports (Hobbit → adventure | survival | puzzle; never romance). You
  step into an authored world whose nature is already there.
- **Built / generated worlds (Path B — from a premise):** the type is an **INPUT TO
  GENERATION, chosen up front** — and because it DRIVES the authoring, the world
  comes out coherent by construction. "A fantasy dating-sim" generates a court,
  suitors, social stakes; "a fantasy combat-adventure" generates a dragon and a
  war. Same genre, genuinely different worlds (the founder's maiden-vs-dragon
  case). **The free choice lives HERE** — the choice *makes* the substance.
- **Ready-made library worlds** carry their derived/locked type already (it's part
  of what was ingested/generated); the player ADOPTS it, doesn't re-pick. (This is
  the structured form of the `genre` tag we already derive per world.)

Net: the Atrium's `set_game_type` is a real creative choice on the BUILD path
(it shapes generation), and a LOCKED/derived fact on the ingest/ready-made path
(the Construct presents it, the player adopts or picks among compatible alternates).
The "rule of cool" Foyer can flavor within a world, but it can't repurpose a quest
into a dating sim — that's the world-coherence wall ([[improv-and-authority-model]]).

## What a game type IS — the categorical statement + authoring template
**Categorical statement:** *A game type is a claim about the SHAPE OF ENGAGEMENT —
the core loop the player is really playing, and therefore what the narrator
DRAMATIZES vs. HAND-WAVES to serve that loop, how TENSION builds, and what WINNING
and LOSING mean — valid only for a world whose substance can SUPPORT that loop.*

A type is these six axes filled in (the founder curates one block per type):
1. **Core loop** — what the player is actually doing, turn to turn, that IS the fun.
2. **Dramatize** — what the narrator slows down and renders in rich detail.
3. **Hand-wave** — what compresses to a sentence (connective tissue).
4. **Tension shape** — how pressure builds (ratchet / accrete / grind / warm / …).
5. **Win / loss shape** — what victory means; how it goes wrong.
6. **World requires** — what the world must contain for the loop to run at all.

The maintained **directive** (briefing every turn) distills axes 1–4; axis 5 is the
arc author's win/loss prior; axis 6 is the ingest "can this fiction support it?"
check. Worked example — **Mystery:** loop = gather info + reason to a hidden truth;
dramatize = clues/testimony/evidence/contradictions; hand-wave = travel/logistics;
tension = accretion (the noose tightens); win/loss = name the truth / right
accusation vs. wrong accusation or cold case; requires = a concealed truth, ≥2
suspects w/ motives, discoverable evidence, red herrings.

## The mechanism — a maintained narrative directive, NOT a toggle matrix (founder)
Founder, thinking it through and landing it: toggles ("ok to hand-wave" / "needs
deep narrative clarity") risk being **dangerously heavy and over-built**. A
dating-sim isn't two toggles — it's literally *one sentence* ("hand-wave the
mundane life logistics; slow down and give deep narrative clarity to anything
involving the romantic interest"). The decomposition lives in the PROSE. "This is
narrative LLM stuff — almost what LLMs were built for." So:

**Each game type = a sharp NARRATIVE DIRECTIVE (a short paragraph) the agent
MAINTAINS AWARENESS OF throughout the simulation.** No toggle web, no config
matrix. A host-side table `{game_type → directive}`; the directive rides in the
narrator briefing EVERY turn (a `PLAY STYLE` section, exactly like the existing
`STYLE` voice overlay and the pin channel — already the proven pattern). Adding a
type = writing one good directive. **Free improvised narrative** = no directive
(today's default). This is the whole feature; everything below is plumbing, not
machinery.

Example directives (wording is the founder's to curate):
- *Mystery:* "Compress travel and logistics to a sentence — getting somewhere is
  never the game. Slow down and give deep clarity to clues, testimony, scenes of
  evidence, and contradictions between witnesses' stories; let the player sift
  motive, history, and red herrings toward the truth."
- *Heist / Escape:* "Do NOT hand-wave the plan — each step is its own beat with
  stakes and consequence. Build tension as the scheme advances; a slip cascades.
  The intricate mechanics ARE the game."
- *Dating-sim / Romance:* "Hand-wave mundane life details. Give deep narrative
  clarity to every beat involving a romantic interest — glances, subtext, the slow
  turn of feeling; social maneuvering is the substance."

## The shape (when built)
- **A curated, CRAFTED list of game types** — this time a real list the engine
  uses (distinct from "no list" for world *details*, because each type carries
  authored implications we deliberately craft). Anything not matching → **"free
  improvised narrative"** (the genre-only default we have today).
- **Chosen in the Atrium, just before the ending question** — a `set_game_type`
  tool on the Construct dialogue (or a natural beat in it). The founder wants to
  engage the user on this *before* win/loss, since it frames the goal.
- **Per-world `game_type`** stored on meta (and/or a constitutive fact), like
  `scenario_mode`. It threads to:
  1. **The narrator's resolution lens** — a per-type directive (host-side,
     fed into the briefing): what to hand-wave vs. dramatize, the tension/pacing
     posture. (e.g. mystery: "compress travel/logistics to a sentence; slow down
     for clues, testimony, and contradictions"; heist/escape: "do NOT skip the
     mechanics — each step is a beat with stakes and rising tension".)
  2. **Win/loss authoring** — the arc author + `_player_goal` take the type as a
     strong prior for the destination's shape (combat→defeat the threat;
     romance→win the heart; heist→pull it off; escape→get out).
  3. **Pacing** — type-appropriate escalation (the heist/escape ramps; the
     mystery accretes; the romance warms).
- **Free improvised narrative** is a first-class entry (no special lens) — the
  honest default, not a failure mode.

## Strawman shortlist — FOR THE FOUNDER TO CURATE
A starting palette to react to / cut / rename / reorder (not final):
- **Mystery / Whodunnit** — clues, interrogation, deduction; hand-wave logistics;
  win = name the truth / make the right accusation.
- **Puzzle / Escape** — chained narrative puzzles ARE the game; nothing hand-waved;
  win = escape / crack the chain.
- **Heist / Caper** — an intricate multi-stage plan under rising tension; win =
  pull it off (and get clear).
- **Action / Combat Adventure** — confrontation, set-pieces, stakes; win = defeat
  the threat / reach the prize (slay the dragon).
- **Romance / Dating-sim** — relationships, social maneuvering, longing; win = win
  the heart.
- **Survival** — scarcity, attrition, hard choices; win = endure / escape the
  situation.
- **Paranormal / Horror Investigation** — dread and the unknown; win = expose /
  banish / survive.
- **Exploration / Adventure** — discovery, wonder, traversal; win = reach / find
  the destination.
- **Intrigue / Political** — alliances, leverage, betrayal; win = seize / hold
  power.
- **Free Improvised Narrative** — no special lens; the genre-only default.

## Banked (founder, later)
An optional **stats / game-modification system** (and a combat system) — some types
(combat adventure) would benefit; explicitly a down-the-road idea, not now.

## Next step
Founder returns a curated shortlist → we lock the per-type **resolution-lens
directives** + win/loss priors, wire `set_game_type` into the Atrium just before
the ending question, store `game_type` on the world, and thread it into the
narrator briefing + arc authoring. Until then: this is design, not built; today's
behavior is "free improvised narrative" for everything.
