# Awareness & Shape — design report

**Status:** under mesh round-robin review (K → Cx → PB; kickoff: Kernos
`dev_inbox/037-from-c-roundrobin-awareness-and-shape.md`). Founder-directed
design; this is the durable record. Nothing here is built yet — it's the
*what-to-build + who-builds-it* brief.

## Theme
Get the right information into frame **exactly when it's relevant**, and let the
data **shape follow the fiction** — with **retrieval that returns the same answer
regardless of which shape was chosen.**

## Governing principle (the host/engine wall)
- **Engine (pattern-buffer)** owns *what shapes exist and how to retrieve across
  them invariantly* — storage shapes, the relations, the union/inverse/as-of
  reads.
- **Host (Construct)** owns *which shape fits this moment and what it means* —
  read the fiction, choose the shape, decide what's pinned/critical, set salience,
  narrate.
- **Litmus:** would a different host (D&D tracker, life-assistant) still need it? →
  engine. Requires knowing what the *fiction* means? → host.
- **Corollary (decisive):** the retrieval-invariance guarantee can only be made by
  the owner of storage + reads — the engine. The host can't provide it without
  reimplementing engine internals. So most load-bearing mechanism is engine-side;
  Construct proves the need and supplies the meaning layer.

## Elements & ownership

**1 · Pinned universals (scoped, with a salience lifecycle).**
Always-in-awareness world conditions, *scoped* by region (containment ancestry),
time (valid-time window), or presence (scene contents). Salient while live, recede
to history when the window closes. `awareness = scene-reads ∪ scoped-pins`.
- Engine: scoping substrate exists; maybe a containment-chain pin-inheritance
  read. **New primitives:** continuous/time-derived **quantities** (rates) and
  **non-monotonic/looping time**.
- Host: pin marker, salience-as-scope-proximity, briefing, lifecycle.

**2 · Knowledge-as-object (who-knows, when the info matters).**
For critical facts the query is "who's aware?" — info-anchored beats frame-
membership on space + retrieval. Fork for PB: stored `known_by` edge (membrane
question) vs a computed **inverse read** over frames (membrane-clean).
- Engine: representation + who-knows read. Host: which facts are critical.

**3 · Polymorphic identity (keystone — resolves the reveal gap).**
Keep the mysterious-figure and the real person as separate entities; at the reveal
**append a valid-timed correlation** (not a destructive merge). As-of-before =
mystery intact; as-of-after = correlated. Needs a **third identity relation** —
non-collapsing **`aka`/correlation** (between `same_as`-collapse and
`distinct_from`-separate) — plus a **correlation-union read** (mirrors
`knows:O ∪ public`) for retrieval-invariance. Handles reveals, dual personas,
amalgamation. *"The unknown of identity," sibling to RFC-002.*
- Engine: the `aka` relation + union read + valid-timed reveal. Host: when to
  correlate / which shape / narration.

**4 · Dynamic world-graph (saloon hole; dug burrow).**
Edges/places created/destroyed mid-play. Mostly already engine-supported
(valid-timed `connects_to`, runtime entities, route-as-of, blocked-passage). Open
part: the structure-choice (place vs feature) = element 3's polymorphism over
places.

**5 · Structure-polymorphism + retrieval-invariance (cross-cut).**
Engine offers entity/feature/facet/correlation as first-class shapes and
guarantees retrieval is shape-invariant; host picks the shape from the fiction.

## Related but separate
`route() no_path` / adjacency = *extraction-completeness* (the connection map is
drawn with cross-chunk holes), not a shape question. PB's ingest extractor +
Construct's chunking.

## Asks by owner (draft, pending the round-robin)
- **Engine (PB):** `aka` correlation + union read + valid-timed reveal · who-knows
  inverse read + membrane ruling · structure-polymorphism + invariant reads ·
  continuous/time-derived quantities · non-monotonic time · maybe scoped-pin
  containment-inheritance.
- **Host (Construct):** the pinned-awareness layer · shape-choice heuristics at
  extraction/turn time · writing dynamic edges/places (mostly done) · adjacency
  extraction-completeness.
