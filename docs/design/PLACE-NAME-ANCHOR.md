# The player knows the name of the place they stand in (R20, criterion 5)

**Status:** spec r1, 2026-10-14, for cr review. Not built.

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

**The player knows the name of the place they are standing in.** Once per turn, after movement has committed and before the briefing's player-frame snapshot, construct mirrors the scene's canon name into the player frame when the frame lacks it:
1. **The scene:** `scene`, the protagonist's place at the play horizon, as the turn already computes it after movement.
2. **The name:** `p.state(scene, "name", as_of=horizon)`. Only a `known` literal counts.
3. **Skip** when:
   - the player frame already has a `name` for the scene (any value);
   - `(scene, "name")` is in `arc_protected_keys(arc, live_reads)` (a concealed place, such as a lair or a hidden room, keeps its frame discipline);
   - the read raises. The anchor then stays name-free, as today.
4. **The write:** `{"entity": scene, "attribute": "name", "value": <name>}` into `knows:<protagonist>`, `valid_from = turn_time(turn)`, with `classify="rules"` (a name is CONSTITUTIVE by the guardrail; no model call). It is traced as `trace.place_named = scene`.
5. **The opening:** `settle_opening` does the same for the opening scene, so turn 1's anchor is named.

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
8. **The full suite,** with the turntrace golden moved only by the new `place_named` field.
