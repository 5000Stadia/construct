# Audit: `construct/turnloop.py` (intelligence and elegance)

Auditor scope: `construct/turnloop.py` (7,969 lines at HEAD `26b2e6a` + working tree), read in full. Read-only. Adjacent-module evidence was checked only where a finding depends on it (`cohorts.narrate`, `arc/executor.value_leaks`, `session.run_turn` call, `resolve.py` imports).
Test sanity: `tests/test_cast_moves.py tests/test_drift.py tests/test_growth.py tests/test_tangent.py` all pass (279 passed, 161 s). 1,235 tests were collected suite-wide.

---

## 0. Map of the file

| Region | Lines | What it holds |
|---|---|---|
| Concealment vocab helpers | 90–304 | `_destination_facts/_directive`, `_secret_tokens`, `_secret_word_set`, `_take_touches_secret`, `_concealed_move_vocab`, `_growth_concealed_vocab`, `_move_touches_secret` |
| World-growth invocations | 306–716 | `_tangent_attempt` (146 lines), `_growth_attempt` (253 lines) |
| Convergence and lexical heuristics | 718–1012 | `_convergence_directive`, `_is_pressing`, `_is_scrutiny`, `_ROLE_NOUNS/_ROLE_SYNONYMS`, `_words`, `_names_entity`, vocative parsing, `_departed_from`, `_colocated` |
| Infra | 1014–1104 | `_phase`, `_parallel`, env-var constants, phantom sets |
| `TurnTrace` / `TurnResult` | 1106–1213 | about 90 fields |
| Extraction partition and cast-moves lane | 1216–1693 | `_FailOpenIngest`, `_partition_frames`, `_canonicalize_containment`, `_partition_cast_moves`, `_run_cast_moves_lane` (266 lines) |
| Route, price and furnish helpers | 1695–1922 | |
| Grants and mint | 1924–2338 | `_mint_held_object`, `_grant_equipment`, `_grant_taken_object`, `_FIXTURE_HEADS`, `_embedded_container`, `_grant_moved_place` (124 lines) |
| Carrier-move public surface | 2340–2504 | `CarrierMovePolicy`, `validate/prepare/confirm/commit_carrier_move` (12 external refs) |
| Off-screen world and drift | 2506–3621 | `_world_tick` (219 lines), `_drift_pass`, `_absence_beat` (242), `_relocate_beat`, `_repair_beat` (271) |
| Adjudicate, conclusion, time | 3623–3908 | `adjudicate`, `terminal_outcome`, `_fire_event_occurs`, `_advance_diegetic_time` |
| **`run_turn`** | **3910–7919** | **4,010 lines, 21 parameters, 70 `except Exception`** |
| Mechanics log | 7922–7969 | `_write_mechanics_log`, `run_turn_sync` alias |

### The phases inside `run_turn` (all inline)
1. Setup (3946–3977): laws block, gauge fold, horizon, trace, generative slot, `_FailOpenIngest` wrap.
2. Pre-classify assembly (3982–4084): about 20 verdict locals with defaults, actor descriptor, opaque NPC and ask candidates.
3. Classify and unpack (4085–4174).
4. Early returns (4176–4267): exit, question→`ask`, ooc, canon-strict declaration, adjudication denial (which has its own narrate call and archive).
5. Player-input extract→partition→canonicalize→resolve→stamp→ingest (4269–4367).
6. Dismissals (4369–4400).
7. **Movement (4402–4890, about 490 lines):** a deliberation closure, seek-unwrap, refer, horizon guard, entitlement gate, person→place redirect, non-place absorb, same-place, route→deliberate→commit; the unresolved entitlement gate; the zero-candidate branch (fixture heads, place-roster build, `_do_grant` closure, embedded container, known-place reuse, semantic bind plus alias accrual plus route→deliberate→commit, ambiguous, mint).
8. Growth G1, tangent G-A, staged-mutation flush (4892–4995).
9. Nearness inversion (4996–5027). 10. Companions and companionship (5029–5089). 11. Take and drop (5091–5194).
12. Scene, snapshot, mirror, arc-touch (5196–5234). 13. Gauges, early time, clocks, furnish, `on_scene` (5236–5276).
14. Presence, Remembrancer, parallel `npc_turn`, NPC action commits (5278–5450).
15. Vocative, addressed set, interview delivery, examine delivery, discovery, engaged set (5452–5626).
16. Make-it-real, grounding runway, card weaving (5628–5796).
17. Resolution tier, `event_occurs`, death gate (5798–5887). 18. Reshape and same-turn replan (5889–5958).
19. `beat_pass` and drift for main and side arcs (5959–6031). 20. Pins, scene_lines, irony threads (6033–6136).
20. Conclusion, commitment (three stacked `if commits and earned and …` blocks), outcome, terminal receipts, ending consequences (6138–6468).
21. Side-arc lifecycle, DM generator, pacing nudge, NPC intents (6470–6668).
22. **Briefing assembly (6669–7502, about 830 lines, 64 `briefing_parts` append sites).**
23. Render and the third-person re-ask (7504–7534).
24. **`_settle` closure (7536–7890, about 355 lines):** extract, cast-moves lane, quarantine stage, promote gate, audit, transcript and compaction, time, last-seen, world tick, mechanics log.
25. Synchronous receipt and archive (7892–7919).

### Guard stacks
- Movement: 18 writes to `trace.movement_status` (lines 702, 4485, 4552–4880), plus `trace.same_place`, `_move_clarify`, `_growth_miss`, and a `target`/`status` pair that guards null out in sequence.
- Concealment: 5 vocabulary builders (see finding 4).
- Commitment: 3 consecutive blocks sharing `commits and earned and terminal_outcome(...) is None` (6202, 6236, 6250), with `_csum` defined in the second block and read in the third.

---

## 1. Status of the July audit findings that touch this part

| July finding | Status | Evidence |
|---|---|---|
| `run_turn` is 2,242 lines with 15 inline phases | **WORSE** | Now 4,010 lines (3910–7919) with about 26 inline phases. |
| 53 broad try/excepts | **WORSE** | 70 `except Exception` inside `run_turn`, 154 in the file, 19 of them followed directly by `pass` or `continue`. |
| Movement = 10 sequential guards mutating shared `status`/`target` | **WORSE** | 18 `movement_status` writes. The route→deliberate→commit sequence is hand-copied 3 times (4601–4619, 4790–4795, 4857–4875). Deliberation (#102), growth (`_growth_miss`), nearness and alias accrual are layered into the same branch tree. |
| Collapse movement into one `resolve_move` decision table in `resolve.py` | **OPEN** | No `resolve_move` exists (`grep` in `construct/`). |
| Zero-candidate mint → phantom scene | **FIXED in the small, structure OPEN** | Semantic bind before mint (4800–4885, Cx 354). The roster includes the current scene (4709). Compound containers are handled (`_embedded_container`). Bind authority is still spread across the guards. |
| Unify the three tokenizers | **WORSE** | There are now at least 8 tokenization schemes: `_words` (877), `_secret_word_set` (165), the inline split in `_secret_tokens` (158), `_is_pressing` (814), `_is_scrutiny` (838), `names_protagonist` (3663), `_dest_head` (2050), the `re.split` calls in `_embedded_container` (2136–2174), the deflection split (7384), the `license_tokens` split (7557), plus `executor.value_leaks` with whitespace split. One of these has a live punctuation bug (Bug 1). |
| P0 phase extraction | **PARTIAL** | New features landed as named helpers with contracts: `_world_tick`, `_drift_pass`/`_absence_beat`/`_relocate_beat`/`_repair_beat`, `_growth_attempt`, `_tangent_attempt`, `_run_cast_moves_lane`, `_advance_diegetic_time`, `_turn_salience`. None of the pre-July inline phases were extracted. |
| Band-aids outliving wounds (verified-then-strip) | **MOSTLY FIXED** | The promote-gate phantom, deixis and malformed guards were stripped (Cx 313; tombstone comments at 1087–1103 and 7719). `_NARRATOR_PHANTOM`/`_PRONOUN_PHANTOM` remain for take and drop (5109, 5183), although `resolve.is_voice`/`is_deixis` now exist. |
| `_FIXTURE_HEADS` lexical guessing | **OPEN, grown** | The list grew ("grating", "hatch", …, 2041–2043). It is checked at 4580 and 4652 before the semantic bind could rule. |
| Weave momentum magic `<= 2` | **OPEN** | 5750. |
| Dead classify fields (`asserts_or_reveals`, `reshape_attempt`) | **FIXED** | Both are consumed (4295, 5900). New dead branch: `kind == "ooc"` (4204), because the classify schema enum is `["action","question","declaration","exit"]` (cohorts.py:46). |
| `_state_value` clone farm | **N/A here; analogous clones OPEN** | The turnloop analogue is 11 local name-reader closures (finding 9). |

---

## 2. Bugs (separate from the ranked list)

**B1. Punctuation bypass in the concealment screen that guards world-tick canon writes. CONFIRMED.**
`_world_tick` screens model-authored `detail` with `value_leaks(detail, _ctoks)` (2654) before committing it to canon. The run_turn place roster also redacts labels with it (4698). `executor.value_leaks` tokenizes by whitespace, so a token with trailing punctuation never matches. Reproduced:
`value_leaks('he named the culprit, then left', {'culprit',...}) -> False`, while the same text without the comma returns `True`.
This is the Cx 274 bug class that `_secret_word_set` already fixed for takes. The `_pvals` substring check (2654) covers protected VALUES only, not the entity and attribute tokens.
Fix: tokenize with `_secret_word_set` (`re.findall(r"[a-z0-9]+")`) inside `value_leaks`, or have turnloop screen through the one vocabulary object in finding 4. Size S. **Safe bug-fix:** it only tightens the screen. Note that `Session._value_leaks`/`live_threads` share the function (outside this part).

**B2. World-tick reads are not bound to the play horizon. PLAUSIBLE, for horizon/book worlds.**
`_world_tick` reads `p.snapshot(nid, frame=f"knows:{nid}", lens="character_sheet")` without `as_of` (2575). It also calls `p.locate(nid)` (2571) and `p.locate(pid)` (2688) without it, and enumerates `world.porcelain.entities("canon", prefix="place:")` (2608) at head. Its `CarrierMovePolicy` passes `horizon=None` (2647).
The NPC-turn sheet had exactly this fixed (5344–5348, "Cx 259 … a future-stamped knows:<npc> row must NOT drive NPC behavior"). The tick's sheet feeds a model whose `detail` is then committed to canon, so aftermath knowledge can leak into present canon.
Fix: thread `horizon` into `_world_tick` and pass `as_of=horizon` on all four reads and the policy. Size S. Safe bug-fix (it is a no-op when horizon is None).

**B3. A dangling prompt cross-reference on every solo turn. CONFIRMED.**
"NEUTRAL ON THE ANSWER" (7485–7495) is appended on every hold-mode turn and says "(see A PEOPLED WORLD)". "WITHHELD QUESTION" (7400) says the same. `cohorts.narrate` injects `WORLD_IS_PEOPLED` only when `peopled=bool(npcs)` (turnloop 7509, cohorts 3576). When the player is alone, the narrator is told to see a block that is absent.
Fix: drop the parenthetical, since the clause around it already says the characters keep their feeling. Size S. This is a prompt edit (trivial model-input change).

**B4. A latent rebind of the `cast` parameter. CONFIRMED latent.**
On a non-death terminal turn, `cast = sorted({...ids})` (7017) replaces the `dict[str, CastNode]` with a list of strings. `_settle` later passes `cast=cast` to `_world_tick` (7886). That call is masked only because `_world_tick` returns early on `trace.terminal` (2524). If that guard is reordered, `{n.node_id: n for n in cast}` raises inside a broad except and the world tick silently stops.
Fix: rename the local (`fate_cast`). Size S, polish.

**B5. The concealment audit is blind to the hidden answer. CONFIRMED by reading (telemetry only).**
`license_tokens` is built from the whole `briefing` (7557). In hold mode the briefing contains the destination card with the hidden answer in human form (`_destination_directive`, 7498). So `_licensed()` treats a narrator-minted entity named after the culprit as "given to the narrator", and `trace.concealment_audit` cannot flag the one leak it exists to catch. The strict protected-key gate (7756) still protects canon, so this is a debug-surface defect.
Fix: compute license tokens from the briefing before the card is appended, or from the parts list without `dest`. Size S, polish.

**B6. Inconsistent temporal stamping of in-turn writes. PLAUSIBLE.**
The equipment grant mints with no `valid_from` (`_grant_equipment` → `_mint_held_object(..., hint)` without `at`, 1977). The take grant passes `at=turn_time(turn)` (2004). Claim rows (6278–6283), furnish rows (1901, 1913) and whereabouts rows (5606) carry no stamp either, while 86 other call sites stamp by hand. In a horizon world, an unstamped `in` row lands at the ingest default (see the `_TEMPORAL_PROMOTE_ATTRS` rationale, 1292–1300).
Fix: pass `at` in `adjudicate→_grant_equipment`, and see finding 10. Size S.

**B7. Known-place reuse skips the passability gate. CONFIRMED by reading.**
When `refer` misses but `_match_known_place` token-matches an established place (4782–4795), the protagonist's `in` row commits after only the deliberation check. No `_route_obstruction` call is made. The resolved path (4601) and the semantic-bind path (4857, "SAME MOVEMENT GATES AS RESOLVED TRAVEL (Cx 358 blocker)") both gate, so a blocked way to a known place can be walked through by phrasing it so refer misses. Fixed structurally by finding 3. Size S.

---

## 3. Ranked findings (value per unit of effort)

### 1. The classify verdict should be a typed object, not about 20 loose locals. S–M, **polish**
**Evidence:** 3982–4174. Twenty-one locals are pre-declared with individually reasoned defaults and comments: `addresses_present=True` "fail-open", `asserts_or_reveals=True`, `moves_open=False` "fail-closed", `seeks_encounter`, `_t_aim`, and so on. The unpack then re-implements `bool(...) and kind == "action"` gating field by field. The opaque-id maps (`_npc_by_oid`, `_ask_by_oid`) are separate locals, and the ProviderError path relies on the pre-declarations.
**Why it matters:** this is the single largest source of loose state in `run_turn`. The fail-open/fail-closed default policy, which reviewers re-litigated for months, is scattered across comments instead of declared once. It also blocks phase extraction, because every later phase closes over these locals.
**Fix:** a `@dataclass(frozen=True) class Intent` with `Intent.from_verdict(verdict, npc_by_oid, ask_by_oid)` and `Intent.fallback()` for the ProviderError path. Put each default and its one-line reason on the field. `kind`-gating lives in `from_verdict`. Size S–M. Behaviour-preserving, and the existing suite pins it.

### 2. Extract `run_turn` into phases over an explicit turn state (the July P0, now twice as urgent). M–L, **polish**
**Evidence:** section 0. `run_turn` is 4,010 lines. `_settle` is a 355-line closure that reads about 25 outer locals (`receipt_rows`, `player_table`, `briefing`, `canon_table`, `snap_scope`, `_present`, `_reshape_license`, `_clock`, `_time_committed`, `_recent`, …). Variables are shadowed across phases: `_here` is a presence set at 6097 and a scene-name string at 6216; `_resolved` is the player-extract rows at 4337 and a bool at 5172; `cast` is rebound per B4.
**Why it matters:** no phase can be tested or reasoned about alone, and every new feature has to thread through the whole function. Shadowing bugs like B4 are what such a function grows.
**Fix:** a frozen `TurnInputs` (world, arc, provider, config; see finding 11) and a mutable `TurnState` (scene, chain, canon_table, npcs, intent, decisions). Extract in this order, cheapest and purest first:
(a) `build_briefing(state) -> str` (6669–7502). This is the biggest win: about 830 lines that only read.
(b) `settle(state)` as a module function.
(c) `resolve_conclusion(state)` (6138–6468).
(d) `delivery_phase` (5452–5626).
(e) `movement_phase` (4402–4890), which finding 3 then shrinks.
Keep `run_turn`'s signature and the names tests import (`_GROWTH_SEAM` ×19, `_world_tick`, `_stored_route_price`, …) as re-exports. Size M per phase, L in total. Mechanical, and the suite is the net.

### 3. Movement: one `_commit_travel` now, the `resolve_move` table later. S (helper, **polish**) / L (table, **proposal**)
**Evidence:** route gate → `_hold_for_deliberation` → `ingest in-row` → `movement_status = seg.status or "clear"` → obstruction appears three times: 4601–4619 (resolved), 4857–4875 (semantic bind), and 4790–4795 (known-place reuse, where the route gate is *missing*). Known-place reuse commits with no `_route_obstruction` check, while the bound path's comment says "SAME MOVEMENT GATES AS RESOLVED TRAVEL (Cx 358 blocker)". The same-place no-op is set at 4591, 4797 and 4846.
**Why it matters:** the duplication already produced a gate asymmetry: token-matched reuse skips passability. Each new movement rule (deliberation, growth) has to be spliced into every copy.
**Fix (polish):** `def _commit_travel(dest, label) -> MoveOutcome` holding the route check, deliberation and commit, plus `_already_here()`. Call it from all three sites. The reuse site gaining the route gate is a small behaviour change; flag it in review. Size S.
**Fix (proposal):** finish the July P1. Write a pure `resolve_move(phrase, ctx) -> Bound|Here|InScene|Blocked|Undiscovered|Ambiguous|Mint|GrowthMiss|Deliberate` in `resolve.py` with an ordered decision list, and have `run_turn` only commit its result. This also absorbs `_FIXTURE_HEADS` as one row, ideally after the semantic bind. Size L. Spec-first with cr.

### 4. Concealment: one vocabulary object with named views and one tokenizer. M, **polish** (+ the B1 tightening)
**Evidence:** five builders over the same `arc_protected_keys`:
- `_secret_tokens` (144): len>3, its own split, minus public names;
- `_take_touches_secret` (173): total tokenizer, adds names and aliases;
- `_concealed_move_vocab` (202): entity-ref values only;
- `_growth_concealed_vocab` (234): strict, horizon-bound identity log;
- `executor.concealed_tokens/value_leaks`: entity and attribute only, whitespace split, a separate `_CONCEAL_STOP`.
Each re-reads `reads.state(e, a)` per key per call. Some callers run several per turn, for example takes plus the roster plus deflection.
`_concealed_move_vocab`'s docstring says it is "Shared by … the WORLD-GROWTH leaks predicate", but growth uses `_growth_concealed_vocab` (569). The docstring is wrong.
**Why it matters:** this is the truth-keeping law's machinery, and it has drifted into five subtly different definitions. B1 is the cost.
**Fix:** `ConcealmentVocab.build(arc, reads, *, strict: bool)` reads once per turn and exposes `.full`, `.answer_refs`, `.question_probe(public_names)`, and `.leaks(text, view)`, all over `_secret_word_set`. Each view keeps its current semantics, and the strict/fail-closed variant stays a flag on `build`. Size M. Behaviour-preserving except the B1 fix.

### 5. `TurnTrace` is the turn's control channel, so type it as one. M, **polish**
**Evidence:** the docstring says "a formatting of session/audit rows, never a second bookkeeping" (1108). The turn and its consumers read about 18 fields as control: `movement_status`, `same_place`, `distance_unknown`, `journey_est`, `journey_priceable`, `growth`, `growth_retry`, `growth_moved`, `relocate_directive`, `repair_directive`, `tangent_directive`, `reshape`, `terminal`, `concluded`, `dropped`, and others; `session.py:1100/1114/1128` read `growth_retry`, `reshape_entities` and `terminal_kind`. The receipts are stringly typed and parsed back: `str(trace.growth).startswith("activated:")` (2803, 5041); `trace.distance_unknown.partition("->")` (3869, 3899); `trace.deliberating.split(' — ')` (6886–6888) is used to rebuild prompt text. `movement_status` has 9 untyped values plus the empty string.
**Why it matters:** string parsing of your own state is fragile. Splitting a human-readable debug string to build a prompt is one em-dash away from a garbled briefing.
**Fix:** a `MovementStatus` str-Enum; `growth: GrowthReceipt(state, ref, reason)` with a `__str__` that keeps the current debug rendering; `distance_unknown` as `tuple[str, str] | None`; `deliberating` as `(label, est_min, remaining_min)`. Keep the attribute names that session reads. Optionally move the control fields to `TurnState` (finding 2) and leave `TurnTrace` as pure telemetry, which would make its docstring true. Size M.

### 6. The narrator briefing deserves its own module, and a prompt pass under the elegance tenet. M (move, **polish**) / M (prompt, **proposal**)
**Evidence:** about 830 lines of inline prompt prose in `run_turn` (6669–7502) plus directives built elsewhere in the file: `_destination_directive` (106), `_convergence_directive` (728), MAKE IT REAL (5689), WEAVE (5785), the tangent, relocate and repair directives. `cohorts.py` is the prompt home, but none of this turnloop text sits under its discipline. Against the tenet:
- **Restated house rules:** "diegetic" appears 57 times and "never as an announcement/announce" 5 times, nearly every block restating the voice contract `RENDER_STYLE` already carries. Each directive could be one line of *situation* ("THE STORY TURNS: <hook>") if the voice contract owned "render it in-world".
- **An unconditional niche rule:** "NEUTRAL ON THE ANSWER … the mystery's SOLUTION" (7485) rides every hold-mode turn of every genre (romance, sandbox, survival). It belongs behind the same condition as the destination card (`_destination_facts(arc) != ""`).
- **Rule stacks rather than situation:** the destination card's RESTRAINT paragraph (129–136) is six prohibitions. UNDER-DETERMINED QUESTION (7405–7421) embeds worked examples (a pizza joint in Anchor, a smartphone in a medieval vale) and bullet rules. MORTAL STAKES, DEATH TRANSFORMED and PRICE STOPS SHORT are three policy lectures where one line of the world's death contract plus the drawn tier would do.
- **Author meta leaking into the model's input:** "(founder: the full name in every reply reads canned)" (7153), "(CHARACTER-GROUNDING, founder)" (7373), "— NARRATION-DISCIPLINE)" (5690).
- **Good examples to copy:** YOU ARE AT (6767), PRESENT CHARACTERS with live/dead/companion truth (7239–7330), and WHAT YOU ARE CARRYING (7219) state engine truth plus one principle.
**Fix:** move assembly to `construct/briefing.py` as `build_briefing(situation: TurnSituation) -> list[Block]`, where each block is `(label, text, condition)`. That makes the injection conditions auditable in one place and testable as data (polish, no text change). Then a separate proposal edit: strip the meta, gate NEUTRAL, collapse the restated clauses into `RENDER_STYLE`, and turn the rule stacks into situation lines. Fix B3 there too. The prompt edit needs the founder's eye and a live A/B.

### 7. Lexical address and intent heuristics duplicate classify's job, and are genre-biased. M, **proposal**
**Evidence:**
- `_names_entity` + `_ROLE_NOUNS` (864–874) contains a Victorian household: governess, footman, coachman, sexton, publican. Captain is there, but pilot, medic and engineer are not.
- `_ROLE_SYNONYMS` (849).
- `_is_pressing`: `_PROBE_SIGNALS` contains "did/was/were/what/know/tell". Any "?" or `needs_test` returns True, so the gate is near-vacuous.
- `_is_scrutiny` (833) overlaps classify's `examines_target`.
- `_vocative_token` regex parsing (939).
Classify already receives the present NPCs as opaque candidates (4087–4090, `npc_candidates`) and returns `addresses_present`, `npcs_dismissed`, `moved_with`, `joins` and `asks_targets`. Addressing is nonetheless recomputed lexically in three places: the addressed set (5493–5499), interview delivery (5527–5530) and the make-it-real `names_authored` check (5654–5658). `resolve.py` even imports `_names_entity` from turnloop (resolve.py:206, 445).
**Why it matters:** non-period genres silently lose role-address. The pressure gate does not discriminate. Three call sites must agree on who was addressed and currently use different predicates (`only_one` with and without `addresses_present`, 5491 vs 5515).
**Fix:** add `addresses: [npc_k…]` and `presses: bool` to the classify schema. That is model judgment over the opaque candidates it already sees. Derive the one addressed set from it, keeping the vocative-to-absent-holder rule as the deterministic exception. Retire `_ROLE_NOUNS`/`_ROLE_SYNONYMS`/`_PROBE_SIGNALS`. This is a cohort-schema and behaviour change, so it is a proposal. Size M.

### 8. `cast` has one real shape; give it an index. S–M, **polish**
**Evidence:** production always passes `dict[str, CastNode]` (session.py:197, 1089), but 12 sites shim list-or-dict (`cast.items() if hasattr(cast, "items") else [(n.node_id, n) …]`: 2528, 2942, 2988, 3176, 3437, 4054, 4061, 4531, 5567, 5595, 5650, 6418). Two sites assume a dict outright (`cast.get`, 5494 and 5524; `cast.values()`, 5723), so the shims are dead. The "holders of this surface_fact" join is rebuilt in 3 places (2946, 3181, 3442). The culprit scan (6419) and the anchored-set build (2555–2560) each walk clues by hand.
**Fix:** `CastIndex(nodes)` built once per turn, with `.get`, `.people()`, `.holders_of(fact)`, `.culprit`, `.genuine_required_holders(req)` and `.clues`. Annotate `cast: CastIndex | None` and delete the shims. Size S–M. Behaviour-preserving.

### 9. Display-name reading is cloned 11 times and the humanize idiom 17 times. S, **polish**
**Evidence:** local closures `_disp` (527, 6081), `_display` (3043), `_pin_name` (4303), `_name_of` (4534), `_live_name` (5122), `_npc_name` (5424), `_resolve_name_of` (7609), `_held_name` (7210), `_id_attr` (7140) and `_exact_names` (603), plus 19 `state(…, "name")` reads. The inline `split(":",1)[-1].replace("_"," ")` appears 17 times, sometimes with `.title()` and sometimes without, although `_human_entity` (executor `_human`) exists and is imported (63).
**Fix:** `display_name(eid, *, reads, table=None, frame_names=None) -> str`, with a fallback that always goes through `_human_entity`. Make `_human` public in executor. Size S. Mostly behaviour-preserving; title-casing differences should be pinned by tests first.

### 10. The write seam: two handles, hand-stamped time, hand-rolled confirmation. M (**polish** for confirm, **proposal** for default stamping)
**Evidence:**
- In-turn writes go through `p` (`_FailOpenIngest`, fail-open) or the raw `world.porcelain` (1805, 1954, 2326, 2497, 3126, 3595) by call-site taste. For example, `_grant_moved_place` writes raw and unguarded inside the movement phase, so an ingest raise there sinks the turn, while the identical companion commit fails open.
- `"valid_from": turn_time(turn)` is typed by hand 86 times, with gaps (B6).
- The receipt complete-set pattern (`confirmed_batch(rows, _receipt_rows(r), cap=len(rows))` then `len(confirmed)==len(rows)`) is hand-rolled at least 8 times (1644, 1683, 3088, 3106, 3127, 3596, 4978, 2480).
**Why it matters:** "spine loud-fails, fan-out fails open" (the module docstring) is the policy, but which handle a site uses decides its real policy, invisibly. The temporal-state rule (1292–1317) is enforced per site.
**Fix:** a turn-scoped `TurnWriter(p, turn, trace)` with `write(rows, *, frame, classify, temporal=True) -> Receipt`, `write_all_or_nothing(rows, …) -> bool` (the confirmed complete-set), and an explicit `strict=True` for spine writes. The confirm helper and an explicit `strict` flag are polish. Defaulting `valid_from` for positional attributes changes rows, so it is a proposal and fixes B6 structurally. This changes no porcelain verb, only how the host composes calls.

### 11. `run_turn`'s 21 parameters are a per-world contract passed every turn, with contradictory flags. M, **polish**
**Evidence:** 3910–3927 includes `mode="pure"`, `endless: bool=False`, `scenario_mode="endless"`, `terminal_owner`, `death_policy`, `suspense`, `cost_disposition`, `judgment_type`, `result_events`, `style`, `play_style`, `laws`, `reality`, `generate`. All are free strings with defaults, and session passes all of them on every call (session.py:1079–1096). `endless=False` and `scenario_mode="endless"` are both defaults and mean different things: `endless` governs aftermath settling (6333, 6602, 7074, 7168, 7482, 7693), while `scenario_mode` governs win/loss termination (6160, 6323, 6574). The same word names two axes. `death_policy` takes `"mortal"|"premise"|"shielded"` and is compared as raw strings in 4 places.
**Fix:** a frozen `PlayContract` dataclass with Enums (`Authoring.PURE|COAUTHOR`, `Termination.WIN_LOSS|OPEN`, `Settling.AFTERMATH|CONTINUOUS`, `DeathPolicy`, `Suspense`), built once by Session from meta. `run_turn(world, arc, provider, text, turn, *, contract, scope, cast, side_arcs, horizon, on_scene)`. Keep a kwargs shim for the 54 test call sites during migration. Size M.

### 12. Module seams: move presence, the carrier surface and the name matcher out, and stop the reach-ins. S–M, **polish**
**Evidence:**
- `resolve.py` (the identity authority) lazily imports `_names_entity` from turnloop to dodge a circular import (resolve.py:206, 445).
- `session.py:806` imports the private `_colocated` and `_departed_from`.
- The presence authority is split across `_colocated`, `_departed_from`, `_persons_under`, the `_present` closure (5285) and the cast-moves lane's `_dest_in_scene` (1529). `_dest_folds_to_place` (2412) re-implements the lane's `_head_is_place` (1516); its docstring says "reused here", but it is a copy.
- The carrier-move public API (`CarrierMovePolicy`, `validate/prepare/confirm/commit_carrier_move`, 12 external refs) lives in the turn loop.
- Turnloop imports privates from other modules: `_human`, `_last_development_min`, `_mark_development`, `_pacing_ok`, `_sanitize_hook`, `_PLAYER_INPUT_MINT_KINDS` and friends.
- It reaches into `getattr(live_reads, "_horizon", None)` (378, 593).
**Fix:**
- `construct/presence.py`: `is_present(eid, scene, chain, *, reads, as_of)`, `persons_under`, `departed_from`, `head_is_place`.
- `construct/carrier.py`: the carrier surface.
- `construct/names.py`: `names_entity`, the tokenizer and `display_name`; resolve and turnloop both import it, which removes the cycle.
- Make the reached-into privates public in their home modules, and give `PorcelainWorldReads` a `horizon` property.
Size S–M. Pure moves plus re-exports.

### 13. Dead code, near-duplicates and lying names. S, **polish**
- `run_turn_sync = run_turn` (7969): 0 references.
- The `kind == "ooc"` branch (4204–4211): the classify enum has no "ooc".
- `_grant_equipment` (1962) and `_grant_taken_object` (1988) are the same function with a `manner` string and a different return type. Fold them into `_grant_ordinary_object(manner)`.
- `_has_time_deadline` (3824) and `_deadline_remaining` (1837) duplicate the `failure_when` elapsed-Quantity scan. One `_elapsed_deadline(arc) -> Quantity|None` should serve both.
- `_destination_facts` joins with `"\n"` only for `_destination_directive` to split on `"\n"` again (120). Return a list.
- `_RELOCATE_CONFIDENCE_MIN` gates absence (3021) and repair (3560) too; rename it `_DRIFT_PICK_MIN`.
- `_concealed_move_vocab` has the misleading docstring noted in finding 4.
- Two mid-file stdlib imports (`import time` at 86, `import os` at 1057) and 60 function-local imports, most of them not cycle-breakers (`json`, `hashlib`, `Path`, `cohorts` re-imported at 1972 and 1999 although it is imported at the top).
- Tombstone comment blocks (1087–1103) record what moved where. That history belongs in git.
- Redundant guards: a `try` around `_route_obstruction` (2288–2291), which already never raises; the `try` inside `_FailOpenIngest` around a list append (1240–1243); `hasattr(trace, "to_dict")` in `_write_mechanics_log` (7938).
- `terminal_outcome(live_reads)` is evaluated 4 times in about 150 lines (6202, 6236, 6250, 6358), at 3 event reads each. Compute it once.

### 14. Broad excepts and comment sediment: make the failure policy and the "why" legible. M, **polish**
**Evidence:** 154 `except Exception` in the file, 19 of them followed directly by `pass`/`continue` with no log. Example: the companion-snapshot except at 5048 and the alias-learning except at 4841–4842 drop silently, so a broken alias write would never surface.
1,846 comment lines (23% of the file); 224 "Cx NNN", 81 "cr" and 107 "#NN" references. Many blocks narrate the review history ("cr round-3 blocker 3", "re-review round 2") rather than the invariant. Several identifiers and receipts carry incident codes rather than meaning (`_TICK_*` are fine; `# #80 tuning (task #5)`, `# #113 durability BACKSTOP (cr code review)` are not).
**Why it matters:** a reader cannot tell a deliberate fail-open from an accident. The invariants that matter (receipt-confirmation, horizon binding, one generative act per turn) are buried under provenance.
**Fix:** a `fail_open(trace, label)` context manager that logs at warning and appends to `dropped_cohorts` uniformly, replacing the hand-rolled variants. Everything not wrapped is then loud by construction, matching the docstring's stated policy. During each phase extraction (finding 2), rewrite comment blocks as one-sentence invariants with the doc anchor, and move review provenance to the design docs and git messages. Size M, spread across the extraction. Behaviour-preserving apart from added logging.

---

## 4. What to keep (worth protecting during the polish)
- **Receipt-confirmed commits:** `confirmed_batch` and the complete-set discipline in `_absence_beat`, `_repair_beat` and the cast-moves lane are right. They only need one helper.
- **`CarrierMovePolicy`/`CarrierMoveResult`:** a model for the rest of the file. It is frozen, carries explicit mode policy, separates validate, prepare and commit, and is typed.
- **Pure, well-specified helpers:** `_partition_frames`, `_canonicalize_containment`, `_stamp_temporal_state`, `_walkable_route`/`_polar_atoms`, `_partition_cast_moves`. They are small and contract-first.
- **Host-built drift directives** (the model picks only WHO, and the host writes every fact): this is the right authority split.
- **`GenerativeSlot`:** one generative act per turn, enforced structurally.
- **The synchronous receipt plus deferred `_settle` split** for latency, with durability preserved.

## 5. Suggested sequencing for a polishing branch
1. Fix B1–B5 (each S, safe or near-safe; B3 is a one-phrase prompt edit).
2. Findings 1 (`Intent`), 9 (`display_name`), 13 (dead code), 8 (`CastIndex`): small and mechanical, and they shrink `run_turn` before extraction.
3. Finding 12 (module moves), then finding 2 (phase extraction, briefing first), then finding 5 (typed trace and state).
4. Findings 3-polish (`_commit_travel`), 4 (the concealment vocabulary), 10-polish (`TurnWriter` confirm), 11 (`PlayContract`), 14.
5. To the founder as proposals: 3-proposal (`resolve_move` table), 6-prompt (briefing consolidation), 7 (classify `addresses`/`presses`), 10-proposal (default stamping).
