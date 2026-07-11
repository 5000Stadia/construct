# Cast Moves — the narration-seam movement lane (spec)

**Status:** SPEC r5 — BUILT (code GREEN through three cr rounds, suite 942)
and **bar-11 LIVE-ACCEPTANCE AMENDED**: the live probe proved the lane
end-to-end in real fiction and found one correctness defect (a false
unbound exit from a within-scene position) + two tunings; cr disposition
`<f8409447…>` folded here — the unbound-exit path NARROWED fail-closed
(§1.3), per-person normalization + the origin-restatement tie-break made
spec text (§2b), the sole-NPC engagement follow-up slice recorded (§2 rule
5). Review chain: PB `<e1ca7951…>` → cx r1 `<a85c6ade…>` → cx r2
`<9891be53…>` → cr r3 `<787848dc…>` → cr code rounds → live bar 11.
Task #80 (OPTIMAL-IF-EXPERIENCE.md §narration-seam); gate opened by PB 125.

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

**Canonicalize BEFORE resolve (Cx r1 gap 1).** The containment-synonym
canonicalization (`inside → in`, `located_in → in`) runs on the ACCEPTED RAW
extraction rows **before `resolve_rows`** — not after. The resolver's
entity-valued vocabulary (`_ENTITY_VALUED_ATTRS`, resolve.py:40) contains
`in`/`inside` but NOT `located_in`; a `located_in` row reaching the resolver
un-canonicalized would never have its destination bound, and the gate's own
canonicalization map runs at ingest, one boundary too late for either the
resolver or this lane. Canonicalizing at the seam's entry gives every
downstream step one spelling. (Test bar 9 exercises all three spellings —
`located_in` especially, since it is the one the resolver would silently
strand.)

Then partition the resolved narrator rows once more — two candidate shapes:

- **BOUND MOVE:** a canonical `in` row whose ENTITY is a canon **person**
  (folded kind) and whose destination RESOLVED to a bound id. Leaves the
  ordinary promote flow, enters the full policy gate (§2).
- **UNBOUND EXIT (Cx r1 gap 2 — "the maid slips out"; data path
  row-correlated in r2; correlation contract made real in r4 per cr's
  focused RED `<787848dc…>`):** detection is NEVER inferred from the
  resolver's global `(failed_value, attribute, reason)` receipt tuple — with
  several same-attribute rows that tuple cannot say WHICH person moved, nor
  which SIDE of a row failed. The correlation surface is an **out-of-band
  per-input `ResolutionOutcome` record**, chosen precisely so that the
  THREE existing contracts stay untouched:
  1. `resolve_rows` gains an optional collector param; for each ACCEPTED
     input row (post-canonicalization) it appends
     `ResolutionOutcome(row_index, raw_entity, raw_value,
     resolved_entity, resolved_value, subject_outcome, value_outcome,
     reason)` where `subject_outcome`/`value_outcome` ∈
     `{bound, minted, dropped, bound_non_place, not_entity_valued}` — each
     SIDE reported separately (one input row can emit several legacy
     receipts; the outcome record is the per-row truth).
  2. **No contract breaks (cr sub-gap 3):** the legacy `(id, attribute,
     reason)` receipt triples — `trace.resolver`, ~30 destructuring call
     sites, existing oracles — are emitted EXACTLY as today; the resolved
     OUTPUT rows are unchanged and carry NO private metadata, so nothing
     needs stripping before `ingest_structured` (the outcome records are
     out-of-band and never enter the ingest path — pinned by an oracle).
  3. The lane consumes ONLY the outcome records. UNBOUND-EXIT candidate
     (**narrowed per the bar-11 live defect + cr disposition
     `<f8409447…>`** — live fiction proved a fully-unbound destination is
     as often a within-scene POSITION, "she stays by the hearth", as a true
     exit, and a false `departed_scene` is durable negative presence for a
     present person):
     - `value_outcome == dropped` **NEVER creates a candidate** — telemetry
       `ambiguous_unbound_destination`, no event, ever.
     - `value_outcome == bound_non_place` (or bound to a non-place) may
       carry an EVENT-ONLY exit ONLY when the retained `resolved_value`
       PROVES at `_h`: a physical NON-person container/object; a nonempty
       location chain; whose place head lies OUTSIDE the current scene's
       containment area. Person destinations, unknown/no-location values,
       and anything colocated with the scene are REJECTED (reason-tagged
       drops). Rules 1/2/5 apply as always.
     - **Accepted false negative:** a wholly novel exit destination ("the
       passage beyond") no longer fires — preferable to false negative
       presence — until extraction supplies a first-class departure/exit
       EVENT shape (PB consultation authorized: containment rows alone
       cannot distinguish "by the hearth" from leaving).
     A row whose SUBJECT dropped is nothing. A row with both sides bound is
     a BOUND MOVE (above) — same records, one partition.
  4. **Scene-restatement guard:** if `raw_value` names the CURRENT scene
     (token match against the scene's canon name — the `_names_entity`
     discipline), the row is an ambiguous restatement of where X already
     is, NOT an exit — dropped with reason `ambiguous_scene_restatement`,
     no event.
  A surviving candidate enters the reduced gate (§2 rules 1, 2, 5) and, if
  licensed, takes the EVENT-ONLY departure path (§4): a `departed_scene`
  event and nothing else — negative scene presence without a canon location
  claim, the same shape as the shipped player-dismissal mechanism. Never a
  place mint.
- **Out of scope, stated honestly:** a narrated exit that produces NO
  containment-shaped extraction row at all ("she slips out" extracted as
  nothing) gives the seam nothing to license. That residual drift stays
  open; it is bounded by presence-holds prompt discipline and closes only
  if extraction learns a departure shape (a future, separate decision).

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
3. **The destination BINDS** (bound moves only). `place:D` must already exist
   in canon (the narration channel cannot mint places — Entity Authority;
   PB's rule: an unknown destination is REJECTED, never minted). The resolver
   enforces most of this upstream; the lane re-verifies the **folded kind on
   the RESOLVED head** == place (PB: the bound id may be a `same_as` alias —
   fold in canon), read **at the play horizon** (`as_of=_h` — Cx r1 gap 5:
   every turn read is bound to `_h` per AS-OF-PLAY-HORIZON so future source
   rows never leak backward; same-turn rows at that coordinate are admitted.
   PB's "no as_of" note meant *not historical* — the horizon-bound current
   head satisfies both). No preflight of the engine's structural reasons
   (cycle/self-edge): those are graph-state-dependent as-of the edge's
   `valid_from` and a host preflight would duplicate them imperfectly; commit
   and audit the receipt instead.
4. **The move touches the CURRENT scene.** Either origin (X's `locate` head
   at the play horizon — `p.locate(X, as_of=_h)`, same invariant as rule 3)
   or destination is the scene (an on-screen departure or arrival). A
   REMOTE move — the narrator asserting motion happening elsewhere — is not
   the narrator's to know (its briefing is scene-scoped truth); world-tick
   owns off-screen motion. Drop + telemetry.
5. **X is not mid-conversation-turn protected.** A same-turn narrated exit of
   an engaged character contradicts presence-holds ("came and went before I
   could talk to them"). **`engaged_this_turn` is constructed explicitly**
   (Cx r1 gap 3, identity domain corrected in r2 — it is assembled pre-render
   in `run_turn` and passed BY VALUE into the deferred `_settle` closure) as
   the union of:
   - the **ADDRESSED set** — every present NPC satisfying the SHIPPED
     interview addressing predicate against the player input
     (turnloop.py:3240-3242): `only_one` (sole present NPC, vocative not
     absent) OR `npc == _voc_holder` OR `_names_entity(npc, input, name,
     role)` — captured at the interview site BEFORE eligibility/delivery
     filtering, so a questioned NPC with NO eligible or fresh clue is still
     engaged. **`asks_targets` is excluded from this union** (Cx r2: it
     holds opaque `ask_N` TOPIC ids, not people — it may choose the topic,
     never the person);
   - learned INTERVIEW-source NPCs this turn (confirmation only, always a
     subset of the addressed set). **Never the whole `learned` list** (cr
     build note: `learned` later also carries EXAMINE object holders — an
     object's holder is not a conversation partner);
   - autonomous speaker intent — every NPC whose `npc_turn_results[npc]
     ["speaks"]` is truthy.
   **Stated limitation:** dialogue the narrator improvises in prose BEYOND
   these pre-render intents is NOT detected in v1 — there is no reliable
   post-render speech-attribution surface. Accepted: the presence-holds
   directive still binds the narrator prompt-side, and every pre-render
   engagement signal is protected. Departures license only for cast NOT in
   `engaged_this_turn`; arrivals are presence-positive and skip this rule.
   **FOLLOW-UP slice (bar-11 finding 3, cr-shaped, separate from the
   correctness fix):** the `only_one` fallback over-protects — a LONE
   present NPC is "addressed" by every action turn ("I bank the fire"), so
   their narrated departure can never license in a two-person scene. The
   approved shape: a backward-compatible `npcs_addressed` opaque-ID field
   on the existing classify call (fail-open: omitted = empty; never
   inferred from punctuation); the sole-NPC fallback then protects only
   when that signal says the input ADDRESSES them. Named/role/vocative and
   autonomous-speaker protection stay deterministic. Required oracle pair:
   unnamed sole NPC + "What did you see?" → protected; unnamed sole NPC +
   "I bank the fire" → not.

### 2b. Per-person normalization (before the gate; cr code review + bar-11 tuning)

One narrated intent per person per turn. Exact duplicate candidates collapse
to ONE. Conflicting candidates for one person fail CLOSED
(`ambiguous_multiple_moves`) — with exactly ONE structural exception, the
**origin-restatement tie-break** (cr disposition `<f8409447…>`, from the
live finding that natural arrival prose "X comes in FROM THE YARD" extracts
BOTH the destination and a restated origin): when a person has EXACTLY two
candidates, BOTH bound, and EXACTLY one resolves to the person's current
immediate location at `_h` while the other resolves to a DIFFERENT known
place — the current-location row is a restatement of served truth, not a
move; discard it and send the other through every ordinary rule and receipt
check. This is not winner-picking: one row restates the served origin, one
is the sole state transition. Anything else — an unbound candidate in the
pair, indeterminate origin, two non-current destinations, three or more
candidates — stays `ambiguous_multiple_moves`. Pinned: candidate-order
independence and each fail-closed counterexample.

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
- **Receipt-gated sequencing (Cx r1 gap 4).** For a bound departure, the
  `departed_scene` event is written ONLY after the move's `in` row is
  RECEIPT-CONFIRMED: commit the moves batch first, confirm the move's
  entity/attribute key in the ingest receipt under the `confirmed_batch`
  discipline (exact per-key match — the shipped fact-source v3 rule), then
  write the event rows in a second batch. A structurally SKIPPED move
  (cycle/self-edge/malformed) therefore produces NO event and NO negative
  presence — otherwise `_departed_from` would suppress a person who never
  moved. Order within the departure pair: event committed second but with a
  PREDETERMINED id, so the `in` row's item-level `caused_by` (the lever
  below) can reference it. The UNBOUND-EXIT path has no move row to gate on;
  its event commits directly (it asserts only "X left the scene," which is
  exactly what was licensed).
- A committed DEPARTURE writes the existing `departed_scene` event
  (agent=X, patient=scene) — negative scene truth for the presence reads,
  reusing the shipped mechanism rather than inventing a second one. Event rows
  are **stamped `valid_from=turn_time`** (PB: an unstamped event ignores
  `as_of` exclusion and sorts oldest in recency ordering). PB confirms no
  harmful lens interaction: EVENT-durability rows are excluded from folds, so
  the event can never pollute presence/state, and a bare `departed_scene`
  never surfaces in `snapshot(lens="situation")`.
- **ADOPTED (PB's optional lever):** the bound departure's new `in` row
  carries the item-level `caused_by` field pointing at the `departed_scene`
  event (predetermined id, per the sequencing rule above). The situation lens
  then lights "X left" in re-entry briefings for as long as X's away-location
  is the served truth — the verified `emit_fallout` linkage shape, and exactly
  this project's re-entry-coherence goal. An arrival needs no event: the `in`
  row IS presence-positive truth.
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
2. **Bound departure:** narrated exit to a bound destination (origin==scene)
   → committed + `departed_scene` event (stamped `valid_from=turn_time`); the
   new `in` row's `caused_by` points at the event; X gone from presence next
   turn; no re-offer; a re-entry briefing surfaces "X left" via the situation
   lens.
2b. **Unbound exit (NARROWED — the verified-container path):** a containment
   row bound to a physical NON-person object provably located OUTSIDE the
   scene at `_h`, origin==scene, rules 1/2/5 pass → EVENT-ONLY
   `departed_scene`; no `in` row, no place mint; X gone from presence next
   turn; canon location unchanged (stale by design, world-tick's to move
   later). AND the narrowing oracles: (i) **stay-by-hearth negative** — a
   fully-DROPPED destination ("by the hearth") creates NO candidate, NO
   event, `ambiguous_unbound_destination` telemetry; (ii) **novel-
   destination false negative** — "the passage beyond" (wholly unbound) no
   longer fires, asserted as ABSENCE; (iii) person destination / no-location
   object / object colocated with the scene → reason-tagged drops, no event.
2d. **Origin-restatement tie-break:** exactly two bound candidates, one ==
   the person's current immediate location at `_h`, one == a different
   known place → the restatement is discarded and the move licenses through
   every ordinary check; counterexamples (unbound in the pair, two
   non-current, 3+ candidates, order swapped) stay `ambiguous_multiple_moves`
   — pinned order-independent.
2c. **Row-correlation oracles (Cx r2, expanded per cr r3):** a multi-row
   same-attribute batch distinguishing (a) SUBJECT drop vs DESTINATION drop
   (subject-drop rows are nothing), (b) exactly one destination drop → the
   RIGHTFUL person alone gets the event, (c) multiple simultaneous drops —
   each resolved per its own outcome record, (d) a destination bound to a
   NON-place → unbound-exit path, not a bound move, (e) NO private
   correlation metadata reaches `ingest_structured` (outcome records are
   out-of-band; committed rows are byte-identical to today's), and (f) an
   ambiguous restatement of the CURRENT scene ("she's in the room",
   unresolvable) emits NO `departed_scene` (`ambiguous_scene_restatement`
   drop). Plus: the legacy receipt-triple surface (`trace.resolver` and
   its destructuring consumers) is byte-for-byte unchanged.
3. **Protagonist move** in prose → dropped, telemetry, player unmoved.
4. **Companion move** (ACCOMPANYING X) → dropped, telemetry, bond intact.
5. **Remote move** (neither endpoint is the scene) → dropped, telemetry.
6. **Unknown destination** → rejected upstream (resolver) or by the lane's
   re-verify; never minted; telemetry.
7. **Engaged-this-turn departure** → dropped (presence-holds); the same exit
   next turn (unengaged) licenses. Separate cases per `engaged_this_turn`
   source: (a) player-addressed via the interview predicate (only_one /
   vocative / named), (b) learned-interview holder, (c) autonomous speaker
   intent (`speaks` truthy) — each protects; an unengaged present NPC does
   not. **Plus the r2 oracle:** a NAMED, questioned NPC with NO eligible or
   fresh clue is still protected — addressing engages, delivery does not
   define it.
8. **Structural skip:** a move the engine refuses (e.g. cycle-forming) →
   typed skip receipt surfaced in telemetry; turn survives; AND a skipped
   departure writes **NO `departed_scene` event and no negative-presence
   projection** (the receipt-gated sequencing oracle — Cx r1 gap 4).
9. **Ordinary person rows** (non-containment) still flow through the normal
   promote gate unchanged — the lane takes ONLY movement — AND
   **synonym-authored moves in all three spellings** (`in`, `inside`,
   `located_in` at the seam) enter the lane rather than leaking to ordinary
   promotion; `located_in` especially, since un-canonicalized it would never
   even bind its destination (Cx r1 gap 1 oracle).
10. **Horizon oracle:** a FUTURE-stamped location or kind row (beyond the
    play horizon `_h`) can neither license nor reject a present move — rules
    3/4 read as-of `_h` (Cx r1 gap 5); same-turn rows at the horizon
    coordinate are admitted.
11. Full suite green; live acceptance = a staged two-NPC scene where the prose
    moves one out and one in across three turns, presence tracking both.

## Sequencing

PB comment round — DONE (`<e1ca7951…>`) → Cx r1 RED — FOLDED (`<a85c6ade…>`,
five gaps) → Cx r2 focused RED — FOLDED (`<9891be53…>`, two gaps; 1/4/5
confirmed closed) → cr r3 focused RED — FOLDED (`<787848dc…>`, the
ResolutionOutcome correlation contract) → cr r4 confirmation → build
(delegate) → cr code review → live acceptance → docs/push.
