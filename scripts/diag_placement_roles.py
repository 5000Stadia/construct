"""Test the present-cast hypothesis: does interview_world place an ANTAGONIST co-located with the
protagonist in the opening scene? Call it on a heist brief, ingest, and dump each person's role +
location + whether co-located with the protagonist's opening place."""
import logging; logging.basicConfig(level=logging.ERROR)
from construct import cohorts
from construct.provider import CodexProvider
from construct.game import _world, scenario_path, engine_tier_dispatch
from construct.foyer import state_value
from pathlib import Path
prov=CodexProvider()
brief="A small crew has one night to lift a guarded relic from a glittering, well-watched vault; a warden hunts the thieves."
spine=cohorts.interview_world(prov, brief, play_as="the crew's planner")
items=spine.get("items",[])
p=Path("worlds/_diag_place.world"); p.unlink(missing_ok=True); p.with_suffix(".meta.json").unlink(missing_ok=True)
w=_world(p,"_diag_place",model=engine_tier_dispatch(prov),stance="fiction",title="diag")
w.ingestor.cursor.advance(1.0); w.porcelain.ingest_structured(items)
# guess protagonist: the planner — first person with role containing 'planner'/'crew' or play_as
people=sorted({it['entity'] for it in items if str(it.get('entity','')).startswith('person:')})
def loc(e):
    c=w.porcelain.locate(e); return c[0] if c else None
# find protagonist's place (the one whose role looks like the planner)
roles={e:(state_value(w.porcelain,e,'role') or '') for e in people}
proto=next((e for e,r in roles.items() if any(k in r.lower() for k in ('plan','crew','protagonist','thief','lead'))), people[0] if people else None)
pscene=loc(proto) if proto else None
print(f"protagonist guess: {proto} (role={roles.get(proto)!r}) @ {pscene}\n")
print("person | role | location | CO-LOCATED with protagonist?")
for e in people:
    l=loc(e); co = (l==pscene and e!=proto)
    flag = "  <-- co-located" if co else ""
    print(f"  {e} | {roles.get(e)!r} | {l}{flag}")
w.close(); p.unlink(missing_ok=True); p.with_suffix(".meta.json").unlink(missing_ok=True)
