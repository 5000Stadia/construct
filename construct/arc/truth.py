"""Three-valued truth for arc-condition evaluation (ARC-LAYER §2.3).

An atom whose referent is an unresolved thunk, below the resolution
floor, or an underdetermined identity evaluates INDETERMINATE — and
INDETERMINATE satisfies neither `achievable_via` nor `unreachable_if`.
Negation never collapses unknown into false.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable


class Truth(enum.Enum):
    TRUE = "true"
    FALSE = "false"
    INDETERMINATE = "indeterminate"


def t_not(value: Truth) -> Truth:
    if value is Truth.TRUE:
        return Truth.FALSE
    if value is Truth.FALSE:
        return Truth.TRUE
    return Truth.INDETERMINATE


def t_all(values: Iterable[Truth]) -> Truth:
    """Conjunction: FALSE dominates, then INDETERMINATE; empty = TRUE."""
    result = Truth.TRUE
    for value in values:
        if value is Truth.FALSE:
            return Truth.FALSE
        if value is Truth.INDETERMINATE:
            result = Truth.INDETERMINATE
    return result


def t_any(values: Iterable[Truth]) -> Truth:
    """Disjunction: TRUE dominates, then INDETERMINATE; empty = FALSE."""
    result = Truth.FALSE
    for value in values:
        if value is Truth.TRUE:
            return Truth.TRUE
        if value is Truth.INDETERMINATE:
            result = Truth.INDETERMINATE
    return result


def t_at_least(k: int, values: Iterable[Truth]) -> Truth:
    """Sufficiency set: TRUE when k members are TRUE; FALSE when even
    counting every INDETERMINATE as TRUE cannot reach k."""
    vals = list(values)
    true_count = sum(1 for v in vals if v is Truth.TRUE)
    open_count = sum(1 for v in vals if v is Truth.INDETERMINATE)
    if true_count >= k:
        return Truth.TRUE
    if true_count + open_count < k:
        return Truth.FALSE
    return Truth.INDETERMINATE
