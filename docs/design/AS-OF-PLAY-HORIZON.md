# AS-OF PLAY HORIZON — the root fix for staging-aftermath-scatter

Founder ruling (2026-06-27): fix from the principal issue. Cx 249: **Shape B'** — entry is
a real as-of *play horizon*, not "timeline head + patched staging."

## Principal cause

A bible narrates the whole arc incl. aftermath; ingestion folds it; "enter the story" reads
the timeline **head** = the **end** (emberroad opens with the protagonist in her post-quest
Keeper state — bracelet, banked fire, "aged"). Cx-127 fixed the *location* axis (cast `in`
staged to win); the *attribute* axis (arc-added attributes) was never covered, and most host
reads still read head.

## Model: the play horizon

- The whole-story source timeline stays in the log as **future/potential/literary** evidence.
- A playthrough reads through a **current play horizon** (an as-of coordinate):
  - at opening → `opening_as_of` (the story's beginning);
  - after each turn → a live coordinate that **includes** player/NPC/session writes and
    **excludes** unplayed future source rows.
- No unset/sentinel rows. An aftermath-added attribute (the bracelet) is simply *excluded*
  by reading as-of a coordinate before it. Genuine volatile carry uses `valid_to` + host audit.

## Stages (each behind the suite; the four-world A/B is the gate)

**S1 — Monotone source coordinate + `opening_as_of`.** SETTLED (mesh-aligned: Cx 251 + K
082 + PB 080). Root cause: the extraction model emits an explicit `valid_from` from diegetic
prose dates ("year 612"), which OVERRIDES the chunk cursor (`ingest.py:378-380`) → inverted
axis (emberroad opening at 612, end at 8). End-only attrs (bracelet/aged/fire @8) fold in
regardless.

Mechanism (#1, host policy — NO PB default change): **normalize source `valid_from` onto a
monotone narrative coordinate (chunk/scene/beat order + a deterministic intra-chunk offset
where local order matters) BEFORE PB append; demote diegetic dates to plain `year`/`date`
FACTS, never the timeline (lossless — K).** Implementation: either (a) PB exposes a
`valid_from_policy="cursor"` ingest knob (cleanest — pending PB's K-084 answer), or (b) host
wraps the extraction model output during `create_scenario_from_ingest` to strip/remap
extracted `valid_from` so the cursor governs. REJECTED as root: #2 `seq`/asserted-time (not
valid-time, no persisted chunk provenance), #3 range heuristics (miss small/NULL — keep only
as a post-ingest validation gate).

`valid_from=None`: do NOT blindly stamp — NULL is correct for truly timeless/structural rows
(`kind`, aliases, place graph, meta); only STATE/EVENT-like source facts that need horizon
slicing get a coordinate. Audit by attribute family.

emberroad is fixed by a REBUILD from `generated/emberroad.md` under the new policy — NOT an
in-place restamp (PB append-only triggers; old rows would still fold). `opening_as_of` =
an authored coordinate on the normalized axis. *(Crux — get this right or as-of is meaningless.)*

**S2 — Horizon metadata.** SHIPPED (`04e624c`, Cx 253 GREEN). The source axis is spaced at
ingest by `SOURCE_STEP = 1_000_000` (chunk i → `i*SOURCE_STEP`). `executor.horizon_metadata`
gives `opening_as_of = SOURCE_STEP + ENTRY_MARGIN` (strictly above chunk 1, so opening staging
supersedes it) and `next_source_as_of = 2*SOURCE_STEP` (the fail-closed ceiling). The unifying
move: the existing `entry_epoch` contextvar IS the play origin — for a horizon world it is set
to `opening_as_of` (low, just above chunk 1) instead of "above everything," so
`turn_time(n) = opening_as_of + n` and live writes supersede the opening within the reserved
band. `_finalize_scenario(source_step=…)` branches HORIZON vs LEGACY (the Cx-127 epoch-raise is
kept verbatim for interview/single-timeframe worlds, gated out for horizon worlds);
`continue_episode` likewise keeps `opening_as_of` as origin for horizon slots (Cx 253 §4).
meta carries `opening_as_of`/`next_source_as_of`/`source_step`.

**S3 — Thread as-of through the read boundary.** SHIPPED (`04e624c`). `PorcelainWorldReads`
carries a `horizon` (the foundation, `4f949a6`); `Session._horizon(turn) = opening_as_of + turns`
fail-closed strictly below `next_source_as_of`; `None` for legacy worlds (head — byte-for-byte
unchanged). `run_turn(horizon=…)` binds `live_reads` + every direct `p.locate`/`_snap_or_empty`/
`furnish_scene`/`adjudicate` read; `Session` binds `location`/`_present_people`/`_scene_contents`/
scene-imagery/`terminal_outcome`. `state_value`/`_snap_or_empty`/`furnish_scene`/`adjudicate`
gained an `as_of` lane (default `None` = head). `entry_as_of` defaults to `opening_as_of` so the
cold-open establishing/situation snapshots read at the opening. Diegetic CLOCK reads stay at head
(Cx 253 §2 — the clock is world content, not the visibility axis).

**S4 — Regressions.** SHIPPED (`04e624c`, 581 green). `test_porcelain_reads_honor_play_horizon`
(head sees aftermath; horizon excludes location + the bracelet/appearance ATTRIBUTE axis +
events + `assertion_in_frame`), `test_live_turn_supersedes_opening_at_the_horizon`,
`test_horizon_guard_caps_below_next_source`, `test_legacy_world_has_no_play_horizon`,
`test_horizon_metadata_coordinates`. The Cx-127 mechanism tests remain as legacy/no-horizon
compatibility guards.

**S5 — Four-world A/B + live verify.** IN PROGRESS. `anchor`/`latch`/`thedeep` open materially
identical (their fix is a no-op — single-timeframe / no aftermath; confirmed `opening_as_of:
None` on the live run). `emberroad` is REBUILT from `generated/emberroad.md` under the S1/S2
policy and must open at Harth with humble Mara (not the post-quest Keeper end-state), then
re-join the base-4 shelf.

## PB

No new primitive (Cx). Narrow semantics confirm routed via K (letter 083): `valid_time` +
`as_of` as a play horizon, no unset sentinels, volatile carry via `valid_to` + audit. Not
blocked on it.
