"""Structural validation of the entry-epoch staging fix (obs #3 half 3, Phase 3a): build a
FRESH endurance world (so the build computes meta['entry_epoch'] and stamps opening staging on
the entry axis), then confirm the cast is NO LONGER scattered to aftermath locations — the
at_scene/nearby beat-clue holders resolve to the opening scene / their reachable places, not
Providence Hospital / Anchorage. Deterministic check; no playthrough needed to prove the fix.

Run:  PYTHONPATH=. .venv/bin/python scripts/staging_fix_check.py
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.game import create_scenario_from_generated, _unpublish_scenario, slot_path
from construct.provider import CodexProvider
from construct.session import Session

NAME = "endure_v3_epoch"
PLAYER = "epoch:check"
SEED = ("A small expedition stranded after a bush-plane crash high in a frozen pass — "
        "dwindling supplies, a storm closing in, the guide badly hurt, one companion "
        "losing their nerve. Get down alive before the cold and the dark take you.")
GAME_TYPES = ["wilderness_survival"]


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/staging-fix-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    try:
        _unpublish_scenario(NAME)
        sp = slot_path(NAME, PLAYER)
        if sp.exists():
            sp.unlink()
    except Exception:
        pass

    w(f"# staging-fix structural check — {NAME} — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    t0 = time.perf_counter()
    create_scenario_from_generated(NAME, prov, seed=SEED, game_types=GAME_TYPES,
                                   on_stage=lambda m: w(f"  · {m}"))
    w(f"\n_build wall: {time.perf_counter()-t0:.0f}s_\n")

    s = Session.open(NAME, player_id=PLAYER, fresh=True, provider=prov)
    arc = getattr(s, "_main_arc", None) or s._arc
    p = s._world.porcelain
    from construct.cast import beat_delivery_targets
    from construct.turnloop import _colocated
    meta = s._meta
    w(f"## entry_epoch = {meta.get('entry_epoch')}  (TURN_EPOCH default = 1000.0)\n")
    entry_chain = p.locate(arc.protagonist)
    entry = entry_chain[0] if entry_chain else None
    w(f"## protagonist {arc.protagonist} entry scene = {entry}\n")
    nodes = arc.cast if getattr(arc, "cast", None) else s._cast
    src = nodes.items() if hasattr(nodes, "items") else [(n.node_id, n) for n in nodes]
    w("## cast placement (authored presence/location vs canon locate, co-located at entry?):")
    present = []
    for nid, n in src:
        if not nid.startswith("person:"):
            continue
        loc = p.locate(nid)
        co = _colocated(loc, entry, entry_chain) if entry else False
        if co:
            present.append(nid)
        w(f"  {nid}: authored={getattr(n,'presence','?')}/{getattr(n,'location','')!r} "
          f"-> canon={loc}  colocated@entry={co}")
    w(f"\n## present-at-entry cast: {present}")
    # which InFrame beat-clue holders are now present/reachable
    tgts = beat_delivery_targets(arc.beats)
    w("\n## InFrame beat targets + whether SOME present/reachable cast member holds the fact:")
    castmap = dict(src)
    for t in tgts:
        want = (str(t["entity"]), str(t["attribute"]), str(t["value"]))
        holders = [nid for nid, n in src
                   for c in getattr(n, "holds_clues", ())
                   if tuple(str(x) for x in c.surface_fact) == want]
        w(f"  {t['beat_id']} [{t['phase']}]: {want}  held_by={holders}")
    s.close()
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
