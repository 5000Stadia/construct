# The chapter bridge, B1: chapter 2 answers what the player did (R36)

**Status:** spec r3, 2026-10-13, for cr review. Not built.

**r2 (cr RED on r1):**
- each arc's walk-away gets its own event entity;
- a pending walk-away has a bounded confirmation window and clearing rules;
- every episode-cast and seeded-clue row carries the chapter's turn time, so the horizon view sees it;
- the delivery check covers every `InFrame` beat on the protagonist, optional ones included.

**r3 (cr RED on r2):** two delivery-path mismatches.
- **Person holders can only use `none` or `pressure`.** The ASK path calls `revealable_clues(node, pressure=…)` and never passes `examined`/`scrutiny`; those are EXAMINE-only, for object and site holders.
- **Reachability is judged at the horizon.** `_reachable_nodes` reads the authored `presence`/`location`, which go stale over chapter 1. So the episode cast's nodes are **re-derived from the world at `h`** before validation. It builds on READS-AT-PLAY-HORIZON (merged 17d90eb), and reads R35's report where it lands.
**Source:**
- Kabe's plan item B, approved 2026-10-13 ("Sounds good on A and B"), from his Picard-noir example: the outcome (right, wrong, abandoned, elsewhere) causally drives the next chapter.
- The founder's refusal directive, 2026-06-23 (memory: player-avoidance-and-refusal-conclusion).
- Two defects found in R35's review.

## What exists (and stays)

**At conclusion,** an outcome receipt on `session:main` (turnloop.py:6800-6830):
- `kind` arc_won / arc_lost (death has its own path);
- `grade` (right / wrong / partial / pyrrhic, from the commitment grade);
- `outcome_shape` and `basis` (from the conclusion cohort);
- `terminal_location`.

A hollow or wrong landing also writes a concrete canon consequence (COMMITMENT-AS-EFFECT slice 3).

**`continue_episode`** (game.py) then:
- reads the chapter memory, under the horizon view since 17d90eb;
- closes the answered questions as settled history;
- extracts personal threads with one model call, and tells the author to "honor or pay off" each;
- surfaces one consequence callback;
- feeds the grown regions in;
- asks `generate_arc` for the next arc;
- writes the opening directive from the graded shape (`_continuation_intro`: "a wrong close travels as a stain").

## The gaps

1. **The walk-away ending can't fire (a defect).**
   - Every generated arc's refusal clock fires on `Occurred("event:abandoned[_<arc>]")` (arc/build.py:144-149, arc/io.py:381-389), and **nothing writes that event**.
   - The event detector (`_fire_event_occurs`, turnloop.py) collects candidates only from beats, and the tangent-cancel path writes a session record only.
   - So the founder's refusal conclusion ("they endlessly escape … a conclusive scene still reaches them") never happens in a generated story, and "abandoned" is not a recordable outcome.
2. **"Elsewhere" has no category.**
   - Run 10's player escaped out of a window into a street the world grew. Tangent adoption already replaces the main arc when the player's own direction is confirmed.
   - Neither is named in the receipt, so the next chapter can't tell "solved it" from "went off and did something else".
3. **Promises are asked for, never checked.** The author is told to honor each personal thread; nothing verifies it did.
4. **Nothing checks that chapter 2 responds to the outcome.** The opening directive asks for a bridge, and a chapter that ignores the ending passes.
5. **Chapter 2's new clues have no deliverer (a defect).**
   - `continue_episode` authors no cast, and Session loads the scenario's chapter-1 `meta["cast"]` (session.py:205).
   - A chapter-2 `InFrame(knows:<protagonist>, …)` beat whose fact no chapter-1 clue carries can't be delivered by ASK or EXAMINE, and the beat can't be achieved.
   - R35 reports it; B1 fixes it.

## The changes

> **Superseded (2026-10-13):** change 1 below was never built. Kabe's note n54b973 (intent, not a turn count) and his intent ruleset (IR-16: abandonment is never inferred) replace it with `WALK-AWAY-DECLARED.md` (R40). It's kept here as the reviewed record.

### 1. The walk-away becomes reachable (a pending, then a confirm)

- **Detection:** `_fire_event_occurs` also collects, for each arc whose `refusal_clock` is armed and whose `fires_when` is a bare `Occurred(kind)`, the candidate `{kind, what: "the player decisively walks away from <the arc's goal statement>, abandoning it"}`. The detector stays constrained to candidates, as today.
- **A detected walk-away is a PENDING, not an ending.** Ending a chapter is costly and one turn's "I leave" is ambiguous, so the first detection writes `session:abandon_pending` (the arc id and the turn), and nothing else. This is the tangent flow's two-beat shape (pending, then confirm).
- **Before the confirm,** the world shows the cost while the player is still free to turn back:
  - the narrator's briefing carries "the player is walking away from X; let what they're leaving behind be felt, without stopping them";
  - the next pacing nudge leans toward the pillars (memory: player avoidance, move 1).
- **The pending is per arc:** `session:abandon_pending_<arc slug>`, holding the turn of the first detection.
- **The confirm.** A second positive detection of the same arc's walk-away commits the event, if it falls in the confirmation window: at least `ABANDON_CONFIRM_GAP` turns after the pending (default 2: Kabe's gate below) and at most `ABANDON_WINDOW` turns after it (default 6).
  - **The event entity** is unique per arc and turn: `event:abandoned_<arc slug>_<turn>` (the main arc's slug is `main`).
  - **Its `kind`** stays the refusal clock's existing kind (`event:abandoned` for main, `event:abandoned_<slug>` for a side arc), so `Occurred` and `clock_pass` fire it unchanged.
  - It gets `agent` and `caused_by` rows, as any detected event does.
  - Main and a side arc detected in one action write two entities, and each fires only its own clock.
- **What clears a pending:** any of the following clears it, and a later detection then starts a **new** pending rather than confirming:
  - the window passing with no second detection (the pending's age is past `ABANDON_WINDOW`);
  - any beat of that arc achieved;
  - a detected re-engagement. While a pending stands, the detector also gets the candidate `{kind: re_engages:<arc>, what: "the player turns back toward <goal>"}`, and a positive detection of it is a clearing, not an event.

  So two unrelated leavings far apart never combine into an ending, and an ending always takes two positive detections inside one window.
- **What follows is unchanged:** the refusal clock's effect writes `refusal_conclusion`, and the conclusion path runs as designed.

### 2. One outcome category on the receipt

`outcome_category` is written beside `grade` on the outcome receipt, computed by code from facts already recorded, in this order:

| Category | When |
|---|---|
| `abandoned` | the chapter ended through the refusal clock (change 1) |
| `elsewhere` | the main arc at the end was adopted from a tangent (the player's own direction, recorded by tangent adoption), **or** the terminal location lies in grown territory outside the arc's scope at its ending |
| `wrong` | `grade` is `wrong`, or `outcome_shape` is failure / quiet_failure |
| `right` | otherwise, on arc_won (with `partial` and `pyrrhic` kept as shades from `grade`) |

- `continue_episode` reads it with the shape receipt.
- `_continuation_intro` and the generator's trigger name the category plainly ("the player abandoned the case", "the player went elsewhere: <the adopted tangent's goal / the region>").
- **Death** keeps its own permanence path; there is no chapter 2.

### 3. Promises accounted for

- `generate_arc`'s schema gains `thread_disposition`: one entry per personal thread, by index, `{index, disposition: carried | closed, how}`.
- **Code checks completeness:** every thread index appears exactly once, and a `carried` one names an id or beat in the new arc. An incomplete set is a failed attempt in the existing 3-attempt loop, with the missing indices in the retry note.
- The `closed` ones join the settled-history record (as "closed by the author: <how>"), so they're visible to the next chapter and the notebook.
- **Zero threads** means no requirement.

### 4. The new chapter must respond to the outcome

- The schema gains `responds_to_outcome: {how, ids}`.
- **Code checks only that it exists and is grounded:** `how` is non-empty, and at least one of `ids` is an entity at the horizon (through the view) **or** a hook-cast id, and appears in the new arc (a beat referent or the hook cast). A missing or ungrounded answer is a failed attempt, with the note "the next chapter must answer the outcome: <category>".
- **It never dictates the shape:** a delayed or quiet answer is valid ("the real culprit grows bolder, offstage").

### 5. Chapter-2 clues get deliverers

- **The schema** gains `clues: [{beat_id, holder, reveal_condition}]`, one per new `InFrame(knows:<protagonist>, e, a, v)` beat, **required or optional**.
  - **The holder** is a person (`person:`) at the horizon, or a hook-cast id.
  - **`reveal_condition` is `none` or `pressure` only (r3):** the two conditions the ASK path (`revealable_clues(node, pressure=…)`) can satisfy for a person. `examined` and `scrutiny` are EXAMINE-only, for object and site holders, which B1 doesn't author.
  - Any other value is a failed attempt, naming the clue.
- **Horizon re-derivation (r3).** Before validation, every node in the episode cast, carried over from chapter 1 or new, gets its `location` and `presence` recomputed from the world at `h`, through the view:
  - `location = locate(node)[0]`, or none;
  - `presence = at_scene` if that location is the doorway place, `nearby` if the node has any location, `offscene` if it has none;
  - a hook-cast holder is staged at the doorway place (its staged `in` row), so it's `at_scene`.

  The authored chapter-1 values aren't trusted for chapter 2. A holder who moved during chapter 1 is validated (and persisted) where they actually are; a holder with no location at `h` is unreachable unless a live clue names them, as `_reachable_nodes`' discovery chain already allows.
- **Code builds the episode cast:**
  - the chapter-1 cast nodes, plus new or extended nodes holding these clues;
  - it checks delivery for **every** `InFrame` beat on the protagonist's frame, required **and** optional: an exact-match clue, with a live reveal condition, on a holder that is physically reachable (`_reachable_nodes`) and able to act at the horizon. `validate_beat_delivery` (today: required beats only) gains an `include_optional` flag for this.
  - an undeliverable beat of either weight is a failed attempt, naming the beat. An optional beat nobody can deliver is dead content, so it's the same policy.
- **The data lifecycle** is defined, as cr asked on R35:
  - **Persisted,** in the continuation's single atomic commit (`commit_set` already spans the plot, session, canon and `knows:` frames), as the slot's `session:episode` · `cast` literal (JSON, like the episode scope, Cx 191).
  - **Seeded:** the clue rows go into each holder's `knows:` frame, in the same atomic set, by `cast_seed_plan`, never the protagonist's frame.
  - **Timestamps (r2):** every episode-cast literal and every seeded `knows:<holder>` item gets `valid_from = turn_time(turn)`, the chapter's boundary stamp that the other continuation rows already carry. `cast_seed_plan` emits untimed items today; untimed, they would land outside the play band's view, so a reopened horizon Session would never see them.
  - **Read:** Session prefers the slot's episode cast over the scenario `meta["cast"]`, exactly as it already prefers the slot's episode scope. Legacy and first-chapter slots have none, and keep today's behaviour.
- **R35's continuation report** then reads this cast too.

## Not in B1

- **The consequence rehearsal** (a copy of the world, R35's pass before and after). That's B2 (R37), only if B1's runs show chapter 2 still misreading what changed.
- **Choosing the next chapter's genre or location pivot** (the refusal directive's move 3). The generator's trigger already carries "where they went"; a dedicated pivot is a later item.

## A decision for Kabe (reversible; there's a default)

**How firm must a walk-away be before it ends the chapter?**
- **The default:** a second detection at least **2 turns** after the first, with the world showing the cost in between.
- **Shorter:** 1 turn. More responsive, more risk of ending on a misread.
- **Longer:** 3+ turns, or "3 detections". Harder to walk away, closer to "never stonewall".

The confirmation window (`ABANDON_WINDOW`, default 6 turns) is mine to tune. It only stops two unrelated leavings, far apart, from combining into an ending.

## Tests

1. **Walk-away, pending then confirm:**
   - a stub detector reports the main refusal kind on turn 5. That writes `abandon_pending_main` only, with no event, and the briefing carries the walk-away directive;
   - on turn 6 it's still pending (the gap is 2);
   - on turn 7 a second detection commits `event:abandoned_main_7` with kind `event:abandoned`, and `clock_pass` then fires the main refusal clock.
   - **Turn-back:** a beat achieved on turn 6 clears the pending, so turn 7's detection starts a new pending.
   - **Re-engagement:** a positive `re_engages:main` on turn 6 clears it the same way.
2. **No false end:**
   - a single detection never fires the refusal clock, whatever the turn count (the founder's "turns never close stories" guard stays intact);
   - **(r2) stale pending:** a detection on turn 5, nothing for 10 turns (past `ABANDON_WINDOW`), then one detection on turn 16. Turn 16 starts a new pending, and there's no abandonment event.
2b. **(r2) Two arcs, one action:** main and a live side arc are both pending, and are both re-detected on the same confirming turn. Two distinct entities, `event:abandoned_main_<t>` and `event:abandoned_<side>_<t>`, are written, with kinds `event:abandoned` and `event:abandoned_<side>`. Each refusal clock fires once; no other clock fires.
3. **Outcome categories:** four receipt fixtures, one each: the refusal end gives `abandoned`; a tangent-adopted main gives `elsewhere`; a terminal location in a grown region outside the scope gives `elsewhere`; grade wrong gives `wrong`; won gives `right`. The order of precedence is tested (refusal beats elsewhere).
4. **Thread accounting:** three threads, with the proposal disposing of two, is a retry whose note names index 2; complete is accepted; the closed threads land in the settled record.
5. **Response check:** a proposal without `responds_to_outcome`, or with only ids absent at the horizon, retries; a grounded one is accepted.
6. **Chapter-2 clue delivery, on a horizon world** (r2):
   - a proposal whose new `InFrame` beat has no `clues` entry retries;
   - with a holder present at the horizon, the episode cast is committed atomically, every episode-cast and seeded `knows:` row has `valid_from = turn_time(turn)`, the holder's frame holds the fact, and the protagonist's frame doesn't;
   - a reopened Session on that **horizon** slot (`opening_as_of` set, reading through its HorizonView) loads the episode cast, and an ASK of that holder delivers the clue and achieves the beat;
   - **negative control:** with the seed items untimed (the old `cast_seed_plan` output), the reopened Session can't see the holder's fact.
6b. **(r2) Optional beats:** an optional `InFrame` beat whose holder is unreachable (offscene, with no naming chain) is a failed attempt naming that beat. With a reachable holder it's accepted.
6c. **(r3) A person holder with a non-ASK condition:** a proposal whose person-held clue has `reveal_condition: examined` is a failed attempt naming the clue. `pressure` is accepted, and on the reopened horizon Session, pressing the holder delivers it.
6d. **(r3) Stale chapter-1 metadata:**
   - **Setup:** a horizon slot whose `meta["cast"]` records `person:witness` as `at_scene` in `place:study`, while at `h` the witness is `in place:docks` (moved during chapter 1).
   - The new arc's clue held by the witness validates with the re-derived node (`nearby`, `place:docks`), and the persisted episode cast records `place:docks`.
   - On the reopened Session, the player moves to the docks, asks, and the beat is achieved.
   - **Variant:** the witness has **no** location at `h`, and no live clue names them. The proposal retries with the note "holder person:witness is not reachable at the horizon".
7. **Legacy:** a slot without an episode cast plays exactly as today, and existing continuation tests pass unchanged.
8. **The full suite.**

**Acceptance in play:** the next R20 two-chapter run (it needs Kabe's or the monitor's yes) is judged on R20's chapter-2 criteria plus:
- the receipt's category matches what happened;
- chapter 2's opening visibly answers it;
- no new `InFrame` beat in chapter 2 stays undeliverable.
