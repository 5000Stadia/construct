# GAUGE-PRIMITIVE — numeric quantities as a live dramatic constraint

**Status:** SEALED. Substrate (`Quantity` condition + accrue wiring + IO round-trip),
parts 3-5 (per-turn drain / narrator surfacing / `failure_when` floor + costly coloring),
and the runtime-seeding fix are all built — 505 green and LIVE-PROVEN 15/15 on the
endurance harness (`logs/validate-endurance-*`: oxygen 100→80→60→20, escape colors
`costly_victory`). Cx-reviewed (letters 149/151/153/154). No PB letter — pure host
orchestration over the shipped `accrue` surface (the living-world-generator posture).
Standing follow-on (NOT this slice, founder's call): authoring integration — a build-time
hook that MINTS gauges for survival/Speed-shaped worlds (the primitive works; nothing
auto-adds one yet).

## The problem it closes

The "throw any story at it" survey (Jurassic / Speed / Abyss / Alien / Spider-Man /
the Hobbit) surfaced exactly **one** register the engine could not carry at fidelity:
the **continuous numeric constraint** — *Speed*'s "stay above 50," a survival story's
draining oxygen, a chase's fuel burn. The tension is a number moving toward a line.

The earlier read ("the substrate isn't there; numeric-quantities is parked") was
**wrong**, and the correction is the whole motivation:

- **PB handles numeric quantities well.** `fold_policy="accrue"` folds a baseline
  literal plus signed `value_type="delta"` rows into a running total
  (`FoldResult.quantity`, surfaced through `state()`); `where(attr, op, value)` and
  `aggregate()` compare/roll them up. (PB WHITEPAPER §"Numeric quantities"; ADOPTION
  §"Numeric quantities".)
- **We already consume it.** `clock.py` runs diegetic time on accrue
  (`ELAPSED_ATTR="elapsed_minutes"`, `commit_elapsed` appends `+N` each turn,
  `read_clock` folds the total). The adoption pattern is proven and live.

The real gap was **host-side and narrow**: the arc **condition grammar**
(`conditions.py`) had no numeric-threshold atom, so a beat / clock / `world_condition`
/ refusal clock could fire on "this happened" or "N quiet turns" but **never on a
gauge crossing a line.** One missing condition type was the entire Speed gap.

## The model

A **gauge** is an ordinary `accrue` attribute — nothing bespoke:

- Entity `gauge:<slug>` (e.g. `gauge:oxygen`), `kind="gauge"`.
- Attribute **`gauge_level`**, declared `fold_policy="accrue"` in
  `semantics.ACCRUE_ATTRS` (a distinctive name, like `elapsed_minutes`, so no plain
  literal inherits accrue folding by accident).
- Optional `gauge_label` (narrator phrasing), `gauge_floor` / `gauge_ceiling` (bounds).
- Unlike monotonic story-time, a gauge moves **both ways**: oxygen drains (−), a
  sealed vent slows the drain, a tank refuels (+).

**The membrane holds:** the engine reads a gauge only as a number. "The tank is
*tense*" is never a stored row — derived drama (suspense, salience) stays
recomputable from the number + the arc, exactly as `dramatic_tension` is never stored.

## The five parts

1. **`conditions.Quantity(entity, attribute, cmp, value, frame="canon")`** — SHIPPED.
   `evaluate` reads the folded total off `world.state(...)` (accrue folds to
   `fact.value`) and compares with `cmp ∈ {>=,>,<=,<,==,!=}` (the field is named
   `cmp`, not `op`, to avoid colliding with `io.expr_to_obj`'s serialization envelope
   key; `quantity` is registered in `io._ATOM_TYPES` so it round-trips through stored
   arcs — `world_condition`/`failure_when`/beats/clocks). **INDETERMINATE** when
   the gauge is unknown/frontier or non-numeric — a never-seeded gauge never
   spuriously trips a terminal. This is the load-bearing piece: any beat / clock /
   `world_condition` / refusal can now trigger on a gauge.

2. **Gauge accrual wiring** — SHIPPED (`construct/gauge.py`): `seed_gauge`
   (idempotent baseline + label/bounds + `kind`), `commit_gauge` (signed delta),
   `read_gauge` (folded total). Mirrors `clock.commit_elapsed`.

3. **Per-turn delta** *(next; Cx review)* — each turn appends a signed delta,
   modulated by the player's action: run the engine hot → fuel −X; seal the vent →
   the oxygen drain slows. Deterministic where the action implies it (mirror
   `clock.deterministic_elapsed`), else a cheap LM estimate (mirror
   `estimate_elapsed` / `delta_from_estimate`). **LM-vs-algorithm wall:** the *rate*
   is interpretation (a model read); the *fold* is arithmetic (the engine). The model
   never states a total — only a signed increment.

4. **Narrator surfacing** *(next; Cx review)* — the gauge IS the tension: a
   pin-channel line each turn its scope is active ("47 and the needle's trembling" /
   "oxygen: 11%"), ranked by salience as the level nears its floor. Awareness only,
   never a stored dramatic fact (pins are host-owned, never canon — Kernos 060 #7).

5. **Terminal coloring** *(next; Cx review)* — a gauge FLOOR is a LOSS, so its
   `Quantity(<= floor)` folds into **`Arc.failure_when`** (the loss terminal,
   `arc_outcome` → `"lost"`), NEVER `world_condition` (the WON path — a positive
   escape/survival condition lives there and still wins a same-tick tie, won-first)
   and never the counter-only `refusal_clock` (lint check 4). Then the final reading
   colors a WIN's conclusion-as-effect (cleared it with room to spare → triumph;
   escaped with the needle trembling → costly_victory) via a per-shape band→outcome
   map. Composes with the `terminal_owner="world_event"` split from the E1 work.

## What it unlocks

The whole continuous-constraint register — *Speed*, the oxygen-drain survival, the
fuel-burn chase — **and** it deepens every endurance / survival / action story
(hull integrity, ammo, the creature's proximity as numeric "heat"). It is the last
open seam in the "let Picard loose in any style" claim.

## Validation plan

Prove the gauge **inside** a survival world rather than in isolation: author a
`creature_feature` station (endurance → `terminal_owner="world_event"`) with a
draining-oxygen gauge, and one scripted live run proves **both** poles at once — the
world drawing the curtain (no accusation) **and** the gauge floor terminating play.
Consolidated, not strapped-on.

## Open questions for Cx

- **Delta authoring (part 3):** deterministic table vs per-turn LM estimate — where's
  the line, and does the estimate fold into the existing `estimate_elapsed` cohort
  (one call, two numbers) or stand alone?
- **Surfacing salience (part 4):** ranking a gauge pin as it nears the floor — reuse
  the pin salience ladder, or a gauge-specific urgency curve?
- **Terminal coloring (part 5):** the band→outcome map (spare / trembling / crossed) —
  is that a per-shape config like `SHAPE_CONCLUSION`, or a generic gauge property?
