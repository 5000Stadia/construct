"""Backfill a short genre/story-type tag into each library world's meta.json, so
the Construct can tell guests the STYLE of each title (founder feedback). One-time;
skips worlds that already have `genre` and per-player built worlds (`live_*`)."""
from __future__ import annotations

import json
import pathlib

from construct.cohorts import classify_genre
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
        if not title or meta.get("genre"):
            print(f"  skip {name} (no title / already tagged)")
            continue
        desc = meta.get("description") or meta.get("intro") or meta.get("theme") or ""
        try:
            genre = classify_genre(provider, title, desc)
        except Exception as exc:
            print(f"  FAILED {name}: {exc}")
            continue
        meta["genre"] = genre
        mp.write_text(json.dumps(meta, indent=2))
        print(f"  {name}: {title} — {genre}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
