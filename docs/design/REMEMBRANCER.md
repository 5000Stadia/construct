# The Remembrancer — the presence of the player's own awareness and memory

**Status:** design draft for the Cx round (founder-proposed 2026-07-03: "something
mechanically analogous to an NPC that does not 'talk' — it serves as a presence of your
awareness and memory"; deferred to HD judgment → greenlit). Queued behind the #96 round.

## The asymmetry it repairs

Every NPC in the engine is a knowledge frame plus agency: `knows:<npc>` is the sheet,
`npc_turn` is the per-beat decision to act or speak. The protagonist's inner life is a
knowledge frame plus NOTHING — `knows:<prot>` is the richest frame in the world (authored
history, intimate ground, learned clues, relationships) but it has no participant. It is
consulted only when a directive begs the narrator to remember it exists.

That agency gap is the root of a whole live-complaint family:
- an NPC answering the player's self-question ("where did I stay prior?" → Julian);
- competence-volunteering firing only when the prompt happens to reach;
- the intimate opening history going silent for the rest of play;
- recall moves ("I think back to when I last saw him alive") landing as generic scene
  re-description instead of memory.

The house lesson applies: mechanism over pleading. Give the frame a turn.

## The shape

**A silent participant in the turn loop, symmetric with `npc_turn`.**

- **Sheet:** `knows:<prot>` (the same snapshot discipline as NPC sheets; horizon-bound).
- **The call** (`memory_turn`, cheap tier): given the sheet, the scene, and the player's
  move — does the character's OWN MIND contribute this beat? Output is never dialogue and
  never action: `{stirs: bool, memory: str, feeling: str}` — a memory surfacing, a
  connection noticed, a felt familiarity/unease grounded in known facts.
- **Delivery:** a briefing block the narrator weaves as second-person interiority —
  `YOUR OWN MIND THIS TURN (weave as felt memory, never a recital): …` — subject to
  PROPORTION (a flicker, not a flashback, unless the player asked).
- **It owns self-questions mechanically.** classify's `uses_protagonist_knowledge` (and
  self-directed question detection) routes the question TO the Remembrancer; its answer
  is the memory's answer. The 2026-07-03 directive fix ("my own memories should answer
  here") becomes structure: the memory answers because the memory got the turn.

## The retcon half — player-declared memory (founder, 2026-07-03)

"Let it be a bit player controlled and engine controlled — almost a bridge of
explanation between player intention and character shape and world explanation."

The player can AUTHOR their character's past in play: *"I remember back to my childhood
times with a friend named John Johnson. I promised I would never let this happen
again."* That declaration is not flavor to be narrated past — it is an authoring move
the engine HONORS:

1. **The memory becomes frame truth.** Declared autobiography commits into
   `knows:<prot>` as ordinary rows (the friend, the promise, the wound) — the same
   doorway as everything else, so the past the player writes is the past the world
   remembers. A declared PERSON of the past (John Johnson) may be admitted as an
   offscene canon person (the hook_cast admission discipline — real, referable,
   findable someday if the story invites him).
2. **The bridge function.** A declared vow or wound is the player TELLING THE ENGINE
   who their character is — "I promised I would never let this happen again" is a
   drive. The Remembrancer reflects it back at charged moments ("you made a promise
   once"); the narrator's character understanding absorbs it; future arcs may build on
   it (the generator's fuel already reads the ledger — declared character shape joins
   it). Player intention → character shape → world explanation, one seam.
3. **Bounded by the improv-authority spectrum, applied to the self.** Ordinary
   autobiography is GRANTED generously (childhood friends, old promises, a trade
   learned, a town left) — the rule-of-cool default. A memory that would mint
   ADVANTAGE ("I remember where the vault key is hidden") or brush protected
   vocabulary gets the same honest treatment as any player fiat: the emotional truth
   is granted, the load-bearing fact is not ("you remember hunting for it, never
   finding it"). Same screens, same doorway, no new authority.
4. **Append-only like all truth — with the contradiction check (founder, 2026-07-04).**
   "I think back to my childhood home in Lancaster" establishes Lancaster as truth —
   the engine respects it — UNLESS it contradicts what is already true. If Westminster
   was declared (or authored) as the childhood home earlier, the second declaration is
   NOT silently granted: mechanically, the self-fact flows through the same gated
   ingest that quarantines contradictions of established canon values; render-side, the
   narrator honors the established truth and lets the player RECONCILE ("Lancaster?
   Your boyhood was Westminster — unless the Lancaster years came after your father
   moved"). Two childhood homes are possible — but the player has to specify; an
   unexplained clash is a straight contradiction and truth wins. The player's own past
   gets exactly the world's continuity discipline: generous to grant, honest to hold.

## Gates (cost + craft discipline — the world-tick pattern)

Fires ONLY on:
1. Self-questions and recall moves (the classify flag; "I think back…") — always.
2. Scene entry where a `knows:<prot>` row touches the NEW place or a newly-present
   person (arriving somewhere you have history FEELS like something) — deterministic
   pre-check on the frame before any model call.
3. Otherwise: rarely and never twice running (a session-frame last-stirred marker, the
   world-tick's elapsed discipline).
Suppressed during: the grounding runway's first beat is EXEMPT from suppression (memory
is exactly what the runway is for) but terminal flow uses the epilogue's own machinery.
Fail-open everywhere; a missed stir costs nothing.

## Truth bounds (the usual teeth)

- It knows ONLY the frame. Protected keys + concealed vocabulary screened on output —
  it deepens the past, never leaks the answer or manufactures load-bearing facts.
- Ordinary autobiographical elaboration follows the same improv rules as the narrator's
  ordinary-detail license (a remembered smell is free; a remembered CLUE is not unless
  the frame holds it).
- Its contributions are BRIEFING material, not canon writes — memory colors the render;
  the post-extract gate treats any resulting prose exactly as it treats all narration.

## What it unifies (retire-on-arrival candidates)

- PROTAGONIST_COMPETENCE's volunteering clause → becomes its floor behavior.
- The self-questions-answer-inward directive (both sites) → becomes its routing.
- The intimate-ground opening rows (geography-of-self) → become its richest material,
  alive all game instead of opening-only.
- The narrative-memory ledger's recent window → a candidate second sheet (what happened
  EARLIER THIS STORY is also "your memory") — design question below.

## Open questions for Cx

1. Sheet composition: `knows:<prot>` only, or ∪ the narrative-memory ledger (episode
   history is also memory — but it's host-frame, larger, and the transcript window
   already feeds the narrator; my lean: knows-frame only in v1, ledger via one compact
   "the story so far" line).
2. Fold into the existing npc_turn parallel batch (one more concurrent cheap call on
   gated turns) vs a separate phase — my lean: same batch, same latency discipline.
3. Should the notebook (#83) and the Remembrancer share a formatter seam (the same rows,
   one read as case-board, one as felt memory)? My lean: no code sharing beyond the
   frame read — different registers.

## Relation to the whole

This is the live-play descendant of the founder's original "pinned awareness" element
(AWARENESS-AND-SHAPE element 1) and the mechanism behind synthesis pillar 2 (the
player's story is the story): the character's own life becomes a presence in the room.

## As built (Cx 434 constraints folded, 2026-07-04)

- **Signals** (constraint 1): classify gains `recalls` (the deliberate memory reach)
  and `declares_memory` (the recall ASSERTS new autobiography) — `asks_self` untouched.
- **Gate** (constraint 2): `memory_turn` fires on `asks_self | recalls |
  declares_memory | uses_protagonist_knowledge`, action/question kinds only — never a
  generic look-around.
- **`construct/remembrancer.py`**: `build_sheet` (the SCREENED `knows:<prot>` digest —
  journal-discipline concealment: build-stamped protected/leaking rows never reach the
  call; earned-in-play rows show; horizon-bound; 40 rows freshest-last) and
  `commit_declared_memory` (the retcon authority layer).
- **Commit rules** (constraints 3-5): self claims → protagonist rows in `knows:<prot>`;
  world claims → `believes_*` rows on the PROTAGONIST (never a world entity — can never
  satisfy coverage or license a protected key); protected/concealed values screened at
  STORAGE time (the game.py relationship-seeding precedent); attribute collisions
  (canon first, then prior declarations) quarantine — the first value stands, the
  tension returns as a briefing line ("THE MEMORY SITS ODDLY") and rides `memory_turn`.
  Named past people pass `resolve.is_proper_named` → minimal OFFSCENE canon stub
  (kind/name/role, never `in`) + a player-frame relationship row.
- **Ordering** (constraint 6): a declaration commits FIRST (serial, the mind reacts to
  the new autobiography), then `memory_turn` rides the SAME cheap parallel batch as
  `npc_turn` (or runs alone in an empty room). Output = `{stirs, memory, feeling}` —
  interiority only; the briefing block ("YOUR OWN MIND THIS TURN") demands a flicker,
  not a flashback, never dialogue or action. `TurnTrace.memory` is the debug surface.
- **StubProvider default** (the #88A csg precedent): unstubbed `rmb`/`mcl` calls answer
  silent defaults without consuming legacy test queues. The turn tag is `rmb`, NOT
  `mem` — narrative-memory compaction owns `mem` (Cx 439 #2).
- **Declaration kind accepted** (Cx 439 #1): the most literal retcon parse
  (`kind=declaration` + `declares_memory`) is exempt from the canon-strict
  declaration denial — the player's own past is theirs to author through the
  guarded channel; it then flows on as an ordinary in-world beat. Non-memory
  world-fact declarations stay denied.
