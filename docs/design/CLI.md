# The Player CLI — interactive REPL + one-shot turn

**Status:** Shipped. Two surfaces over one turn function
(`construct.turnloop.run_turn`): an interactive **REPL** for humans
(letter 032) and the **one-shot `turn`** for scripting, tests, and the
live-tester (letters 017/019). The REPL is a loop around the same
machinery — zero change to the turn loop, cohorts, or engine.

**One sentence:** the `.world` file IS the state and a turn is
load → ingest → render → save; the REPL opens the world once and loops
read→turn→print, while `turn` does exactly one of those per process —
same function, two transports.

## Commands

```
construct scenarios
    List the scenario library — charter self-ID: title / stance /
    description (the ship in a bottle, labeled on the glass).

construct new --ingest <path> [--name <name>]
    Session-zero via fiction ingest → a new pristine scenario.
    (--interview follows post-first-playable.)

construct play <scenario> [--fresh] [--debug] [--at COORD]
    THE PLAY INTERFACE. Load/resume the single playthrough slot, print
    the opening, then loop: read a line → run one turn → print the
    prose → repeat, until you exit. Bare `play <scenario>` RESUMES
    (progress saved every turn); `--fresh` recopies the pristine
    scenario over the slot first; `--debug` starts with the trace on.
    `--at COORD` ENTERS at a timeline coordinate (ENTRY:WHERE): the
    establishing view is materialized as-of it ("the world at rest" at
    that point), recorded on a fresh playthrough and restored on resume.
    Default entry is the timeline head. (v1: the entry coordinate governs
    the establishing entry view; turns still run forward at TURN_EPOCH —
    rewinding ongoing play below entry is a documented future deepening.)

construct turn <scenario> "<player input>" [--debug]
    One-shot: process exactly one turn against the saved slot — the
    full TURN-LOOP DAG — print the prose, save, exit. Retained for
    scripting, automated tests, and the agent live-tester. One call =
    one turn.

construct knows <scenario> <character> [--contrast <other>]
    Inspect a character's authored knowledge frame (knows:<id>), or with
    --contrast show how two characters' knowledge DIVERGES over the same
    world — the structural-non-leak demo (play the detective vs the clerk
    who hid the core: provably different information states). Read-only,
    deterministic, no model call.
```

## The REPL session (letter 032)

```
$ construct play anchor
  The Last Honest Meter
You are person:marn, at place:council_tier.

Type what you do. (:help for commands, :quit to leave.)

> I look around the council tier
  (the world turns… / 12s)
[narration]
> :quit
The world holds. (saved)
```

- **In-session commands:** `:help`, `:debug on|off` (toggle the trace
  mid-session), `:quit` / `:exit` / `Ctrl-D`. Empty lines are ignored;
  an unknown `:command` is reported, not run as a turn.
- **Meta/chat is already handled** — the classifier cohort routes
  action / question / out-of-character, so "what can I do?" or a
  question resolves through the existing turn path. The REPL prints
  whatever comes back; there is no separate chat mode.
- **The spinner** ("the world turns… N s") shows only on a TTY, so
  piped/captured runs stay clean; turns take ~50s on the good-tier
  narrator.
- **Save is free:** each turn persists to the slot, so exiting and
  re-entering resumes mid-scene. The opening banner is deterministic
  (no model call) — launch is instant; type "look around" for a
  furnished render.
- **Loud-but-survivable:** a turn that raises is reported on stderr and
  the loop continues; the world is closed cleanly on exit.

## `--debug`: the turn trace

`--debug` (on `turn`, or toggled in the REPL) emits, alongside the
prose, the turn's receipts:

- the assembled briefing's **frame list** — verifies zero `plot:` rows
  (TURN-LOOP criterion (b));
- the **cohort trace** — which cohorts fired, at which tier;
- the **concealment-audit** and **player_boundary** results (post-hoc);
- any beat / clock / nudge that triggered, and the **adjudication**
  verdict.

The prose tells you it's *good*; the trace tells you it's *correct* —
the trace is a formatting of `session:main` + audit rows, never a
second bookkeeping.

## The five-probe set (verified live, all PASS)

1. **Object permanence** — put an object down, wander, return.
2. **Non-leak** — the briefing never holds a fact only another frame
   knows (criterion (g)).
3. **Loop closure** — a described place is the same place on return.
4. **Player agency** — refuse the arc; it pushes the world at you,
   never your character (two refusal modes).
5. **Adjudication** — attempt the impossible (a key not held);
   `locate()` is the rules lawyer, the world refuses diegetically.

## Standalone, not host-shaped (letter 032)

Construct ships this *minimal* CLI/REPL so a holonovel is playable and
demoable with no host — the REPL is transport (text in, text out), not
a cohort; the six cohorts already do the turn processing. The rich,
ambient, multi-user chat experience is the adopting host's job (Kernos,
via the adapter) wrapping the same engine; Construct never builds the
heavy chat in or duplicates it.
