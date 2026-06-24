# Diegetic time — the story's own clock (design)

**Status:** DESIGN for founder alignment + a PB engine-boundary confer (2026-06-19).
Founder direction: the engine must intuitively track in-world time by what's
HAPPENING, not by turn count.

## The need (founder)
- Time advances **relative to events**, not per turn. A caravan trip across the
  kingdom that started at high noon does NOT arrive at high noon. Twenty turns
  examining a crime scene might be twenty minutes.
- The player can **direct time**: "I wait until sunset and go to the bar to meet
  the contact." "Rest until morning." "Three days later, I return."
- It "needs to be considered" — the world (and its prose, light, who's about)
  should reflect the hour.

## The model — a HOST-side clock stored as canon, on a WORLD-SPECIFIC calendar
A **diegetic clock** the host maintains and the engine remembers (so it re-enters
coherently and the narrator/NPCs read it natively — the project's whole thesis is
"the world remembers" via the pattern-buffer). Two canon entities:

**`time:calendar` — the world's TIME MODEL (founder: time is world-specific).** Time
of day is tracked the same way everywhere, but the SHAPE of time belongs to the
world — "I should be able to be on a world where the days are 72 hours long." So
the calendar is authored at world creation and stored as world canon (copied into
each slot — per-world, tied to the world's cursor). Fields:
- `hours_per_day` (default 24; a fantasy world might set 72),
- `phases` (ordered time-of-day bands with their fractional/absolute bounds —
  dawn/morning/noon/afternoon/dusk/evening/night by default; a world may rename or
  re-proportion them, e.g. twin suns, a long dusk),
- optional flavor (`day_name`, `unit` names, seasons) — additive.
Default is Earth-like 24h; the world author overrides when the fiction implies it.

**Per-LOCATION calendars (founder: a space adventure — each planet has its own
orbital day/night).** The calendar isn't only per-world; a PLACE can carry its
own. The elapsed counter is UNIVERSAL (real time passing, one accrue total), but
the time-of-day the player experiences is resolved against the calendar of **where
they're standing** — so it can be noon on one planet and midnight on another, out
of sync. A place's calendar adds an `offset_minutes` (where that body sits in its
cycle at t=0) on top of `hours_per_day`/`phases`, so two planets with the same day
length still differ in phase. Resolution each turn: the player's current location's
calendar → else the world's `time:calendar` default → else Earth-like.

**It's a CONSTITUTIVE universal condition of the planet, and RARE (founder).** A
non-Earth day/night is established in the PB like any other physical truth of the
place — read straight off the location as a plain constitutive attribute
(`hours_per_day` / `day_hours` / `day_length_hours`) OR a full `calendar` JSON
blob; not a bolted-on time config. **Most stories are Earth-default (24h)** and
author nothing; only a world with distinct bodies (a space adventure) establishes
per-planet day-lengths at creation, alongside its other pinned universal
conditions (gravity, atmosphere, suns/moons).

**`time:now` — the current moment**, resolved on the governing calendar:
- `minutes` (absolute in-world minutes elapsed since the story's start — the
  precise accumulator; lets "20 minutes" accrue and "wait until sunset" be a jump),
- `day` (1-based, derived: `minutes // (hours_per_day*60) + 1`),
- `phase` (derived from the within-day minutes against the calendar's `phases` — so
  a 72h-day world's "noon" lands at hour 36, not 12).

This is STORY time, a separate axis from the engine's bookkeeping/validity time
(turns still stamp at `TURN_EPOCH`; as-of queries are unchanged), and it is
**tied to the world** (each fork carries its own `time:now` + inherits the
scenario's `time:calendar`). The clock is a stored, superseding canon fact the
host updates each turn — **no new engine primitive needed** (confer below
double-checks). Phase derivation always goes through the world's calendar, never a
hardcoded 24h.

## How it advances — an LLM estimate, each turn
After the turn's action is classified and narrated (so we know what actually
happened), a **cheap-tier `estimate_elapsed` cohort** reads (current clock + the
player's action + a short summary of what occurred) and returns how in-world time
moved:
- `advance_minutes` for the ordinary case (examine the desk → a few minutes; ride
  to the castle → hours), OR
- `jump_to` for an explicit directive ("wait until sunset" → set phase=dusk;
  "three days later" → +3 days), OR
- a small/zero advance for pure dialogue/observation.
The host commits the result and recomputes `phase`/`day` from the new total via
the calendar. LLM judgment for the AMOUNT (founder: "intuitively try to track…
relative to what's happening"); the trigger is crisp (every turn). Cheap tier — a
small bounded estimate, exactly the "minor things" the mini model handles.

**Commit seam — `accrue`, not superseded-absolute (Kernos steer, letter 074; HOLD
pending PB 071).** Rather than superseding an absolute minutes value each turn,
store **`time:elapsed · minutes` as `value_type=delta` / `fold_policy=accrue`**
(the engine's shipped numeric-quantities primitive): each turn APPENDS `+N
minutes` and the engine folds the running total; a jump is a larger forward
`+delta` (or a `set`). Append-only (dissolves "is frequent supersession sound?"),
monotonic (time only moves forward), arithmetic on the engine ("math off the
model"). The `Clock` math (phase/day from the folded total) is unchanged — this is
the ONE seam held for PB's ruling; the cohort, `Clock`, and briefing wiring are
identical either way.

## What it feeds
- **Narration (v1):** the current `phase`/`day` go into the narrator briefing, so
  prose reflects the hour (failing light, a shuttered market, the night watch) —
  the GM-style grounding ([[narrator-gm-style]]) gains a temporal anchor.
- **Player-directed jumps (v1):** "wait until sunset / rest until morning / three
  days later" resolve through `estimate_elapsed` as a `jump_to`.
- **Availability & schedules (FOLLOW-ON):** "the bar opens at night," "the contact
  arrives at dusk." This is a richer layer — authored or improvised appointments
  keyed to `phase`. v1 lets the player wait-to-sunset and go; whether the contact
  is THERE is good-DM improv ([[improv-and-authority-model]]) or an authored beat.
  A natural future tie-in: **arc pressure clocks firing on diegetic time** (a
  deadline at dawn), not just turn/beat counts — flagged, not built.

## The engine-boundary question (PB confer — [[collaboration-model]])
Diegetic story-time is HOST meaning (what o'clock it is, how an event spends time)
over the engine's invariant temporal retrieval (validity/as-of). The plan stores
the clock as an ordinary canon fact and advances it host-side — **zero new engine
primitive**. Before building, a short letter to PB (via Kernos CC) to confirm:
(a) nothing in the engine already models diegetic time we should adopt instead of
inventing; (b) storing a frequently-superseded `time:now` fact is sound (vs. a
dedicated surface); (c) no interaction hazard with as-of/valid-interval semantics.
Likely GREEN (host orchestration over shipped surface, like the living-world
generator was), but it touches the temporal model, so we confer first.

## Forks for founder
1. **Storage:** canon fact (`time:now`, the world remembers + re-enters coherent)
   vs. host session meta. *Lean: canon.*
2. **v1 scope:** clock + time-aware narration + player-directed jumps NOW;
   NPC-availability/appointments + arc-clocks-on-diegetic-time as a follow-on. vs.
   build scheduling now. *Lean: clock + narration + jumps first; scheduling next.*
3. **Confer PB first, or build host-side in parallel?** *Lean: send the confer and
   start the host-side clock + estimate cohort in parallel (it's host-only); fold
   in PB's reply.*

## Build order — SHIPPED (2026-06-19)
1. **DONE.** `construct/clock.py` — `Calendar` (world/location-scalable phases +
   `offset_minutes` desync) + `Clock` (advance/jump/phase-from-total) + the canon
   seam helpers (`read_clock`/`commit_elapsed`/`delta_from_estimate`/
   `governing_calendar`). `cohorts.estimate_elapsed` (cheap, tag `elp`). 11 clock
   tests (incl. 72h day + two-planet desync). Accrue declared in `semantics.py`
   (`elapsed_minutes` → `fold_policy=accrue`); **round-trip verified live**
   (0→+30→120).
2. **DONE.** Turn loop (`run_turn`): reads the governing clock by location into the
   briefing as a felt "THE TIME" line; after the render, `estimate_elapsed` →
   `delta_from_estimate` → `commit_elapsed` (accrue append). `TurnTrace.time_now`/
   `time_advanced`. Best-effort (never sinks a turn). No explicit seeding needed —
   `read_clock` defaults (Earth-like 24h, 0 min) for worlds with no calendar; a
   world author may set `time:calendar.config` / per-place `calendar` later.
3. **IN PROGRESS.** Live-verify a normal advance + a "wait until sunset" jump on
   anchor (`scripts/verify_time.py`); then bot restart.
4. Follow-on: per-world/planet calendar AUTHORING at build; NPC
   availability/appointments; arc pressure-clocks on diegetic time. Codex review
   of the Atrium/Foyer/time wiring still owed.

## Commit-seam status
Built against `accrue` (Kernos 074); the primitive is verified present + working
in the engine build (`indexes._fold_accrue`; live 0→30→120). PB's confer reply
(my 075 / Kernos 071) still outstanding but NOT blocking — if PB flags a nuance
the swap is localized to `clock.commit_elapsed`/`read_clock`.
