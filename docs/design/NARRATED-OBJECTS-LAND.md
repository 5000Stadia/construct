# A narrated object lands where it was narrated (R20 run 11)

**Status:** spec r2, 2026-10-14, for cr review. Not built.

**r2 (cr RED on r1):** the landing is a second phase, after the promotion's receipt. The promote ingest fails open: it can return an empty or partial receipt. Deciding the landing from the unconfirmed `promote` list could create `obj:pin in scene` when neither the pin's tie row nor its other rows reached canon, and the mirror would then make that ghost playable. In r2, every input to the landing is receipt-confirmed, and only confirmed landing rows are mirrored.

**Source:** R20 run 11 (eval/12; archive `/media/k/Blank/construct-scratch/run11`, world included), read after the run.

## The failure

The narrator wrote "The lower pin drops free onto the wet stone below the bell-pull". The settle's extraction recorded it as:
- `obj:lower_pin part_of obj:bell_pull_plate`;
- `fastening_anything = False`, `shape = narrow`;
- and **no `in` row**.

So the pin was in canon but nowhere. The scene snapshot lists only what is `in` the place, and the carrying list only what is `in` the protagonist. The next turn's "I snatch up the fallen lower pin" was refused as "not a thing you are known to have". The critic filed the same break five turns running. Run 11's straw and paper strip show the same family. Run 10's chapter-2 shed and hasp were the opening's version of it: created by the settle, placed nowhere.

## The rule

**In the narrator settle, an object the settle promoted that has no live location, but that the same promotion ties to something present in the scene, is placed `in` the scene, by rule.**

Precisely, as a second phase in `_settle_prose_facts`, **after** the promote batch's ingest and its receipt:
1. **Confirmed rows only:** `confirmed = confirmed_batch(promote, promote_receipt_rows, cap=len(promote))`, the existing fail-closed helper (a key counts only when the receipt accounts for exactly its candidates). An empty or partial receipt confirms nothing, or only what it names. If the promote ingest raised, or there was no promotion, this phase does nothing.
2. **Candidates:** every `obj:` entity that is the subject of a row in `confirmed`.
3. **No live location, read after the promotion, at the play horizon:** canon gives it no live `in` (`p.state(e, "in", as_of=horizon)` is neither `known` nor `conflicted`; a confirmed `in` row from this promotion therefore excludes it), and it isn't in the protagonist's held set (`_held_now`, re-read).
4. **Tied to the scene, by a confirmed row:** some row in `confirmed` has the candidate as subject and an entity value `v` that is present at the scene at the horizon:
   - `v` is the scene itself;
   - or the scene is in `v`'s containment chain (`scene in p.locate(v, as_of=horizon)`: the engine walks the single-parent chain, so nested containment counts; `contents` is direct only, so it is not used);
   - or `v` is a part of something present (`p.composition(v, as_of=horizon)` reaches an entity that passes either test above);
   - or `v` is the protagonist, or something the protagonist holds (the player is in the scene).
   Which attribute carries the tie (`part_of`, `on`, `against`, `beside`, `under`) is not consulted. A confirmed entity-valued row naming something present is the evidence; a literal (`position = "below the bell-pull"`) is not.
5. **The write:** `{"entity": e, "attribute": "in", "value": scene, "source_doc": _NARRATOR_SOURCE}`, stamped by `_stamp_temporal_state` for the turn. It is **ingested in its own call with `classify="rules"`**, so it is STATE with no model call (PLACEMENTS-BY-RULE: a placement construct decides is movable state).
6. **Its own receipt:** `landed = confirmed_batch(landing_rows, landing_receipt_rows, cap=len(landing_rows))`. Only `landed` rows are mirrored into the player frame, appended to the promote receipt surface, and recorded in the trace as `landed: [ids]`. A refused or failed landing writes nothing to the player frame. A failure is logged and never sinks the turn: the prose is already delivered, the same fail-open policy as the promotion.

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
- **Keeping `held_by` / `carried_by` / `worn_by` as written** (pattern-buffer's advice, 2026-10-14). The settle's `_canonicalize_containment` rewrites them to `in`, which costs a lifetime-classifier call per held-thing row: the guardrail makes the holding forms STATE with no model call. The fold is identical. This is a separate spec.
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
8b. **Receipt boundary (r2, cr):**
   - the promote ingest raises, or returns an empty receipt: no `in` for the pin in canon or in the player frame;
   - a partial receipt that omits the `part_of` row (the pin's other rows confirmed): no landing;
   - a partial receipt that confirms the `part_of` row but omits an unrelated row: the pin lands;
   - the landing ingest returns an empty receipt: nothing is mirrored, and `landed` is empty;
   - the landing ingest raises: the turn completes, and nothing is mirrored.
9. **The full suite,** with the turntrace golden moved only by the new `landed` trace field (explained in the build note).
