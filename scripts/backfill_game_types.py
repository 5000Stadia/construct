"""Backfill a derived game_type (primary + optional secondaries, as taxonomy keys)
into each library world's meta.json, so every scenario carries its type(s) on load
and the narrator holds them throughout (GAME-TYPES.md). One-time; skips worlds that
already have game_type and per-player built worlds."""
from __future__ import annotations

import json
import pathlib

from construct import play_styles
from construct.cohorts import classify_game_type
from construct.provider import CodexProvider


def main() -> int:
    provider = CodexProvider()
    d = pathlib.Path("worlds")
    for mp in sorted(d.glob("*.meta.json")):
        name = mp.stem.replace(".meta", "")
        if name.startswith("live_") or ".play" in mp.name:
            continue
        meta = json.loads(mp.read_text())
        title = (meta.get("title") or "").strip()
        if not title or meta.get("game_type"):
            print(f"  skip {name}")
            continue
        desc = meta.get("description") or meta.get("intro") or meta.get("theme") or ""
        try:
            out = classify_game_type(provider, title, desc)
            keys = play_styles.match_many([out.get("primary", "")] + (out.get("secondary") or []))
        except Exception as exc:
            print(f"  FAILED {name}: {exc}")
            continue
        if not keys:
            print(f"  {name}: no type matched (free improvised)")
            continue
        meta["game_type"] = keys
        mp.write_text(json.dumps(meta, indent=2))
        print(f"  {name}: {title} → {keys} ({play_styles.names(keys)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
