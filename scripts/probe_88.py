"""#88 live-acceptance probe: exercise the CLARIFICATION GATE and the TWO-BEAT CLOSE
directly with scripted player inputs (the LLM-player harness roams; this drives the
exact seam). Fresh bodycase slot; live CodexProvider narration; ~8 turns.

Script: investigate briefly → attempt an UNSTAGED accusation from the wrong room
(expect the staging clarification, not a graded outcome) → travel to the accused and
put it to him plainly (expect the staged commitment → two-beat reckoning/aftermath)."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

SCRIPT = [
    "I examine the body and the yard closely with my field kit.",
    "Reed, walk me through who had use of the yard gate last night.",
    "I press Reed on where the sample token points.",
    # THE UNSTAGED ATTEMPT — alone-ish, away from the accused, underspecified:
    "It was Arthur Liddell. He killed the messenger. Case closed.",
    # Follow the story's own staging guidance:
    "I go to Arthur Liddell at his warehouse, with Reed.",
    ("I put it to Liddell to his face, in front of Reed: the token, the gate, and the "
     "scales say he met the messenger and killed him — I am taking him in for the "
     "murder."),
    # If the close landed, this is post-ending; if not, one more push:
    "I hold his eye and wait.",
]


def main() -> None:
    prov = CodexProvider()
    ts = int(time.time())
    log = Path(f"logs/probe88-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    s = Session.open("bodycase", player_id="probe88", fresh=True, provider=prov)
    w(f"# #88 probe — bodycase — {ts}\n")
    w("## OPENING\n\n" + s.opening() + "\n")
    for i, inp in enumerate(SCRIPT, 1):
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            tr = r.trace
            w(f"\n## Turn {i} ({wall:.0f}s)\n\n> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            if tr is not None:
                w(f"*trace: clarified={getattr(tr, 'commitment_clarified', '')!r} "
                  f"concluded={getattr(tr, 'concluded', '')} terminal={tr.terminal!r} "
                  f"adj={tr.adjudication} ended={r.ended}*\n")
            else:
                w("*SESSION DEGRADED*\n")
            if r.ended:
                w("\n**— chapter ended here —**\n")
                break
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} — ENGINE ERROR: {exc}\n")
    s.close()
    w(f"\nLOG: {log}")


if __name__ == "__main__":
    main()
