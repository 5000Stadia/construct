"""Focused live probe for task #74 — the grounded cold open.

Opens a FRESH bodycase entry (turn 0), simulates the Foyer naming the founder used
(Bradford Clemense / he-him / parents murdered), captures the assembled opening BRIEF
(so we can see the GROUND THE PLAYER directive + WHAT YOU ALREADY KNOW block + the
solo-vs-present grounding mode), and renders the real cold open via CodexProvider.
Single Codex consumer; opening only (no turn loop)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.ERROR)

from construct import cohorts
from construct.provider import CodexProvider
from construct.session import Session

SCEN = "bodycase"
ts = int(time.time())
log = Path(f"logs/grounding-open-{ts}.md")
log.parent.mkdir(exist_ok=True)


def w(s: str) -> None:
    with log.open("a") as f:
        f.write(s + "\n")
    print(s, flush=True)


# capture the brief handed to the open cohort + the grounding mode chosen
_orig = cohorts.open_scene
cap: dict = {}


def _spy(provider, briefing, protagonist, *, grounding=True):
    cap["brief"] = briefing
    cap["grounding"] = grounding
    return _orig(provider, briefing, protagonist, grounding=grounding)


cohorts.open_scene = _spy

prov = CodexProvider()
s = Session.open(SCEN, player_id="grounding_probe", fresh=True, provider=prov)
prot = s._arc.protagonist

# simulate the Foyer (founder's exact flow)
s._world.porcelain.ingest_structured([
    {"entity": prot, "attribute": "name", "value": "Bradford Clemense"},
    {"entity": prot, "attribute": "pronouns", "value": "he/him"},
    {"entity": prot, "attribute": "background", "value": "his parents were murdered"},
])

t0 = time.perf_counter()
opening = s.opening()
wall = time.perf_counter() - t0

w(f"# Grounded cold open probe — {SCEN} (fresh entry)\n")
w(f"protagonist={prot}  grounding_mode={cap.get('grounding')}  ({wall:.0f}s)\n")
w("## ASSEMBLED OPEN BRIEF (what the narrator was handed)\n")
w("```\n" + (cap.get("brief") or "(none captured)") + "\n```\n")
w("## RENDERED COLD OPEN (player-facing)\n")
w(opening + "\n")
s.close()
w("\n--- END ---")
print("LOG:", log, flush=True)
