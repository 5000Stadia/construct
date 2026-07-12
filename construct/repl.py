"""The terminal transport — the Telegram experience at the local prompt.

`construct start` enters the SAME conversational session-zero every phone
player gets: the projector welcome, the emoji world shelf, natural-language
world picks, the describe-a-new-world interview, /help, /exit, /notebook —
because it IS the same machinery. Structurally identical to the Telegram
poller and the loopback channel (one `TransportCore`, one `registry`
bookkeeping path); only the IO differs: stdin lines in, stdout prose out.

The one deliberate divergence: NO INVITE GATE. The invite gate exists so a
public bot ignores strangers; the local terminal is the operator's own couch.
First contact mints and claims a code silently — and feeds it through the
ordinary claim path, so the first thing a new player sees is the genuine
Telegram welcome (image line, greeting, the world shelf), not a re-creation
of it.
"""

from __future__ import annotations

import getpass
import logging
import sys
import time

from construct import registry
from construct.transport_core import InboundEvent, TransportCore

logger = logging.getLogger(__name__)

PLATFORM = "cli"
#: A terminal has no message-size ceiling — one chunk per reply keeps prose whole.
MSG_LIMIT = 100_000


def _default_scenario() -> str:
    """The seed scenario for the silent first-contact claim (scope only —
    the start menu lets the player open any world from the shelf)."""
    try:
        from construct.game import list_scenarios
        rows = list_scenarios()
        return rows[0]["name"] if rows else "anchor"
    except Exception:  # noqa: BLE001 — an empty library still gets a menu
        return "anchor"


def serve(registry_path, *, session_factory=None,
          input_fn=input, out=print) -> None:
    """Run the terminal loop (Ctrl-C / Ctrl-D to leave; the game is saved
    every turn regardless). Mirrors `telegram_bot.serve`/`loopback.serve`."""
    conn = registry.connect(registry_path)

    def _notify(_chat_id: str, text: str) -> None:
        out(f"  · {text}")  # interim build/Atrium pings, as dim side notes

    def _photo(_chat_id: str, path: str, caption: str = "") -> None:
        line = f"  [scene image] {path}"
        if caption:
            line += f" — {caption}"
        out(line)

    core = TransportCore(conn, platform=PLATFORM, msg_limit=MSG_LIMIT,
                         session_factory=session_factory,
                         notify=_notify, photo=_photo)
    ext = getpass.getuser() or "local"

    _next_uid = [int(time.time() * 1000)]

    def _turn(text: str) -> None:
        # Exactly-once ids (cr: wall-time collides under fast/piped input and
        # a single ignored retry silently shadowed the event's outbox row):
        # a session-local monotonic counter, advanced UNTIL the claim
        # actually succeeds — every handled event owns a distinct processed
        # id and outbox row, same durable sequence as the other transports.
        uid = max(_next_uid[0], int(time.time() * 1000))
        while not registry.claim_update(conn, PLATFORM, uid):
            uid += 1
        _next_uid[0] = uid + 1
        ev = InboundEvent(platform=PLATFORM, external_id=ext, chat_id=ext,
                          text=text, update_ids=(uid,))
        outbound = core.handle(ev, now=time.time())
        registry.record_outbox(conn, PLATFORM, uid, outbound.chat_id,
                               outbound.chunks)
        for seq, chunk in enumerate(outbound.chunks):
            out("\n" + chunk)
            registry.mark_sent(conn, PLATFORM, uid, seq)
        core.settle(ev)  # post-send bookkeeping, same as the phone transports

    # First contact: mint + claim silently, THROUGH the ordinary claim path —
    # the reply is the genuine welcome (image, greeting, the world shelf).
    if registry.scenario_for(conn, PLATFORM, ext) is None:
        code = registry.mint_invite(conn, PLATFORM, _default_scenario(),
                                    now=time.time())
        _turn(code)
    else:
        _turn("/exit")  # returning player: step to the start menu / welcome

    while True:
        try:
            line = input_fn("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            out("\nSaved — pick it back up any time with `construct start`.")
            return
        if not line:
            continue
        if line.lower() in ("/quit", "quit", "exit()"):
            out("Saved — pick it back up any time with `construct start`.")
            return
        try:
            _turn(line)
        except Exception:  # noqa: BLE001 — a bad turn must not kill the channel
            logger.exception("terminal turn error")
            out("(that turn hit an error — it's logged; try again)")
