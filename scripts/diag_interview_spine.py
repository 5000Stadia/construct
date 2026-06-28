"""Diagnose the interview-path protagonist-guard failure: build the spine, ingest it, and show
whether people get locatable `in` placements."""
import logging
logging.basicConfig(level=logging.ERROR)
from construct import cohorts
from construct.provider import CodexProvider
from construct.game import _world, scenario_path, engine_tier_dispatch
from pathlib import Path

prov = CodexProvider()
brief = "A slow-burn romance between two people thrown together by a long winter in a remote lighthouse station."
spine = cohorts.interview_world(prov, brief, play_as="")
items = spine.get("items", [])
print(f"spine: {len(items)} items, title={spine.get('title')!r}")
# show all `in` rows + people
people = sorted({it['entity'] for it in items if str(it.get('entity','')).startswith('person:')})
ins = [(it['entity'], it.get('value')) for it in items if it.get('attribute')=='in']
print(f"people ({len(people)}): {people}")
print(f"`in` rows ({len(ins)}): {ins}")
# ingest + check locate
p = Path("worlds/_diag_spine.world"); p.unlink(missing_ok=True); p.with_suffix(".meta.json").unlink(missing_ok=True)
w = _world(p, "_diag_spine", model=engine_tier_dispatch(prov), stance="fiction", title="diag")
w.ingestor.cursor.advance(1.0)
w.porcelain.ingest_structured(items)
print("--- locate() per person after ingest ---")
for e in people:
    print(f"  {e}: {w.porcelain.locate(e)}")
w.close(); p.unlink(missing_ok=True); p.with_suffix(".meta.json").unlink(missing_ok=True)
