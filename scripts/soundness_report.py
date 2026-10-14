#!/usr/bin/env python3
"""STORY SOUNDNESS calibration (docs/design/STORY-SOUNDNESS.md r4, R35).

Runs the advisory producer fixed point, READ-ONLY, over archived worlds: every arc in each
world's plot frame, at that world's horizon (the opening for a scenario world; the play
horizon for a played/checkpoint world). Worlds are copied to a temp dir before opening.

    scripts/soundness_report.py DIR [DIR ...]

Each DIR holds `<name>.world` files and `<name>.meta.json` (the run archives' layout).
The refusal-clock defect (nothing writes `event:abandoned`) is named ONCE, not per arc.
No model calls.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path


def _report_world(path: Path, meta: dict) -> list[str]:
    from construct.adapter import HorizonView, PorcelainWorldReads, play_horizon
    from construct.arc import io as arc_io
    from construct.arc.soundness import analyse
    from construct.cast import cast_from_proposal
    from construct.game import _world, next_turn_number
    name = path.name.split(".")[0]
    tmp = Path(tempfile.mkdtemp()) / path.name
    shutil.copyfile(path, tmp)
    world = _world(tmp, name, model=lambda _p, _s: {"items": []})
    out = []
    try:
        played = ".play." in path.name or ".checkpoint." in path.name
        h = play_horizon(meta.get("opening_as_of"), meta.get("next_source_as_of"),
                         next_turn_number(world) if played else 0)
        view = HorizonView(world, h)
        reads = PorcelainWorldReads(view)
        cast = tuple(cast_from_proposal(meta["cast"])[0]) if meta.get("cast") else ()
        for arc in arc_io.portfolio_from_frame(reads):
            kind = "continuation" if arc.arc_id.startswith("arc:ep_") else "fresh"
            rep = analyse(arc, cast, arc.protagonist, reads, horizon=h, world=view,
                          kind=kind, goal_statement=meta.get("goal_statement", ""))
            out.append(f"  {arc.arc_id} ({kind}, h={h}): "
                       f"{len(rep.findings)} finding(s)")
            out += [f"    {line}" for line in rep.lines()]
    finally:
        world.close()
    return out


def main(argv: list[str]) -> int:
    print("Known defect (reported once, not per arc): every generated arc's refusal clock "
          "waits on Occurred(event:abandoned*), which nothing writes (R36 / B1 fixes it).")
    for d in map(Path, argv):
        metas = {m.name.split(".")[0]: json.loads(m.read_text())
                 for m in d.glob("*.meta.json")}
        for wpath in sorted(d.glob("*.world")):
            meta = metas.get(wpath.name.split(".")[0], {})
            print(f"{wpath}")
            try:
                print("\n".join(_report_world(wpath, meta)))
            except Exception as exc:  # noqa: BLE001 — one unreadable world never stops the run
                print(f"  skipped: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
