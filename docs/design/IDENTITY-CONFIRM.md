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

## Role-noise adjudication (R20 run 8; spec r5, for cr review, not built)

**Status.** r5 (cr RED on r4: kind_conflict admission, audit field names, the API) is written against pattern-buffer's `porcelain.merge_gate(pairs, *, context=None, batch_size=25)` verb, MERGE-GATE-VERB-V1 r1.1 at pattern-buffer `36bd8b6` (`feat/merge-gate-verb`). Construct pins the engine to the merged revision when it lands. The verb is (R48, mae57ff; contract r1.1 mfee55c: report-only, never caches). The verb was approved by the monitor (g9e7f39) and is in pbr's review. Construct builds this stage only when the verb has shipped. Until then the build stop stays.

**History.**
- r1 (lexical) was RED: "Breck the baker".
- r2 (one quoted model verdict) was RED on three points:
  - it could join two load-bearing closures;
  - a single verdict is a proposal, not a confirmation;
  - a `different` must be written only on a checked receipt.

r3 takes all three and uses the engine's adjudicator instead of a construct one. The engine's gate is MERGE-GATE-V1 (0 wrong merges in 39 known-different pairs, measured 2026-10-13 under Kabe's yes, gf981cd).

### The failure, and what r5 does and does not fix

Run 8's build stopped, by design, on four load-bearing same-name `person:` pairs, each auto-declined: `elias`/`elias_venn`, `breck`/`tomas_breck`, `father_oren_vale`/`father_vale`, `nessa`/`nessa_reed`. Each is one person in the build's own source.

Making the kinds agree does not resolve them. Tested on the real engine: with both kinds `person`, the engine declines Breck/Tomas Breck and Lysa/Lysa Fen alike, as `alias_not_specific`, "gate declined (adjudicate)".

**r5 does not fix run 8's four pairs by itself.** They are `kind_conflict`. They become eligible only once extraction keeps `kind` to a closed type set with the role in its own attribute: pattern-buffer's root-cause point, and its planned type/role split. They would then fold same-kind and arrive as `alias_not_specific`, as the test above shows. So R20's next run depends on both:
- the `merge_gate` verb;
- that split.

Until both land, a world like run 8's still stops at build, by design.

### The stage: `_stage_adjudicate_identity`

It runs after `_stage_vouch_merges` and before `_stage_confirm_identity`.

**1. Candidates: a hard eligibility rule, checked per exact pair.** The audit is read field by field. A group in `fidelity_audit()["name_collisions"]` has:
- `entities`, and `kinds` parallel to them;
- `pairs[]`, each `{a, b, status, reason?}`.

A pair is a candidate only when all of these hold:
- **Its engine verdict.** The pair's own `status == "auto_declined"` and its `reason == "alias_not_specific"`. That is the shipped vouch's allowlist (`_fidelity_vouched_pairs`), where the folded kinds of a and b (read from the group's parallel `kinds`) are equal.
- **Never eligible:**
  - any other status: `unlinked`, `typing_slip`, `hard_blocked` (whatever its reason, `containment` or `distinct_from` included), and any unknown status;
  - any other `auto_declined` reason, **`kind_conflict` included** (cr r4 P1). A `kind_conflict` says only that the two folded kinds differ. Nothing in construct can prove the difference is a role word ("condemned man") rather than a type ("horse"), and a negative word list is not proof.

- **Not already decided.** There is no shared closure, and `distinct_between(a, b)` is empty.
- **Exactly one load-bearing id** in `closure(a) ∪ closure(b)`. The load-bearing ids are the protagonist plus the required-clue holders. With none, the pair is held apart as today. With more than one, the confirm stop fires.
- **Source-backed** (cr r3 P1). The build's source has at least one sentence naming each side; see context below. On the interview path, or where either side has no matching sentence, the pair is **not a candidate**, and today's stop stands.

**2. Context.** The host supplies it, because the engine holds no source:
- for each candidate id, the source sentences that contain any of its names or aliases (whole word, case-insensitive);
- in source order, at most 2 per id, each cut to 400 characters. That is exactly how the verb normalizes context (2 sentences per representative, at 400 characters), so the frozen request is what the model receives. A test asserts the final gate payload.

**3. Two independent asks, tied to one frozen request.**
- **The frozen request.** The candidate list (sorted pairs, with stable pair ids) and the context are built **once**, and a digest is taken over their canonical JSON.
- **Two fresh calls.** `porcelain.merge_gate(<frozen pairs>, context=<frozen context>)` is invoked twice. The verb only reports and writes nothing; its contract says it never caches (pattern-buffer mfee55c). Each report must carry `cached: false` and its own fresh `call_id`. A report with `cached` true, or a second `call_id` equal to the first, is rejected. Construct's injected model (`engine_tier_dispatch(provider)`) must not memoize either, and a test pins that.
- **Checking each answer against the request.** Each report's `requested` must equal the frozen pairs exactly, and the `requested_as` indexes over its entries must cover every index exactly once. Otherwise that whole answer is void, and every pair is left open.

A pair's outcome:
- **Merged.** Both answers say `same`, and neither puts the pair in a `conflicting_component`. The host writes `porcelain.merge(keep, other, evidence="merge gate x2 <digest>: <reason 1> | <reason 2>", representative=keep)`, where `keep` is the one load-bearing id. The receipt must be `merged`; otherwise the stop stays.
- **Held apart.** Both answers say `different`. The host writes `porcelain.reject(a, b)`. The receipt must be `rejected` or `noop_already_distinct`, and `distinct_between(a, b)` must then be non-empty. Only then does the confirm stage count the pair as decided.
- **Left open.** Anything else. Nothing is written, and the confirm stage stops the build as today.

**4. Revalidate before each write.** Re-read the closures. The exact requested pair must still be two closures and must still pass every eligibility test in step 1, re-run against the current audit. An earlier merge in the same pass may have changed them. If it fails, the pair is left open.

**Why this meets r2's objections.**
- A merge needs two independent `same` verdicts from the engine's measured gate, plus a checked receipt.
- Two load-bearing closures are never joined.
- `different` is written only when both calls say so and the receipt checks out.
- The worst case is today's stop.

### Telemetry

The build's stage output reads "identity: adjudicated N pair(s): M merged, K held apart, U left open". Each decision logs at INFO with both reasons.

### Tests (stub `merge_gate`, real engine otherwise)

- **Eligibility, selected field by field from real `fidelity_audit()` group fixtures:**
  - an `auto_declined` / `alias_not_specific` pair is a candidate;
  - `auto_declined` / `kind_conflict` is never sent, including a person-role pair like run 8's and a `person:` id whose kind is "horse";
  - every other status is never sent: `unlinked`, `typing_slip`, and `hard_blocked` with `containment` or `distinct_from`, as is an unknown status;
  - a pair is matched to its kinds through the group's parallel `entities`/`kinds`.
- **No source.** The interview path, or one side with no matching sentence: not a candidate, and the build stops.
- **Two load-bearing ids, or none.** Not sent; the build stops, or the pair is held apart as today.
- **A same-kind role split, the run 8 shape after the type/role split.** An `alias_not_specific` pair (for example `person:breck` and `person:tomas_breck`, both of kind person) is merged on two `same` answers with a checked receipt, with the load-bearing representative and the digest in the evidence.
- **Left open:** a `same` with an `unsure`; disagreement; a `conflicting_component`.
- **Held apart.** Two `different` answers: a checked reject. A bad reject receipt is not counted, and the build stops.
- **Answer integrity.**
  - An answer missing a pair, with an extra pair, or with mismatched ids is void for the whole answer.
  - A reused or cached second result is rejected.
- **Revalidation.** A pair whose closures changed between the asks and the write, or that no longer passes eligibility, is left open.
- **Context.** Deterministic and capped, holding only sentences naming the pair.
- **The verb's absence.** An engine without `merge_gate` skips the stage, and the build stops as today.

### Cost

Two gate calls per build at most; candidates are batched, 25 to a call. Run 8 had four pairs, so one batch per call. They run on the world's injected model, which is the Codex subscription for construct's runs.

## Not in scope (a separate item)

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
