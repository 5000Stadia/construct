# The chapter bridge, B1: chapter 2 answers what the player did (R36)

**Status:** spec r1, 2026-10-13, for cr review. Not built. It builds on READS-AT-PLAY-HORIZON (merged 17d90eb), and reads R35's report where it lands.
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

### 1. The walk-away becomes reachable (a pending, then a confirm)

- **Detection:** `_fire_event_occurs` also collects, for each arc whose `refusal_clock` is armed and whose `fires_when` is a bare `Occurred(kind)`, the candidate `{kind, what: "the player decisively walks away from <the arc's goal statement>, abandoning it"}`. The detector stays constrained to candidates, as today.
- **A detected walk-away is a PENDING, not an ending.** Ending a chapter is costly and one turn's "I leave" is ambiguous, so the first detection writes `session:abandon_pending` (the arc id and the turn), and nothing else. This is the tangent flow's two-beat shape (pending, then confirm).
- **Before the confirm,** the world shows the cost while the player is still free to turn back:
  - the narrator's briefing carries "the player is walking away from X; let what they're leaving behind be felt, without stopping them";
  - the next pacing nudge leans toward the pillars (memory: player avoidance, move 1).
- **The confirm.** A later detection of the same walk-away, on a turn at least `ABANDON_CONFIRM_GAP` turns after the pending (default 2: Kabe's gate below), commits the event. The event row is `event:abandoned_<turn>` with `kind` set to the refusal clock's kind (so the existing `Occurred` and `clock_pass` fire it unchanged), with `agent` and `caused_by` rows as for any detected event.
- **Turning back** (any achieved beat of that arc, or a detected re-engagement) clears the pending.
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

- **The schema** gains `clues: [{beat_id, holder, reveal_condition}]`, one per new `InFrame(knows:<protagonist>, e, a, v)` beat. The holder is a person at the horizon or a hook-cast id; `reveal_condition` is one of the live conditions (`LIVE_REVEAL_CONDITIONS`).
- **Code builds the episode cast:**
  - the chapter-1 cast nodes, plus new or extended nodes holding these clues;
  - it validates with `validate_beat_delivery` over the new arc's `InFrame` beats against **that** cast;
  - an undeliverable beat is a failed attempt, naming the beat.
- **The data lifecycle** is defined, as cr asked on R35:
  - **Persisted,** in the continuation's single atomic commit, as the slot's `session:episode` · `cast` literal (JSON, like the episode scope, Cx 191), stamped at the chapter's turn time.
  - **Seeded:** the clue rows go into each holder's `knows:` frame, in the same atomic set, by `cast_seed_plan`, never the protagonist's frame.
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

## Tests

1. **Walk-away, pending then confirm:**
   - a stub detector reports the refusal kind on turn 5. That writes `abandon_pending` only, with no event, and the briefing carries the walk-away directive;
   - on turn 6 it's still pending (the gap is 2);
   - on turn 7 a second detection commits `event:abandoned_7` with kind `event:abandoned`, and `clock_pass` then fires the refusal clock.
   - **Turn-back:** a beat achieved on turn 6 clears the pending, so turn 7's detection starts over.
2. **No false end:** a single detection never fires the refusal clock, whatever the turn count (the founder's "turns never close stories" guard stays intact).
3. **Outcome categories:** four receipt fixtures, one each: the refusal end gives `abandoned`; a tangent-adopted main gives `elsewhere`; a terminal location in a grown region outside the scope gives `elsewhere`; grade wrong gives `wrong`; won gives `right`. The order of precedence is tested (refusal beats elsewhere).
4. **Thread accounting:** three threads, with the proposal disposing of two, is a retry whose note names index 2; complete is accepted; the closed threads land in the settled record.
5. **Response check:** a proposal without `responds_to_outcome`, or with only ids absent at the horizon, retries; a grounded one is accepted.
6. **Chapter-2 clue delivery:**
   - a proposal whose new `InFrame` beat has no `clues` entry retries;
   - with a holder present at the horizon, the episode cast is committed atomically, the holder's `knows:` frame holds the fact, and the protagonist's frame doesn't;
   - a reopened Session loads the episode cast, and an ASK of that holder delivers the clue and achieves the beat.
7. **Legacy:** a slot without an episode cast plays exactly as today, and existing continuation tests pass unchanged.
8. **The full suite.**

**Acceptance in play:** the next R20 two-chapter run (it needs Kabe's or the monitor's yes) is judged on R20's chapter-2 criteria plus:
- the receipt's category matches what happened;
- chapter 2's opening visibly answers it;
- no new `InFrame` beat in chapter 2 stays undeliverable.
