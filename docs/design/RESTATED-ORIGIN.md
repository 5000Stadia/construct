# One end per move: drop a restated origin before ingest (R20 run 11)

**Status:** spec r2, 2026-10-14, for cr review. Not built.

**r2 (cr RED on r1):** under r1, the holding forms could never group with an `in` row. `_canonicalize_containment` leaves `held_by` / `worn_by` / `carried_by` as written, and `_stamp_temporal_state` stamps only `in`. So `in obj:belt` (stamped T) and `held_by person:player` (unstamped) fell into different groups. r2 chooses its route explicitly: **stamp the whole containment family at the turn, attributes kept as written** (rule 0 below). The holding forms stay as the extractor wrote them; pattern-buffer's advice is that they are STATE by guardrail, with no model call. This also fixes a latent stale-state fault: an unstamped holding row lands at the ingest default and can lose the fold to an older, properly-timed `in` row, which is the same bodycase-teleport reasoning that made `in` temporal.

**Source:**
- R20 run 11 (eval/12; archive `/media/k/Blank/construct-scratch/run11`, world included).
- pattern-buffer's view (AgentPost, 2026-10-14). They first proposed an engine gate rule. Their build of it diverged from today's behaviour three ways, and they withdrew it at their main 6f710f2. Their answer: the fix belongs in construct, before the write, and it does not paper over a conflict.

## The failure

The player's turn-27 line: "...cracking the clacker into his knee and grabbing for the key-ring at his belt." The **player-input** extraction (not the settle: the rows carry no narrator source) wrote two rows in one batch, at one valid time:
- `obj:key_ring in obj:belt` (a:5798), which restates where it already was (a:2643);
- `obj:key_ring in person:tomas_venn` (a:5799), which is the move.

The containment family is one functional key, so the engine serves it `conflicted`, and that is its honest read of two containers at one time. The next turn treated the keys as not held, and the critic filed it at t29–t30.

## The rule

**Before a batch of extracted rows is written, construct drops a containment row that only restates the subject's current container, when the same batch moves that subject somewhere else.**

**0. The family is stamped together (r2).** `_TEMPORAL_PROMOTE_ATTRS` grows from `{"in"}` to `{"in", "held_by", "worn_by", "carried_by"}`. `_stamp_temporal_state` gives every unstamped containment-family row `valid_from = turn_time(turn)`, keeping its attribute. A row that already carries a `valid_from` keeps it, so different explicit times stay separate (test 4). Both channels already stamp before ingest: the player path does so after resolve, and the settle does so at promote.

`_drop_restated_origins(p, rows, *, as_of) -> (kept, dropped)`, a pure function over one batch:
1. **Group** the batch's containment-family rows (`in`, `held_by`, `worn_by`, `carried_by`, after `_canonicalize_containment`) by `(entity, valid_from)`. Unstamped rows group under `None`.
2. **The current container,** read once per grouped entity: `p.state(entity, "in", as_of=as_of)`, taken before the batch is written. Only a `known` status counts. `conflicted`, `unknown` or an unreadable read means no drop for that entity.
3. **Drop** a row in a group of two or more only when all of these hold:
   - its value equals the current container;
   - the group also holds exactly one row with a different value (the move);
   - and that is everything the group holds.
   - If the group has two or more different new values, all rows stay, for the engine's honest conflict.
4. **Only the containment row is dropped.** Every other row in the batch stays, including other attributes of the same entity (aliases, `same_as`, `source_doc`). Each row is a separate item in construct's batches.
5. **Telemetry:** `trace.restated_origin` lists `(entity, value)` for each dropped row, and the drop is logged at INFO.

**Where it runs:** on both extraction channels, after resolve and the temporal stamp, before the batch's ingest:
- **The player channel** (`run_turn`'s player ingest): on `_resolved`, after `_stamp_temporal_state`, before both the growth-deferred stage and the direct `ingest_structured`.
- **The narrator settle** (`_settle_prose_facts`): on `_resolved`, stamped first by `_stamp_temporal_state` (the same stamp promote applies later; stamping twice is idempotent, because a stamped row keeps its time), before the staging ingest to `proposed:main`. The staging snapshot is keyed by (entity, attribute), so a pair there today resolves to an arbitrary one of the two.

`as_of` is the turn's play horizon (`_h` / `horizon`). The batch isn't written yet, so the read is the pre-turn container.

## Why this shape

- **One timestamp can't order two containers.** The only reading in which both rows are true is "it was there, and now it's here". The origin is already in the log, and supersession closes it.
- **The honest conflict is kept** wherever the batch itself is ambiguous: two new places, or no readable current container.
- **pattern-buffer's two cautions,** from their withdrawn build: drop only the containment row, never what else the item carries; and leave two new places for the conflict.
- **The root fix** is pattern-buffer's extraction prompt rule ("write only where a thing ends up"). That is a metered check they'll put to Kabe. This guard stays as defence in depth.

## Tests (pure, plus one end-to-end)

1. **Run 11's key-ring:** `in obj:belt` (current) and `in person:player`, both at T. The belt row is dropped, the player row kept, and `trace.restated_origin == [("obj:key_ring", "obj:belt")]`.
2. **Two new places:** `in place:a` and `in place:b` (neither current): both kept.
3. **No current container,** or a `conflicted` one: both kept.
4. **Different valid times:** `in obj:belt` at T and `in person:player` at T+1: both kept (they're different groups).
5. **A lone restatement** (only `in obj:belt`): kept.
6. **Other attributes untouched:** the same entity's `alias` and `name` rows in the batch survive the drop.
7. **Holding forms (r2):** the extractor's unstamped `in obj:belt` and `held_by person:player`, run through `_stamp_temporal_state` and then the drop. Both are stamped T and kept as written; the belt row is dropped and `held_by` is kept. End to end on the player channel, `state(obj:key_ring, in)` folds to the player.
7b. **The stamp (r2):** an unstamped `held_by` / `worn_by` / `carried_by` row gets `turn_time(turn)`; a pre-stamped one keeps its time; a non-containment attribute (`colour`) is untouched.
8. **End-to-end, the player channel:** a turn whose stubbed player extraction yields run 11's pair. After the turn, `state(obj:key_ring, in)` is `known` as the player, not `conflicted`.
9. **End-to-end, the settle:** the narrator extraction yields the pair, and after the settle the key-ring is the player's.
10. **The full suite,** with the turntrace golden moved only by the new `restated_origin` field.
