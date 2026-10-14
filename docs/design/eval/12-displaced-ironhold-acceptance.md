# R20 acceptance: the displaced-Ironhold probe (2026-10-08)

The WORLD-GROWTH acceptance pass the roadmap left open (`NEXT-UP.md`, "WORLD-GROWTH acceptance + latency"). Script: `scripts/displaced_ch2_probe.py`, on the subscription wire (CodexProvider). No metered calls. The build is fresh, so the probe exercises today's main (bce91b2). Logs are on `/media/k/Blank/construct-scratch/`.

## Pass mark, set before the run

The probe passes only if every one of these holds:

1. **Chapter 1 lands a conclusion** within its 11-turn schedule (`concluded=True`).
2. **The world grew where the player walked.** Chapter 1 ends in a place that did not exist in the pristine Ironhold world, a place minted in play, not one of the prison's built places.
3. **Chapter 2 opens where chapter 1 ended.** `CH2 OPEN STATE` equals `CH1 END STATE`, with no snap-back to Ironhold.
4. **No broken turns.** No chapter-2 `ENGINE ERROR`, and no turn returns empty prose.
5. **No critic breaker on the WHERE bar.** No filed note reports a teleport or snap-back. Notes on the goal-pivot and style bars are recorded as fiction-quality findings, not failures.

It fails if any of 1–4 fails, or if 5 does. If it fails, the fix goes on a branch and merges when green, and the probe re-runs.

Latency is recorded, not judged: the per-turn wall time and the `cp_*` checkpoints from `CONSTRUCT_MECHANICS_LOG` feed the R23 breakdown below.

## Run 1 — FAIL (criterion 1), causes found and fixed

Build: viable after one config change. This account refuses the default Codex cheap model `gpt-5.4-mini`, so the cheap tier ran on `gpt-5.5` (`HOLODECK_CODEX_CHEAP_MODEL`). The first attempt skipped all 12 chunks one by one, then failed later as a misleading 'bare world' arc error.

Chapter 1 played 11 turns and **did not conclude**. The protagonist ended at `obj:laundry_barge` (canon), still inside Ironhold. Chapter 2 never ran. July's run failed the same way (`place:ironhold`, not concluded), so this is not a regression.

What happened, and what was done:

1. **The escape turn lost its move to one passing server error.** On the turn where the player hails a skiff to Dyers' quay, classify hit one OpenAI `server_error` ("You can retry your request"). It was not retried, because today's stream-error fix had made every error event final. So the turn fell back to a plain action with no move, the narration improvised a chain-boom, and the critic-player retreated. **Fixed** (merged as `e5dec13`): server, overload, rate-limit and timeout stream errors are now transient and retried. Request errors and refusals still fail fast.
2. **A build whose every chunk fails now stops at once with the cause** (merged as `a34ae81`).
3. **Foreshadow pins were never indexed.** A second timeless `pin_index` row conflicted with the arc's own, and the fold served `[]`. **Fixed** (merged as `3eaf0bb`).
4. **Continuity breaks the critic filed** (a hymn slip changing hands, `held_by` cycles). These trace to pattern-buffer's `holds`/`wearing` inversion at its gate, whose fix (GATE-INVERSE-ALIAS-V1) is with pbr. That is engine-side by our law; nothing is changed in construct.
5. ~~**Canon/prose location divergence.**~~ **Withdrawn after run 2: a probe error, not a world error.** The probe read the player's place without the play horizon, so it printed the source book's later canon (`obj:laundry_barge`). Read at the horizon, as the session reads it, run 1 ended at `place:chapel_threshold`, which matches the prose. The probe is fixed.
6. **Live bots.** The Codex opt-in's default cheap model is refused by this account. The live Telegram bots aren't running (last active in July), so no player has been hit. The fix at the next start is one line, sent to the monitor for Kabe.

## Run 2 — FAIL (criterion 1), causes found and fixed

Fresh build with all of run 1's fixes. Chapter 1 played 11 turns. The player worked the dead man and the red-thread chit, broke out onto the river road when a warrant seal cracked, reached the chain-piers, took a false name, and stepped into a downstream hauler. The arc reached its won state on turn 9, at the piers (`beat:river_window_won`, lifecycle `won`, the narrator told the decisive moment is within reach). **The chapter did not conclude**, so chapter 2 never ran.

1. **The conclusory move was read as plain action.** On turn 11 the player made the escape's decisive act ("knot it around my wrist like a vow before stepping down into the hauler … I'm done earning the old"). The classifier only had accusation-shaped examples and nothing about the story's readiness, so `commits` stayed false. **Fixed:** while a commitment-owned win_loss arc is ready, classify is told the decisive moment is within reach and what this shape's conclusory act is (`commitment_kind`). The earned gate, stage gate and pillar bounce still stand behind it.
2. **A turn was lost to an HTTP 503** ("no healthy upstream") on narration. The stream-error fix covered errors inside a stream, not a failed status before it. **Fixed:** 429 and 5xx statuses are transient and retried; other 4xx errors still fail fast.
3. **The probe printed the wrong end place.** See run 1's item 5. Played to the horizon, run 2 ended at `place:river_road`, which **was minted in play** (absent from the pristine world). So criterion 2 holds for where canon has the player.
4. **Finding, for Kabe: the player cannot board a vessel.** "Step down into the hauler" resolved to `obj:hauler`, and the movement rule (Cx 327) never puts a person *in* an object, so the move was dropped. The prose ends with the player aboard and drifting downstream while canon keeps him on the river road (`obj:chain_piers` and `place:low_quay` sit inside it). The source book itself puts people in boats (`person:ewan in obj:mercy_finch`). Conveyances (enter a vessel, the vessel travels, the next chapter opens aboard) are a design question. Not changed tonight.
5. **Critic notes:** one, on Pike's role (staff in the opening, the condemned man's paperwork later). Not a WHERE note.

### R23 timings, run 2 (10 instrumented turns)

| | Run 2 |
|---|---|
| Player-felt (cp_generator + narrate) | 41–209 s; typically 70–110 s |
| Salience window | 8–69 s; typically 30–57 s |
| Narrate | 19–51 s; 124 s on a turn with a transport retry |
| Player-input ingest | 5–29 s |
| Settle tail (post_extract + promote) | 27–55 s; it did not grow steadily this run |
| Classify | 5–8 s |

The ranking holds: the serial salience window is the largest block before the reply, then narration, then the settle tail after it.

## Run 3 — FAIL (criterion 1); the last run tonight, by the monitor's stop rule

Fresh build on main `020f38d`, with run 2's fixes. The build was a different world: Ewan Vale, condemned cartwright, in the cartwright shed with the fortress captain, the chaplain and a deathwatch orderly over a dead reeve. Chapter 1 played 11 turns. The player investigated for seven turns (the orderly's sighting, the chaplain's satchel, a copied ledger scrap with a cartwright's mark), then tried to leave: the yard and river road, the north pier, then the wash-house. **The arc never became ready** (lifecycle `active`, act I, throughout), so there was no conclusory moment to take, and chapter 2 never ran. Canon kept the player in `place:cartwright_shed` all chapter, a built place, so criterion 2 fails too.

What happened, in order of weight:

1. **Too little room for this world's arc.** This build opened as an investigation, and the player spent seven turns on it. No escape beat fired before the 11-turn schedule ran out. That is not a defect by itself (the founder's rule: no turn cap, the chapter ends on its climax). But it means the probe's fixed 11 turns can't judge a build whose escape needs a longer run. **For Kabe:** whether the acceptance probe should run until readiness, with a much higher ceiling, rather than to a fixed count.
2. **The walk-out never moved the player.** Turn 8 ("turn from the shed door into the yard, and take the river road") left canon in the shed. The prose reads like the deliberation hold, where a journey is held for the player to weigh it ("If you're for the pier, know what you're stepping toward"). The mechanics log did not record movement, so this can't be confirmed. **Fixed (diagnostic):** the log now records movement status, and denied turns reach it.
3. **A refused claim also swallowed the move.** Turn 9 ("go down to the north pier, show my seal …") was refused whole, because the player has no seal. The refusal is right; losing the walk to the pier with it is the cost. Not changed tonight: this is the reviewed "a failed precondition does not commit" rule.
4. **An object-named destination dropped the move again.** Turn 10 ("make for the wash-house lamps") resolved to `obj:wash_house_lamps`, and the move was dropped under the same rule that dropped run 2's hauler (Cx 327). **For Kabe, with the conveyance question:** a destination named by an object could take the player to that object's place, as a move to a person already takes them to the person's place.
5. **"I lower the scrap" was refused (turn 7)** as if the scrap were elsewhere. The fiction's one scrap had split into four canon entities (`obj:scrap`, `obj:copied_scrap`, `obj:chaplains_scrap`, `doc:anselm_scrap`), none of them carried by the player. Separately, the player's own inner coat was minted with no location. This is an identity and anchoring gap in extraction, and it is not a small fix. The critic filed it twice (both notes are on the action-refusal bar, not WHERE).
6. **The refusal named the scene by its id** ("with the cartwright_shed behind you"). **Fixed:** the denial brief now uses the scene's name.
7. **One character, two ids.** `person:anselm_roake` and `person:brother_anselm` both took NPC turns every turn. This is the cast/canon identity collision lesson again, at build time. It also costs time: one more serial cheap call per turn.
8. **Engine inversion rows** are visible here too (`person:ewan_vale held_by doc:gallows_ledger`, `worn_by obj:felt_cap`). This is pattern-buffer's GATE-INVERSE-ALIAS, pending with pbr.

### R23 timings, run 3 (9 instrumented turns)

Player-felt 38–125 s, climbing as the cast grew; typically 80–115 s. Salience window 13–64 s, with four NPC turns run back to back, one of them the duplicate chaplain. Narrate 16–36 s. Settle tail 37–50 s. Classify 3–10 s. The ranking is unchanged: the serial salience window first.

## Where R20 stands for the morning

Three runs, three fails on criterion 1, for three different reasons: a lost retry (fixed), a missed conclusory move (fixed), and an arc that needed more turns than the probe gives. The world-growth half did work in run 2 (`place:river_road` was minted in play). The open design questions, all Kabe's:
- conveyances, and object-named destinations;
- whether the probe should run to readiness rather than to a fixed count;
- the identity split of carried things (run 3, item 5).

No run 4 tonight.

## Run 4: the pass mark as changed, set before the run

Kabe's gate g855759 went to its default: movement stays as it is (no conveyances; the object-destination branch stays unmerged), and the probe plays **to readiness**, with a 30-turn ceiling, before run 4. Chapter 1 now plays the original seven opening stances. If the arc is still not ready, it plays an escape stance until it is. Once ready, it plays the three displacement stances, then resolve, repeated until the chapter concludes or reaches 30 turns.

Criteria 2–5 stand. Criterion 1 becomes: **chapter 1 lands a conclusion within 30 turns** (`concluded=True`). The turn the arc became ready is recorded too. Since movement is unchanged, a fail that comes from boarding a vessel or an object-named destination is recorded as that, and not worked around.

## Run 4 — FAIL (criterion 1): the action deck was stuck on one card

Fresh build on main `2330910`, against a frozen copy of pattern-buffer at `0aaa30c` (it includes R22). The copy was needed because pb's R22 merge rewrote the engine mid-import and crashed the first attempt (archived in `ironhold-run4-aborted/`). The world: a condemned man in Ironhold, the Night Ice Reader's room, the death of the river clerk Arlen Pike. Chapter 1 played all 30 turns: seven of investigation, then the escape stance from turn 8. The player talked their way to a guarded trip to the necessary-house, slipped out the back, crawled the cart-rut to the river, fought a boatman over a skiff and a corded bundle, and ended in the wash-yard behind the hanging linen. **The arc was never ready** (2 of 6 beats; 0 of the 3 climax beats), so `concluded=False`, and chapter 2 never ran. Artifacts are in `ironhold-run4/`.

Against the mark: **1 fails.** 2 and 3 can't be judged without a conclusion. Canon's end place, `place:behind_hanging_linen`, came from the book, not from play. **4 passes in play** (no ENGINE ERROR, no empty prose); the build logged one ERROR, item 3 below. **5 fails:** the critic filed a WHERE note at turn 17 (prose had the player outside while canon kept them in the necessary-house).

What happened, in order of weight:

1. **Every uncertain action drew the same card.** From turn 6, 18 checks drew `failure_opportunity` 18 times, never a success. Each failure opened a new opening and took nothing, so no escape beat could land. The cause: the deck's seed and cursor were timeless session rows rewritten on every draw. Rows that tie on valid time read as *conflicted*, and the engine serves the first one, so the cursor read 1 forever and every draw after the first was card 1. This is not new: run 2's four `success_cost` draws in a row were the same stuck card on a luckier seed. The unit test's fake world kept the last write, so it never showed. **Fixed** (`fix/deck-cursor`): the rows are now `deck_seed` / `deck_cursor`, declared `fold_policy: last_write` on first use (pb READ-SURFACE-V1 §2). They need new names because the engine refuses to declare an attribute that already holds data. A saved world with old rows simply starts a fresh deck. Two real-engine tests were added; a copy of this run's world now draws success, failure, complete success.
2. **The engine's extractor dropped 266 facts** (`place:/chapel`, `event:mara-steps-from-fog`), ids its own grammar rejects. Run 2 had 371 of these. The cause is in the engine's extraction prompt (`ingest.py`, two places): "entity ids namespaced: person:/place:/obj:/event:" reads as `person:/`. pb's `c52736b` fixed the same slash in its eval harness only, not the engine. **Sent to pb** (m8be3a3 and follow-up); it is engine law, not ours to work around.
3. **The protagonist split** (build ERROR, #107 SEAL-LINT): the arc row says `person:tomas` while the authored arc says `person:tomas_reed`. Most of `tomas_reed`'s rows were among item 2's dropped facts. Play used `person:tomas`, and `person:tomas_reed` took an NPC turn on 28 of 30 turns, one extra serial cheap call each turn. He never surfaced in prose. It did not block readiness, because every beat here is an event beat with no knows: gate. Likely to go with item 2's fix; watch it in run 5.
4. **Moves to unnamed places stayed underdetermined** (`the necessary-house`, `the black mud beyond its light`, `the dark rut`, `the wash-yard`): no target and no candidates, so canon held the player while the prose moved on. That gap is behind turn 17's WHERE note. Movement stays as it is by g855759; recorded, not worked around.
5. **A prose-offered thing was refused as not owned.** Turn 29's prose put a river-office shirt "within reach"; turn 30's "drag the office shirt over my shoulders" was denied as "not a thing you are known to have". The narration never committed the shirt, and the refusal treated "within reach" as "not yours". This is first-mention permanence again; noted for daytime.
6. **The Night Ice Reader changed sex mid-turn** (critic, turn 4). Narration drift; no fix tonight.

### R23 timings, run 4 (30 instrumented turns)

Whole turn 24–268 s, median 170 s, 83 minutes for the chapter. Player-felt (generator + narrate): median 107 s, p90 143 s. Salience window: median 32 s, p90 83 s, max 103 s. It was largest in the six-person room (turns 3–12, 49–103 s) and fell to 10–34 s once the player was alone with the boatman. The settle tail is now the largest single block: median 63 s, p90 114 s (post_extract median 41 s, max 97 s; promote 8–48 s, no steady climb this time). Player-input ingest 4–50 s, median 19 s. Narrate 9–53 s. Classify 4–12 s. The ranking moves: the salience window still leads on crowded turns, and the settle tail now rivals it on every turn. A fast next message waits on the tail.

### Where R20 stands after run 4

Four runs, four fails on criterion 1. The two newest causes are a stuck action deck (fixed) and the engine's id drops (with pb). Run 3's cause, an arc that needed more turns, is what run 4's 30-turn ceiling answered; run 4 had the turns and was stopped by the deck. Run 5 needs no new decision from Kabe: same probe and same pass mark, a fresh build on main with the deck fix. The extractor's slash ids may recur until pb fixes the prompt; they cost facts, not the deck.

## Run 5 — FAIL (criteria 1 and 4): the protagonist split swallowed earned beats; the last run in this loop

Fresh build on main `605f121` (with the deck fix), against a frozen pb copy at `4f1a6a8` (engine code the same as run 4). The monitor made this the last run in the loop (nc47ee4). The world: Elias Venn, condemned, with Warder Hobb and the Scrivener over a skipped laundry weighing and a missing warrant. The player built the case for seven turns, talked and forced a way through the scale-room service door, followed a wicker drag-line through the laundry to the upper ash-stove, and ended at the rope side by the river. Chapter 1 hit the 30-turn ceiling, **never ready**, `concluded=False`; no chapter 2. Artifacts are in `ironhold-run5/`.

Against the mark: **1 fails.** 2 and 3 can't be judged. **4 fails:** turn 10 returned no fiction, only "(the turn could not complete: payload 40KB exceeds the 40KB Codex transport cap …)". **5:** no WHERE breaker. The critic filed 13 continuity notes (people and carried things disappearing), all on other bars.

**The deck fix held.** Nine checks drew 5 `success_cost`, 2 `complete_success`, 2 `failure_opportunity`.

What happened, in order of weight:

1. **The protagonist split decided it.** At build, #107 SEAL-LINT logged it again: the arc row says `person:elias_venn` while the authored arc says `person:elias`. Play wrote what the hero learned to `knows:person:elias_venn`, but the arc's four knowledge beats watch `knows:person:elias`. The player did learn two of them (the chaplain's seventh bell; the missing warrant's significance): both rows are in `knows:person:elias_venn`, and neither counted. The escape event did fire (`take_the_thaw_barge` is true), and readiness needs two of three climax beats. The likely second one, `weigh_the_condemned_laundry`, is a knowledge beat behind the same split. Its fact reached only Mara's frame, so even without the split the arc was one delivery short. `person:elias` also took an NPC turn on 22 turns. The seal lint fails open by design ("a false positive must not deny a player a world"). Twice in two runs it has been a true positive. **For Kabe:** whether a protagonist split should stop the build, or be repaired at seal, rather than only logged.
2. **A take of several things committed none of them.** Turn 22, "I hook the ash-rake and poker under my arm, shove the complaint slate inside my coat": the player-input ingest was skipped as `no asserts/reveals` (the A-lite skip). The narrator rendered all three takes. Only the slate reached canon, through promote. Worse, the after-turn extraction restated the poker's old place and promote re-committed `obj:short_poker in place:upper_ash_stove` at turn 22. The ash-rake never became an entity. From then on, the carrying list left them out, and turns 26–29 refused the poker and the rake. Recorded, not fixed (the loop is closed).
3. **Things the prose offered were refused** (seven refusals in all): the measures slate, a chain link, the bent witness-strip. Run 4's shirt is the same family. Most were never committed. The witness-strip is different: canon has it on the player (`in person:elias_venn`), alongside an older `held_by person:scrivener`, so that refusal is a reference or fold miss, not a missing row. Recorded with the movement findings, not worked around.
4. **Turn 10 crossed the Codex 40KB cap**, and the turn returned an error line instead of fiction. The narrate briefing outgrew the transport cap mid-chapter, with nothing to shape it below the cap. The founder's rule is no prompt budget, inclusion by merit; the transport cap is a hard edge that rule doesn't cover. For R23 and the briefing composer, not tonight.
5. **The engine extractor dropped 342 facts** (311 slash ids, 25 hyphenated event ids), on the pre-fix engine. pb has since fixed the wording (`4a1105a`, the extraction rules and the movement rule's `event:` example). **After the fix:** one build only, no play, of the same seed on pb `5fc61d4` (monitor n7c97a8) dropped **0** facts as `malformed_id` over 10 chunks, and its seal showed no protagonist split. One build is suggestive, not proof. Sent to pb.
6. **One in-turn ingest was dropped whole (turn 2):** "cannot declare semantics for attribute 'knows' after folded data already exists (a:1662)". The build held no `knows` rows (probably among item 5's drops). In play, `attr:knows` was declared at a:1661 and the first row landed at a:1662, and then a second declaration attempt was refused. pb traced it: the refusal came from a second World handle on the same file, whose semantics cache had not seen a:1661. ADOPTION.md forbids that (one live World per file). pb reproduced the exact error with two World handles on one file, and found no other way to cause it. On our side, every World opens through `game._world()`, only `open_playthrough` opens the slot during play, the settle runs on the session's own thread, and the scene-image thread never touches the world. So the second connection is still unaccounted for. The monitor's follow-up search (nd4bf81) found none: no in-play code opens the slot twice, and a pytest plugin that flags a second World opened on a file while an earlier handle is still alive found 0 in the full suite (1554 passed on pb `8dfeff0`). Not reproduced, so nothing to fix yet. pb's second-writer guard (`8dfeff0`, `SecondWriter` on another connection's commit) is now live, and the next real run will name the handle if one exists. pb proposes that the engine fail loudly on a second writer, as a candidate for Kabe. The fail-open shield (task #89) kept the turn.
7. **Two transient stalls:** a cheap-tier classify batch hit the 180 s bound (the engine defaulted the batch), and one 503 was retried.

### R23 timings, run 5 (29 instrumented turns)

Whole turn 13–359 s, median 117 s, 64 minutes for the chapter. Player-felt median 79 s, p90 106 s (max 298 s, on the turn whose player ingest took 193 s). Salience window: median 34 s, max 66 s; the room never held more than three NPCs. Settle tail: median 62 s, p90 130 s (post_extract median 29 s, max 120 s; promote median 29 s). Narrate median 23 s. Classify 3–14 s. As in run 4, the settle tail is the largest steady block.

### Where R20 stands after run 5

Five runs, five fails on criterion 1, each for a different first cause. Of those causes, the lost retry, the missed conclusory move and the stuck deck are fixed. The engine's id drops are fixed upstream. The cause that remains is the protagonist split, which fails open at seal. It showed in runs 2, 4 and 5 and decided run 5. The loop stops here, as agreed. No run 6 without Kabe. What waits on him:
- whether a protagonist split stops or repairs the build;
- conveyances and object-named destinations;
- whether to fix the multi-object take, and the briefing's 40KB edge, as R20 work or later.

## Run 6 — FAIL (criteria 2 and 5): chapter 1 concluded for the first time, but the player never left the room

Kabe opened run 6 (monitor n715a22, 2026-10-12), after main was pushed (`ce6186c`). Same probe and pass mark, on pushed main, with pattern-buffer frozen at `1041704` (engine source as `8dfeff0`, the SecondWriter guard). A crash at about 00:32 killed the pre-push suite; it was rerun green before the push.

| Criterion | Result |
|---|---|
| 1. Chapter 1 concludes | **Pass.** Turn 5: `beat:writ_chain_broken` (event `gallows_writ_bell_chain_disrupted`) took the arc to act III, `won`, and the settle closed the chapter. The first conclusion in six runs. |
| 2. Ends in a place grown in play | **Fail.** The player ended at `place:ironhold`, the prison itself. They never moved: all five turns were talk and a forensic act in one room. |
| 3. Chapter 2 opens where chapter 1 ended | Pass (`place:ironhold` to `place:ironhold`). |
| 4. No broken turns | Pass. Chapter 2 played 6 turns with no `ENGINE ERROR` and no empty prose. Two Codex 503s were retried and recovered. |
| 5. No WHERE breaker | **Fail.** Notes t2–t4 report the narration putting the scene "in a cell" ("the cell's iron holds the cold around all of you", Hal angling "toward the cell door") while the scene was set below the key gallery; t4 calls it "snapping us into a cell that we didn't enter". Canon never moved; this is prose drift, but it is the teleport report the bar names. |

What run 6 showed:

1. **The conclusion came early and without the escape.** A prison-break build (win_loss: escape) won on its fifth turn, on the player's linen-and-ink move against the writ chain. That meets the founder's rule (the chapter ends inside a resolution), but the story the critic-player was steered toward, "get out", never happened, so the world-growth criterion had nothing to test. The probe's ch1 schedule only pushes movement after the arc is ready; here readiness and the win came on the same turn. Recorded, not changed: whether criterion 2 should require the move, or the probe should push it earlier, is a pass-mark question.
2. **The protagonist's twin, again.** The seal passed: the arc row and the authored arc both say `person:tomas_reed`. But `person:tomas_reed_cell` ("Tomas Reed Cell") was a separate person in the room and took an NPC turn on all 10 played turns, one serial cheap call each. This is the case the frame-owner consult (gate gc53c58, point 2) names: the naming stays consistent, so today's seal check misses it, and a live twin of the hero sits in the scene. Built on the pre-R35 engine, so it is not R35's doing.
3. **No protagonist split, no id drops, no second writer.** No `malformed_id` skips, no `ProtagonistSplitError`, no `SecondWriter`, no knows-declaration error. The turn-3 error from run 5 did not recur, so the guard had nothing to name.
4. **Fiction-quality notes** (recorded, not failures): at the chapter seam the roles of Venn and Morrow swapped (clerk and bellman); in chapter 2 the lock-twine vanished ("there is no lock-twine there") and came back the next turn.

R23 timings, 10 instrumented turns: whole turn 95–306 s in chapter 1. Player-felt (cp_generator + narrate) min 52, median 138, max 184 s. The salience window (snapshot to salience) median 78 s, max 97 s, about twice run 5's median of 34 s, though npc_action itself stayed at 3–9 s; the machine was under heavy load from other projects all night (load average near 20), and the cheap tier returned two 503s, so this is not read as a regression without a quieter rerun. Settle tail median 62 s, max 131 s. Narrate median 29 s. Classify 5–14 s. Player-input ingest 16–34 s.

### Where R20 stands after run 6

Chapter 1 now concludes and chapter 2 plays without engine errors. Two things stand between this and a pass:
- the twin of the hero (gate gc53c58, with Kabe);
- whether criterion 2 is still the right test when the arc can win without the player moving (Kabe's call; the movement findings stay recorded, not worked around).

No run 7 without Kabe.

## Run 7 — FAIL (criterion 5 only): the player escaped, chapter 1 concluded in a place grown in play, and chapter 2 opened there

Kabe opened run 7 (monitor nf6e067, 2026-10-12: "Construct tests seem warranted as we are designing elements to engage with construct"). Same probe and pass mark, on local main `131a02c` with the pinned engine (`0eb4e3f`), so the first run with IDENTITY-CONFIRM (R34) at build. Codex subscription only; about 70 minutes. A first launch stopped before any model call because run 6's world was still in `worlds/`; it was moved aside (checked byte-identical to the run 6 archive) and the probe relaunched.

| Criterion | Result |
|---|---|
| 1. Chapter 1 concludes | **Pass.** Turn 16, with the player out of the fortress and in the river drain. |
| 2. Ends in a place grown in play | **Pass.** `place:barred_drain_mouth` is not in the built world; play made it. The first pass in seven runs. |
| 3. Chapter 2 opens where chapter 1 ended | **Pass** (`place:barred_drain_mouth` to `place:barred_drain_mouth`). |
| 4. No broken turns | **Pass.** No `ENGINE ERROR`, no empty prose, across 16 + 6 turns. One logged ingest failure (finding 3) dropped rows but not the turn. |
| 5. No WHERE breaker | **Fail.** Critic notes t2 and t3: canon kept the player in their cell (`place:elias_venn_cell`), but turn 1's prose has Dena set the sack down "beside the cold hearth" and the player examining the hearth, which the opening placed in the warrant room, seen "past Dena's shoulder, through the open angle". The critic: "unclear whether Venn is still in the cell or has been moved to the warrant-room hearth." Prose drift, not a canon move, the same class as run 6's. |

What run 7 showed:

1. **Movement works when the arc needs it.** From turn 10 the player walked: under the laundry arch to the lower yard and river gate, onto the winch roof, down the stair into the river, along under the pier, and out at a drain mouth the world grew for them. The escape win landed there. This is the run 6 question answered by play: with an escape goal that the arc does not grant early, the player moves.
2. **The hero is split again, and now held apart.** At build, pattern-buffer's identity reconcile (stage 2) wrote `a:1166`, `person:elias distinct_from person:elias_venn`. `person:elias` carries 70 rows of the hero (aliases "elias", "venn", "the condemned cartwright"; the wrist brand; their own cell, `place:elias_cell`), while the arc and play use `person:elias_venn` (19 rows). The vouch cannot fold a pair the engine holds apart, and IDENTITY-CONFIRM treats an engine-decided pair as decided, so no check stopped it. It did not show in play because `person:elias` sat in another cell and never entered a scene. The same pass held three Quill ids apart (`person:quill`, `person:silas_quill`, `person:warrant_clerk_quill`). This is the run 5 split, now hidden behind a keep-apart row. pattern-buffer traced it (mbaab95): the engine wrote nothing; construct's own homonym pass in the reconcile read the differing role words in `kind` as two kinds and rejected the pair. **Fixed** (`fc6c15d`, cr GREEN after one RED): the reconcile holds apart only pairs in two id namespaces. A live same-name pair in one namespace with differing kinds may be role noise or two people sharing a name, and nothing in the build tells them apart, so the identity confirm never merges one. If it touches a load-bearing id the build stops; otherwise the pair is held apart. This seed's world would now fail its build instead of building split.
3. **A turn's ingest refused a declaration its own turn had made.** Turn 4's player-input ingest declared `keeps` set-valued (`a:2597`) and wrote two rows. A later ingest in the same turn was refused whole: "cannot declare semantics for attribute 'keeps' after folded data already exists (a:2598)". pattern-buffer found the cause (mbaab95): the refused batch carried an explicit `attr:keeps` declaration item, which the engine refuses once the attribute holds data. No host code builds such an item on purpose, and the producer is not yet found. **Mitigated** (`fc6c15d`): the turn's ingest wrapper drops `attr:*` items, logs each with its contents, and marks it on the trace (`dropped_declarations`, in the mechanics log), so the next run names the producer.
4. **A question became fact.** The same turn-4 line asked "Quill, who keeps the wash tally ink and knife?" and the player-input ingest wrote `Quill keeps obj:wash_tally_ink` and `Quill keeps obj:knife` to canon. The question-only skip did not apply because the line mixed a question with a statement. **Fixed** (merge after `a35d9cd`, cr GREEN after one RED for '?!'): the player-input extraction sees only the line's statements; a question-only line extracts nothing.
5. **Object permanence broke in chapter 2** (fiction quality, recorded): the packet's vellum, narrated in hand at ch2 t2, was "no vellum to unroll" at t3 and back at t4; the ash-blue thread, pinched free in turn 11's prose and "still with" the player at the chapter 1 close, was by canon still at the laundry sack; one lost boot became bare feet at the seam. Each is prose that canon never held, the first-mention-permanence class.

R23 timings, 22 instrumented turns: whole turn in chapter 1 128–291 s, median 152 s. Player-felt (generator + narrate) min 63, median 99, p90 163, max 195 s. Salience window median 30 s, p90 100 s, max 112 s (npc_action 5–7 s; the load average was near 11). Settle tail median 56 s, max 128 s (post_extract median 30 s, promote median 24 s). Narrate median 28 s. Classify 5–19 s. Player-input ingest 15–51 s, median 20 s.

### Where R20 stands after run 7

Criteria 1–4 pass for the first time. What stands between this and a pass is prose that places the player somewhere canon does not (runs 6 and 7), and the same truth-keeping gap shows as objects that come and go in chapter 2. The hero split (finding 2) is a build-identity defect that this run happened not to expose.

### Criterion 5 traced (on paper, 2026-10-13; nothing run)

From run 7's mechanics log and play world:

- **The opening.** It put the torn sack and a hearth in the warrant room, seen from the cell "past Dena's shoulder, through the open angle". Canon held the sack there (`obj:torn_laundry_sack in place:warrant_room`, from the build). It held no hearth, and nothing said the warrant room can be seen from the cell. The opening's prose is shown but never read back into canon (`session.py`, `_opening_narration`; only turns run post_extract). So its hearth, firelight and sightline existed in prose only.
- **Turn 1.** The player said "Let me see the sack and the hearth". The briefing's scene list held two rows: Quill's private-audit relation and the cell's description. The location filter (`turnloop.py`, the `_here` set) keeps anything placed elsewhere out of that list. So the sack, its place, and the warrant room were all absent, and no line told the narrator that the sack and the hearth were not here. Under "The scene is HERE and only here", the narrator brought both into the cell: Dena sets the sack down "beside the cold hearth".
- **Canon followed the prose.** Post_extract wrote `obj:hearth` with no place, and `person:dena beside obj:hearth`. By turn 8 the sack is `in place:elias_venn_cell`. Canon and the later prose agree with each other. Only the opening disagrees, and the critic read the opening.

Two gaps, both construct's:

1. **The opening never becomes canon.** First-mention permanence does not cover the cold open. This is the class of finding 5.
2. **A named thing that is elsewhere gets no "not here" line.** The location filter is right to keep elsewhere objects out of the scene list; that is the "tape followed us everywhere" fix. But when the player names one, the narrator learns nothing about where it is, and the HERE directive pulls it into the room.

Fix shapes (not built). Run 7 needed both:

- **For gap 2.** When the player's line names an entity that the player's own frame places elsewhere, the briefing carries one line: "<name> is not here: it is in <place>." The narrator can then have someone fetch it, have the player look across, or say it is not here. The line reads the player's frame, never canon, so it gives away no whereabouts the player has not learned.
- **For gap 1.** Run the turn's prose extraction on the opening too, so that what the opening shows is committed where the opening puts it, in canon and in the player's frame. In run 7 the player's frame held nothing about the sack before turn 1 (one warrant-room row, the clue turn 1 delivered). Only canon knew where the sack was, and the hearth was nowhere. Without this fix, the gap-2 line has nothing to read.

**Built (`66e9774`, cr GREEN at `3049d31`).** Spec: `docs/design/OPENING-SETTLE-AND-ELSEWHERE.md` (cr GREEN at r3, after two REDs). Code review: one RED, places, fixed.
- The opening's prose now settles once into canon and the player frame before turn 1.
- A named thing or place that the player frame puts elsewhere gets a binding NAMED BUT NOT HERE line.
- Residual risk: a fresh extraction could still place a distant vista in the opening scene.
- Not yet proven in play. That needs a run 8, which waits for its own say-so.

## Run 8 — NOT PLAYED: the build stopped itself on four same-name pairs

Opened by the monitor (n715eb5, 2026-10-13, under Kabe's run-7 word). It ran on local main `bb59ab3`, so it carried the criterion-5 fix (`66e9774`) but not the question fix: cr was RED on that branch at the time, and the monitor's word was to run on main as it was. Codex subscription only; about 10 minutes, all build.

The build reached stage 4 and stopped: "BUILD NOT VIABLE: a key character came out as two different people". IDENTITY-CONFIRM found four load-bearing same-name pairs, each in the `person:` namespace. The engine's audit had auto-declined each as `kind_conflict` ("same name, kinds differ"):

| Pair | Same name |
|---|---|
| `person:elias` ~ `person:elias_venn` | elias (the hero) |
| `person:breck` ~ `person:tomas_breck` | breck, tomas breck |
| `person:father_oren_vale` ~ `person:father_vale` | father vale, vale |
| `person:nessa` ~ `person:nessa_reed` | nessa |

**Every pair is one person.** The build's own generated source names each fully in some places and partly in others: "Tomas Breck", "Clerk Tomas Breck" and "Breck"; "Father Oren Vale" and "Father Vale".

So this is the run 7 fix doing exactly what it promised: this seed's world now fails its build instead of building split. It is also its cost. Nothing in the build tells role noise from two people sharing a name, so every pair like these stops the build, and a world with several named supporting characters will rarely build.

The criterion-5 fix (`66e9774`) and the question fix are untested in play until a build gets through.

### What it needs (not built; design, then review)

The confirm stage needs evidence that tells a name fragment of one person from two people sharing a name. Candidate sources:
- **The build's own source text.** A short name that only one full name in the source contains is that person's fragment ("Breck" inside "Tomas Breck"). Lysa beside both "Lysa Marr" and "Lysa Fen" is ambiguous and stays held apart.
- **The engine's vouch.** Why does the engine's audit auto-decline same-namespace kind conflicts before its vouch can judge them? The kinds are extraction's role words ("condemned man" beside "person"). That is a question for pattern-buffer.

No run 9 until one of these is designed, reviewed and built. (Built as IDENTITY-CONFIRM r6 plus pattern-buffer R48 and R49; see run 9.)

## Run 9 — INCOMPLETE: built and played 25 clean turns, then the Codex login expired

Opened under the monitor's pre-approval (n94c4cd), on local main `f038999`, engine pinned at pattern-buffer `9e0620f` (R48 merge gate plus R49 person roles). Main suite 1686 passed, 1 skipped. Codex subscription only. Started 12:11 PDT 2026-10-13. Stopped by hand at about 13:20, at turn 28.

**The build passed.** The identity check that stopped run 8 did not fire: under R49 a person's role words are no longer their kind. The viability gate published the world after about 20 minutes.

**Chapter 1 played 25 turns with no engine error**, average about 2 minutes a turn. The play was escape work on condemned row through Hester, Mara and Jory: door marks, the stone tag, the laundry bundle. Chapter 1 had not concluded by turn 25. No turn cap applies (chapter ends on climax only).

**At turn 26 every model call failed:** "Codex auth failed (401): Your authentication token has expired." The token in `~/.codex/auth.json` was last refreshed 2026-10-04. Construct's Codex provider reads that file and does not refresh it. The probe was stopped at turn 28; turns 26 to 28 are failed turns, not play. **The run proves nothing about criteria 1 to 3 and 5.** Criterion 4 failed on infrastructure, not code.

### Findings from the 25 turns (for the next run and R20's open items)

1. **Object permanence flickers within one scene** (critic, turns 17 to 20). The stone tag was in the player's cell, then "there is no tag under it", then "your fingers find the stone beneath you: not gone", then "you have hidden only filth in the crack", then "the hidden stone" again. Hester likewise vanished from the passage and came back. This is R20's open item, object permanence, now seen in chapter 1.
2. **The world denied the player's own clothing** (turn 21). The player tore a strip from their shirt hem, which Hester had just suggested ("Shirt, sheet, bandage"). The narration: "your teeth and fingers find no shirt there." There was no canon row for the player's clothes, so the permanence check refused an ordinary belonging. This is a make-it-real gap: World-Growth's commit-on-first-mention, applied to the player's own things.
3. **"Hester Rook 2."** The cast's #92 identity gate remapped the cast's Hester (`person:hester_rook`, a chapel cook) to `person:hester_rook_2`, because canon's `person:hester_rook` now carries R49 roles "soldier, sergeant" that share no words with "chapel cook". Before R49, those words sat in `kind` and the gate saw no role, so it reused the id. The world now holds a nameless soldier `person:hester_rook` and the cook `person:hester_rook_2` (named "Hester Rook"). Labels built from the id ("Hester Rook 2") reach the cast listing and the mechanics log, but not the prose. To check: is the source story's Hester a soldier at all, or did extraction fuse two people? The gate also reads only the newest role, not every role in force.
4. A smaller continuity snag (critic, turn 4): "Mara's empty stool" while Mara stood in the passage.

### Where R20 stands after run 9

The identity route works: the build gets through. The run needs repeating once Codex is logged in again. The world built in this run was moved out of `worlds/` into the session scratchpad, so the rerun builds fresh. Findings 1 and 2 are the next real fiction work. Finding 3 needs a look at the source story first.

## Run 9, restart — FAIL (criteria 2 and 5): chapter 1 concluded, but the player never left the cell

Restarted from scratch at 14:05 PDT, after the monitor redid the Codex login (n7c1df5), under the same approval (n94c4cd), on main `f55fcbb` with pattern-buffer `9e0620f`. The build took about 15 minutes and published a viable world. The identity stop did not fire. Chapter 1 concluded at turn 12, chapter 2 played 6 turns, and the probe exited 0 at 15:13. The output is archived at `/media/k/Blank/construct-scratch/run9` (the first attempt at `run9a`).

| # | Criterion | Result |
|---|---|---|
| 1 | Chapter 1 concludes | **PASS**, at turn 12 |
| 2 | Chapter 1 ends in a place grown in play | **FAIL**: end state `place:tomas_cell`, the starting cell |
| 3 | Chapter 2 opens where chapter 1 ended | PASS by the engine (`place:tomas_cell` both). But the reader saw a jump: chapter 1's last prose has the player at the gate table, and chapter 2 opens back in the cell |
| 4 | No ENGINE ERROR or empty prose | **PASS** |
| 5 | No critic WHERE breaker | **FAIL**: chapter 2's opening put "a black-edged slip just inside the barred door"; the next reply said "There is no loose paper on the floor" and moved it into the Chaplain's book (critic, ch2 t102 and t103). Jory was also present without being staged |

### Why the player never left the cell (criterion 2)

Turns 9, 11 and 12 moved "to the gate table". The movement step resolved each to `obj:gate_table`, an object born in play with kind "table" and **no location**, and returned `in_scene`, which treats an unlocated object as here. So no move was committed, and no place was grown. The prose narrated the walk anyway, which caused criterion 3's jump. The fix belongs in movement: a move whose target is an object that isn't located in the current scene (unlocated, or elsewhere) is a destination, not an in-scene approach. An unlocated one should go to world growth, so the place around it is made real. This is the same family as run 7's sack: an object's place unknown to the player frame.

### Also seen

- `person:jory_kest_2`: the cast's #92 identity gate split a character again, as Hester in the first attempt. The cause is known: the cast author reuses canon names without seeing their roles. SEEDING-REGISTRY-FIRST.md fixes it at the root.
- The chapter 2 opening named the chalk clerk "Did Not Blow", a model glitch in naming.
- Object and presence continuity flickered again (the slip; Jory), as in the first attempt's stone tag.
- Turn time was about 2 to 4 minutes. The salience window (cp_salience_done) took 42 to 97 s of each turn, as R23 found.

### Where R20 stands after run 9

The identity route works: two builds in a row passed. Chapter 1 concludes. What fails is the move itself: an object target with no location swallows the escape. That is the next fix (movement), together with the object-continuity flicker, which now shows in both attempts.

## Run 10 — FAIL (criterion 5 only): the player escaped into a grown place; chapter 2 then denied what its own opening described

Under Kabe's "Ok on 1 test" (2026-10-13), on main `7e855e8` (with the movement fix MOVE-TO-UNPLACED-OBJECT) and pattern-buffer `9e0620f`, Codex subscription only, timing log on. Output is archived at `/media/k/Blank/construct-scratch/run10`.

**The first attempt stopped at build, by design** (archived as `run10a`, 273 s in): `person:holt_2 ~ person:signe_holt`.
- In the story, "Rivermaster Holt" is "Signe Holt, Rivermaster of the Torne". Extraction split her into `person:holt` and `person:signe_holt`.
- The cast step then moved its own conception of her to `person:holt_2`, and the identity stop refused the split.
- This is the third build in a row with a `_2` cast remap since R49, and the motivating failure for SEEDING-REGISTRY-FIRST r4 and pattern-buffer's BUILD-LIBRARY-V1.

**The retry built in 424 s** and played 14 chapter-1 turns and 6 chapter-2 turns, exiting 0.

| # | Criterion | Result |
|---|---|---|
| 1 | Chapter 1 concludes | **PASS**, at turn 14 |
| 2 | Chapter 1 ends in a place grown in play | **PASS**: `place:streetlamp_smoke`, minted when the player climbed out of the Last Office window ("keeping low below the streetlamp's line") |
| 3 | Chapter 2 opens where chapter 1 ended | **PASS**: `place:streetlamp_smoke` both, "on the narrow pavement ... under the old streetlamp" |
| 4 | No ENGINE ERROR or empty prose | **PASS** |
| 5 | No critic WHERE breaker | **FAIL**: chapter 2's opening put the player "outside the ice cutter shed ... its double doors barred with a frost-whitened hasp", with "a clean northbound pass and a sealed packet" in their coat. The next reply: "there is no shed in this patch of pavement, and no hasp under your gloved fingers". Then "no pass" (critic ch2 t1–t5) |

### Why criterion 5 failed (traced in the mechanics log)

1. **The chapter-2 opening invented scene things and inventory that canon doesn't hold.**
   - `refer` found `obj:shed_hasp` (the opening settle extracted it), but not in the scene.
   - The narrator's briefing had no shed or hasp, and its EXCLUSIVE carrying list had no pass.
   - So the narrator denied them, and the classifier refused the pass ("never been established in this world's canon").
   - This is the old ghost-hook family: an opening stages props in prose only. Here the settle created the entities but did not place them in the opening's scene or in the player's possession.
2. **The player frame kept the player "in cell 12".** The briefing's YOU block read `you · in · cell 12` after the escape. At turn 14 the move grant to "the streetlamp smoke" wrote its rows but "did not take" and fell back to extraction. Canon then got the player into the new place, but the player's own frame never did.

### Next fixes (not built)

- **The continuation opening's settle anchors what the opening stages.** Objects described as present go `in` the opening scene; things "in your coat" are `held_by` the player. Or the opening is grounded strictly in canon. This needs a spec.
- **Trace "move grant did not take".** Find why the protagonist chain check failed after the rows were written, and make the player frame follow every committed move.
- **A place-naming quirk:** the classifier's `moves_to` ("the streetlamp smoke") became the place id. It is harmless in prose, but the registry and naming work should improve it.

### First per-turn timing (20 turns)

- Turn wall time: 20–177 s.
- Calls inside a turn ran serially (×1.0 parallel).
- The settle after each turn took a further 33–64 s.
- Calls by step:
  - **extraction:** 64 calls, 1337 s, mean 21 s;
  - **the engine's lifetime classifier:** 109 calls, 566 s, mean 5.2 s. This is a literal categorization (CONSTITUTIVE, DISPOSITIONAL or STATE) and the clearest case for the fastest model, batched;
  - **narration:** 23 calls, 464 s, mean 20 s;
  - **the classify cohort:** 20 calls, 163 s;
  - **NPC turns:** 27 calls, 109 s.
- Full tables: `run10/timing-report.md`.

## Run 11 — first attempt stopped at build (archived as `run11a`); retry under way

The monitor authorised this run for Kabe (note n96b11a): one run, after the containment pin, to test everything merged since run 10. It ran on main `ef5febe` with pattern-buffer `42d0c23` (CONTAINMENT-DURABILITY-V1), Codex subscription only, timing log on. Before the pin, main's suite passed on the new engine: 1,828 passed, 1 skipped.

**The first attempt stopped at the identity stop, about 6 minutes in:** `person:seal_press_keeper_1 ~ person:seal_press_keeper_2`.
- Both carried the name "one of two seal-press keepers", and the engine declined the pair as `not_name_like`.
- The story plainly makes them two people: "two seal-press keepers behind him", and later "One seal-press keeper followed; the other froze."
- The adjudication stage takes only `alias_not_specific` pairs, so it never asked. In this story the stop was false, but it stays: an honest stop.
- A fix was proposed and withdrawn. Amendment r7 would have held a `not_name_like` pair apart on two `different` answers from the merge gate. cr returned RED. The class also covers speaker-relative labels ("my apprentice"), which can be one person extracted twice. Without case evidence, a reject would make a false split permanent, and the engine has no sentence-level provenance to supply that evidence.
- The real fix is SEEDING-LIBRARY-WIRING r2.1 (cr GREEN; it waits on pattern-buffer's BUILD-LIBRARY-V1 merge). There, the author's manifest declares each person, and same-named entries are held apart by that declaration.
- The build also logged five `valid_to_before_valid_from` skipped edges, all reported by the engine's ingest.

As with run 10a, the retry ran under the same single-run approval.

## Run 11 — FAIL (criteria 1–3 and 5): chapter 1 never concluded; narrated objects vanished from canon

**The retry built in 469 s** and played 30 chapter-1 turns. The probe then halted with 15 critic filings, so there was no chapter-2 leg. Output is archived at `/media/k/Blank/construct-scratch/run11` (world included).

| # | Criterion | Result |
|---|---|---|
| 1 | Chapter 1 concludes | **FAIL**: still active at turn 30 (act I) |
| 2 | Chapter 1 ends in a place grown in play | **not reached** |
| 3 | Chapter 2 opens where chapter 1 ended | **not reached** |
| 4 | No ENGINE ERROR or empty prose | **PASS** |
| 5 | No critic WHERE breaker | **FAIL**: 15 continuity filings (t9–t30), every one the same family |

### Why it failed (traced in the world, read after the run)

From turn 9 on, the narrator described an object, and the next turn's classifier refused it as "not a thing you are known to have — it has never been established in this world's canon". The player spent the chapter re-trying with things the world kept un-saying, so no beat landed. Three causes, none from tonight's merges:

1. **A narrated drop got no destination.** "The lower pin drops free onto the wet stone below the bell-pull" settled as `obj:lower_pin` with `part_of obj:bell_pull_plate`, `fastening_anything = False` and no `in` row. It was in canon, but nowhere. The scene listed only what is `in` the place, so the next turn's take was refused (t17), and the critic filed it at t18–t22.
2. **A narrated hand-over got both ends.** "The key-ring is yours" settled as two `in` rows at one valid time, written consecutively by one extraction: `in obj:belt` and `in person:tomas_venn`. The engine serves the key `conflicted`, so the next turn treated the keys as not held (t29–t30). Before CONTAINMENT-DURABILITY, one of the two would have been served instead (CONSTITUTIVE outranks STATE), and the belt row could have won, so this would have been wrong either way.
3. **A twin id for one thing.** The cell's straw from the build, `obj:straw`, has no location. The player's `obj:straw_scrap` (named "scrap of straw") is correctly `in person:tomas_venn`. "The straw" in the player's turn-9 line bound to the location-less twin, and was refused (t9–t12). Turn 18's carrying list still showed "scrap of straw".

Also seen:
- The player's place at the grille was minted as the id `closed` (`closed · description · c-wing inner grille`), and the plate later read `held_by closed`. A state word was minted as a place id, from extraction.
- Some build-time `role` and `former_residence` rows were skipped as `valid_to_before_valid_from`, and three `obj` self-containment edges at the opening were refused by the engine's tree invariant. Both reported by the engine's ingest.

### What did work

- **The identity stop held its line on the first attempt** (run 11a, above).
- **Placements by rule cut the in-turn classifier load in half.** In-turn "Classify the lifetime" calls fell from 3.5 to 1.8 a turn (run 10: 69 calls, 247 s over 20 turns; run 11: 54 calls, 192 s over 30 turns). Mean turn wall time fell from 78 s to 60 s, though that mean is flattered by several short refused turns. Settle calls held at about 1.5 a turn (45 calls, 357 s).
- **No containment flicker from a host placement.** Every refused object above came from the narrator settle's extraction, the residual PLACEMENTS-BY-RULE named.

### Next fixes (not built; each needs a spec)

- **A narrator-settled object is somewhere.** An object the settle mints or changes with no live `in`/`held_by` falls back to the scene it was narrated in, written by rule. That is first-mention permanence applied to placement. A part detached from its whole is the same case.
- **One end per transfer.** When one settle extraction yields two live `in` rows for one subject at one valid time, the host keeps the one the prose's outcome names (the destination). It needs an engine or extraction-shape decision with pattern-buffer first: the conflict is the engine's honest read.
- **"Known to have" reads the scene and canon, not only possession.** The refusal wording was false (the pin was established), and a take of a thing lying in the scene is a move, not a claim. The classify cohort's existence check should see the scene's objects, and the twin straw shows refer binding to a location-less twin over a held one.


## Run 12 — FAIL (criterion 5 only, narrowly): first library build; the player escaped into a grown place, and chapter 2 opened there

The monitor authorised this run for Kabe (note n4f4a40). It tests the night's three fixes (NARRATED-OBJECTS-LAND, RESTATED-ORIGIN, the known-but-not-yet movement guard) and the seeding library (SEEDING-LIBRARY-WIRING). It ran on main `9e6c34e` with pattern-buffer `e3101a4`, the library path on, Codex subscription only, timing log on. Output is archived at `/media/k/Blank/construct-scratch/run12` (world, manifest and critic notes included).

**The build, through the library: 410 s** (run 11: 469 s; eval/13 baseline: 474 s).
- The author's manifest validated first time: 17 identities.
- One chunk was refused ("declared but not used: new:3, new:4"), and construct's retry succeeded. That is the case pattern-buffer's r1.9 now handles itself.
- Stage 1 took 59 s of wall time (run 11: 85 s). Stage 2 was skipped (run 11: 17 s). No identity stop.

| # | Criterion | Result |
|---|---|---|
| 1 | Chapter 1 concludes | **PASS**, at turn 16 |
| 2 | Chapter 1 ends in a place grown in play | **PASS**: `place:deck` (the laundry barge's deck), minted at turn 15; absent from the built world |
| 3 | Chapter 2 opens where chapter 1 ended | **PASS**: `place:deck` both |
| 4 | No ENGINE ERROR or empty prose | **PASS** |
| 5 | No critic WHERE breaker | **FAIL**, narrowly: t4 reports the narration putting Jory and the tool-ledger boy back "by the works-master's desk ... by the inkstand", the previous room, while the player stood at the scullery threshold. Canon didn't move; this is NPC staging prose drift, the run-7 class |

### The other critic notes (7 in all; none on the WHERE bar but t4)

- **Narrated things still vanished, from three causes the run-11 fixes don't reach:**
  - **"An oilskin packet ... slides down behind it" (t15–t16)** settled with only literal rows (kind, alias, condition, material). No entity tie means NARRATED-OBJECTS-LAND rightly leaves it unplaced, since an untied object may be absent. A later turn mentions it again.
  - **"Rope loops" (t12)** settled `in obj:hold`, an object twin of the scene place `place:laundry_hold` (the engine skipped `place:laundry_hold same_as place:hold` as not-canon). The loops were in canon, inside the wrong "hold". This is the twin-id family, pattern-buffer's R55.
  - **The sack-hook (t13–t14)** was never minted at all: prose offered "a wet glint on a sack-hook or a tin laundry tally", a hedge, not a thing.
- **Chapter 2 concluded at its second turn.** The player dictated a hold-fast warrant and the chapter's arc read it as its climax (`lifecycle=won`). The probe's next four moves got "(This chapter has closed.)", and the critic filed that as a stall (ch2 t6). The probe keeps sending moves after a conclusion, so the stall is the harness's; the two-turn chapter is a real pacing finding.

### What the night's fixes did

- **No two-place object in play:** no containment read was `conflicted` at chapter 1's horizon. Whether RESTATED-ORIGIN dropped a row is not known: its log line is INFO, which the probe didn't capture.
- **At the head, three conflicts come from the library build's extraction, all at source-chapter times past chapter 1, so none was visible in play:**
  - `obj:ash_peg` is both `in obj:pike_s_left_pocket` and `in obj:wrapped_twist_of_oiled_cloth` (nested containers written as two direct `in`s, chapter 5);
  - the protagonist is both `in place:lower_dock_2` and `in obj:laundry_barge` (chapter 7);
  - `place:ironhold` is in two containers, both CONSTITUTIVE.

  These belong to the build-side "one direct container per move" rule, pattern-buffer's extraction prompt fix, and are sent to them.
- **Chapter 1's objects held for 10 turns** before the hold's twin and the untied packet broke them. Run 11's first break came at turn 9.
- **Timing:** in-turn lifetime classifier calls were 72 (254 s) over 18 measured turns, 4.0 a turn (run 11: 1.8). Settle calls were 30 (220 s). Mean turn wall time was 112 s (run 11: 60 s). This is a different story and a busy machine (load about 30), so it is measured, not explained. The next run's log decides whether it is the content.

### Next fixes (not built; each needs a spec)

- **Bind a container mention to the scene before minting a twin.** "The hold" while the player stands in `place:laundry_hold` should bind to the scene, not mint `obj:hold`. This sits on the resolver's bind-before-mint path, and pattern-buffer's R55 (play-time extraction against what exists at the horizon) is the engine half.
- **NPC staging drift (t4).** Turn 2's "the scullery threshold" was ruled in-scene (underdetermined, no target; g855759 keeps it so), so canon kept the player in the counting room while the prose walked into the passage. A related finding: **the briefing's location anchor ran name-free on almost every turn** of runs 10–12 ("YOU ARE AT the place you now stand in"). It names the scene only from the player frame, and the player frame held no scene name (run 12: 865 rows, zero place names). PLACE-NAME-ANCHOR (spec r1, at cr) gives the player the name of the place they stand in. Each present NPC's in-scene position in PRESENT CHARACTERS is a further option.
- **Chapter-length floor for a continuation arc:** a chapter-2 arc should not reach climax-ready within its first turns. This is a pacing question for R36/R37 (the chapter bridge), and it needs Kabe's view on chapter length.

## Run 13 — the five criteria pass as written, but R20 is not closed: chapter 1's climax event fired on the wrong chain

The monitor authorised this run for Kabe (note n75d6ca). It tests PLACE-NAME-ANCHOR on its own (pattern-buffer's one-location fix stays out until Kabe's paid check). The first attempt stopped at build on unused-handle chunk refusals and is archived as `run13a`. That led to adopting BUILD-LIBRARY r1.9.1. The retry ran on main `e3a459f` with pattern-buffer `c4a8eba`, Codex subscription only, timing log on. Output is archived at `/media/k/Blank/construct-scratch/run13` (world, manifest and critic notes included).

**The build: 335 s**, all 7 chunks extracted with no refusal and no construct re-run (run 12: 410 s, one refusal). Stage 1 took 30 s of wall time (run 12: 59 s).

| # | Criterion | Result |
|---|---|---|
| 1 | Chapter 1 concludes | **PASS on the letter**, at turn 9; the conclusion was a misfire (below) |
| 2 | Chapter 1 ends in a place grown in play | **PASS**: `place:dark_runoff_lane`, minted at t7–t8; absent from the built world (0 rows) |
| 3 | Chapter 2 opens where chapter 1 ended | **PASS**: `place:dark_runoff_lane` both |
| 4 | No ENGINE ERROR or empty prose | **PASS**. One turn (t7) shipped its prose but skipped its world commit after a schema re-ask failed |
| 5 | No critic WHERE breaker | **PASS**: no note reports a teleport or snap-back of the player's place. The three chapter-seam notes are about time and the chain's condition (below) |

### PLACE-NAME-ANCHOR worked

The anchor named the scene on **15 of 15 turns** ("YOU ARE AT: North Quay." on t1–t7, "YOU ARE AT: dark runoff lane." from t8 on). Runs 10–12 had 0/17, 7/23 (all the mis-minted "closed") and 0/15. On t8 the player stepped into a lane minted in play, and that same turn's briefing already named it. No WHERE note was filed in 15 turns, where run 12 had one at t4. That fits the fix but doesn't prove it: one run, a different story.

### Why R20 is not closed: the climax event fired on the wrong chain

The chapter's required climax beat is `beat:pay_the_rivers_timetable`, achieved when the event `fog_bell_window_taken_at_lower_chain` occurs. In the authored story, the **lower chain** is the river boom at the lower chain tower: during the fog-bell watch it is "blind for twelve minutes", Hobb drops it, and the laundry barge gets away (`ironhold_20.md`, "The Lower Chain"). At t9 the player ground his **wrist chain** against a drain-lip in the lane while the fog bell struck, and broke one link. The event detector (`_fire_event_occurs`, `turnloop.py:4004`) fired the kind, the beat was achieved (`justified_by {"turn": 9}`), and chapter 1 concluded with the player still shackled in a lane inside Ironhold.

The detector is given each candidate only as its kind with underscores turned to spaces ("fog bell window taken at lower chain"). It has nothing about what the authored event is, where it happens or who is involved, so a fog bell and a chain in the same action were enough.

### The chapter seam broke on time and the chain (critic ch2 t1–t3, one finding filed three times)

Canon at chapter 1's end has `obj:chain condition broken, whole false` (t9 and t10). Chapter 2's opening reads: "The black river bought you time, not freedom. Enough mornings have passed since the water kept the rope from having you … the chain between your cuffs dragging cold weight at your knees". That is a river escape that never happened in play, days that canon didn't pass (chapter 2's turns follow t9 directly), and a chain whole again. The continuation author wrote the chapter-1 ending the arc *meant*, which the misfired beat told it had happened. Later chapter-2 turns follow canon: the boy sees "the jagged half-link hanging near your left shackle".

### The other critic notes (5 in all)

- **t2:** the opening has Sore look "to the wet boards where Mara says she found him", and Mara then says "Not here … I found Pike at the record room threshold". The opening's prose put a past event in the wrong place. The player's own place never moved.
- **t8:** the critic read "Jory" and "Pike" as two people. They are one man, Jory Pike; Sore says "Jory's papers" and the next lines say "Pike". The critic misread the names, but switching between a first and a last name within a few lines is unclear.

### Also seen

- **Chapter 2 did not end early:** its arc was still active after 6 turns. Run 12's chapter 2 won at its second turn.
- **A twin:** the wrist chain is both `obj:chain` and `obj:tomas_reed_chains` (t9). Nothing contradicted them in play.
- **Timing:** mean turn wall time was 111 s over 15 turns (run 12: 112 s). The world-state extraction call was the slowest step in most chapter-1 turns (45–78 s on t2–t7).

### Next fixes (not built; each needs a spec)

- **Ground the event detector.** Give it each candidate's authored meaning (its places, objects and participants, from the arc and the source story), and have it fire only when the action happens with those. The wrong chain at the wrong place must not fire. This is the most important fix from this run: a false climax ends a chapter and the next chapter is built on it.
- **The continuation opening must read the end state from canon**, not the arc's intended ending: where the player is (already right), and the condition of what they carry. The opening's directive (`_continuation_intro`) gives the place but nothing of what the player carries, so the chain came back whole.
- **The doorway's time jump.** "Enough mornings have passed" is not the author's invention: `_plan_episode_doorway` always jumps the clock to the next calendar phase (the "by morning" seam, #88 S4), and the directive says "after time has passed". With the player mid-escape in a lane, a fixed jump at the same place is incoherent. Kabe's ch2-doorway ruling is "honor implied elapsed time" (a cryosleep of 50 years wakes 50 years later). That reads as: the jump should be the time the ending implies, which may be none. A spec should follow that ruling; it is not built.

## R23 findings: where a turn's time goes now (run 1, 9 instrumented turns; no build yet)

| | July (eval/11) | Tonight |
|---|---|---|
| Whole turn | 400–615 s | 24–252 s; mostly 130–200 s |
| Player-felt (pre-send = cp_generator + narrate) | ≈ 260 s | 48–158 s; typically 85–120 s |
| Snapshot → salience window (serial cheap cohorts) | 128–138 s | 14–65 s |
| Drift and lifecycle | 46–56 s | 0.1–0.4 s |
| Narrate (main tier) | 13–80 s | 15–42 s |
| Player-input ingest, when it runs | ~6 s | 13–30 s |
| Settle tail (post_extract + promote, after send) | ~19–95 s | 25–65 s |
| Classify | 6–9 s | 4.6–7.6 s; 60.8 s on the server-error turn |

Where the remaining time is, largest first:

1. **The salience window.** 30–65 s on most turns. npc_turn, weave_pick and detect_events run as serial cheap calls. eval/11's recommendation stands: run the independent cheap cohorts concurrently. Note that the cheap tier is now `gpt-5.5` on this account; it is slower than a mini model, and that falls exactly on this serial chain.
2. **The settle tail.** 25–65 s, and it grows across turns (post_extract 20→40 s, promote 5→33 s). It runs after the reply is sent, but a fast next message joins on it. Promote's growth over the session is worth a look.
3. **Narration.** 15–42 s on the main tier. Not compressible without the render+capture collapse (TURN-LATENCY "Kernos reframe").
4. **Player-input ingest.** 13–30 s on turns that assert something. The A-lite skip already avoids it on pure questions.

R23 is not built tonight. These are its starting numbers.

A later engine change to watch: pattern-buffer's REFER-LEARNING-V1 (batch D, 2026-10-09) stops pinning an ambiguous reference to one entity, so each ambiguous phrase costs a tier-2 cheap call when it comes up. Expect a few seconds on turns that name an ambiguous thing; check it in the next probe's movement and adjudication timings.
