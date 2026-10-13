# Seeding, registry first: identity decided once, by code

**Status:** r4, 2026-10-13. r4 folds in round two of the fresh views (consult c33a2ae). Earlier: Kabe answered gate g2fd391 ("Full agree on your 5 directions"): points 1, 2, 3 (pattern-buffer's form) and 5 accepted, point 4 rejected. The settled approach is the section below. Round two of the fresh views checks it before any build. Not built. It changes pattern-buffer's ingest and identity, so it is co-designed with pattern-buffer and goes to two fresh views from other model families before anything is built. The baseline numbers come from the first run with the timing log (`CONSTRUCT_TIMING_LOG`, feat/timing-log).

## Kabe's direction (2026-10-13)

- "things that are literal name matching that don't have any nondeterministic discernment should be programmatic and not an LLM call. We should consider in our shape how many of these things we can establish as programmatic reference items as early as possible. And we should be able to do so in a way where a Rex person and a Rex dog are initially and immediately identifiable in separation."
- "I have an ignorance that I have not looked under the hood of the structure and allowed the history of this development to be pretty much naturally evolving by LLM Design decisions, The weakness I feel should be addressed now before moving forward is a more elegant architectural method to improve the time of this kind of a pass because it is so foundational to the initial seeding of a new world story"
- "there may be a difference in cognitive complexity ... save a detailed higher order of thinking nuance to hire models, but identify what literal category analysis ... which can be handled by literally the fastest model in probably a process that can mass group work in a single turn batch"
- "everything I'm discussing is when construct establishes a fresh story ingested into pattern buffer that length of duration for preparation before the world is available to the user"

**The target:** the build, from a fresh story to a world the player can enter. About 15 to 20 minutes in R20 run 9.

## r3: the settled approach (gate g2fd391)

1. **The author's manifest is the sole authority on the cast** (accepted P1).
   - **Generated story:** the story-authoring call returns, after the prose, the entries (name, kind, aliases), the namesake pairs it intends as different people, and its secrets (persona A, persona B, the sentence that reveals them).
   - **Code checks it against the prose:** where each alias first appears, which chunk each reveal sentence falls in, and capitalised names no entry covers.
   - **Imported prose:** category passes (beings, places, things, groups) only check or extend a manifest; they never compete with it.
2. **Identity is written before any fact** (accepted P2).
   - **Code mints the ids** from manifest entries: readable and type-prefixed (`person:rex`, `animal:rex`, `person:john_2`), with the R51 type fact as the authority (P4 rejected).
   - **Namesakes** the author lists as different get `distinct_from`.
   - **Hidden identities** are two entries plus one `correlate` (a dated `aka`), dated to the reveal chunk. The two ids never collapse, and the link shows only from the reveal onward.
   - **Never** a `distinct_from` between two personas of one secret.
   - **A secret the prose never reveals** belongs to the arc, not the build.
3. **Mentions are resolved in code.**
   - A multi-pattern scan over the manifest's names and aliases tags each mention.
   - A unique name resolves directly; a shared name becomes candidates. Only names known by that chunk count (time gate).
   - Each chunk's extraction gets the prose so far, the entries known by then, and the tagged chunk. It attaches facts to entries, picks among candidates, and flags unknown entities as new.
4. **Ambiguity is append-safe** (accepted P3, pattern-buffer's form).
   - An unresolved mention's facts go on a provisional id, filtered out of rosters.
   - When evidence settles it, a single explicit, evidenced `same_as` joins it. Nothing is rewritten.
5. **Acceptance runs on planted-trap stories** (accepted P5): Rex the man and Rex the dog, two Brecks, a late-revealed stranger. Pass means:
   - no fact on the wrong look-alike;
   - no name bound before its reveal (GRADE-LEAKS-V1);
   - no repair calls in the normal path;
   - stage time measured with the timing log.
6. **Ownership is the r2 split.** pattern-buffer promotes INGEST-V2 to the shared library. construct supplies the authored manifest and the calls into the library.

## r4: round two's checks, folded in (consult c33a2ae)

Round two (claude-opus-5-5 and gpt-6.1-sol, both at max effort) checked r3 against the code. Its closing instruction was "fix what the checks found that holds up, and go on". All five hold up:

1. **The time gate is per entry, not per string.**
   - The manifest gives each entry its entry anchor: the sentence where that being first appears. A chunk's candidates are the entries that have entered by then.
   - A reveal is anchored to its sentence. A reveal falling mid-chunk splits the chunk there, so nothing before the sentence sees the link.
   - Tests: a namesake who enters mid-story (Rex the dog in chapter 6); a duke mentioned before the stranger's reveal; a mid-chunk reveal. Each chunk's candidate set is logged and GRADE-LEAKS-V1 is run.
2. **Secrets are checked by code.** No secret persona's name may also appear as a plain alias of an entry, or the scan would bind it from its first appearance and leak it. The manifest validator refuses that. Test: a late-revealed nickname ("the Crow").
3. **Beings stay in `person:`; no `animal:` namespace** (corrects r3; this is the "person: read as being" plan that rejecting P4 keeps).
   - construct branches on the `person:` prefix in about 70 places, including the scene's NPC list (`turnloop.py`), the arc inputs (`game.py`) and the world digest. A dog under `animal:` would silently vanish.
   - So Rex the man and Rex the dog are `person:rex` and `person:rex_2`, with types `person` and `dog` (R51's type fact as the authority).
   - A provisional id for an unresolved mention gets a neutral prefix that claims no type (for example `mention:`), filtered out of rosters.
   - Tests: the Rex fixture through ingestion and the whole of world preparation; both survive, with the dog's facts, into the arc inputs, the digest and a played scene.
4. **A model's pick between candidates is evidence, not identity.**
   - Only a unique-candidate resolution in code writes facts directly onto an entry.
   - A mention with several candidates gets a provisional id even when the extractor picks one. Its pick is recorded as the evidence on a proposed `same_as`, which a later, evidenced decision accepts.
   - Test: force the extractor to pick one Breck for an ambiguous mention; the facts land on the provisional id.
5. **Stage 2 is scoped.**
   - The reconcile's name passes (auto-merge, `adjudicate_deferred`, the homonym `distinct_from`, `typing_conflicts`) act only on provisional and new-escape ids, never on manifest ids.
   - Two parallel chunks reporting the same unlisted figure as new (the innkeeper) are joined at the serial commit by code: same normalized name, compatible type, and no manifest namesake. Otherwise they stay provisional.
   - Test: stage 2 on the trap manifest plus one provisional "Rex" makes no merge or `distinct_from` the manifest didn't author.

## Measured: this is a correctness design, not mainly a speed one (eval/13, 2026-10-13)

The first timed build (474 s, 27 calls) spent about 11 s on identity reconcile, with no model calls, and about 9 s on literal categorization. Build time sits in extraction (104 s wall), story authoring (120 s), the serial arc and cast (96 s), and serial post-arc stages (about 100 s). Registry-first earns its place by **correctness**: no fused or split characters, no `_2` remaps, the Rex test, leak-safe reveals. The speed levers are separate, and ranked in eval/13: the extraction model and effort, parallel post-arc stages, and per-stage effort.

## r2: what changed after pattern-buffer's read (m52998c)

1. **One implementation, in a shared library.** pattern-buffer's book pipeline (`evals/harness/pipeline.py`, `registry.py`, INGEST-V2) is already registry-first:
   - pass 0 builds a `WorldRegistry` and seeds kind, name and alias rows before any fact;
   - pass 1 extracts per chunk in parallel against a registry slice, through a strict line grammar;
   - an unknown id comes back as an "escape" (this design's new-entity item).
   It is promoted from the eval harness to a library that both pattern-buffer and construct use. Construct's per-chunk `extract()` never used it. The library closes its two gaps: the model writes the ids today, and aliases carry no first-known chapter.
2. **Name resolution runs in that pre-pass, not at the engine's ingest gate.** If the gate rewrote entity ids by a fragment rule, identity would be decided silently at write time. In an append-only log, a wrong binding writes facts onto the wrong person, recoverable only by retract-and-retype. Other writers (the recorder, author sessions) write canonical ids that must never be rewritten. The engine keeps identity as explicit verbs with evidence and receipts (merge, `same_as`, `distinct_from`). It supplies registry seeding as ordinary rows (exists), `refer()` tier 1 for surface-form lookup (exists), R51's closed type set, and reads.
3. **The registry entry is the identity; (type, normalized name) is only a blocking key.** GraphRAG's merge rule fuses namesakes; pattern-buffer's held-out novella has 29 look-alike pairs. Two Johns the author lists are two ids even with the same type and name, and the name index marks "john" ambiguous, so it goes to the queue. The (type, name) key still separates the man and the dog called Rex at once: Kabe's test.
4. **The fragment rule is time-gated.** It counts only names known by that chunk's chapter, or "the duke" resolves early and leaks a reveal (GRADE-LEAKS-V1 charges exactly that).
5. **The category passes are adopted for both projects,** replacing pattern-buffer's single whole-book cast call. Pass 0 never joins two names into one being. Hidden identities are interpretation (pass 2, top model), written as dated joins with their reveal chapter, so the registry is leak-safe by construction: pass 0 can't know the twist, because it isn't asked.
6. **Fast-tier routing needs no engine change.** The engine's injected model receives the schema, and WorldService's `model_route` routes by schema, so a host can send classification batches to the fast tier today.

**The split *(r2)*:**
- **pattern-buffer:** promote INGEST-V2 to a library, containing:
  - the registry, with code-minted ids keyed by registry entry and a first-known chapter per alias;
  - fragment resolution, with the time gate and the ambiguity queue;
  - the category passes;
  - new-entity escapes;
  - R51's closed types;
  - a surface-form-to-id read, if `refer()` isn't enough.
- **construct:**
  - `author_story` returns its after-the-fact registry;
  - categorization calls merged and routed to the fast tier;
  - the cast author sees the registry;
  - the build calls the library in place of per-chunk `extract()`.

Sections 2 to 4 below are r1's design, kept for the record. Where they say "at the gate" or "the identity key is (type, normalized name)", r2 above supersedes them.

## How the build decides identity today

Traced 2026-10-13. File references are in the session record; the summary:

1. **The story author knows the cast, then throws it away.** `author_story` returns only `{title, prose}`.
2. **Every chunk mints identity blind.** The prose is cut into chunks (11 in run 9), and each goes to its own model call, in parallel. The model writes each entity's id string itself (`person:tomas_breck`), chooses its namespace and its kind, and lists its aliases. No chunk sees another chunk's ids, and no name list is supplied.
3. **At commit, identity is string equality.** Two chunks writing `person:rex` become one entity with no check, so a man and a dog both written `person:rex` are fused at write time. Since R49, the dog's "dog" is then stored as a role. Two different strings for one person (`person:breck`, `person:tomas_breck`) become two entities.
4. **Most later stages repair step 2:** the reconcile's name merges, `adjudicate_deferred`'s subset merges, `typing_conflicts` with retype-and-absorb, the cross-namespace homonym rejects, the cast's `_2` remaps (`person:hester_rook_2`, `person:jory_kest_2` in run 9), and the merge gate's model calls, each run twice. The identity stops exist because these repairs can't always tell.

The design flaw: **identity is a side effect of fact extraction, decided many times by a model, and reconciled afterwards.**

## The proposal: identity first, decided once, by code

### 1. A registry before any fact is extracted

The registry lists every entity: its canonical id, its **type**, its canonical name and its name variants.

- **The registry describes the story; it never directs it** (Kabe asked, 2026-10-13: "Does that help things or does that make for a less organic story build"). Authoring stays prose-first. The author writes freely, inventing people as the story needs them, and then lists what it wrote, like closing credits. It need not be exhaustive: a minor character the list misses still arrives through extraction as a new-entity item and is registered by code. Cast-first planning (premise → characters → plot → scenes, as in DeepMind's Dramatron) buys long-form coherence but risks a story that feels assembled. Construct takes its coherence from the hidden arc, authored afterwards over the real cast.
- **A generated story (the common path): zero extra calls.** `author_story`'s schema gains a `registry` beside `prose`. The author already knows its cast, places and key objects; it just has to say them.
- **An ingested book (no author):** one deterministic scan finds name candidates: capitalised spans, with titles and honorifics stripped by rule. One batched fast-model call types and groups the candidate list (person, animal, place, object, group).

### 1b. The pass structure (Kabe, 2026-10-13: "Pass for cast list, pass for locations, etc")

For any story that doesn't arrive with an author's list (a book; or as a cross-check):

- **Pass 0, the registry, as parallel category passes.**
  - Each pass reads the whole story and answers one narrow question:
    - **beings:** people, animals and creatures, with name variants and the chapter each name is first known;
    - **places,** and their nesting;
    - **key things;**
    - perhaps **groups:** factions, crews, families.
  - Each is homogeneous and low-judgment, so a fast model at low effort can do it. All run concurrently, so the wall time is the slowest pass, not the sum.
  - Code merges the lists on (type, normalized name), so the being "Rex" and the ship "the Rex" never collide.
- **Pass 1, facts,** per chunk and in parallel, against the merged registry.
- **Pass 2, interpretation,** on the top model, in a few calls: motive, dynamics, hidden identities and reveals. This is where deep thinking belongs.
- **Code between passes:** merging, name matching, time-gating.

Two refinements:
- **Size.** A book longer than one call runs each category pass per chapter group, and code merges by the same key. That also stamps each name's first-known chapter.
- **Speed.** Latency follows output and thinking tokens, not input (pattern-buffer's profile). Category passes write short lists with little thinking, so re-reading the story per category should cost less wall time than one call that does everything. The timing log checks this.

### 2. Code mints the ids

- **The identity key is (type, normalized name).** This is GraphRAG's merge rule. Rex the man and Rex the dog have different keys, so they get different ids at first mention.
- **The id is minted by code from that key** (`person:rex`, `animal:rex`), never written by a model.
- **Types are a closed set.** A role word ("condemned man", "sergeant") cannot be a type. It is rejected as a type and kept as a role. This lines up with R51's being → type → role layers.

### 3. A name index, consulted by code

- **Exact surface forms.** Every name variant, lowercased with titles stripped, maps to its id.
- **Fragments, by rule.** A bare "Breck" maps to "Tomas Breck" only when exactly one entry of a compatible type contains that token. With two candidates ("Mr. Holmes": Sherlock or Mycroft), or a role word, the mention is left unresolved and queued.
- **Only the queue reaches a model:** one batched call over all ambiguous mentions, on the fastest model.

### 4. Facts extracted against the registry

- **Each chunk's extraction gets the registry.** Subjects and objects must be registry ids. This is KGGen's two-pass rule; at this size, the whole registry fits in the prompt.
- **Chunks stay parallel,** since the registry is fixed first.
- **A truly new entity arrives as a "new entity" item** (type plus name). Code registers it at the serial commit by its key, so two chunks that both meet the same new barmaid converge on one id.

### 5. The repairs shrink to what they're for

- **The reconcile and its friends** become a safety net that rarely fires.
- **The cast author sees the registry,** with types and roles, so it reuses "Hester Rook, sergeant" as the sergeant or picks a new name. The `_2` remaps stop.
- **The merge gate runs only on queued ambiguous pairs,** on the fast tier, batched.

### 6. Literal categorization goes to the fastest model, batched

The call catalogue (2026-10-13) found 17 kinds of call that are literal sorting: an enum, a yes/no or a name match. In the build:
- genre, game type and death policy are three separate calls → one call;
- the lifetime classifier → one batch per build;
- the law critic is already one call.

On this Codex account, the cheap tier is `gpt-5.5`, the same model as the main tier, because the account refuses `gpt-5.4-mini`. So "cheap" calls cost the same time as main ones today. Finding the fastest model the account allows is the first lever, and it needs no design.

Batching safeguards, from the batching literature (BatchPrompt and later work):
- homogeneous items;
- batches of about 20 to 50;
- each answer echoes its item's key, not an index;
- re-ask only the low-confidence items;
- check against single-item calls on a sample before switching.

## Already in pattern-buffer's speed plan (read 2026-10-13)

pattern-buffer's `docs/SPEED-PLAN-2026-10-13.md` (book builds, R27) has the same shape at its step 4: one whole-book cast call writes a registry, pass 1 extracts in parallel against it, and the merge gate checks rather than repairs. pattern-buffer already has a `registry.py`. This proposal should build on that, not beside it. Two of its points change this design:

- **The registry must carry time.** Each alias records the chapter where the reader first meets it, and a chunk receives only the aliases known by then. Otherwise a whole-story registry leaks a chapter-10 reveal (the stranger is the duke) into chapter 2. This is Kabe's threat model exactly: nothing narrates ahead or leaks future knowledge into characters. For a generated story, the author's registry must mark hidden identities and when each is revealed. Canon identity stays timeless; what is time-gated is which aliases each chunk is told.
- **Effort is the biggest single lever.** Their profile measured about 96% of output tokens as hidden thinking, and latency follows output tokens (R² 0.97). Tiering effort by how hard each judgment is (Kabe: deep thinking for motive and dynamics, chore work for "gathering details accurately already established") comes before, and alongside, choosing models.

## Who builds what

- **pattern-buffer (the engine owns identity):**
  - the name index at the ingest gate, resolving surface forms to ids;
  - ids keyed by (type, name), with code doing the minting;
  - extraction that accepts a registry (`extract(context=...)` already exists) and returns new-entity items;
  - the closed type set (R51);
  - the batched classifier.
- **construct:**
  - `author_story` returns the registry;
  - the book path's candidate scan and batched typing call;
  - the registry passed into extraction and into the cast author;
  - merged categorization calls;
  - routing class-A calls to the fastest model.

## How we'll know

- **Speed:** build wall time, and model calls in the build, from the timing log: before (the next run) and after.
- **Quality:** zero `_2` remaps; zero fragment pairs reaching the merge gate on a generated story; the Rex test (a man and a dog both named Rex stay two entities from the first commit); R20's build still passes.

## Prior art, and what we take from it

- **GraphRAG:** entities merge in code on exact (title, type); the model only summarizes. We take the identity key. We don't take its weakness: it never joins fragments, so "Breck" stays apart from "Tomas Breck".
- **KGGen, and the two-pass extract-entities-then-relations papers:** relations are extracted against a fixed entity list. We take the two passes; our registry comes free from the author.
- **BookNLP:** character name clustering by name parts and honorifics; a common noun never corefers with a named entity. We take the fragment rule and the type constraint as code.
- **Splink, Fellegi-Sunter:** cheap exact blocking keys first; only candidates get scored. We take block-then-discern.
- **sift-kg:** deterministic normalization, then batched model resolution per type, people sorted by surname. We take the batching shape. We don't take its same-name/different-type merge.
- **BatchPrompt** (arXiv 2309.00384) and arXiv 2604.03684: batching holds accuracy with the safeguards above.

**Safety pass.** Names come from model output over prose. They are treated as data: normalized, length-capped and reserved words refused before they become ids (LightRAG's sanitizing). Nothing is copied from these projects; it is design adoption only.

## Open questions for the fresh views

1. Where should the name index live: in the engine's gate, or in a pre-pass library? *(r2: pre-pass library; put both to the fresh views.)*
2. What is the closed type set, and how does it meet R51 (being → type → role)?
3. Is the fragment rule (exactly one compatible container, among names known by that chapter) safe enough, or does it need the author's registry to list the fragments explicitly? *(r2: also, (type, name) as the identity against registry-entry identity: put both to the fresh views.)*
4. Is the book-ingest path's scan plus one batched typing call enough, or does a long book need the scan per chapter?
5. How much of today's repair machinery can be retired, and how much stays as a safety net?
6. Craft: does asking the author to list what it wrote (after the prose, in the same call) change the prose at all? Compare a few stories with and without the registry field.

## Fresh views (consult cb0483e, 2026-10-13; gate g2fd391 for Kabe)

Two consultants from different model families (claude-opus-5-5 and gpt-5.6-terra, both at max effort) read a sourced digest with this plan left out. Both endorse a registry-first, identity-before-facts build with code resolving mentions. Their points that would change the approach went to Kabe as one gate (g2fd391):

1. **The author's manifest is the sole authority** (both consultants). Category passes only check or extend it, for imported prose.
2. **Hidden identities are written at build** as two entries plus a dated `correlate` (the engine's existing `aka` verb, which never collapses ids and shows only from its valid time), with `distinct_from` for namesakes the author lists (both).
3. **Ambiguity is append-safe:** facts on mention nodes, plus a later `denotes(mention, entity)` edge on evidence; nothing is ever rewritten (consultant 2).
4. **Ids carry no ontology:** neutral entity ids, with the type as a fact. This replaces "person: read as being" (consultant 2).
5. **Acceptance on planted-trap stories:** Rex the man and Rex the dog, two Brecks, a late reveal (consultant 1).

Also from consultant 1, matching eval/13: with both tiers on gpt-5.5, the only fast lever is lower reasoning effort, and batching saves cost, not wall time, when calls already run in parallel. An extractor that no longer decides identity is the one most likely to stay accurate at low effort.

### pattern-buffer's weighing of the engine points (mf08994)

- **Point 2 (hidden identities as dated `aka` via `correlate`, plus `distinct_from` for listed namesakes): endorsed.** Both verbs exist (AKA-CORRELATION-V1). `aka` keeps the facets apart in default reads; a correlated read joins them on purpose; the reveal is a `knows:` fact. Grading caveat: `aka` is not identity closure, so book grading counts an aka-joined reveal as joined.
- **Point 3 (mention nodes plus `denotes`): the goal is right, the engine already has it.** Facts go on a provisional id for the ambiguous mention, joined later with `same_as`: an explicit, evidenced, retractable assertion whose facts fold into the entity's closure. A new `denotes` would duplicate `same_as` with weaker tooling. Hosts filter provisional ids out of rosters by a kind or flag.
- **Point 4 (neutral ids): lean no, on cost against gain.** Registry-entry identity, minted by code, solves Rex. R49, and R51 for every type, make the kind fact authoritative over the namespace. Neutral ids would ripple through `ID_RE`, the person/place predicates, the mirror, every test and every host's readability. Instead: code-minted, readable, type-prefixed ids (`person:rex`, `animal:rex`, `person:john_2` for a listed namesake), with the R51 type fact as the authority and the namespace a readable hint only.
