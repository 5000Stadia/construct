# Holodeck — Concept & Founding Brief

> A text holodeck. A persistent world — ingested from a book or built live through an interview — held in a pattern-buffer world store and played turn by turn. The player chooses who they are and where in the timeline they enter, pursues an authored arc they cannot see, and the world remembers everything: object permanence, frame-scoped NPC knowledge, re-entry coherence.

**Status:** Founding brief for design-first genesis. No code yet. This document is the debrief for the Holodeck (HD) instance — vision, the session-zero flow, the host architecture, the syntax for using pattern-buffer, the patterns worth adopting from Kernos, and the one genuinely new design surface (the arc layer). Brainstorm and outline from here.

---

## 1. What this is, and why it can exist now

Interactive fiction has always had to choose between two failures: hand-authored worlds (rich but rigid — every path pre-written) or generative worlds (free but amnesiac — AI Dungeon, which contradicts itself within twenty turns). The thing that makes a *holodeck* different from either is **a persistent, queryable world model underneath the improvisation** — so the world can be freely generated *and* never forget, never contradict, never re-invent the drawer you already opened.

That substrate now exists: **pattern-buffer** (`/home/k/pattern-buffer`), a validated append-only world-state engine. Holodeck is the first product built on it. The strategic point: **Holodeck needs only the engine's fiction mode — the validated mode, four graded runs deep — plus its porcelain API.** It does not wait on tracking-mode maturity. It can consume the porcelain the moment it ships and exercise it as a real host while tracking matures elsewhere (in Kernos).

Holodeck also *is* a test instrument. It exercises the pattern-buffer §19.2 interactive criteria — thunk stability across a long session, NPC non-leak, loop closure (the town that remembers you), the resonances surface — by **play** rather than by synthetic harness. Eval-as-product, the same trick the chapter test pulled, one level up.

## 2. The session-zero flow (the spine of the UX)

One unified interview — "session zero," the tabletop term — is the front door for **every** game. The two creation paths (ingest a book vs. build live) are not different wizards; they are the same wizard with **different sections pre-filled**. This unification is the design's first elegance: *ingested and live are one session-zero under a which-sections-are-known switch* — the same way fiction and reality are one engine under a policy switch.

```
ENGINE LOADS → simple chat greeting
│
├─ Reload saved world? ──────────→ World.open(<file>.world)
│                                   materialize(establishing_set) → re-enter at rest
│
└─ New world?
   ├─ Path A: INGEST a work ──────→ registry-first ingestion → world born (stance=fiction)
   │     (book's prose authors the physics; world-setup section SKIPPED)
   │
   └─ Path B: LIVE fiction ───────→ short interview authors genre/era/world_defining pins
         (the interview IS the World Charter creation wizard + constitutive spine)

   THEN, both paths — entry configuration:
   ├─ WHERE in the timeline do you enter?   → materialize(establishing_set, as_of=t)
   │     (as-of makes "enter Anchor before the meter went dark" nearly free —
   │      you choose a coordinate, not a fixed scene)
   ├─ WHO do you play?
   │     canon character → step into their existing knows:<id> frame (you inherit
   │                       exactly their information state, structurally — P4)
   │     new character   → resolver authors one under canon
   │     (note: in ingested fiction, play the detective OR the clerk who hid the
   │      core — same world, opposite frames, completely different game)
   └─ DESTINATION (the arc) — both paths:
         player states a desired end, OR engine proposes a book-like conclusion +
         character arc appropriate to that character / genre / setting.
         Authored into a hidden plot: frame the player cannot see.

WORLD STARTS.
```

## 3. Architecture: Holodeck is a HOST

The single most important framing, carried from how Kernos relates to its substrates: **Holodeck orchestrates the pattern-buffer engine; it does not reimplement it.** The engine owns world state, ingestion, projection, frames, thunks, identity, as-of queries. Holodeck owns four things the engine deliberately does not:

| Holodeck owns | Uses from the engine |
|---|---|
| **The turn loop** — player input → world mutation → NPC response → render | `ingest()` (player acts = canon events), `materialize()` (scene context), `resolve()` (force thunks at the floor) |
| **Session-zero interview** | `World.create` + charter writes; constitutive-spine assertions |
| **Character engines** (§14.1 of the whitepaper — designed, unbuilt) | each NPC = an agent handed ONLY its `knows:<id>` frame; secrecy by structural absence |
| **The arc / destination layer** (the new surface, §5 below) | the `plot:` frame; the evidence-graph machinery generalized to arcs; clocks |

The dependency is one-way and the rule is absolute: **never import from or edit the pattern-buffer tree.** The engine takes one injected thing — a model callable. Holodeck supplies it (subscription auth — Codex-shape HTTP shim, the Kernos-proven pattern; see §7). If Holodeck needs a capability the engine lacks, that is a **[DECISION] letter to Kernos CC**, never a local fork.

## 4. The syntax for using pattern-buffer (the porcelain)

Read `/home/k/pattern-buffer/docs/ADOPTION.md` for exact signatures; the shape:

```
world = World.open(path, model=shim)          # reload a saved world
World.create(path, physics=Physics(...), model=shim)   # new world (charter written at genesis)

# the three host seams + two world verbs:
await world.ingest(text, source=, scene=, at=)   # player acted / something happened → canon
world.snapshot(text, frame=, budget=)            # assemble scene context (NO LLM; deterministic)
await world.ask(question, frame=, as_of=)        # a query (player or engine)
world.materialize(scope, lens, frame, as_of, budget)   # full scene briefing for the renderer
await world.resolve(entity, aspect)              # force a thunk (player opens the drawer)
```

Holodeck's turn loop is mostly: `snapshot` the scene for the renderer → render to the player → `ingest` what the player does as canon events → `materialize` the NPC's frame for its response → render. Object permanence, frames, and re-entry are *inherited*, not built.

**Charter (pattern-buffer letter 026):** every world self-describes via a reserved `world:self` entity — `stance` (fiction here), `title`, `description`, `genre_era`, `derived_from`. The session-zero interview's output IS the charter plus the constitutive spine. Saved worlds are self-identifying when listed (the ship in a bottle, labeled on the glass).

## 5. The arc layer — the one new design surface

Pacing/drama management is pattern-buffer's named-unsolved problem (whitepaper §14). Holodeck's end-condition idea makes it **tractable** by turning aimless improvisation into **navigation toward a declared destination** — and the mechanism falls out of existing machinery, no new primitives:

- **The arc is authored at session zero into a hidden `plot:` frame** the player cannot see (the mystery machinery — frame-scoped secrecy — reused for *destiny* instead of *whodunit*). Milestones, growth beats, the conclusion shape: all assertions in `plot:`.
- **The evidence graph generalizes to an arc graph:** `discoverable_via` → `achievable_via`; a beat becomes reachable when its preconditions are met, path-independent (the player can reach the same arc beat many ways).
- **Clocks** (whitepaper §14.3) escalate toward unmet beats — the world moves toward the story even when the player dawdles.
- **The dramatic-irony delta** (canon minus the player's frame — already a computable query in the engine) becomes the GM-renderer's actual pacing instrument: it measures how much story remains unrevealed, and the nudge policy surfaces an unwalked thread when the delta stalls.

This layer is the project's intellectual contribution and where the real design work concentrates. **Pressure-test it on paper first** (the house method) — especially: how an authored arc survives a player who refuses it, how "book-like conclusion" is generated for an arbitrary character, and how the GM-renderer balances the destination against player agency without railroading.

## 6. Adopted patterns from Kernos (orchestration knowledge)

Kernos (`/home/k/Kernos`) is the reference host. Patterns worth lifting — by **pattern**, never by import:

- **The Cognitive UI / rendered context window.** Each turn, compose the renderer's entire view deliberately — what the scene materialization surfaces *is* the renderer's control set; a callback it cannot see, it cannot play. (This is why loop-closure resonances must be *surfaced into* the briefing, not left to the renderer's memory — pattern-buffer letter 013.)
- **The Quiet Cohort.** Single-purpose cheap model calls around the main render: an NPC-response cohort (frame-scoped), a beat-evaluator cohort (did this turn advance an arc beat?), an input-classifier (is this player utterance an action, a question, or out-of-character?). Selectively invoked, fail-open, silent.
- **The dispatch gate, narrowed.** Player actions with real stakes (irreversible world changes, NPC death) get a proportional confirmation beat — not a permission wall, a dramatic one.
- **Loud-fail over silent degradation.** A render that can't be grounded surfaces an honest seam, never a vague hallucination.
- **Provenance honesty.** `generated` NPC dialogue and `stated` canon stay distinguishable in the log — the holodeck's own audit trail.
- **The genesis method itself:** docs-first, the dev_inbox mesh, spec-then-review, deliberate closure.

## 7. Model auth (no API credits) — Codex auth for EVERY agent

Same decision as the rest of the mesh (pattern-buffer letter 020): **no Anthropic API key, no metered SDK.** **Every model-calling agent in Holodeck wires to subscription auth via the Codex-shape HTTP shim** — the pattern proven in Kernos production (`/home/k/Kernos/kernos/providers/codex_provider.py`, read-only reference: copy the pattern, never import). This is a first-class architectural requirement, not just the engine's plumbing:

- **The engine's injected `model=` callable** (ingestion, classification, resolution, refer tier-2) — one shim instance.
- **Holodeck's own primary in-engine agents**, all on the same shim: the **renderer/GM**, the **NPC character engines** (one frame-scoped call each), the **beat-evaluator cohort**, the **input-classifier cohort**, and the **session-zero interviewer**.

Build it once as a shared provider module Holodeck owns (`holodeck/provider.py` or similar — host-side, never in the engine): fresh-read `~/.codex/auth.json` per run, fail-fast and loud on 401 (`codex login` needed), bound every call (~10 min, Kernos house standard), respect the `strict: null` and large-payload transport caveats. Hand the same callable to `World(model=…)` and to every cohort. One auth path, one credential, zero billing surface — exactly how Kernos runs its entire production load.

### Provider-agnostic by architecture; Codex by dev default

Separate two things that must not be conflated:

- **The architecture is provider-agnostic.** The shim is one implementation of a small **provider interface** — `(prompt, schema) -> json`, plus a model-tier hint (main / cheap). At session setup, a user may supply **any LLM API** they hold (OpenAI key, Anthropic key, a local/Ollama endpoint, etc.); each is just another provider implementation behind the same interface. This is the same injected-callable discipline the engine already enforces — Holodeck inherits it and extends it to its own cohorts. Build the interface first; never hardcode a provider anywhere downstream of it. (One config surface selects the active provider; everything else — engine `model=`, renderer, NPC engines, evaluators — takes whatever the interface hands them.)
- **Codex subscription auth is the FOUNDER'S DEV DEFAULT**, wired and working out of the box so development costs zero credits. It is the reference provider implementation, not a hard dependency. Ship it as the default; keep it swappable. A user with their own card selects their provider at setup and never touches Codex.

The MUST/NEVER for the spec: MUST route every model call through the provider interface; MUST ship Codex-auth as the working default; NEVER hardcode credentials or a vendor past the interface boundary; the user's own provider, when supplied, is honored everywhere a model is called.

## 8. What needs building (the thin host)

Mostly orchestration of finished machinery:

1. **Session-zero interview** — chat wizard → charter + constitutive spine + entry frame + arc. (No engine code; pure design + prompt.)
2. **The arc layer** — `plot:` frame authoring, arc-graph, beat evaluation, clocks, the nudge policy. (The real design work; pressure-test first.)
3. **The turn loop** — snapshot → render → ingest → NPC-materialize → render.
4. **Character engines** — frame-scoped NPC agents (whitepaper §14.1).
5. **The render leash** — describe only what the briefing supports; introduce no new canon; route unknowns through `resolve`.
6. **Save/load** — nearly free: the `.world` file is the save format; `materialize(establishing_set)` is re-entry.

## 9. Sequencing

1. **Brainstorm + outline** (now): refine this concept, draft the arc-layer design on paper, settle the session-zero script shape. No code.
2. **Design docs to review** — the arc layer especially earns a Codex pass before any build.
3. **Build against the porcelain when it ships** (pattern-buffer is finalizing it now). Session-zero and the arc layer can be designed — and partially built as pure logic — before the engine API lands.
4. **First playable:** ingest a short public-domain work → play one character toward one arc → the §19.2 criteria graded by play.

The dependency gate is honest and stated: Holodeck integrates the day the pattern-buffer porcelain exists. Until then, design the two surfaces that need no engine — session-zero and the arc layer — which is exactly where the project's originality lives anyway.
