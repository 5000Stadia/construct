"""B1 trace (task #78, Cx 354/360): WHERE did the narrated departures/accompaniment get lost?
Replays the live turn-14 prose through the SAME extract→resolve path settle uses, against a
copy of the founder's slot, and prints raw rows vs resolved rows vs receipts."""
from __future__ import annotations

import logging
import shutil

logging.basicConfig(level=logging.ERROR)

from construct.provider import CodexProvider, engine_callable
from construct.resolve import resolve_rows
from patternbuffer import World

shutil.copyfile("worlds/bodycase.telegram_8786956263.play.world", "/tmp/b1probe.world")
prov = CodexProvider()
w = World("/tmp/b1probe.world", world_id="w:bodycase", stance="fiction",
          model=engine_callable(prov, tier="cheap"))
p = w.porcelain

PROSE = (
    "Edmund Reed gives Maud and Nell a level look. “You heard John broalonamini. Keep to "
    "lit streets, and if any man troubles you over what you saw, come straight to St. Bride’s.” "
    "Maud nods once, grateful but guarded, and takes Nell out into the wet dark. Their steps fade "
    "through the shop-front, swallowed by the mutter of Ratcliff Highway and the hiss of rain in "
    "the gutter.\n\nReed turns to you. “Just so.” He leads you into the narrow back room "
    "behind the little shop and stops on the threshold rather than foul the floor."
)
SCENE = "place:briefing_room"
raw = p.extract(PROSE, scene=SCENE, extract="lean")
print("=== RAW EXTRACT (%d rows) ===" % len(raw))
for r in raw:
    print(" ", {k: r.get(k) for k in ("entity", "attribute", "value") if r.get(k) is not None})

cands = {"person:clara_vale", "person:maud_greaves", "person:nell_carter", "person:edmund_reed",
         "place:briefing_room", "place:bluegate_yard", "place:ratcliff_highway",
         "place:st_bride_bureau"}
names = {"person:maud_greaves": "Maud Greaves", "person:nell_carter": "Nell Carter",
         "person:edmund_reed": "Edmund Reed", "person:clara_vale": "John broalonamini"}
resolved, receipts = resolve_rows(raw, scene=cands, protagonist="person:clara_vale",
                                  name_of=lambda e: names.get(e, ""), allow_mint=True)
print("=== RESOLVED (%d rows) ===" % len(resolved))
for r in resolved:
    print(" ", {k: r.get(k) for k in ("entity", "attribute", "value") if r.get(k) is not None})
print("=== RECEIPTS ===")
for rc in receipts:
    print(" ", rc)
w.close()
