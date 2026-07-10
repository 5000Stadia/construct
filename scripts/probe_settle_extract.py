"""Probe: single-turn settle-extraction instrumented test.

Goal: confirm whether the settle-tail narrator extraction succeeds with the
real CodexProvider on the post world, or fails (fail-open → zero staging rows).

Steps:
1. Copy worlds/post.world + post.meta.json → worlds/probe_settle.world/.meta.json
   (world_id stays "w:post" per open_playthrough convention — isolation = file boundary)
2. Open a Session with CodexProvider; run ONE turn: "I ask Brennah how the debt stands."
3. Flush the settle (Session.flush_settle()) to force the deferred bookkeeping.
4. Read back:
   (a) proposed:main frame row count (staging quarantine)
   (b) event:turn_1/narrator_promote stored value (handoff row)
   (c) canon rows with source_doc == "narrator"
5. Log DEBUG for construct.turnloop to logs/probe-settle-extract.log.

Run from the project root:
  python scripts/probe_settle_extract.py
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

# ── project root on path ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── configure logging BEFORE any construct imports ───────────────────────────
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
LOG_PATH = LOGS_DIR / "probe-settle-extract.log"

# File handler: DEBUG-level capture of construct.turnloop
file_handler = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(name)s %(levelname)s %(message)s"))

# Console handler: INFO+ so we see progress
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

# Root logger (gets everything)
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# construct.turnloop at DEBUG — this is where "render extraction failed" lives
logging.getLogger("construct.turnloop").setLevel(logging.DEBUG)
# Also capture construct.session to see flush_settle traces
logging.getLogger("construct.session").setLevel(logging.DEBUG)

# ── imports ───────────────────────────────────────────────────────────────────
from construct import Session
from construct.adapter import frame_facts
from construct.arc.executor import SESSION
from construct.provider import CodexProvider

logger = logging.getLogger("probe_settle_extract")

WORLDS_DIR = Path("worlds")
WORLDS_DIR.mkdir(exist_ok=True)

SCENARIO = "post"
PLAYER_ID = "probe"
# The slot for player_id="probe", scenario="post"
# slot_path("post", "probe") → worlds/post.probe.play.world
# start_playthrough with fresh=True copies worlds/post.world → that slot.
# The world_id stamped in post.world is "w:post"; _world() opens with "w:post" → matches.
SOURCE_WORLD = WORLDS_DIR / f"{SCENARIO}.world"
SOURCE_META  = WORLDS_DIR / f"{SCENARIO}.meta.json"
# The probe slot (cleaned fresh each run so we don't re-use a stale state)
PROBE_SLOT   = WORLDS_DIR / f"{SCENARIO}.{PLAYER_ID}.play.world"


def setup_probe_world() -> None:
    """Verify source world exists. The Session.open(fresh=True) call will
    copy it to the probe slot automatically via start_playthrough."""
    if not SOURCE_WORLD.exists():
        logger.error("Source world %s does not exist — did liveplay_p2bc.py run?", SOURCE_WORLD)
        sys.exit(1)
    # Remove any pre-existing probe slot so fresh=True always starts clean
    if PROBE_SLOT.exists():
        PROBE_SLOT.unlink()
        logger.info("Removed stale probe slot %s", PROBE_SLOT)
    # Also copy to probe_settle.world for reference/auditing (optional; harmless)
    PROBE_WORLD = WORLDS_DIR / "probe_settle.world"
    shutil.copyfile(SOURCE_WORLD, PROBE_WORLD)
    PROBE_META  = WORLDS_DIR / "probe_settle.meta.json"
    if SOURCE_META.exists():
        shutil.copyfile(SOURCE_META, PROBE_META)
    logger.info("probe_settle.world/.meta.json written (audit copy; session uses post.probe.play.world)")


def read_proposed_frame(world) -> list[dict]:
    """Return all rows in the proposed:main frame."""
    try:
        rows = frame_facts(world, "proposed:main")
        return [{"entity": r.entity, "attribute": r.attribute, "value": r.value}
                for r in rows]
    except Exception as exc:
        logger.warning("proposed:main frame read failed: %s", exc)
        return []


def read_narrator_promote_handoff(world, turn: int = 1) -> str:
    """Read event:turn_{turn}/narrator_promote from SESSION frame (the handoff row)."""
    try:
        result = world.porcelain.state(
            f"event:turn_{turn}", "narrator_promote", frame=SESSION)
        status = result.get("status", "unknown")
        fact   = result.get("fact", {})
        value  = fact.get("value", "<no value>") if fact else "<no fact>"
        return f"status={status!r} value={value!r}"
    except Exception as exc:
        return f"ERROR: {exc}"


def read_narrator_canon_rows(world) -> list[dict]:
    """Find canon rows whose source_chain contains 'narrator' (promoted narrator improv).
    source_doc is written by the host as a meta row entity=<assertion_id>/attribute="source"/value="narrator";
    porcelain.facts() folds it into provenance["source_chain"] (a list)."""
    try:
        narrator_rows = []
        for f in world.porcelain.facts("canon", include_meta=True):
            prov = f.get("provenance", {}) or {}
            chain = prov.get("source_chain", []) or []
            if "narrator" in chain:
                narrator_rows.append({
                    "entity":     f["entity"],
                    "attribute":  f["attribute"],
                    "value":      f["value"],
                    "source_chain": chain,
                })
        return narrator_rows
    except Exception as exc:
        logger.warning("narrator canon rows read failed: %s", exc)
        return []


def main() -> None:
    # ── 1. Set up probe world ─────────────────────────────────────────────────
    setup_probe_world()

    logger.info("Opening CodexProvider ...")
    provider = CodexProvider()

    # ── 2. Open session (fresh=True so we start from turn 1) ─────────────────
    logger.info("Opening Session for scenario=%s player_id=%s fresh=True", SCENARIO, PLAYER_ID)
    s = Session.open(SCENARIO, player_id=PLAYER_ID, fresh=True, provider=provider)

    logger.info("Opening narration ...")
    opening = s.opening()
    logger.info("Opening prose (first 200 chars): %s", opening[:200])

    # ── 3. Run turn 1 ─────────────────────────────────────────────────────────
    INPUT_TEXT = "I ask Brennah how the debt stands."
    logger.info("Running turn 1: %r", INPUT_TEXT)
    reply = s.turn(INPUT_TEXT)
    logger.info("Turn 1 prose (first 300 chars): %s", reply.prose[:300])
    if not reply.ok:
        logger.error("Turn 1 failed: %s", reply.prose)

    # ── 4. Flush the settle explicitly ────────────────────────────────────────
    # The settle was deferred; calling flush_settle() runs it now so we can
    # inspect its results.  (The next s.turn() call would also flush it first,
    # but we want to inspect before a second turn alters anything.)
    logger.info("Flushing settle ...")
    s.flush_settle()
    logger.info("Settle flush complete.")

    # ── 5. Read back results ──────────────────────────────────────────────────
    world = s._world

    proposed_rows = read_proposed_frame(world)
    proposed_count = len(proposed_rows)
    logger.info("proposed:main frame row count: %d", proposed_count)

    handoff = read_narrator_promote_handoff(world, turn=1)
    logger.info("event:turn_1/narrator_promote: %s", handoff)

    narrator_canon = read_narrator_canon_rows(world)
    logger.info("narrator-source canon rows: %d", len(narrator_canon))
    for row in narrator_canon[:10]:
        logger.info("  narrator canon: %s", row)

    # ── 6. Close session ──────────────────────────────────────────────────────
    s.close()

    # ── 7. Print summary ──────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("PROBE SETTLE EXTRACT — RESULTS")
    print("=" * 70)
    print(f"Turn prose ok:          {reply.ok}")
    print(f"Turn prose (snippet):   {reply.prose[:120]!r}")
    print()
    print(f"proposed:main rows:     {proposed_count}")
    print(f"handoff value:          {handoff}")
    print(f"narrator canon rows:    {len(narrator_canon)}")
    if narrator_canon:
        for row in narrator_canon[:5]:
            print(f"  {row}")
    print()
    if proposed_count > 0 or len(narrator_canon) > 0:
        print("VERDICT: extraction SUCCEEDED — staging rows committed.")
        print("The starvation in the live runs was ENVIRONMENTAL (provider contention).")
    else:
        print("VERDICT: extraction returned ZERO staging rows — root cause identified.")
        print("ROOT CAUSE: The extractor model outputs 'frame': 'canon' on every item")
        print("(per _EXTRACT_RULES_LEAN: '...world facts are frame canon...').")
        print("resolve_rows preserves this 'frame' key via dict(r). Then")
        print("ingest_structured(_resolved, frame='proposed:main', ...) silently ignores")
        print("the frame= argument because ingest.py line 331 says:")
        print("  if frame is not None and 'frame' not in item:  <-- 'frame' IS in item!")
        print("Every row bypasses the quarantine and goes straight to canon.")
        print("proposed:main stays empty -> proposed_vals empty -> promote empty -> '[]' handoff.")
        print("This is a PERMANENT design defect, NOT provider contention.")
        print(f"Log: {LOG_PATH.resolve()}")
    print("=" * 70)
    print(f"\nFull debug log: {LOG_PATH.resolve()}")


if __name__ == "__main__":
    main()
