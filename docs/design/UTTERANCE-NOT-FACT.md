# Utterance is not fact: what the player's character says never becomes canon by saying it (R42, first slice)

**Status:** spec r2, 2026-10-13, for cr review. Not built.

**r2 (cr RED on r1):**
- It fails closed: an unknown classification strips speech.
- A deterministic quote scanner, single quotes and unmatched quotes included.
- The addressees come from the existing addressed set.
- A reserved event kind that can't collide with, or satisfy, an authored event.
- Only the player-input factual extraction is prohibited: clue delivery and other interaction paths are untouched.
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

**Missing or unknown counts as `mixed` (r2: fail closed).** Spoken text is stripped by the scanner (rule 2), and what's left is extracted as today. Legacy and stub lines with no quotes extract exactly as before; a quoted lie in an old-shaped response no longer lands.

**2. Speech is never extracted.** At the player-input extraction (turnloop.py:4717):
- **`speech`:** no extraction at all. The trace records `player_ingest (speech: an utterance, not a fact)`.
- **`mixed` (or missing):** spoken spans are removed before extraction by one deterministic scanner, `strip_speech(text)`. It scans left to right:
  - **Openers** are `"`, `“`, `«`, `‘`, and an ASCII `'` only at a word boundary: at the start, or after whitespace or `(—–-:,;`, and followed by a non-space. So the apostrophes in `don't` and `Quincy's` never open.
  - **Each opener closes on its own partner,** and only that: `"`→`"`, `“`→`”`, `«`→`»`, `‘`→`’`, `'`→`'` followed by end, whitespace or punctuation.
  - **Nesting:** the outermost span wins. Inner quotes are part of it.
  - **An unmatched opener strips to the end of the line** (fail closed: the rest is treated as speech).
  - What's left goes through today's path. **A line that is only quotes leaves nothing to extract,** so there's no extraction call.
- **The named residual gap:** reported speech **without** quotes inside a mixed line ("…and tell him Ellis cooked it") can still reach extraction. It's covered by a test that pins today's behaviour, so a later fix shows up, and by a critic-campaign probe.
- **`act`:** unchanged.
- **This holds in every authority mode.** In coauthor mode, a **declaration** (`kind == "declaration"`) still authors facts as today; that's the mode's contract. Dialogue spoken to a character is an in-world utterance in any mode (the ruleset's IR-6: the least-authoritative reading the mode allows).

**3. The utterance commits as a speech event.** On a turn where the line includes speech (`claims_are` is `speech` or `mixed` and the scanner found a span, or `claims_are` is `speech`), canon gets one event:
- **Identity (r2):** `event:said_<turn>`, with `kind` = the **reserved** kind `player_speech`.
  - `_fire_event_occurs` never offers a reserved kind as a candidate.
  - `_build_arc` refuses an authored `event_occurs` beat whose kind is reserved: a failed attempt, retried as any unbuildable proposal is.
  - So a speech event can neither collide with an authored event (`event:<kind>_<turn>`) nor satisfy an authored `Occurred` beat. Speech never becomes a world occurrence.
- `agent` = the protagonist.
- **`patient` (r2)** = each id in `_addressed_this_turn`, the deterministic addressed set run_turn already computes (sole-present plus the classifier signal, the vocative, name matching). It's written **after** that set is computed. An empty set means no patient rows. An ambiguous set is whatever that computation already decides, unchanged.
- `content` = the scanner's spoken spans, joined, else the whole line for `speech`, trimmed to 300 characters, as a literal.

It's a fact that something was **said**, never that what was said is **true**.

**What this slice prohibits is only the player-input factual extraction of speech.** Clue delivery (ASK), player-frame learning, NPC turns and every other deterministic interaction consequence of dialogue run exactly as today.

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
5. **Legacy (r2: fail closed):** a verdict without `claims_are` on an unquoted act line extracts exactly as today, and the existing player-input extraction tests pass unchanged. On a line with a quoted lie, the lie is stripped.
5b. **(r2) The scanner:**
   - single-quoted dialogue (`I hand Quincy the ledger and say 'Ellis cooked the numbers.'`) is stripped;
   - apostrophes (`I take Quincy's ledger; don't move`) are kept;
   - an unmatched `"` strips to the end;
   - nested `"he said 'no'"` is one span;
   - a quote-only line makes no extraction call;
   - a quoted question is stripped;
   - quotes around an action with `claims_are=act` take today's path, unstripped.
5c. **(r2) Addressees and delivery:**
   - two present NPCs with only one addressed gives exactly one patient row;
   - no addressee gives none;
   - an interrogating line ("'Where were you at nine?' I ask the clerk") still delivers an authorized clue through ASK, as today.
5d. **(r2) No collision:** a pending authored `Occurred("utterance")` beat, and a speech turn on which the detector also fires it. That gives `event:said_<t>` (kind `player_speech`) and `event:utterance_<t>` (the authored kind), with no shared rows, and the speech event doesn't achieve any beat. `_build_arc` rejects an authored `player_speech` event kind.
5e. **(r2) The named gap, pinned:** unquoted reported speech in a mixed line ("…and tell him Ellis cooked it") still reaches extraction today. The test pins that, so a later fix shows up.
6. **Coauthor declaration:** in coauthor mode, a `kind == "declaration"` line still authors as today.
7. **The full suite.**
