"""Construct — the engine that loads a pattern-buffer world into a
played, remembered holonovel.

This package is the HOST: turn loop, session zero, character engines, and
the arc layer. World truth lives in the engine (read-only reference at
/home/k/pattern-buffer); nothing engine-shaped is reimplemented here.

`Session` is the public play surface every interface (REPL, Discord bot,
future web/MCP) is a thin client of:

    from construct import Session
    s = Session.open("anchor", player_id="discord:42")
    print(s.turn("I look around").prose)
    s.close()
"""

from construct.session import Reply, Session, slot_exists

__all__ = ["Session", "Reply", "slot_exists"]
