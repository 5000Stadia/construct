"""The precondition atom grammar and its evaluation (ARC-LAYER §2.3).

Atoms are frozen dataclasses; `evaluate()` walks an expression against a
`WorldReads` source — the narrow, read-only protocol that is Holodeck's
half of the porcelain contract. Every method maps to a deterministic
engine read (state folds, containment walks, `what_happened` event
matches, frame membership); if this protocol ever wants something the
five porcelain verbs do not deterministically provide, that is a
[DECISION] letter to Kernos CC, never a stub-around (letter 010).

Evaluation semantics (ARC-LAYER §2.3, Codex r1 finding 2):
- `state` / `located`: TRUE/FALSE where the aspect is resolved;
  INDETERMINATE where it is an unresolved thunk, below the resolution
  floor, or an unknown entity. Negation never collapses unknown to false.
- `occurred`: definite both ways — fiction stance closes the world under
  the log; an event absent from canon did not happen.
- `in_frame` / `beat_achieved` / `clock_fired`: definite both ways — a
  frame's current fold is an enumerable set; arc bookkeeping is host-
  authored.
- Counter atoms (`turns_elapsed`, `turns_quiet`) evaluate against
  `PacingCounters` (folded from the session frame, §2.5); with no
  counters supplied they are INDETERMINATE.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Protocol, Union, runtime_checkable

from construct.arc.truth import Truth, t_all, t_any, t_at_least, t_not

#: Comparators a `Quantity` atom may use against a folded gauge total.
_QUANTITY_OPS = {
    ">=": operator.ge, ">": operator.gt, "<=": operator.le,
    "<": operator.lt, "==": operator.eq, "!=": operator.ne,
}


def _as_number(v: object) -> float | None:
    """Coerce a folded state value to float, or None if it is not numeric
    (an accrue total folds to int/float; defend against a stray string)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v))
    except (TypeError, ValueError):
        return None


class _Unresolved:
    """Sentinel: an aspect that exists as frontier — unresolved thunk,
    below the resolution floor, or underdetermined identity."""

    def __repr__(self) -> str:  # pragma: no cover
        return "UNRESOLVED"


UNRESOLVED = _Unresolved()


@dataclass(frozen=True)
class EventRow:
    """One event from the spine, in the letter-007 structured shape.

    `agents`/`patients` follow the binding authoring convention:
    entity-valued attributes on `event:` entities.
    """

    event_id: str
    kind: str
    agents: tuple[str, ...] = ()
    patients: tuple[str, ...] = ()
    at: int | None = None  # narrative-time coordinate (world-specific units)
    caused_by: tuple[str, ...] = ()


@runtime_checkable
class WorldReads(Protocol):
    """Read-only world access. Implemented by the porcelain adapter at
    integration; by static fixture folds in tests. Keep narrow."""

    def has_entity(self, entity: str) -> bool:
        """Entity is known to the world (registry / locatable)."""
        ...

    def state(self, entity: str, attribute: str, *, frame: str = "canon") -> object:
        """Current fold value for (entity, attribute, frame): the value,
        UNRESOLVED (frontier), or None (nothing asserted; in fiction an
        unreferenced aspect is frontier — callers treat None as
        UNRESOLVED unless the atom is definite-by-construction)."""
        ...

    def location_chain(self, entity: str) -> list[str] | None:
        """Containment chain, nearest first; None = entity unknown."""
        ...

    def assertion_in_frame(self, frame: str, entity: str, attribute: str, value: object) -> bool:
        """Membership in the frame's current (non-superseded,
        non-retracted) fold."""
        ...

    def events(
        self,
        *,
        kind: str | None = None,
        participant: str | None = None,
        since: int | None = None,
        until: int | None = None,
        frame: str = "canon",
    ) -> list[EventRow]:
        """Deterministic event-spine match (what_happened lens)."""
        ...


@dataclass(frozen=True)
class PacingCounters:
    """Folded from the session frame (ARC-LAYER §2.5): `turns_quiet`
    counts turns since the last beat achievement AND the last player
    interaction with any arc-referenced entity."""

    turns_elapsed: int
    turns_quiet: int


# --- atoms ---------------------------------------------------------------


@dataclass(frozen=True)
class StateIs:
    entity: str
    attribute: str
    value: object


@dataclass(frozen=True)
class Located:
    entity: str
    place: str


@dataclass(frozen=True)
class InFrame:
    frame: str
    entity: str
    attribute: str
    value: object


@dataclass(frozen=True)
class Occurred:
    kind: str
    participants: tuple[str, ...] = ()
    since: int | None = None
    until: int | None = None
    min_count: int = 1


@dataclass(frozen=True)
class BeatAchieved:
    beat_id: str
    plot_frame: str = "plot:main"


@dataclass(frozen=True)
class ClockFired:
    clock_id: str
    n: int = 1
    plot_frame: str = "plot:main"


@dataclass(frozen=True)
class TurnsElapsed:
    at_least: int


@dataclass(frozen=True)
class TurnsQuiet:
    at_least: int


@dataclass(frozen=True)
class Quantity:
    """A numeric-threshold atom (GAUGE-PRIMITIVE.md): TRUE when the folded
    `accrue` total on (entity, attribute) satisfies `op` against `value`. The
    one condition that lets a beat/clock/world_condition/refusal fire on a live
    GAUGE crossing a line — the continuous-constraint register (oxygen at 0,
    speed below 50, fuel dry). Reads the running total straight off `state()`
    (an accrue attribute folds its baseline+deltas into `fact.value`, exactly as
    `clock.read_clock` reads `elapsed_minutes`); no new porcelain surface — the
    engine already folds the number (PB ADOPTION §Numeric quantities).

    INDETERMINATE where the gauge is unknown/frontier or holds a non-number, so
    a gauge that was never seeded never spuriously trips a terminal."""

    entity: str
    attribute: str
    cmp: str  # ">=" | ">" | "<=" | "<" | "==" | "!="  (field name avoids the IO
    #          serialization envelope's own "op" key — io.expr_to_obj collision)
    value: float
    frame: str = "canon"


@dataclass(frozen=True)
class Not:
    operand: "Expr"


@dataclass(frozen=True)
class AllOf:
    operands: tuple["Expr", ...]


@dataclass(frozen=True)
class AnyOf:
    operands: tuple["Expr", ...]


@dataclass(frozen=True)
class AtLeast:
    k: int
    operands: tuple["Expr", ...]


Atom = Union[
    StateIs, Located, InFrame, Occurred, BeatAchieved, ClockFired,
    TurnsElapsed, TurnsQuiet, Quantity,
]
Expr = Union[Atom, Not, AllOf, AnyOf, AtLeast]

COUNTER_ATOMS = (TurnsElapsed, TurnsQuiet)


def atoms_of(expr: Expr) -> list[Atom]:
    """Flatten an expression to its atom leaves (lint walks this)."""
    if isinstance(expr, Not):
        return atoms_of(expr.operand)
    if isinstance(expr, (AllOf, AnyOf)):
        return [a for op in expr.operands for a in atoms_of(op)]
    if isinstance(expr, AtLeast):
        return [a for op in expr.operands for a in atoms_of(op)]
    return [expr]


def evaluate(
    expr: Expr,
    world: WorldReads,
    counters: PacingCounters | None = None,
) -> Truth:
    """Three-valued evaluation of a condition expression."""
    if isinstance(expr, Not):
        return t_not(evaluate(expr.operand, world, counters))
    if isinstance(expr, AllOf):
        return t_all(evaluate(op, world, counters) for op in expr.operands)
    if isinstance(expr, AnyOf):
        return t_any(evaluate(op, world, counters) for op in expr.operands)
    if isinstance(expr, AtLeast):
        return t_at_least(expr.k, [evaluate(op, world, counters) for op in expr.operands])

    if isinstance(expr, StateIs):
        if not world.has_entity(expr.entity):
            return Truth.INDETERMINATE
        value = world.state(expr.entity, expr.attribute)
        if value is UNRESOLVED or value is None:
            return Truth.INDETERMINATE
        return Truth.TRUE if value == expr.value else Truth.FALSE

    if isinstance(expr, Located):
        chain = world.location_chain(expr.entity)
        if chain is None:
            return Truth.INDETERMINATE
        return Truth.TRUE if expr.place in chain else Truth.FALSE

    if isinstance(expr, InFrame):
        present = world.assertion_in_frame(
            expr.frame, expr.entity, expr.attribute, expr.value
        )
        return Truth.TRUE if present else Truth.FALSE

    if isinstance(expr, Occurred):
        rows = world.events(kind=expr.kind, since=expr.since, until=expr.until)
        if expr.participants:
            wanted = set(expr.participants)
            rows = [
                r for r in rows
                if wanted.issubset(set(r.agents) | set(r.patients))
            ]
        return Truth.TRUE if len(rows) >= expr.min_count else Truth.FALSE

    if isinstance(expr, BeatAchieved):
        status = world.state(expr.beat_id, "status", frame=expr.plot_frame)
        return Truth.TRUE if status == "achieved" else Truth.FALSE

    if isinstance(expr, ClockFired):
        rows = world.events(kind="clock_fired", participant=None, frame=expr.plot_frame)
        count = sum(1 for r in rows if expr.clock_id in r.agents)
        return Truth.TRUE if count >= expr.n else Truth.FALSE

    if isinstance(expr, TurnsElapsed):
        if counters is None:
            return Truth.INDETERMINATE
        return Truth.TRUE if counters.turns_elapsed >= expr.at_least else Truth.FALSE

    if isinstance(expr, TurnsQuiet):
        if counters is None:
            return Truth.INDETERMINATE
        return Truth.TRUE if counters.turns_quiet >= expr.at_least else Truth.FALSE

    if isinstance(expr, Quantity):
        if not world.has_entity(expr.entity):
            return Truth.INDETERMINATE
        raw = world.state(expr.entity, expr.attribute, frame=expr.frame)
        if raw is UNRESOLVED or raw is None:
            return Truth.INDETERMINATE
        n = _as_number(raw)
        if n is None:
            return Truth.INDETERMINATE
        op = _QUANTITY_OPS.get(expr.cmp)
        if op is None:
            raise ValueError(f"Quantity: unknown comparator {expr.cmp!r}")
        return Truth.TRUE if op(n, float(expr.value)) else Truth.FALSE

    raise TypeError(f"unknown expression node: {expr!r}")
