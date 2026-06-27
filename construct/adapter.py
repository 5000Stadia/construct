"""PorcelainWorldReads — the one adapter class (letters 010/011/019).

Implements the narrow `WorldReads` protocol over the frozen
`world.porcelain` surface. Every method is a deterministic porcelain
read; nothing engine-shaped is reimplemented. This file is the entire
integration boundary on the read side.
"""

from __future__ import annotations

import logging
from typing import Any

from construct.arc.conditions import EventRow

logger = logging.getLogger(__name__)


class PorcelainWorldReads:
    """WorldReads over a pattern-buffer World's porcelain."""

    def __init__(self, world: Any, *, horizon: float | None = None) -> None:
        self._p = world.porcelain
        # AS-OF PLAY HORIZON (B' / Cx 253): when set, EVERY read materializes as-of this
        # coordinate — so beat/clock conditions and Located/InFrame/Occurred read the
        # current play horizon, never the timeline head (which is the source aftermath).
        # None = head = legacy behavior (single-timeframe / pre-horizon worlds).
        self._horizon = horizon

    def has_entity(self, entity: str) -> bool:
        # Every registered entity carries a kind row; locate covers
        # anchored-but-kindless edge cases.
        st = self._p.state(entity, "kind", as_of=self._horizon)
        if st["status"] in ("known", "conflicted"):
            return True
        return bool(self._p.locate(entity, as_of=self._horizon))

    def state(self, entity: str, attribute: str, *, frame: str = "canon") -> object:
        st = self._p.state(entity, attribute, frame=frame, as_of=self._horizon)
        if st["status"] == "known":
            return st["fact"]["value"]
        if st["status"] == "conflicted":
            # The engine's holding answer under an open TM flag. This is normally
            # silent — fine for ordinary facts, but DANGEROUS for the host-control
            # portfolio manifest: a conflicted `arc:portfolio` read silently serves
            # the stale arc (the EP2 bug, Cx 167). Surface it loudly so a future
            # mid-play writer that forgets to retract is caught (telemetry, not a fix).
            if entity == "arc:portfolio":
                logger.warning(
                    "CONFLICTED read on arc:portfolio.%s — serving the holding value %r; "
                    "a mid-play portfolio writer must retract the sealed rows before appending",
                    attribute, st["fact"]["value"])
            return st["fact"]["value"]
        return None  # unknown/frontier — INDETERMINATE to the atoms

    def location_chain(self, entity: str) -> list[str] | None:
        chain = self._p.locate(entity, as_of=self._horizon)
        if chain:
            return list(chain)
        return [] if self.has_entity(entity) else None

    def assertion_in_frame(self, frame: str, entity: str, attribute: str, value: object) -> bool:
        st = self._p.state(entity, attribute, frame=frame, as_of=self._horizon)
        return st["status"] in ("known", "conflicted") and st["fact"]["value"] == value

    def events(
        self,
        *,
        kind: str | None = None,
        participant: str | None = None,
        since: int | None = None,
        until: int | None = None,
        frame: str = "canon",
    ) -> list[EventRow]:
        # Horizon-bound the event read (Cx 253 §4: events() feeding conditions must not see
        # future source rows). Cap `until` at the play horizon when one is set.
        if self._horizon is not None:
            until = self._horizon if until is None else min(until, self._horizon)
        rows = self._p.events(
            kind=kind, participants=participant, since=since, until=until, frame=frame)
        return [
            EventRow(
                event_id=r["id"], kind=r["kind"],
                agents=tuple(r.get("agents", ())),
                patients=tuple(r.get("patients", ())),
                at=r.get("t"),
                caused_by=tuple(r.get("caused_by", ())),
            )
            for r in rows
        ]
