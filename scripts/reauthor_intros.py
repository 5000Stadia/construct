"""Re-author the THEMATIC INTRO for the base showcase worlds with the fixed
author_intro cohort (concrete + plain, no purple aphorism-stacking). Reads each
world's digest, re-runs the cohort, prints OLD vs NEW, and updates meta['intro'].
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING)

from construct import cohorts
from construct.game import _world, _world_digest, scenario_path
from construct.provider import CodexProvider

WORLDS = ["anchor", "latch", "thedeep", "emberroad"]


def main() -> None:
    prov = CodexProvider()
    for name in WORLDS:
        mp = scenario_path(name).with_suffix(".meta.json")
        if not mp.exists():
            print(f"(skip {name}: no meta)")
            continue
        meta = json.loads(mp.read_text())
        world = _world(scenario_path(name), name)  # read-only digest, no model
        try:
            digest = _world_digest(world)
        finally:
            world.close()
        theme = meta.get("theme", "")
        style = meta.get("style", "")
        aim = meta.get("goal_statement") or "find your way through the story to its end"
        new = (cohorts.author_intro(prov, digest, theme, style, aim).get("intro") or "").strip()
        print(f"\n===== {name} ({meta.get('title')!r}) =====")
        print(f"OLD:\n{meta.get('intro','')}\n")
        print(f"NEW:\n{new}\n")
        if new:
            meta["intro"] = new
            mp.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
            print("(meta updated)")
        else:
            print("(no new intro returned — kept old)")


if __name__ == "__main__":
    main()
