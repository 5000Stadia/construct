# Wiring the build library: construct's side of registry-first seeding

**Status:** spec r2.1, cr GREEN. **Built** on engine pin e3101a4 (BUILD-LIBRARY-V1 r1.8.3, `identity_time='gate'` the default), 2026-10-14; at cr for code review.

**Build notes (where the build refines the text):**
- **The title chunk is folded into chapter 1** (`seeding.text_by_chapter`). `_chunk_chapters` puts a generated story's `# Title` line in a chunk of its own. Numbered as written, the story's first chapter would be chapter 2, stamped at 2 × SOURCE_STEP, above `opening_as_of`. With gate-stamped identity, the whole chapter-1 cast would then be invisible at the opening. Today's per-chunk path has the same offset, which rule 4's "chapter 1 keeps the band below `opening_as_of`" rules out for the library path.
- **Rule 7's `reject` lives in the build module** (`game._hold_manifest_namesakes_apart`). `construct/seeding.py` only lists the pairs (`same_named_entry_pairs`), because R34 P1 keeps identity verbs in `construct/game.py` (test_identity_play_guard).
- **The code lives in `construct/seeding.py`.** `game.create_scenario_from_ingest` branches on the switch, and the existing build tests run with `CONSTRUCT_BUILD_LIBRARY=0` (an autouse fixture in tests/conftest.py).

**r2 (cr RED on r1):**
- P1: the library's `commit()` writes every manifest identity row (shape, name, alias, role, persona names) **timeless**, before the facts. So a late entry, or a persona's true name, is canon-visible at the opening, and r1's opening-horizon test couldn't pass. r2 makes gate-stamped identity a precondition, asked of pattern-buffer (colony m3310d2, 2026-10-14), not a construct-side filter.
- P2: Stage 3, the traversal policy, is kept explicitly.
- The `mention:` exception is pinned to the exact code path.
**Source:**
- The settled design, SEEDING-REGISTRY-FIRST.md r4: Kabe's gate g2fd391 answered; two consult rounds.
- pattern-buffer's BUILD-LIBRARY-V1 r1.7: merged at 6073bfe, docs at 958691d, pbr GREEN. Construct was GREEN on its spec.
- The library surface was mapped read-only on 2026-10-14. Moving from engine 9e0620f changes no porcelain API (`git diff` touches only the new `patternbuffer/build/` package).

## Amendment r2.2: adopting BUILD-LIBRARY r1.9.1 (pin pattern-buffer c4a8eba; spec for cr review, not built)

**Why now.** R20 run 13's first build (archived as `run13a`) stopped at Stage 1. Three of its six chunks were refused for "handles: declared but not used", and chunk 0 again on its retry. Run 12 had one such refusal and passed on retry. Under r1.9.1 the library drops an unused declared handle with a typed receipt instead of refusing the chunk.

**The pin.** pattern-buffer `c4a8eba`. Its engine source is identical to `30c5ede` (BUILD-SPEED-V1). It carries BUILD-LIBRARY r1.9.1, BEATS-V1 r1.1 and RECIPE-VOCAB-V1, all merged and pbr GREEN. ONE-LOCATION-V1 is **not** in it: that code lives on pattern-buffer's `feat/one-location` branch, waiting on Kabe's metered check. Main's suite is run against `c4a8eba` before the pin.

**The changes:**
1. **One retry owner.** `extract(..., retries=1)`: the library re-asks a chunk whose returned answer refused it. Construct re-runs a chunk itself **only** when `len(result.attempts) == 1 and result.attempts[0].raw is None`, meaning exactly one call, and it raised. pattern-buffer's precise test, m8d16d6: an error text such as "model call failed" can also follow the library's own retry. So no chunk is ever retried twice. A chunk still in error after that stops the build with its first cause, as today.
2. **Dropped handles are logged, not stopped on.** A dropped handle is one no accepted line used, so it carries no fact. Nothing about a manifest entry is lost, so there is nothing for a load-bearing stop to protect. Construct logs every `DroppedHandle` (chunk, kind, name, candidates) at INFO and counts them in the Stage 1 line ("…N dropped handle(s)"). The "load-bearing pick" stop discussed with pattern-buffer is not adopted, for this reason.
3. **Nothing else changes.** The extraction prompt is byte-identical (r1.9.1). `vocabulary` is not passed; RECIPE adoption waits on g8f1157 and a metered check.

**Tests:**
- a chunk that refuses once and is accepted on the library's retry builds, with two attempts and no construct re-run;
- a chunk whose single call raised is re-run once by construct;
- a chunk refused, retried by the library, and refused again is not re-run by construct (two attempts), and the build stops with its cause;
- an answer that declares an unused handle builds, with the dropped handle logged and counted;
- the full suite on `c4a8eba`.

## What changes, in one paragraph

Today every chunk's extraction call invents its own ids, and stage 2 repairs the result afterwards (merges, retypes, homonym rejects, `_2` remaps). With the library:
- the story's author lists the cast as a **manifest**;
- code mints every id from it;
- each chunk's extraction sees only the candidates known by then (a per-entry time gate);
- an ambiguous mention lands on a provisional `mention:` id, with a proposal;
- one serial writer commits it all.

So identity is decided once, by code.

## The rules

**1. The engine pin moves to pattern-buffer 958691d** (or a later commit, if CONTAINMENT-DURABILITY-V1 has merged by build time; the build note names the exact pin). `engine.pin` and the `.venv` install move together. The full suite is run before any wiring.

**2. `author_story` returns the manifest.**
- Its schema gains `manifest`, in the library's JSON shape (`Manifest.from_dict`):
  - `entries[]`: `key`, `type` (from the library's closed `TYPES`), `names` (canonical first), `anchor_quote` (one whole sentence, verbatim, where the entry first appears), `role`, `species`, and `personas[]` (`name`, `intro_quote`, `reveal_quote`);
  - `namesakes[]`: `[key_a, key_b, anchor_quote]` for same-named entries the author means as different beings.
- **The prompt asks for the list after the prose,** like closing credits (r4 §1: "the registry describes the story; it never directs it"), and for quotes copied as whole sentences.
- **The manifest is saved beside the prose,** on the authoring side of the firewall (`<name>.manifest.json`). The player never sees it.

**3. Validation, then a single repair, then a fallback.**
- `Registry.from_manifest(manifest, text_by_chapter)` validates it.
- On `ManifestError`, **one** repair call (the main tier) gets the prose, the manifest and the full `.problems` list, and returns a corrected manifest.
- If that fails too, the build falls back to `category_passes(text_by_chapter, model)`, the library's own manifest for prose with no author. It is logged as `manifest_fallback`.
- **Imported prose** (`create_scenario_from_ingest` with no saved manifest) takes `category_passes` directly.

**4. Chapters and time.**
- `text_by_chapter` = construct's existing `_chunk_chapters(text)`, numbered from 1. Paragraphs are already separated by blank lines.
- The library's `plan(text_by_chapter, registry, max_words=…)` does the chunking. `max_words` is set at or above the largest chapter, so a chapter normally plans as one chunk, split only before a reveal sentence.
- **`time_of(i) = chunk.chapter × SOURCE_STEP + k`**, where k is the chunk's index within its chapter (0, 1, …). So chapter 1 keeps the band below `opening_as_of` (`SOURCE_STEP + ENTRY_MARGIN`), and the play horizon contract (READS-AT-PLAY-HORIZON, `horizon_metadata`) holds unchanged.
- A persona's `correlate` lands at its reveal chunk's time, so it's invisible at any earlier horizon.

**4b. Identities are stamped at their gates: a library precondition (r2).**
- Every entry's identity rows (shape, `name`, `alias`, `role`) must carry `valid_from = time_of(the chunk holding the entry's gate sentence)`, not timeless.
- **Every persona's shape rows** (`kind`, `being_type`, `species`) **and name rows** must carry `valid_from = time_of(the persona's own gate chunk)` (r2, cr): a timeless shape alone would put the persona in `entities(canon, as_of=h)` before its intro. pattern-buffer's r1.8 states exactly this (med4ef1: "each persona's shape and name rows get its own gate's time").
- Then a chapter-3 entry is future-only at the opening, exactly as a future source entity is today. It's absent from `entities(canon, as_of=h)`, from every HorizonView roster, and from construct's identity rule (`is_future_only`).
- **This is pattern-buffer's change** (asked in m3310d2). **The wiring doesn't build until the pinned library provides it.**
  - **Accepted, 2026-10-14 (pattern-buffer med4ef1):** BUILD-LIBRARY-V1 r1.8 makes it the default, `commit(identity_time='gate')`.
    - Each entry's shape, name, aliases, role and fixture rows are stamped at its gate chunk's time.
    - Persona shape and name rows are stamped at their own gate; the correlate stays at the reveal.
    - Escapes and mentions are stamped at their declaring chunk.
    - Rows are still written first by seq; only valid time moves.
    - A CONSTITUTIVE row with a `valid_from` has no value before it, so state at an earlier horizon is unknown.
  - Construct pins r1.8's merge.
- **The fallback, if pattern-buffer keeps identities timeless:** a construct presentation filter from `Registry.entries()` gates, applied to every roster, digest, scene and cast path. cr judges it fragile, so it would need its own spec and review; it isn't adopted here.

**5. Extraction, then commit, inside the existing build session.**
- `extract(chunks, registry, model, workers=8)`, with `model = engine_tier_dispatch(provider)`. The library's pinned heads route by prefix: `EXTRACT_HEAD` ("Extract world-state facts (build library, chunk)") already matches `_CHEAP_ENGINE_PREFIXES`. `CATEGORY_HEAD` ("Name the beings, places and things") is added to them, since category passes are literal sorting, so fast tier (r4 §6).
- **Chunk errors:** the library doesn't retry, and `commit` refuses the whole build if any chunk has `error`. Construct re-runs `extract` on the errored chunks once. If any still has an error, the build stops with the first cause, exactly as today's "every chunk failed" stop does (the build never ships a world with a chapter silently missing).
- **Commit:** `commit(world, registry, results, time_of=…, ingest_kwargs={"classify": "defer", "cursor_authoritative": True})`, inside the existing `begin_build` session. Durability is classified at the seal, as today.

**6. Stage 2 is skipped in library mode** (r4 §5, made concrete). Its passes would undo the design: `reconcile`, `adjudicate_deferred`, `typing_conflicts` retypes and the cross-namespace homonym `reject`. For example, the homonym pass would write `distinct_from` between `mention:rex_1` and `person:rex`, so their later evidenced join could never land. The library already:
- mints namespaces from the closed types (no typing slips);
- joins escapes by code at the serial commit;
- writes the author's namesake `reject`s;
- puts every ambiguity on a provisional id.

The skip is logged as `Stage 2 · identity decided by the manifest (library)`.

**Stage 3 still runs (r2).** `_stage_declare_policy` (the `traversal:<kind>` rules that `route()` reads) is not part of identity, and is kept unchanged in library mode. Only `_stage_reconcile_identity` is skipped.

**7. The author's entries are held apart by code.** After commit, every pair of manifest entries that share a normalised name and aren't already rejected as namesakes gets `reject(a, b)` (a `distinct_from`): the man and the dog called Rex become `person:rex` and `person:rex_2`, types `person` and `dog`. This is P1, the manifest as sole authority on the cast, applied mechanically. **It never touches a `mention:` id or an escape.**

**8. Provisional ids stay out of play and out of the build stops.**
- **Rosters:** every enumeration without a namespace prefix excludes `mention:` ids: `_canon_entity_ids`, the world digest, scope and staging candidates. Prefix enumerations (`person:`, `place:`) already exclude them.
- **Proposals stay open in r1.** The library's `maybe_same_as` proposals (a pick, or an escape colliding with a manifest name) are logged with their evidence and left open. Their facts stay on the provisional id, invisible to play. An evidenced confirm step (the merge gate, on the fast tier) is a later item, sized by what acceptance measures.
- **The identity confirm stage** (R34, `_stage_confirm_identity`). Its stops come from `_identity_stops`, which examines open `frame_owner` proposals and **live name-collision pairs** (it doesn't read `maybe_same_as` proposals at all). A provisional `mention:` id that carries the same name as a manifest entry would therefore surface as a live name-collision pair.
  - **The exact change:** `_identity_stops` (and `_role_kind_pairs`) skip any pair with a `mention:` id on either side.
  - Its facts are quarantined on the provisional id, so the pair is safe to leave open.
  - Nothing else changes: frame-owner proposals and manifest-to-manifest collisions stop exactly as today.

**9. The cast author sees the registry** (r4 §5): `_stage_author_cast`'s known-id list gains each manifest entry's names, type and role, so it reuses "Hester Rook, sergeant" rather than minting a twin.

**10. A switch, until acceptance.** `CONSTRUCT_BUILD_LIBRARY` (default `1`) selects the library path. `0` keeps today's per-chunk path exactly, for a rollback without a code change. Once acceptance passes, the old path is deleted in its own commit.

## Not in this spec

- The evidenced confirm of proposals.
- The `controls` / fixture vocabulary (R56, CONTAINMENT-DURABILITY-V1). They ride the next pin.
- Moving other build stages to the fast tier (eval/13's other levers).

## Tests (stub model, no live calls)

1. **The manifest round trip:** a stub author returns prose plus a manifest; `Registry.from_manifest` accepts it, and the ids are minted by code (`person:rex`, `person:rex_2`), with `kind=person` and `being_type` `person` / `dog`.
2. **Repair, then fallback:**
   - a manifest with a `persona_name_is_alias` problem gets one repair call carrying the problem list;
   - a second bad manifest falls back to `category_passes` (stub), logged.
3. **Rex** (r4's planted trap): the man and the dog stay two entities after commit. They're held apart (`distinct_from`), and both reach `_known_people`, the world digest, the arc inputs and a played scene, with the dog's facts.
4. **Two Brecks:** an ambiguous "Breck" mention the stub extractor resolves to one Breck lands its facts on `mention:breck_1`, with a `maybe_same_as` proposal. No fact lands on either Breck. The roster excludes the mention id. The identity confirm stage doesn't stop the build.
5. **A late reveal and a late entry** (once the library stamps at gates, rule 4b):
   - "the stranger", revealed as the duke in chapter 3; an entry first appearing in chapter 3; and **a persona first introduced in chapter 3** (its intro gate there);
   - **a direct opening-horizon read oracle:** at `opening_as_of`, `entities(canon, as_of=h)`, `_canon_entity_ids` through a HorizonView, the world digest and a played scene's reads contain neither the chapter-3 entry nor the duke's name nor the link;
   - the late persona's **id** and **name** are both absent at the opening (no shape row either);
   - at the head, all of them are present (the negative control);
   - this test gates the library pin.
6. **The time mapping:** chapter-1 facts sit below `opening_as_of`; chapter-2 facts sit at or above `next_source_as_of`. A two-chunk chapter (split at a reveal) gets distinct, increasing times.
7. **Chunk errors:** one chunk errors once and is retried successfully, so the build completes. One that errors twice stops the build with its cause, and nothing is committed.
8. **Stage 2 skipped, Stage 3 kept:**
   - in library mode, no `reconcile` / `adjudicate_deferred` / `retype` / homonym `reject` call is made (spy), and the provisional id has no `distinct_from`;
   - `_stage_declare_policy` runs, and its `traversal:` rows exist.
8b. **The confirm-stage exception:** a `mention:breck_1` that shares the name "Breck" with the hero gives no `_identity_stops` entry. A manifest-to-manifest same-name pair touching the hero, not held apart, still stops.
9. **The switch:** with `CONSTRUCT_BUILD_LIBRARY=0`, the build takes today's path exactly (the existing build tests pass with the variable set).
10. **The full suite** on the new pin, before and after the wiring.

## Acceptance in play

**A live build of the planted-trap story** (Rex, two Brecks, the late stranger; it needs Kabe's or the monitor's yes), with the timing log on. It passes when:
- no fact sits on the wrong look-alike;
- no name is bound before its reveal;
- no repair stage runs;
- build time is reported against eval/13's 474 s baseline.

Then one R20 run.
