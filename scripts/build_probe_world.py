"""Build one fresh contrasting-shape probe world (overnight shape-breadth test)."""
import sys, json
from construct.game import create_scenario_from_generated, scenario_path
from construct.provider import CodexProvider
name, reality = sys.argv[1], sys.argv[2]
seed = sys.stdin.read().strip()
if scenario_path(name).exists():
    scenario_path(name).unlink(); scenario_path(name).with_suffix(".meta.json").unlink(missing_ok=True)
meta = create_scenario_from_generated(name, CodexProvider(), seed=seed,
        endless=False, reality_register=reality,
        on_stage=lambda m: print("STAGE:", m, flush=True))
laws = [(l["name"], l["register"], l["disclosure"]) for l in meta.get("laws", [])]
print(f"SEALED {name}: {meta.get('title')} | reality={meta.get('reality_register')} "
      f"| game_type={meta.get('game_type')} | laws={laws}")
