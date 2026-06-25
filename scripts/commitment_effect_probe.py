"""COMMITMENT-AS-EFFECT live acceptance (slice 4) on the crossweb deduction world.

Validates the shipped feature in live play:
- an EARLY accusation (before the evidence is gathered) BOUNCES — non-terminal, the world
  declines, the player is told to keep going (slice 1, the founder's "bad accusation, world
  behaves accurately, not over");
- after the case is genuinely assembled, the accusation LANDS and grades as the coverage EFFECT
  (vindicated/triumph) — no LLM judge (slice 2).

Live CodexProvider; logs the transcript + per-turn trace.
Run:  PYTHONPATH=. .venv/bin/python scripts/commitment_effect_probe.py [world]
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
    "I take in the parlor and everyone here.",
    "Without hearing anyone out, I immediately accuse Dr. Ames of the murder and demand he be arrested.",
    "I press Lady Brackenmere on what she saw the doctor do with his bag after dinner.",
    "I press Hobbes: who did you let into the study, and what did you overhear?",
    "I press Julian on what he saw through the conservatory glass.",
    "Now I lay out the whole case — motive, means, and opportunity — and name the killer.",
]


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/commitment-effect-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    s = Session.open(NAME, player_id="commit-probe", fresh=True, provider=prov)
    w(f"# commitment-as-effect probe — {NAME} — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
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
                w(f"*trace: bounced={getattr(tr, 'commitment_bounced', False)} "
                  f"grade={getattr(tr, 'commitment_grade', '') or '-'} "
                  f"conclusion={getattr(tr, 'conclusion_shape', '') or '-'} "
                  f"terminal={getattr(tr, 'terminal', False)} "
                  f"learned={getattr(tr, 'learned_clues', []) or '-'} "
                  f"fallout={getattr(tr, 'main_fallout', []) or '-'}*\n")
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} — ENGINE ERROR: {exc}\n")
    s.close()
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
