# Living-World Generator — P2: the opportunistic DM generator (spec)

**Status:** SPEC, for build. Depends on P1 (multi-arc portfolio + lifecycle +
fallout-as-canon-consequence — SHIPPED). Round-robin C-071 concluded GREEN (PB
072: zero new engine primitive); **P2 is gated on the six host-side receipts in
PB 072 §5 and Cx's leg.** This spec makes those six concrete. Everything is host
orchestration over the shipped arc grammar + existing reads; the generator writes
ONLY hidden `plot:`/`session:` frames (concealment = the membrane).

## 1. What P2 adds
A paced, fail-open **DM cohort** that, between turns, reads the world's standing
tensions and *mints a fresh side arc* through the EXISTING arc grammar (a beat or
two + a clock + a small ConclusionShape), authored into `plot:<id>` and registered
in the portfolio. The player meets it as any arc: the narrator surfaces the hook
diegetically (a runner bursts in; the clerk makes her move) via a briefing
directive — never as a visible system event. P1 already handles its life and death.

## 2. The three triggers (paced; a good DM waits for the moment)
- **Opportunistic** (the heart) — reads *what the player just changed this turn*
  and the standing tensions; asks "is there an opening for an engaging
  development?" and, if so, seeds a complication/hook/consequence grounded in the
  world's premises + an NPC's drive.
- **Regenerative** — an arc concluded/died (P1 emitted fallout) → spawn a new arc
  *from that fallout consequence*.
- **Ambient** — too many quiet turns → the world throws something up.

All three are subject to the budget/cadence in §4; at most ONE mint per turn.

## 3. The fuel (all shipped reads — §5 of the P1 spec, confirmed by PB 072 §1)
- **Committed delta** — `p.snapshot(scope, since=T)` / `events(since=T)` where `T`
  is the turn's opening `asserted_at`. Reads only what actually canonized this
  turn (post-gate). NEVER raw narrator prose (receipt #6 / K's grounding rule).
- **Fallout consequences** — the P1 `event:arc_terminal_*` rows + their
  `caused_by`-linked canon facts (read via the `situation` lens / `live_threads`).
- **NPC dispositional spines** — `drive`/`fear`/`breaks_if` via the
  `character_sheet` lens (already read in the turn loop for NPC cohorts).
- **Standing tensions / threads** — `snapshot(lens="situation")`.
- **Positioning / plausibility / reachability** — `who_knows`, `confidence`,
  `route`/`path`/`frame_diff` (for the coherence preflight, §5).

## 4. The six guards (PB 072 §5 / Cx's leg — the gate to building)
All six live in hidden `plot:`/`session:` frames as the generator's OWN bookkeeping
— membrane-clean (PB 072 §2: "is it a recomputable claim about the WORLD? → never
canon; is it the host's own plan/audit? → fine"). NONE is canon world-truth.

1. **Slack-pacing off lineage receipts (not thread count).** Each mint writes a
   `generation_attempt` receipt (session frame); each decline a `generation_declined`.
   The cadence reads these receipts — a budget of "≥ N quiet turns since the last
   *attempt*, and ≤ M active generated arcs" — NOT the live thread count (a
   legitimately fluctuating derived read — Cx #2). Hard cap on concurrent active
   generated arcs (`GEN_ACTIVE_CAP`) — avoids quest-soup.
2. **Fallout lineage.** Every generated arc carries `generated_from = <fallout
   term_id or "player_delta:<turn>" or "ambient:<turn>">` on its `arc:<id>` row —
   provenance for audit and for the depth cap.
3. **Fingerprint dedupe.** Before minting, compute a stable **fingerprint** of the
   proposed arc — the sorted tension triple + the gated beat entities,
   **deliberately EXCLUDING the trigger source** (Codex review: source-scoping
   let identical situations reappear from a different dead arc; the shipped
   `_fingerprint` is situation-scoped and a test pins cross-source dedupe).
   Store it in a `gen_fingerprint` index (session frame). A fingerprint already
   present → DECLINE (a `generation_declined` receipt). Stops the same situation
   regenerating (the "find the dockworker" five times problem).
4. **Depth cap.** A generated arc's depth = its parent's depth + 1 (a
   `gen_depth` row, root fallout = depth 1). At `GEN_DEPTH_CAP` the regenerative
   trigger STOPS spawning from that lineage and marks it `exhausted_for_generation`
   (session frame). Bounds death→fallout→death chains.
5. **Mint-time coherence preflight.** A proposed arc is checked BEFORE it exists:
   its beats' `achievable_via`/`unreachable_if` atoms must reference established
   entities (the lint `1-referents` rule, reused); its premise must hold or be
   reachable (`StateIs`/`InFrame` evaluate to TRUE/INDETERMINATE, not FALSE;
   `route`/`path` for any spatial precondition); and it must pass `lint_arc`
   (the existing arc linter). Fail → DECLINE, not a broken arc. (PB gives the
   atoms — `frame_diff`, folds, `route`/`path`, `confidence`, situation; the
   coherence *policy* is ours.)
6. **Committed-delta read** — already in §3; the opportunistic trigger keys off
   the `since`-scoped post-ingest read, never prose.

Plus the always-on P1 invariants: generator output is authored into `plot:<id>`
(structurally absent from canon + `knows:player` — the concealment is the
membrane, not a prompt); the hook reaches the player ONLY as a briefing directive;
a generator miss never breaks the turn (fail-open — the world just stays quiet).

## 5. The mint mechanism (reuses P1 + session-zero authoring)
1. **Propose** — the DM cohort (`cohorts.generate_arc`, new) gets: the committed
   delta, the active fallout/threads, the present NPCs' spines, the genre/style,
   and the AVAILABLE ENTITY IDS (the `known_ids` allowlist, as session-zero arc
   authoring uses). It returns a compact arc proposal in the SAME shape
   `_build_arc` already consumes (protagonist, delta_type, tension, 1-2 beats,
   optional `unreachable_if`), plus a one-line diegetic `hook`.
2. **Build** — `game._build_arc(proposal, arc_id="arc:gen_<n>")` (P1 already
   parametrizes arc_id, mints per-arc refusal/beat ids → no collision).
3. **Preflight** — guard #5 (`lint_arc` + referents + premise reachability +
   fingerprint dedupe + depth/active caps). Any fail → DECLINE + receipt.
4. **Commit** — `arc_to_items(arc) + index_items(arc)` into `plot:main`; append the
   id to `arc:portfolio.arc_ids` (a new `io.add_arc_to_portfolio(world, arc_id)`);
   write `generated_from`/`gen_depth` provenance + the `generation_attempt` receipt
   + the fingerprint. A short clock so the arc can also conclude on its own.
5. **Surface** — the new arc's `hook` becomes a briefing directive on THIS turn
   (or the next), like the P1 fallout/reveal directives — diegetic, no system leak.

## 6. Where it runs in the turn loop
A new step in `run_turn`, AFTER the P1 side-arc lifecycle block (so it can react to
a death THIS turn) and AFTER the committed-delta read is available, BEFORE the
briefing assembly (so a fresh hook can be briefed). Fail-open: wrapped so any error
logs and leaves the world quiet. The minted arc joins `side_arcs` for subsequent
turns automatically (re-read from the portfolio on the next `open_playthrough`;
within the same session, appended to the live `side_arcs` list).

## 7. Phasing within P2
- **P2a** — the **regenerative** trigger only (spawn from P1 fallout), with all six
  guards. The cleanest first slice: a dead arc seeds exactly one successor, capped
  and deduped. Live-test: kill a side arc, watch a grounded successor appear.
- **P2b** — the **opportunistic** trigger (player-delta reading).
- **P2c** — the **ambient** trigger (quiet-turn filler).
Each slice: build → Codex review → live-test (logged) before the next.

## 8. Open questions for the mesh (raise only if they bite)
- The `generate_arc` cohort tier (main vs a cheaper tier) + cost cadence — likely
  main/deliberate but paced so it's rare.
- Whether the minted hook briefs THIS turn or strictly next (pacing feel) — start
  with next-turn to avoid a same-turn whiplash; tune in live-test.

## 9. Status
P2a SHIPPED (regenerative + all six guards, Codex-reviewed; `arc/generator.py`,
`cohorts.generate_arc`, turnloop step, 13 tests). P2b/P2c: spec'd below, for
review then build.

---

# P2b (opportunistic) + P2c (ambient) — build spec

**Status:** SPEC, for Cx review then build. Extends the shipped P2a machinery —
same cohort (`generate_arc`), same guards, same mint path (`_build_arc` →
preflight → commit → portfolio → hook). What P2b/P2c add is *when the DM wakes
and what fuel it reads*. Four fresh-eyes amendments below are load-bearing.

## A. The salience pre-filter (P2b's gate — "waits for the moment" made structural)

The naive P2b fires the DM cohort every `GEN_COOLDOWN` turns and asks "anything
interesting?" — expensive (main-tier, deliberate) and spammy in spirit even when
the answer is no. A good DM doesn't poll; they *notice*. So P2b's trigger is a
**deterministic, zero-model-call salience read** over the turn's committed
delta, and the cohort wakes ONLY when it finds a qualifying moment:

- **Source (guard #6 — THIRD revision; the first two were falsified by
  evidence, chain recorded):**
  1. ~~`snapshot(scope, since=…)`~~ — falsified by Cx 498: PB applies `since`
     only to the `what_happened` lens; on `current_state` it is ignored and the
     "delta" is the full standing state (any scene with a spined NPC reads
     salient every turn).
  2. ~~valid_from-window over `frame_facts`~~ (`valid_from > turn_time(turn-1)`)
     — falsified by the FIRST LIVE §F RUN (2026-07-09): narrator-extracted
     facts are committed UNSTAMPED in the settle tail and land at the engine
     CURSOR, which never moves during play. In a session-zero/harness world
     the cursor sits BELOW `TURN_EPOCH` → promote rows can never enter any
     window (the trigger is BLIND to dialogue-driven deltas — the live Probe 1
     failure); in an ingested world the cursor sits at the LAST SOURCE CHUNK,
     above every `turn_time` → all past narrator facts qualify forever
     (permanently salient). A time-window over unstamped rows is the wrong
     predicate in both directions.
  3. **CURRENT — the explicit committed batch** (what Cx 496 amendment 1
     offered first; precision per Cx 525): the turn loop passes the actual
     commit lists, no time-window read at all —
     - *previous turn's narrator delta:* the settle tail persists its
       **RECEIPT-CONFIRMED** promotions — never the candidate `promote` list
       (fail-open ingest converts a failed commit into an empty receipt, and a
       candidate that didn't land must not wake the generator as truth). PB
       receipts carry entity/attribute but NOT value, so the settle retains the
       resolved candidate VALUES for receipt-confirmed keys locally (a small
       hydration join; PB's frozen porcelain is not widened).
     - *the handoff row is per-turn KEYED, not a singleton:* an append-only
       `event:turn_<n>` / `narrator_promote` JSON literal in `session:main`,
       `valid_from=turn_time(turn)`, `classify="rules"` (deterministic, no
       model call). The entity carries an `event:` prefix; PB's guardrail
       classifies it as EVENT rather than STATE — that is fine because the
       reader uses a raw bounded `frame_facts` read (not a folded state read),
       so durability classification does not affect retrieval. Written EVERY
       settle, OUTSIDE `if promote:` — an empty list on quiet turns.
       Deterministic cap (~60) with BOTH kept and dropped counts recorded. The
       reader at turn n reads EXACTLY turn n-1's row and returns `[]` when it
       is absent or malformed — a missing/failed settle yields a false negative,
       never a stale replay (structural, not dependent on the next settle
       succeeding).
     - *current turn's player-action delta:* the adjudication/input-extraction
       commits, receipt-confirmed under the SAME rule (values hydrated locally
       for confirmed keys — the raw `receipt_rows` alone lacks values for the
       spine-touch value-side check).
     Both are post-gate, receipt-confirmed committed rows — guard #6 (never
     prose) holds, and the batch is membrane-clean precisely BECAUSE it records
     successful commits rather than intended candidates.
  - event rows (unchanged, they carry explicit stamps):
    `reads.events(since=int(turn_time(turn-1)), frame="canon")` client-filtered
    via `window_events` to `e.at > turn_time(turn-1)`.
  - Never prose.
- **Qualifying signals (the initial set — small, tunable in live-test):**
  1. **Spine-touch:** a window fact row whose `entity` or `value` is a person id
     in the SPINED set — the present NPCs whose `drive`/`fear` the turn loop
     already read into `canon_table` (the P2a `present_characters` source). The
     player touched someone who *wants* something.
  2. **First-time event kind:** a window event whose `kind` is not in
     `prior_kinds` (the kinds of all events BEFORE the window — one
     `reads.events(until=int(turn_time(turn-1)))` scan, kinds collected),
     EXCLUDING the routine bookkeeping kinds
     `{"turn", "player_action", "arc_touch", "arc_terminal", "arc_won",
     "arc_lost", "generation_attempt", "generation_declined", "conclusion",
     "commitment", "seal_incoherence"}` AND any event whose id starts with
     `event:tick_` (the world's own off-screen motion is not a player-caused
     moment — that is ambient's domain, and discovery-gating parity applies).
  3. **Causal ripple:** a window event with non-empty `caused_by` — something
     durable just rippled. (Fact-row `caused_by` can join the set later; events
     carry it today on the shipped `EventRow`.) The ROUTINE-kind and tick
     exclusions apply to this signal too — a bookkeeping event carrying causal
     linkage is not a dramatic moment; without this, live worlds where engine
     events routinely carry `caused_by` are salient EVERY turn and the filter
     stops filtering (implementation finding, pinned by test).
- No qualifying signal → **no cohort call, no generation attempt/decline
  receipt, no trigger-side bookkeeping, no cost** (a non-salient turn is not an
  attempt; pacing must not see it — Cx 496 ruled this sound: `_last_try_turn`
  reads only attempt/decline receipts). The neutral per-turn batch-handoff
  receipt (`narrator_promote`) is written regardless — it is settle-side world
  bookkeeping, not trigger bookkeeping (Cx 525 amendment 3 reconciliation).
  A salient turn → the existing pacing guard (`_pacing_ok`: cooldown + active
  cap) still applies, then the cohort fires with the salient rows phrased as
  `fuel` lines.
- **Presence gate (implementation decision, conservative):** the P2b/P2c cohort
  call additionally requires ≥1 PRESENT spine-carrying NPC (the `spined` set
  non-empty) — without one, the DM has no grounded NPC protagonist in scene to
  propose, and P2 arcs are NPC-protagonist by invariant (§D). Known narrowing:
  a quiet EMPTY scene never fires ambient even in endless mode. Deliberate for
  the first slice of a spam-risk feature; relax to "any spined NPC in scope"
  only if live-test shows real quiet-empty-scene developments being missed.

**Shape it as a reusable PURE reader** (Cx 496 amendment 1 — explicit inputs,
no hidden reads, unit-testable without a world):

```python
def salient_moments(fact_rows: list[dict], events: list,      # EventRow
                    prior_kinds: set[str], spined: set[str]) -> list[str]
```

returning human-phrased fuel lines (empty = not salient). The turn loop
assembles the four inputs (snapshot-since facts, events-since window,
`prior_kinds` = the kinds already seen before the window, `spined` = present
NPC ids with a canon `drive`/`fear`). Separate from the generator because the
founder's captured drift-handling designs (relocate-the-beat,
absence-consequence) will need the SAME "what just changed + who is positioned
to care" read. One reader, several consumers; don't fuse it into the DM.

## B. Dramatic right-of-way (a NEW guard, all triggers)

Nothing in the shipped guards knows where the MAIN story is. A DM who launches a
fresh subplot during the climax is a bad DM. New structural rule: **no generation
while the main arc is in CRISIS or CLIMAX** (`executor.current_phase(reads,
main_arc)` — a cheap derived read). This gate runs FIRST in the trigger chain
and is **silent**, meaning exactly (Cx 496 amendment 2, boundary sharpened per
Cx 498): **no GENERATOR bookkeeping** — no `generation_declined` receipt, no
pacing-visible row, no fingerprint, nothing the DM's own audit trail would
record (it isn't a DM judgment; it's right-of-way, and receipting every peak
turn would churn rows and distort the `_last_try_turn` pacing read). Applies to
all three triggers.

**The development LEDGER is not generator bookkeeping.** The `session:ambient`
/ `last_development_min` row (§C) records that the WORLD developed — a beat
achieved, a clock fired, a fallout emitted — and must record peak-turn
developments too, so it is written OUTSIDE the trigger chain (before the gate,
independent of `generate`). Skipping it at peak would make a beat-rich climax
read as a false half-day of silence and fire ambient the moment the climax
breaks — the exact misfire the ledger exists to prevent. The right-of-way
silence contract is therefore: on a peak turn the trigger chain contributes
ZERO rows; the ledger still tracks real developments, as it does on every turn.

**Acceptable loss, ruled by Cx 496 — no fallout queue.** The regenerative
trigger consumes only the SAME-TURN `fallouts` list; a side-arc death during
the main peak therefore **intentionally forfeits its same-turn regenerative
mint** — there is no backlog scan and none is added in this slice. This is
acceptable because `emit_fallout` has already written the terminal event AND
the `caused_by`-linked canon consequence: the fuel persists as world truth and
remains available to the later opportunistic (causal-ripple signal) and ambient
triggers. Do NOT implement a queue.

## C. P2c ambient keys on DIEGETIC time, never turn count (founder-ruling conflict)

The P2 spec's original "too many quiet turns" phrasing **violates the sealed
ruling** (2026-06-25): *turns are free; only diegetic time is the clock.* Thirty
contemplation turns = five in-world minutes — the world throwing something up
there would punish exactly the play the ruling protects. So:

- **Quietness is measured on the story clock**, with explicit bookkeeping (Cx
  496 amendment 3 — existing receipts are stamped `turn_time(turn)`, a TURN
  coordinate; there is no historical clock read, so the diegetic minutes of the
  last development must be STORED, never derived):
  - A hidden session row **`session:ambient` / `last_development_min`** holds
    the diegetic-minute stamp (a float from `read_clock(world).minutes`) of the
    most recent development. One helper `_mark_development(world, minutes_now,
    turn)` writes it (`valid_from=turn_time(turn)`, superseding).
  - **Update points:** any generation MINT (all triggers), any beat achieved,
    any clock fired, any fallout emitted — all sites already explicit in
    `run_turn`.
  - **Seed-on-absent is a WRITE-ONCE baseline (Cx 498):** if the row is missing
    (fresh or pre-P2c world), WRITE the current `read_clock(world).minutes` as
    the baseline before returning it — the quiet-timer starts "now", never at
    genesis. A read-only seed that merely RETURNS "now" reseeds every check and
    the interval never accrues: ambient would be structurally dead on fresh
    worlds. Regression required: a fresh quiet endless world does not fire
    immediately, and DOES fire once `AMBIENT_QUIET_MIN` diegetic minutes accrue
    past the seeded baseline.
  - **The trigger test** (after right-of-way and `_pacing_ok`):
    `read_clock(world).minutes - last_development_min >= AMBIENT_QUIET_MIN`
    (default `720.0` — half an in-world day; genre-tunable later).
- **Scope: endless mode only** — gate on `scenario_mode == "endless"` (the
  string `run_turn` already receives; NOT the legacy `endless` bool — Cx 496),
  incl. post-conclusion continuation. In a win_loss story the refusal clock +
  the nudge ladder already own drift, and ambient filler would dilute an
  authored destination. Default OFF in win_loss.
- Ambient fuel = the standing tensions (`live_threads` / situation) + present
  NPC spines; trigger string names it ambient; `generated_from =
  "ambient:<turn>"` (the lineage shape §4.2 already reserves).

## D. Trigger arbitration + the player boundary

- **At most ONE mint per turn** (already the P2a invariant). Priority when
  several triggers qualify: **regenerative > opportunistic > ambient** —
  reaction to a death beats reaction to a deed beats filling silence.
- **P2b/P2c always mint NPC-protagonist arcs, enforced HOST-SIDE** (Cx 496
  amendment 4 — the prompt branch is not an invariant): `generate_arc` is
  called WITHOUT `protagonist=` (that kwarg is the episodic-continuation path),
  AND the wrapper deterministically rejects a proposal whose built
  `arc.protagonist == main_arc.protagonist` — decline with reason
  `"player_protagonist"` (a normal `generation_declined` receipt; this IS a DM
  judgment, unlike right-of-way). The world moves *at* the player, never *as*
  them.
- **Depth-0 roots, enforced explicitly** (Cx 496 amendment 5): P2b/P2c wrappers
  call `_record_attempt(world, arc, source, 0, fp, turn)` — the literal depth
  `0`, with `source = "player_delta:<turn>"` / `"ambient:<turn>"`. They must
  NOT reuse the regenerative path's `parent_depth + 1` increment (which would
  wrongly record depth 1). `_parent_depth` returning 0 for non-terminal sources
  keeps any FUTURE death of a P2b/P2c arc at regenerative depth 1.
- Fingerprint/dedupe (situation-scoped, source-EXCLUDED — see §4.3), active
  cap, cooldown, preflight, hook sanitizer: unchanged, shared across triggers.

## E. Build inventory (small; all shipped surfaces)

- `construct/arc/generator.py`:
  - `+salient_moments(fact_rows, events, prior_kinds, spined) -> list[str]`
    (PURE — §A signature; plus the module-level `ROUTINE_EVENT_KINDS` frozenset).
  - `+_mint_side_arc(world, reads, provider, trigger, fuel, source, side_arcs,
    ctx, turn, main_protagonist)` — the shared mint path factored from
    `generate_from_fallout`'s body (cohort → fingerprint → `_build_arc` →
    preflight → player-protagonist reject → commit → portfolio →
    `_record_attempt` with an EXPLICIT depth arg → sanitized hook), so all
    three triggers share one audited path. `generate_from_fallout` keeps its
    exact signature + behavior (depth = parent+1, exhaust/depth-cap logic);
    P2b/P2c wrappers pass depth 0.
  - `+generate_opportunistic(world, reads, provider, moments, side_arcs, ctx,
    turn, main_protagonist)` and `+generate_ambient(...)` — thin wrappers:
    trigger strings "the player's actions opened a door (opportunistic)" /
    "the world has been quiet a while (ambient)", fuel from the moment lines /
    standing threads + spines, `source = "player_delta:<turn>"` /
    `"ambient:<turn>"`, depth 0.
  - `+main_at_peak(reads, main_arc) -> bool` (right-of-way:
    `current_phase(reads, main_arc) in (Phase.CRISIS, Phase.CLIMAX)`).
  - `+AMBIENT_QUIET_MIN = 720.0`, `+_last_development_min(reads, minutes_now)`,
    `+_mark_development(world, minutes_now, turn)` (the `session:ambient` row,
    §C).
- `construct/turnloop.py` — extend the existing P2a step (same location, same
  fail-open wrapper, same hook briefing):
  1. `main_at_peak(...)` → skip everything, SILENTLY (no receipt).
  2. Regenerative exactly as today (fallouts non-empty).
  3. Else opportunistic: assemble the §A inputs (snapshot-since over `scope`,
     events-since, prior_kinds, spined-present set from `canon_table`) → if
     `salient_moments(...)` non-empty and `_pacing_ok`, mint.
  4. Else ambient: `scenario_mode == "endless"` and the §C diegetic test and
     `_pacing_ok`, mint from standing threads + spines.
  5. `_mark_development(...)` calls at: mint (any trigger), beat achieved,
     clock fired, fallout emitted.
  At most ONE mint per turn (the if/elif chain enforces it structurally).
- Tests — salience unit cases on the PURE function (spine-touch / first-kind /
  routine-kind excluded / tick excluded / caused_by / non-salient); right-of-way
  (CRISIS/CLIMAX → no mint AND no decline receipt; SETUP/RISING mints);
  ambient diegetic threshold (many quiet turns + few in-world minutes → NO
  mint; a quiet half-day → mint; seed-on-absent → no first-turn fire) +
  win_loss OFF; arbitration order (fallout beats salient delta beats quiet);
  player-boundary (a proposal naming the main protagonist → declined
  `player_protagonist`, no mint); depth-0 roots (`gen_depth == 0` on a P2b
  mint; a P2b arc's later death regenerates at depth 1).
- **Fact-source v3 test bar (HD 520 + Cx 525):**
  - a settle-persisted promote batch touching a spined NPC → salient NEXT turn
    (the live Probe-1 blind case, closed);
  - a quiet settle writes `[]` and an OLDER batch cannot re-trigger; a
    MISSING/failed settle (no turn n-1 row) reads `[]` — never replays an older
    source turn;
  - a failed/dropped promotion (fail-open empty receipt) never appears in the
    stored batch;
  - a VALUE-side relation to a spined NPC survives receipt confirmation (the
    hydration join preserves values for confirmed keys);
  - first-turn absence reads `[]`; clean close/reopen reads the persisted
    prior-turn receipt;
  - cap/truncation is deterministic with kept AND dropped counts recorded;
  - standing canon rows at a high cursor (ingested-world shape) do NOT make
    turns salient — holds by construction (no fact window exists), pinned;
  - the existing pre-existing-spined-NPC run_turn pin stays green.
- No engine work; no new frames; membrane unchanged (all bookkeeping stays
  `plot:`/`session:`).

## F. Live acceptance (post-GREEN, logged to the founder)

In an endless world: (1) antagonize a spine-carrying NPC → a grounded
complication arrives within a few turns (P2b); (2) contemplate for 30 turns (5
in-world minutes) → the world stays quiet (the ruling holds); (3) let a half
in-world day pass idle → the world throws something up (P2c); (4) drive the main
arc to crisis → no mints until it breaks (right-of-way).
