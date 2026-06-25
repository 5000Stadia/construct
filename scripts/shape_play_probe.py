"""Per-shape LIVE richness probe (task #33 — founder: "test all the story shapes, same
richness"). Plays a built world with shape-appropriate inputs and logs the transcript + per-turn
trace, so we can read whether the narrator EMBODIES that shape's signature across turns (and, for
peril shapes, whether the suspense build-up mounts toward the conclusion).

Inputs are shape-flavored (the player pursues that genre's signature moves). Live CodexProvider.
Run:  GENRE=endurance PYTHONPATH=. .venv/bin/python scripts/shape_play_probe.py <world>
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

# Shape-flavored input arcs — the player pursues each genre's signature toward its climax.
_INPUTS = {
    "endurance": [  # trigger-aware: engage the cast (InFrame beats) + DO the acts (Occurred beats)
        "I check on Elias and assess his injured leg.",
        "I take a full inventory of everything that survived the wreck — supplies, gear, the ore.",
        "I ask Elias the safe way down through the snow.",
        "I tell Elias I mean to bring the ore down with us.",
        "I cut the ore loose and abandon it to keep us both on the red cord.",
        "I make the final descent along the cord toward shelter, whatever it costs.",
    ],
    "bond": [
        "I find a quiet moment with the one I keep circling and try, clumsily, to connect.",
        "I press on the thing that's been unsaid between us.",
        "When the old wound surfaces, I don't flinch from it.",
        "I make the gesture that costs me something to make.",
        "I lay my heart open and ask for what I want.",
    ],
    "discovery": [
        "I take in the place and let it unsettle me.",
        "I examine the nearest stratum/inscription closely.",
        "I study the deeper site, even knowing it may cost me.",
        "I weigh the rival readings of what this place was.",
        "I commit to what I now believe this place truly was.",
    ],
    "gambit": [
        "I take the measure of the players and the board.",
        "I work the inside angle and set the pieces.",
        "I press the leverage I've found.",
        "When a complication hits, I adapt the plan on the fly.",
        "I execute the play and spring it.",
    ],
}
GENRE = os.environ.get("GENRE", "endurance")
WORLD = sys.argv[1] if len(sys.argv) > 1 else f"{GENRE}_test"


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/shape-play-{GENRE}-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    s = Session.open(WORLD, player_id=f"shape-{GENRE}", fresh=True, provider=prov)
    w(f"# shape richness probe — {GENRE} — world {WORLD} — "
      f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    w("## OPENING\n\n" + s.opening() + "\n")
    for i, inp in enumerate(_INPUTS.get(GENRE, _INPUTS["endurance"]), 1):
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            tr = r.trace
            w(f"\n## Turn {i} ({wall:.0f}s)\n> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            if tr is not None:
                w(f"*trace: act={getattr(tr, 'act', '')} pacing={tr.pacing} "
                  f"learned={getattr(tr, 'learned_clues', []) or '-'} "
                  f"events_fired={getattr(tr, 'events_fired', []) or '-'} "
                  f"beats={getattr(tr, 'beats_achieved', []) or '-'} "
                  f"conclusion={getattr(tr, 'conclusion_shape', '') or '-'} "
                  f"bounced={getattr(tr, 'commitment_bounced', False)} "
                  f"terminal={getattr(tr, 'terminal', False)} time={tr.time_now!r}*\n")
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} — ENGINE ERROR: {exc}\n")
    s.close()
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
