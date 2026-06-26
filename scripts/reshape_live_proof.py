"""LIVE PROOF — world-changing agency (WORLD-CHANGING-AGENCY.md), Cx-GREEN (223).

Multi-turn proof on the ALREADY-BUILT lighthouse world (no rebuild): flag ON, revive
the dead keeper (the reshape), then question the revived witness and pursue who
attacked him (the re-aimed case keeps going). Transcript → logs/reshape-live-proof-*.md.

Set REBUILD=1 to author a fresh world first (≈25 min).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.game import create_scenario_from_generated, slot_path, _unpublish_scenario, scenario_path
from construct.provider import CodexProvider
from construct.session import Session
from construct.transport_core import _humanize_stage

NAME = "reshape_live_proof"
PLAYER = "proof2"
SEED = ("an 1894 lighthouse station on a storm-cut rock, the relief boat overdue; the "
        "assistant keeper found dead at the foot of the tower stair; a handful of souls "
        "trapped together on the rock, each with something to hide")
WIN = "find out who killed the assistant keeper and name them"
PLAY_AS = "the doctor rowed out to tend the living and account for the dead"

MOVES = [
    # phrased WITHOUT referencing unestablished items (a 'my bag'/'phial' reference can trip
    # the object-adjudication deny, which is a separate concern from the reshape path)
    "I am a physician and I refuse to let him die. I work over the dead assistant keeper with "
    "everything my training and my hands can do, fighting to bring him back to life.",
    "Now that breath is in him, I lean close and ask him gently: who did this to you?",
    "I press him for a name and a face, and I turn to confront whoever he points toward.",
    "I question the one he named about where they were when he went down the stair.",
]

OUT = Path("logs") / f"reshape-live-proof-{int(time.time())}.md"
OUT.parent.mkdir(exist_ok=True)
_buf: list[str] = []


def w(line: str) -> None:
    _buf.append(line)
    OUT.write_text("\n".join(_buf))
    print(line, flush=True)


def main() -> None:
    os.environ["CONSTRUCT_WORLD_RESHAPE"] = "1"   # the founder's flag — ON for the proof
    prov = CodexProvider()
    w("# LIVE PROOF — world-changing agency (reshape → re-aim) — flag ON\n")

    if os.getenv("REBUILD") == "1" or not scenario_path(NAME).exists():
        if scenario_path(NAME).exists():
            _unpublish_scenario(NAME)
        w("## BUILD (fresh, production generate-then-ingest)\n")
        t0 = time.time()
        create_scenario_from_generated(
            NAME, prov, seed=SEED, endless=False, win_direction=WIN, play_as=PLAY_AS,
            on_stage=lambda m: w("  " + (_humanize_stage(m) or f"· {m}…")))
        w(f"\n*(build completed in {time.time()-t0:.0f}s)*\n")
    else:
        w("## (reusing the already-built lighthouse world)\n")

    slot = slot_path(NAME, PLAYER)
    if slot.exists():
        slot.unlink()
    s = Session.open(NAME, player_id=PLAYER, fresh=True, provider=prov)
    w("## OPENING\n")
    w(s.opening() + "\n")

    reshaped_at = replanned_to = ""
    for i, inp in enumerate(MOVES, 1):
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            tr = r.trace
            w(f"\n## turn {i} ({wall:.0f}s)\n")
            w(f"> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            if tr is not None:
                rsh = getattr(tr, "reshape", "")
                rep = getattr(tr, "replanned", "")
                ents = getattr(tr, "reshape_entities", []) or []
                reshaped_at = reshaped_at or (str(i) if rsh else "")
                replanned_to = replanned_to or rep
                w(f"*trace: reshape={bool(rsh)} replanned={rep!r} reshape_entities={ents} "
                  f"main_arc(session)={s._arc.arc_id} adjudication={getattr(tr,'adjudication','')!r}*\n")
                if rsh:
                    w(f"\n  ↳ RESHAPE SUMMARY (host directive to the narrator): {rsh}\n")
            if getattr(r, "ended", False):
                w(f"\n*(— reached a terminal conclusion at turn {i} —)*\n")
                break
        except Exception as exc:  # noqa: BLE001
            w(f"\n## turn {i} — ENGINE ERROR: {exc}\n")
    s.close()

    w("\n## PROOF SUMMARY\n")
    w(f"- reshape committed at turn: {reshaped_at or 'NONE'}")
    w(f"- arc re-planned to: {replanned_to or 'NONE'}")
    w("\n--- END ---")
    print(f"\nTranscript: {OUT}")


if __name__ == "__main__":
    main()
