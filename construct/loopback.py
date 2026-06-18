"""The loopback transport — the offline self-test channel.

Structurally identical to the Telegram poller (same `TransportCore`, same
exactly-once `registry` bookkeeping) but its IO is two local JSONL files
instead of `getUpdates`/`sendMessage`. A developer (or an operator validating
a fresh setup) drives the FULL pipe — invite claim → /play → turn → chunked
reply — with no Telegram token and no network, by appending inbound lines and
reading the outbox.

Inbound line:  {"external_id": "u1", "chat_id": "u1", "text": "...", "update_id": 1}
Outbox line:   {"update_id": 1, "seq": 0, "chat_id": "u1", "text": "..."}

`pump` processes all currently-pending inbound lines once (dedup via the
registry, so re-reading the whole file is safe); `serve` loops it.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable

from construct import registry
from construct.transport_core import InboundEvent, TransportCore

logger = logging.getLogger(__name__)

PLATFORM = "loopback"
MSG_LIMIT = 4096  # match Telegram so chunking behaves identically


def _read_inbound(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("loopback: skipping malformed inbound line: %r", line[:80])
    return out


def _append(path: Path, obj: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(obj) + "\n")


def pump(conn, core: TransportCore, inbound_path: Path, outbox_path: Path,
         *, now_fn: Callable[[], float] = time.time) -> int:
    """Process all pending inbound lines once; return how many turns ran.
    Exactly-once: an update already in the registry is skipped, so a restart
    re-reading the whole inbound file never re-runs a turn."""
    ran = 0
    for e in _read_inbound(inbound_path):
        try:
            uid = int(e["update_id"])
        except (KeyError, ValueError, TypeError):
            continue
        if not registry.claim_update(conn, core._platform, uid):
            continue  # already processed (dedup across restarts)
        ev = InboundEvent(
            platform=core._platform, external_id=str(e["external_id"]),
            chat_id=str(e.get("chat_id", e["external_id"])),
            text=str(e.get("text", "")), update_ids=(uid,))
        out = core.handle(ev, now=now_fn())
        registry.record_outbox(conn, core._platform, uid, out.chat_id, out.chunks)
        for seq, ch in enumerate(out.chunks):
            _append(outbox_path, {"update_id": uid, "seq": seq,
                                  "chat_id": out.chat_id, "text": ch})
            registry.mark_sent(conn, core._platform, uid, seq)
        ran += 1
    return ran


def build_core(conn, *, session_factory=None, log_dir=None) -> TransportCore:
    return TransportCore(conn, platform=PLATFORM, msg_limit=MSG_LIMIT,
                         session_factory=session_factory, log_dir=log_dir)


def serve(inbound_path: str | Path, outbox_path: str | Path, registry_path: str | Path,
          *, poll: float = 0.5, session_factory=None) -> None:
    """Run the loopback loop (Ctrl-C to stop). Mirrors `telegram_bot.serve`."""
    inbound_path, outbox_path = Path(inbound_path), Path(outbox_path)
    conn = registry.connect(registry_path)
    core = build_core(conn, session_factory=session_factory)
    logger.info("loopback serving: in=%s out=%s", inbound_path, outbox_path)
    while True:
        try:
            pump(conn, core, inbound_path, outbox_path)
        except Exception:  # a bad turn must not kill the channel
            logger.exception("loopback pump error")
        time.sleep(poll)
