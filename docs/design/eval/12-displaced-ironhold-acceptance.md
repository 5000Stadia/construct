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
