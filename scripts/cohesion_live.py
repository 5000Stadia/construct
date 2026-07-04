"""Multi-location object/location COHESION live test (founder, 2026-06-29).

Drives a FRESH world through a SCRIPTED sequence that crosses several locations and
moves objects, so we can read — turn by turn — whether the world stays coherent:
- a taken object persists and is CARRIED across locations (not duplicated, not lost);
- an object set DOWN stays where it was left (not following the player);
- each new location renders as ITSELF (no conflation — the prior scene's furniture/cast
  must not bleed into the next);
- the canon location (`session.location()`) tracks the intended move every turn.

Scripted (not an LLM wanderer) so coverage is guaranteed. Logs prose + the load-bearing
trace per turn to logs/cohesion-<ts>.md. Runs against the live CodexProvider.

Usage: python scripts/cohesion_live.py [scenario]   (default: latch — the London world)
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from construct import Session
from construct.provider import CodexProvider

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "latch"

#: A deliberate cross-location, object-moving route.
#: NB use a MUNDANE, non-load-bearing improv object (a pencil) so the take mints cleanly
#: via object-permanence — a clue-word like "brass" is correctly blocked by the secret guard.
SCRIPT = [
    "I take stock of the room, then pick up a plain pencil from the desk and pocket it.",
    "I step out the front door into the street.",
    "I look around the street. What is here — and do I still have the pencil?",
    "I walk to the coffee house on the corner and go inside.",
    "I look around the coffee house, then set the pencil down on a table.",
    "I head back out to the street.",
    "I return to the bureau office and look around. Is the pencil here?",
]


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/cohesion-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    s = Session.open(SCENARIO, player_id="cohesion", fresh=True, provider=prov)
    w(f"# Cohesion live test — {SCENARIO} — {len(SCRIPT)} scripted turns\n")
    w("## OPENING\n\n" + s.opening() + "\n")
    w(f"*location after opening: {s.location()!r}*\n")

    for i, inp in enumerate(SCRIPT, 1):
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            s.flush_settle()  # complete the deferred bookkeeping before reading location
            tr = r.trace
            w(f"\n## Turn {i} ({wall:.0f}s)\n")
            w(f"> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            loc = s.location()
            if tr is None:
                w(f"*SESSION DEGRADED — location={loc!r}*\n")
                continue
            w(f"*trace: location={loc!r} moved={tr.movement_status or '-'} "
              f"took={tr.took or '-'} dropped={tr.dropped or '-'} "
              f"adj={tr.adjudication or '-'} audit={tr.concealment_audit} "
              f"time={tr.time_now!r}*\n")
            w(f"*move_debug: {tr.move_debug or '(no moves_to)'}*\n")
            w(f"*carrying: {s.carrying() if hasattr(s, 'carrying') else '?'}*\n")
            # ENTITY AUTHORITY (verified-then-strip proof): the resolver receipts show it shaping the
            # graph at the write boundary; quarantined should be empty for resolver-handled classes.
            w(f"*resolver: {getattr(tr, 'resolver', None) or '-'}*\n")
            w(f"*quarantined: {getattr(tr, 'quarantined', None) or '-'}*\n")
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} — ENGINE ERROR: {exc}\n")
    s.close()
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
