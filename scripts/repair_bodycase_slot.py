"""SURGICAL SLOT REPAIR (task #78 C, founder-approved shape, Cx 354/364):
retract the phantom `place:scene_of_the_crime`, place the player + Reed at the REAL crime
scene (place:bluegate_yard), and honor Maud/Nell's narrated departure from the briefing room
as departed_scene events. Leaves the ledger prose alone (the story knits forward).

DRY-RUN by default (prints the plan). Run with --apply to execute.
RUN ONLY WHILE THE BOT IS STOPPED (single-writer SQLite); reload the bot after."""
from __future__ import annotations

import sys

from patternbuffer import World

SLOT = "worlds/bodycase.telegram_8786956263.play.world"
APPLY = "--apply" in sys.argv
PHANTOM = "place:scene_of_the_crime"
YARD = "place:bluegate_yard"
PLAYER = "person:clara_vale"
REED = "person:edmund_reed"
BRIEFING = "place:briefing_room"

w = World(SLOT, world_id="w:bodycase", stance="fiction")
p = w.porcelain

# current max turn → the repair lands just after the latest played turn
turns = [r for r in w.buffer.visible(frame="session:main", attribute="kind")
         if r.entity.startswith("event:turn_") and "turn" in str(r.value)]
max_turn = max((int(r.entity.rsplit("_", 1)[-1]) for r in turns), default=0)
at = 1000.0 + max_turn + 0.5
print(f"latest turn: {max_turn}; repair valid_from={at}")

# 1. retract every visible phantom row (canon + player frame) — kills roster/refer pollution
phantom_rows = [r for frame in (None, f"knows:{PLAYER}")
                for r in w.buffer.visible(entity=PHANTOM, frame=frame)]
print(f"phantom rows to retract: {len(phantom_rows)}")
for r in phantom_rows:
    print(f"  retract {r.frame}:{r.attribute}={str(r.value)[:50]}")
    if APPLY:
        p.retract(r.id, "slot repair: phantom place minted by the pre-fix move channel")

# 2. player + Reed to the real crime scene (ordinary in rows; newer valid_from supersedes)
moves = [{"entity": e, "attribute": "in", "value": YARD, "value_type": "entity",
          "valid_from": at} for e in (PLAYER, REED)]
print(f"relocate: {PLAYER} + {REED} -> {YARD}")

# 3. Maud/Nell honestly departed the briefing room (their narrated exit never committed)
deps = []
for npc in ("person:maud_greaves", "person:nell_carter"):
    ev = f"event:departed_{npc.split(':', 1)[-1]}_repair{max_turn}"
    deps += [
        {"entity": ev, "attribute": "kind", "value": "departed_scene", "valid_from": at},
        {"entity": ev, "attribute": "agent", "value": npc, "value_type": "entity",
         "valid_from": at},
        {"entity": ev, "attribute": "patient", "value": BRIEFING, "value_type": "entity",
         "valid_from": at},
    ]
    print(f"departed_scene: {npc} left {BRIEFING}")

if APPLY:
    p.ingest_structured(moves + deps, classify="batch")
    print("APPLIED. Reload the bot; the next turn opens at Bluegate Yard with Reed.")
else:
    print("DRY RUN ONLY — rerun with --apply (bot stopped) to execute.")
w.close()
