# Identity confirm at build (R34 P2 + P3): spec r1

**Status:** r1, 2026-10-12. Built only after pattern-buffer ships IDENTITY-REPRESENTATIVE-V1. Review: cr.
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
2. **Confirm the load-bearing frame-owner pairs (P3).** For each open `frame_owner` proposal with exactly one load-bearing side:
   - **Reject first, on frame evidence.** If either side's own `knows:` frame holds a relating row between the two ids (`a · <relation> · b` or the reverse), they are two people. `reject(a, b)` (sticky), and don't confirm. Rows *about* the other id are not evidence: a fragment's facts often sit in the hero's frame under the fragment's id.
   - **Never join two load-bearing ids.** A proposal whose closures would put two load-bearing ids together is left open.
   - **Otherwise** `confirm(a, b, representative=<load-bearing id>)`.
   - Re-read proposals after each confirm, and repeat until nothing changes, because each confirm can raise knock-on proposals. Decisions are made per closure, not pair by pair, so a cascade like a six-way fusion in a live world cannot build up.
3. **Stop the build when the hero or a clue holder stays split (P2).** After step 2, raise `IdentityUnresolvedError` (wrapped as `ViabilityError`, like `ProtagonistSplitError`) if any of these touch a load-bearing id:
   - an open `frame_owner` proposal;
   - a live same-name group from `fidelity_audit()` whose members are not merged and not marked distinct.

   The creation paths already delete the half-built world, and the atrium transport retries a build once.
4. **Cast-collision ids are deliberately distinct.** `disambiguate_cast_identities` gives a cast conception a fresh `person:<slug>_N` when its id collides with a different canon person (#92), for example `voss` and `voss_2`. `_admit_disambiguated_cast` will also write `reject(orig, fresh)`. That keeps reconcile from ever proposing the pair, and keeps step 3 from stopping on it.

## Not in scope

- **Continuing the fragment's knowledge** (R36 `continue_frame`) into the hero's frame. Beat gates read `knows:<hero>` with the exact scope. Widening it would let pre-play telling-scene knowledge satisfy beats before play begins. So no beat read widens, and whether any read should is a separate decision.
- **Merges during play** (P1 forbids them) and **repairs to existing worlds** (Kabe's, gate g82aabc).

## Checks

1. A fixture with a first-seen fragment folded into the protagonist: the arc row reads back as the authored id, and the seal passes. Negative control: without `representative=`, the seal raises `ProtagonistSplitError`.
2. A fixture with an open `frame_owner` proposal on the protagonist: it is confirmed with the protagonist as survivor, and the build is viable.
3. A frame-evidence pair (`knows:a` holds `a · sibling_of · b`): it is rejected, not confirmed. Then step 3 stops the build if it touches a load-bearing id.
4. Two load-bearing ids proposed together: they are not merged, and the build stops.
5. A cast-collision pair (`voss`/`voss_2`): `distinct_from` is written, there is no proposal after reconcile, and the build doesn't stop.
6. A build-only rerun of the eval/14 seed, twice. Record viable or stopped, and every confirm, reject and stop with its pair.
7. The full suite is green.
