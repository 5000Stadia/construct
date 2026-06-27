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

**S1 — Monotone source coordinate + `opening_as_of`.** The source axis is mixed/inverted
(emberroad: opening rows 606/612, end rows 7/8). The finalize pass must normalize ingested
rows to a monotone story coordinate (opening < aftermath) and record `opening_as_of` in meta.
Calendar years stay diegetic facts, not the timeline. *(Crux — get this right or as-of is
meaningless.)*

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
