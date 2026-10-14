# Story soundness: can this story be finished? (R35)

**Status:** spec r1, 2026-10-13, for cr review. Not built. It builds after READS-AT-PLAY-HORIZON (it reads through `HorizonView`).
**Source:** plan item A, approved by Kabe 2026-10-13 ("Sounds good on A and B"). The prior-art scan is archived at `/media/k/Blank/construct-scratch/r35-prior-art/`.

## What already exists (and stays)

- **The plot linter** (`arc/lint.py`) has 8 checks:
  - referents exist;
  - two climax paths (advisory);
  - required beats have clocks;
  - the refusal clock;
  - no plot-frame gating;
  - budgets;
  - confront scale;
  - no self-learning.

  It is fatal at build (`game.py:673-752`, 3 attempts with the findings fed back), a decline in the generator's `_preflight` and in repair, and **absent from `continue_episode`.**
- **The cast checks at build** (`game.py:904-914`):
  - `check_solvability`: every required pillar has a genuine live-reachable clue; debunkers are reachable; holders are known; staging rules for deductions;
  - `validate_beat_delivery`: a required `InFrame` beat has a matching live clue on a reachable holder;
  - `validate_signature_support`.
- **The viability gate** (`_assess_viability`, Stage 7): title, protagonist located, at least 2 people and 1 place, a non-empty opening, not won at genesis.

## The gaps (facts from the code)

1. **Chapter 2 and later get none of these.** `continue_episode` retries `_build_arc` only on exceptions (`game.py:~3340`); no lint, solvability or delivery check runs.
2. **Events the player can't cause.**
   - The play-time event detector (`_fire_event_occurs`, turnloop.py:3879-3940) considers only beats whose `achievable_via` is a **bare** `Occurred`.
   - It writes the event with `agent = protagonist` and no other participant.
   - So an `Occurred(kind, participants=(person:x,))`, or an `Occurred` nested inside `AllOf`/`AnyOf`/`AtLeast`, can only become true if a clock effect or an existing row produces it.
   - Nothing checks this.
3. **States nothing writes.** `StateIs` and `Quantity` (other than `time:elapsed`) have no player write path. Such a condition is satisfiable only by an opening fact or a clock effect. Nothing checks this either.
4. **The dead as producers.** `validate_beat_delivery` counts a holder as reachable without asking whether that holder can act at the opening (`person_can_act`, arc/executor.py:274). A dead holder's clue can't be asked for.
5. **The hidden future.** Nothing checks that a chapter's plot, clue holders and hook cast exist at the player's horizon. Run 10's chapter 2 was built on source-future props. READS-AT-PLAY-HORIZON closes the cause; this is the regression guard.

## The check: one producer fixed point

The prior art is planning's delete-relaxation reachability (Helmert 2009, Fast Downward's translator), adopted as an idea only:
- start from what is true at the horizon;
- repeatedly add what any producer could make true;
- stop at the fixed point.

It over-approximates (deletions are ignored), so **anything outside the fixed point is provably unproducible, with no false alarms on that verdict.** The cost is that it can miss subtler faults; those stay advisory.

**Input:** the arc (beats, clocks, refusal clock, `world_condition`, `failure_when`), the cast (`meta["cast"]`), the protagonist, and a `WorldReads` at the horizon `h`:
- for a fresh build, the opening horizon (`opening_as_of`);
- for a continuation, the chapter's `h` from READS-AT-PLAY-HORIZON;
- for a legacy world, the head.

**Producers,** each a rule from the code's real write paths:

| # | Producer | Produces | Code path it models |
|---|---|---|---|
| P0 | the world at `h` | every atom true at `h` (`evaluate(atom, reads) is TRUE`) | — |
| P1 | clue delivery (ASK or EXAMINE) | `InFrame(knows:<protagonist>, e, a, v)` for each clue `(e, a, v)` whose `reveal_condition` is live, on a holder that is physically reachable (`_reachable_nodes`) **and** able to act at `h` (`person_can_act`; objects and places always can) | turnloop.py:5918-5990 |
| P2 | movement and improv | `Located(protagonist, P)` for any `place:` P. Improvised moves can mint a place, so this is over-approximate; a P that doesn't exist at `h` makes an advisory note "relies on improvisation" | turnloop.py:4892, `_grant_moved_place` |
| P3 | take and drop | `Located(obj, protagonist)` and `Located(obj, P)` for any `obj:` that exists at `h` | turnloop.py:5515-5606 |
| P4 | the event detector | `Occurred(kind, participants)`, only when some beat's `achievable_via` **is** that bare atom and `participants ⊆ {protagonist}` | turnloop.py:3879-3940 |
| P5 | clock firing | `ClockFired(c)` when `c.fires_when` is produced. Counter atoms (`TurnsElapsed`, `TurnsQuiet`) are always produced | arc/executor.py:54-102 |
| P6 | clock effects | for a fired clock, each effect row `(e, a, v)`: `StateIs(e, a, v)`; `Occurred(v)` when `a == "kind"` (the clock's event entity); and `Quantity(e, a, ...)` as satisfiable (monotone over-approximation) | arc/executor.py:54-102 |
| P7 | beat achievement | `BeatAchieved(b)` when `b.achievable_via` is produced | arc/executor.py:105-160 |
| P8 | time | `Quantity(time:elapsed, ...)` is always produced (time advances) | clock.py `commit_elapsed` |
| P9 | refusal | `Occurred("event:abandoned...")`, via the abandonment detector **(the build note confirms where that row is written; if no path writes it, P9 is dropped and the refusal clock becomes a finding)** | turnloop.py:346 |

**Combinators:**
- `AllOf`: all of its operands produced.
- `AnyOf`: any operand produced.
- `AtLeast(k, ...)`: at least k operands produced.
- `Not(x)`: always counted as produced, because the relaxation can't prove a negation. That's the over-approximation's known blind spot, and P1's "able to act at `h`" handles the one negation that matters (the dead), as a separate ordered fact.

**Output:** the produced set, each atom's first **layer** (the round it entered, h^max-style), and for each unproduced condition a **witness**: its atoms that are unproduced, each with the producers that would have made it and why each didn't apply. Example: "Occurred(confession, participants=[person:breen]): the detector only writes protagonist-only events; no clock effect writes kind=confession".

## Findings and severity

**Fatal** (the story can't be finished):

| Code | Finding |
|---|---|
| S1 | a REQUIRED beat's `achievable_via` is unproduced |
| S2 | `world_condition` is unproduced: the chapter can't be won (e.g. `AtLeast(k, BeatAchieved...)` with fewer than k producible beats) |
| S3 | a required clue's every live holder is dead, or unable to act, at `h` (gap 4) |
| S4 | **continuation only:** a beat referent, clue holder or hook-cast id that exists after `h` but not at `h`. A future-only id (gap 5) is a regression guard behind the horizon fix |

**Advisory** (logged, and listed in the build note's report):

| Code | Finding |
|---|---|
| S5 | an OPTIONAL beat unproduced |
| S6 | a beat whose only path runs through P2's improvised-place over-approximation |
| S7 | a genuine clue that feeds no beat and no pillar (Chekhov), unless it is a declared red herring (`is_red_herring`) |
| S8 | a cast member with no location at `h` and no producer for one |
| S9 | **fresh build only:** a beat referent that exists only after the opening horizon. The arc author sees the whole hidden story by design, so this is measured before it could ever become fatal |
| S10 | `failure_when` unproduced (the chapter can't be lost: noted, not wrong) |
| S11 | no tension or goal: an empty `shape.tension`, and no `goal_statement` in meta |

Advisory findings are promoted to fatal only by a later spec, after calibration shows they don't false-alarm.

## Where it runs

| Point | Today | With R35 |
|---|---|---|
| Fresh build (`game.py:673-752`) | lint, plus cast checks at 904-914 | the soundness pass joins the same 3-attempt loop. Fatal findings are added to `last_findings` with their witnesses, so the author sees the reason, exactly as lint findings are fed back today |
| `continue_episode` | nothing | **new:** `lint_arc`, `validate_beat_delivery` over the new arc's `InFrame` beats, and the soundness pass, inside its existing 3-attempt loop, reading through the chapter's `HorizonView`. A fatal finding becomes a retry with the findings as the build note (the loop's `_build_note` mechanism); after 3 attempts it raises, as a failed build does today |
| Generator `_preflight` | lint, then decline | the soundness pass's fatal findings join the decline reasons |
| Repair, tangent | `lint_post_repair` | unchanged in r1. Mid-play repair works on a live world; it is noted for a later revision once r1 is calibrated |

**Cost:** no model calls. A fixed point over at most a few hundred atoms is milliseconds. One retry, when a fatal finding fires, costs one arc authoring call (about 1 to 2 minutes), the same as a lint retry today.

## Calibration before it gates anything

Before the fatal findings are wired into the loops, the pass runs read-only over the archived worlds and the in-box worlds:
- run 9 and run 10, each with its chapter-1 world and, where present, its chapter-2 checkpoint, from `/media/k/Blank/construct-scratch/run9|run10/world/`;
- the three bundled worlds.

The build note reports every finding per world. **The rule:** a fatal finding on an arc that actually played through to its conclusion is a false alarm, and the rule that produced it is fixed (or demoted to advisory) before it lands. Run 10's chapter-2 checkpoint is expected to show S4 against today's code: the leak, as a positive control.

## Code shape

- **New module `construct/arc/soundness.py`:** pure functions, no I/O, over `(arc, cast, protagonist, reads, horizon_kind)`, returning `SoundnessReport(produced, layers, findings)`. `LintFinding`-compatible findings, so the existing feedback and decline paths take them unchanged.
- **One wiring call** at each point in the table above.
- **The witness text** is short and factual, because it goes back to the arc author as a retry note.

## Tests

**Planted faults,** one fixture each, each with a minimal passing twin:
1. **S1 event with a participant:** a required beat `Occurred(confession, participants=[person:breen])`, with no clock writing `kind=confession`. The twin: a clock effect writes `{event:confession_x, kind, confession}`, and so produces it.
2. **S1 nested event:** a required beat `AllOf(InFrame(...), Occurred(signal))`, so P4 doesn't apply. Fatal.
3. **S1 orphan state:** a required beat `StateIs(obj:gate, state, open)`, with the gate shut at `h` and no clock writing it. The twin: an escalation clock's effect writes it.
4. **S2:** `world_condition = AtLeast(3, BeatAchieved...)` over 4 beats, 2 of them unproducible.
5. **S3:** a required clue's only holder has `alive=false` at `h`. Fatal; the twin has the holder alive.
6. **S4:** a continuation arc names `person:future`, which exists only at 10,000,000. Fatal at continuation; the same arc at a fresh build gives advisory S9 only.
7. **S7:** a genuine clue feeding no beat or pillar gives an advisory; marked `is_red_herring`, no finding.
8. **Layers and witness:** a 3-step chain (a clue enables beat A; A's clock writes a state; the state enables beat B). The layers come out 1, 2, 3, and removing the clue makes B's witness name the missing clue.
9. **The over-approximation holds:** for every fixture whose arc an existing scripted-play test completes, the pass reports no fatal finding.

**Wiring:**
10. The fresh build: a stub author's first proposal has S1. The retry note contains the witness, and the second (clean) proposal builds.
11. `continue_episode`: a stub generator's first proposal has S4. It retries, and after 3 bad proposals it raises without writing anything (the atomic commit never runs).
12. The generator's `_preflight` declines with the S-code in the reason.

**Calibration:**
13. The archived-world report is attached to the build note, with the run 10 chapter-2 positive control showing S4.
14. **The full suite.**

## Not in scope

- **Prose quality, pacing feel, and whether the story is good.** This checks structure only.
- **The "last described" record** (bardic's other idea). It is a narration item, separate.
- **Exact solvability** (an ordered playthrough exists), via ASP or model checking (DendryScope, Lester). Expensive, and only worth it if R35's relaxation leaves faults that play still finds.
