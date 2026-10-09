# R20 acceptance: the displaced-Ironhold probe (2026-10-08)

The WORLD-GROWTH acceptance pass the roadmap left open (`NEXT-UP.md`, "WORLD-GROWTH acceptance + latency"). Script: `scripts/displaced_ch2_probe.py`, on the subscription wire (CodexProvider). No metered calls. The build is fresh, so the probe exercises today's main (bce91b2). Logs are on `/media/k/Blank/construct-scratch/`.

## Pass mark, set before the run

The probe passes only if every one of these holds:

1. **Chapter 1 lands a conclusion** within its 11-turn schedule (`concluded=True`).
2. **The world grew where the player walked.** Chapter 1 ends in a place that did not exist in the pristine Ironhold world, a place minted in play, not one of the prison's built places.
3. **Chapter 2 opens where chapter 1 ended.** `CH2 OPEN STATE` equals `CH1 END STATE`, with no snap-back to Ironhold.
4. **No broken turns.** No chapter-2 `ENGINE ERROR`, and no turn returns empty prose.
5. **No critic breaker on the WHERE bar.** No filed note reports a teleport or snap-back. Notes on the goal-pivot and style bars are recorded as fiction-quality findings, not failures.

It fails if any of 1–4 fails, or if 5 does. If it fails, the fix goes on a branch and merges when green, and the probe re-runs.

Latency is recorded, not judged: the per-turn wall time and the `cp_*` checkpoints from `CONSTRUCT_MECHANICS_LOG` feed the R23 breakdown below.

## Run 1 — FAIL (criterion 1), causes found and fixed

Build: viable after one config change. This account refuses the default Codex cheap model `gpt-5.4-mini`, so the cheap tier ran on `gpt-5.5` (`HOLODECK_CODEX_CHEAP_MODEL`). The first attempt skipped all 12 chunks one by one, then failed later as a misleading 'bare world' arc error.

Chapter 1 played 11 turns and **did not conclude**. The protagonist ended at `obj:laundry_barge` (canon), still inside Ironhold. Chapter 2 never ran. July's run failed the same way (`place:ironhold`, not concluded), so this is not a regression.

What happened, and what was done:

1. **The escape turn lost its move to one passing server error.** On the turn where the player hails a skiff to Dyers' quay, classify hit one OpenAI `server_error` ("You can retry your request"). It was not retried, because today's stream-error fix had made every error event final. So the turn fell back to a plain action with no move, the narration improvised a chain-boom, and the critic-player retreated. **Fixed** (merged as `e5dec13`): server, overload, rate-limit and timeout stream errors are now transient and retried. Request errors and refusals still fail fast.
2. **A build whose every chunk fails now stops at once with the cause** (merged as `a34ae81`).
3. **Foreshadow pins were never indexed.** A second timeless `pin_index` row conflicted with the arc's own, and the fold served `[]`. **Fixed** (merged as `3eaf0bb`).
4. **Continuity breaks the critic filed** (a hymn slip changing hands, `held_by` cycles). These trace to pattern-buffer's `holds`/`wearing` inversion at its gate, whose fix (GATE-INVERSE-ALIAS-V1) is with pbr. That is engine-side by our law; nothing is changed in construct.
5. ~~**Canon/prose location divergence.**~~ **Withdrawn after run 2: a probe error, not a world error.** The probe read the player's place without the play horizon, so it printed the source book's later canon (`obj:laundry_barge`). Read at the horizon, as the session reads it, run 1 ended at `place:chapel_threshold`, which matches the prose. The probe is fixed.
6. **Live bots.** The Codex opt-in's default cheap model is refused by this account. The live Telegram bots aren't running (last active in July), so no player has been hit. The fix at the next start is one line, sent to the monitor for Kabe.

## Run 2 — FAIL (criterion 1), causes found and fixed

Fresh build with all of run 1's fixes. Chapter 1 played 11 turns. The player worked the dead man and the red-thread chit, broke out onto the river road when a warrant seal cracked, reached the chain-piers, took a false name, and stepped into a downstream hauler. The arc reached its won state on turn 9, at the piers (`beat:river_window_won`, lifecycle `won`, the narrator told the decisive moment is within reach). **The chapter did not conclude**, so chapter 2 never ran.

1. **The conclusory move was read as plain action.** On turn 11 the player made the escape's decisive act ("knot it around my wrist like a vow before stepping down into the hauler … I'm done earning the old"). The classifier only had accusation-shaped examples and nothing about the story's readiness, so `commits` stayed false. **Fixed:** while a commitment-owned win_loss arc is ready, classify is told the decisive moment is within reach and what this shape's conclusory act is (`commitment_kind`). The earned gate, stage gate and pillar bounce still stand behind it.
2. **A turn was lost to an HTTP 503** ("no healthy upstream") on narration. The stream-error fix covered errors inside a stream, not a failed status before it. **Fixed:** 429 and 5xx statuses are transient and retried; other 4xx errors still fail fast.
3. **The probe printed the wrong end place.** See run 1's item 5. Played to the horizon, run 2 ended at `place:river_road`, which **was minted in play** (absent from the pristine world). So criterion 2 holds for where canon has the player.
4. **Finding, for Kabe: the player cannot board a vessel.** "Step down into the hauler" resolved to `obj:hauler`, and the movement rule (Cx 327) never puts a person *in* an object, so the move was dropped. The prose ends with the player aboard and drifting downstream while canon keeps him on the river road (`obj:chain_piers` and `place:low_quay` sit inside it). The source book itself puts people in boats (`person:ewan in obj:mercy_finch`). Conveyances (enter a vessel, the vessel travels, the next chapter opens aboard) are a design question. Not changed tonight.
5. **Critic notes:** one, on Pike's role (staff in the opening, the condemned man's paperwork later). Not a WHERE note.

### R23 timings, run 2 (10 instrumented turns)

| | Run 2 |
|---|---|
| Player-felt (cp_generator + narrate) | 41–209 s; typically 70–110 s |
| Salience window | 8–69 s; typically 30–57 s |
| Narrate | 19–51 s; 124 s on a turn with a transport retry |
| Player-input ingest | 5–29 s |
| Settle tail (post_extract + promote) | 27–55 s; it did not grow steadily this run |
| Classify | 5–8 s |

The ranking holds: the serial salience window is the largest block before the reply, then narration, then the settle tail after it.

Run 3 (these fixes, a fresh build) follows.

## R23 findings: where a turn's time goes now (run 1, 9 instrumented turns; no build yet)

| | July (eval/11) | Tonight |
|---|---|---|
| Whole turn | 400–615 s | 24–252 s; mostly 130–200 s |
| Player-felt (pre-send = cp_generator + narrate) | ≈ 260 s | 48–158 s; typically 85–120 s |
| Snapshot → salience window (serial cheap cohorts) | 128–138 s | 14–65 s |
| Drift and lifecycle | 46–56 s | 0.1–0.4 s |
| Narrate (main tier) | 13–80 s | 15–42 s |
| Player-input ingest, when it runs | ~6 s | 13–30 s |
| Settle tail (post_extract + promote, after send) | ~19–95 s | 25–65 s |
| Classify | 6–9 s | 4.6–7.6 s; 60.8 s on the server-error turn |

Where the remaining time is, largest first:

1. **The salience window.** 30–65 s on most turns. npc_turn, weave_pick and detect_events run as serial cheap calls. eval/11's recommendation stands: run the independent cheap cohorts concurrently. Note that the cheap tier is now `gpt-5.5` on this account; it is slower than a mini model, and that falls exactly on this serial chain.
2. **The settle tail.** 25–65 s, and it grows across turns (post_extract 20→40 s, promote 5→33 s). It runs after the reply is sent, but a fast next message joins on it. Promote's growth over the session is worth a look.
3. **Narration.** 15–42 s on the main tier. Not compressible without the render+capture collapse (TURN-LATENCY "Kernos reframe").
4. **Player-input ingest.** 13–30 s on turns that assert something. The A-lite skip already avoids it on pure questions.

R23 is not built tonight. These are its starting numbers.
