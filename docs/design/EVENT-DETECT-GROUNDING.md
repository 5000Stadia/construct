# An authored event fires only when its own act happens (R20 run 13)

**Status:** spec r1, 2026-10-14, for cr review. Not built.

**Source:** R20 run 13 (eval/12, "Why R20 is not closed"), archived at `/media/k/Blank/construct-scratch/run13`.

## The finding

Run 13's chapter 1 has one required climax beat, `beat:pay_the_rivers_timetable`, achieved by `Occurred("fog_bell_window_taken_at_lower_chain")`. In the authored story, the lower chain is the river boom at `place:lower_chain_tower`: during the fog-bell watch it is "blind for twelve minutes", Hobb drops it, and the laundry barge passes. At turn 9 the player, in `place:dark_runoff_lane`, wrote: "I let the snag take me down hard, twisting my left wrist under the chain … and grind the bright-worn link against the cracked drain-lip". The detector fired the kind, the beat was achieved, and chapter 1 concluded with the player still shackled inside Ironhold. Chapter 2's author then wrote the river escape the beat stood for ("The black river bought you time … Enough mornings have passed"), with the chain whole again, against canon (`obj:chain condition broken, whole false`). The critic filed that three times.

What the detector is given today (`_fire_event_occurs`, `turnloop.py`; `cohorts.detect_events`):
- the player's raw input;
- the resolved tier;
- each candidate as `{"kind": k, "what": k.replace("_", " ")}`.

Nothing says what the authored event is, where it happens or with what. The beat schema has no field for it: an `event_occurs` beat's only content is its slug. "Fog bell" and "chain" in the slug, and a chain in the action, were enough.

## The rule

**An authored event carries its meaning, and the detector judges the action against that meaning and the place the player stands.**

1. **Authoring.** Both beat schemas (the main arc's `ARC_SCHEMA` in `arc/build.py` and `GEN_ARC_SCHEMA` in `cohorts.py`, which both feed `build.py`'s single `Beat(...)` construction) gain a `what` string:
   - for `event_occurs`, one plain sentence naming the act and what makes it this act: the place, the object, the people, in the story's own names ("Hobb drops the lower chain, the river boom at the lower chain tower, during the fog-bell blind window, and the barge carrying the protagonist passes");
   - for `player_learns`, the empty string.
   It is `required` in the JSON schema (strict mode needs every property), with `""` allowed.
2. **The beat.** `Beat` gains `what: str = ""`. `_beat_rows` writes a timeless plot row `(beat, "what", text)` only when the text is non-empty, so a beat without it is byte-shaped as today. Both loaders (`arc_from_frame` and `beat_from_reads`) read it back, with a missing row as `""`. It lives in the plot frame like every other beat row: never canon, never in the narrator's prompt. The arc cache (`arc_to_cache`/`arc_from_cache`) carries it as an optional key, absent when empty, and a drift repair's replacement beat keeps it, since the replacement keeps the dead beat's own condition.
3. **The detector's candidates.** `_fire_event_occurs` sends `what = beat.what` when non-empty, else today's de-slugged kind. A world built before this change keeps working as it does.
4. **The place.** `_fire_event_occurs` takes the scene's name as the briefing resolves it (the PLACE-NAME-ANCHOR name, from the player frame), and `detect_events` shows it: "THE PLAYER IS AT: <name>". With no name, the line is left out.
5. **The prompt rule** in `detect_events`, added to the strictness paragraph: "An event happens only when the action is the act described: with the things, the people and at the place the description names. The same word for a different thing (another chain, another door, another key) is not the event. If the description names a place and the player is somewhere else, it did not happen unless the description says it can be done from afar."
6. **Unchanged:** success tiers only; candidates are pending beats only; the result is constrained to the listed kinds; any failure is fail-open (no event).

## Why this shape

- **The fault is missing meaning, not a weak model.** The cheap tier answered the question it was asked: does this action match "fog bell window taken at lower chain"? Giving it the authored sentence asks the right question.
- **The model judges, not a rule.** A deterministic "must be at the named place" gate would refuse events that are done from a distance (a lantern shown across water, a shout from the wall). The place is evidence the detector weighs, and the description can say "from afar".
- **It is cheap:** no new call. One authored sentence per event beat, and a longer candidate line.
- **The secrecy line holds** (Kabe's beats threat model): `what` lives in the plot frame and is read only by the detector's backend call. It never reaches the narrator or a character's prompt.

## Not in scope

- **The continuation opening's end state.** Chapter 2's opening should be written from canon's end state (the player's condition and what they carry, and the time that actually passed), not from the arc's intended ending. That is a separate spec; this one removes the false ending that misled it.
- Backfilling `what` into worlds built earlier. They keep the slug.
- `failure_when` event kinds. They go through the same detector only for declared loss kinds, and their meaning is the loss event's slug; the same field can be added there later if a run shows a false loss.

## Tests

1. **Authoring round-trip:** a proposal with an `event_occurs` beat carrying `what` builds a `Beat` with it. `_beat_rows` writes the row; `arc_from_frame` and `beat_from_reads` read it back equal.
2. **Byte-shape:** a beat with `what=""` writes exactly today's rows (no `what` row). The arc golden doesn't move.
3. **Old world:** a sealed arc with no `what` rows loads with `what == ""`.
4. **Detector candidates (spy):** with `what` present, the candidate line is the authored sentence; without it, the de-slugged kind.
5. **The place (spy):** the detector prompt carries "THE PLAYER IS AT: dark runoff lane" when the player frame names the scene, and no such line when it doesn't.
6. **The rule (spy):** the strictness paragraph includes the same-word-different-thing and named-place sentences.
7. **Schemas:** both beat schemas list `what` in `properties` and `required`, and validate a proposal with `what: ""` for `player_learns`.
8. **Fail-open:** a detector that raises fires nothing, and the turn completes (as today).
9. **The run 13 case, measured, not asserted:** replay turn 9's detector call on the subscription with the run 13 candidate, given (a) today's inputs and (b) the authored sentence plus the scene. Report both answers. A model's answer is not a unit test.
10. **The full suite.**

## Measured (test 9, 2026-10-14, Codex subscription, cheap tier, 3 repeats each)

Turn 9's action and its three pending candidates (`escape_completed_without_condemning_another_prisoner`, `fog_bell_window_taken_at_lower_chain`, `hearth_debt_called_without_open_betrayal`), resolved `complete_success`:

| Variant | Fired `fog_bell_window_taken_at_lower_chain` |
|---|---|
| (a) today's prompt: de-slugged kinds, no scene | 3 of 3 |
| (b) de-slugged kinds, plus the scene ("dark runoff lane") and the new rule | 3 of 3 |
| (c) authored meanings, plus the scene and the rule | 0 of 3 |
| positive control: (c)'s inputs with a genuine boom-window escape in the laundry barge | 3 of 3 fired |

The authored meaning is what does the work. The scene and the rule alone don't fix a world built before this change (b). The meanings in this replay were written by hand from the source story, and in play the arc author writes them. Script and output: `scratchpad/replay` (not tracked).

**On gpt-6-astra (2026-10-14, after the subscription stopped accepting gpt-5.5; same inputs, 3 repeats each):** (a) 0 of 3, (b) 0 of 3, (c) 0 of 3; the positive control fired 3 of 3. Astra doesn't make this misfire even without the fix, so a run on astra can't show that the fix worked. Run 14 was not started (the monitor's note na0fa63).
