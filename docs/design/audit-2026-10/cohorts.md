# Audit: `construct/cohorts.py` + `construct/provider.py`

Scope: `construct/cohorts.py` (3,602 lines, 49 functions, 44 `*_SCHEMA` constants) and `construct/provider.py` (739 lines). I also followed each cohort's output to where it is used (turnloop, game, foyer, architect, imagery, cast) when I needed to know whether a field is actually read.
Read-only audit, nothing in the repo was changed. `tests/test_provider.py` and `tests/test_cohort_schemas.py` pass (26 passed, 1 skipped).

**About the safety tags.** **polish** means the change keeps behaviour the same and can be done on a branch with the tests green. **proposal** means it goes to the founder. **Any edit to prompt text is tagged proposal**, even when the host logic stays identical, because it can change what the live model writes and the tests cannot catch that. Where a proposal is low-risk (for example, the deduction path stays byte-identical), I say so.

---

## Actual bugs (confirmed)

### BUG-1: `_clean_prose` cuts ordinary English out of the player's narration
`cohorts.py:3475-3499`. This function is meant to strip leaked JSON or "model talking about its own output" text from the end of the narrator's prose. It cuts the prose at the **first** occurrence of any marker. Some markers are common English phrases (`'it ends with'`, `'the final has'`), and any `{` or `}` also counts. I ran it on four inputs:

```
'The corridor — it ends with a sealed hatch, rust-red.'  -> 'The corridor —'
'You read the ledger. The final has a smudge.'           -> 'You read the ledger.'
'A brace {of pheasants}'                                 -> 'A brace'
```

- **Why it matters:** the player gets truncated prose with no error or log. A scene fact can disappear mid-sentence, which breaks the truth-keeping law. Both `narrate` and `open_scene` pass through this function.
- **Fix:**
  - Cut only at the structural markers (`"prose"`, `⟦`, `⟧`, a quote immediately followed by a brace).
  - Treat the meta phrases as a cut point only when they appear *after* a structural marker, or inside a trailing window that already contains one.
  - Add regression tests for the false positives above, next to the existing true positive in `tests/test_integration.py:3870`.
- **Size:** S. **Tag:** polish. It is a bug fix, and the leak cases the function was built for still get stripped.

### BUG-2 (the known issue, confirmed): the stream reader ignores error, failure, incomplete and refusal events
`provider.py:498-512`. `_collect_sse_text` only recognises three event types: `response.completed`, `response.done` and `response.output_text.delta`. I fed it simulated streams:

| stream contains | what the reader produces |
|---|---|
| `{"type":"error","code":"rate_limit_exceeded",…}` | `ProviderTransportError: response stream ended without output text; final event tail: {}` |
| `response.failed` with `error.message="boom"` | same message, tail `{}`. The server's reason is lost |
| completed message whose content is `{"type":"refusal",…}` | same "ended without output text" error. The refusal is visible only in the 300-character tail |
| deltas, then `response.incomplete` (`max_output_tokens`) | **returns the truncated JSON `'{"prose": "abc'`**. `complete()` then reports a JSON decode error and **re-asks the full prompt** with the wrong diagnosis (`provider.py:524-537`), paying for the call twice |

- **Fix:**
  - Handle each event type explicitly. `error` and `response.failed` raise `ProviderTransportError` carrying the code and message.
  - `response.incomplete` raises a typed `ProviderIncomplete(reason)`, and the re-ask is skipped for it.
  - A `refusal` content part raises a new `ProviderRefusal(ProviderError)`, so callers that fail open on `ProviderError` keep working.
  - Pull the framing loop out into one `iter_sse_events(resp)` async generator. `imagery._codex_dispatch` (`imagery.py:383-399`) currently has its own copy of that loop and would share it.
  - Add a test with fake streams, like the simulation above. Today no test sends an error event.
- **Size:** S-M. **Tag:** polish (error paths only). Whether to mark rate-limit or server errors as retryable ("transient") is a retry-policy decision. Leave them non-retryable for now.

### BUG-3: three task tags are malformed, so `task_of()` cannot see them
The tag pattern is `⟦([a-z]{3})⟧` (`provider.py:183`), but `author_cast` uses `task="cast"` (`cohorts.py:600`), `adapt_decision` uses `task="adapt"` (`:2691`), and `classify_death_policy` uses `task="dpol"` (`:3053`). For these three cohorts `task_of()` returns `''`: profiling, StubProvider dispatch and effort routing cannot target them. The comment at `provider.py:172-181` describes tags as the stable dispatch key, so this quietly breaks that contract.

- **Fix:**
  - Rename them to unused three-letter codes. `cst` is already the architect's tag, which makes "cast" doubly confusing.
  - Make `task_tag()` raise `ValueError` on a code that does not match the pattern.
  - Add a test that runs every cohort through a capturing stub and asserts `task_of(prompt)` is non-empty and unique.
- **Size:** S. **Tag:** polish.

### BUG-4: `author_cast` gives every story shape the deduction-only staging rules
The deterministic validator applies the culprit, first-witness and at-scene staging rules **only for deduction** (`cast.py:215-250`, gated by `require_staging=(_shape == "deduction")` at `game.py:881`). Strong red herrings and cross-suspicion are also deduction-only (`cast.py:317-333`).

The prompt, however, states all of these unconditionally (`cohorts.py:565-598`):
- "flag exactly one … `first_witness` (the one who found the body)"
- "□ EXACTLY ONE member has is_culprit=true"
- "□ at least TWO members are at_scene"
- "□ at least ONE strong red herring"
- "□ CROSS-SUSPICION …"

The schema descriptions say the same (`:375-394`).

A romance, survival or heist cast is therefore told to stage a crime scene and name a culprit. The architect prompt (`:1031`) insists "THIS IS NOT A MURDER-MYSTERY MACHINE", but the cast author still behaves like one. The rule exists in two places, and the copies have diverged.

- **Fix:**
  - Pass `require_staging` (or the shape) into `author_cast`.
  - Build the staging paragraph and the checklist from the same conditions the validator uses: deduction gets the current text, other shapes get a shape-neutral "who is reachable from the opening" clause.
  - The SUSPECT WEB block (`:491-499`) already shows the pattern to copy.
- **Size:** M. **Tag:** proposal. The deduction path can stay byte-identical; only non-deduction builds change.

---

## Status of the July audit's findings that touch these files

| July finding | Status | Evidence |
|---|---|---|
| The 4,500-character prompt budget is full; RENDER_LEASH and RENDER_STYLE overlap | **Cap retired (founder ruling); overlap WORSE.** | A consolidation landed in `bddaa59` (2026-06-27): LEASH 2,099 + STYLE 1,497 = 3,596 characters. At the audit commit `1043c80` they were 6,443. Today they are **2,993 + 4,736 = 7,729**. The narrator prompt now carries 8.6k-12.9k characters of fixed rules, and `open_scene` carries 14.4k. Duplication is back (Finding 3). |
| Dead classify fields (`asserts_or_reveals`, `reshape_attempt`, …) | **FIXED.** | All 26 `CLASSIFY_SCHEMA` fields are now read. For example: `asserts_or_reveals` at `turnloop.py:4138`/`4295`, `reshape_attempt` at `:4102`/`5900`, `uses_protagonist_knowledge` at `:4139`/`5311`. New dead outputs have appeared elsewhere, though (Finding 1). |
| `open_scene` stacks every directive unconditionally | **OPEN.** | `cohorts.py:3562-3564` always appends LEASH, STYLE, COMPETENCE and WORLD_IS_PEOPLED. `narrate` gained conditional flags (`:3576-3581`); the cold open did not. With `grounding=True` the player is alone in their own space, yet still gets PEOPLED and the "close on a present character handing them the moment" ending (`:3548-3553`). |
| `imagery.py` re-implements Codex auth and stream parsing | **PARTIAL.** | Auth is now reused, but by reaching into private attributes (`imagery.py:357-360`: `p._read_auth()`, `p._headers`, `p._base_url`, `p._cheap_model`). The endpoint is hard-coded as `"/codex/responses"` instead of `p._endpoint_path`. The stream-framing loop is still a clone (`imagery.py:383-399` ≈ `provider.py:485-497`). |
| The Foyer's tool names are bare strings; should be an enum shared with the schema | **OPEN.** | `foyer.py:269-275` and `architect.py:194-245` compare against bare strings. The vocabulary exists only inside the schema enums (`cohorts.py:681-684`, `:1068`). |
| Config sprawl (four env-var prefixes) | **OPEN, now misleading.** | `provider.py` reads `HOLODECK_CODEX_*`, `CONSTRUCT_OPENAI_*`, `CONSTRUCT_PROVIDER` and `OPENAI_API_KEY`. The *OpenAI* provider's effort settings come from `HOLODECK_CODEX_MAIN_EFFORT`/`_CHEAP_EFFORT`/`_REASONING_EFFORT` (`:391-392`, `:465`, inherited). The README documents only `CONSTRUCT_OPENAI_*` (README.md:76). |
| Task tagging ("what I would NOT change") | Kept, with defects. | Three tags are malformed (BUG-3). |

---

## Findings, ranked by value for effort

### 1. The weave cohort asks for outputs the host throws away (S, proposal, low-risk)
`WEAVE_SCHEMA` (`cohorts.py:249-264`) and `weave_pick` (`:3419-3461`) teach the model a three-way decision and ask for `seam_hint` and `directive`. The host (`turnloop.py:5767-5790`) behaves differently:
- it **always demotes `deliver_card` to `pepper_hook`**;
- it **never reads `seam_hint` or `directive`**, by design: "NO free model prose at all … (Cx 043/045)".

So on every weave call the cheap model spends reasoning on a decision branch and two prose fields that cannot have any effect. The prompt describes a contract the host does not honour. That is the "every clause must earn its place" failure in its plainest form.

- **Fix:** shrink the schema to `{decision: let_run|pepper_hook, card_id}`. Delete the `deliver_card` and seam paragraphs from the prompt (`:3434-3439`, `:3458-3460`). Fix the docstring claim "Subsumes `nudge_pick`": nudge is still live for worlds without a cast (`turnloop.py:6607`).
- **Size:** S. **Tag:** proposal. Host behaviour stays identical; the model's choice set gets smaller.

### 2. The classify verdict is a 26-field dict, its defaults live 4,000 lines away, and each field rule is stated twice (M; part A polish, part B proposal)
- **Data shape.** `classify()` returns a raw dict. `turnloop.py:3983-4160` (about 180 lines) unpacks it into roughly 25 local variables, each with its own fallback when the call fails:
  - `addresses_present` and `asserts_or_reveals` default to **True**;
  - `moves_open` and `seeks_encounter` use a strict-True check;
  - `kind == "action"` conditions are scattered through the unpacking.
  These semantics are the actual contract of the call, yet they live in the turn loop rather than next to the schema. Every new field means edits in three places: schema, prompt, turnloop.
- **Duplicated rules.** The prompt's "Additionally:" paragraphs (`cohorts.py:2603-2634`) restate the schema descriptions of `moves_to`, `requires`, `commits`, `takes`, `drops`, `examines_target` and `mortal_risk` (`:59-157`). `npc_note` (`:2549-2557`) restates `moved_with`/`npcs_dismissed`/`joins`, and `ask_note` restates `asks_targets`. The model reads both copies: 4.2k characters of prompt plus 9.9k of schema on every turn, on the cheap tier. The copies have already drifted: the hedged-accusation rule for `commits` is only in the prompt. On top of that, the prompt opens with the conditional notes (ASK CANDIDATES…) *before* saying what the task is.
- **Fix A (polish):** add a frozen `TurnIntent` dataclass next to `CLASSIFY_SCHEMA`, with `TurnIntent.from_verdict(verdict)` (holding all the normalisation and kind-gating now in turnloop) and a `TurnIntent.FAIL_OPEN` constant for the `ProviderError` branch. The turn loop then reads `intent = …`. Behaviour is unchanged, and it is testable without running the turn loop.
- **Fix B (proposal):** state each field's rule once, in the schema description. Keep in the prompt only the rule for `kind` and the principle "read intent, stay in fiction". Put the task statement first and the situation notes after it.

### 3. The narrator's rule blocks have re-accreted, and the cold open still gets all of them (M, proposal)
Restating the same rule raises its weight and contradicts the elegance tenet. Counts:
- **"Don't re-describe what hasn't changed"** appears four times inside RENDER_STYLE alone: "GROUND … otherwise … without recapping the room", "DON'T FIXATE", "DESCRIBED ONCE, IT STAYS", and "PROPORTION … when nothing in the scene has changed, do not re-describe it" (`cohorts.py:2396-2425`).
- **Second person** is stated five times: LEASH `:2381`, STYLE PERSPECTIVE `:2425-2429`, `player_constraint` `:2514`, PROTAGONIST_COMPETENCE `:2451`, WORLD_IS_PEOPLED `:2487`.
- **"A question about the player's own life is answered by their memory first"** is stated twice: COMPETENCE `:2456-2458` and PEOPLED `:2485-2492`.
- **"Briefing is truth; don't conjure significant things"** is stated three times within LEASH (`:2345-2355`, `:2365-2368`), plus the open's CONCEALMENT paragraph.

Fixes:
- Run a second consolidation pass in the style of `bddaa59`: one principle, stated once, with at most one example.
- Give `open_scene` the same conditional flags `narrate` has. The caller (`session.py:788`) knows whether cast is present and whether this is the grounding open.
- Prerequisite: about 85 assertions in 12 test files pin exact prompt wording (for example `test_architect.py:206-209`). Change them to check that named sections are present, or every consolidation will be fought by the tests.

### 4. `author_cast` staging rules on every shape
See BUG-4. Listed again here because it is the highest-value *prompt* change: it is a correctness fix for every non-deduction build. **Size:** M. **Tag:** proposal.

### 5. Front-door prompts inject both sides of state the code already knows (M, proposal)
- **`foyer_turn`** (6.0k characters) always contains both "THE OPENING TURN ONLY (… empty)" and "EVERY TURN AFTER THE OPENING" (`cohorts.py:1116-1145`), then asks the model to work out which applies from the `history` text. The function already has `history` and could include only the relevant branch. The pronoun-menu exception is likewise only relevant while pronouns are unset.
- **`architect_turn`** (10.5k characters, the largest prompt in the file) always includes:
  - the `reroll_surprise` instructions, though they only matter "while a HOST-ROLLED PROPOSAL stands";
  - the `resume` instructions, though they only matter when `resumable` is set;
  - the OPENING-A-NEW-BUILD and full interview blocks, including THE LAW, on every turn (`:943-1037`).
- **The host persona is written out five times:** entry `:641`, architect `:890-893`, foyer `:1105-1107`, ooc `:805`, plus schema descriptions `:626`, `:670-671`, `:1059-1060`.
- **Fix:** gate each block on state the caller already holds, and add one `HOST_VOICE` constant. This is the conditional-injection discipline `narrate` already follows.

### 6. `OpenAIProvider` subclasses `CodexProvider`: names that mislead and settings that leak across (M, polish)
`class OpenAIProvider(CodexProvider)` (`provider.py:661`) inherits Codex-specific behaviour:
- reasoning effort comes from `HOLODECK_CODEX_*` environment variables (`:391-392`, `:465`);
- the Codex consumer backend's transport cap `CODEX_PAYLOAD_CAP_BYTES` is enforced on the metered API (`:592`);
- an unused `_auth_path` to `~/.codex/auth.json` is set (`:381`).

`imagery.py` reaches into private attributes and hard-codes the Codex path.

- **Fix:**
  - Add a `ResponsesProvider` base that owns the request body, stream reading, retry, timeouts and effort ladder.
  - Make `CodexOAuth` and `OpenAIKey` two thin auth subclasses, each with its own env prefix, keeping `HOLODECK_*` as deprecated aliases so behaviour is preserved.
  - Make the payload cap a per-subclass setting.
  - Expose public `auth_headers()`, `endpoint` and `iter_sse_events` so imagery uses the provider instead of copying it. This also closes the July "PARTIAL" and "config sprawl" rows for the provider's part.

### 7. Five copy-pasted test defaults inside the production StubProvider (S, polish)
`provider.py:235-268` has five near-identical `if task_of(prompt) == X and not (queue head carries key K): return default` blocks: `csg`, `rmb`, `mcl`, `law`, `lwc`. Each was added as "the same precedent" when a new cohort call appeared inside paths that older tests had already stubbed.

- **Fix:** replace them with one table, `_SILENT_DEFAULTS: dict[str, tuple[str, dict]]`, and one lookup. Better still, make it a `StubProvider(defaults=…)` constructor argument supplied from `tests/conftest.py`, so test scaffolding leaves production code.

### 8. Small provider clean-ups (S, polish)
- **Timeout bound** (`:606-607`): `min(max(tb, HARD) if deliberate else tb, HARD)` always evaluates to `HARD` for deliberate calls. Write it as `HARD if deliberate else min(tb, HARD)`.
- **Retryable marker** (`:651`): `err.transient = True` attaches an attribute to the exception on the fly, and `getattr(exc, "transient", False)` reads it at `:556`. Replace it with a `ProviderTransientError(ProviderTransportError)` subclass.
- **Effort strings** (`:463`, `:470`): they are never validated. `_EFFORT_RANK.get(effort, 1)` treats an unknown value as "low", and a typo reaches the API only at the first call. Validate the effort level when the provider is constructed.
- **Duplicate engine callables**: `engine_callable` (`:146-160`, used only by `scripts/b1_trace_probe.py` and one test) and `engine_tier_dispatch` (`:208-217`, the live one) are near-duplicates, and only the unused one has the running-event-loop guard. Merge them into `engine_callable(provider, tier=None)`, where `None` means dispatch by prefix.

### 9. Engine calls are routed to a tier by matching pattern-buffer's prompt wording (S polish now; proposal to PB)
`_CHEAP_ENGINE_PREFIXES = ("Extract world-state", "Classify the lifetime")` (`provider.py:167`, `:214`) depends on the exact wording at `~/pattern-buffer/src/patternbuffer/ingest.py:117`/`187` and `classify.py:138`/`293`. If PB rewords those prompts, all extraction silently moves to the main tier: slower and more expensive, with no error.

- **Now (polish):** add a test that runs a small PB ingest with a capturing callable and asserts the extraction calls went to the cheap tier.
- **Later (proposal):** send pattern-buffer a request to pass a task or tier hint to the model callable. Under the "never work around the engine" law, this belongs to PB.

### 10. Module seam: 3,600 lines across five lifecycles, and the biggest planning prompt lives elsewhere (M, polish)
`cohorts.py` mixes:
- the front door (entry, architect, foyer, ooc);
- build-time authoring (story, laws, cast, intro, premise, flavor, interview, knows, relationships, ground, image);
- per-turn cohorts (classify, npc, memory, elapsed, equipment, reshape, events, gate, destination, weave, nudge);
- drift and growth (relocate, absence, repair, assessor, tangent, generate_arc);
- memory (compact, personal threads, claims);
- and the render directives.

Meanwhile the **arc-authoring prompt** is written inline in `game.py:629-700`, and `holo/deck.py:378` makes its own call, so the module's promise that every model call lives in one place no longer holds. The header docstring (`:1-9`) still describes the retired `npc_world_action` tiering.

- **Fix:**
  - Turn it into a package, `construct/cohorts/{front_door,authoring,turn,drift,memory,render}.py`, with an `__init__` that re-exports every public name so `cohorts.X` call sites and tests keep working.
  - Move the arc prompt into `cohorts.author_arc`.
  - Refresh the stale docstrings.
- **Cross-part note:** turnloop rebinds a local variable named `cohorts` to a list (56 uses of `cohorts.append`) and imports the module as `_co` to get around it. Rename that list.

### 11. Unread rationale fields (S, proposal)
Three schemas ask for a reason that nothing reads:
- `reason` in `ESTIMATE_ELAPSED_SCHEMA` (`:1208`), read site `turnloop.py:4465`;
- `reason` in `EQUIPMENT_SCHEMA` (`:1325`), read site `turnloop.py:1975`;
- `rationale` in `JUDGE_COMMITMENT_SCHEMA` (`:2701`), read site `turnloop.py:6272`.

Either log them into the turn trace as audit receipts, which is what growth does with `assessment`, or drop them. Reasoning-effort models do not need written rationale to reason.

### 12. The same schema-lint rule is enforced twice (S, polish)
`tests/test_cohort_schemas.py` re-implements the "required ⊆ properties" walk that `lint_schema` already enforces (`provider.py:114-120`), and `test_provider.py:307` already runs it over every schema. Keep one: have the test call `lint_schema`, and keep only the "found at least 30 schemas" sanity check.

---

## Considered and not recommended (or not now)
- **A new event loop and TLS connection per model call.** `complete_sync` calls `asyncio.run` every time and builds a fresh `AsyncClient` (`provider.py:143`, `:617-621`), so connections are never reused. That costs a handshake per call (about 0.1-0.3 s; a turn makes several calls), which is small next to model latency. A persistent loop thread plus one shared client would fix it, but it touches the keepalive and wedge-avoidance history (letters 059/060). Not worth the risk now.
- **The world-laws clause appended to about eight cohorts.** Each is already conditional (`if laws`) and tailored to its cohort. That is conditional injection done right, so leave it.
- **No broad try/except** in either file. The provider raises typed errors and the cohorts are thin: both files hold up well on this.
- **Uneven quoting and truncation of untrusted input.** The architect, foyer and story author use `<<<GUEST`/`<<<SEED` delimiters plus length caps; `classify` and `npc_turn` include player text raw (`:2635`). This is low-impact, since a player can only affect their own session. Worth making consistent during the item 2 restructure.
