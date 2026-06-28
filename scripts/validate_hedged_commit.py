"""#2 live validation: a HEDGED accusation must fire the conclusion (or bounce), never stall.

Builds the deterministic Brackenmere pillar-whodunit (author_cast_demo), covers the 3 pillars
over a few investigative turns, then issues a TENTATIVE accusation ("I think it was X...") and
reads the trace. PASS = the hedged move registers as a commitment (trace.commitment set) and
either CONCLUDES (trace.terminal / conclusion_shape) or BOUNCES (commitment_bounced) — i.e. the
story RESPONDS. FAIL (the old bug) = commits never fires, the turn is ordinary narration, nothing.
"""
from __future__ import annotations
import logging, subprocess, sys
from pathlib import Path
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

NAME = "hedgetest"
# build the deterministic pillar whodunit fresh
for suf in (".world", ".meta.json"):
    Path(f"worlds/{NAME}{suf}").unlink(missing_ok=True)
subprocess.run([sys.executable, "scripts/author_cast_demo.py", NAME], check=True)

OUT = Path("logs") / f"hedged-commit-{NAME}.md"
buf: list[str] = []
def w(s):
    buf.append(s); OUT.write_text("\n".join(buf)); print(s, flush=True)

# investigative moves to cover motive (heir), opportunity (butler), means (doctor, pressure),
# then the HEDGED accusation (note the tentative phrasing — the whole point of #2).
MOVES = [
    "I ask Julian, the disinherited nephew, plainly why he was cut out of the will and what he stood to gain by his uncle's death.",
    "I turn to Hobbes the butler and ask who had the chance to be alone with Lord Brackenmere before he was found.",
    "I press Dr. Ames hard — I will not be put off — about exactly how Lord Brackenmere died and what means was used.",
    "I lay out what I have gathered so far and weigh it.",
    "I think it was Julian, the nephew. It must have been him — that's my read.",   # HEDGED accusation
]

prov = CodexProvider()
s = Session.open(NAME, player_id="hedge", fresh=True, provider=prov)
w(f"# #2 HEDGED-COMMITMENT VALIDATION — {NAME}\n")
w("## OPENING\n" + s.opening() + "\n")
for i, mv in enumerate(MOVES, 1):
    r = s.turn(mv)
    t = r.trace
    w(f"\n## turn {i}\n> **Player:** {mv}\n")
    w((r.prose or "(empty)") + "\n")
    if t:
        w(f"_trace: commitment={getattr(t,'commitment','')!r} "
          f"bounced={getattr(t,'commitment_bounced',None)} "
          f"terminal={getattr(t,'terminal',None)} "
          f"conclusion_shape={getattr(t,'conclusion_shape',None)!r} "
          f"pacing={getattr(t,'pacing',None)} learned={getattr(t,'learned_clues',None)} "
          f"ended={r.ended}_")
s.close()
w("\n--- END ---")
print(f"\nTranscript: {OUT}")
