"""Build a FRESH London story (founder, 2026-06-29): ditch the ledger/accounting focus —
an operative of an active investigative BODY working a fresh MURDER. Active fieldwork:
a corpse to examine, a scene to work, witnesses to canvass, suspects to run down across
the city. New field-investigator protagonist (no clerk, no ledgers). Logs build stages.

Usage: python scripts/build_bodycase.py [name]   (default: bodycase)
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from construct.game import create_scenario_from_interview
from construct.provider import CodexProvider

NAME = sys.argv[1] if len(sys.argv) > 1 else "bodycase"

BRIEF = (
    "London, 1888 — gaslit streets, river fog, hansom cabs, soot and rain. This is an ACTIVE "
    "field investigation, hands-on and out in the city — emphatically NOT paperwork, accounting, "
    "or ledgers. You are a field operative of an active investigative BODY: a plain-clothes "
    "detective bureau (a small, hard-pressed inquiry division working with, and sometimes around, "
    "the Metropolitan Police). The bureau has a chief who applies pressure, real resources, and at "
    "least one colleague/partner who works the case alongside you.\n\n"
    "The case: a fresh MURDER has just been reported. You are dispatched to the scene, where there "
    "is a BODY to examine — its wounds, its posture, what it carried, what was taken — and a crime "
    "scene to comb for physical traces. The investigation is LEGWORK: read the body, work the "
    "scene, canvass witnesses in the surrounding streets, follow the physical evidence (wounds, "
    "marks, movements, alibis) to suspects scattered across distinct parts of the city, and track "
    "them down and confront them. There are SEVERAL real locations to move between — the scene, the "
    "bureau's offices, the streets around it, a suspect's lodging or place of work, a public house "
    "or two — each its own place with its own people. The truth turns on what the body and the "
    "scene physically show, run down by footwork, not on documents.\n\n"
    "Tone: a Victorian detective procedural — methodical, atmospheric, with a real culprit to catch."
)

PLAY_AS = (
    "a field investigator (detective-operative) of the bureau — newly assigned to active casework, "
    "the one sent out to the body and into the streets to run the case down. A capable observer of "
    "physical detail and people; known for legwork, not paperwork."
)


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/build-{NAME}-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def stage(m: str) -> None:
        line = f"· {m}"
        with log.open("a") as f:
            f.write(line + "\n")
        print(line, flush=True)

    t0 = time.perf_counter()
    meta = create_scenario_from_interview(
        NAME, BRIEF, CodexProvider(), play_as=PLAY_AS,
        game_types=["detective_procedural", "mystery_whodunnit"], on_stage=stage)
    dt = time.perf_counter() - t0
    title = (meta or {}).get("title", "(untitled)")
    gt = (meta or {}).get("game_type") or (meta or {}).get("game_types")
    with log.open("a") as f:
        f.write(f"\nBUILT {NAME!r} in {dt:.0f}s — title={title!r} game_type={gt}\n")
    print(f"BUILT {NAME!r} in {dt:.0f}s — title={title!r} game_type={gt}", flush=True)
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
