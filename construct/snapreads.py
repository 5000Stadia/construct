"""SnapshotReads — WorldReads over cached snapshot payloads.

At play-world scale the engine's per-key reads each pay a full log
deserialization (measured: ~2-3s per state() fold at ~1300 rows; profile
to PB). The turn loop therefore takes a FEW materializations and
evaluates the many per-atom reads against them — one rendered view, not
N point reads (the Cognitive-UI discipline applied to the host's own
read pattern). The cache is per-turn, disposable, never stored.

Frames included in the cache are definite; anything outside the cached
scope answers None/unknown — callers keep three-valued honesty.
"""

from __future__ import annotations

from construct.arc.conditions import EventRow


class SnapshotReads:
    """WorldReads over {frame: snapshot_dict} caches + an events source."""

    def __init__(self, snaps: dict[str, dict], events_fn=None) -> None:
        self._facts: dict[str, dict[tuple[str, str], object]] = {}
        self._entities: set[str] = set()
        for frame, snap in snaps.items():
            table = {}
            for f in snap.get("facts", []):
                table[(f["entity"], f["attribute"])] = f["value"]
                self._entities.add(f["entity"])
            self._facts[frame] = table
        self._events_fn = events_fn

    def has_entity(self, entity: str) -> bool:
        return entity in self._entities

    def state(self, entity: str, attribute: str, *, frame: str = "canon") -> object:
        return self._facts.get(frame, {}).get((entity, attribute))

    def location_chain(self, entity: str) -> list[str] | None:
        chain: list[str] = []
        current = entity
        canon = self._facts.get("canon", {})
        for _ in range(16):  # containment depth bound
            parent = canon.get((current, "in"))
            if not isinstance(parent, str):
                break
            chain.append(parent)
            current = parent
        if chain:
            return chain
        return [] if self.has_entity(entity) else None

    def assertion_in_frame(self, frame: str, entity: str, attribute: str, value: object) -> bool:
        return self._facts.get(frame, {}).get((entity, attribute)) == value

    def events(self, *, kind=None, participant=None, since=None, until=None,
               frame: str = "canon") -> list[EventRow]:
        if self._events_fn is None:
            return []
        return self._events_fn(kind=kind, participant=participant,
                               since=since, until=until, frame=frame)
