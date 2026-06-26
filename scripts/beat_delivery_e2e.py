"""End-to-end proof of BEAT-DELIVERY-COHERENCE (obs #3): build a FRESH endurance world via
the real generate-then-ingest pipeline (which now feeds the arc's InFrame beats into
author_cast as delivery targets), then play it with shape-appropriate inputs and log the
per-turn trace — so we can see the rising beats ACTUALLY FIRE (learned≠-, beats include the
InFrame ladder) and the act climb I→II before the climax, instead of skipping straight to the
Occurred conclusion.

Run:  PYTHONPATH=. .venv/bin/python scripts/beat_delivery_e2e.py
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.game import create_scenario_from_generated, _unpublish_scenario, slot_path
from construct.provider import CodexProvider
from construct.session import Session

NAME = "endure_e2e_beatfix"
PLAYER = "e2e:tester"
SEED = ("A small expedition stranded after a bush-plane crash high in a frozen pass — "
        "dwindling supplies, a storm closing in, the guide badly hurt, one companion "
        "losing their nerve. Get down alive before the cold and the dark take you.")
GAME_TYPES = ["wilderness_survival"]
INPUTS = [
    "I kneel by the guide and check how bad the injury is.",
    "I press the shaken companion on what they're really afraid of.",
    "I take stock of everything that survived the crash.",
    "I ask the guide which way down we should take, and listen to the warning.",
    "I commit us to the low route and start the descent before dark, whatever it costs.",
    "I push on through the last of the light toward the shelter below.",
]


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/beat-delivery-e2e-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    # clean any prior run
    try:
        _unpublish_scenario(NAME)
        sp = slot_path(NAME, PLAYER)
        if sp.exists():
            sp.unlink()
    except Exception:
        pass

    w(f"# beat-delivery E2E — fresh endurance build — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    w("## BUILD (real generate-then-ingest, with beat_targets wiring)\n")
    t0 = time.perf_counter()
    create_scenario_from_generated(NAME, prov, seed=SEED, game_types=GAME_TYPES,
                                   on_stage=lambda m: w(f"  · {m}"))
    w(f"\n_build wall: {time.perf_counter()-t0:.0f}s_\n")

    s = Session.open(NAME, player_id=PLAYER, fresh=True, provider=prov)
    # surface the arc's InFrame beat ladder so we can match it against what fires
    arc = getattr(s, "_main_arc", None) or s._arc
    from construct.cast import beat_delivery_targets
    tgts = beat_delivery_targets(arc.beats)
    w("## ARC InFrame beat ladder (must be deliverable now):")
    for t in tgts:
        w(f"  - {t['beat_id']} [{t['phase']}/{'req' if t['required'] else 'opt'}]: "
          f"({t['entity']}, {t['attribute']}, {t['value']})")
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
