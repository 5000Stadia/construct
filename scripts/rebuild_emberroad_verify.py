"""#56 verify + PB-099 fidelity data: rebuild emberroad from its source on the
CURRENT pipeline (Entity Authority + build-seal SHAPE-FIX cleanup, #108) and
measure the relic/typing fragmentation before vs after."""
import json, logging
from collections import defaultdict
from pathlib import Path
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
from construct.game import create_scenario_from_ingest, scenario_path
from construct.provider import CodexProvider
from patternbuffer import World
from patternbuffer.testing import StubModel

def frag(world_path, wid):
    w = World(world_path, world_id=wid, model=StubModel(fallback=lambda p,s:{"items":[]}))
    byname, kinds = defaultdict(set), {}
    for r in w.buffer.visible():
        e=str(r.entity)
        if str(r.attribute)=="kind": kinds[e]=str(r.value)
        if str(r.attribute) in ("name","alias") and isinstance(r.value,str):
            byname[r.value.strip().lower()].add(e)
    splits={n:{e:kinds.get(e,'?') for e in s} for n,s in byname.items() if len(s)>1}
    w.close()
    return splits

before = frag("worlds/emberroad.world", "w:emberroad")
print(f"BEFORE (shipped 2026-06-28): {len(before)} shared-name splits")

name = "emberroad_v2"
if scenario_path(name).exists():
    scenario_path(name).unlink(); scenario_path(name).with_suffix(".meta.json").unlink(missing_ok=True)
meta = create_scenario_from_ingest(name, Path("generated/emberroad.md"), CodexProvider(),
                                   on_stage=lambda m: print("STAGE:", m, flush=True))
after = frag(scenario_path(name), f"w:{name}")
print(f"\nAFTER (current pipeline): {len(after)} shared-name splits")
print("\n=== splits that REMAIN after rebuild ===")
for n,ks in list(after.items())[:20]:
    print(f"  '{n}': {ks}")
print(f"\nRESULT: {len(before)} -> {len(after)} splits (protagonist={meta.get('protagonist')})")
