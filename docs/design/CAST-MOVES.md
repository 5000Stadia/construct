# Cast Moves — the narration-seam movement lane (spec)

**Status:** SPEC, PB comment round FOLDED (PB letter
`<e1ca7951…>`, 2026-07-10: two catches fixed, four answers integrated,
optional caused_by lever ADOPTED), now for Cx review then build. Task #80 —
"the single highest-leverage remaining gap" (OPTIMAL-IF-EXPERIENCE.md
§narration-seam). Gate opened by PB letter 125.

## Problem

Narrator prose stages cast movement constantly — "the maid slips out", "Harl
comes in from the yard, stamping snow" — and nothing commits it. Presence truth
drifts from the render: the maid is still `in` the parlor per canon, so the
presence system keeps offering her; Harl is present in prose but absent from
`_persons_under`, so engagement with him grounds nothing. WORLD-TICK moves
people OFF-screen deliberately; on-screen arrivals/departures were explicitly
left as #80's job (WORLD-TICK.md §59).

**The sharpened problem, post-quarantine-liveness:** now that the gated ingest
actually runs on live narrator output (the 2026-07-09 fix), a narrated move
reaches the promote gate and is **quarantined as a contradiction by design** —
an NPC's `in` change is exactly "the narrator overwrote established canon."
The gate is doing its job; movement needs its own LICENSED lane, not a loophole.

## Shape: a licensed person-movement lane in the settle

PB's recipe (letter 125, confirmed current in the 2026-07-10 deliberation):
capture at the seam → bind the destination → commit through the gate → audit
the receipt. The engine guards *structure* (cycle/self-edge/malformed →
typed skip receipts); *stagecraft* — who may be moved by narration, when — is
the host policy this spec defines.

### 1. Capture (in `_settle`, after the frame partition, before the promote diff)

Partition the resolved narrator rows once more: rows whose attribute is in
the **containment-synonym set `{in, inside, located_in}`** and whose ENTITY is
a canon **person** (folded kind) leave the ordinary promote flow and enter the
cast-moves lane; the lane canonicalizes the attribute to `in` before the policy
gate. The synonym set matters (PB catch): the gate's canonicalization map
(`inside → in`, `located_in → in`) runs AT INGEST — i.e. *after* this
partition — so matching the literal `"in"` alone would let a narrated "she's
inside the barn" slip past the lane into the ordinary promote flow and
quarantine as a contradiction, resurrecting exactly the drift this lane closes.
Everything else is untouched (objects keep the held-object guard and ordinary
promotion; places keep their no-mint channel policy).

### 2. The policy gate (stagecraft — each rule with its doctrine source)

A candidate move `person:X in place:D` is LICENSED only if ALL hold:

1. **Never the protagonist.** The world cannot puppet the player
   (structural-absence doctrine). Drop + telemetry.
2. **Never a bound companion.** An ACCOMPANYING companion may not be silently
   stranded by prose drift (presence-holds + companion-state doctrine, the
   founder's live "Reed!? Where are you!?"). Explicit player dismissal already
   has the `departed_scene` path via classify; the narrator does not get to
   dissolve the bond. Drop + telemetry.
3. **The destination BINDS.** `place:D` must already exist in canon (the
   narration channel cannot mint places — Entity Authority; PB's rule: an
   unknown destination is REJECTED, never minted). The resolver enforces most
   of this upstream; the lane re-verifies the **folded kind on the RESOLVED
   head** == place (PB: the bound id may be a `same_as` alias — fold in canon).
   No preflight of the engine's structural reasons (cycle/self-edge): those are
   graph-state-dependent as-of the edge's `valid_from` and a host preflight
   would duplicate them imperfectly; commit and audit the receipt instead.
4. **The move touches the CURRENT scene.** Either origin (X's current `locate`
   head — the canon current head, no `as_of`) or destination is the scene (an
   on-screen departure or arrival). A
   REMOTE move — the narrator asserting motion happening elsewhere — is not
   the narrator's to know (its briefing is scene-scoped truth); world-tick
   owns off-screen motion. Drop + telemetry.
5. **X is not mid-conversation-turn protected** — if X spoke or was engaged
   THIS turn (present in the turn's npc engagement set), a same-turn narrated
   exit contradicts presence-holds ("came and went before I could talk to
   them"). Departures license only for cast the player is NOT actively
   engaging this turn. Arrivals are always presence-positive and skip this rule.

### 3. Commit (the doorway)

Licensed moves commit via `ingest_structured(moves, classify="rules")`
**direct to canon** — NOT through the proposed-frame quarantine. There is NO
call-level `valid_from` kwarg (PB catch: the signature is
`(items, frame, classify, cursor_authoritative)`); **each move dict carries
`valid_from: turn_time(turn)` per-item** — the lane authors the items, so this
is one line. Rationale for direct-to-canon (PB-confirmed the right doorway;
the engine gate — canonicalization, malformed-id, structural guards, typed
receipts, provenance — applies fully on `ingest_structured` regardless): the
move was already RENDERED to the player as world truth; staging it for a gate
that exists to catch contradictions would re-create the render/truth drift this
lane exists to close. The contradiction the promote gate would flag (the old
`in` value) is precisely the supersession the move intends; single-parent
semantics retire the old holder automatically (PB 125: "no delete, no
cleanup"; PB confirms the gate's single-parent guard skips only CYCLE-forming
edges — a plain second `in` row is never skipped, and the old holder retires
at fold time by `(valid_from, asserted_at)` winner selection). No retract
needed. `classify="rules"` = zero model calls (PB-verified: the containment
guardrail defers a non-held, non-place person·in row and rules-mode resolves
the deferral to STATE deterministically).

### 4. Audit + downstream

- The engine receipt's `skipped` (cycle/self-edge/malformed) and the lane's own
  drops surface as `trace.cast_moves` (committed) + `trace.cast_move_drops`
  (reason-tagged) — the same telemetry discipline as `settle_noncanon_frames`.
  Any skip receipt in the lane is **telemetry, not error** (PB). Known benign
  reason since INGESTION-FIDELITY-V2: `merged_self_edge` (a containment edge
  whose raw ids resolve to one identity head post-`same_as` — travel-commit
  noise after a place merge, not an authored bug).
- `locate(X)` is the post-commit verification in tests (PB 125 step 4).
- A committed DEPARTURE additionally writes the existing `departed_scene`
  event (agent=X, patient=scene) — negative scene truth for the presence reads,
  reusing the shipped mechanism rather than inventing a second one. Event rows
  are **stamped `valid_from=turn_time`** (PB: an unstamped event ignores
  `as_of` exclusion and sorts oldest in recency ordering). PB confirms no
  harmful lens interaction: EVENT-durability rows are excluded from folds, so
  the event can never pollute presence/state, and a bare `departed_scene`
  never surfaces in `snapshot(lens="situation")`.
- **ADOPTED (PB's optional lever):** the departure's new `in` row carries the
  item-level `caused_by` field pointing at the `departed_scene` event. The
  situation lens then lights "X left" in re-entry briefings for as long as X's
  away-location is the served truth — the verified `emit_fallout` linkage
  shape, and exactly this project's re-entry-coherence goal. An arrival needs
  no event: the `in` row IS presence-positive truth.
- Salience note: cast-move rows ride the narrator settle batch (the
  `narrator_promote` audit receipt) but — per the LWG salience split — do NOT
  feed spine-touch. An arrival becoming DM fuel would need the player to act on
  it; correct as-is, no special-casing.

## Non-goals

- No narrator authority over objects (held-object guard unchanged) or places.
- No remote/off-screen movement (world-tick's).
- No new event vocabulary beyond the existing `departed_scene`.
- No engine change of any kind (PB 125: all shipped verbs).

## Test bar

1. **Arrival:** narrated "Harl comes in" (X off-scene, destination==scene) →
   `in` row committed at the turn coordinate; `locate` confirms; X appears in
   `_persons_under` next turn; engageable.
2. **Departure:** narrated exit (origin==scene) → committed + `departed_scene`
   event (stamped `valid_from=turn_time`); the new `in` row's `caused_by`
   points at the event; X gone from presence next turn; no re-offer; a
   re-entry briefing surfaces "X left" via the situation lens.
3. **Protagonist move** in prose → dropped, telemetry, player unmoved.
4. **Companion move** (ACCOMPANYING X) → dropped, telemetry, bond intact.
5. **Remote move** (neither endpoint is the scene) → dropped, telemetry.
6. **Unknown destination** → rejected upstream (resolver) or by the lane's
   re-verify; never minted; telemetry.
7. **Engaged-this-turn departure** → dropped (presence-holds); the same exit
   next turn (unengaged) licenses.
8. **Structural skip:** a move the engine refuses (e.g. cycle-forming) →
   typed skip receipt surfaced in telemetry; turn survives.
9. **Ordinary person rows** (non-containment) still flow through the normal
   promote gate unchanged — the lane takes ONLY movement — AND a
   **synonym-authored move** (`attribute == "inside"` at the seam) enters the
   lane rather than leaking to ordinary promotion (PB catch 2 oracle).
10. Full suite green; live acceptance = a staged two-NPC scene where the prose
    moves one out and one in across three turns, presence tracking both.

## Sequencing

PB comment round on this doc — DONE 2026-07-10 (letter `<e1ca7951…>`: two
catches folded above; direct-to-canon doorway, no-retract, and the kind
re-verify shape all PB-confirmed; stagecraft rules 1-5 scanned, all host
doctrine) → Cx spec review → build (delegate) → Cx code review → live
acceptance → docs/push.
