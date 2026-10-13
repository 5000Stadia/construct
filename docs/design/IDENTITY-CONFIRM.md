# Identity confirm at build (R34 P2 + P3): spec r2

**Status:** r2, 2026-10-12, GREEN at cr as a specification. r1 was RED at cr (two blockers, both taken below; the policy itself was judged sound). pattern-buffer shipped IDENTITY-REPRESENTATIVE-V1 at `f275e40`. Review: cr.
**Built** on `feat/identity-confirm`: `_stage_confirm_identity` in `construct/game.py` (steps 2 and 3, run right after the vouch), the cast-collision reject in `_admit_disambiguated_cast` (step 4), and the build-stop contract on every creation path, the CLI and the atrium. Checks 2-7 are `tests/test_identity_confirm.py` plus the atrium case in `tests/test_telegram.py`. All engine reads go through the porcelain: closures and distinctness come from `closure()` and `distinct_between()` (pattern-buffer CLOSURE-READ-V1, R42), and the frame-evidence scan reads `facts(frame, bookkeeping=False)` (FACTS-BOOKKEEPING-V1, R42a), so the host holds no list of the engine's bookkeeping attributes. Engine pin `0eb4e3f`.
**cr's code review** of `8ec8e27` was RED on two points, both fixed. (1) The vouch failed open: a bad receipt or a wrong survivor now stops the build, and so does a failed cast-collision reject. (2) The scan imported an engine constant; it now uses the porcelain filter above.
**Decision:** gate gc53c58, consult c12f82c. The monitor accepted P1–P3 on Kabe's behalf (note n126701). P1 is shipped as a test (`tests/test_identity_play_guard.py`).
**Evidence:** `eval/14-frame-owner-measurement.md` (2 of 2 fresh builds split or twinned the hero); `eval/12` runs 2, 4, 5 and 6.
**Engine:** R35 (no auto-merge of a frame owner), R36 (P1: frames read only their own names), IDENTITY-REPRESENTATIVE-V1 (a host merge or confirm names the survivor; `Receipt.canonical_id` is the elected representative).

## Need

The hidden arc binds play to literal ids: the protagonist, and the holders of required clues ("load-bearing" ids). Under the engine's rules, two things go wrong at build:
1. **The wrong survivor.** Construct's vouched merge folds a fragment into a load-bearing id. The engine elects the first-seen member, so the fragment's id can win. The arc row then reads back under it, while the beats watch the authored id (build 1 in eval/14; runs 2, 4, 5).
2. **The unmerged twin.** A name variant that owns a `knows:` frame comes back as a `frame_owner` proposal. The vouch allowlist never folds it, so a second copy of the hero stays live and takes NPC turns (build 2; run 6).

## Design

All of this happens at the **vouch slot** (`construct/game.py`, after cast authoring, before `arc_to_items`). It is the one point where the load-bearing ids are known, the beats name them, and no frame is seeded yet.

1. **Survivor = the load-bearing id.** Every host merge or confirm that touches a load-bearing id passes `representative=<that id>`. The build checks that `receipt["canonical_id"]` equals it. If it doesn't, the build stops as not viable. This applies to the existing vouched merges as well as the confirms below.
2. **Confirm the load-bearing frame-owner pairs (P3).** For each open `frame_owner` proposal with exactly one load-bearing side, decide over **closures**, not ids. A is the fresh closure of one side and B of the other, both recomputed after every decision.
   - **Frame-evidence scan (exact).** Read the **raw stored rows** of `knows:<m>` for every member `m` of A ∪ B. Use no identity-resolved or entity-filtered read: a frame can be owned by any member, and a resolved read would fold the very pair in question. A row is evidence of two people only if it is:
     - entity-valued;
     - not a mechanism row (identity, provenance, receipt, retraction);
     - such that its subject is in A and its value is in B, or the reverse.

     Rows merely *about* the other closure (its subject in B, its value not in A) are not evidence. A fragment's facts often sit in the hero's frame under the fragment's id. On evidence, `reject(a, b)`.
   - **Never join two load-bearing closures.** If A ∪ B would hold two load-bearing ids, either directly or through a closure grown by an earlier confirm in the same pass, nothing is merged and the pair is left open (and step 3 stops the build).
   - **Otherwise** `confirm(a, b, representative=<the one load-bearing id>)`.
   - **Receipts decide, not intentions.**
     - A reject clears the pair only if its outcome is `rejected` or `noop_already_distinct`.
     - A confirm clears the pair only if its outcome is `merged` or `noop_already_merged` **and** `canonical_id` equals that sole load-bearing id.
     - Any other receipt leaves the pair unresolved, and step 3 stops the build. That includes `no_proposal`, `vetoed`, `conflict_*`, a different `canonical_id`, or an exception.
   - Re-read proposals after each decision, and repeat until a pass decides nothing.
3. **Stop the build when the hero or a clue holder stays split (P2).** The check is per pair and per closure, never inferred from a group as a whole. After step 2, the build stops if any of these touch a load-bearing closure:
   - an open `frame_owner` proposal;
   - a pair in a live `fidelity_audit()` name-collision group whose own status is `unlinked`, `auto_declined` or `typing_slip`, unless that exact pair is merged (same closure) or explicitly distinct (`distinct_from` between those two closures).

   An id merely appearing in some `distinct_from` row does not count. The stop raises `IdentityUnresolvedError`, which carries the unresolved pairs.
4. **Cast-collision ids are deliberately distinct.** `disambiguate_cast_identities` gives a cast conception a fresh `person:<slug>_N` when its id collides with a different canon person (#92), for example `voss` and `voss_2`. `_admit_disambiguated_cast` will also write `reject(orig, fresh)`. That keeps reconcile from ever proposing the pair, and keeps step 3 from stopping on it.

## The build-stop contract (every creation path)

`ProtagonistSplitError` (the seal) and `IdentityUnresolvedError` (step 3) share a base, `BuildIdentityError`.
- **Every public creation function** turns it into `ViabilityError(name, source_path, [the reason])` after its own cleanup has removed the half-built world. These are `create_scenario_from_generated`, `create_scenario_from_ingest` and `create_scenario_from_interview`. `source_path` is:
  - the generated source, for a generated world;
  - the prose file, for an ingested one;
  - for an interview, which has no source file, the interview's brief, saved beside generated sources as `generated/<name>.brief.md`.
- **Every caller** handles `ViabilityError`, and nothing reaches the user as a traceback:
  - `cli build`, on its generate, interview and ingest branches (today only generate catches it);
  - the CLI's in-session create and import (already caught);
  - the atrium.
- **The atrium's** one retry consumes `ViabilityError` like any build failure. The guest is shown the first of `exc.problems` in plain words, never the exception's text.

## Role-noise adjudication (R20 run 8; spec r2, for cr review, not built)

r1 merged on lexical evidence and was RED (cr, <3da26109>).
- **Lexical evidence is not enough.** In "Tomas Breck entered the yard. Breck the baker shut his stall.", a scan of full-name runs cannot show that every bare "Breck" is Tomas. So a lexical rule can merge two real people.
- **The title rule was undefined.**

r2 replaces the lexical rule with the resolver decision cr named, which is also what the engine itself asks for. Its decline evidence reads "gate declined (adjudicate)".

### The failure

Run 8's build stopped, by design, on four load-bearing same-name pairs in the `person:` namespace, each auto-declined `kind_conflict`:
- `elias` ~ `elias_venn`;
- `breck` ~ `tomas_breck`;
- `father_oren_vale` ~ `father_vale`;
- `nessa` ~ `nessa_reed`.

Each is one person in the build's own source. The kinds differ only by extraction's role words.

### What does not fix it

**Making the kinds agree** (pattern-buffer's root-cause point) does not merge them. Tested on the real engine (2026-10-13, scratchpad `kindexp`): with both kinds `person`, the engine declines Breck/Tomas Breck **and** Lysa/Lysa Fen alike, as `alias_not_specific`, "gate declined (adjudicate)". The engine has no evidence to tell them apart either.

### The adjudication

`_stage_adjudicate_identity`, run just before the confirm stops. It applies to each live same-name pair that touches a load-bearing closure and that the engine left undecided: no shared closure, no `distinct_from`, and an auto-decline code of `kind_conflict` or `alias_not_specific`.

**Evidence.** The resolver gets two kinds:
- **Each entity's folded canon facts.** These are kind, role, aliases, places and relations: the closure's rows, capped.
- **The source passages that mention each name** (ingest path). Every sentence of the build's source containing either entity's name or alias, each tagged with which names it contains. The interview path has no source; its resolver gets facts only.

**The question.** One cheap-tier model call per pair: "Are A and B the same person?" The schema allows exactly one of:
- `same`, with `quote`: the source sentence or fact that ties them, verbatim;
- `different`, with `quote`: the sentence or fact that separates them;
- `unsure`.

**Acting on the verdict:**
- **`same`.** Allowed only if the quote is found verbatim in the evidence given; otherwise the verdict counts as `unsure`. The pair is merged with `porcelain.merge(a, b, evidence)`, and the representative is the load-bearing id (the hero keeps `person:elias_venn`). The evidence string is `adjudicated same person: "<quote>"`.
- **`different`.** Allowed only with a verbatim quote, else `unsure`. The pair is held apart with `porcelain.reject(a, b)`. A pair held apart by a decision is decided, so the confirm stage does not stop on it.
- **`unsure`, or a failed call.** Nothing is written, and the confirm stage stops the build as today.

**Scope:**
- Only load-bearing pairs are adjudicated. Non-load-bearing pairs stay held apart as today.
- Cast-move, vouch and confirm logic is otherwise unchanged.

### Why this answers r1's objection

The resolver reads the very sentence cr's counterexample turns on ("Breck the baker shut his stall"). A `same` verdict must quote its tie, and an unquoted or unsure answer stops the build, so the worst case is today's behaviour.

### Telemetry

Each verdict logs at INFO with its quote. The build's stage output lists "identity: adjudicated N pair(s): M same, K different, U unsure".

### Tests (stub provider, real engine)

- the four run 8 pairs merge on `same` with a verbatim quote;
- `same` with a quote not in the evidence counts as unsure and stops;
- `different` holds apart (`distinct_from`), and the build does not stop on that pair;
- `unsure`, and a raised call, both stop;
- the Breck-the-baker source gives `different` (scripted), and it is respected;
- non-load-bearing pairs are never adjudicated;
- the representative is the load-bearing id;
- the evidence passages hold only sentences naming either entity.

### Cost

One cheap-tier call per undecided load-bearing pair, usually 0–4 per build. Run 8 would have made four.

### Not in scope (a separate item)

pattern-buffer's root-cause point: `kind` should be a closed type set, with the role in its own attribute. It is still worth doing for its own sake, but the test above shows it does not by itself resolve these pairs.

## Not in scope

- **Continuing the fragment's knowledge** (R36 `continue_frame`) into the hero's frame. Beat gates read `knows:<hero>` with the exact scope. Widening it would let pre-play telling-scene knowledge satisfy beats before play begins. So no beat read widens, and whether any read should is a separate decision.
- **Merges during play** (P1 forbids them) and **repairs to existing worlds** (Kabe's, gate g82aabc).

## Checks

1. A fixture with a first-seen fragment folded into the protagonist: the arc row reads back as the authored id, and the seal passes. Negative control: without `representative=`, the seal raises `ProtagonistSplitError`. (The vouch side is shipped ahead of this spec on `fix/vouch-representative`, narrower than it: it names the survivor and logs a mismatch.)
2. A fixture with an open `frame_owner` proposal on the protagonist: confirmed with the protagonist as the survivor, and the build is viable.
3. **(a)** A frame owned by a **closure member** (not the proposal's own id) holding a relating row between A and B: the pair is rejected. A row only *about* the other closure: not rejected.
4. **(b)** Non-success receipts stop the build. A stubbed `reject` or `confirm` returns `no_proposal`, `vetoed`, `conflict_already_merged`, or a different `canonical_id`; each one stops the build with the pair named.
5. **(c)** Transitive cascade: three proposals where confirming the first would let the second join two load-bearing closures. No closure ever holds two load-bearing ids, and the build stops.
6. A cast-collision pair (`voss`/`voss_2`): `distinct_from` is written, there is no proposal after reconcile, and the build doesn't stop.
7. **(d)** The same identity stop through each entry point: generated, direct ingest, interview, and the atrium. Each one cleans up the half-built world and surfaces one `ViabilityError` outcome. The CLI prints the viability message with exit code 1, and the atrium retries once and then shows the plain reason.
8. A build-only rerun of the eval/14 seed, twice. Record viable or stopped, and every confirm, reject and stop with its pair.
9. The full suite is green.
