"""make-it-real LIVE acceptance (NARRATION-DISCIPLINE.md slice 4).

Two probes against the examinewho world (means is on obj:bag, scrutiny):

  EMBRACE: the player pursues an UN-AUTHORED detail (a damp ring on the sideboard, a back
  door) instead of the obvious bag. Expected: make-it-real reroutes — `trace.adapted` fires,
  the means pillar COVERS via the player's chosen thread (the chase pays off), the player is
  never railroaded back to the bag, and the case can conclude non-partial via THEIR path.

  RUINOUS (destructive lane, Cx 086): the player does something world-breaking (attacks the
  doctor / destroys evidence). Expected: NO make-it-real rescue (no adapted), the world reacts
  realistically, and the conclusion-as-effect reflects the wrecked case — not a clean solve.

Live CodexProvider. Logs the full transcript + per-turn trace to logs/.
Run:  .venv/bin/python scripts/makereal_acceptance.py [embrace|ruinous|both]
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

WHICH = sys.argv[1] if len(sys.argv) > 1 else "both"

# Semi-scripted player inputs — each probe pursues a SPECIFIC un-authored detail so the run
# deterministically exercises the lane under test (the generic play_harness covers organic play).
EMBRACE = [
    "I look around the parlor and take in who is here.",
    "Something catches my eye on the sideboard — a damp ring where a glass once stood. "
    "I crouch and examine that wet ring closely.",
    "I follow what the wet ring tells me — where did that glass go? I study the spot and the "
    "floor around it carefully.",
    "I press the doctor on what was served to Lord Brackenmere that night.",
    "Based on what I've found, I name the killer and lay out how it was done.",
]
RUINOUS = [
    "I look around the parlor and size up the doctor.",
    "I've had enough of his lies — I grab the fire poker and strike Dr. Ames down, hard, "
    "to kill him right here.",
    "I drag the body aside and set the doctor's bag and its contents into the hearth to burn.",
    "I tell the butler the doctor confessed before he died, and name the doctor the killer.",
]

prov = CodexProvider()


def run(name: str, inputs: list[str], w) -> None:
    s = Session.open("examinewho", player_id=f"makereal-{name}", fresh=True, provider=prov)
    w(f"\n# ===== PROBE: {name} =====\n")
    opening = s.opening()
    w("## OPENING\n\n" + opening + "\n")
    adapted_any = False
    for i, inp in enumerate(inputs, 1):
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            tr = r.trace
            w(f"\n## Turn {i} ({wall:.0f}s)\n> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            if tr is None:
                w("*(session degraded)*\n")
                continue
            adapted = getattr(tr, "adapted", [])
            adapted_any = adapted_any or bool(adapted)
            w(f"*trace: examines_target-driven adapted={adapted or '-'} "
              f"learned={getattr(tr, 'learned_clues', []) or '-'} "
              f"conclusion={getattr(tr, 'conclusion_shape', '') or '-'} "
              f"({getattr(tr, 'conclusion_basis', '')}) "
              f"commitment_grade={getattr(tr, 'commitment_grade', '') or '-'} "
              f"adj={tr.adjudication} terminal={getattr(tr, 'terminal', False)} "
              f"dropped={tr.dropped_cohorts or '-'}*\n")
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} — ENGINE ERROR: {exc}\n")
    # coverage read-out (did the means actually cover?)
    try:
        from construct.adapter import PorcelainWorldReads
        from construct.arc.executor import coverage_summary
        rd = PorcelainWorldReads(s._world)
        summ = coverage_summary(rd, s._arc)
        w(f"\n**FINAL COVERAGE [{name}]:** genuine={summ['genuine']} false={summ['false']} "
          f"unfilled={summ['unfilled']} | adapted_fired={adapted_any}\n")
    except Exception as exc:  # noqa: BLE001
        w(f"\n**(coverage read failed: {exc})**\n")
    s.close()


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/makereal-acceptance-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    w(f"# make-it-real live acceptance — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}")
    if WHICH in ("embrace", "both"):
        run("embrace", EMBRACE, w)
    if WHICH in ("ruinous", "both"):
        run("ruinous", RUINOUS, w)
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
