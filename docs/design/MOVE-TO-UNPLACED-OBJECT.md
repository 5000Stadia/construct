# Moving to a thing: decide by where it is, not by its head noun

**Status:** spec r1, 2026-10-13, for cr review. Not built.
**Source:** R20 run 9 (eval/12, run 9 restart). Criterion 2 failed because the player never left the cell.

## The failure

Turns 9, 11 and 12 all moved toward the gate table: "I slip through the opened door ... Gate table first", "I keep my pace steady toward the gate table". The turn classifier set `moves_to` each time; its own instruction says "Walking off within the same place is not a move". `refer` resolved the phrase to `obj:gate_table`, an object born in play with kind "table" and **no location**.

The resolved non-place branch (`turnloop.py`, around the "RESOLVED NON-PLACE target (Cx 327)" comment) then returned `IN_SCENE`. Its condition is

    _dest_head(moves_to) in _FIXTURE_HEADS or _in_scene_obj

"table" is in the fixture word list, so the head noun alone decided it, whatever the object's actual place. No move was committed and no place was grown, so the escape never happened in the world. The narrator described the walk anyway, which is why chapter 2 opened back in the cell.

The word list exists for real cases: Cx 325 and Cx 327 ("step to the table" must not mint `place:table` and walk the player away from the people in the room). It just answers the wrong question when the thing is somewhere else.

## The rule

Decide by facts first. Use a judgment only where the facts are silent, and take that judgment from a call that already runs.

For a move whose target resolved to a **non-place, non-person** entity:

1. **Located in the current scene** (its chain contains the scene, or shares the player's immediate place). This is `IN_SCENE`, as today.
2. **Located elsewhere** (it has a chain that doesn't reach the scene). The destination is **its place**: the first `place:` on its chain. The move goes through the same gates as any resolved place (undiscovered offscene, same place, `_gated_move_commit`), exactly as a move to a person goes to that person's place today.
3. **Unlocated** (no chain). The facts are silent, so the turn classifier's new field decides:
   - `within_scene: true` → `IN_SCENE`, and the object is placed in the current scene (`obj in pre_scene`), so it stops being unlocated;
   - `within_scene: false` → the move continues down the existing **unresolved-destination path** (the roster bind with `resolve_destination`, then the mint), with the fixture guard **skipped** for this case. On a commit, the object is placed in the destination;
   - field missing (an older stub, or a fail-open classify) → today's behaviour: the fixture word list decides.

### The new field (no new call)

`classify`'s schema gains:

    "within_scene": {"type": "boolean",
      "description": "when moves_to is set: true if the destination is something INSIDE the
       place the player is in now (a table, the window, a person here: repositioning);
       false if it is somewhere else they go to"}

It is optional in the schema (not in `required`), so stubs without it keep working. `classify` does not see the scene today: it gets the player's line, the actor, candidates, laws and `decisive`. It gains one optional argument, `scene` (the current place's display name, from the turn's existing scene read), shown in the prompt as "The player is now in: <scene>." This is one boolean and one line on a call that already runs every turn; no new call. Without `scene`, the model judges from the line alone. Run 9's line ("I slip through the opened door ... Gate table first") carries the answer.

**Elsewhere.** The zero-candidate fixture guard (in the unresolved path, "IN-SCENE FIXTURE GUARD (Cx 325)") also reads `within_scene` when it is present: `true` → `IN_SCENE`; `false` → no fixture absorb; missing → the word list. The word list remains only as the fallback.

## Not in scope

- Object continuity in general (the stone tag and the slip flickering): this is a narration and permanence item of its own.
- The registry-first seeding redesign: it reduces unlocated objects at build, not ones born in play.

## Tests

1. **Run 9's shape.** An unlocated `obj:gate_table` (kind table) and a player in `place:tomas_cell`; classify says `moves_to="Gate table"`, `within_scene=false`. The move is not `IN_SCENE`. The unresolved path runs: the roster bind returns "new", then the mint. The player ends in a new place, and `obj:gate_table` is in that place.
2. **Cx 325 kept.** "I step to the table" with an unlocated or freshly minted `obj:table` and `within_scene=true` → `IN_SCENE`, no relocation row, and the table is placed in the scene.
3. **Located elsewhere.** `obj:ledger` in `place:office`; the player is in `place:hall`, and refer resolves "the ledger". The move goes to `place:office` through `_gated_move_commit`. An undiscovered-offscene office is still gated.
4. **Located here.** `obj:lamp` in the current scene → `IN_SCENE`, whatever the classify field says (facts win).
5. **Field missing.** Today's behaviour, byte for byte: the existing movement tests pass unchanged.
6. **Zero-candidate guard.** "the rain barrel" with `within_scene=false` → no fixture absorb (bind, then mint); with `true` → `IN_SCENE`.
7. The turntrace golden moves only if a recorded scenario's classify stub carries the new field; any change is explained.
