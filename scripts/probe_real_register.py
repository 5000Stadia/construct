"""#103/#105 live probe: REAL-register domain respect. Build a courtroom
drama (A Few Good Men-shaped) on the laws layer; assert no metaphysical/delta
law ships; then two live turns — a grounded move and a physics-breaking one."""
import json, logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
from construct.game import create_scenario_from_generated
from construct.provider import CodexProvider

meta = create_scenario_from_generated(
    "probe_real_court", CodexProvider(),
    seed=("A military courtroom drama in 1992 Washington D.C., real world "
          "exactly as it was: a young Navy JAG lawyer defending two Marines "
          "for a hazing death their chain of command may have ordered. The "
          "informal code of the unit against the law of the land."),
    endless=False, play_as="the young defense lawyer",
    game_types=["courtroom_trial"], reality_register="real",
    on_stage=lambda m: print("STAGE:", m, flush=True))
print("SEALED:", meta.get("title"))
print("REALITY:", meta.get("reality_register"))
for l in meta.get("laws", []):
    print("LAW:", l["name"], "|", l["register"], "|", l["disclosure"])
registers = {l["register"] for l in meta.get("laws", [])}
assert not (registers & {"metaphysical", "delta"}), f"DOMAIN RESPECT FAILED: {registers}"
print("DOMAIN RESPECT: PASS (no metaphysical/delta in REAL register)")

from construct.session import Session
s = Session.open("probe_real_court", provider=CodexProvider(), player_id="probe")
r1 = s.turn("I review the autopsy file on the table before me.")
print("TURN1 tier:", r1.trace.adjudication if r1.trace else "?", "| ok:", r1.ok)
r2 = s.turn("I raise my hand and levitate the gavel off the judge's bench with my mind.")
print("TURN2 tier:", r2.trace.adjudication if r2.trace else "?")
print("TURN2 prose:", (r2.prose or "")[:300])
s.close()
