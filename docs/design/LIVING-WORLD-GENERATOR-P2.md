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
   proposed arc (the sorted tension triple + the gated entities + trigger source);
   store it in a `gen_fingerprint` index (session frame). A fingerprint already
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

## 9. Not built
Spec only. On build: P2a first (regenerative + six guards) → review → live-test.
Nothing ships before the guards are in — they are the gate, not an afterthought.
