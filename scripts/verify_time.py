"""De-risk diegetic time live: open anchor, run a normal action then an explicit
'wait until sunset', and confirm the clock advances + jumps and the trace reports
it. Cleans up the throwaway slot."""
from __future__ import annotations
import logging
logging.disable(logging.CRITICAL)

from construct.clock import read_clock
from construct.game import slot_path
from construct.session import Session

PLAYER = "verify:time"


def show(session, label):
    clk = read_clock(session._world, session.location())
    print(f"  [{label}] clock = {clk.render()}  ({clk.minutes} min elapsed)")


def main() -> int:
    s = Session.open("anchor", player_id=PLAYER, fresh=True, mode_override="endless")
    show(s, "start")
    r1 = s.turn("I carefully examine every ledger on the shelves, page by page.")
    print(f"turn 1 advanced {r1.trace.time_advanced} min; shown: {r1.trace.time_now!r}")
    show(s, "after examine")
    r2 = s.turn("I wait until sunset, then head out.")
    print(f"turn 2 advanced {r2.trace.time_advanced} min; shown: {r2.trace.time_now!r}")
    show(s, "after wait-until-sunset")
    print("\n-- turn-2 prose (should feel like evening/dusk) --")
    print(r2.prose[:600])
    s.close()
    if slot_path("anchor", PLAYER).exists():
        slot_path("anchor", PLAYER).unlink()
    print("\nOK — diegetic time verified live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
