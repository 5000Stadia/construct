# Entity Authority — one write path; narration is read-only w.r.t. canon (map-governs)

**Status:** DESIGN (docs-first; pressure-test before engine code). Author: HD. Review: Cx (shape),
then code review. Founder-directed (2026-06-29): *fix the SHAPE, do not append rules to handle a
misshapen set of information.*

## Framing (the founder's correction)
**PB is the object architecture** (the substrate: entities, frames, as-of, the structural ops —
`reconcile`/candidate surface, `merge`/`reject`, a future retype op). **Construct is the engine** that
USES it. Therefore the **object-graph shape during play** — how mentions are coreferenced, typed,
created, and presented — is the **engine's** responsibility, i.e. **ours**. The fix is not "wait for
PB to add a merge pass"; it is the engine producing a clean graph, using PB's object primitives.

## Problem — the misshapen graph is born at three free-text writes
Canon entities are created through several *uncoordinated* write paths. The clean ones are the
engine's deliberate `ingest_structured` decisions (movement/take/drop commits, clue/whereabouts,
fallout). The misshapen ones are the **three free-text `p.ingest(<text>)` calls**:

| site | turnloop.py | what it mints from |
|---|---|---|
| player-input extraction | ~1415 | the player's raw sentence |
| NPC action extraction | ~1780 | an NPC's narrated act |
| **settle narrator-prose extraction** | ~3094 | the **rendered prose** (the original sin) |

Each free-mints a *new* entity per surface mention, with **no shared identity authority and no type
discipline**. PB faithfully stores the result; projection and narration faithfully propagate it.
Observed live (bodycase):
- **Fragmentation:** one pencil → `obj:pencil`, `obj:pencil_1` (take-mint twin), `obj:plain_pencil`.
- **Typing slip:** "street" → both `place:street` AND `obj:street`; `person:X in obj:street`.
- **Voice/deixis phantoms:** `person:unknown_speaker`, `person:narrator`, `person:/you`,
  `place:/coffee_house`.

The current host **band-aids** (promote-gate guards for person-in-object / malformed `:/` /
`*narrator*` holders; render directives exclusive-carry + drop-ack) cope with the misshapen graph
*after* it forms. That is the rule-stack the founder is rejecting (= Kernos 078's "rule-stack is the
symptom, shape is the bug"). They must be **retired** once this lands (Kernos 084: verified-then-strip).

## Principle
**Map governs narration; narration never writes the map.** Canon mutates only through structured
engine decisions. New diegetic objects/places enter canon ONLY through **one typed, coreference-aware
minter** shared by every path. Re-mining structured facts out of *rendered prose* is the original sin.

## Design

### 1. The resolver (engine-owned; `construct/resolve.py`)
`resolve_or_mint(world, mention, *, channel, scene_ctx, protagonist, at) -> entity_id | None`
A single seam every entity-write consults. In order:
1. **Malformed** (empty / leading-`/` local-part) → reject (None). *(was bucket 4a)*
2. **Voice / non-referent** (narration voice: narrator/speaker/unknown-voice) → None; never an entity.
   Voice is a *frame*, not a thing. *(was bucket 4b)*
3. **Deixis** ("you"/"I"/"me"/"myself"/"self") → the protagonist. *(was bucket 4c)*
4. **Coreference — bind to a KNOWN entity.** Match the mention against the live candidate set
   (scene entities ∪ protagonist-held ∪ present cast ∪ recently-introduced) via the identity matcher.
   A **unique high-confidence** match binds; the existing entity's `kind` is authoritative (no retype).
5. **Typed mint — only if genuinely novel AND plausibly present.** Mint ONE entity with the `kind`
   the **channel** dictates (move → `place`; take/drop/handle → `obj`; cast → `person`). One referent,
   one id, correct kind. *(kills `place:street` vs `obj:street`)*
6. **Else** → None: no canon write; the narrator handles it diegetically (improv that isn't acted on
   stays prose, not canon).

The matcher (step 4) reuses the cheap whole-token `_names_entity` against the live set; the harder
cross-chunk cases are reconciled AFTER THE FACT by PB's `reconcile()` — a host-invoked global
finalize pass, never a per-mention lookup (NOT reimplemented, and never called live).
Bind requires a UNIQUE match — ambiguity yields NO canon write (never a sibling), per the LOCKED
DECISIONS below. Zero candidates + a sanctioned kind → typed mint; multiple → drop.

### 2. Narration read-only w.r.t. canon (the settle change, ~3094)
Two candidates — **recommend (B)**:
- **(A) Drop prose-extraction-as-canon entirely.** Cleanest map-governs, but loses passive improv
  permanence ("the drawer's papers" the narrator mentions never persist unless acted on). Too lossy.
- **(B) Keep prose-extraction, but route every proposed (entity,attr,value) through the resolver**
  before the promote gate: entities bind-to-known or mint-typed, voice/deixis resolved, malformed
  dropped. The promote gate keeps ONLY its arc-key contradiction guard (protects the hidden answer);
  the pattern band-aids (person-in-object / malformed / narrator-phantom) become **unreachable** and
  are deleted. Preserves "a mug from the bar exists" while killing fragmentation at the source.

### 3. Unify the deterministic minters (kills twins)
`_grant_taken_object` / `_grant_moved_place` currently mint independently → twins. They call
`resolve_or_mint`: a take/move first **binds** an existing scene entity when one matches (no
`obj:pencil_1`), mints typed only when novel. The take-mint and prose-extraction now share the
resolver → one pencil. `_mint_held_object` becomes the resolver's mint step (kind from channel).

### 4. PB (object architecture) vs Construct (engine) — the line
- **PB provides:** entity storage, frames/as-of, `reconcile` + candidate structure, `merge`/`reject`,
  (future) retype. The engine USES these.
- **Construct owns:** WHEN to resolve, the coreference decision against the *live scene set*, the
  typed mint, deixis/voice handling — i.e. the *use* and the *meaning*. This honors Kernos 083's split
  (structure-decidable → PB primitives; meaning/use → engine) and 084 (voice-suppress is engine-use).
  Because the engine mints *correct-from-the-start*, a retype op is not needed at the write boundary.

## DELETED on live-verify (Kernos 084 / Cx 313 verified-then-strip — DONE)
STRIPPED from the promote gate (the resolver subsumes them upstream — live-proven `quarantined`
empty on all 7 bodycase turns): `_malformed_id`, `_is_narrator_phantom`/`_VOICE_PHANTOM_TOKENS`, the
pronoun-phantom check, and the person-in-object quarantine. The predicates now live solely in
`construct/resolve.py` (`is_malformed`/`is_voice`/`is_deixis`).
KEPT (NOT resolver-subsumed, Cx 313): the **held-object guard** (the resolver does not know live
inventory or same-turn drop licensing); the **arc-key/contradiction gates** (concealment/canon-diff
policy, a different layer); the **render directives** (`WHAT YOU ARE CARRYING` exclusivity + `JUST SET
DOWN` — prose-input discipline, not canon truth; kept while the residual cross-scene pencil twins
persist, pending PB bucket 1). `_NARRATOR_PHANTOM`/`_PRONOUN_PHANTOM` constants stay — the
deterministic take/drop guards still use them. Plus the deterministic player actions (now twin-free)
and the bucket-3 semantic-residue seam.

## Risk
Over-binding (mis-merging a genuinely-new entity into an existing one). Mitigation: bind only on a
UNIQUE high-confidence match; ambiguity → NO canon write (never a sibling, never a fresh mint). The cohesion scenarios (pencil twin, street
typing, voice phantom) become the regression set, unit + live.

## LOCKED DECISIONS (Cx 304 shape review, YELLOW → folded — build against these)
1. **Ambiguity NEVER mints.** unique high-confidence match → **bind**; **zero** candidate + channel
   sanctions novelty + plausibility → **typed mint**; **multiple** candidates → **no canon write**
   (drop/underdetermined; narrator handles). Definite/ambiguous mentions ("the pencil", "the office")
   must never mint a third sibling — only a zero-candidate indefinite introduction ("a mug") mints.
2. **`extract → resolve → ingest_structured`, never `ingest → fix receipt`.** Use PB's read-only
   `porcelain.extract(text, scene, extract="lean")` (confirmed present, no write) → the resolver
   rewrites/drops rows → `ingest_structured(resolved_rows)`. Construct is the identity/type authority
   BEFORE rows touch canon; PB stays the append-only gate. (Post-render may still stage in `_PROPOSED`
   for the contradiction diff, but extraction is read-only first.)
3. **Resolve BOTH row positions** with kind expectations. The resolver rewrites `row["entity"]` AND,
   when `value_type=="entity"` or the attribute is entity-valued, `row["value"]`. Kind constraint by
   subject·attribute: `person:*.in` expects `place:`/`person:`, never `obj:`; `obj:*.in` may be
   protagonist/place/real-container by channel. If EITHER side resolves to None → **drop the whole
   row** (no half-repaired facts). This is what makes the person-in-object/malformed/voice guards
   *unreachable*, not relocated.
4. **Map-governs = option B, tightened:** rendered prose is NOT authority; extracted/render-delta rows
   are PROPOSALS; only the resolver + promote gate turn them into canon.
5. **Matcher = hybrid, bounded:** cheap whole-token (`_names_entity`) over a DELIBERATELY BOUNDED live
   set first (scene/place-chain, scene contents, scene features, protagonist-held, present cast, recent
   same-turn intros); PB `World.refer(scope=bounded_ids, as_of=_h)` only where the channel tolerates
   tier-2 (player take/move/examine targets). **Never** `porcelain.reconcile()` per mention (it's a
   global finalize pass, not a live row resolver).
6. **Locus = new `construct/resolve.py`**, returning `(entity_id|None, reason)` where reason ∈
   {bound, minted, dropped_voice, dropped_malformed, deixis_bound, ambiguous, novel_denied,
   kind_mismatch, …} for live debugging. `turnloop.py` assembles `scene_ctx` and calls it.
7. **Confidence:** bind only on a unique deterministic match OR PB `refer` resolved above its floor.
   Ambiguity calls **no** model and **never** mints. Post-render narrator proposals: deterministic
   bind/drop in v1 (model-aided disambiguation deferred until proven necessary + traceable).
8. **No PB retype dependency.** PB lacks a first-class pre-write retype API; mint-correct-from-start
   or drop. (PB provides identity closure, `refer`, `reconcile`, proposals, guarded `merge`, `reject`.)
9. **Verified-then-strip, staged:** FIRST move malformed/voice/deixis/held-ownership logic INTO the
   resolver and invert the old guard tests around the new path; DELETE the promote-gate guards +
   render directives (exclusive-carry/drop-ack) only after focused tests + one live bodycase run show
   the resolver is why they no longer fire (Kernos 084).

### Cx 306 refinements (folded — re-review)
- **Ambiguous take never mints:** the take caller mints ONLY on `bind_or_mint` → `_why == "mint"`;
  `ambiguous`/dropped → no canon write + a `trace.resolver` receipt.
- **No retype of an existing entity:** a `kind` row whose subject BOUND to a known entity is dropped
  (`bound_kind_skipped`) — kills the cross-prefix `{place:street, kind, object}` retype.
- **Free-text never mints a place:** `_FREE_TEXT_MINT_KINDS = {obj, person, fact, event, doc}` — a
  novel `place:` from prose is dropped (`novel_denied`); the deterministic MOVE channel is the sole
  place-minting authority (`bind_or_mint(kind="place")` still mints).
- **A place-like `obj:` is a mistyped place → denied (Cx 308):** a zero-candidate free-text `obj:`
  whose declared KIND is in `_PLACE_LIKE_KINDS` (street/road/room/office/…) is dropped
  (`place_like_obj_denied`), so `obj:street kind street` can't mint and reform the split. Judged on
  the KIND value only (NOT id-stem — `obj:office_key` is a real object). Interim host typing signal
  pending PB's engine retype path (Kernos 083 bucket 2). Together with the above, the place/obj split
  cannot form from free text.
- **Same-kind bind guard (Cx 308):** `_match_one` compares the bare namespace (`person`/`obj`/`place`,
  no colon — the colon comparison was dead). `obj:`↔`place:` cross-binds (the typing-slip retype);
  `obj:`→`person:` does NOT (would write object facts onto a person).
- `trace.resolver` APPENDS across all sites (player-input/NPC/settle), never overwrites.

### Cx 415 amendment — first-mention permanence (#98, built 2026-07-04)
The founder's robot-vacuum ruling: a proper-named detail the WORLD establishes ("The
Hart and Bell") becomes solid immediately as a minimal STUB; engagement paints the rest.
- **`is_proper_named(name)`** — resolver-side predicate (NOT the session display helper):
  strip an optional leading article, then every significant token must be capitalized
  (connectives `and/of/de/…` may stay lower). Case is the evidence → a lowercasing
  extractor fails CLOSED. Accepts "The Hart and Bell"/"John Johnson"/"Dr. Ames";
  rejects "the street"/"the wrapped crown"/"the landlord of the Hart and Bell".
- **Narration channel only:** the settle site passes `_NARRATION_MINT_KINDS`
  (obj/fact/event/doc — person LEFT the free set on this channel) +
  `_NARRATION_STUB_KINDS` ({place, person}). Player-input (`Bradford Clemense` pin)
  and NPC-action channels untouched.
- **Stubs are minimal, non-present** (`_STUB_ATTRS`): place → kind/name/(`in` iff the
  container BINDS to an existing place); person → kind/name/role/title, never `in`.
  Everything else trims (`stub_trimmed`). A stub NEVER enters the VALUE position
  (`stub_value_denied`) — no relocation/presence effects through the stub gate.
- **Roster-wide bind-before-mint:** the settle candidate set unions every NAMED canon
  `place:`/`person:` (horizon-safe), so a second mention scenes away BINDS instead of
  minting a twin. Ambiguity still drops.
- **Live probe (2026-07-04, letter 442):** the lean extractor DOES surface the
  mentions (no PB routing needed) but emits NO `name` rows — the cased evidence never
  arrived. Fixed host-side: `resolve.reconstruct_names(rows, prose)` recovers the
  id-stem's cased span from the prose verbatim and injects a SYNTHETIC name row;
  `is_proper_named` judges the real casing (fail-closed: no span → no stub).
  Synthetic names commit ONLY with a stub mint (`synthetic_name_skipped` on bound
  entities). The probe's own over-production validates the gate: "Brackenmere
  village"/"coach yard" reconstruct lowercase and stay denied.

### Required regression pins (Cx 304)
- player-input names "plain pencil" while scene `obj:pencil` exists → binds, no `obj:plain_pencil`.
- take after passive prose "a mug" → binds the same mug, not `obj:mug_1`.
- move vs take channel mints `place:` vs `obj:` for "street", never both.
- entity-valued repair/drop: `obj:pencil in person:unknown_speaker`, `person:/you in place:/coffee_house`,
  `person:you in obj:street` never reach canon.
- ambiguous known candidates → no fresh third entity.
- protected arc-key quarantine still wins after resolver rewriting.
- terminal/curtain prose still mints nothing.

## Open questions for Cx (shape review) — RESOLVED in 304, see LOCKED DECISIONS above
1. **(B) vs (A)** for narration-as-canon-source — confirm (B) (preserve improv permanence, route
   through resolver) is the right call, or is full map-governs (A) cleaner long-term?
2. **Matcher:** cheap token `_names_entity` against the live set vs per-mention PB `reconcile`
   (heavier). Hybrid (token first, reconcile on ambiguity)? Latency vs accuracy.
3. **Resolver locus:** new `construct/resolve.py` consulted by every write, vs inline in the loop.
4. **Bind confidence threshold** (when does a mention bind vs mint) — and whether ambiguity should
   ever ask the model (bucket-3-style) or always mint-fresh.
5. Anything PB-architecture-side this assumes that doesn't exist yet (so we route it correctly).
