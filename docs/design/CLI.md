# The Player CLI — agent-drivable, one-shot per turn (design)

**Status:** Surface settled pre-freeze (Kernos letter 017,
founder-directed); built at first-playable. Kernos CC is the assigned
live tester, driving from the player's seat — so the CLI is
agent-drivable by construction, and it is also the real product
surface, not a test harness.

**One sentence:** the `.world` file IS the state and a turn is
load → ingest → render → save, so turns are discrete one-shot
invocations — stateless per call, stateful via the playthrough slot —
which is exactly what both a human shell and a testing agent drive
cleanly.

## Commands

```
construct scenarios
    List the scenario library — charter self-ID: title / stance /
    description (the ship in a bottle, labeled on the glass).

holodeck new --ingest <path>
    Session-zero via fiction ingest → a new pristine scenario.
    (--interview follows post-first-playable.)

construct play <scenario> --fresh | --resume
    Establish or resume the single playthrough slot (letter 013);
    prints the opening render.

construct turn <playthrough> "<player input>"
    THE LOAD-BEARING ONE: process exactly one player turn against the
    saved playthrough — the full TURN-LOOP DAG — print the rendered
    prose to stdout, save. One call = one turn.
```

## `--debug`: the turn trace

`turn --debug` emits, alongside the prose, the turn's receipts:

- the assembled briefing's **frame list** — to verify zero `plot:`
  rows, grep-able (TURN-LOOP criterion (b));
- the **cohort trace** — which cohorts fired, at which tier (criterion
  (e)'s two-good-call audit);
- the **concealment-audit** result (post-hoc, letter 006 note 2);
- any beat / clock / nudge that triggered this turn.

The prose tells the tester it's *good*; the trace tells them it's
*correct* — receipts culture applied to live testing. The trace is a
formatting of `session:main` + audit rows, never a second bookkeeping.

## The live-test probes (expected; design must survive them)

1. **Drawer test, live** — put an object down, wander, return.
2. **Non-leak** — play a canon character; the briefing must never
   contain a fact only another frame holds (criterion (g)).
3. **Loop closure** — return to a described place: same place, no
   duplicate.
4. **Refusal probe** — refuse the arc's direction for several turns:
   adapt, never rail (the §5 ladder + §8 limit under live fire).
5. **Adjudication** — attempt the impossible (a key not held):
   `locate()` adjudicates; the world refuses diegetically.

Findings arrive as [STATUS]/[BLOCKED] letters.

## Pre-staged now (engine-free)

`holodeck/cli.py` parses all four commands and `--debug` today; every
command exits 2 with a named "waiting on the porcelain freeze" message
until integration wires it. The parser is tested; first-playable wiring
replaces the exits, not the surface.
