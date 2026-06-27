"""Four-world live A/B (B' S5 + founder's 2-3-turn check): open a starting scenario FRESH and
play a few genre-neutral moves, logging the opening + each turn's prose AND a per-turn
diagnostic header (protagonist location + who is present) so the staging/opening can be graded.

The diagnostic is the B' gate: a horizon world (emberroad) must OPEN at its beginning (Harth,
humble Mara), never the source aftermath; the legacy worlds (anchor/latch/thedeep) must open
materially as before. Usage: python scripts/four_world_live.py <scenario> [turns]
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "anchor"
TURNS = int(sys.argv[2]) if len(sys.argv) > 2 else 3

# Genre-neutral moves that exercise staging/presence/coherence in any opening.
MOVES = [
    "I take in where I am — the place, the hour, who is here with me — and get my bearings.",
    "I turn to the nearest person and ask them plainly what's happening and what they need of me.",
    "I follow the most pressing thread in front of me and take a concrete first step on it.",
]

OUT = Path("logs") / f"fourworld-{SCENARIO}-{int(time.time())}.md"
OUT.parent.mkdir(exist_ok=True)
_buf: list[str] = []


def w(line: str) -> None:
    _buf.append(line)
    OUT.write_text("\n".join(_buf))
    print(line, flush=True)


def _diag(s: Session) -> str:
    """Where the protagonist is + who's present, read through the session (horizon-aware)."""
    try:
        loc = s.location()
        where = s._display_name(loc) if loc else "(nowhere)"
        names = s._establishing_anchors()[1]
        present, absent = s._present_people(names)
        h = s._horizon()
        return (f"_loc: {where} ({loc}) · present: {present or '—'} · "
                f"elsewhere-known: {absent or '—'} · horizon: {h}_")
    except Exception as exc:  # diagnostics must never sink the run
        return f"_(diag unavailable: {exc})_"


def main() -> None:
    prov = CodexProvider()
    s = Session.open(SCENARIO, player_id="ab", fresh=True, provider=prov)
    w(f"# FOUR-WORLD LIVE — {SCENARIO}\n")
    meta = s._meta
    w(f"_game_type: {meta.get('game_type')!r} · opening_as_of: {meta.get('opening_as_of')} · "
      f"next_source_as_of: {meta.get('next_source_as_of')}_\n")
    w("## OPENING")
    w(_diag(s) + "\n")
    w(s.opening() + "\n")
    for i, mv in enumerate(MOVES[:TURNS], 1):
        r = s.turn(mv)
        w(f"\n## turn {i}\n> **Player:** {mv}\n")
        w(_diag(s) + "\n")
        w((r.prose or "(empty)") + "\n")
    s.close()
    w("\n--- END ---")
    print(f"\nTranscript: {OUT}")


if __name__ == "__main__":
    main()
