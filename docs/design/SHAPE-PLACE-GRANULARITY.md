# Shape-aware place granularity — grounding the intimate interior (spec)

**Status:** SPEC, for Cx review then build. Task #109. Extends the story-shapes
author-signature layer with a setting-scale element for intimate/domestic shapes.

## Problem (measured, live-verified)

The overnight shape-breadth campaign (2026-07-09, Finding 3) built a **fresh
romance** world (`probe_romance`) and the critic hit a real break at t2: the
opening scene snapped `morning-front-room → night-kitchen` with no movement and
nothing to hold onto.

Ground truth (NOT fragmentation): the generated fiction authored ~30 Lisbon
**neighborhoods** (alfama/arroios/estrela/…) but **no apartment ROOMS** — no
`front_room`, no `kitchen`. The protagonist (`person:marta_vale`, properly named
+ roled) was located at `place:lisbon` — **city granularity**. So the intimate
opening had no room-level anchor: the narrator improvised "front room," then
drifted to "kitchen/night" with no committed place to stand on.

**Root cause:** `author_story` (the world-generation prose author,
`cohorts.py:1472`) asks for "a definite SETTING with a few **connected places**"
— tuned for INVESTIGATION/ADVENTURE geography (locations to travel *between*). A
domestic/relationship shape's scene **IS a room**, not a city to traverse. The
prose never grounds the immediate interior, so ingestion has only city-scale
places to mint, and `_opening_scene_place` (`game.py:2034`) — which anchors on
the protagonist's opening-horizon location — inherits the city. Adventure and
mystery worlds mask this; it only surfaces on an intimate shape, which is exactly
why the founder asked for varied-shape testing.

## The fix: TWO halves — author the interior, and select it deterministically

Cx 490 (spec review) verified against the archived `probe_romance` artifacts that
the prose lever ALONE is not robust: PB's `locate()` returns the FIRST-inserted
row among same-timestamp co-asserted `in` rows, so a generated chapter can obey
the new prose instruction and still lose the room if extraction emits a coarse
setting row *before* the room row in the same chunk. So #109 is:

- **(A) Author the interior** — a `bond` author-channel signature element so the
  generated fiction grounds the immediate interior at ROOM granularity and opens
  inside a specific named room; and
- **(B) Select it deterministically** — an opening-place SPECIFICITY backstop in
  `_opening_scene_place` so, when the protagonist is co-asserted at several places
  at the opening horizon, the most-specific interior wins over `locate()`'s
  first-inserted pick. Without (B), (A) is a coin-flip on extraction row order.

### Half A: one author-channel signature element on the `bond` shape

The story-shapes layer already carries per-shape **author-insist** signature
elements (`SHAPE_SIGNATURE`, `story_shapes.py:163`) that flow into the
world-generation prose author via `author_signature_directive(game_types)` —
already computed and passed as `signature_directive` in
`create_scenario_from_generated` (`game.py:1554`). **No new plumbing:** add one
author-channel element to the `bond` shape and it rides the existing directive.

New element on `SHAPES["bond"]` → `SHAPE_SIGNATURE["bond"]`:

```python
{"name": "the_grounded_interior", "channels": ("author",),
 "element": "the intimacy lives INSIDE named rooms of a home or shared venue — "
            "author the immediate interior at ROOM granularity (a kitchen, a "
            "sitting room, a bedroom, a hallway, a studio, a cafe's back room) and "
            "OPEN the story inside one specific named room with the protagonist "
            "there, never at street, neighborhood, or city scale; a bond is built "
            "in a place small enough to share"},
```

Element-text note (Cx 490): the examples are all genuine ROOMS — no "shared
table" (it extracts as an `obj:`/`place:long_table`, not a room anchor) and no
bare "stoop"; the anchor must be an enclosing interior.

### Why `bond` covers the whole domestic band (and only it)

`signature_elements()` unions the **primary + secondary** shapes
(`story_shapes.py:281`). The `bond` shape is:
- the **primary** for the "Social, Relationship & Intimacy" family (romance,
  relationship webs) — `FAMILY_SHAPE`, `story_shapes.py:67`; and
- the **secondary** for "Moral, Psychological & Literary Drama"
  (`FAMILY_SECONDARY`, `story_shapes.py:90`) — so literary/psychological dramas
  union the element in too.

So a single `bond` element grounds romance AND relationship/psych drama. It does
NOT touch **pure non-bond** worlds (deduction/endurance/contest/gambit/discovery/
mastery) — the traversable-geography shapes that (correctly) want connected
locations. **It DOES apply, by design, to any MIXED world whose blend includes a
bond-shaped type** — `shapes_for()` folds a later type's primary shape into the
secondary set (`story_shapes.py:388-396`), so e.g. `deduction + romance` unions
`bond` in and receives the element. That is correct: a mystery-romance still wants
its intimate scenes grounded in a shared interior. Farce is often interior too,
but the measured signal is romance-specific; leaving farce out (it maps to
`farce`, not `bond`) is the conservative call — add it only if a farce probe
reproduces the gap.

### Half B: the opening-place specificity backstop (Cx 490 blocker)

`_opening_scene_place` resolves the opening tableau to **the protagonist's
location at the opening horizon** (`game.py:2036-2047`) via `locate()[0]`. But
`locate()` collapses same-timestamp co-asserted `in` rows to the FIRST-inserted
one — so even a correctly room-grounded chapter loses the room if extraction
emitted the city row first (Cx verified this on the archived `probe_romance`:
Marta is co-asserted `in place:lisbon` / `place:campo_de_ourique` /
`place:pastelaria_estrela_do_norte` at one timestamp, and `locate()` returns the
city).

The backstop (`_specific_opening_place`, called only inside the horizon branch):
1. `_live_in_candidates(world, prot, as_of)` — the protagonist's co-asserted `in`
   places at the current state layer (rows at the max `valid_from ≤ as_of`).
2. Score each by `_place_specificity` = **(non-coarse kind?, containment depth)**:
   a non-coarse kind (room/cafe/hall) outranks a coarse settlement/region
   (`_COARSE_PLACE_KINDS` — city, neighborhood, district, region, country, …);
   deeper containment breaks ties.
3. Return the most-specific candidate **only when it is a STRICT improvement** over
   `locate()`'s pick (never make the anchor coarser). Single-candidate and
   no-improvement cases return `locate()[0]` unchanged — **backward compatible**;
   non-domestic worlds are untouched.

This is a read-only selection over shipped porcelain (`state`/`locate`/`facts`) —
no grammar change, no new write, no engine work. Verified on the archived romance
world: the backstop now anchors to `place:pastelaria_estrela_do_norte` (the cafe)
instead of `place:lisbon`.

**The existing staging fallbacks do NOT cover this gap** (so Half A is
load-bearing, not redundant): the bare-world backstop (`game.py:597-615`) and the
play-as staging (`game.py:712-736`) only place a person onto an *already-minted*
place — neither mints a missing room. They put people on the map; they cannot
invent the room granularity the prose never authored. Half A creates the room;
Half B makes sure the opening actually anchors to it.

## Non-goals / out of scope

- No change to traversable-geography shapes (they keep connected locations).
- No engine work — pure host control data + prompt text (Half A) and a read-only
  porcelain selection (Half B). No grammar change, no new canon write.
- Half B never makes an anchor coarser and is inert for single-candidate worlds,
  so non-domestic worlds are byte-for-byte unaffected.
- No live-play re-run in this slice — the fiction re-verify (a fresh romance
  build that stages the protagonist at room granularity) is the acceptance
  evidence, run after code + Cx GREEN, logged to the founder.

## Test bar

- **Unit — signature scoping (deterministic):**
  `signature_elements(["romance"], "author")` and
  `author_signature_directive(["romance"])` include `the_grounded_interior`;
  `signature_elements(["mystery_whodunnit"], "author")` (pure deduction) does
  NOT; a relationship/psych-drama type (transformation + bond secondary) DOES
  include it. **Mixed blend:** `["mystery_whodunnit", "romance"]` DOES include it
  (bond is folded into the blend's secondary set by design). Guards the shape-band
  scoping AND the mixed-blend inclusion.
- **Unit — the backstop (Cx 490 blocker guard):** ingest a protagonist co-asserted
  at a coarse `place:lisbon` (kind `city`, inserted FIRST) AND a `place:kitchen`
  (kind `room`, `in place:lisbon`) at the SAME `valid_from`; assert
  `locate()[0] == "place:lisbon"` (the collapse) but
  `_opening_scene_place(...) == "place:kitchen"` (the recovery). Plus a
  single-candidate world returns `locate()`'s pick unchanged (backward compat).
- **Acceptance (live, post-GREEN):** a fresh romance rebuild stages the
  protagonist at ROOM granularity (a place contained within the home/venue) and
  the opening tableau anchors to a room/interior, not a city/neighborhood/street;
  a live transcript shows the opening and first response do not change room or
  time without movement. Logged to the founder.
