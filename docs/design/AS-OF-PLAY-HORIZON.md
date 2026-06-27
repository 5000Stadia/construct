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

**S2 — Horizon metadata.** Durable `opening_as_of` (meta) + per-slot `play_as_of` (session
frame). Fresh ingested-fiction worlds default to `opening_as_of`, NOT `None`=head. A live
turn advances `play_as_of` into a reserved interval below the next authored future coordinate
(so future chapter rows can't re-enter by numeric accident).

**S3 — Thread as-of through the read boundary.** Add an as-of lane to `PorcelainWorldReads`
(`state`, `location_chain`, `events`, `assertion_in_frame`) so beat/clock conditions and
`InFrame`/`Located`/`Occurred` read the horizon, not head. Thread the horizon through
`Session.location`, `_present_people`, scene description + image selection, status, opening
anchors, and `run_turn`'s scene/presence/movement/adjudication reads.

**S4 — Regressions.** Keep Cx-127 (calendar-year rows never opening-current; a live turn
supersedes opening state) until replaced. Add the non-location-attribute regression: future
`bracelet`/`appearance`/`fire_under_skin` rows exist, the opening read omits them, a later
live acquisition includes them.

**S5 — Four-world A/B + live verify.** `anchor`/`latch`/`thedeep` open materially identical
(their fix is a no-op — single-timeframe / no aftermath). `emberroad` opens at Harth with
humble Mara, the relic just waking, Tovin/Lysa present per the opening dossier.

## PB

No new primitive (Cx). Narrow semantics confirm routed via K (letter 083): `valid_time` +
`as_of` as a play horizon, no unset sentinels, volatile carry via `valid_to` + audit. Not
blocked on it.
