# Live-world repair, gate g698a80 (2026-10-12)

**Authority.** Kabe's gate g698a80 (2026-10-09) asked to repair the live Telegram worlds. The default stood until the monitor approved it on his behalf (note ne409d4, 2026-10-12), on four terms:
1. back up each file first;
2. re-run each recipe on a fresh copy under the engine the live service actually runs, then reconcile, with 0 re-merges and no change beyond the intended rows;
3. apply between turns, never mid-turn, and leave run 6 alone;
4. report before and after for each world.

This is that report. The live worlds are players' own stories, so this public report calls them worlds A to D and names no title, character or line of their text. The full report, with titles, entity ids and the text evidence, is kept off the repo in the scratch work folder, with the file-level detail (file names carry player ids).

## How it was done

- **Backups.** All 16 live world files and the player registry were copied, and the checksums verified, before anything was opened.
- **Engine.** A live bot loaded pattern-buffer from its working tree on `main`, so the engine was whatever `main` was when the bot started. The repair ran on a frozen copy of `main` as it was at apply time, `00949bf`, which includes R35 (identity root causes) and R36 (frame continuity). pattern-buffer generated the manifests on `a92de08`. R36 changes provenance labels only, and the results below confirm it changed nothing in the repair.
- **No turn in flight.** No bot was running, and no process had the files open.
- **The manifests.** pattern-buffer produced one manifest per file (rows to retract, pairs to reject) with its own dry runs. Construct used them as data and applied a narrower scope, set out below.
- **Two copies, then the live file.** For each file the repair first ran on a fresh copy taken with SQLite's backup API, and these were checked:
  - the old log is an exact prefix of the new one (no existing row changed or removed);
  - new rows are only retractions, keep-apart rows (`distinct_from`) and corrected holds rows;
  - every retraction wrote, every reject came back `rejected` or `noop_already_distinct`, and every holds repair committed with no skip;
  - `identity_conflicts()` is empty;
  - each repaired group's closure is exactly the target.

  A second copy of the repaired file then ran `reconcile()`. It made **0 merges** and re-merged none of the repaired pairs. The live file got the same operations only after all of this passed, and only if it hadn't changed since the copy. It was then re-checked the same way, and its new rows matched the verified copy row for row.
- **No reconcile on the live files.** Reconcile was part of the check, run on copies only. Running it live would add unrelated merge proposals, which go beyond the intended rows.

## Before and after, per world

### World A (one file: the scenario world; no player has a save of it)
- **Wrong merge.** Before: an NPC and a fragment of the protagonist were one entity, joined on a sentence used as an alias. After: two people, kept apart by a `distinct_from` row, each at their own location.
- **Holds row stored backwards.** Before: a person was stored inside an object (`person held_by obj`). After: `obj held_by person`.
- **Junk aliases.** Retracted 8 rows: two wrong-entity aliases on the NPC, in four characters' knowledge frames.
- 1892 rows before, 1904 after (12 added, none changed).

### World B (one file: the scenario world; its player has not started a save)
- **Wrong merge.** Before: four ids (the protagonist, a second id for the protagonist, and two ids of one NPC) were one entity, joined through two speaker-relative phrases. After: three groups held apart (the second id; the NPC's two ids, a right merge, kept; the protagonist alone, with no location row of their own).
- **Holds row stored backwards.** Before: `person held_by obj`. After: `obj held_by person`.
- **Junk alias.** Retracted one row: the protagonist's description as an alias on the NPC.
- 2108 rows before, 2116 after.

### World C (four files: the scenario world, the player's save, its checkpoint, and a critic play)
- **Wrong merge.** Before: six different people were one entity, on a single shared sentence. One of them read the clues of two others. After: six separate people, with all 15 pairs held apart. Their locations are unchanged (each reads their own rows).
- **Holds rows stored backwards (5).** One `person held_by doc` row and four `place held_by obj` rows, each now the other way round.
- **Junk alias.** Retracted one person's name stored as an alias on another, in five knowledge frames.
- 35 rows added per file, none changed. The player's save and its checkpoint got identical repairs.

### World D (two files)
Untouched. None of the three groups is present, and its only flagged holds row is text-valued (see below). pattern-buffer warns that a reconcile there would make two unrelated merges; none was run.

## Left alone (outside the approved scope; for Kabe)

1. **Two text-valued holds rows** (worlds B and D), which a swap cannot fix and which may be nonsense either way.
2. **Two speaker-relative merges** pattern-buffer found outside the named groups (worlds B and C), each joining two people on "her father" or "my father". They may be right.
3. **Leftover aliases from the fusions** in worlds A and C: the other people's names, kinship phrases and the sentence that caused the fusion, left on the person the fusion folded them into, plus two wrong-entity aliases in world A's canon.
4. **'san pedro'** is only in the thedeep preset (tracked in this repo), not in any live world. The thedeep `chen`/`elias_chen` confirm from the earlier list is also still open.
5. **The engine version a live bot loads isn't fixed.** It's whatever pattern-buffer's `main` is at the moment the bot starts.
