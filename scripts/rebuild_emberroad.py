"""Button up `emberroad`: KEEP the (charming) authored bible, but re-ingest it with the
game-type FORCED to the quest/journey shape so it plays as the epic it is — not the
social-drama it misclassified into. The old mis-staged world is moved aside first.

Fix: classify drift (`social_drama_relationship_web`) → forced `epic_quest_saga +
pilgrimage`, which drives BOTH the narrator's journey directives and the shape-aware
staging/opening. Source bible unchanged (generated/emberroad.md). Then play the opening
+ a few journey-testing turns to confirm it actually SETS OUT on the East Road.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.game import create_scenario_from_ingest, scenario_path, slot_path
from construct.provider import CodexProvider
from construct.session import Session
from construct.transport_core import _humanize_stage

NAME = "emberroad"
BIBLE = Path("generated/emberroad.md")
GAME_TYPES = ["epic_quest_saga", "pilgrimage"]
WIN = "carry the waking relic to the mountain and decide its fate — and yours"
PLAY_AS = "an unlikely villager who didn't ask to be the one to go"
MOVES = [
    "I shoulder the wrapped Crown and set out east on the road, watchful for what travels it.",
    "I press on toward the mountain and ask my companions what they make of the road ahead.",
    "I keep moving east, mindful of the cold relic and whoever might be following us.",
]

OUT = Path("logs") / f"emberroad-rebuild-{int(time.time())}.md"
OUT.parent.mkdir(exist_ok=True)
_buf: list[str] = []


def w(line: str) -> None:
    _buf.append(line)
    OUT.write_text("\n".join(_buf))
    print(line, flush=True)


def main() -> None:
    prov = CodexProvider()
    # Move the old (mis-staged) world aside — the bible regenerates it, so this is safe.
    retired = Path("worlds/_retired"); retired.mkdir(parents=True, exist_ok=True)
    for suf in (".world", ".meta.json", ".images.json"):
        p = scenario_path(NAME).with_suffix(suf) if suf != ".world" else scenario_path(NAME)
        if p.exists():
            shutil.move(str(p), str(retired / f"{NAME}-drama-{int(time.time())}{suf}"))
            w(f"moved aside: {p.name}")
    for slot in (slot_path(NAME, "preset"),):
        if slot.exists():
            slot.unlink()

    w(f"\n# REBUILD emberroad — bible kept, game_type forced → {GAME_TYPES}\n")
    t0 = time.time()
    try:
        meta = create_scenario_from_ingest(
            NAME, BIBLE, prov, endless=False, win_direction=WIN, play_as=PLAY_AS,
            game_types=GAME_TYPES,
            on_stage=lambda m: w("  " + (_humanize_stage(m) or f"· {m}…")))
    except Exception as exc:  # noqa: BLE001
        w(f"\n*** REBUILD FAILED: {exc} ***")
        raise
    w(f"\n*(built in {time.time()-t0:.0f}s)*")
    w(f"TITLE: {meta.get('title')!r}  protagonist: {meta.get('protagonist')!r}  "
      f"game_type: {meta.get('game_type')!r}\n")

    s = Session.open(NAME, player_id="preset", fresh=True, provider=prov)
    w("## OPENING\n")
    w(s.opening() + "\n")
    for i, mv in enumerate(MOVES, 1):
        r = s.turn(mv)
        w(f"\n## turn {i}\n> **Player:** {mv}\n")
        w((r.prose or "(empty)") + "\n")
    s.close()
    w("\n--- END ---")
    print(f"\nTranscript: {OUT}")


if __name__ == "__main__":
    main()
