# The Construct dialogue — the holodeck arrival (design)

**Status:** DESIGN for founder alignment (2026-06-19). No code yet — the house
method is design-first. Supersedes the rigid one-message mode interview
(STARTUP-ENTRY "SHIPPED" block) with a *conversation*; reuses the build
substrate (`cohorts.interview_world` / `author_story`,
`game.create_scenario_from_*`) and the progress pings
(`INGEST-PROGRESS-NOTIFICATIONS.md`). Conversational counterpart to the staged
`SESSION-ZERO.md` wizard — same output brief, warmer front door.

## The feeling we're after (founder)
"Like the computer on the Enterprise as we enter the holodeck — we should be
able to naturally talk with it. It asks qualifying questions, answers our
qualifying questions, and collaborates on the intended shape of the simulation.
Along the way of its questions is the end condition." So: not a form, not a
keyword prompt — a **collaborative dialogue** with a capable host that converges
on a world brief + an end-condition, then builds it (narrating each phase).

## Example arrival (the target feel)
> **Construct:** Online. The grid is empty and waiting. What kind of world do you
> want to step into? Anywhere, anywhen — a rain-soaked detective city, a dying
> star's last colony, a court of feuding mages. Or I can surprise you.
>
> **Player:** Something like a noir mystery but on a space station.
>
> **Construct:** A station noir — recycled air, neon corridors, everyone with a
> secret. Who are you in it? A weary detective on a case, a fixer who knows where
> the bodies are, a newcomer who's stumbled into something? Or someone else.
>
> **Player:** Can I be the station's AI?
>
> **Construct:** You can be anything the fiction can hold — and an AI watching
> through every camera is a wonderful lens for a mystery: you'd see much, touch
> little, move people like pieces. One last thing shapes everything: do you want
> a story that builds toward a real ending — a case to crack, something you can
> win or lose — or an open station to simply inhabit, with no final curtain?
>
> **Player:** A real case. What happens if I lose?
>
> **Construct:** Then the story tells you so honestly — a culprit who slips the
> airlock, a truth that surfaces too late. Losing isn't a game-over screen; it's
> an ending with a different colour, and I keep the destination hidden so the
> tension is real. Ready? I'll need a few minutes to dream the station into
> being, and I'll narrate each step as I build.
>
> **Player:** Go.
>
> **Construct:** Building your world…
> · dreaming the source story · populating the station and its people · hiding
> your case beneath the surface… (~15 min — I'll tell you when the doors open.)

Note what the dialogue does: **asks** qualifying questions (world → role →
end-condition), **answers** the player's questions ("can I be the AI?", "what if
I lose?"), and **folds the mode choice into the conversation** instead of a rigid
prompt. It also always honors "surprise me" / "just start."

## Architecture — a TOOL-USING agent (founder's governing principle)
Founder: "the shape of these things needs to be **tools that the agent can
use**, so we can have natural conversation that is interpreted by the agent —
who knows the intended direction — and utilizes the correct tool / executed
directive from its interpretation." So the Construct is not a fixed wizard; it
is an agent that *talks*, and from each message emits the **tool calls** it
interprets. The host executes them and loops. (The provider is structured-JSON-
out with no native function-calling, so a "tool call" is a structured-output
action the host dispatches — same effect, zero provider/engine work. The
existing `cohorts.entry_agent` is exactly this pattern at single-shot; we evolve
it into a stateful, multi-turn accumulator.)

### 1. The cohort — `architect_turn` (the Construct voice + its tools)
Main-tier. Each call gets the conversation-so-far + the brief assembled so far +
the latest message, and returns its spoken line PLUS the tools it's invoking
this turn (zero or more — "a noir station, and I'm the AI" is two `add_element`
calls in one breath):
```
architect_turn(provider, history, brief_so_far, latest) -> {
  reply: str,                 # always — the Construct's spoken line (in voice)
  actions: [                  # the tools it interprets and invokes this turn
    {tool: "add_element",  detail: str},                 # fold a world element in
    {tool: "set_ending",   mode: "win_loss"|"endless", direction: str},
    {tool: "pick_world",   name: str},                   # route to a ready-made
    {tool: "begin_build"},                               # player satisfied → cook
    {tool: "chat"},                                      # just talk/answer/ask
  ]
}
```
**The tools** (host-dispatched against an `ArchitectState`):
- `add_element(detail)` — append to the accumulating brief. The player can keep
  adding **indefinitely** until satisfied ("…and a T-Rex with a machine gun
  somewhere"); the storymaker cooks with everything brought (founder).
- `set_ending(mode, direction)` — the end-condition, woven into the dialogue:
  `win_loss` + a hidden destination *direction*, or `endless`.
- `pick_world(name)` — universal front door: route to an existing showcase world
  instead of building (only names actually in the library).
- `begin_build()` — fired only when the player signals they're satisfied. The
  Construct should **start decisive but always do a final confirm** ("anything
  else you'd like woven in before I cook?") and keep accepting additions until
  the player says go (founder). Then assemble the brief → build.
- `chat()` — answer the player's question / ask the next one; no state change.

- Leans on smart defaults and treats "surprise me / just start" as license to
  fill the rest and `begin_build`. No list-picking — it curates the coolest
  shape from what was brought (LLM-leverage directive).
- AUTHORING side → may carry the `FICTION_CRAFT` preamble (session-zero only).
- Tagged via the systematic `⟦…⟧` prompt-tagging discipline.

### 1a. The BUILD path is a guided multi-step FICTION-creation interview (founder)
When building a NEW world (not pick_world/resume), the Construct runs a brief
guided, multi-step interview — the world's counterpart to the Foyer's
character-creation — one beat at a time, choose-or-I'll-pick, accepting additions.
Before it cooks, it must EXPLICITLY establish and REFLECT BACK the fiction's
grounding, each anchored to a **close, recognizable analog** (a real era/place or a
well-known fiction), because these change everything a generator produces:
- **WHERE** — setting/location ("a port city like 1880s Marseille").
- **WHEN** — time period ("roughly Prohibition-era").
- **TONE** — named on a spectrum (**gritty realism ↔ heightened drama ↔ campy
  pulp**) — gritty realism is a wholly different world from campy pulp.
Captured via `add_element` with the analog folded in, so the generator builds to
them. "Surprise me / just go" always short-circuits to filling these itself. This
is a directive (prose), not new machinery. (Ingest/ready-made worlds already carry
their setting/time/tone from the source — this is the build path only.)

### 1b. `ArchitectState` — the accumulating brief (host-side, pure Python)
`{elements: list[str], play_as: str, mode, win_direction, chosen_world}`.
Testable without a live model (stub-driven). Renders to the build inputs:
`premise = synthesized(elements)` → `author_story(seed=)` / `interview_world`;
`play_as`, `mode` (→ `mode_override`), `win_direction`.

### 2. A transport pre-session state — "the Atrium"
Today: gate → (one-shot mode prompt) → open world → play. New shape:
```
gate (claim) → ATRIUM (Construct dialogue, N turns) → BUILD (with pings) →
  open session → cold open → play
```
- While in the Atrium, each player message routes to `architect_turn`, NOT a
  `Session.turn` (no world exists yet). The running conversation + accumulated
  brief persist (registry `creation` blob, keyed by player — survives restart;
  appends only, like session-zero checkpoints).
- On `status=="ready"`: send the "building…" heads-up, run
  `create_scenario_from_generated(seed=premise, win_direction=…, on_stage→pings)`
  (or `_interview` for the lighter path), publish a per-player scenario, then
  `Session.open(fresh, mode_override=mode)` and send the cold open.
- The end-condition is decided HERE, in dialogue → it supersedes the keyword
  `_interpret_mode` mode interview (which stays as the fallback for the
  pre-built-world path / players who just want the showcase anchor).

### 3. Universal front door, but ready-mades still reachable
The Atrium is the default arrival, but a player who wants the curated showcase
(anchor) can say so ("just give me a ready world / the detective one") and the
Construct routes them to an existing scenario instead of building. So the dialogue
covers both **build-new** (headline) and **pick-existing** (showcase) — one warm
front door.

### 4. The end-condition connects to conclusion-as-destination
When the player wants an ending, `win_direction` is the seed of the **interesting
destination that buttons up this story** ([[conclusion-as-event-outcome-as-judgment]]
/ CONCLUSION-AND-OUTCOME) — authored hidden, recognized at the third act. The
Construct collaborates on the *direction* ("a case to crack"), never the spoiler.

## Adopted from Kernos (founder: "KERNOS handled this pretty good")
Kernos's integration layer is the proven instance of "natural conversation →
structured tool directive when the provider only emits JSON." Patterns borrowed
(see `/home/k/Kernos` integration/template.py + DESIGN-PRINCIPLES.md):
- **The JSON output IS the tool call** — a strict discriminated-action schema
  (Kernos `decided_action.kind` enum + per-variant required fields). The loop
  orchestration is pure Python, provider-agnostic. ✓ our `actions[].tool`.
- **Always speak a reply** + **cost-asymmetry** ("when in doubt, chat / don't
  bounce back asking the user to restate what they already said"). ✓ (already in
  `entry_agent`).
- **Render context FRESH per turn, don't blind-accumulate** (the "Cognitive UI"
  principle): each call gets the assembled `brief_so_far` + a recent-history
  window, not the raw running transcript. ✓ `ArchitectState` is the rendered brief.
- **Show the schema at the decision point** (recency): tool spec near the END of
  the prompt. ✓
- **Typed failure / no silent degradation**: a malformed turn fails loud, never a
  vague reply. ✓
- **Divergence (justified):** Kernos splits integration (decide) from presence
  (express) across two cohorts and loops within a turn for read-tools. The
  Construct needs neither — its actions are pure state-appends + `begin_build`
  (no within-turn reads), and its single voice IS the presence. So `reply` +
  `actions[]` come back in ONE call, and the loop is across USER turns. We keep
  the strictness, drop the two-layer weight.

## What this reuses vs. adds
- **Reuses:** `interview_world`/`author_story` (brief → world), the whole
  `create_scenario_from_*` build + viability gate, per-player slots, the cold
  open, the mode plumbing (`mode_override`), the `on_stage` hook.
- **Adds:** the `architect_turn` cohort; the Atrium pre-session state in
  `transport_core` + a registry `creation` blob; the interim-send `notify`
  channel (the pings, per INGEST-PROGRESS-NOTIFICATIONS); the build trigger.

## Forks — RESOLVED (founder, 2026-06-19)
1. **Front-door scope → UNIVERSAL.** One dialogue: build-new (headline) OR route
   to a ready-made via `pick_world`.
2. **Reach → DECISIVE, then a satisfaction loop.** Start decisive, but ALWAYS do
   a final confirm ("anything else you'd like woven in?") and keep accepting
   additions until the player says go — they can layer endlessly (the T-Rex with
   a machine gun); then the storymaker cooks with all of it.
3. **Persona → "the Construct": between the Enterprise computer and Wadsworth,
   the butler from *Clue*** — a capable, lightly-characterful holodeck-arch host
   introducing the situation to the guest. Calm and helpful (the computer) with a
   touch of warm, knowing host (the butler welcoming you in). Never hammy.

## Build order (after alignment)
1. **DONE (2026-06-19).** `architect_turn` cohort (`cohorts.py`, tag `cst`, main
   tier) + host tool loop (`construct/architect.py`: `ArchitectState`,
   `architect_step`, outcomes continue/build/load) + 11 stub tests
   (`tests/test_architect.py`) + an offline live harness
   (`scripts/architect_demo.py`). Live-run confirmed the voice + convergence: it
   asks (world→role→ending), answers the guest's questions, accepts unlimited
   additions (the T-Rex), does a final confirm, and on "go" assembles a clean
   brief (premise/play_as/mode/win_direction). 243 tests green.
2. **DONE (2026-06-19).** The interim-send `notify` channel
   (`TransportCore(notify=…)`, wired to Telegram `sendMessage`; best-effort,
   outside the exactly-once outbox) + `on_stage→_humanize_stage→notify` bridge
   (warm per-phase pings; per-chunk collapsed to one counter; internal stages
   silent). The build heads-up + "doors open" bookend it.
3. **DONE (2026-06-19).** The Atrium in `transport_core` (`_atrium`,
   `_enter_world`, `_build_and_enter`) + registry `creation` blob persistence
   (survives restart) + `set_scenario` (repoint to the built per-player world
   `live_<platform>_<id>`). Replaces the keyword `_interpret_mode` mode interview
   as the default arrival (the gate now sends `GREETING`); `_interpret_mode`
   stays defined as an unused fallback. `pick_world` is the universal-front-door
   load path. 246 tests green (14 new across architect + atrium + humanize).
4. **IN PROGRESS.** Live-verify: the offline architect demo confirmed voice +
   convergence (4 scripted arrivals); a real end-to-end build+enter
   (`scripts/verify_build_enter.py`) de-risks the generate→enter path before the
   Telegram restart. Then Codex review.

## Known v1 constraint (single-process demo)
A build runs SYNCHRONOUSLY inside the turn (the poller blocks ~16 min while it
runs), so the progress pings reach the building player but OTHER players wait
until it finishes. Acceptable for the trusted-tester demo (consistent with the
transport's existing single-process scoping); a background-build worker is the
post-demo fix.
