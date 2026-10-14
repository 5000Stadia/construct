# The player knows the name of the place they stand in (R20, criterion 5)

**Status:** spec r2, 2026-10-14, for cr review. Not built.

**r2 (cr RED on r1):** three precision clauses.
- The "already known" check reads the player frame at the play horizon.
- Concealment fails closed and is checked first.
- `place_named` means a receipt-confirmed write.

The opening's blank-prose return is now stated.

**Source:** R20 runs 10–12 mechanics logs (archived on Blank), read 2026-10-14.

## The finding

The briefing's location anchor (`briefing.py`, "THE LOCATION ANCHOR", task #10) names the scene only from the **player frame**. cr's frame discipline: a canon-only name the player never learned must not ride into prose. The player frame almost never holds the name of the place the player stands in.

| Run | Turns with a named anchor | Turns with "YOU ARE AT the place you now stand in." |
|---|---|---|
| 10 | 0 | 17 |
| 11 | 7 (all "closed", a mis-minted id) | 16 |
| 12 | 0 | 15 |

Run 12's player frame holds 865 rows and **no place name**. Run 11's holds two, neither of them a scene's. So the anchor the critic campaign added "with the same explicit force as PRESENT CHARACTERS" has run name-free in play. The WHERE notes that failed criterion 5 in runs 7, 9 and 12 were prose drift, with canon unmoved: the narrator re-placed furniture from the last room, or staged a cell the scene wasn't (eval/12). In run 12, the one run measured both ways, the anchor was name-free on every turn of that drift. An unnamed anchor is a plausible contributor, not a proven cause; this spec gives the narrator the name, and the next run's WHERE notes measure the effect.

## The rule

**The player knows the name of the place they are standing in.** Once per turn, after movement has committed and before the briefing's player-frame snapshot, construct mirrors the scene's canon name into the player frame when the frame lacks it, in this order:
1. **The scene:** `scene`, the protagonist's place at the play horizon, as the turn already computes it after movement.
2. **Concealment first, failing closed (r2).** `arc_protected_keys(arc, live_reads)` is evaluated before any name read.
   - If `(scene, "name")` is in it, nothing is written.
   - If it raises, nothing is written either: protection that can't be read is never treated as empty. The skip is recorded in `trace.dropped_cohorts` as `place_name (protection unreadable)`.
3. **Already known, read at the horizon (r2):** `p.state(scene, "name", frame=knows:<protagonist>, as_of=horizon)`. A `known` or `conflicted` frame name, of any value, means no write. A frame name stamped past the horizon does not count, so it never suppresses a needed mirror.
4. **The canon name:** `p.state(scene, "name", as_of=horizon)`. Only a `known` literal counts.
5. **Any read that raises** in steps 3–4 means no write. The anchor stays name-free, as today.
6. **The write:** `{"entity": scene, "attribute": "name", "value": <name>}` into `knows:<protagonist>`, `valid_from = turn_time(turn)`, with `classify="rules"` (a name is CONSTITUTIVE by the guardrail; no model call).
7. **Receipt-confirmed (r2).** `trace.place_named = scene` only when the write's receipt contains the `(scene, "name")` row (`confirmed_batch`). An empty or partial receipt (the fail-open ingest), or a raising write, leaves `place_named` empty and the anchor name-free. The turn always completes.
8. **The opening (r2 clarification).** `settle_opening` runs the same helper first, before its blank-prose early return, so a turn-0 frame names the opening scene even when the opening prose is blank. Turn 1's own mirror is the fallback in any case.

What it changes: the briefing's `names` map (built from the player frame) now resolves the scene, so the anchor reads "YOU ARE AT: the laundry hold." The same name labels the scene wherever `_disp` renders it.

## Why this shape

- **It is true to the fiction.** Standing in a room, you know what it's called, or at least the name the world gives it. A place whose name is a secret is exactly what `arc_protected_keys` already marks.
- **It keeps cr's frame discipline.** The name enters the player frame through an explicit, traced rule ("you are here, so you know here"). It never leaks a place the player hasn't reached: only the scene's name is mirrored, never a destination's or a neighbour's.
- **It's cheap:** one state read and, at most, one rules write a turn.

## Not in scope

- Naming the place a move is headed to, or adjacent places. The player learns those by going.
- Underdetermined moves to unnamed places ("the scullery threshold"), which g855759 holds as they are.
- NPC positions inside a scene (run 12's t4 detail: "by the works-master's desk").

## Tests

1. **A named scene:** the player in `place:laundry_hold` (canon name "the laundry hold"), with the player frame lacking it. After a turn, the frame has the name, and the narrator's prompt reads "YOU ARE AT: the laundry hold." (the real briefing). The write is `classify="rules"` (spy), and `trace.place_named` is the scene.
2. **Already known:** a frame that names the scene differently ("the hold") is left alone, with no write.
3. **Concealed:** `(scene, "name")` in `arc_protected_keys`, so nothing is written and the anchor stays name-free.
4. **A future-only name:** the scene's name row is stamped past the horizon, so nothing is written (the read is at the horizon).
5. **Unreadable:** `state` raises, so nothing is written and the turn completes.
6. **After a move:** a granted, improvised place (`place:deck`, canon name "deck") is named in the same turn's briefing.
7. **Opening:** `settle_opening` names the opening scene in the frame.
8. **A future frame name (r2):** the canon name is visible now, and the player frame names the scene only past the horizon. The current turn writes and shows the canon name.
9. **Protection unreadable (r2):** `arc_protected_keys` raises, so nothing is written, the skip is recorded, and the anchor is name-free.
10. **Write refused (r2):** the frame write returns an empty receipt (and, separately, raises). `trace.place_named` is empty, the anchor is name-free, and the turn completes.
11. **Opening with blank prose (r2):** `settle_opening(world, arc, "", turn=0)` still names the opening scene in the frame.
12. **The full suite,** with the turntrace golden moved only by the new `place_named` field.
