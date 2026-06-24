# Startup Entry — play / generate / provide (host spec, DRAFT, under group review)

**Status:** initial draft, circulated to K / Cx / PB for full draft-then-review
before build. Construct-owned (session-zero + CLI). Founder side-spec 1.
**No engine dependency** — reuses the shipped ingestion pipeline; the only new
build path is "generate the fiction, then ingest it."

## 1. The three startup paths
On startup the player chooses one of:
1. **Play an established world** — pick from the library (`scenarios` →
   `play <name>`). *Exists.*
2. **Generate a new world** — the model writes a complete **hidden fiction
   (prose)** from an optional seed, that prose is **ingested through the existing
   pipeline** (`create_scenario_from_ingest`), then play. *New.*
3. **Provide the fiction** — ingest a `.txt`/`.md` the player supplies
   (`new --ingest` / the `import` command). *Exists.*

The new piece is path 2; paths 1 and 3 are surfaced by a **guided entry menu**
(vs today's flags-only CLI).

## 2. Why generate-prose-then-ingest (and how it differs from `--interview`)
There's already an `--interview` path: it expands a brief into the **constitutive
spine directly** (structured items, *no prose*). Generate-then-ingest is
different and complementary:
- It writes a **full story** (real prose, a hidden source-of-truth), then runs it
  through the **same extraction** a provided document gets.
- So it exercises the rich projection (coreference, events, the whole shape) and
  produces a more naturalistic, coherent world than a hand-minted spine — and it's
  consistent with the provided-fiction path (one ingestion).
- *Proposed:* keep `--interview` as the fast/lightweight path; generate-then-ingest
  is the "build a rich new world" path. (Open question §6.)

## 3. The new build path: `create_scenario_from_generated`
A thin new function alongside the existing creation paths:
1. **Author the fiction** — a new "story-author" cohort writes a complete short
   work from an optional seed (genre / premise / length; else "surprise me").
   Good-tier; the prose is the hidden bible.
2. **Save the prose** — write it to disk (proposed: `generated/<name>.md` + a
   stamp), so it is auditable and re-ingestable, exactly like the frozen example
   fixture. *(The whole point of the showcase is fiction → projection; a saved
   source keeps that contract.)*
3. **Ingest it** — call `create_scenario_from_ingest(name, <saved prose>, ...)`
   unchanged — the same six-stage pipeline (extraction → reconcile → traversal
   policy → arc → seeding → seal), with the same per-stage status narration.
4. **Play.**

Reuses everything; the only net-new code is the story-author cohort + the menu +
this orchestrator.

## 4. The guided entry menu
A startup surface (REPL `play` with no arg, or a `construct start`) that presents
the three paths and routes to the existing commands. Each path can still be
reached by flag for scripting. This pairs naturally with the win/loss mode choice
([WIN-LOSS-CONDITIONS.md](WIN-LOSS-CONDITIONS.md) §2) — both are session-zero
questions: *which world* and *which mode*.

## 5. Explicitly out of scope
- No engine change — extraction is PB's `ingest`, unchanged; this orchestrates it.
- Generation quality / prompt-craft for the story-author cohort is its own tuning
  track (like the extraction prompts); the spec defines the *path*, not the prose
  recipe.

## 6. Open questions for the reviewers
- **K (host discipline / SESSION-ZERO):** does generate-then-ingest belong beside
  `--interview`, or should it *replace* it (one "build new" path, prose-first)?
  Is the guided menu the right session-zero entry, and does saving generated prose
  to `generated/` fit the project's fixture/firewall conventions?
- **Cx (shape / adversarial):** any failure mode in "generate → save → ingest"
  (e.g. the author cohort produces prose that extracts poorly / too thin to make a
  playable arc — should there be a post-ingest viability check before declaring
  the scenario built)? Seed-injection edge cases?
- **PB (engine truth):** confirm this is purely host orchestration over the
  shipped `ingest` pipeline — no new engine surface.

## 7. Built (review integrated — Kernos 063 B, Cx 063 #6/#7, PB 064)
Shipped host-side; no engine surface (PB 064 confirmed). What landed and the
review decisions baked in:
- **`cohorts.author_story(provider, seed)`** — prose-first story-author (good
  tier). The seed is **untrusted player text**: bounded (`_SEED_MAX_CHARS`) and
  quoted strictly as premise DATA inside `<<<SEED … SEED>>>` markers, never as
  instructions (Cx #7 injection hardening; fixture-tested with an "ignore
  previous instructions" seed).
- **`game.create_scenario_from_generated(...)`** — author → `_save_generated_prose`
  → `create_scenario_from_ingest` (UNCHANGED pipeline) → **viability gate**.
- **`generated/`** — the authoring side of the firewall (the hidden bible);
  **gitignored** runtime artifact, distinct from committed `examples/`
  (Kernos B.2); collision-proof stamped names (B.3); never read in a play
  session (B.1).
- **Viability gate `_assess_viability`** (Cx #6, PB 064): entry material (title,
  a resolvable protagonist, ≥2 people, ≥1 place), arc seeded (`arc_scope` +
  ≥1 knowledge frame), and a cold establishing-set read renders a non-empty
  world-at-rest. On failure: `ViabilityError` — the published `.world`/`.meta`
  are removed (`_unpublish_scenario`), the generated **source is preserved for
  audit**, and the caller surfaces an actionable failure (never a
  playable-but-broken scenario).
- **Entry menu** — `construct start` (Cx: cleaner than overloading `play`); a
  **surface over the flags** (`new --generate [SEED]` / `--ingest` / `--interview`),
  every path still reachable by flag for headless/scripted play (Kernos B). The
  menu asks the two session-zero questions: which world + which mode (freeplay →
  endless/no-terminal; win/loss → terminating).
- **`--interview` kept beside** generate-then-ingest: spine-first (sketch) vs
  prose-first (the showcase loop, the primary "build a rich new world" path).

## SHIPPED — the live transport mode interview (2026-06-19)
The "which mode" session-zero question is now asked **over the chat transport
itself**, not just the CLI menu — so a Telegram/loopback player co-authors the
shape of their own experience before the world opens (founder direction: "right
before the story even starts… whether they want FreePlay or a conclusive end").

Flow (`construct/transport_core.py`):
1. **Claim → ask.** On a successful invite claim the gate sends `MODE_PROMPT`
   ("a story that builds toward a real ENDING, or open-ended FREEPLAY?") and
   records an `_ASKING` sentinel in the registry `mode` column.
2. **Next message → answer.** The player's next message is read into a mode by
   `_interpret_mode` (keyword cues; **ambiguous → endless**, the safe default —
   stakes are never forced on someone who didn't ask). The chosen mode is
   persisted, the player is marked `started`, the world opens FRESH, and the
   cold open is shown. Their *next* message is the first move.
3. **Two-step, entry-agnostic.** The prompt is shown exactly once regardless of
   entry path — including legacy players who claimed before the interview
   existed (mode `NULL` + not `started` → ask now, answer next).
4. **Resume honors the choice.** A returning player auto-resumes in their stored
   mode (`registry.get_mode`, normalized by `_valid_mode`); the sentinel never
   reaches a `Session`.

Modes (`Session`): **win_loss** (has an aim; can terminate) · **endless**
(world carries on, never settles) · **bounded** (the CLI/legacy default: the arc
concludes and the world settles into "concluded" pacing, no aim, no
termination). In the live transport a concrete mode is ALWAYS supplied as
`mode_override`, so the bounded default only governs CLI/tests.

Also shipped: **`/feedback <note>`** — drops a letter into the operator
`dev_inbox/` bundling the note with the last few turns of the player's
transcript, so a problem flagged mid-play can be picked up and fixed without
leaving the session.
