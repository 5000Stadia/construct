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

    def __init__(self, world: Any) -> None:
        self._p = world.porcelain

    def has_entity(self, entity: str) -> bool:
        # Every registered entity carries a kind row; locate covers
        # anchored-but-kindless edge cases.
        st = self._p.state(entity, "kind")
        if st["status"] in ("known", "conflicted"):
            return True
        return bool(self._p.locate(entity))

    def state(self, entity: str, attribute: str, *, frame: str = "canon") -> object:
        st = self._p.state(entity, attribute, frame=frame)
        if st["status"] == "known":
            return st["fact"]["value"]
        if st["status"] == "conflicted":
            # The engine's holding answer under an open TM flag.
            return st["fact"]["value"]
        return None  # unknown/frontier — INDETERMINATE to the atoms

    def location_chain(self, entity: str) -> list[str] | None:
        chain = self._p.locate(entity)
        if chain:
            return list(chain)
        return [] if self.has_entity(entity) else None

    def assertion_in_frame(self, frame: str, entity: str, attribute: str, value: object) -> bool:
        st = self._p.state(entity, attribute, frame=frame)
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
