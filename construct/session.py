"""The public session API (letter 034).

One surface that every interface — the REPL, the Discord bot, a future
web/MCP client — is a thin client of. It is a small wrapper around the
SAME `run_turn` the one-shot CLI uses: no change to the turn loop,
cohorts, or engine. A session holds one open world for its lifetime and
persists every turn to the player's slot.

    session = Session.open("anchor", player_id="discord:42")
    reply = session.turn("I look around the council tier")
    print(reply.prose)
    session.close()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from construct.game import (
    next_turn_number,
    open_playthrough,
    slot_path,
    start_playthrough,
)
from construct.provider import Provider
from construct.turnloop import TurnTrace, run_turn

logger = logging.getLogger(__name__)


@dataclass
class Reply:
    """What a turn returns to any transport: the prose to show, and the
    trace for debug surfaces. `ok` is False only for a failed turn that
    the transport should surface without tearing the session down."""

    prose: str
    trace: TurnTrace | None
    ok: bool = True


class Session:
    """An open holonovel for one player. Construct does all the model
    work inside `turn`; transports carry text in and out, nothing more."""

    def __init__(self, scenario: str, world: Any, arc: Any, meta: dict,
                 provider: Provider, player_id: str | None) -> None:
        self.scenario = scenario
        self.player_id = player_id
        self._world = world
        self._arc = arc
        self._provider = provider
        self._scope = meta.get("arc_scope") or None
        self._mode = meta.get("mode", "pure")
        self._meta = meta
        self._closed = False

    @classmethod
    def open(cls, scenario: str, player_id: str | None = None,
             *, fresh: bool = False, provider: Provider | None = None) -> "Session":
        """Load or resume `scenario` for `player_id` (its own slot) and
        return a ready session. fresh=True restarts from the pristine
        scenario; otherwise it resumes where the player left off."""
        if provider is None:
            from construct.provider import CodexProvider
            provider = CodexProvider()
        start_playthrough(scenario, fresh=fresh, player_id=player_id)
        world, arc, meta = open_playthrough(scenario, provider, player_id=player_id)
        return cls(scenario, world, arc, meta, provider, player_id)

    @property
    def title(self) -> str:
        return self._meta.get("title", self.scenario)

    @property
    def protagonist(self) -> str:
        return self._arc.protagonist

    def location(self) -> str | None:
        """Current scene id (deterministic; no model call)."""
        chain = self._world.porcelain.locate(self._arc.protagonist)
        return chain[0] if chain else None

    def opening(self) -> str:
        """A deterministic entry banner — instant, no model call."""
        where = self.location()
        line = f"You are {self.protagonist}" + (f", at {where}." if where else ".")
        return f"{self.title}\n{line}"

    def turn(self, text: str) -> Reply:
        """Run exactly one player turn and persist it. Never raises for
        an in-world failure — returns ok=False with an honest message so
        a long-lived transport (REPL/bot) survives the turn."""
        if self._closed:
            raise RuntimeError("session is closed")
        n = next_turn_number(self._world)
        try:
            result = run_turn(self._world, self._arc, self._provider, text, n,
                              scope=self._scope, mode=self._mode)
        except Exception as exc:  # loud, but the session lives
            logger.exception("turn failed for %s/%s", self.scenario, self.player_id)
            return Reply(prose=f"(the turn could not complete: {exc})",
                         trace=None, ok=False)
        return Reply(prose=result.prose, trace=result.trace)

    def close(self) -> None:
        if not self._closed:
            self._world.close()
            self._closed = True

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def slot_exists(scenario: str, player_id: str | None = None) -> bool:
    return slot_path(scenario, player_id).exists()
