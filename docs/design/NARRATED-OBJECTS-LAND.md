# A narrated object lands where it was narrated (R20 run 11)

**Status:** spec r1, 2026-10-14, for cr review. Not built.

**Source:** R20 run 11 (eval/12; archive `/media/k/Blank/construct-scratch/run11`, world included), read after the run.

## The failure

The narrator wrote "The lower pin drops free onto the wet stone below the bell-pull". The settle's extraction recorded it as:
- `obj:lower_pin part_of obj:bell_pull_plate`;
- `fastening_anything = False`, `shape = narrow`;
- and **no `in` row**.

So the pin was in canon but nowhere. The scene snapshot lists only what is `in` the place, and the carrying list only what is `in` the protagonist. The next turn's "I snatch up the fallen lower pin" was refused as "not a thing you are known to have". The critic filed the same break five turns running. Run 11's straw and paper strip show the same family. Run 10's chapter-2 shed and hasp were the opening's version of it: created by the settle, placed nowhere.

## The rule

**In the narrator settle, an object the settle promoted that has no live location, but that the same promotion ties to something present in the scene, is placed `in` the scene, by rule.**

Precisely, after `_settle_prose_facts` builds `promote` and before its ingest:
1. **Candidates:** every `obj:` entity that is the subject of a row in `promote`.
2. **No live location, read once at the play horizon:** neither `promote` nor canon gives it a live `in` (`p.state(e, "in", as_of=horizon)` is not `known` or `conflicted`), and it isn't in the protagonist's held set (`_held_now`).
3. **Tied to the scene:** some row in `promote` has the candidate as subject and an entity value `v` that is present at the scene at the horizon:
   - `v` is the scene itself;
   - or the scene is in `v`'s containment chain (`scene in p.locate(v, as_of=horizon)`: the engine walks the single-parent chain, so nested containment counts; `contents` is direct only, so it is not used);
   - or `v` is a part of something present (`p.composition(v, as_of=horizon)` reaches an entity that passes either test above);
   - or `v` is the protagonist, or something the protagonist holds (the player is in the scene).
   Which attribute carries the tie (`part_of`, `on`, `against`, `beside`, `under`) is not consulted. An entity-valued row naming something present is the evidence; a literal (`position = "below the bell-pull"`) is not.
4. **The write:** `{"entity": e, "attribute": "in", "value": scene, "source_doc": _NARRATOR_SOURCE}`. It is stamped by `_stamp_temporal_state` with the turn's rows. It is **ingested in its own call with `classify="rules"`**, so it is STATE with no model call (PLACEMENTS-BY-RULE: a placement construct decides is movable state). It is mirrored into the player frame with the promote batch. The trace records `landed: [ids]`.

**Not placed:**
- an object tied only to something absent (a letter "from the capital": `v` is not present);
- an object with only literal rows;
- an object whose `in` is `conflicted` (run 11's key-ring, a separate question with pattern-buffer);
- anything on an epilogue turn (`promote` is empty there already);
- persons and places: persons move by the cast-movement lane, and places by the place grant.

**The opening settle** (`settle_opening`) shares `_settle_prose_facts`, so an opening's staged props land in its scene too. That closes the run-10 shed-and-hasp case for things the opening ties to its scene. Things "in your coat" are still the possession lane's business (not here).

## Why this shape

- **First-mention permanence** (founder): what the world has said exists must persist. A thing placed nowhere can't persist in play.
- **Map-governs:** a tie to the scene is evidence the extraction itself produced. The host only completes the containment the prose's own rows imply. It never moves an object that has a location.
- **Absent objects stay absent:** narrator prose names remembered and distant things all the time. Requiring a tie to something present keeps them out of the scene.

## Not in scope

- **The two-ended hand-over** (`in obj:belt` and `in person:tomas_venn` at one time): asked of pattern-buffer first (run 11 report).
- **Twin ids** (build-time `obj:straw` beside play-time `obj:straw_scrap`): a refer and binding question, for the seeding registry (SEEDING-LIBRARY-WIRING) and a later item.
- **The classify cohort's refusal wording** ("never been established in this world's canon" for a thing that was): with this rule the pin would be in the scene, and the refusal wouldn't fire. The wording is a separate craft fix.

## Tests (stub extractor, real engine)

1. **Run 11's pin:** the settle extracts `obj:lower_pin part_of obj:bell_pull_plate` (the plate `in` the scene) and no `in`. After the settle, `state(obj:lower_pin, in)` is the scene, stored STATE (sidecar verdict), with zero "Classify the lifetime" calls for that row. The next turn's scene snapshot lists the pin.
2. **The tie through the protagonist:** `obj:pulp on obj:irons` (the irons held by the protagonist) lands in the scene.
3. **Absent stays absent:** `obj:letter from place:capital` (not present) gets no `in`.
4. **Literal only:** `obj:pin position = "below the bell-pull"` gets no `in`.
5. **Located stays put:** an object with a live canon `in` elsewhere, tied to a scene object this turn, is not moved. An object the protagonist holds is not moved.
6. **Conflicted is left alone:** two same-time `in` rows give no landing row.
7. **Opening:** an opening settle that stages `obj:shed_hasp part_of obj:shed` (the shed in the opening scene) lands the hasp there.
8. **Epilogue:** nothing lands.
9. **The full suite,** with the turntrace golden moved only by the new `landed` trace field (explained in the build note).
