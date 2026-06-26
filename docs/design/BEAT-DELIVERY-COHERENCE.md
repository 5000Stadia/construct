# Beat ↔ Delivery Coherence (observation #3)

## The problem (diagnosed 2026-06-25, confirmed live)

An arc has two parallel coverage systems, authored by two **independent** LM calls:

- **Beats** (`author_story`, `game.py`) — the dramatic ladder (SETUP→RISING→CRISIS→CLIMAX→
  FALLING). A `player_learns` beat is an `InFrame(knows:<protagonist>, entity, attribute,
  value)` condition: it fires when that fact lands in the player frame. An `event_occurs`
  beat is an `Occurred(kind)`: it fires through EVENT-OCCURS-FIRING when an act lands.
- **Pillars + clues** (`author_cast`, `cohorts.py`) — the conclusion-as-effect coverage. The
  cast holds `Clue`s whose `surface_fact` fills pillars when surfaced into the player frame.

**Nothing connected them.** The only way an InFrame beat's fact reaches the player frame is
through cast-clue delivery (ASK/EXAMINE/RELATE → `learn_clue_items`). But `author_cast` chose
its own `surface_fact`s to fill *pillars*, with no guarantee any clue surfaced a given *beat's*
target fact. So the InFrame rising beats (SETUP/RISING/CRISIS) routinely had **no delivery
path** and could never fire.

### The live symptom
The endurance shape proof showed `act=I` and `learned=-` for every turn until the Occurred
CLIMAX beat fired (turn 5, via EVENT-OCCURS-FIRING) and concluded `quiet_failure`. The arc
**skipped its entire SETUP→RISING→CRISIS ladder** — only the act-climax fired — so the Act-II
suspense amplifier (`_convergence_directive`, keyed off `current_phase`) never engaged. The
phase machinery was correct; there were simply no achieved rising beats to climb to.

### Why deduction (anchor) worked anyway
A detective interviews exactly the suspects whose digest facts the beats gate on, so clue
delivery *coincidentally* surfaced them. The other eight shapes author relationship/resource/
site clues that fill pillars but don't map to beat facts → every non-deduction arc rushed its
Occurred climax and played shallow. This is the SHAPE-STRUCTURES.md "RELATE/ACT delivery is the
gap" item, precisely located: it's an **authoring-coherence** gap, not a delivery-code gap.

## The fix (LM authors, deterministic check — per the LM-vs-algorithm guardrail)

Unify the two tracks **at authoring time, interpretively**. After `author_story` produces the
arc, extract its InFrame beats as **delivery targets** and feed them to `author_cast` as
REQUIRED facts the cast must make surfaceable. The **LM** authors the clue — which member holds
it, its hook, its juice, its reveal_condition — keeping all the interpretive work with the
model. We only insist the *fact* ships, and **validate that deterministically** (a rigid
exact-match check, the appropriate use of an algorithm).

### Pieces
- `cast.beat_delivery_targets(beats)` — the arc's InFrame beats as target dicts
  (entity/attribute/value + phase + required + beat_id). Occurred beats are excluded (they fire
  through EVENT-OCCURS-FIRING, not clue delivery).
- `cohorts.author_cast(..., beat_targets=...)` — a binding prompt block ("THE ARC'S
  RISING-TENSION BEATS NEED DELIVERY") listing each target; the LM must author a clue whose
  `fact` is EXACTLY each REQUIRED one, held by a reachable member at a LIVE-reachable condition
  (`none`/`pressure` to ask a person; `examined`/`scrutiny` to inspect an object/site — matching
  `_live_reachable()`). A beat fact may ride the same juicy card as a pillar clue. Uses the EXACT
  canon entity ids.
- `cast.validate_beat_delivery(beat_targets, cast)` — deterministic lint: every REQUIRED
  InFrame beat must have a clue whose `surface_fact` matches exactly, live-reachable AND held by
  a physically reachable member (`_reachable_nodes`). Required-only, mirroring
  `check_solvability`. Merged into the same `author_cast` feedback/retry loop in `game.py`.

### A free win: coreference alignment
The exact fact-match also forces the arc author and the cast author onto the **same canon
entity id** (the obs #3 fixture had beats on `person:elias` while the cast held clues on
`person:elias_baptiste` — a split that made every InFrame beat undeliverable). The validator
now rejects that split, so the retry loop drives them back into agreement.

## Why this is the keystone for per-genre richness (task #33)
Without the rising beats firing, EVERY non-deduction shape rushes its Occurred climax and skips
the tension build. Making the InFrame ladder deliverable is what lets all nine shapes reach the
same depth as the Deduction template — the genre-faithful staging/opening/delivery/conclusion
each shape was supposed to get.

## Status
**Authoring half SHIPPED + Cx-GREEN 2026-06-25** (letter 121). Unit tests in `tests/test_cast.py`
(extractor + 4 validator cases); full suite 474 green. Authoring validation is live-proven:
`scripts/beat_delivery_check.py` (one author_cast call per genre) and a fresh 31-min
`create_scenario_from_generated` endurance build both show `validate_beat_delivery == NONE` on a
real generated arc — every required InFrame beat has a live-reachable clue surfacing its exact
fact, coreference clean.

**Half 2 (topic-aware delivery) — SHIPPED + LIVE-PROVEN (Cx 129/130 GREEN).** `classify` returns
`asks_targets` (opaque ask_N candidate ids → clues) from entry-scene present holders; the delivery
loop selects the targeted clue ONLY among `revealable_clues(node, pressure=pressing)` (the
deterministic reveal gate stays authoritative), fallback to authored order. The clues now both
EXIST (half 1) and SURFACE on-topic (half 2).

**3a (entry-epoch staging) — SHIPPED (Cx 127/129/130 GREEN).** A per-scenario entry epoch above
every pre-play `valid_from` (`executor.compute_entry_epoch` + contextvar; staging `in` rows on the
entry axis) so the opening cast wins the containment fold over aftermath rows the source narrates —
fixing the scatter that left beat-clue holders absent. No-op for worlds whose pre-play rows all sit
below `TURN_EPOCH`.

**The whole chain is LIVE-PROVEN end-to-end:** `scripts/validate_reshaped.py` — a hand-authored
clean world (immune to auto-build variance) — fires **11/11** reshaped mechanisms in a scripted live
playthrough: the rising-tension ladder fires turn-over-turn (witness→signed→seized), the act climbs
I→II, EVENT-OCCURS fires the Occurred climax, and it concludes `triumph`. obs #3's original symptom
(`act=I` forever, beats never firing) is RESOLVED. That script is the permanent regression harness.

**Adjacent follow-ups (vet-pending / deferred):** self-referential-beat lint (SHIPPED — `lint_arc`
check `8-self-learn`); the opening-state dossier (3b — deferred: 3a handles the scatter class, and
coreference dupes are reconcile/PB territory, not the dossier's).
