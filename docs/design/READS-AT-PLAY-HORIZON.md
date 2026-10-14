# Reads at the play horizon: the move check and the chapter-2 build

**Status:** spec r1, 2026-10-13, for cr review. Not built.
**Source:** R20 run 10 (eval/12): criterion 5 failed, and three new-place moves logged "move grant ... did not take".

## The facts

A generated world's canon holds the whole hidden source story:
- **Source time:** chunk *i* is written at `i × SOURCE_STEP` (1e6), so 1e6 to 1e7 in run 10.
- **Play time:** play begins at `opening_as_of` (1,001,000 in run 10), right after chunk 1. Each turn writes at `turn_time(turn) = opening_as_of + turn`.
- **The rest of the source story is the future of play,** and play reads are bound to the horizon (B' S3), so they never see it.
- **A read without `as_of` reads the timeline head: the source story's ending.**
  - In run 10's played world, `locate(person:elias_venn)` at the head gives `place:ice_cutter_shed` (written at 10,000,000).
  - At the play horizon it gives the place the player actually reached, `place:streetlamp_smoke`.

## Defect 1: the improv-move grant checks at the head

`_grant_moved_place` (turnloop.py) writes the move, then checks:

    chain = PorcelainWorldReads(world).location_chain(protagonist) or []
    if not chain or chain[0] != place_id: ... return None, {"status": "grant_failed", ...}

- **No horizon.** In any world with source rows after the play band, the head chain is the source ending's location. So every improv mint reports `grant_failed`. Run 10 had three: 'the renewed Last Office', 'the streetlamp smoke', 'the nearest moored barge'.
- **The consequences:**
  - movement status stays unset;
  - the move is never treated as committed (whatever follows a committed move doesn't run);
  - the player's own frame kept `you · in · cell 12` after the escape;
  - canon got the location only through extraction, later.
- **The same function's** earlier `reads = PorcelainWorldReads(world)` (the `has_entity` checks) is unbound too.

**Fix.** `_grant_moved_place` already receives `as_of`. Both of its `PorcelainWorldReads(world)` constructions become `PorcelainWorldReads(world, horizon=as_of)`. `as_of=None` (legacy, horizon-less worlds) keeps today's head read exactly.

## Defect 2: the chapter-2 build reads the head, so the hidden story's future enters chapter 2

`continue_episode` (game.py) builds `reads = PorcelainWorldReads(world)` with no horizon. It also calls `world.porcelain.locate(prior_main.protagonist)` and `_canon_entity_ids(world)` unbound. These feed the next chapter's author: known ids, the region-card order, the episode fuel, and the reads `_episode_fuel` makes.

- **What happened in run 10:** chapter 2's opening put the player "outside the ice cutter shed" with "a clean northbound pass and a sealed packet". These are the source story's ending place and props, all written after the play band.
- **At the player's horizon** the shed doesn't exist, so the narrator correctly said "there is no shed in this patch of pavement", and the classifier refused the pass.
- **This is both a continuity break and a concealment leak.** The chapter-2 author was handed the hidden story's future: Kabe's "nothing narrates ahead or leaks future knowledge".

**Fix.**
- **Bind every world read in `continue_episode` to the play horizon of the chapter that just ended,** the horizon its last turn played at. Compute it exactly as `Session._horizon` does, from the same meta fields: `opening_as_of + next_turn_number`, capped at `next_source_as_of - 1`, or None for a legacy world. Factor that rule into one shared function, so the two can't drift. It is bound to:
  - `reads`;
  - the protagonist `locate`;
  - the known-ids enumeration (it becomes the horizon-bound entity list, `entities(canon, as_of=h)`);
  - every read `_episode_fuel` and the arc author's digest make.
- **The commit set** (the new arc's rows) is unchanged.
- **Unchanged too:** what the chapter-2 build *writes* (origin and epoch rules, Cx 253 §4). Only what it *reads* changes.

## Scope check: other unbound reads on play paths

The build finds them with a grep, and the review checks the list:
- `PorcelainWorldReads(world)` without `horizon`, and `porcelain.locate(` / `.state(` without `as_of`, in `turnloop.py`, `session.py`, `game.py` (`continue_episode`, the opening, `start_playthrough`) and `growth.py`.
- **Each is either bound** to the turn's or chapter's horizon, **or annotated** with why the head is right (build-time code before play exists; legacy worlds; session-frame bookkeeping that has no source rows).
- The build note lists every site and its decision.

## Tests

1. **Grant at the horizon.** A world with a source row placing the protagonist at a later valid time (the source ending), and play at `opening_as_of`. An improv move mints `place:x` and returns `(place:x, seg)`, not `grant_failed`. Movement status is committed. The player frame (if the turn writes it on a committed move) reads `place:x` at the horizon. A head-only world (no horizon) behaves as today.
2. **Run 10's shape, chapter 2.**
   - A world whose source future has the protagonist `in place:ice_cutter_shed` and holding `obj:northbound_pass` at 10,000,000. Play ends with the protagonist in `place:streetlamp_smoke`.
   - `continue_episode` with a stub provider: the prompts it sends (the generator and opening authors) contain neither "ice cutter shed" nor "northbound pass".
   - The region-card order and known ids come from the horizon.
   - Negative control: unbound, they do appear.
3. **The legacy world:** no `opening_as_of`, and today's behaviour is byte-identical (existing continuation tests pass unchanged).
4. **The full suite.**
