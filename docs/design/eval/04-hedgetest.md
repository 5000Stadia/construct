# Eval 4/5 — hedgetest ("A Death at Brackenmere") — probes ON, 18 turns
Log: logs/harness-1782956121.md · win_loss whodunit fixture

## Verdicts
- **Machinery: WORKED until the last step.** 3 clues delivered (herring, alibi, means), pacing
  climbed to sustained `confront`, cast held. Whodunit spine functional.
- **CRITICAL FAILURE at the climax:** the turn-18 conclusory accusation CRASHED —
  `cannot declare semantics for attribute 'took' after folded data already exists (a:952)` →
  SESSION DEGRADED. The player's climactic move produced an extraction attribute (`took`) whose
  durability semantics were declared too late; PB correctly raised; the TURN SANK.
  **No conclusion, no ch2 leg.**

## Clunk inventory
| # | Finding | Attribution |
|---|---|---|
| H1 | Turn-sinking PB declaration error at the climax | **SCAFFOLDING ×2:** (a) hedgetest was authored WITHOUT Construct's `attribute_default` semantics hook (the known raw-World fixture hazard — same as test_raw_authored_world_without_semantics_hook); (b) ROBUSTNESS GAP: a late-declaration `ingest` error must be fail-open (drop the offending row, ship the turn) — the player-facing turn must never die to a bookkeeping raise |
| H2 | Conclusion unreached in 18 turns (agent committed only at t18, which crashed) | consequence of H1 |

## Elements evidence
- Neutral on #83/#84/#85 (run truncated by H1).
- **#88 evidence indirectly:** the single most fragile moment in the whole engine is the
  conclusory turn — it deserves the most protection and currently has the least.
