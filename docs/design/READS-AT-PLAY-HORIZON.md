# Reads at the play horizon: the move check, the mint check, and the chapter-2 build

**Status:** spec r2, 2026-10-13, for cr review. Not built.
**Source:** R20 run 10 (eval/12): criterion 5 failed, and three new-place moves logged "move grant ... did not take".
**r2 (cr RED on r1, 327d2fe):**
- `_plan_episode_doorway` and `_plan_hook_cast` read the head on their own; they are now bound, with a fallback-path test.
- The scope check is an audited table (below), not a promise to grep.
- `_mint_held_object` gets an explicit split.
- Applying the same split to `_grant_moved_place`'s reuse check and to hook-cast staging is r2's own addition (see "The identity rule").

## The facts

A generated world's canon holds the whole hidden source story:
- **Source time:** chunk *i* is written at `i × SOURCE_STEP` (1e6), so 1e6 to 1e7 in run 10.
- **Play time:** play begins at `opening_as_of` (1,001,000 in run 10), right after chunk 1. Each turn writes at `turn_time(turn) = opening_as_of + turn`.
- **The rest of the source story is the future of play,** and play reads are bound to the horizon (B' S3), so they never see it.
- **A read without `as_of` reads the timeline head: the source story's ending.**
  - In run 10's played world, `locate(person:elias_venn)` at the head gives `place:ice_cutter_shed` (written at 10,000,000).
  - At the play horizon it gives the place the player actually reached, `place:streetlamp_smoke`.

## The horizon rule, in one place

`Session._horizon` (session.py:312) computes `opening_as_of + n`, capped at `next_source_as_of - 1`, or None for a legacy world. That rule moves into one module-level function, `play_horizon(meta_or_fields, turn)`, which `Session._horizon` calls, so the session and the chapter-2 build can't drift.

## The identity rule: two different questions, two different reads

A play-time site asks one of two questions, and they need different reads:

1. **"Does this id exist anywhere, so a fresh mint must not take it?"** That's id-collision avoidance, and it reads the **head**. A mint must never write onto an entity the hidden story introduces later: in an append-only log that would fuse the player's improvised thing with a future character or place, and couldn't be undone.
2. **"Does this exist now, in play?"** That covers coreference reuse, existence, and whether a write took. It reads at the **horizon**.

So an id that exists at the head but **not** at the horizon (a future-only id) is **neither reused nor written onto:**
- a mint takes the next free suffix (`place:ice_cutter_shed_1`), as `_mint_held_object` already does for any collision;
- staging skips it and logs it.

Joining the player's thing to the later source thing, if they turn out to be the same, is the registry's `same_as` work (seeding r4), never a guess here.

## Defect 1: the improv-move grant checks at the head

`_grant_moved_place` (turnloop.py:2365) writes the move, then checks:

    chain = PorcelainWorldReads(world).location_chain(protagonist) or []
    if not chain or chain[0] != place_id: ... return None, {"status": "grant_failed", ...}

- In any world with source rows after the play band, the head chain is the source ending's location, so every improv mint reports `grant_failed`. Run 10 had three: 'the renewed Last Office', 'the streetlamp smoke', 'the nearest moored barge'.
- **The consequences:** movement status stayed unset; whatever follows a committed move didn't run; the player's frame kept `you · in · cell 12`; canon got the location only later, through extraction.

**Fix.**
- **The verification** (line 2480) reads `PorcelainWorldReads(world, horizon=as_of)`. `as_of=None` (legacy) keeps today's head read exactly. cr confirmed this repair on r1.
- **The reuse checks** (line 2429: `has_entity(place_id)`, `has_entity(container)`, and `_gate_target`) follow the identity rule:
  - exists at the horizon: reuse it, as today;
  - exists only at the head (future-only): mint the next free suffix, and the obstruction gate treats it as a fresh mint;
  - absent at both: mint, as today.
- **Two reads,** `head = PorcelainWorldReads(world)` and `now = PorcelainWorldReads(world, horizon=as_of)`, named for the question each answers. With `as_of=None` they are the same read, so legacy is unchanged.

## Defect 2: the chapter-2 build reads the head, so the hidden story's future enters chapter 2

**What happened in run 10:**
- Chapter 2's opening put the player "outside the ice cutter shed" with "a clean northbound pass and a sealed packet". These are the source story's ending place and props, all written after the play band.
- At the player's horizon the shed doesn't exist. The narrator correctly said "there is no shed in this patch of pavement", and the classifier refused the pass.

This is a continuity break and a concealment leak: the chapter-2 author was handed the hidden story's future.

**Fix.** `continue_episode` computes `h = play_horizon(meta, next_turn_number(world))`, the horizon its last turn played at (None for a legacy world), and threads `h` through every read, transitively. Each site is listed in the table (rows G1 to G11). The commit set, and what the build *writes* (origin and epoch rules, Cx 253 §4), are unchanged.

## The audited table

**How the list was made.** It is every `PorcelainWorldReads(` construction and every `porcelain.locate/state/entities/facts/snapshot/who_knows` call, plus `_canon_entity_ids`/`_known_people`/`_world_digest` calls, in `turnloop.py`, `session.py`, `game.py`, `growth.py` and `foyer.py` (main at 2b165b6).
- **Already bound** (`as_of=` or `horizon=`): left out.
- **Every other site:** listed with its path and the decision.
- **The build** re-runs the same grep and fails its own checklist if a site appears that this table doesn't cover.

**Helpers gain an optional `as_of=None`:** `_canon_entity_ids(world, as_of=None)`, `_known_people(world, as_of=None)` and `_world_digest(world, limit, as_of=None)` (passed to `entities` and `snapshot`). With None, today's head read is byte-identical, so the build-time callers don't change.

### Bound to the play horizon (play-time paths)

| # | Site | Path | Change |
|---|---|---|---|
| T1 | turnloop.py:2480 `_grant_moved_place` verify | every improv move | `horizon=as_of` |
| T2 | turnloop.py:2429 `_grant_moved_place` reuse checks | every improv move | the identity rule: horizon for reuse, head for collision |
| T3 | turnloop.py:2112 `_mint_held_object` verify | equipment and take grants | `horizon=at` (the turn time it wrote at; `at=None` keeps head) |
| T4 | turnloop.py:5115 `run_turn` place-candidate enumeration (`entities(canon/player_frame, prefix="place:")`) | the briefing's place list | `as_of=horizon`. Today a future-only place enters the candidate set and is filtered only because its name/kind read is bound; enumerating at the horizon removes the dependence |
| S1 | session.py:1424 `_reload_arc_portfolio` | after a mid-play re-plan | split: the plot-frame reads (`main_arc_from_frame`, `portfolio_from_frame`) stay at the head (see H3); `arc_entities(...)` and the scope's `has_entity` filter use a `horizon=self._horizon()` read, as `_refresh_beat_scope` (session.py:1406) already does. Today a future-only arc referent enters next-turn scope |
| S2 | session.py:482 → foyer.py:128 `ingest_character` → `_world_digest(world)` | the foyer, before turn 1 | `ingest_character(..., as_of=self._horizon())`, and the digest at `as_of`. Today the model that binds the player's additions sees the source ending. `ground_character` (the next line) is already bound |
| R1 | game.py:2718 / 2733 `author_replan`: `_canon_entity_ids`, `_known_people` | mid-play re-plan (turnloop.py:6339) | `author_replan(..., as_of=h)`; turnloop passes the turn's horizon. Same leak as G4/G5, mid-chapter |
| G1 | game.py:3177 `continue_episode` `reads` | chapter-2 build | `PorcelainWorldReads(world, horizon=h)`. This covers, through `reads`: `main_arc_from_frame`, `portfolio_from_frame`, `terminal_outcome`, the `narrative_memory` state, `_episode_fuel`'s `reads.events(...)`, the region-card `state` reads, the consequence-callback `reads.events(kind=...)`, `_plan_hook_cast`'s `has_entity`, and `_ep2_scope`'s `has_entity` |
| G2 | game.py:3212 `known_ids` from `_canon_entity_ids(world)` | chapter-2 build, to the generator | `_canon_entity_ids(world, as_of=h)` |
| G3 | game.py:3229 region-card ordering `locate(prior_main.protagonist)` | chapter-2 build | `as_of=h` |
| G4 | game.py:3339 `_known_people(world)` to `generate_arc` | chapter-2 build, to the generator | `_known_people(world, as_of=h)` |
| G5 | game.py:3069 `_plan_episode_doorway` live-locate fallback | chapter-2 doorway when no terminal-location receipt exists | `_plan_episode_doorway(world, prot, as_of=h)` → `locate(prot, as_of=h)` |
| G6 | game.py:3100 `_plan_hook_cast` stage-place fallback `locate(protagonist)` | hook staging when the doorway has no place | `as_of=h` |
| G7 | game.py:3124 `_plan_hook_cast` cycle check `locate(stage_place)` | hook staging | `as_of=h` |
| G8 | game.py:3108 `_plan_hook_cast` `reads.has_entity(hid)` (bound by G1) | hook staging | the identity rule: a hook id that exists only at the head is **not staged** (no kind/name/role/in rows written onto a future entity), and is logged. The generator never saw future ids (G2), so this is a coincidental collision |

### Kept at the head, with the reason

| # | Site | Why the head is right |
|---|---|---|
| H1 | turnloop.py:2094 `_mint_held_object` collision `reads.has_entity` | Global id-collision avoidance: the identity rule's question 1. A future-only id must not be taken. Already mints a fresh suffix |
| H2 | session.py:1390 `_read_independent_extra` | A `session:main` literal. The session frame holds no source rows, and the head is its latest value |
| H3 | game.py:2841 `open_playthrough` `reads`; session.py:1424 plot-frame reads (S1) | Plot-frame arc manifests are written at build or at turn time, never in the source band. The head is the newest arc, which is what a reopen or reload needs. These reads don't touch canon entities |
| H4 | game.py `continue_episode` `frame_facts(world, session:main / SESSION, ...)` (doorway receipt, settled cards, shape receipt) | Row-level reads of session bookkeeping. No source rows, and the newest receipt is selected by entity suffix |
| H5 | game.py:508, 516, 609, 616, 640, 647, 856 (`_stage_*`, `_stage_author_arc`, `_stage_author_cast`) | Build time, before play exists. The hidden-plot author is meant to see the whole story |
| H6 | game.py:1180, 1465, 2396, 2403, 2588, 2598, 2684 (`_frames_tell_apart`, `_link_law_embodiment`, `seed_player_relationships`, `_place_kind`, `_place_specificity`, `_score`) | Build time only (callers inside the build stages, lines 1209, 1484, 1510, 2597, 2628, 2688) |
| H7 | game.py:2020, 2021, 2033 `_assess_viability` | The post-build gate, before play. Note: its "protagonist has a location" check reads the head, so it accepts a protagonist placed only in the future. That's a build-gate question, left to plan item A's future-leak check, not this spec |
| H8 | game.py:2461, 2471 `reseed_character_frames`; 2501 `knows_inspect`; 2538 `who_knows_inspect` | CLI and dev tools, not on a play path |
| H9 | growth.py | No unbound sites (its reads take the turn's `as_of`) |

## Tests

1. **Grant at the horizon** (T1, T2).
   - **Setup:** a source row places the protagonist at a later valid time (the source ending); play is at `opening_as_of`.
   - An improv move mints `place:x` and returns `(place:x, seg)`, not `grant_failed`. Movement status is committed.
   - The player frame, if the turn writes it on a committed move, reads `place:x` at the horizon.
   - A head-only world (no horizon) behaves as today.
2. **Future-only id on a move** (T2).
   - **Setup:** `place:ice_cutter_shed` exists only at 10,000,000. The player improvises "the ice cutter shed".
   - The grant mints `place:ice_cutter_shed_1`.
   - Its kind/name rows are on `_1`.
   - No row is written to `place:ice_cutter_shed` at any time.
3. **The mint split** (T3, H1).
   - A future-only `obj:pass` exists; a take of "the pass" mints `obj:pass_1` (collision at the head), and the verification at `at` succeeds, so it returns `obj:pass_1`.
   - With `at=None`, behaviour is as today.
4. **Run 10's shape, chapter 2, through the prompts** (G1 to G4).
   - **Setup:** the source future has the protagonist `in place:ice_cutter_shed` and holding `obj:northbound_pass` at 10,000,000. Play ends in `place:streetlamp_smoke`, with a terminal-location receipt.
   - `continue_episode` with a stub provider: no prompt it sends (generator, personal threads, death policy, opening) contains "ice cutter shed" or "northbound pass".
   - `known_ids` and the region-card order come from the horizon.
   - **Negative control:** with `h` forced to None, they do appear.
5. **The doorway fallback path** (G5). The same world, **without** the terminal-location receipt, so the doorway falls back to a live locate.
   - The doorway place is `place:streetlamp_smoke`, not the shed.
   - The committed chapter-2 rows contain no `in` row to the shed.
   - **Negative control:** unbound, the doorway is the shed.
6. **The hook-cast fallback path** (G6 to G8).
   - **Setup:** no receipt and no doorway place, so `_plan_hook_cast` falls back to its own locate. The stub proposal's `hook_cast` names one ordinary new id and one future-only `person:` id.
   - The staged `in` rows target `place:streetlamp_smoke`.
   - The future-only id gets no rows and is logged.
   - The cycle pre-check reads the horizon chain.
7. **The re-plan and the foyer** (R1, S1, S2).
   - `author_replan` with a stub provider at a horizon: `available_ids` and `present_characters` exclude a future-only person.
   - `_reload_arc_portfolio`: a future-only arc referent doesn't enter `_scope`.
   - `ingest_character` with additions: the digest sent to `ingest_additions` excludes a future-only place.
8. **Legacy worlds:** with no `opening_as_of`, today's behaviour is byte-identical (the existing continuation, grant and foyer tests pass unchanged).
9. **The full suite.**
