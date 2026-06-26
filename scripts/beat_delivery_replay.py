"""Replay (NO rebuild) of the already-built endure_e2e_beatfix world with TARGETED inputs that
walk the arc's InFrame beat ladder — press Jack about Eli (rising: eli shivering), reach Mara
and press about the frostbite (climax: eli feet_gone), then the costly choice and the aftermath
(falling: the troopers hear). Proves the rising-tension beats now FIRE in play (beats≠-) — the
delivery path the BEAT-DELIVERY-COHERENCE fix created — where the blind first run rushed the
Occurred crisis and concluded before any InFrame beat fired.

Run:  PYTHONPATH=. .venv/bin/python scripts/beat_delivery_replay.py
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

NAME = "endure_e2e_beatfix"
PLAYER = "replay:ladder"
INPUTS = [
    "I crouch beside Jack and press him hard — never mind his own leg, how is Eli bearing "
    "this cold? Give it to me straight, is he shivering, going quiet?",
    "I dig through the Super Cub wreck and take hard stock of what's there and what it'll cost "
    "us to carry.",
    "I leave Jack with the wreck and push out toward the Kuskulana lodge to find Mara Bell.",
    "I press Mara about Eli — how bad are his feet now, really? Has the frostbite taken them?",
    "I cut the ore samples loose and commit us to the old hunter's traverse below the wind "
    "scour — Eli's life over the claim, whatever it costs.",
    "Once we're down, I make certain the troopers hear exactly what happened to Eli up there.",
]


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/beat-delivery-replay-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    s = Session.open(NAME, player_id=PLAYER, fresh=True, provider=prov)
    arc = getattr(s, "_main_arc", None) or s._arc
    from construct.cast import beat_delivery_targets
    w(f"# beat-delivery LADDER replay — {NAME} — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    w("## Arc InFrame beat ladder (targeted inputs walk these):")
    for t in beat_delivery_targets(arc.beats):
        w(f"  - {t['beat_id']} [{t['phase']}]: ({t['entity']}, {t['attribute']}, {t['value']})")
    w("\n## OPENING\n\n" + s.opening() + "\n")
    for i, inp in enumerate(INPUTS, 1):
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            tr = r.trace
            w(f"\n## Turn {i} ({wall:.0f}s)\n> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            if tr is not None:
                w(f"*trace: act={getattr(tr,'act','')} pacing={tr.pacing} "
                  f"learned={getattr(tr,'learned_clues',[]) or '-'} "
                  f"events_fired={getattr(tr,'events_fired',[]) or '-'} "
                  f"beats={getattr(tr,'beats_achieved',[]) or '-'} "
                  f"conclusion={getattr(tr,'conclusion_shape','') or '-'} "
                  f"terminal={getattr(tr,'terminal',False)} time={tr.time_now!r}*\n")
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} — ENGINE ERROR: {exc}\n")
    s.close()
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
