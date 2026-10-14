# Construct's own placements are movable state, by rule (R23 lever)

**Status:** spec r2, 2026-10-14, for cr review. Not built.

**r2 (cr RED on r1):** the three build-stage staging sites are added; they place people too, so a model could freeze staging. The site spies enumerate every table row, including the less obvious ones.
**Source:**
- A read-only audit of `run_turn`'s writes and same-turn reads (2026-10-14, against main 1e46d42).
- Run 10's timing log: 69 in-turn "Classify the lifetime" calls, 247 s over 20 turns.
- It replaces TURN-CLASSIFY-ONCE, which stays parked (see "Why not turn batching").

## The facts

- **The engine's durability classifier decides containment by guardrail only for some subjects** (patternbuffer classify.py `_guardrails`):
  - `in` on a `place:` subject is CONSTITUTIVE;
  - `held_by` / `worn_by` / `carried_by` are STATE;
  - **`in` on an `obj:` or `person:` subject goes to the model** (a fixture-vs-movable judgement).
- **`classify="rules"` costs no model call.** It stores the guardrail verdict where one applies, and STATE for every other row. Verified on the pinned engine: `kind` is structural (CONSTITUTIVE), `name` is a guardrail (CONSTITUTIVE), `in` is containment, and for an object or person it falls through to STATE.
- **Construct writes many placements itself, deterministically,** each a fact it has already decided: the player moved, took, dropped or carried something; an NPC moved or now accompanies the player. Today these go through `classify="batch"` (a model call per ingest call) or inline classification. So construct pays a model to judge a fact it already knows, and risks the costly verdict: a portable object made CONSTITUTIVE, which then outranks every later move (the flicker, R20 run 9).
- **The audit's 8 class-dependent cases come from model-judged `in` rows** colliding within a turn. That's also why batching the turn's classification behind a seal is unsafe (below).

## The rule

**Every placement or companionship row construct decides itself is written with `classify="rules"`.** The sites (current main):

| Site | Rows | Today |
|---|---|---|
| `_gated_move_commit` (turnloop ~5135) | the protagonist `in` the destination; a carried object `in` the destination | batch |
| object placed in the pre-move scene (~5260) | `obj in pre_scene` | batch |
| `_grant_moved_place` (~2518) | a new place's `kind` / `name` / `in` container; the protagonist `in` the place; carried objects | inline |
| NPC follows the player (~5718) | `npc in new_scene` | batch |
| companionship (~5738) | `npc accompanying protagonist` | batch |
| departures (~5021 / staged ~5633) | `event:departed_*` rows; `npc accompanying ""` | batch |
| the take grant (~5773 / ~5791) | `obj in protagonist` | batch |
| the drop (~5849) | `obj in pre_scene` | batch |
| `_mint_held_object` (~2125) | a fresh object's `kind` / `name` / `in protagonist` | inline |

**Build-time staging (r2):** the same rule, the same reason. Construct decides these placements itself.

| Site | Rows | Today |
|---|---|---|
| `game._stage_ensure_located_people` | the selected person `in` the selected place | default |
| `game._stage_ground_play_as_figure` | the protagonist `in` the opening place | default |
| `game._stage_cast_in_place` | `cast_location_plan()` rows, plus the protagonist's entry-scene `in` | default |

`commit_carrier_move` (~2691) already uses `rules`. So does the continuation's hook-cast staging (via `arc_io.commit_ops`, whose atomic path is rules-classified).

**What it yields:**
- Every row in the table is classified at write time, with no model call. Placements of objects and people are STATE, which they are by definition: construct just moved them.
- Structural rows (`kind`), names and place containment get their guardrail verdicts, unchanged.

**Unchanged** (they carry claims that need the model's judgement):
- the player-input factual extraction (~4987 / ~5631);
- NPC action extraction (~6091);
- the narrator settle;
- clock effects, reshape rows, mirror rows, and the `claim:` grade.

**The residual, named:** an **extracted** object `in` row (from the player's line, or the narrator's prose) can still be judged CONSTITUTIVE and outrank a same-turn host placement (the audit's cases 2 and 3). pattern-buffer's CONTAINMENT-DURABILITY-V1 closes that at its source, with a confidence floor for movable subjects and host-declared fixtures. It rides the next engine pin.

## Why not turn batching (TURN-CLASSIFY-ONCE stays parked)

The audit found eight cases where a same-turn read would answer differently before and after a deferred seal. Examples:
- a drop against an extracted container row;
- a take against extraction at the same `turn_time`;
- the protagonist's move against an extracted location;
- NPC moves, and clock-effect collisions.

The dependent reads are spread through the turn (locate, route, the scene snapshot, presence, beat_pass), so no single seal point avoids them. Batching would show the narrator one location while canon later serves another. Writing construct's own placements by rule removes most of those model calls at no correctness risk, and leaves the rest classified immediately, as today.

## Expected

Per turn, the classifier calls for the host-placement sites go to zero. Run 10's in-turn count (mean about 3.5 a turn, 2 to 9 s each) falls by the share those sites made. The next R20 run's timing log measures it against run 10.

## Tests

1. **Each site, by spy, one test per table row (r2):** a spy on `ingest_structured`'s kwargs records `classify` per placement row, for:
   - a move (`_gated_move_commit`, with a carried object);
   - the pre-scene object placement;
   - an improvised-place grant (`_grant_moved_place`);
   - an NPC follow;
   - a join and a dismissal (`accompanying` set and cleared, the departure event);
   - a take;
   - a drop;
   - a fresh object mint (`_mint_held_object`);
   - each of the three build stages (`_stage_ensure_located_people`, `_stage_ground_play_as_figure`, `_stage_cast_in_place`, through a stub-provider build).
   Each passes `classify="rules"`. The player-input extraction still passes `batch` (a control).
2. **No model call for a host placement:**
   - a turn where the player takes an object and the extraction returns nothing makes **zero** "Classify the lifetime" calls (stub provider count);
   - the taken object's `in` row is stored STATE (sidecar verdict, read right after the turn).
3. **Guardrails kept:** a granted new place's `kind` and its `in` container are stored CONSTITUTIVE, and its `name` CONSTITUTIVE.
4. **The flicker can't come from a host take:** take an object, then drop it in another place next turn. It reads in the second place, never back in the first (no CONSTITUTIVE host row can exist).
5. **The full suite,** and the turntrace golden moved only by the classifier call counts (explained in the build note).
