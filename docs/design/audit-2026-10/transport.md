# Audit: transports, CLI, imagery, play styles, holo

Scope: `construct/transport_core.py` (1,754 lines), `telegram_bot.py` (244), `discord_bot.py` (477), `loopback.py` (110), `repl.py` (112), `cli.py` (727), `setup.py` (176), `imagery.py` (448), `play_styles.py` (106), `play_styles_data.py` (781, generated), `construct/holo/` (deck 418, vocab 334; light touch).

Method: I read every file in full and grepped across the tree for callers. Two of the bugs below were reproduced with scratch tests kept outside the repo (`scratchpad/audit/repro/`); both reproductions pass, which confirms the bugs. The existing suites are green: `tests/test_telegram.py`, `test_cli.py`, `test_imagery.py`, `test_play_styles.py` and `test_holo_*` give 203 passed. The repo was not modified.

## Are the transports thin clients over one session API?

**Partly.** Telegram, the loopback channel and the terminal REPL are thin adapters over `TransportCore`. Each is 110 to 250 lines of IO plus exactly-once bookkeeping. The `InboundEvent`/`Outbound` pair, the injectable session factory and the durable outbox are good shapes, and they should be kept.

The picture breaks down in two ways:

1. **`TransportCore` is not a pipe; it is the player-lifecycle product.** Its docstring calls it "the dumb pipe". In practice it owns all of the following:
   - the Atrium (the conversation before a world is chosen)
   - the Foyer (character creation)
   - a three-step restart state machine
   - chapter-end and continue handling
   - death terminals
   - the shared world shelf, including moving world files to the attic on disk
   - the player's notes, status, `/ooc`, `/feedback` and transcripts
   - build retries
   - the image layout policy
   - operator process control (`/reboot`)

   In total that is about 50 methods. The result is two session APIs: `Session` for in-world play and `TransportCore` for lifecycle.
2. **Three clients bypass `TransportCore` and talk to `Session` directly, each with its own partial lifecycle.**
   - `discord_bot.py` has no invite gate, no Foyer, no chapters and no images.
   - `cli.py` has `play`, `turn` and the bare-`construct` shell. The shell uses a separate agent (`cohorts.entry_agent`) and a separate save slot.

## July audit (AUDIT-2026-07-FRESH-EYES §5 / P4): status

| July finding | Status | Evidence |
|---|---|---|
| Three chunkers (transport_core / telegram / discord) | **PARTLY FIXED** (3 → 2) | Telegram now uses `transport_core.chunk` (`transport_core.py:156`). Discord still has its own (`discord_bot.py:104`), and the two behave differently: Discord falls back to a space boundary and turns empty text into "(the world is quiet)", while core hard-cuts and returns `""`. |
| Discord bypasses TransportCore (no invite gate, no scenario scope lock) | **OPEN, and worse in effect** | Discord still calls `Session.open` directly (`discord_bot.py:179`). `!play <any name>` reaches any scenario, including other players' `live_*` builds (`:285-291`). Any DM user can attach a `.txt` and trigger a metered ingest (`:327-358`). Since July, TransportCore gained the Foyer, chapter end and continue, the death terminal, the notebook, notes, status, scene images and `/ooc`, and Discord has none of them. README.md:32 still says "Discord works too". |
| imagery.py re-implements Codex auth/SSE | **PARTLY FIXED** | Auth and headers are now borrowed from `CodexProvider`, but through four private members: `p._read_auth()`, `p._headers()`, `p._base_url` and `p._cheap_model` (`imagery.py:358-361`). The SSE block splitter is still a copy of `provider._collect_sse_text` (`imagery.py:385-392` vs `provider.py:484-493`). The OpenAI image backend hand-rolls httpx instead of using `OpenAIProvider` auth. |
| Config sprawl, no startup validation | **OPEN** | About 35 environment variables across `CONSTRUCT_*`, `HOLODECK_CODEX_*` and `OPENAI_*`, read ad hoc (Discord reads at import time, `discord_bot.py:42-56`). Nothing validates them at startup. `CONSTRUCT_IMAGE_SIZE` has two defaults depending on the backend: `1536x1024` at `imagery.py:362` and `1024x1024` at `:436`. `.env` is read only for the Telegram token (`setup.py:56-75`). |
| P4 transport unification | **OPEN** | See Findings 5 and 6 below. |

---

## Actual bugs (fix first)

### BUG 1: `/exit` (or `/wipe`, `/disconnect`) after "End of Chapter" leaves the continue prompt armed. The next start-menu message builds a new chapter. **Reproduced.**
- `_pending_continue.add(pid)` happens at `transport_core.py:1025`.
- `_exit` (`:590-599`) and `_wipe_data` (`:528-533`) clear every other pending set but not `_pending_continue`.
- In `handle` (`:273-290`), any later non-command, non-"no" message goes to `_do_continue`, which runs `continue_episode` (`game.py:2572`). That is a real model-cost chapter build over the world the player just left, while they sit at the start menu.
- Repro: chapter ends, then `/exit`, then `list` gets the reply from `_do_continue`. A second repro shows that `/wipe` keeps the arm.
- **Fix:** a single `_clear_pending(pid)` called from `_exit`, `_wipe_data` and `_enter_world`. The structural fix is Finding 2. **S. polish (bug fix).**

### BUG 2: Telegram outbox head-of-line wedge. One permanently failing chat silences every player. **Reproduced.**
- `process_updates` calls `flush_outbox` first (`telegram_bot.py:158`).
- `send_message` raises on any non-ok status (`:92-93`).
- The outbox has no attempt count and no dead-letter state (`registry.py:442-466`).
- So a 403 (the user blocked the bot) or a permanent 400 on one row raises before any new update is handled. The offset never advances and `serve` retries the same thing every 2 s, forever (`:237-243`).
- Repro: a "blocked" chat's reply fails, after which a healthy player's three later messages are never answered.
- An aggravating factor is that Telegram's 4096 limit counts UTF-16 code units, while `chunk` counts code points. A chunk heavy in emoji (the menus and the 155-name styles wall are emoji-dense) can exceed the limit and trigger exactly this permanent 400.
- **Fix:** classify send failures. Retry 429, 5xx and network errors. Dead-letter any other 4xx (mark the row failed, log it, move on). Chunk Telegram text by UTF-16 length. Send with POST JSON rather than GET query params (`:86`). **S–M. polish (bug fix).**

### BUG 3: The "restart just this chapter" option is unreachable since episodic continuation shipped.
- `_in_episodes` always returns `False`, with a comment saying "Episodic continuation isn't built yet" (`transport_core.py:502-508`).
- It is built: `continue_episode` checkpoints each chapter boundary (`game.py:2910`).
- So a player in chapter 3 who types `/restart` is only offered "from the beginning", which erases every chapter. `_pending_restart`, `_do_restart` and `restore_episode_start` are dead code (`:313-321`, `:363-402`).
- **Fix:** derive `_in_episodes` from a game accessor (an episode count above 1, from the `settled:episode_*` records or a meta counter). **S. proposal** (it changes a destructive user flow).

### BUG 4: The restart-confirm answers are parsed by substring on destructive paths, and commands are swallowed.
- `_do_restart_notes`: `"yes"` is in the wipe list (`:437`), so "yes, keep them" **wipes the notes**. The docstring says "Ambiguous → keep".
- `_do_restart_original`: the redo list includes `"new"`, `"again"` and `"2"` and is checked first (`:413-417`). So "keep my character, new name" **discards the character**.
- At step 3, any message that is not a cancel word, including `/help` or `/feedback …`, **executes the restart** (`:438-440`). The live `/feedback`-swallowed bug was fixed for `_pending_continue` only (`:275-279`).
- **Fix:** match exact choices (`keep` / `redo` / `wipe` / `cancel` / `1` / `2`) as whole words, re-ask on anything ambiguous and keep the state armed, and let commands pass through. **S. polish (bug fix; ambiguous answers now re-ask).**

### BUG 5: Operator commands have no operator check.
- `/reboot` (re-execs the whole bot process, `:561-588`), `/disconnect`, `/wipe`, `/dump` (reveals an absolute server path, `:1480`) and `/remove` (moves any shelf world, including house worlds and other players' builds, to the attic, `:811-846`) are routed for **every claimed player** (`:332-341`, `:793`).
- Any invited tester can kill everyone's in-flight 20-minute build. The standing rule is "no reboot during in-flight builds".
- **Fix:** an operator allowlist (registry column or a single config value), with the commands hidden and refused for everyone else. **S. proposal** (the founder decides who counts as an operator).

### BUG 6: `/wipe` claims "clean slate, no saves" but misses most saves.
- `_wipe_data` deletes the current scenario's slot, plus a built-world name `live_{plat}_{ext}` (`:521`) that no build has used since builds became `live_{plat}_{ext}_{n}` (`:1279-1283`). The `_unpublish_scenario(built)` call is therefore a no-op.
- The player's slots in every other world survive.
- **Fix:** delete every `*.{safe_pid}.play.world` and `*.{safe_pid}.ep.checkpoint.world` belonging to that player. Drop the stale unpublish, because built worlds are now shared shelf entries. **S. proposal** (changes what a destructive command deletes).

### BUG 7 (holo, small): the deck prompt contains a literal `{PREFIX}`. **Verified.**
- `deck.py:450-452`: the `f` prefix sits on the line before the one that holds `{PREFIX}`, so the model is told `Ids start with "{PREFIX}"`.
- The schema pattern and `check_deck` catch bad ids, so the cost is wasted repair rounds.
- **Fix:** move the `f`. **S. polish.**

### Smaller doc lies
- The `/reboot` docstring says the re-exec re-reads `.env` (`:565-566`). `os.execv` keeps the parent's environment, and only the Telegram token is ever read from `.env`. Editing `.env` to change `CONSTRUCT_PROVIDER` and then sending `/reboot` changes nothing.
- README.md:32 says "bare `construct play` resumes", but `play` requires a scenario argument (`cli.py:84`).
- The `cli.py` docstring says "Two surfaces over ONE turn function (`turnloop.run_turn`)". There are now five entry surfaces, and they go through `Session`.

---

## Findings, ranked by value per effort

### 1. Pending prompts: replace six ad-hoc sets with one tagged state per player. **M. polish.**
- The six sets and dicts are `_pending_exit`, `_ooc_pressed`, `_pending_restart`, `_pending_restart_original`, `_pending_restart_notes` and `_pending_continue` (`transport_core.py:194-208`).
- Each one is cleared by hand in some places and forgotten in others; that is the root cause of BUG 1.
- `handle` (`:238-347`) is a priority ladder over them, with the same `self._log(ev, "BOT", …)` repeated six times.
- **Why it matters:** it is the most bug-dense structure in the file (BUG 1, BUG 4, and the earlier `/feedback`-swallowed live bug), and every new confirm flow adds another set.
- **Fix:**
  - `self._pending: dict[str, Pending]`, where `Pending` is a small frozen dataclass (`kind: Literal["exit","restart_depth","restart_character","restart_notes","continue"]`, `data: dict`).
  - A handler table keyed by `kind`.
  - Uniform rules in one place: a command passes through and leaves the prompt armed; leaving a world clears it.
  - `handle` becomes `out = self._route(...)`, followed by a single log line.
- `_ooc_pressed` is a separate flag, not a prompt, so it stays a set.

### 2. One command router, not two. **S–M. polish.**
- `handle` routes `/restart`, `/play`, `/wipe`, `/disconnect`, `/reboot`, `/dump` and `/exit` in an elif chain (`:299-343`).
- `_command` routes the rest with a second chain (`:769-808`), and `/play` appears in both (`:299-310` and `:795-807`).
- **Fix:** one `COMMANDS: dict[str, Callable]` table, with an `operator=True` flag on the hidden commands. This is also where BUG 5's gate attaches. `HELP` could be generated from the table so the two never drift.

### 3. Give `TransportCore` a player handle and a single session-open path. **S. polish.**
- There are 83 `registry.x(self._conn, ev.platform, ev.external_id, …)` calls.
- There are seven copies of "read the mode, call `_valid_mode`, read the scenario, `self._sessions[pid] = self._session_factory(...)`, try/except, then a '(could not open…)' reply": `:480`, `:801`, `:871`, `:982`, `:1052`, `:1151`, `:1216`.
- None of them closes the session it replaces: there is no `.close()` anywhere in the file, and `_exit`, `_wipe_data` and `_do_continue` simply `pop`. As a result, old PB world connections stay open, including on slots that `_drop_slot` or `restore_original` just unlinked.
- **Fix:** a `PlayerRef(conn, platform, ext)` with methods (`.scenario`, `.started`, `.mark_started()`, …), plus `_open_session(pid, ref, *, fresh) -> Session` that closes the predecessor. This is mechanical and suite-gated.

### 4. Split `TransportCore` along its real seams. **L, staged. polish** (pure moves).
- Today's 1,360-line class mixes five concerns:
  1. the chat protocol: gate, routing, chunking, transcript
  2. the lifecycle state machine: Atrium → Foyer → play → concluded → continue, plus restart
  3. the shelf: `_library`, `_catalog`, `_world_menu`, `_remove_world` with direct file moves into `attic/`, `_genre_emoji`, `_styles_wall`
  4. operator tools: `/reboot`, `/wipe`, `/disconnect`, `/dump`, `/feedback`
  5. presentation copy and build-progress humanizing (`_STAGE_LINES`, `_StageProgress`)
- **Fix:** a `construct/chat/` package with `router.py`, `lifecycle.py`, `shelf.py`, `operator.py` and `copy.py`. Do it after Findings 1–3 so the moves are small.
- Related reach-ins to remove in the same pass:
  - `session._meta["continuation_intro"] = …` (`:1059`) should become a `Session.open(..., opening_note=)` parameter, or the value should be read from the slot.
  - meta.json is parsed directly at `:627` and `:674` (and in architect and game); add a `game.scenario_meta(name)`.
  - `_styles_wall` reads `STYLE_CARDS` directly (`:1580`); add `play_styles.families()`.
  - `story_shapes` imports the private `play_styles._norm`.
  - `loopback.py` reads `core._platform` five times (`:70-85`).

### 5. Exactly-once delivery is written three times. Write it once. **S–M. polish.**
- The order "claim → handle → record_outbox → send → mark_sent → settle" is coded separately in `telegram_bot.process_updates`, `_send_pending` and `flush_outbox` (`:143-192`), in `loopback.pump` and `_flush` (`:53-90`), and in `repl._turn` (`:68-85`).
- **Why it matters:** this order is the exactly-once invariant that Codex reviewed. Three copies means BUG 2's dead-letter fix would have to land three times.
- **Fix:** `transport_core.deliver(conn, core, ev, uid, send: Callable[[str, str], None])` plus `flush(conn, platform, send)`. Each adapter keeps only its IO.

### 6. Discord: retire it or port it. Stop advertising it in its current state. **M. proposal.**
- See the July table. It is a different, older product that sits behind an "invite-only" brand.
- It also has the better concurrency model: a per-player mailbox, burst coalescing, and a per-player owner thread that respects PB's `check_same_thread` (`discord_bot.py:155-173`).
- **Fix, either:**
  - (a) Delete it and drop the README line, or
  - (b) Rewrite it as a roughly 150-line adapter over `TransportCore`, keeping the mailbox and owner-thread executor and dropping `_handle_command`, `_Pipe._open`, the custom chunker and the attachment ingest (or gating them behind operator status).

### 7. Telegram serializes all players on one thread. A 20-minute build freezes everyone. **M–L. proposal.**
- `process_updates` handles updates in sequence (`telegram_bot.py:160-181`), and `TransportCore.handle` runs the whole build inline, including `time.sleep(BUILD_RETRY_DELAY_S)` (`transport_core.py:1328`).
- The class docstring says the adapter "serializes per-player". In fact it serializes globally.
- **Fix:** lift Discord's per-player owner-thread executor into a shared adapter base. Telegram then dispatches each update to its player's worker, and the offset advances once the update is durably claimed, since the outbox already makes sending safe. This needs care around the shared registry connection (one connection per thread, or a lock), so it goes to the founder.

### 8. Scene images: two delivery policies and an untyped holder. **S–M. polish.**
- The turn path waits 12 s and then sends the picture late (`transport_core.py:1370-1416`).
- The opening path calls `session.pending_image()` with its default **75 s** timeout (`session.py:1300`, called at `transport_core.py:1441`). That blocks the poll thread for up to 75 s, and a late image is dropped rather than sent late.
- The handoff is a raw dict `{"rec", "done"}` (`session.py:1291-1298`).
- `Outbound.image` is never set (`transport_core.py:152`). `Reply.image` (`session.py:1130`) is never read by any transport.
- **Fix:** a `PendingImage` dataclass (`rec`, `done: Event`, `ready(timeout) -> path|None`) and one `_deliver_image(ev, pending, *, before_text_s, late_s, caption)` that both paths use. Delete the two dead fields.

### 9. Imagery should use a public provider streaming method, not private reach-ins. **M. polish.**
- `_codex_dispatch` (`imagery.py:342-424`) reaches into four private `CodexProvider` members and re-parses SSE by hand.
- **Fix:** add `CodexProvider.stream_events(body) -> AsyncIterator[dict]`, factored out of `_collect_sse_text`, and make `_collect_sse_text` and imagery both consume it. Route `_openai_dispatch`'s auth through `OpenAIProvider` too. This is behaviour-preserving, and the provider stays the single owner of auth and transport.
- While in this code:
  - `_codex_available` re-imports `Path` as `_P` (`:310`).
  - The depict-only constraint is written twice, once in `compose_prompt` (`:150-154`) and again in the Codex `instructions` (`:371-375`). Keep a single copy, in the deterministic `compose_prompt`.

### 10. Three CLI front doors, two conversational agents, two save namespaces. **M. proposal.**
- Bare `construct` runs `_cmd_shell` (`cli.py:439-485`). It uses `cohorts.entry_agent` (its only caller), runs no Foyer, and saves to `X.play.world`.
- `construct start` runs `repl.serve`, which goes through `TransportCore` with the architect agent and the Foyer, and saves to `X.cli_<user>.play.world`.
- `start --classic` is a third, flag-wizard door.
- `play` and `turn` use the default slot. So a game started under `construct start` is invisible to `construct play X`.
- **Fix:** make bare `construct` mean `start`. Retire `_cmd_shell`, `_shell_open`, `_unique_setting_name` and `cohorts.entry_agent`. Keep `play` and `turn` for scripting, but make them accept `--player` (defaulting to the terminal identity) so both doors share one save. Moving existing slots is a migration, which is why this is a proposal.

### 11. Delete dead code. **S. polish.**
- `_interpret_mode`, `_WIN_LOSS_CUES`, `_ENDLESS_CUES` and `_ASKING` (`transport_core.py:1550-1626`) are used only by tests (`tests/test_telegram.py:22, 967-983`). `_MODES` stays, because `_valid_mode` uses it.
- `Outbound.image`.
- `play_styles.card()`, which has no caller.
- `_wipe(..., now=)`, an unused parameter (`:542`).
- The local re-imports of `threading` and `time` inside `_reboot` (`:572-574`).
- After BUG 3: either `_in_episodes` becomes real, or the episode branch goes.
- Rename the incident codes left in comments to what they mean. Examples: "TURN-LATENCY dumbfire, Cx 266 #2" should become "drain the previous turn's deferred writes first", and "#95 (Cx 422)". The letter number can stay in parentheses.

### 12. `/feedback` writes actionable files into the retired `dev_inbox/`. **S. proposal.**
- `DEFAULT_FEEDBACK_DIR = Path("dev_inbox")` (`transport_core.py:39`). There are 73 `feedback-*.md` files there now.
- CLAUDE.md says that `dev_inbox/` is read-only history and must never receive new actionable files.
- **Fix:** write to `worlds/.construct/feedback/` (gitignored, next to the transcripts) and, optionally, post an AgentPost `[STATUS]` pointer. The founder chooses the destination.

### 13. Config: one typed module loaded once. **M. polish** (proposal only if the `HOLODECK_*` names change).
- About 35 environment variables across three prefixes are read wherever they are used. Discord's are frozen at import time.
- `CONSTRUCT_IMAGE_SIZE` has two defaults.
- `.env` is honoured only for the token. That is why "live bots need the env before restart" is a recurring trap, and it is the source of the `/reboot` doc lie.
- **Fix:** a `construct/config.py` holding a frozen dataclass with `from_env()`. Load `.env` for everything at process start. Log the resolved config at transport start with secrets redacted, and validate enums such as backend names. Keep the existing names; aliasing `HOLODECK_*` to `CONSTRUCT_*` would be the founder's call.

### 14. holo (light touch): the deck prompt has a hard-coded incident clause. **S. polish.**
- `deck.py:448-449` injects "PLAYTESTS SAID: a naive player never questioned one suspect…; solves ran far longer than the 30 to 60 minutes" into **every** case's prompt. Those are notes about one case. Under the founder's tenet, a niche rule should be injected only when it applies.
- **Fix:** take playtest notes as an input (a case field or `construct holo deck --notes FILE`) and include the paragraph only when notes exist. The audit's gap list already carries the general version.
- Also:
  - `_arr` is duplicated (`deck.py:33` and `vocab.py:53`); import it from `vocab`.
  - "40 words" is hard-coded in both `CRAFT` (`:192`) and the check message (`:420`). Use `HOOK_MAX_WORDS`.
- Otherwise the holo slice is clean:
  - an audit with no model call
  - one deliberate call with a strict schema
  - a ported checker, pinned by tests
  - one repair re-ask
  - drop-and-report for parts that still fail
- The prompt is close to the tenet: a role, the closed language, the craft, the situation, and one directive.

### 15. Play-style directives: the template produces broken English that rides every narrator briefing. **S. polish.**
- `play_styles_data.py` is generated by `scripts/build_play_styles.py` with the template "Make victory mean {X}; make loss come from {Y}". It yields lines such as "make loss come from silenced, discredited, co-opted…" (`:29`) and "Make victory mean name the truth…" (`:9`).
- These directives are loaded into the narrator briefing every turn (`session.py:154-155`).
- **Fix:** change the template to "Victory: {X}. Loss: {Y}." and regenerate. That is one edit, with no change to the data shape.
- The directive format itself (dwell / compress / tension / win / loss) is a good situation-shaped directive, not a rule stack, and should be kept.

---

## What I would not change
- `InboundEvent` / `Outbound` as the normalized transport boundary, and the injectable `session_factory`, `builder` and `provider`, which keep the transport tests offline and fast.
- The exactly-once discipline: persist before send, advance the offset only after the update is durably recorded, recover interrupted updates on restart.
- `setup.py`'s handling of secrets: the 0600 file created with that mode, redaction everywhere, the token never in argv.
- The two-phase imagery design: `plan_scene` is pure and fast, `render` runs in parallel, and nothing is cached when the backend fails.
- The Discord mailbox, burst coalescing and owner-thread model. Generalize it (Finding 7) rather than delete it.
