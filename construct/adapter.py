"""PorcelainWorldReads — the one adapter class (letters 010/011/019).

Implements the narrow `WorldReads` protocol over the frozen
`world.porcelain` surface. Every method is a deterministic porcelain
read; nothing engine-shaped is reimplemented. This file is the entire
integration boundary on the read side.
"""

from __future__ import annotations

import logging
from typing import Any

from construct import hostcontrol
from construct.arc.conditions import EventRow

logger = logging.getLogger(__name__)


def frame_facts(world: Any, frame: str, *, entity: str | None = None,
                attribute: str | None = None, prefix: str | None = None,
                as_of: float | None = None, include_meta: bool = False) -> list:
    """BOUNDED-READS take-up (PB 092): the porcelain `facts()` frame-scan,
    presented row-like (`.entity`/`.attribute`/`.value`/`.valid_from`) so the
    host's audited scan sites read the SAME shape they always did — receipt
    trails, knowledge digests, marker rows. This retires every direct
    `buffer.visible(...)` reach; folded truth still comes from
    `state`/`snapshot`, never from here."""
    from types import SimpleNamespace
    out = []
    for f in world.porcelain.facts(frame, entity=entity, attribute=attribute,
                                   prefix=prefix, as_of=as_of,
                                   include_meta=include_meta):
        valid = f.get("valid") or [None, None]
        out.append(SimpleNamespace(entity=f["entity"], attribute=f["attribute"],
                                   value=f["value"], valid_from=valid[0],
                                   valid_to=valid[1],
                                   id=(f.get("provenance") or {}).get("assertion_id")))
    return out


def state_value(porcelain: Any, entity: str, attribute: str,
                *, as_of: float | None = None) -> Any:
    """The bare canon value for (entity, attribute), or None: THE one host helper
    for a single-fact canon read (audit 2026-10 F1/July §5 — formerly three copies in
    foyer, clock and gauge).

    `porcelain.state` returns a structured `{status, fact:{value}}` dict; this unwraps
    it through `hostcontrol.collapse_state` (unknown/frontier -> None, known -> value,
    conflicted -> the holding value, loud on host-control keys). A porcelain that raises
    (a frontier/unknown entity) reads as absent.

    `as_of` (B' S3): materialize as-of the play horizon, so scene/imagery reads see the
    opening state, not the source aftermath. None (the default) = the timeline head, and
    the kwarg is then NOT passed, so a caller that never bound a horizon (clock) issues
    exactly the call it always did."""
    try:
        if as_of is None:
            st = porcelain.state(entity, attribute)
        else:
            st = porcelain.state(entity, attribute, as_of=as_of)
    except Exception:  # noqa: BLE001 — a frontier/unknown entity reads as absent
        return None
    return hostcontrol.collapse_state(st, entity, attribute)


class PorcelainWorldReads:
    """WorldReads over a pattern-buffer World's porcelain."""

    def __init__(self, world: Any, *, horizon: float | None = None) -> None:
        self._world = world
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
        # known → value; unknown → None; conflicted → the engine's holding answer
        # under an open TM flag, surfaced loudly for the whole host-control `arc:`
        # class (a conflicted read there = a mid-play writer that appended without
        # retracting — the EP2/Cx-167 stale-arc serve). One policy in hostcontrol.
        return hostcontrol.collapse_state(st, entity, attribute)

    def location_chain(self, entity: str) -> list[str] | None:
        chain = self._p.locate(entity, as_of=self._horizon)
        if chain:
            return list(chain)
        return [] if self.has_entity(entity) else None

    def assertion_in_frame(self, frame: str, entity: str, attribute: str, value: object) -> bool:
        st = self._p.state(entity, attribute, frame=frame, as_of=self._horizon)
        return st["status"] in ("known", "conflicted") and st["fact"]["value"] == value

    def frame_rows(self, frame: str, *, entity: str | None = None,
                  attribute: str | None = None, prefix: str | None = None,
                  include_meta: bool = False) -> list:
        """HORIZON-SAFE bounded frame scan (ITEM 1 / Cx 603).

        Calls the module-level ``frame_facts`` with this adapter's own
        ``self._horizon`` as the ``as_of`` ceiling, so callers never see
        assertions whose ``valid_from`` is in the player's future.  Pass
        ``entity``/``attribute``/``prefix`` to narrow the scan.

        Use this instead of reaching for ``self._world`` + a bare
        ``frame_facts`` call, which is a head scan and violates the adapter's
        load-bearing promise that every read materialises at the play horizon.
        """
        return frame_facts(
            self._world, frame,
            entity=entity, attribute=attribute, prefix=prefix,
            as_of=self._horizon, include_meta=include_meta,
        )

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
