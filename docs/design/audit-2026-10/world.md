# Audit: the world/scenario/session layer (2026-10-08)

**Scope.** `construct/game.py` (2,949 lines), `session.py` (1,450), `adapter.py`, `registry.py`, `library.py`, `semantics.py`, `session_zero/`, `architect.py`, `foyer.py`, `pins.py`, `journal.py`, `remembrancer.py`.
**Method.** I read every file in scope in full and checked the porcelain surface in `~/pattern-buffer/src/patternbuffer/porcelain.py`. I ran small read-only probes in `.venv` to confirm the bugs marked *confirmed*. The tests for these modules pass: `test_architect`, `test_foyer`, `test_journal`, `test_library`, `test_machine` and `test_session`, 104 passed.
**Read-only.** I changed nothing in the repo.

---

## 0. Bugs (listed separately, most severe first)

| # | Bug | Evidence | Status |
|---|-----|----------|--------|
| B1 | **Every freeform text that names the protagonist gets screened as a spoiler.** `_build_arc` gives every arc the placeholder premise `StateIs(protagonist, "kind", "person")`. `arc_protected_keys` folds the premise into the protected keys, and `concealed_tokens` then turns the protagonist's id into concealed words. | `game.py:2252`; `arc/executor.py:771,795-806`. A probe gave `person:edith_marlowe` → tokens `{'edith','marlowe'}`, and `value_leaks('Edith Marlowe has been your oldest friend', …)` returned **True**. | Confirmed |
| | *Impact.* The over-screening is silent and fails closed. It drops: relationship rows that mention the player's name or surname, at build time (`game.py:1896`); grounding lines in the cold open (`session.py:879`); live threads; build-stamped notebook rows; and Remembrancer declarations, including family members who share the surname, which come back as `memory_screened` (`remembrancer.py:136,172`). | | |
| B2 | **The per-chapter death policy and the new chapter title are computed and then thrown away.** `continue_episode` re-derives `death_policy` (the #95 / Cx 422 "per-chapter" rule) and a new `title`, and returns them in `meta`. The only caller keeps nothing but `continuation_intro` (`transport_core.py:1057-1059`). Session then reloads the shared scenario `.meta.json`, so it uses chapter 1's `death_policy` (`session.py:1092`) and title (`session.py:301`). | `game.py:2911-2941` | Confirmed by reading the code; no test covers it |
| B3 | **Settled history marks the protagonist as "a past chapter's answer".** The #96 S3 "CLOSED HISTORY" is built from `prior_main.shape.premise` / `world_condition` atoms. Because of B1's placeholder the premise is always `person:<prot> · kind · person — ANSWERED`, and `AtLeast` has no entity, so it adds nothing. So the next chapter's author is told the protagonist is closed history. After every continuation the notebook prints `YOU — <name> — settled (a past chapter's answer)`. | `game.py:2671-2677`; `session.py:399-415`; `journal.py:75`. Confirmed by a `render_journal` probe. | Confirmed |
| B4 | **Episode checkpoints show up as scenarios.** `list_scenarios` filters only `*.play.world`, so `*.ep.checkpoint.world` files are listed. Five ghost scenarios are in `worlds/` right now (`bodycase.critic.ep.checkpoint`, …). They reach the CLI list, the CLI pickers (`cli.py:436,452`) and Discord. The transport hides them only because its `_library` skips untitled entries. | `game.py:162-163` | Confirmed (probe) |
| B5 | **`continue_episode` is not atomic and leaks the open world handle.** It writes `settled:episode_N` and `session:personal_threads` (`2684`, `2704`) *before* the calls that can fail (`generate_arc` at `2734`, `_build_arc` at `2746`, the drift check at `2747`). `world.close()` runs only on the happy path (`2907`) and the death path (`2618`); the `finally` resets only the epoch. A failed continuation therefore leaves half an episode in the slot: the notebook shows settled marks with no new chapter, and a retry appends duplicates. It also leaves a SQLite handle open in the long-running bot. | `game.py:2603-2945` | Confirmed by reading the code |
| B6 | **`_finalize_scenario` leaks the entry-epoch contextvar.** It calls `set_entry_epoch` with no reset. That is the same leak Cx 383 fixed in `continue_episode`, where the comment reads "leaking it poisons turn_time() for whoever runs next in the process". | `game.py:540,545` vs `2600-2603, 2943-2945` | Confirmed by reading the code |
| B7 | **Foyer details outside a fixed list are agreed to and then dropped, which breaks truth-keeping.** `FOYER_SCHEMA.field` is open-ended ("name \| gender \| pronouns \| background \| …") and `set_detail` accepts any field. `ingest_character` writes only `_DETAIL_ATTRS = (name, gender, pronouns, background, role)`. If the guest settles "age: 40" or "appearance", the sheet shows it as captured (`summary()`), but the world never learns it. | `cohorts.py:1069-1071`; `foyer.py:37-39,133-135` | Confirmed by reading the code |
| B8 | **An arc proposal that fails to build aborts the whole build instead of retrying.** `_build_arc(proposal)` runs inside the arc retry loop but outside any handler. Empty `beats` raises `IndexError` (`beats[-1]`, `2244`), and an off-enum phase raises `ValueError`; I reproduced both. `author_replan` guards both cases (`2204`, `2208-2214`); `_finalize_scenario` and `continue_episode` do not. | `game.py:690`, `2746` | Plausible (it depends on how strictly the provider enforces the schema) |
| B9 | **The world can carry two contradictory mode flags.** Meta stores both `endless: bool` and `scenario_mode`. Shared library worlds built as freeplay have `endless=True` (`transport_core.py:1313`). If another player opens one with `mode_override="win_loss"`, the session ends up with `_scenario_mode="win_loss"` and `_endless=True` (`session.py:149-150`). `run_turn` then gets contradictory flags: win/loss terminals fire, but the "concluded" pacing is off and there is no `goal_statement`. | `session.py:149-150`; `game.py:1136,1151` | Plausible edge case |

Minor:
- `except RuntimeError: pass` around `seal_build` (`game.py:1249`) treats every RuntimeError as "no session open". Both creation paths always open a build session, so the guard is dead code that can hide real failures.
- Two different stages are both labelled "Stage 6.2" (`1206`, `1243`).
- "Stage 0" is emitted twice in the generated path (`1548`, `1561`).

---

## 1. Status of the July audit findings in this part

| July finding | Status | Evidence |
|---|---|---|
| §4 meta.json and the slot keep the same bookkeeping twice; precedence should be documented in one place and read through one accessor | **WORSE** | Scope now has **three** sources: meta `arc_scope`, the slot row `session:episode.arc_scope`, and `session:scope.independent_extra`. `entry_epoch` lives in meta and in the slot. The precedence is explained in four separate comment blocks (`session.py:106-109`, `247-250`; `game.py:2834-2862`; `transport_core.py:1057`), and there is still no accessor. `continue_episode` builds a new meta that the transport throws away (B2). The meta dict also carries runtime-only keys: `_side_arcs` holds `Arc` objects (`game.py:2371`). There are 9 separate `json.loads(meta_path.read_text()) if exists else {}` sites, across `game.py`, `architect.py:139` and `transport_core.py:627,674`. |
| §4 `_finalize_scenario` (520 lines) needs phase extraction | **WORSE: 827 lines** | `game.py:428-1254`. It has 3 nested retry loops, 25 broad `except`s, and its own nested functions (`_pscore`, `_toks`, `_identity_of`). `cohorts` is imported 3 times under 2 aliases (`788`, `818`, `1181`). |
| §4 `_opening_narration` (149 lines) needs phase extraction | **WORSE: 190 lines** | `session.py:604-793`. |
| §4 Foyer's magic tool-name strings should be an enum shared with the cohort schema | **OPEN** | `foyer.py:269-278` and `cohorts.py:1067-1068` keep separate lists. `architect.py:194-283` has the same pattern with 11 tool strings, and its outcomes are also bare strings (`CONTINUE, BUILD, …`, `architect.py:28`). |
| §5 three `_state_value` copies should be one shared helper in `adapter.py`; the clock copy lacks `as_of` | **OPEN** | The de-facto shared helper is `foyer.state_value` (`foyer.py:89`), in the character-creation module. Session imports it locally 7 times. `clock._state_value` (`clock.py:166`) still lacks `as_of`, which the July audit called "a live horizon bug waiting". `gauge._state_value` (`gauge.py:38`) still unwraps by hand and bypasses `collapse_state`'s conflict telemetry. Nothing moved to `adapter.py`. |
| §3 dead arc fields `phase_budget` and `refusal_variant_id` (written by `game._build_arc`) | **OPEN** | `game.py:2253`, `2282`. `phase_budget` is read only by lint check 6, and no caller passes `session_length_turns` (`arc/lint.py:137`). `refusal_variant` is read back in `arc/io.py:419` and never used. Both also contradict the founder's "turns are free" ruling. |
| Verdict: "the five-verb porcelain boundary is right, keep it" | **HELD, with three local re-folds** | No private engine access in scope; everything goes through `world.porcelain.*`, about 20 methods. Three places fold rows locally, though (finding 6). |

---

## 2. Findings, ranked by value per unit of effort

### F1. Give scenario and playthrough state a type and one accessor (`ScenarioMeta` / `PlaythroughState`)
- **Evidence.**
  - Meta is a free dict read at 9 sites with the same three-line idiom (listed above).
  - Precedence between the slot and meta is re-derived inline in `Session.__init__` (`session.py:105-118`, `251-258`).
  - `open_playthrough` puts runtime `Arc` objects into the persisted-shape dict (`game.py:2371`).
  - `continue_episode` returns a meta that is mostly discarded (B2).
  - Two flags overlap (B9).
  - The word "mode" means two different things: `meta["mode"]` is `pure`/`coauthor` input authority (`game.py:1127`), while `registry.players.mode`, `ArchitectState.mode` and `scenario_mode` are all win_loss/endless.
- **Why it matters.** This is the root of B2 and B9, and it is the July §4 finding, now grown. Every new per-chapter field will hit the same "we wrote it to the wrong place" problem.
- **Fix.**
  - A frozen dataclass `ScenarioMeta` with `load(name)`, `save()` and typed fields: a `ScenarioMode` enum and `input_authority`. It must serialize to **exactly the same JSON keys**.
  - A `PlaythroughState` that layers the slot's `session:episode.*` rows over the meta. One precedence rule, written once.
  - Session takes the `PlaythroughState`. `_side_arcs` becomes a real return value of `open_playthrough`.
- **Size.** M.
- **Safety.** **Polish** for the accessor, as long as the JSON is identical. **Proposal** for fixing B2 properly: persist `death_policy` and `title` per slot as `session:episode` rows, which adds new slot rows.

### F2. Fix the placeholder premise (fixes B1 and B3) and make "latest receipt" one function
- **Evidence.**
  - `game.py:2252` stores a premise that is always true. It feeds `arc_protected_keys` (B1), `continue_episode`'s settled history (B3), and `Session.concealed_truths` (`session.py:492`), which shows the `/ooc` host "Premise (hidden): StateIs(person:x, kind, person)" as if it were the hidden answer.
  - The "latest terminal receipt" is found three different ways in one file:
    - `_episode_fuel` uses `events(...)` with `max(at)` (`2395-2396`);
    - `_episode_doorway` parses the turn number out of the event id (`2539-2554`);
    - `_prior_shape` parses the id again, with an `isdigit` guard (`2874-2876`).
    - `turnloop.terminal_outcome` is a fourth.
  - Parsing meaning out of id text is the pattern the MOVED-EVENT contract forbids ("NEVER id-grammar").
- **Fix.**
  - Make `ConclusionShape.premise` optional, or have `arc_protected_keys` skip the protagonist's `kind` key.
  - Build settled history from what the chapter actually answered: the achieved `player_learns` beats, read off the beat status rows.
  - Add one `latest_outcome_receipt(reads) -> (entity, rows)` that orders by `valid_from` / event time, and use it in all three places.
- **Size.** S–M.
- **Safety.** **Proposal**, because it changes concealment and the arc format. The receipt helper alone is **polish**.

### F3. `continue_episode`: compute first, commit once, close in `finally`
- **Evidence.**
  - 374 lines (`game.py:2572-2945`) that alternate reads, model calls and writes (B5).
  - About 15 lines compute `_open_epoch` (`2776-2791`, the "Cx 382 blocker" block) and pass it to `_episode_doorway(world, protagonist, epoch, turn)`, which **uses neither `epoch` nor `turn`** (`2496-2569`). The computation is dead.
  - The comment at `2792-2798` says the doorway "returns to the prior episode's OPENING place". That is the reverse of the G-C invariant `_episode_doorway` actually implements: "opens WHERE THE STORY ENDED".
  - `frame_facts` is re-imported 5 times under different aliases (`_ffs`, `_ffp`, `_ffr`, `_ffu`, `_ffd`).
- **Fix.** Split into:
  - `gather_continuation(reads)`: a pure read, returning a dataclass with fuel, settled, personal, regions, prior shape and callback.
  - `author_next_arc(...)`: model calls only, and it calls `_build_arc` inside a handler.
  - `commit_episode(world, plan)`: one ordered write batch.

  Wrap it all in `with _open_slot(...) as world:` plus a public `entry_epoch()` context manager (F9). Delete the dead `_open_epoch` block and the unused parameters, and fix the comment.
- **Size.** M.
- **Safety.** Polish for the restructure. The B5 fix changes failure behaviour only.

### F4. Break up `_finalize_scenario` into named build stages
- **Evidence.** 827 lines (`game.py:428-1254`). Inside it:
  - Stage 2's identity pass is 60 lines of nested pair loops with `_`-prefixed locals (`459-515`).
  - The arc authoring loop includes a 60-line inline prompt (`629-689`).
  - Cast authoring (`807-937`) has its own retry loop, plus the canon-admission rows for disambiguated persons (`906-925`).
  - Seal and meta assembly come last (`1125-1253`).
  - Three hand-written "retry ×3 with feedback" loops: laws (`366-409`), arc (`628-756`) and cast (`850-932`).
  - The "honour play_as" token match is written twice with different tokenization (`604-610` drops only `:`; `715-718` also drops `_`), and a third time in `_fallback_protagonist` (`2144-2149`).
- **Fix.**
  - A `BuildContext` dataclass (world, reads, provider, known_ids, located_people, digest, laws_block, on_stage).
  - One function per stage: `reconcile_identity`, `declare_policy`, `establish_epoch`, `author_arc`, `author_cast`, `vouch_merges`, `commit_arc`, `seed_knowledge`, `stage_cast`, `author_meta`, `seal`.
  - One `retry_with_feedback(author, validate, attempts=3)` helper.
  - One `_play_as_match(world, play_as, ids)` helper.
  - The Cx/#-letter commentary (around 40% of the lines) moves to the stage docstrings or `docs/`, keeping a one-line pointer.
- **Size.** L, done stage by stage with the suite green between moves.
- **Safety.** Polish. Unifying the play_as tokenizer changes matching slightly; flag that in review.

### F5. Split `game.py` by responsibility, starting with arc construction
- **Evidence.** `game.py` holds five modules:
  1. file layout: paths, slots, checkpoints (`130-168`, `2288-2341`);
  2. the build pipeline (`353-1599`);
  3. arc-from-proposal construction: `ARC_SCHEMA`, `_beat_expr`, `_failure_expr`, `_build_arc`, `author_replan`, `ReplanOutcome` (`51-118`, `199-229`, `2156-2285`);
  4. knowledge seeding and inspection (`1751-2016`);
  5. episodes (`2298-2945`).

  `arc/generator.py:479` and `tangent.py:318` import the **private** `game._build_arc` with the comment "deferred — avoids an import cycle". That signals that arc construction belongs in `construct/arc/`.
- **Fix.** Create:
  - `construct/arc/authoring.py` for (3), which removes the cycle;
  - `construct/worldfiles.py` for (1) plus the F1 accessor, and fix B4 there with one `is_scenario_file()`;
  - `construct/build.py` (F4), `construct/seeding.py` and `construct/episodes.py`.

  Keep `game.py` as a thin re-export so the CLI and transports don't change.
- **Size.** M for the arc piece alone; L in full.
- **Safety.** Polish.

### F6. Rules enforced in several places: concealment screen, frame folds, display names
- **Concealment screen.**
  - The "screen by provenance" rule ("build-stamped rows get the key and token screen; rows learned in play show") is written twice: `Session.journal._shows` (`session.py:376-383`) and `remembrancer.build_sheet` (`remembrancer.py:57-64`).
  - `live_threads` keeps its own `_leaks` tokenizer (`session.py:1000-1004`), although its docstring and `executor.value_leaks` both say it uses the shared one "so the two cannot drift" (Cx 337).
  - `_establishing_anchors` screens protected keys but never `value_leaks` (`session.py:956-960`).
- **Frame folds.** `journal.render_journal` (`46-57`), `remembrancer.build_sheet` (`59-63`) and `remembrancer._existing_value` (`80-91`) each hand-fold "latest value per (entity, attribute)" over raw `frame_facts`. That is a local re-implementation of the engine's fold. It ignores fold policy: a constitutive key serves its earliest value, and conflicts are flagged.
- **Display names.** At least 5 near-copies: `Session._display_name` (`573`), `disp` inside `_establishing_anchors` (`936`), `foyer.world_anchors` (`117`), `journal._humanize` (`26`), and `remembrancer._slug` vs `game._slug`. The id-humanizing idiom `split(":", 1)[-1].replace("_", " ")` appears 23 times across `construct/`, 13 of them in turnloop.
- **Fix.**
  - One `player_frame_rows(world, prot, arc, horizon)` in `arc/executor.py`, next to `value_leaks`, used by the journal and the Remembrancer. `live_threads` and `_establishing_anchors` call `value_leaks`.
  - One `humanize_id()` and one `display_name(reads, entity, frame=None)` in `adapter.py`.
  - For the folds, ask PB for a fold that keeps provenance (a `snapshot(frame=…)` that returns `valid_from` per fact) and drop the local folds.
- **Size.** S–M.
- **Safety.** Polish for the screen, the names and `live_threads`. **Proposal** for the fold change, which is a porcelain request.

### F7. Make the Foyer and Architect tool vocabulary typed, and close the open `field`
- **Evidence.** `foyer.py:265-278` and `architect.py:191-285` dispatch on string literals that are repeated in `cohorts` schema enums. The Foyer's `field` is unconstrained, and that is the cause of B7. Session reaches into the private `foyer._DETAIL_ATTRS` (`session.py:423`).
- **Fix.**
  - `class FoyerTool(StrEnum)` and `class ArchitectTool(StrEnum)`, with the cohort schema `enum` generated from them.
  - Dispatch through a dict of handlers; `architect_step`'s 114 lines become small named handlers (`_on_begin_build`, `_on_reroll`, …).
  - Make `field` an enum over a public `DETAIL_ATTRS`, or route any other field into `additions`.
- **Size.** S–M.
- **Safety.** Polish for the enums. Changing the `field` schema is a cohort change, so **proposal**.

### F8. `Session.__init__` and scope provenance: one `_rebuild_scope()`
- **Evidence.**
  - `__init__` is 185 lines (`session.py:83-267`).
  - The formula `independent ∪ ⋃ arc_entities(episode_arcs) filtered by has_entity` is written three times: in `__init__` (`128-241`), `_refresh_beat_scope` (`1346-1364`) and `_reload_arc_portfolio` (`1366-1404`).
  - Defensive `getattr(self, "_sealed_beat_scope", set())` and `getattr(self, "_independent_scope", …)` guard attributes that `__init__` always sets (`219`, `1360`, `1383`). `_pending_image` and `_last_image` are never initialized and are always read with `getattr`.
  - `_horizon()` runs a full `events(kind="turn")` scan on every call, and `_opening_narration` calls it about 12 times per open.
- **Fix.**
  - A `ScopeProvenance` dataclass (sealed_beats, live_beats, independent) with one `rebuild(reads)` method.
  - Initialize every attribute in `__init__`.
  - Cache the turn number per turn.
  - The per-shape directives (`153-179`) collapse into one `ShapeProfile` lookup.
- **Size.** M.
- **Safety.** Polish.

### F9. Private reach-ins and import hygiene; add a public epoch context manager (fixes B6)
- **Evidence.**
  - `game.py:2945` does `_arc_executor._ENTRY_EPOCH.reset(...)`.
  - `session.py:806` imports the private `turnloop._colocated` and `_departed_from`.
  - `foyer.py:139` imports the private `game._world_digest`.
  - `library.py:17` imports the private `game._slug`.
  - The `adapter` import is repeated locally even though `game.py` already imports `adapter` at the top (`1924`, `1928`, `2069`, `2116`, `2538`, `2678`, `2764`, `2868`, `2890`).
- **Fix.**
  - `@contextmanager def entry_epoch(e)` in `arc/executor.py`, used by `_finalize_scenario`, `continue_episode` and `Session.turn`.
  - Promote `colocated()` to a public presence helper, in `resolve.py` or `adapter.py`.
  - Make `world_digest` and `slug` public, in `worldfiles` or `adapter`.
  - Hoist the imports.
- **Size.** S.
- **Safety.** Polish. B6 becomes a no-op fix.

### F10. The build-stage messages are a string protocol shared with the transport
- **Evidence.** `game._emit` sends free text, and `transport_core._STAGE_LINES` (`1696-1711`) **substring-matches** it. Rewording a stage message silently drops it from the player's progress bar; continuation stages already fall through to the generic fallback. Also: the duplicate "Stage 6.2" and "Stage 0" labels, and the comment above "Classifying durability" still describes "hundreds of serial classify calls", which has been false since rules-only classification became the default (`game.py:1241`).
- **Fix.** A `BuildStage` enum carrying (operator text, player text). `_emit(on_stage, BuildStage.RECONCILE)` passes the enum, and the transport maps by identity.
- **Size.** S.
- **Safety.** Polish.

### F11. Prompts: the arc-authoring prompt and the continuation directives
- **Arc-authoring prompt** (`game.py:629-689`).
  - It repeats the `ARC_SCHEMA` descriptions almost word for word. The `goal_statement` guidance appears at `56-65` and again at `647-653`; `failure_when` at `66-76` and again at `654-661`. That is about 25 lines said twice on every attempt.
  - It stacks two "HARD RULE"s plus "INSIST ON AN INTERESTING DESTINATION". The conditional blocks (laws, win_direction, play_as, lint feedback) are already well done.
  - *Fix:* move the guidance into the schema only (where the model reads it next to the field), and keep the prompt to SITUATION (available ids, digest, laws, player asks) plus one directive.
- **Continuation directives contradict each other.**
  - `_episode_fuel` always appends "time has passed and their reputation precedes them" (`2409-2417`). That is the very formula `_continuation_intro` forbids two functions later ("no obligatory 'time has passed' or 'you made a name on that one'", `2479-2481`), the opener the founder called "4-for-4 identical".
  - Inside `_continuation_intro`, the doorway clause says "after time has passed" (`2483`) while the body says "time may pass or not" (`2479`). The doorway really does commit a time jump (`_episode_doorway`), so truth-keeping says to state the actual elapsed time as SITUATION and drop the latitude clause.
- **Opening brief** (`session.py:711-769`). The "PRESENT WITH YOU" block injects an investigation-specific rule ("the investigative authority naturally frames why everyone is here, a witness gives their own firsthand account") for **every** genre whenever anyone is present. By the tenet, a niche rule should be injected only when it applies (deduction shapes), or reduced to the generic principle ("each speaks only from their own role").
- **Size.** S per item.
- **Safety.** **Proposal**, since prompt wording changes behaviour. Extracting the brief assembly into a pure, testable `build_opening_brief(...) -> list[str]` is **polish**.

### F12. Meta keeps copies of engine truth (the membrane)
- **Evidence.** These meta fields duplicate or are derivable from engine state:
  - `protagonist`: also the `arc:main.protagonist` row. The #107 seal-lint (`game.py:975-1002`) exists only because these copies can split.
  - `main_arc` / `arc_ids`: a copy of the `arc:portfolio` rows, which `open_playthrough` overwrites anyway (`2369-2372`).
  - `arc_scope`: derivable from arc plus cast; Session rebuilds it at open.
  - `laws`: copied from the canon `law:*` rows "for cheap read".
  - `seeded_frames`: derivable from the `knows:*` frames.
  - `endless`: duplicates `scenario_mode` (B9).

  Host-authored outputs (style, intro, premise, goal_statement, genre, death_policy, cast proposal) legitimately belong in meta.
- **Why it matters.** "Derived state is never stored." Each copy needs its own lint or precedence rule, and each one is a place for drift bugs to appear.
- **Fix.** Stop writing the copies and derive them through the F1 accessor, which reads the engine. Keep reading the legacy keys for old worlds.
- **Size.** M.
- **Safety.** **Proposal** (meta format change).

### F13. An engine gap worked around locally: `_live_in_candidates`
- **Evidence.** `game.py:2065-2077` re-implements the as-of current-layer fold over raw `in` rows: "rows at the max valid_from ≤ as_of", deduplicated by first appearance. It exists because `porcelain.locate()` collapses same-timestamp co-assertions to the first-inserted row (#109). That is engine semantics rebuilt in the host.
- **Fix.** Ask PB for `locate(..., candidates=True)` or a `co_asserted(entity, "in", as_of)` read, then delete the local fold. Until it ships, keep the code and label it as a workaround with the PB request id.
- **Size.** S on the host side.
- **Safety.** **Proposal** (changes how construct calls the porcelain).

### F14. Dead code and names or comments that are wrong
- `construct/session_zero/` (`machine.py`, 124 lines) is never imported in production; only `tests/test_machine.py` uses it. The live session zero is `architect.py` plus `foyer.py`. Delete it and its test, or move it to the docs attic.
- `Session.establishing_lines` is test-only (`session.py:1029`).
- `_episode_doorway`'s `epoch` and `turn` parameters are unused (F3).
- `_hidden_terms(world, …)` and `_player_goal(…, world, …)` take `world` and never use it (`game.py:1684`, `1728`).
- `SEED_CONCURRENCY`'s comment and `seed_character_frames`' docstring both say "Default 1 = sequential", but the default is `"3"` (`game.py:1755-1760`, `1795`).
- `create_scenario_from_ingest` and `create_scenario_from_interview` each close the world twice (an `except BaseException` close plus a `finally` close, `1358-1364`, `1416-1422`) and share a cleanup they could share as code: `_publishing(spath)`.
- `_unpublish_scenario` removes only the default slot, not per-player slots or checkpoints (`1461-1468`).
- `reseed_character_frames`, the "reversibility hook" of founder letter 041, is reachable only from tests; no CLI command exposes it.
- **Size.** S.
- **Safety.** Polish. Deleting `session_zero` is behaviour-preserving, since nothing in production uses it.

---

## 3. What is in good shape (keep as is)

- **`adapter.py`.** A small, honest boundary: horizon-bound reads, `frame_rows` documented as the horizon-safe scan, one `collapse_state` policy. It is the right home for the shared `state_value` and `display_name` (F6, July §5).
- **`registry.py`.** Atomic invite claim, exactly-once outbox, idempotent migrations. The only nit is the repetitive get/set-column pairs with `import json` inside functions; low value to touch.
- **`pins.py`.** A pure, deterministic function with clearly reasoned edge cases. A model module.
- **`semantics.py`.** One clear seam into the engine's RFC-001 hook. Correctly declarative.
- **`library.py`.** A thin wrapper over the build; fine apart from the `_slug` reach-in.
- **`remembrancer.commit_declared_memory`.** The authority rules are well layered (autobiography, framed belief, quarantine). It suffers only from B1 and the duplicated folds (F6).

## 4. Suggested order

1. **This week, safe and small:** F9 (fixes B6), the B4 file filter, B5's `finally: world.close()`, F10, F14.
2. **Founder call, small but high value:** F2 (B1 and B3), B2's per-slot persistence, B7's field enum, F11's prompt fixes.
3. **Structural polish, one branch per item with the suite green:** F1, then F5 (arc piece first), F3, F4, F8, F6.
4. **Founder and PB:** F12 (meta copies), F13 (the `locate` candidates request), the provenance-keeping fold from F6.
