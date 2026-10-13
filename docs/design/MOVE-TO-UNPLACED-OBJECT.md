# Moving to a thing: decide by where it is, not by its head noun

**Status:** spec r2, 2026-10-13, for cr review (cr RED on r1: tri-state field, entitlement, commit seam, scene before classify). Not built.
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
2. **Located elsewhere** (its canon chain doesn't reach the scene). Only the **player's knowledge** can send them there *(r2)*. `refer` resolves against canon, so a canon-known object at a place the player never learned must not become a shortcut past discovery, just as moves to people have their undiscovered-offscene gate.
   - The destination is the first `place:` on `p.locate(obj, frame=player_frame, as_of=horizon)`: where the player knows it is. The move then goes through the same gates as any resolved place: undiscovered offscene, same place, `_gated_move_commit`.
   - If the player frame has no chain for it (canon knows where it is, but the player doesn't), the outcome is `UNDISCOVERED`: no travel, no relocation, and nothing about its place in the trace or the briefing. This is the person rule's outcome.
3. **Unlocated in canon** (no canon chain at all: born in play without a place). The facts are silent, so the turn classifier's new field decides:
   - `within_scene: true` → `IN_SCENE`, and the object is placed in the current scene (`obj in pre_scene`), so it stops being unlocated;
   - `within_scene: false` → the move continues down the existing **unresolved-destination path** (the roster bind with `resolve_destination`, then the mint), with the fixture guard **skipped** for this case;
   - `within_scene: None` (absent or malformed) → exactly today's outcome: the fixture word list decides.

**The commit seam *(r2)*.** For `within_scene=false`, `obj.in = destination` is written only after the same gated move has actually committed the player there, whether by a mint or by an existing-place bind. A blocked, ambiguous, deliberating or undiscovered outcome moves neither the player nor the object. The object row goes in the same ingest batch as the move's commit, not before it.

### The new field is tri-state *(r2)*

`within_scene` is `bool | None` end to end. On `TurnIntent` it is `within_scene: bool | None = None`, never `bool = False`. Only a literal JSON `true` or `false` from the model is authoritative; it is read as `v if isinstance(v, bool) else None`, never `bool(...)`. Absent, null or malformed is `None`, and `None` gives exactly the existing fixture-head outcome on **both** paths (resolved-unlocated and zero-candidate).

### The new field (no new call)

`classify`'s schema gains:

    "within_scene": {"type": "boolean",
      "description": "when moves_to is set: true if the destination is something INSIDE the
       place the player is in now (a table, the window, a person here: repositioning);
       false if it is somewhere else they go to"}

It is optional in the schema (not in `required`), so stubs without it keep working.

**Scene before classify *(r2)*.** Today the classify call runs before `pre_scene` is captured. The implementation reads the protagonist's scene first (the same horizon-bound `locate` the movement code uses for `pre_scene`) and passes its display name in. A test asserts that the classify prompt contains it.

`classify` does not see the scene today: it gets the player's line, the actor, candidates, laws and `decisive`. It gains one optional argument, `scene` (the current place's display name, from the turn's existing scene read), shown in the prompt as "The player is now in: <scene>." This is one boolean and one line on a call that already runs every turn; no new call. Without `scene`, the model judges from the line alone. Run 9's line ("I slip through the opened door ... Gate table first") carries the answer.

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
8. *(r2)* **Legacy stubs, both paths.** With the field absent, an unlocated `obj:table` ("I step to the table") and a zero-candidate "the rain barrel" each give exactly today's outcome. A malformed value ("yes", 1) is also treated as absent.
9. *(r2)* **Entitlement.** `obj:ledger` is in canon at `place:vault`, an offscene place the player has not learned (no player-frame chain). "I go to the ledger" → `UNDISCOVERED`: no relocation row, and `place:vault` appears in neither the trace nor the briefing. With a player-frame chain to `place:vault`, the move goes there through the gates.
10. *(r2)* **The commit seam.** With `within_scene=false`:
    - a mint commits both the player and `obj.in`;
    - an existing-place bind commits both;
    - a blocked route (traversal policy) moves neither: no player row and no object row.
11. *(r2)* **Scene before classify.** The classify prompt contains the current scene's display name; the stub provider's recorded prompt is checked.
