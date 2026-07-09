"""#56 build proof: rebuild emberroad on the fidelity-repair pipeline; measure
name_collisions before/after + confirm no seal-lint false alarm."""
import json, logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
from pathlib import Path
from construct.game import create_scenario_from_ingest, scenario_path
from construct.provider import CodexProvider
from patternbuffer import World
from patternbuffer.testing import StubModel

def score(wp, wid):
    w = World(wp, world_id=wid, model=StubModel(fallback=lambda p,s:{"items":[]}))
    s = w.porcelain.fidelity_audit()["summary"]; w.close(); return s

print("BEFORE (shipped):", score("worlds/emberroad.world", "w:emberroad"))
name = "emberroad_fr"
if scenario_path(name).exists():
    scenario_path(name).unlink(); scenario_path(name).with_suffix(".meta.json").unlink(missing_ok=True)
_seal_alarms = []
import construct.game as g
_orig = g.logger.error
g.logger.error = lambda m,*a,**k: (_seal_alarms.append(m % a if a else m), _orig(m,*a,**k))
meta = create_scenario_from_ingest(name, Path("generated/emberroad.md"), CodexProvider(),
                                   on_stage=lambda m: print("STAGE:", m, flush=True))
after = score(scenario_path(name), f"w:{name}")
print("AFTER (fidelity-repair):", after)
print("protagonist:", meta.get("protagonist"))
print("SEAL-LINT alarms (should be empty):", [a for a in _seal_alarms if "SEAL-LINT" in str(a)])
