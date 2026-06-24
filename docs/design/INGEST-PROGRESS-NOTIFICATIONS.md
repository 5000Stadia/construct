# Ingest progress notifications over chat (SHIPPED)

**Status:** SHIPPED 2026-06-19 as part of the Construct dialogue
(CONSTRUCT-DIALOGUE.md). The trigger now exists — `begin_build` in the Atrium —
and the pings stream during the build. Implementation: `TransportCore(notify=…)`
(an interim-send channel injected by the adapter, outside the exactly-once
outbox), `_humanize_stage` (raw `on_stage` lines → warm player-facing pings;
per-chunk collapsed to one rolling counter; internal stages silent), bookended by
`BUILD_HEADS_UP` and a "doors open" line. The design below is retained for
rationale + the post-demo background-worker note.

## The requirement (founder, verbatim intent)
When a player initiates **live creative fiction**, the agent must *author then
ingest* the world into the pattern-buffer — and we have measured that this takes
a long time (a full generate+ingest is **~16 min**, and can run longer). "What I
don't want is an empty chat window doing nothing for 20 minutes. I want informed
clarity on each step." So: while a world is being built for a player, stream a
**per-phase progress notification** over the chat, each naming the step and
setting expectation ("this can take a few minutes").

## Why nothing fires today
Telegram/loopback players open **pre-built** worlds (the invite is scoped to an
authored scenario, e.g. `anchor`). `Session.open` *loads* — it does not build —
so there is no minutes-long wait on the play path and nothing to notify about.
Notifications matter **only** once a chat command can trigger
`create_scenario_from_generated` / `_ingest` / `_interview` for a player.

## The upstream hook is ready
`construct/game.py` already drives the whole build through an `on_stage(msg)`
callback (`_emit`), emitting human-readable phase lines today consumed by the
CLI:

- Stage 0 · Authoring the hidden source story
- Stage 1 · Ingesting prose → pattern-buffer (per-chunk: "…chunk i/N extracted")
- Stage 2 · Reconciling identity (cross-chunk coreference)
- Stage 3 · Declaring passability
- Stage 5 · Seeding character knowledge · Stage 5.5 · Distilling flavor
- Stage 6 · Sealing · 6.1 intro · 6.2 durability classify (batched)
- Stage 7 · Viability gate

Measured phase costs (dragon profile, `logs/timed-generate-dragon-…md`): Stage 1
extraction ~387s (7 chunks, the biggest), durability classify ~196s (now **19
batched** grouped calls, down from ~400 inline), viability ~199s, authoring
~187s — total ~948s. The slow parts are inherent LLM authoring/extraction, so
the wait is real: the notifications are the right answer, not more optimization.

## The work to build (when the trigger exists)
1. **A chat entry that builds a world** — e.g. a "create your own fiction" flow
   where the player's premise drives `create_scenario_from_generated(seed=…,
   on_stage=…)`. (This is the missing piece; the rest hangs off it.)
2. **An interim-send channel in the transport.** The transport is currently
   synchronous *one inbound → one Outbound*, with an exactly-once outbox. To push
   progress mid-build, the adapter needs an injected `notify(chat_id, text)` that
   sends an *additional* `sendMessage` immediately (outside the single reply).
   Keep it best-effort and OUTSIDE the exactly-once turn bookkeeping — a dropped
   progress ping must never affect turn correctness or be retried.
3. **Bridge `on_stage` → `notify`.** Wrap each `_emit` so the build streams
   player-friendly lines ("Building your world — Stage 3 of 7: reconciling who's
   who… (a few minutes)"). Throttle/curate: collapse the per-chunk spam into a
   single rolling "extracting the world (chunk i/N)…", lead with one upfront
   "this can take ~15–20 minutes" heads-up, and end with "your world is ready."
4. **Map raw stage names → warm phrasing** (host-side; never leak engine ids),
   the same discipline the cold open uses.

## Decision (founder)
Wire **per-phase pings** (not just a single heads-up) once player-initiated live
creation is on the chat path. Until then this is banked, ready, and blocked only
on its trigger.

Connects to: STARTUP-ENTRY (generate-then-ingest), SESSION-ZERO, the transport
core, and the model-tier/build-profile work (where the ~16 min comes from).
