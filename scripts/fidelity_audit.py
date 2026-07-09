"""Ingestion-fidelity audit — the tracked metric for the PB-099 collaboration.
Uses the ENGINE read p.fidelity_audit() (PB 101, ca9c87a) for the canonical
live-fragmentation count, and adds the host-only severity weighting by joining
the flagged entity ids against the arc protagonist + required cast. Read-only."""
import json, sys
from pathlib import Path
from patternbuffer import World
from patternbuffer.testing import StubModel

def audit(name):
    wp = Path(f"worlds/{name}.world")
    if not wp.exists(): return None
    meta = json.loads(Path(f"worlds/{name}.meta.json").read_text()) if Path(f"worlds/{name}.meta.json").exists() else {}
    load_bearing = ({c.get("id") for c in (meta.get("cast") or {}).get("cast") or []}
                    | {meta.get("protagonist")}) - {None}
    w = World(wp, world_id=f"w:{name}", model=StubModel(fallback=lambda p,s:{"items":[]}))
    fa = w.porcelain.fidelity_audit()
    s = fa.get("summary", {})
    # severity: which LIVE collision groups touch the protagonist/required cast?
    severe = 0
    for g in fa.get("name_collisions", []):
        if not g.get("live"): continue
        if set(g.get("entities", [])) & load_bearing: severe += 1
    w.close()
    live = s.get("name_collisions", 0)
    score = severe*5 + (live-severe) + s.get("unstamped_timed",0)//4 + s.get("orphan_entities",0)//4
    return {"name":name, "live":live, "severe":severe,
            "unstamped":s.get("unstamped_timed",0), "orphans":s.get("orphan_entities",0),
            "conflicts":s.get("open_conflicts",0), "score":score}

worlds = sys.argv[1:] or ["bodycase","emberroad","thedeep",
    "live_telegram_8786956263_3","live_telegram_8897888758_1"]
print(f"{'world':<32}{'live':>5}{'sev':>4}{'unstmp':>7}{'orph':>5}{'conf':>5}{'SCORE':>6}")
print("-"*68)
for wn in worlds:
    r = audit(wn)
    print(f"{wn:<32}  (not built)" if r is None else
          f"{r['name']:<32}{r['live']:>5}{r['severe']:>4}{r['unstamped']:>7}{r['orphans']:>5}{r['conflicts']:>5}{r['score']:>6}")
print("-"*68)
print("live=genuine coreference gaps (engine; excludes correctly-distinct)  SCORE=sev*5+live+unstmp/4+orph/4")
