# construct

> **The Construct** — an interactive-fiction engine that loads a stored world into a *played, remembered* holonovel.
>
> Step into a book, or a world built from a conversation. Put something in a drawer, wander for an hour, come back — it's still there. The world remembers, so the model doesn't have to.

**Status: pre-1.0, first-playable.** The engine plays end-to-end on a real model, and its five-probe acceptance set passes 5/5 in live play (below). Built on [**pattern-buffer**](https://github.com/5000Stadia/pattern-buffer), the append-only world-state engine. Not yet on PyPI.

---

## What it is

Interactive fiction has always had to pick a failure: hand-authored worlds are rich but rigid (every path pre-written), and generated worlds are free but amnesiac (AI Dungeon contradicts itself within twenty turns). The Construct is neither, because it separates two jobs:

- **pattern-buffer** holds the world's *truth* — an append-only log of who/what/where, with object permanence, knowledge frames, and as-of queries. Nothing is forgotten; nothing is invented over canon.
- **The Construct** turns that truth into a *played experience* — it narrates the scene, voices the characters, drives a hidden story arc, and keeps the whole thing coherent turn after turn.

The name is the metaphor: like the Construct in *The Matrix*, it's the runtime that loads any world from stored data into a lived one. The vocabulary stacks:

> **pattern-buffer** holds the pattern → **the Construct** loads it into a played → **holonovel**.

A *holonovel* is a single played world — ingested from a book, or built live through an interview. The Construct is the engine that presents them.

---

## Proven in live play (not just unit-tested)

The real acceptance gate isn't a test suite — it's a person (here, an AI tester) in the player's seat, doing what no eval can. The five-probe set, all verified live:

| Probe | Result |
|---|---|
| **Object permanence** — put a spoon on a table, leave, return | **PASS** — fold-verified, the spoon is there |
| **Loop closure** — a room is the *same* room when you walk back in | **PASS** — memoized furnishing, round-trip |
| **Frame non-leak** — you only ever know what your character knows | **PASS** — structural, every turn |
| **Player agency** — refuse the story and it pushes the *world* at you, never your character | **PASS** — two refusal modes, structurally enforced |
| **Adjudication** — you can't unlock a vault with a key you don't have | **PASS** — the world refuses, with the honest reason |

Each turn runs a deterministic spine with model calls only at the boundaries (narration and character), and turns in well under a minute. The whole live-test arc — including the eight issues play surfaced and the fixes — is recorded honestly in the design docs.

---

## How it works (architecture)

The Construct is a **host** over pattern-buffer — it orchestrates the engine, it doesn't reimplement it. Object permanence, frames, identity, and as-of queries are all *inherited*. What the Construct owns:

- **The turn loop** — a serial mutation spine (classify the player's action → commit it → advance clocks → evaluate the arc) followed by a parallel assembly fan-out (compose the narrator's grounded briefing from the world's truth) and a single render. Writes go first; the narrator sees the *final* world.
- **A six-cohort architecture** (the [Kernos](https://github.com/5000Stadia/Kernos) pattern): classify, ingest, scene-assembler, navigator, beat-evaluator, and per-character NPC engines — small, single-purpose, fail-open. Only the narrator and characters use the expensive model; everything upstream is cheap or deterministic.
- **The arc layer** — a story's destination authored into a hidden `plot:` frame the player can't see, navigated by a pacing ladder with anti-railroading guards. The arc pushes the world *at* you; it cannot move *you*.
- **A provider-agnostic model interface** — bring any LLM; ships with a zero-credit ChatGPT-subscription default.

The hardest problems each got solved by the same move — **structural absence over instruction**: characters can't leak secrets because the secrets were never in their window; the narrator can't spoil the arc because the plot frame is never in its briefing; the story can't puppet your character because your character is never handed to it as a scene entity.

## Documents

- **[docs/CONCEPT.md](docs/CONCEPT.md)** — the founding brief: vision, session-zero, host architecture, the arc layer.
- **[docs/design/ARC-LAYER.md](docs/design/ARC-LAYER.md)** — pacing-as-navigation: the hidden-arc design and its anti-railroading guards.
- **[docs/design/TURN-LOOP.md](docs/design/TURN-LOOP.md)** · **[SESSION-ZERO.md](docs/design/SESSION-ZERO.md)** · **[PROVIDER-INTERFACE.md](docs/design/PROVIDER-INTERFACE.md)** · **[CLI.md](docs/design/CLI.md)**
- **[docs/LEXICON.md](docs/LEXICON.md)** — the working vocabulary.

## Play it

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .

construct play anchor          # step into The Last Honest Meter as Officer Marn
```

That drops you into an interactive prompt — just type what you do, line after line:

```
  The Last Honest Meter
You are person:marn, at place:council_tier.

Type what you do. (:help for commands, :quit to leave.)

> I look around the council tier
[narration]
> I set my brass spoon on the table and head for the wellhead
[narration]
> :quit
The world holds. (saved)
```

Bare `construct play anchor` **resumes** where you left off (every turn is saved); add `--fresh` to start over, or `--debug` to see each turn's receipts. In-session commands: `:debug on|off`, `:help`, and `:quit` / `:exit` / `Ctrl-D`.

For scripting or automated testing there's also a one-shot form — one turn per invocation, the same machinery:

```bash
construct turn anchor "I look around." --debug   # one turn; --debug shows the turn's receipts
construct scenarios                              # list the scenario library
```

The shipped example world, *The Last Honest Meter*, is a complete original noir mystery — a drought-stricken settlement, a master water-meter that died the night an honest technician did. Play it. Put something down and come back for it.

## Family

- **[pattern-buffer](https://github.com/5000Stadia/pattern-buffer)** — the world-state engine the Construct is built on.
- **[Kernos](https://github.com/5000Stadia/Kernos)** — a personal-agent kernel; the source of the cohort architecture the Construct's turn loop borrows.

## License

MIT
