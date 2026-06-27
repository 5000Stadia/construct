"""A/B harness for the narrator-prompt collapse (NARRATOR-CONTEXT-SHAPE.md).

Two modes, so we judge the prompt change from SIDE-BY-SIDE TRANSCRIPTS, not theory:

  capture <world>   — play a fixed probe set (chosen to hit the failure modes the
                      standing rules were accreted to fix), saving each turn's SITUATION
                      briefing + the live (current-prompt) prose to a json. Run once.
  compare <world> <candidate.py>
                    — load the saved briefings and, for each, render A (current standing
                      blocks) vs B (candidate blocks from the candidate module) through
                      cohorts.narrate — the ONLY difference is the standing blocks — and
                      dump them side by side to logs/narrator-ab-*.md.

A candidate module defines `OVERRIDES = {"RENDER_STYLE": "...", "RENDER_LEASH": "...", ...}`
applied to `construct.cohorts` for the B render.

Probes target: room-grounding/recap, charged accusation (peopled), search (clue
affordance), competence-implying action, out-of-world request (world-fit), same-location
follow-up (no-recap). Imagery is disabled here — we only want the narrator text.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ["CONSTRUCT_SCENE_IMAGES"] = "0"  # narrator text only; no image gen here

from construct import cohorts
from construct.provider import CodexProvider
from construct.session import Session

PROBES = {
    "latch": [
        "I look slowly around the study, taking in the room.",          # grounding
        "I accuse the nearest person to their face of the murder.",      # peopled/emotion
        "I search the desk and the floor around the body for anything.", # clue affordance
        "As the detective, I reconstruct how the bolt could have been worked from outside.",  # competence
        "I ask if there's a telephone I can use to call the Yard.",      # world-fit (1888)
        "I keep my eyes on them and wait for an answer.",                # same-place, no recap
    ],
    "anchor": [
        "I look around the allocation office.",
        "I accuse the clerk of falsifying the water ledger, to their face.",
        "I search the office for the missing chits.",
        "As the custodian, I recall how night transfers are supposed to be filed.",
        "I ask where the nearest coffee shop is.",
        "I wait, watching them.",
    ],
}

CAP_DIR = Path("logs"); CAP_DIR.mkdir(exist_ok=True)


def _cap_path(world: str) -> Path:
    return CAP_DIR / f"narrator-briefings-{world}.json"


def capture(world: str) -> None:
    prov = CodexProvider()
    s = Session.open(world, player_id="ab", fresh=True, provider=prov)
    rows = []
    s.opening()
    for inp in PROBES.get(world, PROBES["latch"]):
        r = s.turn(inp)
        br = getattr(r.trace, "briefing", "") if r.trace else ""
        rows.append({"input": inp, "briefing": br, "baseline_prose": r.prose or ""})
        print(f"· captured: {inp[:50]}…  (briefing {len(br)} chars)", flush=True)
    s.close()
    _cap_path(world).write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"\nsaved {len(rows)} briefings → {_cap_path(world)}")


def compare(world: str, candidate_path: str) -> None:
    rows = json.loads(_cap_path(world).read_text())
    import importlib.util
    spec = importlib.util.spec_from_file_location("candidate", candidate_path)
    cand = importlib.util.module_from_spec(spec); spec.loader.exec_module(cand)
    overrides = getattr(cand, "OVERRIDES", {})
    prov = CodexProvider()
    out = CAP_DIR / f"narrator-ab-{world}-{int(time.time())}.md"
    buf = [f"# Narrator A/B — {world} — candidate {Path(candidate_path).name}\n",
           f"Overrides: {', '.join(overrides) or '(none)'}\n"]
    proto = "person:protagonist"
    for i, row in enumerate(rows, 1):
        br = row["briefing"]
        if not br:
            continue
        a = cohorts.narrate(prov, br, proto)                       # current standing blocks
        saved = {k: getattr(cohorts, k) for k in overrides}
        try:
            for k, v in overrides.items():
                setattr(cohorts, k, v)
            b = cohorts.narrate(prov, br, proto)                   # candidate standing blocks
        finally:
            for k, v in saved.items():
                setattr(cohorts, k, v)
        buf += [f"\n## probe {i}: {row['input']}\n",
                f"**A (current):**\n{a}\n", f"**B (candidate):**\n{b}\n", "\n---\n"]
        out.write_text("\n".join(buf))
        print(f"· rendered probe {i}", flush=True)
    print(f"\nA/B transcript → {out}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "capture":
        capture(sys.argv[2])
    else:
        print("usage: narrator_ab.py capture <world> | compare <world> <candidate.py>")
