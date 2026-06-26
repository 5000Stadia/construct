"""Live integration check of the WHOLE chain on the fresh entry-epoch world (endure_v3_epoch):
authoring coherence (half 1) + topic-aware delivery (half 2) + staging fix (3a). Plays targeted
inputs that press the PRESENT beat-clue holder (Mara, at the opening scene now — not scattered)
and logs the per-turn trace, so we see whether the InFrame beats fire turn-over-turn and the act
climbs. NOTE: this auto-built arc has some self-referential beats (held by the protagonist Carl
himself) that won't deliver via interview — expect partial firing; the interview-deliverable beat
(Mara holds carl.job_risk) is the clean signal.

Run:  PYTHONPATH=. .venv/bin/python scripts/beat_delivery_replay_v3.py
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

NAME = "endure_v3_epoch"
PLAYER = "replay:v3"
INPUTS = [
    "I turn to Mara and press her hard — she's known me for years. How bad does she think my "
    "money troubles really are, the contracts, the house?",
    "I take hard stock of the wreck and what we have left to get down with.",
    "I press Hal on exactly what he saw in the last minute before we went down.",
    "I say it plainly to them: I never filed those cores with the state, and that's on me.",
    "I face what really happened up here and commit to carrying it down honest, whatever it costs.",
]


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/beat-delivery-v3-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    s = Session.open(NAME, player_id=PLAYER, fresh=True, provider=prov)
    arc = getattr(s, "_main_arc", None) or s._arc
    from construct.cast import beat_delivery_targets
    w(f"# beat-delivery v3 integration — {NAME} — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    w(f"## entry_epoch = {s._meta.get('entry_epoch')}")
    w("## InFrame beat ladder:")
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
