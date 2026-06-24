# Turn Latency — fold, parallelize, and defer the per-turn cohort layers

**Status:** SPEC for Cx review. Founder-directed 2026-06-23 ("a lot of layers per turn — fold
them, improve parallel, or shift ingest until after sendback"). Grounded in a measured turn
(`logs/harness-1782277324.md` instrumentation): **133s wall**, broken down below. Goal: cut the
USER-PERCEIVED latency (the path up to the prose they read) without changing what's built or
risking the gated-ingest correctness invariants.

## The measured turn (4 suspects present, a questioning turn)
| Step | Tier | Dur | Before user sees prose? |
|---|---|---:|---|
| classify | cheap | 3.2s | yes |
| player_ingest | — | 5.9s | yes |
| furnish (scene resolve) | main | 24.7s | yes |
| npc_action ×N (parallel) | main | 6.7s | yes |
| weave_pick | cheap | ~2s | yes |
| npc_intent ×N (parallel) | cheap | 8.9s | yes |
| **narrate** | main | 33.9s | **← user sees prose HERE** |
| post_extract | — | 18.0s | NO (bookkeeping) |
| promote | — | ~0 | NO |
| time_estimate | cheap | 6.3s | NO |
| compact_memory | cheap | (only on overflow) | NO |

**Critical reframe:** the user feels latency only THROUGH `narrate`. Everything after it
(post_extract, promote, time_estimate, compact) is world-bookkeeping that does not change the
prose already sent. ~24s of the 133s is post-`narrate`.

**CORRECTION (verified 2026-06-23, Cx 067):** the 24.7s `furnish` above was a FIRST-turn-in-
scene cost. `furnish_scene` is ALREADY memoized (turnloop:507/511) — a 2-turn static-scene
probe measured turn-1 furnish=10.2s, turn-2 (same scene) furnish=**0.0s**. So furnish is NOT a
per-turn cost; it fires once on scene-ENTRY then is free (regression test
`furnish_is_memoized`). The earlier "25s every turn" framing was wrong. Steady-state turn (memoized
furnish) ≈ narrate(34) + post_extract(18) + npc_intent(9) + npc_action(7) + player_ingest(6) +
time_estimate(6) + classify(3) + weave(2) ≈ **~85s**. So the dominant EVERY-TURN perceived win
is Lever 1 (defer ingest, ~24s), then narrate (inherent), then the npc/ingest model calls.

## The six functional groups (the organizing frame — founder, 2026-06-23)
Every per-turn step belongs to one of six functional GROUPS, and the parallel/serial/deferrable
boundaries fall straight out of them:

| # | Group | Steps | Nature |
|---|-------|-------|--------|
| 1 | **Identification** | `classify` | Serial GATE — decides kind/move/target; all else branches on it |
| 2 | **Settlement** | `player_ingest`, movement, possession, entitlement-gate | Serial — commits the player's action; DEFINES the world the rest reads |
| 3 | **Generation** | `furnish`, `npc_turn`, `weave_pick` | PARALLEL — pure model calls over the frozen settled world; commits serialize after |
| 4 | **Resolution** | interview delivery/discovery, `clock_pass`, `beat_pass` | Deterministic — host computation, no model call |
| 5 | **Assembly** | briefing build + `narrate` | Serial, LAST — composes the response; the user sees output HERE |
| 6 | **Finalization** | `post_extract`, promote/mirror, receipt, archive, compact, `time_estimate`, conclusion-effect | DEFERRABLE — does not change the prose already sent |

Turn shape: **`[1] → [2] → [3 parallel] → [4] → [5 Assembly = user sees it] ‖ [6 Finalization deferred]`**

The levers map ONTO the groups: Group 3 is the only internally-parallel group (Lever 4 = fold,
done; Lever 3 = overlap, marginal post-memoization); Group 6 is the only deferrable group
(Lever 1 = the ~24s/turn win); Groups 1-2 are the irreducible serial prefix (can't parallelize —
they define the world); Group 5 is the serial endpoint (only STREAMING helps, out of scope).

## Deliberation synthesis (Cx 077) — the refined, safer build order
A creative-latency deliberation with Cx (letters 076/077) reshaped the plan. Dispositions:
- **C — deterministic `time_estimate`: GREEN.** Replace the per-turn `estimate_elapsed` model call
  with deterministic defaults by `kind` + classifier fields (look/ask 0-2m; examine/search 5-20m;
  movement→travel table; take 1-3m); model fallback ONLY for explicit temporal language
  ("wait until sunset"), long travel/rest, or montage. Preserve `delta_from_estimate`/
  `commit_elapsed` — change only how the estimate is produced. ~6s, low-risk (already best-effort).
- **A-lite — conditional `player_ingest` skip: GREEN.** NOT a full classify+extract merge (that
  bloats the cheap classifier + risks the verdict, and protected-key licensing needs the real
  extraction's `pre_keys`). Instead add `needs_player_ingest`/`asserts_or_reveals` to
  `CLASSIFY_SCHEMA` (default conservatively TRUE); SKIP `p.ingest(player_input)` only on turns that
  can't add/license facts (pure look, pure talk w/ no claim, simple move/take already on
  `moves_to`/`takes`, questions routing to `ask()`); KEEP extraction for discoveries/claims/
  declarations. ~6s on many turns. (The `EXTRACTION-AND-DISCOVERY.md` option-B bridge.)
- **B-hybrid — delta hints SHRINK post_extract, not replace it: YELLOW.** Narrator self-report
  CANNOT replace extraction (the gate is built on "narrator prose is untrusted"; self-report can
  under/over-report and miss the safety catches — contradiction/protected-same-value/phantom).
  Safe: `narrate` returns `{prose, touched_entities/delta_hints}`; feed the hints to SHRINK the
  extraction scope/prompt; keep extraction over the ACTUAL prose + the deterministic gate
  unchanged; trust a "no deltas" claim only for tightly-defined renders (adjudication-denial/OOC/
  pure-status). Cuts much of the 18s without crossing the trust boundary.
- **D — batch all NPCs into one prompt: BLOCKED (naive).** One prompt with all private `knows:<npc>`
  sheets violates frame isolation (structural windows, not prompt instructions). Lever 4 already
  landed the real win (one cheap per-NPC call, parallel). Only provider-level batching (separate
  prompts) / public-scene-only / a 4+ cast threshold w/ per-NPC fail-open fallback are testable.
- **E — stream `narrate`: GREEN perceived, YELLOW impl.** The biggest founder-visible win (narrator
  is the floor; perceived ≈ time-to-first-token) but a PROVIDER + TRANSPORT contract change
  (`complete()` collects SSE → one JSON today; Telegram only `sendMessage`). Separate transport
  slice; loopback first; composes with B + Lever 1.
- **Cx-added levers:** (i) **prompt-cache locality** — keep stable narrator instructions
  BYTE-IDENTICAL + put dynamic briefing LATE so the provider's `prompt_cache_key` prefix stays
  warm (semantics-free main-call speedup); (ii) **idle-window caching** of deterministic read-only
  assembly artifacts (NPC sheets, scene materialization, status, scope, stable briefing fragments)
  keyed by world revision — NO speculative model calls; (iii) furnish = invalidation-correctness
  only, not latency.

**Refined build order (safest/highest-value first):** C (deterministic time) → A-lite (conditional
ingest) → prompt-cache locality → B-hybrid (hint-shrunk extraction) → **Lever 1 (defer G6, the
~24s, careful)** → E (streaming, transport slice). Lever 3 + D deprioritized. Each: instrument
`trace.timings`, suite green, re-time live.

## Target shape + ensemble ruling (Cx 079 — confirms the sequence, corrects a premise)
**Target turn shape:** `entry-barrier (drain pending finalizer) → G1 Identify (classify +
needs_player_ingest) → G2 Settle (deterministic adjudication/move/take + CONDITIONAL
player_ingest) → freeze immutable inputs → G3 model generation in PARALLEL (furnish on cache-miss,
npc_turn, weave, commitment-judge) → G4 deterministic resolution (serialize commits, delivery,
clocks/beats/coverage, briefing) → G5 Assemble/narrate (stable prefix + dynamic late; STREAM when
built) → SEND → G6 Finalize + populate read-only caches in the idle window`.
**Build sequence (Cx 079):** 1) C + A-lite + prompt-cache (now). 2) B-hybrid (no gate change).
3) Lever 1 G6 deferral (the real steady-state win, behind the durable record + barrier). 4)
streaming (transport slice, loopback first). 5) provider-level batching / public-room ensemble
(prototype only, after a structural `shareable` field).
**Ensemble batching — CORRECTION (Cx 079):** my "protected keys are never in any NPC call" was
WRONG — `npc_turn` is handed each NPC's `knows:<npc>` character-sheet, which is frame-respecting
but does NOT filter Construct's protected keys, and cast clues seed as ORDINARY facts in holder
frames. So a present NPC's sheet can carry game-bearing private rows; naive PROMPT-level all-NPC
batching can leak them. Rulings: provider-level batch (N separate prompts) = clean/GREEN-if-
supported; public-room ensemble (one prompt, PUBLIC/shareable rows only) = YELLOW, needs a
structural `shareable` Clue field + tests proving no protected/clue/private row crosses the shared
prompt; private/secret + schema-failure fallback to per-NPC = required. So prompt-level ensemble
is a QUALITY prototype with a safety contract, NOT on the latency critical path.

## Kernos reframe (077-from-kernos) — collapse render+capture; the turn shrinks to ~2 calls
Kernos (the more mature reference host, a tool-calling turn system) replied to the deliberation
with a stronger version of candidate B + a cast-flat NPC model. Routed to Cx for convergence
(080-from-c); pending Cx + a provider-capability check before sequencing.
- **B as KILL, not shrink — delta-as-TOOL-CALLS:** `narrate` emits prose as free-form CONTENT
  AND the world-delta as structured TOOL CALLS in ONE completion (two channels, NOT prose-as-a-
  JSON-field — that degrades prose). Kills `post_extract` (~30s). The gate is UNCHANGED: it sits
  between proposal and effect and validates the narrator's tool-call delta exactly as any
  proposal ("narrator proposes, gate disposes") — so it doesn't cross the trust boundary.
  Same-call is MORE coherent than a cold post-hoc extractor; belt-and-suspenders = the gate flags
  a delta row referencing an entity absent from the prose (no model call). DEPENDS ON: the
  provider supporting prose+tool-calls in one completion (a contract question, like streaming).
- **Don't classify bookkeeping durability:** receipts/events/transcript are operational artifacts,
  not durable user-facts — skip durability classification entirely; batch-classify genuine
  world-facts at a BOUNDARY (compaction), never per-turn. (Matches our 074 §2.)
- **NPC cost = O(focus), not O(cast):** fold AMBIENT present NPCs into the render (narrator voices
  the room); a focused NPC call only for an NPC in active dialogue / a drive-fired consequential
  action. Most turns: zero dedicated NPC calls.
- **Target ~2 calls/turn:** classify folds into the render's structured channel too → render(+
  classify + delta) + time(cheap) + focused-NPC-only-when-in-dialogue. Kernos's est: ~65s→~35s.
If Cx converges + the provider supports tool-calls, B-via-tool-calls SUPERSEDES the B-hybrid and
becomes the single biggest steady-state cut (~30s), reordering ahead of Lever 1's deferral.

**CONVERGED RULING (Cx 081 + Kernos 077):** B-via-tool-calls is GREEN as a DESIGN DIRECTION
(same completion = free-form prose + structured delta proposals; the existing promotion/
quarantine gate stays the only canon doorway), YELLOW-to-build behind a spec/flag, BLOCKED as a
cut-now schema swap. Two gates Cx added: (1) **no native dual channel** — `CodexProvider.complete`
returns one JSON dict; this needs a new `complete_with_tools(...) -> {content, calls}` provider
method (a provider slice, like streaming), NOT just adding JSON to `NARRATE_SCHEMA` (which would
make prose a JSON string — Kernos's exact warning). (2) **the gate licenses "could have been
allowed to say," not "was shown in prose"** — a same-call proposal isn't evidence the player SAW
it, so add a NON-MODEL ALIGNMENT GUARD before promotion (proposed entities visible by name/alias
or a checked evidence span; stronger evidence for protected/momentous/new rows; Kernos's
"absent-from-prose" flag is necessary but not sufficient). Approved build shape: `narrate_with_
delta` cohort behind a flag → delta through the existing gate → alignment guard → fail-open
(bad delta ships prose, skips commit) → regression tests (unrendered row quarantined, protected
same-value quarantined, earned protected promotes, contradiction quarantined, phantom blocked,
proposal-failure doesn't sink the turn). Until built, the B-hybrid (hints SHRINK extraction)
stands. Bookkeeping-durability-skip = a separate focused pass (endorsed). NPC-by-focus needs the
frame-secrecy discipline (ambient→render, private-consequential→focused/protected call).
**Sequencing: B stays the biggest candidate cut but is a provider+gate slice; C/A-lite/prompt-
cache/Lever-1 (G6 deferral) remain the safer immediate path.**

## The four levers

### Lever 1 — DEFER post-render work behind a SESSION-LEVEL FINALIZATION BARRIER (#1 win, ~24s/turn)
After `narrate`, send the prose to the user IMMEDIATELY, then run the FINALIZER asynchronously
(post_extract → gate → promote → mirror → `event:turn_N` receipt → transcript/archive → compact →
time advance) while the user reads and types.

**Execution model (Cx 069 blocker 2 — NOT a background thread):** PB opens SQLite without
`check_same_thread`, so a background thread writing through the same `World` is unsafe. The
finalizer runs on the **SAME OWNER THREAD**, AFTER the prose is durably recorded + sent to the
user, BEFORE the next inbound update is processed. That still cuts PERCEIVED latency (the user
sees the prose before the finalizer runs, and it overlaps their read/type time) with zero
threading hazard — but it requires TRANSPORT PARTICIPATION (the transport sends, then triggers
finalize), not a blind in-session thread.

**Crash safety (Cx 069 blocker 2):** "close() awaits" covers normal close, NOT a crash after the
prose is sent but before finalize completes — that would leave the player having seen a turn the
append-only world can never recover (Telegram/loopback have exactly-once outbox semantics; Lever
1 must not violate that). So: write a **durable pending-finalization record** (the prose + turn
context) BEFORE sendback; the finalizer clears it on success; a later owner thread/process
DRAINS any pending record before ANY subsequent world/session read.

**The barrier surface (Cx 069 blocker 1 — named gate, not Session.turn()-only):** add a public
`Session.finalize_pending()` (idempotent; runs/awaits the pending finalizer, clears the durable
record). It must be called before EVERY path that reads/writes/replaces/drops/reports a live
session — not just `Session.turn()`. Concretely:
- `Session.turn()` calls it at the very start (before terminal check, `next_turn_number()`,
  player_ingest, retrieval — the turn-numbering race Cx 067 named).
- `Session.close()` calls it.
- `TransportCore` calls it before each bypassing command path (`transport_core.py:176-243`):
  `/status`, `/ooc`, `/note`/`/notes` context reads, `/restart` + its confirmation,
  `/wipe`, `/disconnect`, `/exit`, and any pending restart/exit answer that mutates the slot —
  AND before it pops/replaces/drops a cached session/slot.
The gated-ingest guards run UNCHANGED on the SAME prose at `turn_time(turn)` — only their timing
moves (Cx confirmed no PB append-only/as-of problem once the barrier is strict).

### Lever 2 — `furnish` is already memoized; the work is correct DIRTY-INVALIDATION (small)
DOWNGRADED (Cx 067 + verified): `furnish_scene` already memoizes (skips when the scene has a
description; turn-2 same-scene furnish = 0.0s). It is NOT a per-turn cost — only a scene-ENTRY
cost. So there is no "skip static scenes from scratch" to build. The only useful work is ensuring
the dirty-invalidation is CORRECT: re-furnish when the scene's facts MATERIALLY change (a new
object, a state change), not just on location change. Low priority; verify the memoization +
invalidation are right, add a test if a gap exists, otherwise leave it.

### Lever 3 — PARALLELIZE only FROZEN-INPUT model calls (narrowed; Cx 067 blocker 2)
NOT a naive `furnish ‖ npc_action ‖ npc_intent ‖ weave` fan-out — those are WRITERS with
dependent reads (furnish writes furnished facts to the player frame; npc_action commits serially +
refreshes canon; weave writes card:*/weave:pacing; npc_intent reads the player_snap/scene lines
built downstream). The SAFE shape: (1) freeze inputs SERIALLY (snapshot NPC sheets + scene JSON
into immutable prompt blobs after player_ingest settles movement/possession); (2) run the PURE
MODEL CALLS concurrently over those frozen blobs (e.g. furnish's resolve + npc_action decisions),
touching NO PB; (3) JOIN before any `player_snap`/`beat_pass`/`weave`/`npc_intent`/briefing
assembly; (4) commit ALL PB writes back on the MAIN thread in deterministic order. Modest
steady-state win (overlap furnish-on-entry with npc model latency; npc_action-model ‖
npc_intent-model). Only worth it after Lever 1.

### Lever 4 — FOLD the per-NPC pair into one call (fewer calls, simpler)
`npc_world_action` (does the NPC act) + `npc_intent` (what they want / how they speak) are two
calls per present NPC at different phases. Fold into ONE `npc_turn` call per NPC returning both
{acts, action, intent, line_hint}. Halves per-NPC calls; the combined call can stay cheap-tier
(the action decision is light). Re-time to confirm the merged call isn't slower than the
parallel pair.

## Projected perceived latency (corrected)
Steady-state turn (memoized furnish) is ~85s today. With Lever 1 (defer the ~24s finalizer
behind the barrier): perceived ≈ classify(3) + player_ingest(6) + npc_action(7) + npc_intent(9) +
weave(2) + narrate(34) ≈ **~61s**. With Lever 3 (overlap npc_action-model ‖ npc_intent-model and
furnish-on-entry): a few more seconds. A scene-ENTRY turn adds furnish (~10s) on top. `narrate`
(34s) is the irreducible floor until STREAMING (perceived ≈ time-to-first-token; a transport
change, out of scope, noted as the real next lever after this).

## Risks / why this needs review (not an inline tweak)
- **Deferred ingest changes WHEN the gated-ingest guards run relative to the next retrieval**
  (Cx previously RED-then-guided this cohort). The await-before-retrieval guard must be proven
  to keep the next turn's reads current and the guards intact.
- **Parallel canon writes/reads** (Lever 3) introduce ordering hazards; player_ingest-first +
  no furnish→npc read dependency must be verified.
- **furnish cache invalidation** (Lever 2): the scene-dirty fingerprint must catch every change
  that should re-furnish (movement, new objects, state changes) or the prose goes stale.

## Build order + verification (re-sequenced by risk — Cx 069 surfaced Lever 1's depth)
Lever 1 is the biggest win (~24s) but the HARDEST (transport-bypass barrier + SQLite thread
ownership + crash-safety). The smaller levers are safe, in-`run_turn`, and land sooner — so:
1. **Lever 4 (fold npc pair)** — pure cohort merge (`npc_action`+`npc_intent` → one `npc_turn`
   call). No transport/concurrency/crash surface. Saves ~6s + a call. Re-time to confirm.
2. **Lever 3 (parallelize frozen-input model calls)** — shape GREEN'd by Cx (069 non-blocking):
   freeze inputs serially → pure model calls concurrent → join → commit deterministically on the
   main thread. Purely inside `run_turn`. Saves ~9s.
3. **Lever 1 (defer finalizer)** — the big win, built LAST behind the full barrier design above
   (named `Session.finalize_pending()` gate + transport call-sites + durable pending record +
   owner-thread execution). Needs Cx GREEN on this revised design first.
4. **Lever 2 (furnish dirty-invalidation)** — only if a memoization/invalidation gap is found.

**Acceptance tests (Cx 067):**
- Start a turn, defer finalization, immediately start the next turn → assert the prior finalizer
  completed BEFORE terminal check, turn numbering, retrieval, and player_ingest.
- One-shot `construct turn`: prove the finalizer is NOT lost on process close.
- Send an OOC/restart/new-story while a finalization is pending → assert it cannot discard/fork
  the unfinished turn.
- Parallelized phase with instrumented sleeps → assert NO PB write off the deterministic commit
  path, and the narrator briefing sees furnished + player-frame + NPC-action-commit facts.
- Keep the existing gated-ingest, protected-key, post-extract fail-open, `furnish_is_memoized`,
  and `_parallel` tests green.
Each lever: instrument with `trace.timings`, suite green, re-time a live turn. Turn latency is a
tracked metric (like the fiction-quality score). Debug-trace policy (Cx non-blocking): trace
fields not final at sendback when deferred — debug mode awaits finalization or prints a
provisional-then-final trace.

## Out of scope
Streaming narration (transport change); model-tier downgrades (quality risk); the build-time
durability-classification bottleneck (separate concern).
