"""LIVE confirm the narrator-emphasize signature channel (GENRE-SIGNATURE-ELEMENTS.md): play the
hand-authored cross-suspicion world (crossweb) and watch whether the narrator LEANS INTO the
genre's spirit across turns — suspects pointing at one another (cross-suspicion surfacing from
knows:<npc>), red herrings appearing and being weighable, alibis corroborating/contradicting.

Semi-scripted: interview each suspect and press them, so the web has the chance to surface.
Live CodexProvider. Logs the full transcript + per-turn trace to logs/.
Run:  PYTHONPATH=. .venv/bin/python scripts/signature_play_probe.py [name]
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

NAME = sys.argv[1] if len(sys.argv) > 1 else "crossweb"
INPUTS = [
    "I take in the parlor and everyone here, and ask who found Lord Brackenmere.",
    "I press Hobbes the butler: who did you let into the study, and what did you overhear?",
    "I turn to Julian, the nephew, and press him on what he saw and who he blames.",
    "I question Dr. Ames directly about the cause of death and his medical bag.",
    "I press Lady Brackenmere on what she saw the doctor do after dinner.",
    "I lay the conflicting accounts side by side and confront the doctor with them.",
    "I name the killer and lay out the motive, means, and opportunity.",
]


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/signature-play-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    s = Session.open(NAME, player_id="sigprobe", fresh=True, provider=prov)
    w(f"# Signature narrator-emphasize probe — {NAME} — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    w("## OPENING\n\n" + s.opening() + "\n")
    for i, inp in enumerate(INPUTS, 1):
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            tr = r.trace
            w(f"\n## Turn {i} ({wall:.0f}s)\n> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            if tr is not None:
                w(f"*trace: learned={getattr(tr, 'learned_clues', []) or '-'} "
                  f"adapted={getattr(tr, 'adapted', []) or '-'} "
                  f"conclusion={getattr(tr, 'conclusion_shape', '') or '-'} "
                  f"grade={getattr(tr, 'commitment_grade', '') or '-'} "
                  f"terminal={getattr(tr, 'terminal', False)}*\n")
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} — ENGINE ERROR: {exc}\n")
    try:
        from construct.adapter import PorcelainWorldReads
        from construct.arc.executor import coverage_summary
        summ = coverage_summary(PorcelainWorldReads(s._world), s._arc)
        w(f"\n**FINAL COVERAGE:** genuine={summ['genuine']} false={summ['false']} "
          f"unfilled={summ['unfilled']}\n")
    except Exception as exc:  # noqa: BLE001
        w(f"\n**(coverage read failed: {exc})**\n")
    s.close()
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
