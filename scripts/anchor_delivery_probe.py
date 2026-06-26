"""Clean live proof of topic-aware delivery (half 2) + entry-epoch (3a) on the KNOWN-GOOD anchor
deduction world (FIVE-OF-FIVE) — beats held by PRESENT suspects (not self), so the ladder can
actually fire. Doubles as Cx's required anchor REGRESSION check (the change must not break the
gold-standard world). Targeted inputs press each suspect about the specific topic its beat clue
covers; we watch whether the matching clue is delivered (learned≠-) and the InFrame beats fire.

Run:  PYTHONPATH=. .venv/bin/python scripts/anchor_delivery_probe.py
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

NAME = "anchor"
PLAYER = "probe:anchor_delivery"
# Press each present suspect about the SPECIFIC topic its beat clue covers (the anchor InFrame
# beats: clerk maintains the vault; Cray wrote the phantom reserve / signed the decommission /
# summoned the investigator).
INPUTS = [
    "I ask the old clerk about the vault — what is it he keeps and maintains down here?",
    "I press Administrator Cray hard about the phantom reserve in the ledgers — who wrote it in?",
    "I press Cray on the decommission order: did he sign it, and when?",
    "I put it to Cray plainly — he's the one who summoned me here, isn't he?",
    "I lay out what I've found and name who falsified the reserve.",
]


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/anchor-delivery-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    s = Session.open(NAME, player_id=PLAYER, fresh=True, provider=prov)
    arc = getattr(s, "_main_arc", None) or s._arc
    from construct.cast import beat_delivery_targets
    w(f"# anchor delivery+epoch probe — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    w(f"## entry_epoch = {s._meta.get('entry_epoch')}  (anchor is one-timeframe → expect no-op 1000.0)")
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
