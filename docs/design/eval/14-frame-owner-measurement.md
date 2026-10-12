# Frame-owner proposals on fresh builds (R34 measurement, 2026-10-12)

**Why.** Under pattern-buffer's R35 (`IDENTITY-ROOT-CAUSES-V1` §4), the engine no longer merges two ids automatically when either one owns a `knows:` frame. It records a `maybe_same_as` proposal with the code `frame_owner` and waits for the host to confirm. The gate on how Construct should confirm (gc53c58, consult c12f82c) was answered by the monitor on Kabe's behalf (note n126701): measure first. Then P1 (never confirm during play) and P2 (confirm none, and stop the build when an open proposal or same-name group touches the hero or a required-clue holder). P3 (a judged confirm of those pairs) ships with pattern-buffer's R36.

**How.** Two build-only runs of the R20 Ironhold seed (`scripts/displaced_ch2_probe.py`'s `SEED`, the same `win_direction`), with no play. They used pattern-buffer frozen at `a92de08` (R35 included), on Codex. A wrapper recorded:
- every proposal Construct's stage-2 triage (`_adjudicate_residue`) received;
- the load-bearing ids and the live same-name groups at the vouch slot (`_fidelity_vouched_pairs`);
- every proposal still open in the finished world.

The script and raw JSON are on the scratch disk (`frame-owner-measure*`).

## Results

| | Build 1 | Build 2 |
|---|---|---|
| Frame-owner proposals at stage 2 | 0 | 3: `tomas`/`tomas_vale`, `jory`/`jory_pike`, `elias_rook`/`rook` |
| Vouched merges into a load-bearing id | `elias` ← `elias_venn`, `brigg` ← `ansel_brigg` | `berrick` ← `cad_berrick`, `chaplain` ← `rook` |
| Frame-owner proposals open in the finished world | none (build stopped) | 3, **all touching a load-bearing id**: `tomas`/`tomas_vale` (`tomas_vale` is the protagonist), `jory`/`jory_pike`, `elias_rook`/`chaplain` |
| Outcome | **not viable**: protagonist split at seal | viable, with an **unmerged twin of the hero** |

## What it shows

1. **Frame owners do arrive at stage 2.** The extractor gives some characters `knows:` rows from telling scenes, so their name variants become frame-owner proposals before any frame seeding. The vouch allowlist folds only `alias_not_specific` pairs, so it never touches a `frame_owner` pair, and they stay open. That leaves the hero's twin: run 6's `tomas_reed_cell` (eval/12), and here `tomas` beside the protagonist `tomas_vale`.
2. **The protagonist split has a second, Construct-side cause.** In build 1 the vouch merged `elias_venn` into the protagonist `elias`. Pattern-buffer elects a closure's representative as its **first-seen** member (`IdentityRegistry.resolve`), and that was `elias_venn`. The committed arc row then reads back `person:elias_venn`, while the beats watch `knows:person:elias`. Under P1, frames don't follow merges, so the hero's knowledge would land in a frame no beat reads. The seal (`ProtagonistSplitError`) stopped the build, as designed. This is the runs 2, 4 and 5 split. The host cannot choose the representative today, so pattern-buffer was asked for a host merge or confirm that names it (mail m0243e8).
3. **P2 alone would stop both builds.** Build 1 already stops on the split. Build 2 would stop on its open `tomas`/`tomas_vale` proposal. So P2 ships together with P3, which confirms the right load-bearing pairs, keeps the survivor as the literal id the beats watch, and rejects pairs whose own frames name each other as different people. P2 then stops only the builds P3 cannot settle. P3 needs the representative choice from pattern-buffer.
4. **P1 is already true.** No play path calls `merge` or `confirm`: the only merges are at build (`construct/game.py`). It needs a test that keeps it that way, not new behaviour.

Two builds is a small sample, so these are findings, not rates.
