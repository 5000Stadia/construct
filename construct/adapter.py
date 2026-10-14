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


def state_values(porcelain: Any, entity: str, attribute: str,
                 *, as_of: float | None = None) -> list:
    """Every member in force for a set-valued key (a person's `role`, PERSON-ROLES-V1),
    or [] when none is. `state_value` serves only the fold's winner (the most recent
    member by valid time), which can hide an older member that still holds; this reads
    the engine's `values`. A key that is not set-valued falls back to its one value."""
    try:
        if as_of is None:
            st = porcelain.state(entity, attribute)
        else:
            st = porcelain.state(entity, attribute, as_of=as_of)
    except Exception:  # noqa: BLE001 — a frontier/unknown entity reads as absent
        return []
    if not isinstance(st, dict) or st.get("status") not in ("known", "conflicted"):
        return []
    if st.get("values"):
        return [f.get("value") for f in st["values"] if f.get("value") is not None]
    one = hostcontrol.collapse_state(st, entity, attribute)
    return [] if one is None else [one]


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
                # a story event the extractor wrote with no kind row has kind None (pb R22
                # surfaces two); every reader gets a string, "" meaning untyped
                event_id=r["id"], kind=r.get("kind") or "",
                agents=tuple(r.get("agents", ())),
                patients=tuple(r.get("patients", ())),
                at=r.get("t"),
                caused_by=tuple(r.get("caused_by", ())),
            )
            for r in rows
        ]


# ---- READS AT THE PLAY HORIZON (docs/design/READS-AT-PLAY-HORIZON.md r6) -------------------

def play_horizon(opening_as_of: float | None, next_source_as_of: float | None,
                 turns: int) -> float | None:
    """The play horizon after `turns` turns: `opening_as_of + turns`, capped strictly below
    the next source coordinate (Cx 253 §1), or None for a legacy world (head reads). The one
    rule `Session._horizon` and `continue_episode` share, so the two can't drift."""
    if opening_as_of is None:
        return None
    h = float(opening_as_of) + float(turns)
    if next_source_as_of is not None:
        h = min(h, float(next_source_as_of) - 1.0)
    return h


#: Porcelain valid-time reads: every public method whose (pinned) signature takes `as_of`.
#: Through a HorizonView their `as_of` is set to the horizon when absent or None, and
#: clamped to it when later.
PORCELAIN_VALID_TIME_READS = frozenset({
    "aggregate", "ask", "composition", "confidence", "contents", "correlation_conflicts",
    "correlations", "entities", "facts", "features", "fidelity_audit", "frame_diff",
    "in_transit", "locate", "neighborhood", "path", "refer", "route", "salience",
    "snapshot", "state", "state_union", "where", "who_knows",
})
#: `events` takes no `as_of`: its `until` is capped at the horizon instead.
PORCELAIN_EVENT_READS = frozenset({"events"})
#: Writes, and the asserted-axis / identity reads that have no valid-time coordinate.
PORCELAIN_PASSTHROUGH = frozenset({
    "abort_build", "adjudicate_deferred", "axis_heads", "begin_build", "build",
    "canonical_attribute", "closure", "commit_set", "confirm", "continue_frame",
    "correlate", "distinct_between", "extract", "identity_conflicts", "ingest",
    "ingest_structured", "merge", "merge_gate", "proposals", "reconcile", "reject",
    "resolve", "retract", "retype", "seal_build", "typing_conflicts",
})
#: The World members a HorizonView exposes; every other World attribute is denied.
WORLD_EXPOSED = frozenset({"porcelain", "refer", "close", "head"})

_DENIED = ("not available through the horizon view; read via view.porcelain, "
           "or view.head for an id-collision check")


def _bind_as_of(fn: Any, horizon: float, args: tuple, kwargs: dict) -> tuple[tuple, dict]:
    """Return (args, kwargs) with `as_of` set to the horizon when absent/None, clamped to it
    when later. Handles `as_of` passed positionally."""
    import inspect
    try:
        sig = inspect.signature(fn)
        if "as_of" not in sig.parameters:
            raise TypeError("no named as_of parameter")
        bound = sig.bind_partial(*args, **kwargs)
    except (TypeError, ValueError):
        kwargs = dict(kwargs)
        cur = kwargs.get("as_of")
        kwargs["as_of"] = horizon if cur is None else min(float(cur), horizon)
        return args, kwargs
    cur = bound.arguments.get("as_of")
    new = horizon if cur is None else min(float(cur), horizon)
    if cur is not None and new != cur:
        logger.debug("horizon view: as_of %s clamped to %s", cur, new)
    bound.arguments["as_of"] = new
    return bound.args, bound.kwargs


class _HorizonPorcelain:
    """The porcelain proxy of a HorizonView. Deny by default: a public method in none of the
    three classes raises AttributeError, so an engine bump can't slip a head read through."""

    def __init__(self, porcelain: Any, horizon: Any) -> None:
        self._p = porcelain
        self._h = horizon          # zero-arg callable → float, re-evaluated on every read

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._p, name)
        if name in PORCELAIN_VALID_TIME_READS:
            def read(*args: Any, **kwargs: Any) -> Any:
                args, kwargs = _bind_as_of(target, self._h(), args, kwargs)
                return target(*args, **kwargs)
            return read
        if name in PORCELAIN_EVENT_READS:
            def events(*args: Any, **kwargs: Any) -> Any:
                import inspect
                bound = inspect.signature(target).bind_partial(*args, **kwargs)
                h = self._h()
                cur = bound.arguments.get("until")
                bound.arguments["until"] = h if cur is None else min(float(cur), h)
                return target(*bound.args, **bound.kwargs)
            return events
        if name in PORCELAIN_PASSTHROUGH or name.startswith("_"):
            return target
        raise AttributeError(f"porcelain.{name}: {_DENIED}")


class HorizonView:
    """A play-time view of a World that reads at the play horizon by construction.

    `HorizonView(world, horizon)` returns the RAW world when `horizon` is None, or a
    callable whose one construction-time probe returns None (a legacy world: byte-identical
    behaviour). Otherwise it keeps the callable (a float is wrapped as a constant) and calls
    it afresh on every mediated read, so a Session's horizon advances with its turns. The
    callable must read through `view.head`, never the view.

    Exposes exactly `porcelain` (the proxy), `refer` (a valid-time read), `close` and
    `head` (the raw world: id-collision checks only). Every other World member is denied."""

    def __new__(cls, world: Any, horizon: Any = None) -> Any:
        if isinstance(world, HorizonView):
            world = world.head
        if horizon is None:
            return world
        if callable(horizon) and horizon() is None:   # the legacy probe, never cached
            return world
        return super().__new__(cls)

    def __init__(self, world: Any, horizon: Any = None) -> None:
        if isinstance(world, HorizonView):
            world = world.head
        fn = horizon if callable(horizon) else (lambda h=float(horizon): h)
        object.__setattr__(self, "head", world)
        object.__setattr__(self, "_h", fn)
        object.__setattr__(self, "porcelain", _HorizonPorcelain(world.porcelain, fn))

    def horizon(self) -> float:
        """The horizon now (re-evaluated)."""
        return self._h()

    def refer(self, *args: Any, **kwargs: Any) -> Any:
        target = self.head.refer
        args, kwargs = _bind_as_of(target, self._h(), args, kwargs)
        return target(*args, **kwargs)

    def close(self) -> Any:
        return self.head.close()

    def __getattr__(self, name: str) -> Any:   # only reached for names not defined above
        raise AttributeError(f"world.{name}: {_DENIED}")


def raw_world(world: Any) -> Any:
    """The raw World under a HorizonView (or the world itself). For id-collision checks
    and the horizon computation only."""
    return world.head if isinstance(world, HorizonView) else world


def is_future_only(world: Any, entity: str) -> bool:
    """THE IDENTITY RULE (READS-AT-PLAY-HORIZON): an id that exists at the timeline head but
    not at the view's horizon belongs to the hidden story's future. A play-time write must
    neither reuse it nor write onto it. Always False on a raw (legacy) world."""
    if not isinstance(world, HorizonView) or not entity:
        return False
    try:
        return (PorcelainWorldReads(world.head).has_entity(entity)
                and not PorcelainWorldReads(world).has_entity(entity))
    except Exception:  # noqa: BLE001 — an unreadable check never blocks; it never reuses
        logger.warning("future-only check failed for %s", entity, exc_info=True)
        return False


def next_free_id(world: Any, entity: str) -> str:
    """The next `<id>_<n>` free at the timeline HEAD (global id-collision avoidance)."""
    head = PorcelainWorldReads(raw_world(world))
    n = 1
    while head.has_entity(f"{entity}_{n}"):
        n += 1
    return f"{entity}_{n}"
