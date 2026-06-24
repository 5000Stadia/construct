# Narrative Memory & the Narrator's Context (the Ledger side)

**Status:** SHIPPED v1 (2026-06-19). The presentation the *primary agent* (the
narrator) receives each turn, and the memory that keeps long-form live fiction
feeling like a story rather than a database-retrieval read.

## The problem (founder)
The pattern-buffer gives **factual object-permanence** — a reconciled, gated store
of what is true (the "Facts" store). But the narrator is called **stateless** each
turn (a fresh prompt; no persistent conversation), so with *only* fact retrieval the
experience reads like "an LLM database object-retrieval system trying to act as
narrative fiction." The missing layer is a **rich narrative short-term memory**: what
just happened, in what order, and the through-line beneath it.

## Two stores, two jobs (adopted from Kernos `docs/architecture/memory.md`)
Kernos's matured discipline — **never degrade one store into the other**:

| Kernos | Construct | job |
|---|---|---|
| **Facts** (reconciled, single-call) | **the pattern-buffer canon** (gated ingest, identity reconcile) | durable truth — what *is* |
| **Ledger** (arc, compressed at boundaries, recoverable) | **narrative memory** (host frames, never canon) | the story arc — what *happened* |

The narrative Ledger is **host-side only** — never written to the pattern-buffer
(founder: "would not be so literally injected into the pattern buffer"). Meaning, not
fact.

## The three Ledger layers (turnloop.py)
1. **Append-only ARCHIVE** — every beat preserved on its turn event
   (`event:turn_N.prose` / `.player_said`, `session:` frame). Lossless at its own
   resolution → the compacted memory is **recoverable/regenerable** against it, never
   a lone drifting summary (the Kernos anti-drift property).
2. **Compacted NARRATIVE MEMORY** (`session:narrative_memory.text`) — the Living-State
   analog: standing dynamics, recurring themes/motifs, unresolved threads, how figures
   changed, live promises/debts/threats. **Rewritten at compaction boundaries** (not
   patched) by `cohorts.compact_memory` — a single reconciling call (current memory +
   the beats aging out → updated memory). Boundary-triggered in batches
   (`CONSTRUCT_COMPACT_BATCH`, default 4), not every turn; fail-open.
3. **Recent VERBATIM window** (`session:transcript.recent`) — the last
   `CONSTRUCT_RECENT_TURNS` (default 8) beats, player action + narration, in full.
   The short-term working memory; the narrator's most immediate context.

## How it reaches the narrator (the presentation)
The briefing is framed as one coherent **director's brief**, pre-filtered of all
internal machinery (no frame ids, no entity ids — grounding is rendered **by name**):
1. **STYLE** — the world's voice (one-time flavor overlay).
2. **NARRATIVE MEMORY** — the arc so far (compacted; the through-line to honour).
3. **THE STORY SO FAR** — recent beats, verbatim (short-term memory; continue from it).
4. **THE SCENE RIGHT NOW** — what is true and present, by name.
5. **What presses** — pinned awareness, an NPC's want, a pacing beat, a new
   development/fallout.
6. **THE PLAYER JUST DID** — the move to answer.
7. **The rules of the telling** — the narrator's licence/leash (truth-bound, conceal
   the hidden, pressure-not-puppetry, no control markers).

Rules/craft guidance (`FICTION_CRAFT`) live ONLY in the one-time session-zero
authoring cohorts, **never** in the per-turn briefing (founder: do not dump a rules
window every return). The per-turn brief carries *story*, not *rules*.

## Prompt sectioning (systematic, robust)
Every host cohort prompt opens with a stable 3-letter task tag in mathematical white
brackets — `⟦nar⟧`, `⟦cls⟧`, `⟦mem⟧`, … (`provider.task_tag`/`task_of`). Routing,
tiering, profiling, and test stubs latch onto the **tag**, never the prose, so a
wording change (e.g. a craft preamble) can never break dispatch. The bracket chars
never occur in fiction and are forbidden in player-facing output
(`FORBID_TASK_MARKERS`), even in a sci-fi terminal-sim scene.

## Open / next
- **Archive RETRIEVAL/regeneration** — the archive exists; a retrieval path (pull an
  older span back when a theme recurs, or regenerate the Living State against the
  archive) is not yet built. Kernos's Archive index is the model.
- **Mesh review** — adopting Kernos's Ledger/cohort *presentation* faithfully warrants
  a review from Kernos CC (the road of work behind it has sharp validity).
- **Live validation** — the memory layers + the reframed brief should be A/B'd in a
  real long-form playthrough (the stubbed suite can't judge narration quality).
