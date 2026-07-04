# Character Grounding — the Picard model

**Status:** SPEC (founder-directed 2026-06-29, design locked via AskUserQuestion). Builds on
NARRATIVE-FRAMING (no premise crawl; call-to-action arises) and CHARACTER-CREATION (the Foyer).

## The problem
The player enters play not knowing what their character IS or where ("I don't know what 'my office'
is that I stand in, and the mystery began… am I an accountant?"). The opening jumps to the mystery
with no character grounding, and the old premise crawl spoiled it.

## The shape (founder, verbatim intent)
"A little from the Foyer and one turn in world. Think Captain Picard getting outfitted and declaring
his role in the world, then entering his inhabited space and interacting with it for a little bit
before the story soon starts." And: "Either the player specifies, or the engine completes a rich
description of the player's role and place in the world, then zooms into the space they inhabit and
that moment for them to take from. But it should be grounded."

## Four parts

### P1 — Foyer grounding beat (a little; "outfitted, declares role")
After name + pronouns, the Foyer asks ONE grounding question, shaped:
`"You are [role] — [generalized vibe of where/when, NO plot]. What brought you to this [work/place]?"`
No mystery reveal. The player MAY specify their role, place, and motivation (free narration honored,
per the existing Foyer rule-of-cool). `foyer_turn` gets a directive for this beat; the motivation
answer is captured (`set_detail motivation` / `add_element`).

### P2 — Engine GROUNDS the identity (the core; "completes a rich description, grounded")
A new `ground_character` cohort runs at the Foyer's `done` (in `apply_character`), AFTER the sheet
is ingested. From the world brief + the authored role + the player's sheet (incl. any specifics they
gave), it authors a GROUNDED identity and ENRICHES the protagonist's STARTING place (never mints a
conflicting one):
- protagonist `role` / `profession` + a 1-2 sentence `background` (who they are + the standing
  MOTIVATION that makes the call-to-action coherent — a consulting niche, an auditor's eye). No plot.
- the inhabited PLACE (the protagonist's current `in`): `name`, `kind`, and a concrete `description`
  — what it IS (a public accountancy named Pym & Co., its service, its public presentation).
- Honors what the player specified (don't overwrite their stated role/place); completes only the
  gaps. Committed as canon at the opening horizon. Fail-open (a miss → the build's defaults stand).
- NEVER references the hidden arc answer (passes through the same protected-key discipline).

### P3 — Opening zooms into the inhabited space ("entering his inhabited space")
`open_scene` / `opening_parts`: the cold open foregrounds the player's now-concrete office/quarters,
grounded and low-pressure — "a moment for them to take from" (inhabit it, notice their own things),
NOT the mystery. (The premise crawl is already gone.) Title + this grounded zoom.

### P4 — ~One turn of grounding, then the story "soon starts"
The inciting incident / call-to-action is held ~one turn so the player settles/validates who+where
first, then it lands. A `grounding_runway` of ~1 turn before the arc's first pressure beat /
nudge fires — extends the "ground-first, call-to-action arises" ruling with a deliberate runway.
Implementation: gate the first call-to-action nudge/incident on `turn > opening+1` (host-side
staging; no arc-grammar change — beats stay path-independent conditions).

## Build order & verification
1. P2 `ground_character` cohort + `apply_character` wiring (the core; the player always knows what
   they are). Tests: cohort produces a grounded role+place from a sparse sheet; honors a specified
   role; never overwrites; fail-open. Live: a London build reads as a Sherlock-esque clerk with a
   sensible body-of-investigation, the office is concretely named/placed.
2. P1 Foyer grounding-question directive + motivation capture. Test: the question is asked, the
   motivation is captured, no plot reveal.
3. P3 opening zoom (open_scene directive foregrounds the inhabited space, low-pressure).
4. P4 ~1-turn incident runway (host staging gate). Test: the call-to-action doesn't fire on turn 1.
Each step: tests + full suite green; then a live bot build to validate the felt experience.
Regression-risky steps (P2 commits canon at seal; P4 changes pacing) get a Cx review before live.

## Out of scope
Per-genre grounding-question templates beyond the generic (grow on demand); a multi-turn grounding
"mini-sandbox" (one settling turn is the founder's call).

---

## P5 — The grounded cold open: lived context + player↔cast relationships (founder 2026-06-30)

P3 holds the call and zooms into the player's space; P5 answers a deeper founder note: a named
cast is not enough — "although these people have been named my knowledge and history of them is
not detailed, so it does not explain why I am here why they are here and what the purposes of
talking to them." The character is not arriving as a stranger to their own life. **This is a
standing directive for ALL games.**

### Render side (`construct/session.py`, task #74)
The grounding context already lives in canon — in the player's knowledge frame `knows:<prot>`
(`current_assignment`, `operating_context`, `assignment_status`, `relationship_to_<id>`, …) =
"what the player walks in already knowing." It never reached the open because
`_establishing_anchors` excludes the protagonist's own facts. The open now surfaces it:
- `_player_grounding(names, present_ids, absent_ids)` reads `knows:<prot>`, returns
  `(situation_lines, {present_id: relationship}, absent_rels)`. Filters identity attrs (voiced
  in the PLAYER CHARACTER block), arc **protected** solution keys, and freeform VALUES that
  brush concealed vocabulary (`_value_leaks`, the same screen `live_threads` applies).
- `_opening_narration` adds a standing **GROUND THE PLAYER** directive (cedes call-to-action
  TIMING to the scene's pacing lever — not a plot summary), a **WHAT YOU ALREADY KNOW** block,
  and per-present-cast **relationship** phrases (iterating aligned `(id, name)` pairs).
- **Hold only when solo:** the P3 held-CTA mode ("zoom into your empty space, no hook")
  contradicts a staged open with cast present, so `_fresh` gates on `not present`. Cast present
  → `grounding=False` (ground first, then the call arises), compatible with the lived context.

### Build side (`construct/game.py` + `cohorts.py`, task #75)
For the open to introduce a present character as *who they are TO the player*, the player's
frame must hold that relationship. `seed_player_relationships` (called in `_finalize_scenario`
after cast staging) authors, via the `author_player_relationships` cohort (one roster-aware
call), a `relationship_to_<id>` fact in `knows:<prot>` for each PERSON cast member — the
player's STANDING, second-person, **non-spoiler** connection ("your newly assigned partner";
"a dockside witness you've been sent to question"; "a name on your list you've not yet met").
Fail-open; reversible (knows: only); protected keys screened at build, leaky values at render.

Cx-reviewed (332→335 GREEN for #74). Live-verified on bodycase (logs/grounding-open-*.md):
the open now states why the player is there, the events, and who each person is to them, with
identity authoritative — the relationship phrases fill in once a build authors them (#75).
