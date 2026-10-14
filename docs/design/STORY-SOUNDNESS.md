# Story soundness: can this story be finished? (R35)

**Status:** spec r3, 2026-10-13, for cr review. Not built. It builds after READS-AT-PLAY-HORIZON (it reads through `HorizonView`).

**r2 (cr RED on r1, 502d46d).** Three counterexamples to r1's "no false fatal" claim:
1. **Reshape** (on by default, `reshape_enabled()`) writes arbitrary state, frame and consequence rows after a player action, including revival (`alive` false → true; tests/test_reshape.py:19-78). It's a write channel r1 left out.
2. **P9 doesn't exist.** Nothing in construct writes `event:abandoned*` (grep: only its definitions, in arc/build.py:149 and arc/io.py:389). So the refusal clock of every generated arc can never fire: a real gameplay defect, logged separately (below).
3. **Chapter 2 has no defined cast for delivery.** `continue_episode` authors none, and Session loads the scenario's chapter-1 `meta["cast"]` (session.py:205).

**r2's answer: every finding is ADVISORY in this revision.** The pass runs at every point, reports and is calibrated, but gates nothing. Promoting any rule to fatal is a later spec, with its producer model completed and calibration data behind it. The "provably unproducible" wording is replaced throughout by "unproducible by the ordinary producers P0–P8", stated as what it is.

**r3 (cr RED on r2):** P10's domain was incomplete. Reshape also writes:
- **restage rows on a landing** (`person:x · in · place:y`), which makes `Located`;
- **consequence rows on any tier,** including a non-landing one, and a row `{event:x, kind, signal}` makes `Occurred(signal)`.

P10 now covers both, and fixtures 17 and 18 test them. What P10 can't write is the plot frame: beat status (`BeatAchieved`) and clock firings (`ClockFired`) are written only by `beat_pass` and `clock_pass`. So with reshape enabled, S1 and S2 can only arise through those.
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
| P9 | ~~refusal~~ | **dropped (r2):** no code writes `event:abandoned*`. The refusal clock is excluded from per-arc findings and reported once as a known defect (see "A defect found") | — |
| P10 | reshape, the miracle channel | when `reshape_enabled()`: any `StateIs`, `Quantity`, `InFrame` and revival (`alive` → true) from state and frame rows on a landing; any `Located(x, y)` from restage rows on a landing; any `Occurred(kind)` from a consequence row `{event:…, kind, <kind>}` on **any** tier (r3). It never writes the plot frame, so never `BeatAchieved` or `ClockFired` directly. **Over-approximate by nature:** whether a reshape lands is an earned, cohort-judged miracle. An atom reachable only through P10 gets the finding S12, "relies on a reshape" | reshape.py `apply_reshape` / `reshape_canon` |

**Combinators:**
- `AllOf`: all of its operands produced.
- `AnyOf`: any operand produced.
- `AtLeast(k, ...)`: at least k operands produced.
- `Not(x)`: always counted as produced, because the relaxation can't prove a negation. That's the over-approximation's known blind spot, and P1's "able to act at `h`" handles the one negation that matters (the dead), as a separate ordered fact.

**Output:** the produced set, each atom's first **layer** (the round it entered, h^max-style), and for each unproduced condition a **witness**: its atoms that are unproduced, each with the producers that would have made it and why each didn't apply. Example: "Occurred(confession, participants=[person:breen]): the detector only writes protagonist-only events; no clock effect writes kind=confession".

## Findings (all advisory in r2)

Each finding carries its witness. Severity is a label for later promotion, not a gate:

| Code | Finding | Would-be severity |
|---|---|---|
| S1 | a REQUIRED beat's `achievable_via` unproducible by P0–P8, and not by P10 either | candidate-fatal |
| S2 | `world_condition` unproducible by P0–P8 and P10 | candidate-fatal |
| S3 | a required clue's every live holder is unable to act at `h`. Revival through P10 is possible, so this is advisory by nature | advisory |
| S4 | continuation: a referent, clue holder or hook-cast id that is future-only at `h` (a regression guard behind the horizon view) | candidate-fatal |
| S5 | an OPTIONAL beat unproduced | advisory |
| S6 | a beat whose only path runs through P2's improvised places | advisory |
| S7 | a genuine clue that feeds no beat and no pillar, unless it's a declared red herring | advisory |
| S8 | a cast member with no location at `h` and no producer for one | advisory |
| S9 | fresh build: a beat referent that is future-only at the opening horizon | advisory |
| S10 | `failure_when` unproduced | advisory |
| S11 | no tension and no goal statement | advisory |
| S12 | a required beat or `world_condition` reachable **only** through P10 (a story that needs a miracle) | candidate-fatal, after calibration |

## A defect found: the refusal clock can't fire

`refusal_clock_for` (arc/io.py:381-389; arc/build.py:144-149) fires on `Occurred("event:abandoned[_<arc>]")`, and nothing writes that event. The event detector considers only beats (turnloop.py:3879-3940), and the tangent-cancel path at turnloop.py:346 writes `tangent.PENDING.record = ""` only. So "the player decisively walks away" never reaches the refusal conclusion in a generated arc. This is a separate fix with its own spec (not R35's job). R35 excludes the refusal clock from its per-arc findings and reports the defect once in its calibration note, so it doesn't drown every report.

## Where it runs (r2: report only)

| Point | Today | With R35 r2 |
|---|---|---|
| Fresh build (`game.py:673-752`) | lint, plus cast checks at 904-914 | the pass runs after the arc is accepted. Its report is logged and written to the build's timing/eval log; nothing retries or fails on it |
| `continue_episode` | nothing | the pass runs over the new arc through the chapter's `HorizonView`, **with the cast play will actually use**: the scenario's `meta["cast"]`, loaded exactly as Session does (session.py:205, `cast_from_proposal`). Report only |
| Generator `_preflight` | lint, then decline | the pass's report is logged beside the lint result; no new decline reason |
| Repair, tangent | `lint_post_repair` | unchanged |

**The chapter-2 cast is a finding in itself.** A chapter-2 `InFrame` beat whose fact no chapter-1 clue carries has no deliverer: P1 can't fire for it. R35 reports this (S1 or S12 with the witness "no clue in the play-time cast carries (e, a, v)"). It doesn't fix it; authoring chapter 2's clues and holders belongs to the chapter bridge (R36/B1), and this report is B1's evidence.

**Cost:** no model calls; milliseconds per pass. No retries, so no added authoring time.

## Calibration before it gates anything

Before the fatal findings are wired into the loops, the pass runs read-only over the archived worlds and the in-box worlds:
- run 9 and run 10, each with its chapter-1 world and, where present, its chapter-2 checkpoint, from `/media/k/Blank/construct-scratch/run9|run10/world/`;
- the three bundled worlds.

The build note reports every finding per world. **The rule for later promotion:** a candidate-fatal finding on an arc that actually played through to its conclusion is a false alarm, and that rule can't be promoted. Run 10's chapter-2 checkpoint is the positive control for S4 (its arc was authored before the horizon view).

## Code shape

- **New module `construct/arc/soundness.py`:** pure functions, no I/O, over `(arc, cast, protagonist, reads, horizon_kind)`, returning `SoundnessReport(produced, layers, findings)`. `LintFinding`-compatible findings, so the existing feedback and decline paths take them unchanged.
- **One wiring call** at each point in the table above.
- **The witness text** is short and factual, because it goes back to the arc author as a retry note.

## Tests

**Planted faults,** one fixture each, each with a minimal passing twin:
1. **Event with a participant:** a required beat `Occurred(confession, participants=[person:breen])`, with no clock writing `kind=confession`. With reshape on it's S12; with reshape off it's S1. The twin: a clock effect writes `{event:confession_x, kind, confession}`, so no finding.
2. **Nested event:** a required beat `AllOf(InFrame(...), Occurred(signal))`, so P4 doesn't apply, and no clock writes `kind=signal`. With reshape on it's S12 (only a reshape consequence row could write it, r3); with reshape off it's S1.
3. **Orphan state:** a required beat `StateIs(obj:gate, state, open)`, with the gate shut at `h` and no clock writing it. With reshape on it's S12 (miracle-only); with reshape off it's S1. The twin: an escalation clock's effect writes it, and there's no finding.
4. **S2:** `world_condition = AtLeast(3, BeatAchieved...)` over 4 beats, 2 of them unproducible.
5. **S3:** a required clue's only holder has `alive=false` at `h`. S3 (advisory: revival via P10 is possible); the twin has the holder alive.
6. **S4:** a continuation arc names `person:future`, which exists only at 10,000,000. S4 at continuation; the same arc at a fresh build gives S9.
7. **S7:** a genuine clue feeding no beat or pillar gives an advisory; marked `is_red_herring`, no finding.
8. **Layers and witness:** a 3-step chain (a clue enables beat A; A's clock writes a state; the state enables beat B). The layers come out 1, 2, 3, and removing the clue makes B's witness name the missing clue.
9. **The over-approximation holds:** for every fixture whose arc an existing scripted-play test completes, the pass reports no candidate-fatal finding (S1, S2, S4, S12).

**Wiring (r2: report only):**
10. Fresh build: a stub author's proposal with an S1 fault still builds, and the build log carries the S1 finding and its witness.
11. `continue_episode`, with an `InFrame` beat: the stub generator proposes a chapter-2 arc with one `InFrame(knows:<prot>, fact:new, a, v)` beat that no chapter-1 clue carries, plus one that a chapter-1 clue does carry. The report flags the first ("no clue in the play-time cast carries ...") and not the second. The cast it used is the scenario `meta["cast"]`, and the continuation commits as today.
12. Reshape as a producer: a required beat `StateIs(person:x, alive, true)` with `person:x` dead at `h` and no clock writing it gets S12 (miracle-only), not S1. With `reshape_enabled()` false, it gets S1.
13. The cr oracle: a dead holder revived through the supported reshape path (the shipped revival fixture) then delivers the required clue in a scripted turn. The pass's report for that arc has no S1 or S2, and S3 only as advisory.
14. The refusal clock produces no per-arc finding; the calibration report names the defect once.

**Calibration:**
15. The archived-world report is attached to the build note: every finding per world, with run 10's chapter 2 as the positive control (S4, against pre-view code), and chapter 2's undelivered `InFrame` beats if any.
16. **The full suite.**
17. **(r3) A restaged-only `Located`:** a required beat `Located(person:x, place:far)`, where no ordinary producer places `person:x` there (P2 moves only the protagonist; no clock writes it). With reshape enabled it's S12, not S1 or S2; with reshape disabled it's S1.
18. **(r3) A consequence-only `Occurred`:** a required beat `Occurred(signal)`, with no detector candidate (the beat is nested) and no clock writing it. With reshape enabled it's S12 (witness: "a reshape consequence row on any tier"); with reshape disabled it's S1.
19. **(r3) A plot-only atom:** a required beat `BeatAchieved(beat:ghost)`, where `beat:ghost`'s own condition is unproducible even by P10 (a `ClockFired` of a clock whose `fires_when` is unproducible). It's S1 even with reshape on, since P10 never writes the plot frame.

## Not in scope

- **Prose quality, pacing feel, and whether the story is good.** This checks structure only.
- **The "last described" record** (bardic's other idea). It is a narration item, separate.
- **Exact solvability** (an ordered playthrough exists), via ASP or model checking (DendryScope, Lester). Expensive, and only worth it if R35's relaxation leaves faults that play still finds.
