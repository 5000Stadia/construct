# Audit — why chapter 2 doesn't reshape (the structure-validation gap)

**Status:** AUDIT (2026-07-14), companion to [RESOLUTION-FAN.md](RESOLUTION-FAN.md) §5b.
Triggered by the `genreshift` probe (logs/critic-genreshift-bodycase-1784046935.md):
the player curved the whole mystery toward a warm/romance register; chapter 2 came
back a straight mystery. This audit finds why and scopes the resolution.

## The finding, in one line

The genre/game-type contract is **decided once at session-zero and inherited verbatim**;
nothing reads how the player actually played, and `continue_episode` never re-decides it —
so there is no place for the reshape to happen.

## Evidence (exact locations)

1. **game-type decided at genesis, stored on meta, never rewritten.**
   - Decided in `_create_scenario` (`game.py:783-800`): caller-supplied `game_types` →
     `_ps.resolve`, else DERIVED via `cohorts.classify_game_type` (`cohorts.py:749`).
     bodycase forces `["detective_procedural","mystery_whodunnit"]` (`build_bodycase.py:63`).
   - Persisted as a LIST on `meta["game_type"]` (`game.py:1219`), serialized to
     `<name>.meta.json`.
   - `continue_episode` (`game.py:2572`) loads meta unchanged (`:2592`) and **only reads**
     `meta["game_type"]` — for death-policy re-derivation (`:2926-2927`). It rewrites
     main_arc/arc_ids/entry_epoch/title/death_policy/arc_scope/continuation_intro
     (`:2911-2939`) but NOT `game_type`/`genre`. So the contract is durable and inherited.

2. **Nothing tracks how the player played.** Confirmed negative (searched style/tone/
   tendency/register/profile/tally/behavioral). `session._play_style` (`session.py:155`) is
   STATIC — the fixed directive from `directive_for(meta["game_type"])`, one-way into the
   narrator briefing; it never updates on player moves. `extract_personal_threads`
   (`cohorts.py:2894`, called `game.py:2700`) captures promises/bonds — plot commitments,
   not tone. The only player-derived continuation input is the compacted narrative-memory
   ledger (`history`, `game.py:2624`), a PLOT through-line, not a play-style read.

3. **The continuation arc author is genre-neutral AND not even given the shape directive.**
   `cohorts.generate_arc` (`cohorts.py:2137`, called `game.py:2734`) receives `style`
   (world voice, `meta.get("style","")`), fuel, protagonist, present cast — but NOT the
   game_type/shape/signature directive. So on continuation the inherited game_type governs
   the narrator briefing + death policy, but does NOT shape the freshly-authored arc. (The
   initial build DOES inject shape/signature into the cast block, `game.py:811-841`; the
   continuation path does not.)

## What already EXISTS (the good news — most of §5b's machinery is built)

Genre/shape is **already composable** — blending a second genre is idiomatic:
- `meta["game_type"]` is a LIST; `directive_for()` BLENDS multiple ("this world BLENDS the
  styles below; hold ALL at once… the blend IS the experience", `play_styles.py:44-57`).
- The engine SHAPE layer blends too: `shapes_for()` yields primary + secondary shapes,
  signature elements unioned (`story_shapes.py:382-404`, `:275-285`). "Shapes are BLENDABLE
  — most holodeck programs are compounds" (`story_shapes.py:5-7`).

So **the composite-game-type capability I feared was net-new already exists.** Blending
"mystery + romance" = adding a romance game-type key to `meta["game_type"]`.

## What's actually MISSING (the real gaps)

- **G1 — the signal + decision.** No whole-story play-reflection. Need a cheap §5b cohort
  ("is there a more appropriate SHAPE for where the player is?") reading the story-so-far,
  tone/engagement-driven, NOT performance; default = do nothing (conservative/hysteresis).
- **G2 — the write-back.** `continue_episode` must apply the reassessment to
  `meta["game_type"]` (blend = add keys; reshape = replace keys) BEFORE the new chapter is
  authored, so the durable contract reflects where the player took it.
- **G3 — feed the shape directive into the continuation arc author.** Close the latent gap
  so ch2's ARC (beats/pillars/tension) is authored against the (reshaped) shape, not just
  the narrator briefing. Otherwise the reshape stays narrator-flavor, not structure.
- **G4 — the tonal-register dial (the ONE genuinely-new capability).** There is NO
  light/dark register knob (only a binary peril/general flag off family,
  `story_shapes.py:320-340`). The "slapstick → *lighter* mystery" case (register shift
  within a genre) has no first-class support. Options: (a) approximate by blending a
  lighter game-type card (e.g. a comedy/cozy key); (b) add a first-class register modifier.
  Deferrable — blend covers most cases; the pure register-dial is the only real new build.

## Resolution seam

Insert G1 in the unused space between `game.py:2709` (end of personal-threads) and
`:2734` (`generate_arc`), alongside `extract_personal_threads`; it consumes `history`
(already gathered). G2 rewrites `meta["game_type"]` before the death-policy block
(`:2921`). G3 passes the shape/signature directive (from the possibly-updated game_type)
into `generate_arc` (`:2734`). §5a (invalidation → full reshape + new chapter) is the same
path with REPLACE instead of blend, reusing the tangent-adoption arc-swap.

## Scope verdict

Smaller than feared: G1 (one cohort) + G2/G3 (wiring in `continue_episode`) deliver
confirm/blend/reshape on top of existing blend machinery. G4 (register dial) is the only
net-new capability and is deferrable behind blend approximation.
