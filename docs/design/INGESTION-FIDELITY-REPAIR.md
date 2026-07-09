# Ingestion-Fidelity Repair — the build-seal coreference loop (spec)

**Status:** SPEC, for Cx review then build. Task #56. Extends the #108 build-seal
identity cleanup into a complete, measured fidelity-repair pass.

## Problem (measured, live-verified)

Ingested worlds fragment a single character/object across multiple entity ids
(coreference miss) or collide a character with a place of the same name (a
homonym the extractor typed as both). This degrades **live fiction**, verified
in the overnight critic campaign (2026-07-09): in emberroad the player followed
"Lysa" (split `person:lysa`/`person:lysa_fen`) and "Harth"
(`person:harth`/`place:harth`), and the accompanying cast *flickered in and out
of presence* — the companion/presence system couldn't resolve which id was
present. Object permanence held at the substrate (the player's lantern was still
held), but the render couldn't read a 3-way-split lantern. **Substrate correct;
render degraded by fragmentation.**

Baseline metric (PB's `fidelity_audit().summary.name_collisions`, severity-
joined host-side): emberroad **8 live** coreference groups. bodycase
(hand-crafted) **0** — a clean world is achievable. The break-causer is
coreference + person↔place typing-slips of **actively-interacted** entities
(the live eval, not the raw count — bin-B unstamped rows did not break fiction
in 72 clean turns; see PB letters 100–110).

## The fix: a tiered host loop over PB's SHIPPED tools (no engine work owed)

PB confirmed (letters 106/110) the entire fix is host-side over shipped surface,
routed off `fidelity_audit()`'s per-group `kinds[]` (index-aligned with
`entities[]`) and per-pair `status`. The tiered gate, safest-first:

1. **`adjudicate_deferred()` — the auto-safe subset.** Merges only
   anchor-subsumed pairs (`tovin` ⊆ `tovin beck`); its **durable-contradiction
   veto** declines role/standing contradictions (the "retrieval-lead vs
   apprentice" #107 guard, by construction) and never crosses
   `distinct_from`/containment. Homonym-false-merge-safe. *(Already in #108.)*
2. **`reject()` for cross-kind homonyms.** A collision group with
   `len(set(kinds)) > 1` (person↔place, e.g. `person:harth`/`place:harth`) is
   **two genuinely-distinct entities sharing a name**, not a fragment.
   `reject(a, b)` writes `distinct_from` → drops the pair from the live count
   (status → `hard_blocked`) AND hands `refer()` the kind+scene signal to
   disambiguate at render (the person when addressed, the place when travelled
   to — the presence-flicker fix). Cannot wrongly-merge anything. *(NEW.)*
3. **`retype(absorb=)` for typing slips.** The engine verifies the slip
   signature and vetoes a non-slip (`vetoed_not_a_slip`). *(Already in #108.)*
4. **Vouched `merge()` for arc-load-bearing residue.** The same-name **same-kind**
   true splits `adjudicate_deferred` declined for homonym-safety
   (`alias_not_specific`) — `person:lysa`/`person:lysa_fen`,
   `person:mara`/`person:mara_thist`. The host merges these ONLY when the group
   touches the **arc protagonist or a required-cast id** (the host can vouch:
   the story authored one such character). `guarded_merge` still enforces
   `distinct_from`/containment absolutely, so a vouched merge can never cross a
   step-2 `reject()`. *(NEW.)*

## Ordering (the subtlety — the reason this is a two-part pass)

`reconcile()` runs at **Stage 2**, BEFORE arc authoring (Stage 4). Steps 1–3 are
**arc-independent** (anchor subsumption, homonyms, slips) and stay at Stage 2
(extending the #108 block; add step 2).

Step 4 (vouched merge) NEEDS the arc protagonist + required cast, authored at
Stage 4. So it runs as a **second pass after Stage 4, before the seal** — and
it merges the OTHER fragments **INTO** the arc-canonical id, **never away from
it**. This is the hard invariant: the arc's `protagonist`/cast rows and the
literal beat-gate `knows:<id>` frames must keep naming the same id, so we only
ever collapse `person:mara` → `person:mara_venn` (fragment into canonical),
never the reverse. (The #107 seal-lint already asserts protagonist coherence
after this — a residual divergence is caught + receipted.)

## Severity join (host-only, arc-aware)

For step 4's "does this group touch a load-bearing id?" the host joins each
`fidelity_audit()` group's `entities[]` against the arc protagonist ∪ required
cast. `kinds[]` (PB's additive) makes the person↔place weighting namespace-lie-
proof. The engine stays arc-blind (the membrane); severity is host truth.

## Fail-open + idempotence

The whole pass is wrapped fail-open (a repair failure never sinks a build — an
unrepaired world still plays, just with the known fragmentation). All four ops
are idempotent (re-running finds nothing new). Emits per-stage receipts
(`fidelity_repair` counts) for the turn trace / audit.

## Measurement + success criteria

- **Count:** re-run `fidelity_audit()` after the pass. emberroad throwaway
  prototype: **8 → 1** (reject ×6 homonym pairs, vouched-merge ×11 true splits,
  1 residual). Success = a real emberroad REBUILD drops from 8 toward ~1.
- **Fiction (the real proof):** re-play emberroad post-integration; the Lysa/
  Harth presence flicker resolves (the critic-campaign repro no longer fires).
- **No regression:** the full suite stays green; bodycase (0) stays 0; the
  live player worlds' protagonists stay coherent (seal-lint clean).
- **The 1 residual** is the only bin-B/V2 candidate — reported to PB, not fixed
  speculatively.

## Cx 480 amendments (folded — required for GREEN)

Cx spec review (letter 480, YELLOW→amendments) caught four safety holes; all
folded:

1. **`guarded_merge()` does NOT veto durable-contradictions** — only containment
   / `distinct_from` (porcelain.py:531, identity.py:578). `adjudicate_deferred`
   only *skips* a durable-contradiction pair into residue; a later host
   `merge()` would override it. So step 4 must **host-side exclude** pairs whose
   audit/residue reason is `durable_contradiction` OR `relating_edge` (read the
   structured reason surface); guarded_merge only backstops
   `distinct_from`/containment.
2. **Reject after retype, not before.** Typing-slips are cross-kind too; a
   `reject()` on a slip writes `distinct_from` and then `retype(absorb=)` vetoes
   on it. Order: `adjudicate_deferred` → **`retype(absorb=)` (slips)** →
   **`reject()` (remaining cross-kind homonyms — exclude any pair still returned
   by `typing_conflicts()` / with per-pair status `typing_slip`)**.
3. **Vouched merge fires only when EXACTLY ONE id in the group is load-bearing.**
   A group with two load-bearing ids (protagonist + a required-cast member, or
   two cast members, same name) has no unique canonical to fold into → leave as
   residue + log. Required-cast ids are `_req` (game.py:801); the accepted cast
   nodes are retained (game.py:827).
4. **Preserve the literal arc/cast ids; do not assume PB canonical election
   follows merge direction.** `merge(a,b)` appends `a same_as b`; closure is
   undirected; `resolve()` elects first-seen in log order — so `merge(fragment,
   arc_id)` does NOT guarantee `resolve(arc_id)==arc_id`. Keep `arc.protagonist`,
   required-cast ids, beat/pillar frames, and meta pointed at the retained
   (load-bearing) id; merge only non-load-bearing fragments. **Seal-lint
   interaction:** because the vouched merge may make PB elect a fragment as the
   canonical representative, the #107 seal-lint must compare protagonist
   coherence by **identity (resolve both sides), not literal string** — else a
   correct merge triggers a false `protagonist_split`. (Amend
   `_protagonist_coherence` to resolve, or compare via the registry.)

**Insertion point (Cx Q1 ruling).** Steps 1–3 stay at Stage 2 (pre-arc,
extending the #108 block; add the reject step). Step 4 (vouched merge) runs
AFTER successful cast authoring and BEFORE the `arc_to_items(arc)+index_items`
write (game.py:866) — so the plot rows are written with the already-merged
canonical id. It MUST NOT run after `cast_seed_plan()` / `cast_location_plan()`
(Stage 5), which emit literal `knows:<node_id>` frames + staging rows a later
merge would strand.

**Vouched-merge receipt discipline (Cx Q2).** Treat only `merged` /
`noop_already_merged` as success; a `vetoed` result leaves the group unresolved
and logs fail-open. Candidate allowlist: same folded kind + per-pair reason in
`{alias_not_specific}` by default (add reasons only with tests). Never merge
`typing_slip`, `kind_conflict`, `durable_contradiction`, `relating_edge`,
`containment`, `hard_blocked`.

## Test bar
- A world with `person:X`/`place:X` → after the pass they carry `distinct_from`
  and drop from `name_collisions`; `refer("X")` resolves person-vs-place by scene.
- A protagonist split `person:p`/`person:p_full` where `p_full` is the arc
  protagonist → merged into `p_full`; the arc's beat gates still name `p_full`;
  seal-lint clean.
- A same-name pair with a durable role contradiction → NOT merged (veto holds).
- A background same-name split touching NO load-bearing id → left as a proposal
  (not force-merged; homonym caution) unless anchor-subsumption already took it.
- Fail-open: a raised repair op logs + the build completes.
