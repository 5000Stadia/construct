# Utterance is not fact: what the player's character says never becomes canon by saying it (R42, first slice)

**Status:** spec r1, 2026-10-13, for cr review. Not built.
**Source:**
- IR-5 of Kabe's intent ruleset ("utterances commit as speech events; a lie, confession or claim changes listeners' beliefs, never canon").
- The F6 finding, verified while adopting the ruleset (`INTENT-RULESET.md`).

## The facts

- **Classify counts in-character speech as an action** (cohorts.py:2680-2689). Its own example is the bare line `'Tovan didn't steal anything.'`.
- **The claims flag sends speech to extraction.** `asserts_or_reveals` is "true if this input could ESTABLISH or CHANGE a world fact … makes a claim … When UNSURE, say true" (cohorts.py:162-169). When it is set, the player's line is extracted and ingested into canon (turnloop.py:4717-4790).
- **What the extraction filters today:** only questions (`_declarative_part`) and `knows:`-framed rows (`_partition_frames`).
- **So a spoken claim becomes world truth.** Said aloud to someone, "Tovan didn't steal anything" or "Ellis was at the docks that night" can land as canon facts, a lie included.
- **The pure-mode declaration denial** (turnloop.py:4631) covers `kind == "declaration"` only. Speech is `kind == "action"`, so it passes.
- **Player speech never reaches `knows:<npc>`:** those rows are dropped, since the knowledge-promotion gate isn't built. NPCs answer speech through recent dialogue in their turn context, not through canon.

## The rule

**1. Classify reports what the line's claims are.** CLASSIFY_SCHEMA gains `claims_are`:
- `act`: the claims describe what the character does or changes in the world ("I pocket the key", "I bar the door");
- `speech`: every claim is something the character SAYS: dialogue, telling, accusing, lying, answering ("'Tovan didn't steal anything.'", "I tell Quincy Ellis was at the docks");
- `mixed`: both ("I hand Quincy the ledger and tell him Ellis cooked it").

Missing or unknown counts as `act`, so legacy behaviour holds for old and stub responses.

**2. Speech is never extracted.** At the player-input extraction (turnloop.py:4717):
- **`speech`:** no extraction at all. The trace records `player_ingest (speech: an utterance, not a fact)`.
- **`mixed`:** quoted spans are removed deterministically before extraction: text inside `"…"`, `“…”` and `«…»` (not single quotes, which collide with apostrophes). What's left goes through today's path.
  - **Residual risk, named:** reported speech without quotes inside a mixed line ("…and tell him Ellis cooked it") can still reach extraction. R42's later slice (stated intents in the briefing, and the narration checks) doesn't close it either. It's recorded as a known gap, and the critic campaign is to probe it.
- **`act`:** unchanged.
- **This holds in every authority mode.** In coauthor mode, a **declaration** (`kind == "declaration"`) still authors facts as today; that's the mode's contract. Dialogue spoken to a character is an in-world utterance in any mode (the ruleset's IR-6: the least-authoritative reading the mode allows).

**3. The utterance commits as a speech event.** On a turn where the line includes speech, canon gets one event:
- `event:utterance_<turn>` with `kind` `utterance`;
- `agent` = the protagonist;
- `patient` = each addressed present character (from `addresses_present`, when set);
- `content` = the spoken words, from the quoted spans, else the whole line, trimmed to 300 characters, as a literal.

It's a fact that something was **said**, never that what was said is **true**. It gives later slices (an NPC belief path, consequences computable from speech) an honest anchor. No other row is written.

## Not in scope

- **NPC beliefs formed from what the player says** (the knowledge-promotion gate, RFC-002). That's a later slice; today NPCs answer from recent dialogue.
- **The narration checks and stated intents in the briefing** (R42's next slice).

## Tests

1. **A bare spoken claim:**
   - **Setup:** "'Tovan didn't steal anything,' I tell the warden." with `claims_are=speech`.
   - There's no extraction call (the stub extraction queue is untouched), and no canon row about Tovan's theft.
   - `event:utterance_<turn>` exists, with the warden as patient and the words as content.
2. **A lie:** "I tell Quincy, 'Ellis was at the docks that night.'" adds no canon `Ellis · in · docks`, and the utterance event holds the words.
3. **Mixed:** "I slide the ledger to Quincy. 'Ellis cooked these numbers.'"
   - The extraction input is the line without the quoted span.
   - The ledger's movement is extracted as today.
   - Nothing about Ellis cooking numbers lands.
4. **Act unchanged:** "I bar the door with the plank" is extracted as today.
5. **Legacy:** a verdict without `claims_are` behaves exactly as today. The existing player-input extraction tests pass unchanged.
6. **Coauthor declaration:** in coauthor mode, a `kind == "declaration"` line still authors as today.
7. **The full suite.**
