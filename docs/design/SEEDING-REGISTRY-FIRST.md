# Seeding, registry first: identity decided once, by code

**Status:** construct's proposal, r1.1, 2026-10-13 (adds pattern-buffer's speed-plan overlap). Not built. It changes pattern-buffer's ingest and identity, so it is co-designed with pattern-buffer and goes to two fresh views from other model families before anything is built. The baseline numbers come from the first run with the timing log (`CONSTRUCT_TIMING_LOG`, feat/timing-log).

## Kabe's direction (2026-10-13)

- "things that are literal name matching that don't have any nondeterministic discernment should be programmatic and not an LLM call. We should consider in our shape how many of these things we can establish as programmatic reference items as early as possible. And we should be able to do so in a way where a Rex person and a Rex dog are initially and immediately identifiable in separation."
- "I have an ignorance that I have not looked under the hood of the structure and allowed the history of this development to be pretty much naturally evolving by LLM Design decisions, The weakness I feel should be addressed now before moving forward is a more elegant architectural method to improve the time of this kind of a pass because it is so foundational to the initial seeding of a new world story"
- "there may be a difference in cognitive complexity ... save a detailed higher order of thinking nuance to hire models, but identify what literal category analysis ... which can be handled by literally the fastest model in probably a process that can mass group work in a single turn batch"
- "everything I'm discussing is when construct establishes a fresh story ingested into pattern buffer that length of duration for preparation before the world is available to the user"

**The target:** the build, from a fresh story to a world the player can enter. About 15 to 20 minutes in R20 run 9.

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

- **A generated story (the common path): zero extra calls.** `author_story`'s schema gains a `registry` beside `prose`. The author already knows its cast, places and key objects; it just has to say them.
- **An ingested book (no author):** one deterministic scan finds name candidates: capitalised spans, with titles and honorifics stripped by rule. One batched fast-model call types and groups the candidate list (person, animal, place, object, group).

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

1. Where should the name index live: in the engine's gate (identity is the engine's), or as a construct pre-pass? The proposal says engine.
2. What is the closed type set, and how does it meet R51 (being → type → role)?
3. Is the fragment rule (exactly one compatible container) safe enough, or does it need the author's registry to list the fragments explicitly?
4. Is the book-ingest path's scan plus one batched typing call enough, or does a long book need the scan per chapter?
5. How much of today's repair machinery can be retired, and how much stays as a safety net?
