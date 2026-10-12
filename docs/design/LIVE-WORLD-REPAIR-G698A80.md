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
**Corrected the same night:** the first repair split the protagonist from an NPC who is, by the text, the protagonist, and it left the protagonist with no location. See "Correction to the first repair" below. The file was restored and repaired again.

- **Wrong merge.** Before: four ids (the protagonist, a second id for the protagonist, and two ids of one NPC) were one entity, joined through two speaker-relative phrases. After the first repair: three groups held apart (the second id; the NPC's two ids, a right merge, kept; the protagonist alone, with no location row of their own).
- **Holds row stored backwards.** Before: `person held_by obj`. After: `obj held_by person`.
- **Junk alias.** Retracted one row: the protagonist's description as an alias on the NPC.
- 2108 rows before, 2116 after the first repair; see the correction for the final count.

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

## Follow-up: the leftovers, gate g82aabc (2026-10-12, later the same night)

**Authority.** Gate g82aabc, answered by the monitor on Kabe's behalf (note n05f168), with the same method as g698a80:
- a fresh backup first (the earlier one predates the repair);
- verify every change on copies under the pinned engine, and apply only with no bot running;
- a before/after report.

The rules per item:
- (1) and (3): retract.
- (2) and (4): check the book text first. Fix only where the text clearly shows it; leave and report the rest.
- (5): pin the engine.

**Method.**
- **Backup:** all 16 live files, the thedeep preset and its play copies, and the player registry, with checksums verified.
- **Verification:** each change was verified on a fresh copy with the same checks as above. Two checks were added:
  - the protagonist must still have a location;
  - a merge the merge pass makes on an untouched copy too is not counted against the repair.
- **Apply:** the live file was written only after that, and its new rows matched the verified copy row for row. No bot was running, and no process had the files open.

### Correction to the first repair: world B

The first repair split the four ids into three groups, following pattern-buffer's rule that a speaker-relative anchor ("my X", "his X") is no evidence. The book text says more:
- **The NPC is the protagonist.** The text names the protagonist by that role, and the people around them use the same phrase for them.
- **Only one link was wrong.** The other speaker's phrase meant a different, dead character, so that one merge was a real mistake.

After the first repair, the protagonist had **no location at all**. That would have broken the opening for the next player. Nobody had played it in between: its one player wiped their saves before starting.

The file was restored from the pre-repair backup (checksum equal to the original) and repaired again:
- only the one wrong link is retracted;
- the protagonist's ids and the other character's ids are held apart.

Now:
- the protagonist is one person with a location;
- the other character is at their own place;
- the backwards holds row and the junk alias are fixed as before;
- the text-valued holds row below is retracted.

A lesson for the identity work (`IDENTITY-CONFIRM.md`): the rule "a possessive is no evidence" is right for an automatic merge, and wrong as a repair rule when the text resolves who is meant.

### The five items

1. **Text-valued holds rows: retracted** in worlds B and D (world D's critic play was otherwise untouched, and no merge pass was run on it).
2. **The two father merges, checked against the text.**
   - World B: **right, kept.** The text names the father outright.
   - World C: **wrong, split** in all four files. Two different men say "my father" about two different fathers. The `same_as` row is retracted and the pair held apart.
3. **Leftover fusion aliases: retracted.** Each value was checked against whose alias it is in canon.
   - **World C** (all four files): 50 rows in the five knowledge frames: the other women's names, kinship phrases that are another person's in canon, and the fusion sentence. The person's own name stays.
   - **World A:** 18 rows in the knowledge frames: the protagonist fragment's own lines and the merge sentence. In canon, two wrong-entity aliases (each real owner keeps its own). The NPC's own aliases stay.
   - The fusion sentence's **canon** rows came from extraction, not the fusion. They are left as text; since R35 they carry no weight as identity evidence.
4. **thedeep** (the preset and its four play copies).
   - **'san pedro': retracted.** The text says Keiko "had grown up repairing tuna boats in San Pedro"; it's a place, not her name.
   - **`chen = elias_chen`: confirmed**, once pattern-buffer shipped IDENTITY-REPRESENTATIVE-V1 (`f275e40`; the engine pin moved to it after the full suite passed). It ran as `confirm(chen, elias_chen, representative=chen)` in all five thedeep files. Every receipt is `merged`, with `canonical_id` = `person:chen`, the id the arc's beats name. A follow-up merge pass on each copy kept the pair together, and Chen is at `place:persephone_lock`. Under P1, the two `knows:` frames stay separate, and nothing reads across them.
5. **Engine pinned** at pattern-buffer `c44ad49`, which the full suite passed on (1557 passed, 1 skipped).
   - The commit is in `engine.pin`. `scripts/pin_engine.sh` installs that exact commit into `.venv`, replacing the editable link to pattern-buffer's working tree, and the installed copy was checked byte-identical to it.
   - To bump: run the suite against the new commit, change the one line in `engine.pin` (commit it with the result), and run the script.
   - First bump: to `f275e40` (IDENTITY-REPRESENTATIVE-V1), after the full suite passed on it (commit `b87038e`).
   - Second bump: to `0eb4e3f` (CLOSURE-READ-V1, FACTS-BOOKKEEPING-V1, VIEW-EXPORT-V1), commit `2ea7713`.
   - pattern-buffer rebuilt its unpushed history before its 2026-10-12 push, so its ids in this report and in other docs from before that date are the old ones. Its `docs/COMMIT-ID-MAP-2026-10-12.md` maps each to the new id. The pin was then moved from `0eb4e3f` to `5a9e826`, the same commit under its new id (`src/` byte-identical).

Row counts (old log kept as an exact prefix in every file):

| World | Rows before → after |
|---|---|
| World A | 1904 → 1924 |
| World B | 2108 → 2114 (re-repaired from the original) |
| World C (4 files) | +52 each |
| World D, critic play | 2214 → 2215 |
| thedeep (5 files) | +1 each |
