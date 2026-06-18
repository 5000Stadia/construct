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
from construct.adapter import PorcelainWorldReads
from construct.turnloop import TurnTrace, run_turn, terminal_outcome

logger = logging.getLogger(__name__)


@dataclass
class Reply:
    """What a turn returns to any transport: the prose to show, and the
    trace for debug surfaces. `ok` is False only for a failed turn that
    the transport should surface without tearing the session down."""

    prose: str
    trace: TurnTrace | None
    ok: bool = True
    ended: bool = False  # the scenario reached its win/loss terminal (win_loss mode)


class Session:
    """An open holonovel for one player. Construct does all the model
    work inside `turn`; transports carry text in and out, nothing more."""

    def __init__(self, scenario: str, world: Any, arc: Any, meta: dict,
                 provider: Provider, player_id: str | None,
                 entry_as_of: float | None = None) -> None:
        self.scenario = scenario
        self.player_id = player_id
        self.entry_as_of = entry_as_of
        self._world = world
        self._arc = arc
        self._provider = provider
        self._scope = meta.get("arc_scope") or None
        self._mode = meta.get("mode", "pure")
        self._endless = bool(meta.get("endless", False))
        self._scenario_mode = meta.get("scenario_mode", "endless")  # win_loss terminates
        self._meta = meta
        self._closed = False

    @classmethod
    def open(cls, scenario: str, player_id: str | None = None,
             *, fresh: bool = False, provider: Provider | None = None,
             as_of: float | None = None) -> "Session":
        """Load or resume `scenario` for `player_id` (its own slot) and
        return a ready session. fresh=True restarts from the pristine
        scenario; otherwise it resumes where the player left off.

        `as_of` (ENTRY:WHERE, SESSION-ZERO design) is the timeline
        coordinate the player ENTERS at — the establishing view is
        materialized as-of t ("enter before the meter went dark"). It is
        recorded on the playthrough at fresh start and read back on
        resume; it governs the establishing entry, not ongoing turn
        stamping (turns run forward at TURN_EPOCH as ever)."""
        if provider is None:
            from construct.provider import CodexProvider
            provider = CodexProvider()
        start_playthrough(scenario, fresh=fresh, player_id=player_id)
        world, arc, meta = open_playthrough(scenario, provider, player_id=player_id)
        entry = _entry_as_of(world, requested=as_of, fresh=fresh)
        return cls(scenario, world, arc, meta, provider, player_id, entry_as_of=entry)

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

    def goal_statement(self) -> str | None:
        """The non-spoiling player-facing aim, shown only in win_loss mode.
        Freeplay/endless has no fixed aim, so this returns None there. The
        line is a leak-checked derivative authored at session-zero and
        sealed on the scenario meta (never a plot:/canon row)."""
        if self._scenario_mode != "win_loss":
            return None
        goal = self._meta.get("goal_statement")
        return str(goal) if goal else None

    def opening(self) -> str:
        """A deterministic entry banner — instant, no model call. When an
        entry coordinate is set, the establishing view is taken as-of it
        (the world at rest at that point on the timeline)."""
        where = self.location()
        line = f"You are {self.protagonist}" + (f", at {where}." if where else ".")
        head = f"{self.title}\n{line}"
        goal = self.goal_statement()
        if goal:
            head += f"\nYour aim: {goal}"
        est = self.establishing_lines()
        if self.entry_as_of is not None:
            head += f"\n(entering as of {self.entry_as_of:g})"
        if est:
            head += "\nThe world at rest:\n" + "\n".join(f"  {l}" for l in est)
        threads = self.live_threads()
        if threads:
            head += "\nThreads still live:\n" + "\n".join(f"  {t}" for t in threads)
        return head

    def live_threads(self, limit: int = 6) -> list[str]:
        """Re-entry awareness: the LIVE threads anchored to scope, via the
        `situation` lens (standing-truth ∪ live events, dead history dropped —
        PB SITUATION-LENS-V1, letter 058). Additive to the establishing set,
        which stays the tuned 'world at rest' cold-open. Fail-safe: with no
        `caused_by`-linked live events it returns empty, so a fresh/quiet world
        shows no section. Renders each live event by its alias or kind."""
        scope = self._scope
        if not scope:
            return []
        try:
            snap = self._world.porcelain.snapshot(
                sorted(scope), lens="situation", as_of=self.entry_as_of)
        except Exception:  # lens unsupported / read error — never break the open
            return []
        # The lens adds live EVENT rows on top of standing truth; surface those
        # as threads (alias preferred, else kind), one line per distinct event.
        threads: dict[str, str] = {}
        for f in snap.get("facts", []):
            e = f["entity"]
            if not e.startswith("event:"):
                continue
            if f["attribute"] == "alias":
                threads[e] = str(f["value"])
            elif f["attribute"] == "kind" and e not in threads:
                threads[e] = str(f["value"])
        return list(threads.values())[:limit]

    def establishing_lines(self, limit: int = 8) -> list[str]:
        """The establishing-set facts in scope, as of the entry
        coordinate — `materialize(establishing_set, as_of=t)`, the ENTRY
        design's literal shape. Deterministic; no model."""
        scope = self._scope
        if not scope:
            return []
        snap = self._world.porcelain.snapshot(
            sorted(scope), lens="establishing_set", as_of=self.entry_as_of)
        lines = [f"{f['entity']} · {f['attribute']} · {f['value']}"
                 for f in snap.get("facts", [])
                 if f["entity"] != self.protagonist]
        return lines[:limit]

    def turn(self, text: str) -> Reply:
        """Run exactly one player turn and persist it. Never raises for
        an in-world failure — returns ok=False with an honest message so
        a long-lived transport (REPL/bot) survives the turn."""
        if self._closed:
            raise RuntimeError("session is closed")
        # A win_loss scenario that already reached its terminal doesn't tick
        # again — the story is over. Don't re-render aftermath on every input.
        ended = terminal_outcome(PorcelainWorldReads(self._world))
        if ended:
            return Reply(prose=f"(The story has ended — you {ended}. "
                               f"Start fresh to play again.)", trace=None, ended=True)
        n = next_turn_number(self._world)
        try:
            result = run_turn(self._world, self._arc, self._provider, text, n,
                              scope=self._scope, mode=self._mode, endless=self._endless,
                              scenario_mode=self._scenario_mode)
        except Exception as exc:  # loud, but the session lives
            logger.exception("turn failed for %s/%s", self.scenario, self.player_id)
            return Reply(prose=f"(the turn could not complete: {exc})",
                         trace=None, ok=False)
        return Reply(prose=result.prose, trace=result.trace,
                     ended=bool(result.trace and result.trace.terminal))

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


_ENTRY = "event:entry"
_SESSION_FRAME = "session:main"


def _entry_as_of(world: Any, requested: float | None, fresh: bool) -> float | None:
    """Resolve the entry coordinate: on a fresh start, record the
    requested coordinate (if any) into the session frame; on resume,
    read back whatever was recorded. None = entered at the timeline head
    (current state). Stored as a session:main row so it's inspectable and
    survives across one-shot turns."""
    p = world.porcelain
    if fresh:
        if requested is not None:
            # Record the entry as an EVENT whose valid-time IS the
            # coordinate — read back via events() (the proven session:main
            # read path; state() doesn't fold no-valid-time frame rows).
            p.ingest_structured(
                [{"entity": _ENTRY, "attribute": "kind", "value": "entry",
                  "valid_from": float(requested)}],
                frame=_SESSION_FRAME)
        return requested
    for ev in p.events(kind="entry", frame=_SESSION_FRAME):
        t = ev.get("t")
        if t is not None:
            return float(t)
    return None
