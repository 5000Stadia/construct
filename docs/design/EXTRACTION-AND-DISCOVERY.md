# Per-turn extraction cost & the discovery-licensing coupling

> **Folded into `STORY-SHAPE-AND-RESOLUTION.md`.** That spec resolves this coupling at
> the root: because the player *concludes* (the engine never hands over the answer
> mid-play), the per-turn player-input extraction falls away with no loss of protection.
> This doc remains the detailed analysis of the coupling + the PB-082 prompt-trim lever.


**Goal (founder, latency):** turns are slow; PB letter 077 named the lever — there
are TWO text extractions per turn (the player's input + the narrator's render), and
the substrate only needs one (the render is the authoritative canon-capture). Drop
the per-turn **player-input** extraction and ~half the extraction floor (~11s/turn)
goes away.

## Why it can't just be dropped (the coupling)

The per-turn player-input extraction (`p.ingest(player_input, …)` → `receipt_rows`)
feeds three things in `run_turn`:
1. `_mirror_rows(receipt_rows, player_frame)` — mirror the player's stated facts into
   their knowledge frame.
2. `touched` → the `arc_touch` session event.
3. **`pre_keys` / `pre_entities` — the concealment gate's license set.**

(3) is the blocker. After the Cx-022 hardening, a **protected** arc fact (the
mystery's answer) may enter canon/the player frame **only** if it's in `pre_keys` or
already in the player frame (`briefing_keys`). Token-matching (`_licensed`) was
deliberately ruled **too loose for protected keys** — that looseness *was* the leak.
So `pre_keys` (the player-input extraction) is currently the **only strict signal**
that the player legitimately *earned/observed* a protected fact this turn.

**Therefore:** dropping the player-input extraction removes the only thing that
licenses **discovery of the hidden answer**. Every non-discovery turn would be a pure,
safe win — but the one climactic discovery turn would get the answer **quarantined**
by the gate. Shipping the drop blind reopens exactly the leak we just closed.

## The redesign options (pick one)

### A. Arc-authorized reveal (recommended)
Make discovery a first-class ARC event instead of an extraction artifact. A beat
gains an optional **reveal-precondition**: "when the player does X in context Y, the
beat's fact is written to the player frame" — an arc-authorized, licensed write
through the ingest doorway. Discovery no longer depends on the player-input
extraction at all; the drop becomes safe.
- **Pro:** clean separation; discovery is intentional/authored, not a side effect;
  the gate stays strict; biggest latency win (drop the whole player extraction).
- **Con:** arc-layer work — beats must encode a reveal trigger (today they encode only
  the post-condition, "fact is in frame", which is circular for discovery). Touches
  the grammar + the authoring cohort + the executor.

### B. Conditional extraction (smaller, safer, partial win)
Keep extraction, but **skip it when the input can't assert/reveal a fact** — pure
observation, movement, OOC, simple questions. `classify` (already running, free)
emits `asserts_or_reveals: bool`; only then do the player ingest.
- **Pro:** no gate change; saves ~11s on the *common* turns (most turns); low risk.
- **Con:** doesn't help the fact-bearing turns; the discovery turn still extracts (but
  that's fine — discovery turns are rare and *want* the licensing). Net: most turns get
  faster, the leak stays closed, discovery still works. **This is the safe 80%.**

### C. Targeted player-claim gate-write (PB's literal suggestion)
Drop blanket extraction; when the player *explicitly asserts* a world-fact/knowledge,
route that one claim through `ingest_structured` deliberately. Discovery (observation,
not assertion) still needs A's mechanism, so C alone doesn't solve discovery.

**Recommendation:** **B now** (safe, real win on most turns, zero gate risk), then **A**
as the proper fix that unlocks the full drop. C is subsumed by A.

## The orthogonal, already-safe lever (in flight)
PB owns the extraction **prompt size** (every call pays its tokens) and offered to trim
it / add a "lean extraction" mode, guarded by their eval — *"send the profile and I'll
trim."* That cuts BOTH extractions' per-call cost with no host risk. **Action: send PB
the turn profile and take the offer** (letter). Independent of A/B/C.

## Profile (the lever's evidence)
Live anchor turns (gpt-5.4-mini extraction, gpt-5.5/HIGH narrator):
- `post_extract` (render extraction) ~31s · `narrate` ~25s · `player_ingest` ~11s ·
  `furnish` ~31s one-time · classify ~4s. Steady-turn wall ~92s.
- Dropping `player_ingest` (option A) ≈ −11s/turn; PB prompt-trim ≈ cuts the per-call
  cost of the remaining extraction(s).

Related: the Cx-022 concealment gate (`turnloop` promotion gate), PB letter 077.
