"""Backfill a concrete BACK-OF-THE-BOOK `premise` into each library world's
meta.json, so the Foyer's pregame world-intro is grounded in the REAL authored
world (not the model improvising from a thin theme/style — the fidelity gap). One-
time; OPENS each world to build the digest, then authors the premise FROM it.
Skips per-player built worlds (`live_*`) and worlds that already have `premise`.

Run: `.venv/bin/python -m scripts.backfill_premise`  (or python scripts/backfill_premise.py)
"""
from __future__ import annotations

import json
import pathlib
import sys

from construct.cohorts import author_premise
from construct.game import _world, _world_digest, scenario_path
from construct.provider import CodexProvider, engine_tier_dispatch


def main() -> int:
    force = "--force" in sys.argv  # re-author even if a premise already exists
    provider = CodexProvider()
    d = pathlib.Path("worlds")
    for mp in sorted(d.glob("*.meta.json")):
        name = mp.stem.replace(".meta", "")
        if name.startswith("live_") or ".play" in mp.name:
            continue
        meta = json.loads(mp.read_text())
        title = (meta.get("title") or "").strip()
        if not title:
            print(f"  skip {name} (no title)")
            continue
        if meta.get("premise") and not force:
            print(f"  skip {name} (already has premise; use --force to re-author)")
            continue
        try:
            world = _world(scenario_path(name), name,
                           model=engine_tier_dispatch(provider))
            digest = _world_digest(world)
            premise = (author_premise(provider, digest, meta.get("theme", ""),
                                      meta.get("genre", "")).get("premise") or "").strip()
        except Exception as exc:
            print(f"  FAILED {name}: {exc}")
            continue
        if not premise:
            print(f"  FAILED {name}: empty premise")
            continue
        meta["premise"] = premise
        mp.write_text(json.dumps(meta, indent=2))
        print(f"  {name}: {premise[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
