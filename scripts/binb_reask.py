"""Experiment 1 — Bin-B Re-ask (timeless→timed re-extraction).

Context: the engine's fidelity_audit reports `unstamped_timed` rows —
sidecar-classified STATE/EVENT facts whose valid_from is None (extraction
marked them timeless when they are actually time-anchored).

PB's open question: can the HOST recover stamps by re-asking the model, or
do the rows resist (which would justify an extractor-contract change,
INGESTION-FIDELITY-V2)?

Measurement only — does NOT write back to the world.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patternbuffer import World
from patternbuffer.testing import StubModel

from construct.game import _chunk_chapters
from construct.provider import CodexProvider, complete_sync

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WORLD_NAME = "emberroad2"
WORLD_ID = f"w:{WORLD_NAME}"
WORLD_PATH = Path("worlds") / f"{WORLD_NAME}.world"
PROSE_PATH = Path("generated") / "emberroad.md"
BATCH_SIZE = 10

# Schema for per-row stamp verdicts.
# NOTE: force_strict_object_schema makes ALL properties required and runs strip_nulls
# on the response, so nullable fields that return null get stripped and then fail the
# required check. Workaround: keep chunk as an optional integer (absent = null/unset)
# and use the absence as the null signal — the model omits it for timeless/unplaceable.
REASK_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "attribute": {"type": "string"},
                    "assertion_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["stamp", "timeless", "unplaceable"]},
                    "chunk": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                # chunk is intentionally NOT in required so strip_nulls + force_strict can
                # handle it gracefully: the model omits chunk for timeless/unplaceable rows.
                "required": ["entity", "attribute", "assertion_id", "verdict", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _build_prompt(chunks: list[str], batch: list[dict]) -> str:
    """Build the re-ask prompt for a batch of unstamped rows."""
    chunk_summary = "\n".join(
        f"  Chunk {i + 1}: {c[:200].strip()!r}{'...' if len(c) > 200 else ''}"
        for i, c in enumerate(chunks)
    )
    rows_text = "\n".join(
        f"  {i + 1}. entity={r['entity']!r}, attribute={r['attribute']!r}, assertion_id={r['assertion_id']!r}"
        for i, r in enumerate(batch)
    )
    return (
        "You are a text-archaeology assistant for an interactive-fiction engine.\n\n"
        "A fiction was extracted into a world-state store. The extraction classified "
        "these facts as STATE or EVENT (time-indexed properties), but did NOT assign "
        "a chapter-chunk timestamp. Your task: for each fact below, decide whether "
        "it FIRST BECOMES TRUE at a specific point in the story, or whether it is a "
        "STANDING property with no onset in the text.\n\n"
        "THE STORY is divided into chunks (in story order):\n"
        f"{chunk_summary}\n\n"
        "FACTS TO EVALUATE (extracted from this story):\n"
        f"{rows_text}\n\n"
        "For each fact, output:\n"
        "  - verdict: 'stamp' if it first becomes true at a specific chunk; "
        "'timeless' if it is a standing property that holds across the whole story "
        "with no datable onset; 'unplaceable' if you cannot determine which chunk.\n"
        "  - chunk: the 1-based chunk index where it first becomes true (for 'stamp'), "
        "or null for 'timeless'/'unplaceable'.\n"
        "  - reason: a SHORT (1-sentence) explanation.\n\n"
        "IMPORTANT: Answer honestly. Do not force a stamp if the property is truly "
        "standing (e.g. a character's name, permanent physical description, "
        "their occupation throughout the story). Only stamp facts that have a "
        "clear narrative onset — a change, an event, a first mention in a "
        "specific chapter."
    )


def _find_matching_chunks(entity_local: str, attribute: str, chunks: list[str]) -> list[int]:
    """Find 1-based chunk indices whose text mentions the entity local name."""
    name_part = entity_local.split(":")[-1].replace("_", " ").lower()
    matched = []
    for i, chunk in enumerate(chunks):
        if name_part in chunk.lower():
            matched.append(i + 1)
    return matched


def main() -> None:
    logs = Path("logs")
    logs.mkdir(exist_ok=True)
    ts = os.environ.get("BINB_TS", "manual")
    report_path = logs / "binb-reask-results.md"

    # -----------------------------------------------------------------------
    # Step 1: open world, collect unstamped rows
    # -----------------------------------------------------------------------
    print(f"Opening {WORLD_PATH} ...")
    w = World(
        WORLD_PATH,
        world_id=WORLD_ID,
        model=StubModel(fallback=lambda p, s: {"items": []}),
    )
    fa = w.porcelain.fidelity_audit()
    unstamped_rows: list[dict] = fa["unstamped_timed"]
    w.close()

    total_unstamped = len(unstamped_rows)
    print(f"Unstamped rows found: {total_unstamped}")

    # -----------------------------------------------------------------------
    # Step 2: chunk the source prose
    # -----------------------------------------------------------------------
    if not PROSE_PATH.exists():
        print(f"ERROR: prose file not found at {PROSE_PATH}")
        sys.exit(1)
    prose = PROSE_PATH.read_text(encoding="utf-8")
    chunks = _chunk_chapters(prose)
    n_chunks = len(chunks)
    print(f"Source prose split into {n_chunks} chunks (by _chunk_chapters).")

    # For each row: find which chunks mention its entity local name
    chunk_map: dict[str, list[int]] = {}  # assertion_id → matching chunk indices
    unmatched_ids: list[str] = []
    for row in unstamped_rows:
        matched = _find_matching_chunks(row["entity"], row["attribute"], chunks)
        chunk_map[row["assertion_id"]] = matched
        if not matched:
            unmatched_ids.append(row["assertion_id"])

    print(f"Rows with no chunk text match: {len(unmatched_ids)}")

    # -----------------------------------------------------------------------
    # Step 3: re-ask with the REAL CodexProvider in batches
    # -----------------------------------------------------------------------
    provider = CodexProvider()
    all_results: list[dict] = []

    batches = [
        unstamped_rows[i : i + BATCH_SIZE]
        for i in range(0, len(unstamped_rows), BATCH_SIZE)
    ]
    print(f"Sending {len(batches)} batches of up to {BATCH_SIZE} rows ...")

    for batch_idx, batch in enumerate(batches):
        prompt = _build_prompt(chunks, batch)
        print(f"  Batch {batch_idx + 1}/{len(batches)}: {len(batch)} rows ...")
        try:
            result = complete_sync(provider, prompt, REASK_SCHEMA, tier="cheap",
                                   task="bnb")
            items = result.get("items") or []
            # Align by index (model may return fewer items if it skipped some)
            for i, item in enumerate(items):
                if i < len(batch):
                    item["assertion_id"] = batch[i]["assertion_id"]
                    item["entity"] = batch[i]["entity"]
                    item["attribute"] = batch[i]["attribute"]
            # Fill in any missing items as unplaceable
            for i in range(len(items), len(batch)):
                items.append({
                    "entity": batch[i]["entity"],
                    "attribute": batch[i]["attribute"],
                    "assertion_id": batch[i]["assertion_id"],
                    "verdict": "unplaceable",
                    "chunk": None,
                    "reason": "model did not return a result for this row",
                })
            all_results.extend(items)
        except Exception as exc:
            print(f"  Batch {batch_idx + 1} FAILED: {exc}")
            for row in batch:
                all_results.append({
                    "entity": row["entity"],
                    "attribute": row["attribute"],
                    "assertion_id": row["assertion_id"],
                    "verdict": "unplaceable",
                    "chunk": None,
                    "reason": f"provider error: {exc}",
                })

    # -----------------------------------------------------------------------
    # Step 4: tally and write report
    # -----------------------------------------------------------------------
    restamped = [r for r in all_results if r.get("verdict") == "stamp"]
    upheld_timeless = [r for r in all_results if r.get("verdict") == "timeless"]
    unplaceable = [r for r in all_results if r.get("verdict") == "unplaceable"]

    tally = {
        "total_unstamped": total_unstamped,
        "restamped": len(restamped),
        "upheld_timeless": len(upheld_timeless),
        "unplaceable": len(unplaceable),
        "unmatched_to_chunk": len(unmatched_ids),
        "n_chunks": n_chunks,
    }

    print("\n=== BIN-B RE-ASK TALLY ===")
    for k, v in tally.items():
        print(f"  {k}: {v}")

    # Write report
    lines: list[str] = []
    lines.append("# Bin-B Re-ask Results — Emberroad2")
    lines.append("")
    lines.append(f"World: `{WORLD_NAME}` | Source prose: `{PROSE_PATH}` | Chunks: {n_chunks}")
    lines.append("")
    lines.append("## Tally")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total unstamped_timed rows | {tally['total_unstamped']} |")
    lines.append(f"| Re-stamped (model assigned chunk) | {tally['restamped']} |")
    lines.append(f"| Upheld timeless (standing property) | {tally['upheld_timeless']} |")
    lines.append(f"| Unplaceable (model could not decide) | {tally['unplaceable']} |")
    lines.append(f"| Unmatched to any chunk (no text hit) | {tally['unmatched_to_chunk']} |")
    lines.append("")
    lines.append("## Per-Row Results")
    lines.append("")
    lines.append("| entity | attribute | assertion_id | verdict | chunk | reason |")
    lines.append("|--------|-----------|-------------|---------|-------|--------|")
    for r in all_results:
        ent = r.get("entity", "")
        attr = r.get("attribute", "")
        aid = r.get("assertion_id", "")
        v = r.get("verdict", "")
        chunk = r.get("chunk", "")
        reason = (r.get("reason") or "").replace("|", "\\|")
        lines.append(f"| {ent} | {attr} | {aid} | {v} | {chunk} | {reason} |")

    lines.append("")
    lines.append("## Unmatched Row IDs (no chunk text hit)")
    lines.append("")
    for aid in unmatched_ids:
        lines.append(f"- {aid}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written to: {report_path}")

    # Also print the 5 most interesting resistant rows (upheld-timeless + unplaceable)
    resistant = upheld_timeless + unplaceable
    if resistant:
        print("\n=== 5 MOST INTERESTING RESISTANT ROWS ===")
        # Prioritize: rows that look clearly time-anchored from their names
        # (location/occupation changes, scar activation, etc.) but were upheld timeless
        interesting = sorted(resistant, key=lambda r: (
            0 if r.get("verdict") == "timeless" and r.get("attribute") in (
                "in", "occupation", "scar_on_left_palm", "can_hunt", "can_ride_well",
                "has_been_farther_east_than", "role", "build",
            ) else 1,
            r.get("entity", ""),
        ))[:5]
        for r in interesting:
            print(f"  entity={r.get('entity')} attr={r.get('attribute')} "
                  f"verdict={r.get('verdict')} chunk={r.get('chunk')}")
            print(f"    reason: {r.get('reason')}")

    return report_path


if __name__ == "__main__":
    main()
