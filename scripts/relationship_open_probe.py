"""Full-chain live probe for task #75 — relationship authoring → grounded open.

Targeted RESEED (no 35-min rebuild): copies the bodycase scenario to a fresh slot, reconstructs
the cast roster from meta, authors the player's standing relationships via the new build step, then
names the protagonist (Bradford Clemense / he-him) and renders the grounded cold open — proving the
present cast are now introduced as the player's OWN connection. ~2 Codex calls."""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

logging.basicConfig(level=logging.ERROR)

from construct import cohorts
from construct.arc import io as arc_io
from construct.adapter import PorcelainWorldReads
from construct.arc.executor import arc_protected_keys
from construct.cast import cast_from_proposal
from construct.game import (_world_digest, scenario_path, seed_player_relationships,
                            slot_path)
from construct.provider import CodexProvider
from construct.session import Session
from patternbuffer import World

SCEN = "bodycase"
PID = "rel_probe"
ts = int(time.time())
log = Path(f"logs/relationship-open-{ts}.md")
log.parent.mkdir(exist_ok=True)


def w(s: str) -> None:
    with log.open("a") as f:
        f.write(s + "\n")
    print(s, flush=True)


prov = CodexProvider()

src = scenario_path(SCEN)
meta = json.loads(src.with_suffix(".meta.json").read_text())
prot = meta["protagonist"]
cast_nodes, _ = cast_from_proposal(meta["cast"])

# Open the SESSION first — that opens the slot world WITH the model callable injected (a bare
# World has no model, so ingest durability-classification fails for new attrs). Then reseed the
# player relationships on that live world (the #75 build step), name the protagonist as the
# founder did, and render the grounded open.
_orig = cohorts.open_scene
cap = {}


def _spy(provider, briefing, protagonist, *, grounding=True):
    cap["brief"] = briefing
    return _orig(provider, briefing, protagonist, grounding=grounding)


cohorts.open_scene = _spy

s = Session.open(SCEN, player_id=PID, provider=prov, fresh=True)
reads = PorcelainWorldReads(s._world)
arc = arc_io.arc_from_frame(reads)
digest = _world_digest(s._world)
n = seed_player_relationships(s._world, prov, prot, cast_nodes, digest,
                              protected=arc_protected_keys(arc))
w(f"# Relationship authoring + grounded open — {SCEN}\n")
w(f"authored {n} player-relationship fact(s) into knows:{prot}\n")
w("## RELATIONSHIPS AUTHORED (knows:<prot>)\n")
for node in cast_nodes:
    if node.node_id.startswith("person:"):
        v = reads.state(prot, f"relationship_to_{node.node_id}", frame=f"knows:{prot}")
        w(f"- {node.node_id}: {v or '(none)'}")

s._world.porcelain.ingest_structured([
    {"entity": prot, "attribute": "name", "value": "Bradford Clemense"},
    {"entity": prot, "attribute": "pronouns", "value": "he/him"},
    {"entity": prot, "attribute": "background", "value": "his parents were murdered"},
])
opening = s.opening()
s.close()

w("\n## PRESENT-CAST BLOCK (from the assembled brief)\n")
brief = cap.get("brief", "")
inblock = False
for line in brief.splitlines():
    if line.startswith("PRESENT WITH YOU"):
        inblock = True
    elif inblock and line and not line.startswith(("-", " ")) and ":" not in line[:30]:
        inblock = False
    if inblock:
        w(line)

w("\n## RENDERED COLD OPEN\n")
w(opening + "\n")
w("\n--- END ---")
print("LOG:", log, flush=True)
