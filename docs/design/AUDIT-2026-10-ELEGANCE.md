# Self-audit: the intelligence and elegance of construct's structures — 2026-10-08

**Asked by Kabe** (via the monitor, 2026-10-08): "pattern buffer and construct were made with weaker models they may want to do a self audit on the intelligence and elegence of the structures for self directed polishing."

**Exit, set before starting:** one pass over each part, this ranked note, and the top fixes done on their own branches, with behaviour otherwise unchanged and tests green before (1232 passed) and after. Rewrites, migrations, prompt rewording and anything that changes how construct calls the pattern-buffer porcelain come back to Kabe as proposals.

**Method.** Five read-only auditors each read one part in full against the July fresh-eyes audit (`AUDIT-2026-07-FRESH-EYES.md`), the membrane, the porcelain boundary and the prompt-elegance tenet:
- the turn loop (step-up tier);
- the arc layer (step-up tier);
- cohorts and the provider;
- the world, session and engine seam;
- the transports.

Their full reports, with file:line evidence, are in [`audit-2026-10/`](audit-2026-10/). The ranking below is mine, made across all five.

## Verdict

The July verdict holds and has sharpened. The ideas are right: three-valued truth, frozen atoms, the arc as host `plot:` rows, coverage-as-effect, transports over one Session, and engine gaps sent to the engine. The disease is still **accretion, and it has grown**:
- `run_turn` has gone from 2,242 lines to 4,010.
- Broad excepts have gone from 53 to 70.
- There are now at least 8 tokenizers and 7 slug helpers.
- The `resolve_move` decision table the July audit asked for was never built.

New features since July landed as clean helpers: the world tick, the drift family, growth and cast moves. The old inline phases were never extracted. Stronger models can afford to do now what incident-by-incident fixing never had room for: give the turn its types, and pull its phases apart.

The audit also found **real bugs**, several of which change what players see. Those come first.

## Tier 1: bugs, being fixed now (branches `polish/*`, each with a regression test)

| # | Bug | Where | Why it matters |
|---|---|---|---|
| 1 | **The protagonist's own name is screened as a spoiler.** A placeholder premise `StateIs(protagonist, kind, person)` turns their name into concealed tokens. | `game.py:2252`, `arc/executor.py:771-806` | Silently drops the player's relationships, cold-open grounding, live threads and family memories. It fails closed, so nothing ever surfaced it. |
| 2 | After every chapter, the notebook says **"YOU — settled (a past chapter's answer)"**, and the next chapter's author is told the protagonist is closed history. | `game.py:2671`, `journal.py:75` | Same root cause as #1, and the player can see it. |
| 3 | `value_leaks` splits on whitespace only, so "the culprit," gets past the secret screen. | `arc/executor.py` | Truth-keeping: a hidden answer can leak into world-tick canon and place labels. |
| 4 | The stream reader ignores error, failed, incomplete and refusal events, which show up only as "no output text". Truncated JSON is then re-asked with the wrong diagnosis. | `provider.py:479-512` | Every refused request is undiagnosable. This hit the holo deck's first live run today. |
| 5 | `_clean_prose` cuts ordinary English ("The corridor — it ends…" becomes "The corridor —") and drops everything after a brace. | `cohorts.py:3475` | Player-facing narration is silently truncated. |
| 6 | After "End of Chapter", `/exit` leaves the continue prompt armed, so the next start-menu message builds a new chapter. | `transport_core.py` | An unwanted, slow and costly build. |
| 7 | The restart confirmation is parsed by substring, so `/help` or `/feedback` at step 3 **executes the restart**. | `transport_core.py:438` | A destructive action on an innocent message. |
| 8 | Telegram outbox head-of-line wedge: one permanently failing chat silences every player. | `telegram_bot.py` | Availability for everyone. |
| 9 | `continue_episode` writes the settled marks before calls that can fail, and leaks the world handle on failure. A retry duplicates the marks. | `game.py:2603-2945` | Half-written chapters; a SQLite handle leaked in the long-running bot. |
| 10 | Episode checkpoints are listed as scenarios (five ghosts in `worlds/` now). | `game.py:162` | The CLI and Discord pickers show junk. |
| 11 | Known-place token reuse commits a move without the route check. | `turnloop.py:4782` | A move can bypass map governance. |
| 12 | Reshape event ids lack the turn, so a second reshape overwrites the first. | `reshape.py:208` | Lost history. |
| 13 | Smaller: three malformed task tags; a dangling "(see A PEOPLED WORLD)" in the briefing; `cast` rebound to ids on terminal turns; an epoch contextvar leak in `_finalize_scenario`; a malformed arc proposal aborts the build instead of retrying. | various | Routing, prompt and latent-crash hygiene. |

Under investigation in the same pass:
- `_world_tick` reads not bound to the play horizon, the class Cx 259 fixed for NPC sheets.
- Host clocks possibly waking the player-caused generator.
- The per-chapter `death_policy` and title being computed and then dropped. This may need a meta-format change, which would make it a proposal.

### Outcome of tier 1 (merged into `polish-audit`, not into main, not pushed)

Five branches, each with regression tests, and each test checked to fail before its fix:
- `polish/concealment-arc`: bugs 1, 3 and 12, plus host clocks waking the generator.
- `polish/turnloop`: bug 11, the dangling references, `fate_cast`, and the world-tick horizon. The horizon bug was confirmed with a test.
- `polish/transport`: bugs 6, 7 and 8.
- `polish/world`: bugs 2, 9 and 10, plus the epoch leak, unbuildable arcs, and the per-chapter title and death policy.
- `polish/provider-cohorts`: bugs 4, 5 and 13's task tags.

Behaviour that changes on purpose, for Kabe to see:
- **The protagonist's name is no longer screened.** Relationships, grounding and family memories that were silently dropped now reach play. A genuine secret about the protagonist stays concealed (tested).
- **`_serve_thread` reads the real cast on terminal turns.** It was always true, because `cast` had been rebound to a list. The monitor agreed it can go in.
- **Known-place moves take the same route check and deliberation as the other two travel paths**, through one helper (`_gated_move_commit`) in place of three copies. A held known-place move no longer falls through to minting a new place.
- **Restart confirmations take exact one-word answers.** `/help` and `/feedback` pass through, anything ambiguous is re-asked, and "no" cancels. On main, "yes" to "keep or wipe your notes?" wiped them.
- **Telegram dead-letters a chat that fails permanently** (a 4xx other than 429) instead of blocking every player. Retryable failures still retry.
- **Refused or incomplete model calls now fail with the server's reason**, and are no longer paid for twice through a wrong re-ask.
- **The per-chapter title and death policy are stored as `session:episode` rows in the player's slot.** This is additive: a slot without the rows falls back to the scenario meta, and the meta format is unchanged.
- **`continue_episode` computes everything first, then writes, and closes the world in `finally`.** It also retries an unbuildable arc proposal up to three times.

Left as proposals:
- **Make the continuation's writes one atomic `commit_set`.** That changes how construct calls the porcelain: the classify mode, frames spanning more than one frame argument, and reads interleaved between writes. See `polish/world`'s report.
- **UTF-16 chunking and POST for Telegram.** For now an over-long chunk is dead-lettered, so the reply is lost instead of the chat wedging.

### pattern-buffer's answer on the seam (colony m36d2dd, checked against engine code with repros)

All three seam findings are real.
1. **Host-control folding.** pattern-buffer proposes a **per-attribute durability pin** (`attr:<name> · durability`, read before the model) rather than a frame flag. It also found an engine bug: `fold_policy: last_write` is advertised but ignored. The spec goes to pbr after Kabe has seen it. Interim advice is `classify='rules'` on host-control writes; because that changes how construct calls the porcelain, it is a proposal here.
2. **Tier routing.** Frozen **schema titles** become the task key. pattern-buffer is building this as polish, with no behaviour change. Construct will route on `schema['title']` and keep a drift test until then.
3. **`locate()` co-asserts.** An additive `conflicting_facts` on `state()`. Then construct's re-fold goes, which pattern-buffer showed is less correct than `state()`.

pattern-buffer's mirror findings that touch construct's play:
- `refer` saves ambiguity picks as permanent aliases, so "the drawer" resolves to the wrong drawer forever;
- a stale same-time tie blocks later moves.

Construct has asked for both to be ranked high.

## Tier 2: polish worth doing next (behaviour-preserving, ranked by value per effort)

1. **Type the turn's intent.** Classify returns a 26-field dict. Its defaults live about 4,000 lines away, across about 180 lines of loose locals in `run_turn`, and every field rule is written twice (schema and prompt). Fix: a `TurnIntent` dataclass. (cohorts F2, turnloop top-1; M)
2. **Extract `run_turn`'s phases over an explicit turn state.** Start with the briefing assembly (about 830 lines) moving to its own module, then a single `_commit_travel` in place of three copied route→deliberate→commit paths. (turnloop; M–L, staged)
3. **One text toolkit.** Replace 8+ tokenizers, 7 slug helpers and 11 name closures with one module, and one concealment-vocabulary object in place of five builders. Bug #3 is what drift between copies costs. (turnloop, arc; M)
4. **Type the scenario and playthrough state.** `ScenarioMeta` / `PlaythroughState` with one accessor, in place of meta dict reads across modules. Along the way, give `_state_value` one home in `adapter.py`, with `as_of` (July finding, still open; `clock._state_value` lacks `as_of`). (world F1, July §5; M)
5. **One pending-prompt state per player** in the transport, in place of six ad-hoc sets. These sets are the most bug-dense structure in the file (bugs 6 and 7, plus the earlier `/feedback`-swallowed bug). Also one command router, not two. (transport F1–F2; M)
6. **One per-turn `ArcStatus`** in place of seven overlapping "is it over?" checks, and **one three-valued evaluator** in place of drift's three copies. (arc F4–F5; M)
7. **Split by responsibility:**
   - `game.py`: arc construction goes to `arc/build.py`, with `_finalize_scenario` as named stages;
   - `executor.py`: timeline, conclusion, concealment, supersession;
   - `transport_core.py`: along its seams.

   All of these are pure moves. (arc F2/F6, world F4–F5, transport F4; L, staged)
8. **String vocabularies become `StrEnum`** (same stored values), and `TurnTrace`'s control fields get types (today they're parsed back with `startswith("activated:")`). (arc F7, turnloop; M)
9. **Delete dead code and false docstrings.** `phase_budget`, `refusal_variant_id` and `rearm` are provably dead. Several "review history" docstrings now lie. (arc F1, world F14, transport F11; S)
10. **Provider shape.** `OpenAIProvider` subclasses `CodexProvider`, so names mislead and settings leak across. StubProvider carries five copy-pasted test defaults. (cohorts F6–F7; S–M)

## Tier 3: proposals for Kabe (rewrites, prompt rewording, format or seam changes)

- **The narrator's rule blocks have re-accreted.** RENDER_LEASH and RENDER_STYLE have grown back past their July trim. There are 57 restatements of "diegetic". A mystery-only neutrality rule goes out to every genre. Author notes ("founder:", doc names) leak into the narrator's input. Every story shape states its core rule twice. Recommendation: one careful prompt pass, with a live fiction-quality check before and after against the ledger. (cohorts F3, turnloop, arc)
- **`author_cast` gives every shape the deduction-only staging** (culprit, body-finder, red herring). Recommendation: make it shape-specific. It changes fiction, so it needs a live check. (cohorts BUG-4)
- **The weave cohort's output is mostly thrown away** (`seam_hint`, `directive`, `deliver_card` overridden). Either use it or shrink the call. (cohorts F1)
- **The `resolve_move` decision table** (July's ask, still unbuilt), and **classify returning `addresses`/`presses`**, so the period-specific role lists can retire. (turnloop)
- **An atomic main-arc swap through `commit_set`**, reusing tangent's `PortfolioState`. Today two of the three swaps can leave no manifest. This changes how construct calls the porcelain, so it needs comparing with pattern-buffer. (arc F3)
- **A typed play contract** in place of 21 string parameters to `run_turn`, including the contradictory `endless` / `scenario_mode` pair (world B9). (turnloop, world)
- **Meta keeps copies of engine truth**, against the membrane. Move them to reads. This needs a format migration. (world F12)
- **Transport choices:** retire or port Discord; Telegram serializes all players on one thread, so a 20-minute build freezes everyone; three CLI front doors; `/feedback` still writes into the retired `dev_inbox/`; operator commands have no operator check; `/wipe` misses most saves. (transport F6–F7, F10, F12, bugs 5–6)
- **Engine-seam items for pattern-buffer:**
  - host-control frames could skip the engine's durability classifier (arc F13);
  - engine calls are routed to a tier by matching pattern-buffer's prompt wording, which is fragile (cohorts F9);
  - `_live_in_candidates` works around an engine gap locally (world F13).

  All three go to pattern-buffer as questions, not as local changes.

## What to keep exactly as it is

The five-verb porcelain boundary, three-valued truth with frozen atoms, the host `plot:` rows, coverage-as-effect, the drift family, the world-growth seam on ATOMIC-ACTIVATION, the transports' shared Session API, and the fail-closed concealment instinct. The instinct is right; bug #1 is its placeholder input, not the rule.

## Approved proposal landed: knows: reads via pattern-buffer's frame-knowledge recipe (for Kabe's eye)

A before/after over 72 worlds: 59 differ, and every differing line is a correction. Set members now all show, evidence rank holds, `same_as` identity holds, EVENT rows are no longer shown as knowledge, and pre-play rows are visible.

Surprises:
- **Fold-then-screen.** When the newest value of a key is concealed, nothing shows, where an older value used to stand in. This fails closed, but notebook entries can vanish (Harth in `emberroad.critic`). Say if you'd rather keep the stand-in.
- On an engine-flagged tie the freshest side stands (the old behaviour), until pattern-buffer settles its tie rule.
- `knows_about`, `knows_place`, `knows_person` and `likely_familiar_with` are not declared set-valued in `semantics.py`, so same-time rows tie.
- `journal.py` still shows one member of a set.
- `build_sheet` now takes about 0.1 s a turn on the largest world, up from about 10 ms.
