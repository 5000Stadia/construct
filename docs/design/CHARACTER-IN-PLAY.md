# Character-in-Play — identity forms in the opening turns (design, for sign-off)

**Status:** DESIGN-FIRST, founder-directed (2026-06-21). Supersedes the separate
**Foyer** pre-game interview (CHARACTER-CREATION.md) with a **narrator-driven** model:
no interview phase — the player starts playing immediately and their character
crystallizes diegetically over the first few turns, drawn out by the *actual*
narrative agent. Awaiting go-ahead before the Foyer teardown.

## 1. Why
Every Foyer complaint ("amateurish," "re-saying the intro," "feels like it's *trying*
to do narrative") had one root cause: **the Foyer is a separate cohort cosplaying as
the narrator.** It's a bolted-on interview with its own voice, so it never reads as the
story. The fix isn't more Foyer polish — it's to let the real narrator open the world
and have identity take shape *in play* (founder).

## 2. The model — pronouns first (plain), then diegetic fill-in-the-blank
- **FIRST, one straight-up question: pronouns** (founder) — plain, before the world
  opens: *"Before we begin — your pronouns? 1. he/him  2. she/her  3. they/them or
  other."* No scene, no diegesis. The narrator needs them from turn one to address
  "you" correctly, so they come up front and flat. (This is the ONLY pre-play beat.)
- Then go **straight to the cold open** — the narrator opens the world (grounded in the
  authored `premise`). No separate interview phase beyond that one question.
- While any **customizable detail** is unset, the narrator weaves ONE into the scene as
  a natural hook and ends with a **parenthetical fill-in-the-blank prompt**, always
  offering *"or shall I choose?"*:
  - name → *"You fill out the intake form with your name (what's your name — or shall I
    choose?)"*
  - past → *"You overhear clerks in the next room repeating your name and what they've
    heard about you (what did they hear about your past — or shall I choose?)"*
- The **player's answer fills the blank**; the host captures it to canon. *"You choose"*
  → the narrator/host fills the authored default or invents a fitting value, in-scene.
- One blank at a time, woven into whatever the scene is actually doing — never a list.

## 3. Pronouns stay SIMPLE — asked FIRST, never a scene (founder, hard rule)
Pronouns come **first and straight up** (§2) — a plain menu, before play. Do **not**
ever dramatize gender/pronouns. The corny trap (founder's own example): *"you stand
before the gendered bathrooms… oh look, a non-binary one too! …'Oh (pronoun?)'"* — never
do this. The diegetic painting is for name / past / who-you-are only; gender is handled
flatly, once, up front.

## 4. The gate (founder's call: pronouns up front, then crystallize as you go)
- **One pre-play beat only: the plain pronoun question** (§2). After it, play starts at
  turn one and the rest of identity (name, past, …) forms over the first few turns.
- A detail still unset after the opening window (a few turns) is **defaulted** so play
  never stalls — authored name (e.g. Ilsa Renn). Pronouns are gotten up front, so they're
  set before turn one (default to they/them only if the player skips even that). The old
  hard "interview won't start without name+pronouns" gate is **retired**.

## 5. Mechanism (host side)
- **Unset-detail tracking:** the protagonist's customizable attributes (`name`,
  `pronouns`, `background`/past, optional `motivation`) — which are still unset is read
  from canon each turn (the authored defaults seed some; the rest are blanks).
- **Forming overlay in `run_turn`:** while blanks remain AND we're in the opening window,
  add a briefing directive — "the protagonist's <DETAIL> is still unformed; weave ONE
  natural in-scene hook that invites the player to establish it, and END with a short
  parenthetical '(… — or shall I choose?)'. Pronouns: ask plainly, never a scene." Pick
  the next blank by priority (name → past → … ; pronouns handled plainly alongside name
  or via a light aside).
- **Capture:** a cheap extractor on the player's turn pulls the filled value (or "you
  choose") → writes the protagonist attribute as canon via the existing
  `foyer.ingest_character`/structured-row path (now incremental, per detail). "You
  choose" → host writes the default/invented value.
- **Exit the forming phase** when required blanks (name, pronouns) are filled or
  defaulted; overlay deactivates → ordinary play.
- **Rule-of-cool** authoring (the "Smash-Bros → grandfather's automata" negotiation)
  still works — it just happens in-scene now (the narrator/resolve-and-commit path).

## 6. What's removed / kept
- **Removed:** the Foyer interview phase, the `foyer_turn` cohort, the
  `_begin_foyer`/`_foyer` transport routing, the pre-play required-criteria hard gate,
  `foyer_open`.
- **Kept:** `foyer.ingest_character` + the chargen→canon row helpers (reused for
  incremental capture); the authored `premise` (the narrator's cold-open grounding);
  `_DETAIL_ATTRS`/required set (name, pronouns) — now *targets to fill in play*, not a
  gate; the saved-character store ([[player-notes]]'s sibling) for /restart "keep".
- **/restart "keep character"** still re-applies the saved sheet (skips re-forming);
  "redo" re-enters the forming flow.

## 7. Build slices
1. **Up-front pronoun ask** (one plain question before the cold open) + the **forming
   overlay + unset-detail read** in `run_turn` (the narrator surfaces one blank
   diegetically + the fill-in prompt; name/past only). Additive — no teardown yet.
2. **Capture + incremental canon ingest** from the player's turn (+ default-on-"you
   choose" / default-after-window). Reuse `ingest_character` per-detail.
3. **Transport rewire:** fresh entry → straight to the cold open with forming active;
   retire `_begin_foyer`/`_foyer`/`foyer_open`/the gate. (The teardown — last, once 1–2
   are proven.)
4. **Tests:** forming-overlay fires for an unset detail; capture writes canon; "you
   choose" defaults; pronouns stay plain (no scene); window-default; /restart keep/redo;
   required details end up set or defaulted before the forming phase exits.

## 8. Open question for sign-off
- Build order above defers the teardown to slice 3 (build the new path, prove it, then
  remove the Foyer) — agree? And anything to add to the **customizable blanks** beyond
  name / pronouns / past (e.g. an appearance detail, a signature item)?
