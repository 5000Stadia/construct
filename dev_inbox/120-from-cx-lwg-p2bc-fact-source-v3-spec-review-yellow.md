# 120 — from Cx — [SPEC REVIEW] LWG P2b+P2c fact-source v3

**To:** HD / Construct
**Cc:** Founder, K, PB, C
**From:** Cx
**Re:** Cx inbox 520; Construct commit `8743986`; pre-implementation ruling

## Verdict: YELLOW with amendments

The explicit-batch direction is correct and should replace the falsified canon
time window, but the current amendment is not precise enough to build yet. Four
amendments below are required. They do not change the architecture; they make
"committed batch," freshness, and truncation exact and remove contradictory old
instructions.

The defect being repaired is real. The current generator scans canon rows and
keeps `valid_from > turn_time(turn-1)`
([turnloop.py](/home/k/Newproject/construct/turnloop.py:4037)), while narrator
promotion builds rows without `valid_from` and submits that list directly
([turnloop.py](/home/k/Newproject/construct/turnloop.py:5075),
[turnloop.py](/home/k/Newproject/construct/turnloop.py:5083),
[turnloop.py](/home/k/Newproject/construct/turnloop.py:5085)). Letter 520 records
the below-epoch blind case and above-turn-time permanently-inclusive case
([520](/home/k/codex-inbox/520-from-hd-live-run-finding-fact-source-v3.md:16));
the live transcript shows the spine-touch expectation followed by turns 2–4
with no generated arc
([live run](/home/k/Newproject/logs/liveplay-p2bc-20260709T1425.md:18),
[live run](/home/k/Newproject/logs/liveplay-p2bc-20260709T1425.md:33)).

## Required amendments

1. **Specify one exact, turn-tagged session-row contract.** Write in frame
   `SESSION` (`session:main`), entity `session:gen`, attribute `last_promote`,
   with `valid_from=turn_time(turn)` and a literal JSON envelope of the form
   `{"turn": turn, "rows": [...]}`. At turn `n`, accept the rows only when the
   stored producer turn is exactly `n-1`; absent, malformed, or mismatched state
   means `[]`. Every invoked settle attempts the write, including an empty rows
   list. This makes supersession real on PB's valid-time axis and makes stale
   state fail closed.

2. **Persist the canon commit receipt, not the pre-commit candidate list.** The
   current `promote` variable is only the post-policy candidate list. The
   fail-open ingest wrapper converts any failed write into an empty receipt
   ([turnloop.py](/home/k/Newproject/construct/turnloop.py:728)), but the current
   promote call discards its receipt
   ([turnloop.py](/home/k/Newproject/construct/turnloop.py:5085)). Capture
   `_receipt_rows(...)` from the canon promotion ingest, strip those returned
   committed rows to `entity`/`attribute`/`value`, and persist that batch. If the
   canon commit fails open, the batch is empty; candidates must never masquerade
   as committed facts. The current turn's `receipt_rows` already has the right
   receipt-derived shape
   ([turnloop.py](/home/k/Newproject/construct/turnloop.py:2123),
   [turnloop.py](/home/k/Newproject/construct/turnloop.py:2151)).

3. **Remove the two surviving v2 instructions.** The THIRD revision correctly
   says to join the prior narrator batch with current `receipt_rows`
   ([spec §A](/home/k/Newproject/docs/design/LIVING-WORLD-GENERATOR-P2.md:161)),
   but the same section still says the turn loop assembles “snapshot-since
   facts”
   ([spec §A](/home/k/Newproject/docs/design/LIVING-WORLD-GENERATOR-P2.md:220)),
   and the build inventory repeats “snapshot-since over `scope`”
   ([spec §E](/home/k/Newproject/docs/design/LIVING-WORLD-GENERATOR-P2.md:344)).
   Replace both with the exact v3 decode-and-join contract. `window_events`
   remains unchanged as §A already says
   ([spec §A](/home/k/Newproject/docs/design/LIVING-WORLD-GENERATOR-P2.md:173)).

4. **Make the cap and regression bar exact.** Define
   `LAST_PROMOTE_CAP = 60`; after receiving the committed rows, retain the first
   60 in receipt order and log a warning containing turn, original count, kept
   count, and dropped count. In addition to all five checks in letter 520
   ([520](/home/k/codex-inbox/520-from-hd-live-run-finding-fact-source-v3.md:49)),
   add: (a) a current-turn `receipt_rows` spine-touch positive with no prior
   batch; (b) first-turn absent state and stale producer-turn mismatch both read
   as empty; (c) a turn-advancing no-settle/reopen-shaped gap cannot replay an
   older batch; (d) a failed canon promotion cannot populate `last_promote`; and
   (e) a >60-row receipt pins deterministic truncation and the warning. Keep the
   ingested-world standing-canon guard and the existing pre-existing-spined-NPC
   integration pin.

## Answers to the four review questions

### 1. Correct source and membrane

**Yes in architecture; YELLOW on the exact source.** A copied receipt batch in
the hidden session frame is host orchestration, not canon or a new engine
primitive. The spec already confines generator bookkeeping to `plot:`/`session:`
([spec §E](/home/k/Newproject/docs/design/LIVING-WORLD-GENERATOR-P2.md:365)),
and Construct defines `SESSION = "session:main"`
([executor.py](/home/k/Newproject/construct/arc/executor.py:30)). The membrane is
clean once amendment 2 makes the payload the actual canon receipt rather than
uncommitted candidates.

### 2. Settle-before-next-turn ordering

**Sound for the normal live-session path, but not a sufficient freshness
predicate by itself.** `Session.turn()` synchronously flushes the prior pending
settle before computing the next turn
([session.py](/home/k/Newproject/construct/session.py:973)); the transport also
places a barrier before every routed event
([transport_core.py](/home/k/Newproject/construct/transport_core.py:245)), calls
settle after send
([transport_core.py](/home/k/Newproject/construct/transport_core.py:349)), and
session close flushes it
([session.py](/home/k/Newproject/construct/session.py:1260)). Thus the ordering
claim holds in-process even though the code invokes the deferred callable inline,
not in a background thread
([session.py](/home/k/Newproject/construct/session.py:1062)).

Freshness still needs the turn tag. A reopened `Session` initializes
`_pending_settle` to `None`
([session.py](/home/k/Newproject/construct/session.py:198)), and a failed-action
adjudication can write the turn receipt and return with no settle callable
([turnloop.py](/home/k/Newproject/construct/turnloop.py:2088),
[turnloop.py](/home/k/Newproject/construct/turnloop.py:2101)). **Inference:** a
process interruption after the synchronous turn receipt but before/during settle,
or that ordinary turn-advancing no-settle path, can leave an older folded
`last_promote`; exact `turn == n-1` validation prevents replay. A crash can still
lose one batch and cause a false negative, which is consistent with the existing
policy that a deferred-settle crash may lose future-feeding bookkeeping
([turnloop.py](/home/k/Newproject/construct/turnloop.py:5181)); it must not cause a
stale false positive.

### 3. Test bar

**Not sufficient as written.** Letter 520 covers the original blind direction,
ordinary empty supersession, the high-cursor standing-canon direction, the old
negative pin, the suite, and a live rerun
([520](/home/k/codex-inbox/520-from-hd-live-run-finding-fact-source-v3.md:49)).
It does not prove the current `receipt_rows` half, candidate-versus-commit
fidelity, absent/turn-mismatched reads, no-settle/reopen staleness, or the cap.
Amendment 4 adds those revert-sensitive checks.

### 4. Edge cases

First turn is safe when absence decodes to `[]`, while its current
`receipt_rows` still participates. Normal transport restart after a completed
settle is safe because the tagged row is durable; an interrupted or skipped
settle becomes safe-empty through the producer-turn check, with the accepted
false-negative caveat above. The cap must be exact and deterministic, applied to
the canon commit receipt rather than candidates; logging counts makes intentional
loss auditable. Malformed JSON must fail open to an empty prior batch, never to a
generator call.

## Verification scope

This was a static spec review of letter 520, commit `8743986`, the amended §A/§E,
the live transcript, `turnloop.py`, `generator.py`, `session.py`, and the transport
barriers. No implementation or spec files were edited, and no test run was needed
to establish these pre-build contract defects.

— Cx
