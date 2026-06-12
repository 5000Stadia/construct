# Lexicon — Holodeck

Working vocabulary, under the pattern-buffer lexicon rules adopted
wholesale: (1) every exported name must double-read for an engineer with
zero source-material context; (2) nouns carry the flavor, verbs stay
boring. A term not in this file is added here before it is used twice.
Engine terms (World, PatternBuffer, frame, thunk, frontier,
materialization) are inherited from `/home/k/pattern-buffer/docs/LEXICON.md`
and never redefined.

| Term | Definition | Double-read |
|---|---|---|
| **arc** | The hidden authored destination: a conclusion shape plus beats plus clocks, stored as assertions in a `plot:` frame. | Narrative-canonical (character arc); plain. |
| **beat** | A world-state condition with narrative weight (`achievable_via`), path-independent by definition; never a scripted scene. | Screenwriting-canonical; plain. |
| **clock** | A pre-authored conditional process (`fires_when` → effects through the gate), run by the host's deterministic executor. | Tabletop-canonical (Blades in the Dark progress clocks); plain. |
| **conclusion shape** | The destination as state-shape + character delta (drive inverted, desire at cost, …), never a scene. The pitchable theme; the hidden instantiation. | Plain. |
| **theme consent** | Session-zero move: the player consents to the theme; the plot instantiation stays hidden. Consent and hiddenness coexist. | Plain. |
| **nudge ladder** | The four proportional, diegetic escalation rungs: surface → draw → converge → confront. Timing on the leash, content through the gate. | Plain. |
| **irony delta** | Canon minus `knows:player`, computed host-side as a materialization diff. **Arc-weighted irony delta:** the subset referenced by pending beats — "how much story remains." | Plain compound; heritage: whitepaper §6 "dramatic irony is a computable quantity." |
| **arc repair** | Lazy re-authoring of unreachable beats under the stable conclusion shape, committed as `generated` supersession in `plot:` — accommodation, never intervention. | Plain. |
| **refusal branch** | The mandatory authored ending in which the world's story concludes around an absent protagonist. Refusal is a path, not an error. | Plain. |
| **arc lint** | The deterministic validity checks run on an arc at session zero and after every repair (reachability, path-independence, clock coverage, refusal reachability). | Engineering-canonical (lint); plain. |
| **GM lane** | The arc-layer section of the narrator's per-turn briefing: the `knows:player` scene + NPC intents + ONE pacing directive + resonances. Carries NO `plot:` content — structural spoiler-prevention (letter 012). | Tabletop GM + plain "lane". |
| **scenario** | Session zero's output: the pristine genesis `.world` — self-identifying via charter, shareable, never written by play. | Plain. |
| **playthrough** | A player's accumulated canon within a scenario. v1: one slot per scenario; "start from the beginning" recopies the pristine scenario over the slot. | Plain. |
| **world tick** | The serial write phase of a turn: clock pass → NPC world-actions → beat evaluation (last, sees all mutations). Everything that writes canon finishes before the assembly fan-out reads. | Plain. |
| **narrator** | The principal agent: renders prose from the briefing, speaks to the player, writes NOTHING to canon, sees no `plot:`. The only good-tier call besides the NPC engines. | Plain. |
| **turn trace** | The `--debug` emission alongside a turn's prose: briefing frame list (zero-`plot:` check), cohort trace with tiers, concealment-audit result, triggered beats/clocks/nudges. A formatting of `session:main` + audit rows, never a second bookkeeping. | Plain. |
| **session frame** | The host-owned named frame (`session:main`) holding the turn ledger and pacing receipts — turn boundaries, nudge directives, rung refusals, repair lineages. Same mechanism and doorway as `plot:`; structurally absent from canon. Everything pacing knows folds from it. | Plain. |
| **refusal clock** | The mandatory per-arc clock whose counter-only `fires_when` no in-world behavior can starve; concludes via the refusal variant. The universal backstop for stalls and undetected unreachability. | Plain. |
| **session zero** | The unified creation interview (ingest or live, one wizard under a which-sections-are-known switch): charter, spine, entry, provider, lines-and-veils, arc. | Tabletop-canonical; plain. |
| **lines and veils** | Player content boundaries collected at session zero, stored as covenant-style rules evaluated in the render path — never prompt text. | Tabletop-canonical (safety tools); plain. |
| **dramatic confirmation beat** | The narrowed dispatch gate: a proportional in-fiction confirmation before irreversible player stakes. A dramatic beat, not a permission wall. | Plain. |
| **dispositional spine** | The minimum character material the conclusion generator needs: two ranked drives + one fear or `breaks_if`. Session-zero invariant: no playable character without one. | Plain. |
| **player profile** | Host-side per-player store: provider config, credentials, lines and veils. Never in the `.world` file — worlds ship without secrets or another player's boundaries. | Plain. |
