"""Ingestion-fidelity audit (host-side, read-only) — the tracked metric for
the PB-099 collaboration. For any built world, count the structural gaps the
run-4 bins represent, weight coreference splits by arc-role severity (a split
on the protagonist or a required clue-holder is show-stopping; a background
prop split is cosmetic), and emit one fidelity score. No writes, no model."""
import json, sys
from collections import defaultdict
from pathlib import Path
from patternbuffer import World
from patternbuffer.testing import StubModel

def audit(name):
    wp = Path(f"worlds/{name}.world")
    mp = Path(f"worlds/{name}.meta.json")
    if not wp.exists():
        return None
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    prot = meta.get("protagonist")
    cast = {c.get("id") for c in (meta.get("cast") or {}).get("cast") or []}
    load_bearing = (cast | {prot}) - {None}
    w = World(wp, world_id=f"w:{name}", model=StubModel(fallback=lambda p,s:{"items":[]}))
    p = w.porcelain
    byname, kinds, timed_missing = defaultdict(set), {}, 0
    for r in w.buffer.visible():
        e = str(r.entity)
        a = str(r.attribute)
        if a == "kind": kinds[e] = str(r.value)
        if a in ("name","alias") and isinstance(r.value, str):
            byname[r.value.strip().lower()].add(e)
    # bin A: coreference splits (name shared across ≥2 ids), by severity
    splits = {n:s for n,s in byname.items() if len(s) > 1}
    severe = [n for n,s in splits.items() if s & load_bearing]  # touches protagonist/cast
    # bin A (engine view): open typing slips
    try: tconf = len(p.typing_conflicts())
    except Exception: tconf = -1
    # bin A residue: unmerged coreference proposals the seal couldn't decide
    try: residue = len(p.adjudicate_deferred().get("residue") or [])
    except Exception: residue = -1
    w.close()
    # weighted score: severe splits ×5, other splits ×1, residue ×1, slips ×2
    score = len(severe)*5 + (len(splits)-len(severe)) + max(residue,0) + max(tconf,0)*2
    return {"name": name, "splits": len(splits), "severe": len(severe),
            "severe_names": severe[:6], "typing_slips": tconf,
            "residue": residue, "score": score, "protagonist": prot}

worlds = [a for a in sys.argv[1:]] or [
    "bodycase","emberroad","thedeep",
    "live_telegram_8786956263_3","live_telegram_8897888758_1"]
print(f"{'world':<32} {'splits':>6} {'severe':>6} {'slips':>5} {'resid':>5} {'SCORE':>6}")
print("-"*70)
rows = []
for wname in worlds:
    r = audit(wname)
    if r is None:
        print(f"{wname:<32}  (not built)"); continue
    rows.append(r)
    print(f"{r['name']:<32} {r['splits']:>6} {r['severe']:>6} "
          f"{r['typing_slips']:>5} {r['residue']:>5} {r['score']:>6}"
          + (f"   ⚠ {r['severe_names']}" if r['severe'] else ""))
print("-"*70)
print("SCORE = severe×5 + splits + residue + slips×2  (lower = cleaner; 0 = ideal)")
