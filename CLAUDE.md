# CLAUDE.md — Instructions for Claude Code (Holodeck / "HD")

## Project: Holodeck — a text holodeck

An interactive-fiction engine where a persistent world (ingested from a book, or built live through an interview) is held in a **pattern-buffer** world store and played turn by turn: the player chooses who they are and where in the timeline they enter, pursues an authored character arc they cannot see, and the world remembers everything with object permanence, frame-scoped NPC knowledge, and re-entry coherence.

## Before you do anything

1. **Read `docs/CONCEPT.md` in full.** It is the founding brief: the vision, the session-zero flow, the architecture (you are a HOST over the pattern-buffer engine), the arc layer (the one genuinely new design surface), and the adopted patterns from Kernos and pattern-buffer. Start here.
2. **Read the pattern-buffer whitepaper and adoption guide** at `/home/k/pattern-buffer/docs/WHITEPAPER.md` and `/home/k/pattern-buffer/docs/ADOPTION.md`. The engine is your substrate; you integrate it as a library, you do not reimplement it. **Read-only reference — never import from or edit the pattern-buffer tree.**
3. This is a DESIGN-FIRST project (docs-first genesis, the house method). No engine integration code until a concept is pressure-tested on paper and the pattern-buffer porcelain API exists. Brainstorming and outline first.

## What you are building (and not)

- **You are a HOST**, like Kernos is a host: orchestration over the pattern-buffer engine. The world store, ingestion, projection, frames, thunks, identity — all live in the engine. You supply: the turn loop, the session-zero interview, character engines, the arc/destination layer, and the player-facing render.
- **You never reimplement engine concepts.** If you want object permanence, frames, or as-of queries, they come from the engine. If the engine lacks something you need, that is a **[DECISION] letter to Kernos CC** (see channel below), not a local workaround.
- The arc/destination layer is the new intellectual surface — it is the project's contribution and where the real design work lives.

## Communication channel (the mesh)

You are the third node in a coordination mesh. The other two: **Kernos CC** (`/home/k/Kernos` — instructor, holds pattern-buffer adoption knowledge and the Kernos architectural patterns) and **PB** (`/home/k/pattern-buffer` — builds the engine; you coordinate with PB only through Kernos CC for now).

- **Your inbox:** `/home/k/Newproject/dev_inbox/` — Kernos CC writes here.
- **To reach Kernos CC:** write `NNN-from-hd-<topic>.md` into `/home/k/Kernos/dev_inbox/`.
- **Watch your inbox** for new `from-kernos` letters (a persistent file-watch; poll-loop shape since no inotifywait on this box — mirror pattern in the debrief). Re-arm on session start; record in memory.
- Tag letters: **[STATUS]** / **[DECISION]** / **[BLOCKED]** / **[MILESTONE]**. Blockers and deliberation are letters, never silent waits. Bound every external call (~10 min) and report if it stalls.
- The founder is in the loop on all exchanges. Surface genuine forks to him via Kernos CC; obvious calls you make and record.

## Process conventions

- Python 3.11+, type hints, `logging` not print, docstrings on public surfaces. Simple over clever.
- Docs-first: the concept doc and an outline precede any code. Spec-first with review for substantive batches.
- The dependency truth: this project consumes the pattern-buffer **porcelain API** (the five verbs: ingest/snapshot/ask/materialize/resolve). That API is being finalized now. You can design against it from ADOPTION.md before it ships; you cannot integrate until it does. Design the arc layer and session-zero — they need no engine code — first.

## The mesh (read both, import neither)

Two sibling projects are readable reference — study freely, never import or edit:
- **Kernos** (`/home/k/Kernos`) — reference host; instructor (Kernos CC). Your outbox: `/home/k/Kernos/dev_inbox/` (`NNN-from-hd-<topic>.md`). Design knowledge: `docs/DESIGN-PRINCIPLES.md`, `docs/architecture/`.
- **pattern-buffer** (`/home/k/pattern-buffer`) — the engine you build on. Its inbox is readable (the full coordination history with Kernos CC, letters 007-027 = case law). Design knowledge: `docs/WHITEPAPER.md`, `LEXICON.md`, `ADOPTION.md`, `docs/reference/prior-art-survey-2026-06.md`.

Before/with your read-back: survey both projects' novel elements and report which you adopt for Holodeck and why (element → source → use), per dev_inbox letter 002. Adopt by intent, not osmosis.
