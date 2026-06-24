# Character creation — the Foyer (design)

**Status:** DESIGN for founder alignment (2026-06-19). The conversational **WHO**
phase of session-zero (`SESSION-ZERO.md` ENTRY→WHO), built as a tool-using
dialogue like the Construct (`CONSTRUCT-DIALOGUE.md`, [[agent-as-tools-principle]]).
Runs AFTER the world is built/loaded and BEFORE turn one.

## What the Foyer IS (founder, sharpened)
A **final improvised character + WORLD customization layer** — a *mini world-intro
/ priming moment* before the full intro, where we settle the last elements the
player wants. It is NOT just "pick name/gender": the player can request character
details, history, AND world elements ("can I have an unexpected romantic interest
alluded to mid-story?" → "Sure!"). The authored story already SET these details —
**treat them as defaults**: if the player co-built the world they may have already
chosen the protagonist; they keep, change, or add freely.

### Rule of cool, with negotiation (the load-bearing behavior)
When the player asks for something that strains the world, the engine's job is to
**make it work, not say "Nope."** It proposes a diegetic reframe; the player
counters; the agent crafts it into coherent canon. Founder's example:
> **Player:** Choose all defaults, but let's start with me playing Super Smash
> Brothers in my apartment with my friend Greg.
> **Construct:** This world is medieval high-fantasy — perhaps "smash brothers" is
> a card gambling game?
> **Player:** No, keep it high-fantasy, but say I have the only working TV in the
> kingdom and it plays Super Smash Brothers — someone invented it, and I inherited it.
> **Construct:** I can work with that. Your grandfather, an arch-artificer, built a
> magical automata vision-box that plays the game he called "rabble comrades" —
> which you and others now call "smash brothers."
> **Player:** Cool, let's start.

Wacky, but it's an engaging story *shaped with the player* — and it stays coherent.
Everything agreed is ingested as canon before turn one.

## The flow (founder)
Story written → world ingested/loaded → **the Foyer**: the Construct introduces
the player-character's role in this setting and collaborates on who they are —
then turn one's introduction. Specifically:
- Introduce the role the player will inhabit in THIS world.
- Offer to define character details (name, gender, background, …). For each, ask
  **"choose it, or shall I?"** — the player can define or defer every axis. No
  fixed form/list; the agent fluidly covers the axes that matter for this world.
- **Surface the world's own anchors tied to this character** — the interesting
  threads the fiction already planned around them (a relative in the story, the
  name of the detective agency, the esoteric teacher and their training). The
  player can flesh these out or accept them.
- **Accept free additions** — "oh, and I had a rivalry with the head of the rival
  house." Character freedom is accepted and woven in craftily; additions become
  part of the world.
- Everything defined/added is **ingested into the world as canon BEFORE turn one**,
  so the narrator and NPCs honor it.
- **Completion gate:** the agent keeps asking *"is there anything else you'd like
  to add to your character's details or history before we start?"* until the
  player says they're ready.
- Then the narrative begins: an introduction of the world and where the character
  finds themselves at the start of their story (the existing cold open, now
  character-aware).

## Example feel (a school of esoteric arts)
> **Construct:** Before you step in, let's settle who you are here. You'll play a
> student of the Hollow Conservatory — and the world already holds threads tied to
> you: a mentor, the severe one they call Maon, who taught you your first true
> sigil; and a sibling who left the school under a cloud. We can shape these
> together. First — your name: choose it, or shall I?
> **Player:** Call me Wren.
> **Construct:** Wren it is. Your background — where are you from, what brought you
> to the Conservatory? Choose, or I'll invent something that fits.
> **Player:** You pick.
> **Construct:** Then: a fen-child who read weather-omens before any master found
> you — which is just why Maon both prizes and distrusts you. And how should the
> world refer to you?
> **Player:** She/her. Oh — and I had a rivalry with the head of the rival house,
> someone who always edged me out.
> **Construct:** Noted — a rival who's beaten you to every prize; I'll give them a
> name and a place in the world. Anything else to add to Wren's history before we
> begin?
> **Player:** That's it.
> **Construct:** Then let me weave it in… *(ingesting)* …done. Stepping you in.
> *(cold open: the Conservatory, and where Wren stands as her story opens)*

## Architecture (reuses the Construct pattern)
- **A new cohort `foyer_turn`** (the Construct's voice, now world-grounded). Each
  call gets: the protagonist + the world's anchors tied to them (read from canon),
  the character-sheet-so-far, and the latest message. Returns `{reply, actions[]}`.
  Tools: `set_detail(field, value)` (name/gender/pronouns/background/…),
  `pick_for_me(field)` (the agent invents a fitting value), `add_history(detail)`
  (free additions — minted into the world), `done` (player is ready → ingest +
  begin).
- **`CharacterSheet` host state** `{name, pronouns, gender, background,
  additions:[…], decided:set}` — persisted per-player as a registry `chargen`
  blob (survives restart), exactly like the Atrium `creation` blob.
- **World-anchor read:** from the open world, gather what canon ties to the
  protagonist — their attributes, relations, and the arc-scope entities/NPCs
  connected to them — and hand them to the cohort as "anchors you may offer."
  (Host-side read; the engine is the truth.)
- **Ingest before turn one:** on `done`, a `chargen → structured rows` step turns
  the sheet + additions into `stated` canon (the protagonist's name/gender/
  background; new entities+relations for additions like the rival) and commits via
  `ingest_structured(frame=canon)`. The hidden arc binds the protagonist by entity
  id, so adding attributes never breaks it. THEN the cold open renders.
- **Transport state:** a new phase between world-ready and turn-one. `_enter_world`
  no longer jumps straight to the cold open on a FRESH entry — it opens the world,
  enters the Foyer (seed a `chargen` blob), and converses; `done` → ingest →
  mark_started → cold open. **Resume skips the Foyer** (the character already
  exists). The world is open-but-not-started during the Foyer.

## The authority boundary — rule-of-cool authoring vs. play-time coherence
The Foyer is the **high-permission AUTHORING window**; in-game is **flavor, not
control**. This boundary is the whole game's integrity (founder):
- **In the Foyer:** the player co-authors. Add elements, history, hinted future
  beats, even genre-straining requests — the agent NEGOTIATES them into coherent
  canon (above) rather than refusing. The bar is "can we make this cohere?", and
  the agent works to say yes.
- **In play:** minimize player NARRATIVE CONTROL — they get FLAVOR, never CONTROL,
  and the agent owns the EDGES of the scene. "I take out my grandfather's
  handkerchief and hand it to the crying woman" → fine (plausible, incidental;
  never "you don't have that"). "I take out my whodunit goggles and see who did
  it — tell me now" → refused; that dissolves the world. The world has **walls and
  doors you can't magically bypass**, and it **reacts realistically**: if Sherlock
  murders a witness, Sherlock goes to jail, to everyone's horror — that is the
  world's coherence. No rewinding time UNLESS the world was built with contained
  time-travel rules (a machine, its own constraints) — out of scope for now.
- This refines [[improv-and-authority-model]]: the Foyer is the sanctioned
  fact-MINTING window (authoring); in play, plausible attempts are granted but
  facts are not minted by fiat, and coherence shows the walls. Rule of cool serves
  an engaging, meaningful journey — never a ruleless world that loses immersion.

## Forks — RESOLVED (founder, 2026-06-19)
1. **Defer surface to the Foyer, but the authored story SETS defaults.** Build the
   role + connected anchors richly AND give the protagonist default personal
   details (name/gender/origin) — the Foyer presents them as defaults to keep,
   change, or replace (a co-builder may have already chosen them). The narrator
   must not pre-empt the Foyer: the cold open comes AFTER, so the player's choices
   are settled canon before any prose.
2. **Every fresh entry, agent adapts** — built AND ready-made worlds; light
   "accept or tweak" for a strongly-authored canon protagonist, full creation for
   an open one. Resume always skips the Foyer.
3. **Additions (and negotiated world elements) ingest as `stated` canon** before
   turn one; the authority boundary above keeps them coherent.

## Build order — SHIPPED (2026-06-19)
1. **DONE.** `foyer_turn` cohort (`cohorts.py`, tag `foy`) + `CharacterSheet` +
   host tool loop (`construct/foyer.py`: set_detail/add_element/done/chat) + offline
   demo (`scripts/foyer_demo.py`). Live-confirmed the rule-of-cool negotiation
   (Smash-Bros-in-a-medieval-realm → grandfather's automata vision-box) + the
   anchor-surfacing + free additions.
2. **DONE.** World-anchor read (`foyer.world_anchors` + `Session.character_setup`,
   via `foyer.state_value` which unwraps the `{status,fact:{value}}` porcelain
   shape — the bug a live run caught) + the chargen→canon ingest
   (`foyer.ingest_character`: protagonist details direct + `cohorts.ingest_additions`
   grounding free additions into entities/relations, all `stated`).
3. **DONE.** Transport: the Foyer phase (`_begin_foyer`/`_foyer` in
   `transport_core`; registry `chargen` blob, survives restart; phase-first
   routing) — `_enter_world` hands a FRESH entry to the Foyer, `done` ingests +
   opens; resume/`/play` skip it.
4. **DONE.** 266 tests green (stub loop + ingest + transport phase). Live-verified
   end-to-end on anchor (character_setup reads "Ilsa Renn — custodian…", ingest +
   cold open render clean). Codex review of the Atrium/Foyer wiring still owed.
