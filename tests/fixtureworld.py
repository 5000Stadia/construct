"""FixtureWorld: a static implementation of WorldReads for tests.

Fixtures ARE folds (letter 010): static dicts, no supersession logic,
nothing engine-shaped reimplemented. Hand-author the folded state a
world would serve; the tests exercise arc logic against it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from holodeck.arc.conditions import EventRow


@dataclass
class FixtureWorld:
    entities: set[str] = field(default_factory=set)
    # (frame, entity, attribute) -> value (use UNRESOLVED for frontier)
    states: dict[tuple[str, str, str], object] = field(default_factory=dict)
    # entity -> containment chain, nearest first
    chains: dict[str, list[str]] = field(default_factory=dict)
    # frame -> set of (entity, attribute, value) in the current fold
    frames: dict[str, set[tuple[str, str, object]]] = field(default_factory=dict)
    # (frame) -> list of EventRow
    event_log: dict[str, list[EventRow]] = field(default_factory=dict)

    def has_entity(self, entity: str) -> bool:
        return entity in self.entities

    def state(self, entity: str, attribute: str, *, frame: str = "canon") -> object:
        return self.states.get((frame, entity, attribute))

    def location_chain(self, entity: str) -> list[str] | None:
        return self.chains.get(entity)

    def assertion_in_frame(self, frame: str, entity: str, attribute: str, value: object) -> bool:
        return (entity, attribute, value) in self.frames.get(frame, set())

    def events(self, *, kind=None, participant=None, since=None, until=None,
               frame: str = "canon") -> list[EventRow]:
        rows = self.event_log.get(frame, [])
        out = []
        for r in rows:
            if kind is not None and r.kind != kind:
                continue
            if participant is not None and participant not in (r.agents + r.patients):
                continue
            if since is not None and (r.at is None or r.at < since):
                continue
            if until is not None and (r.at is None or r.at > until):
                continue
            out.append(r)
        return out
