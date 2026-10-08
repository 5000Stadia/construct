"""Property test for the single annotated evaluator (audit-2026-10 arc F4).

Before `conditions.explain` replaced drift.py's three inline copies of the
three-valued truth table, the OLD copies are kept here VERBATIM (renamed
`_ref_*`) as the reference. Randomized expressions over randomized fake reads
are run through each old copy and through the new fold, and must agree
exactly: the witness leaf lists (kind/key/entity/firing_event, in order), the
whole closure witness, the clock-necessity probe, and the polarity-aware
driving entities for every `want`. Also checks `explain(...).verdict ==
evaluate(...)` (with and without pacing counters).

Semantics the old copies shared (and the new fold preserves):
- Not: TRUE<->FALSE, INDETERMINATE stays INDETERMINATE.
- AtLeast: TRUE when trues >= k; INDETERMINATE when trues + indeterminates >= k
  (INDETERMINATE counts as a *possible* true); else FALSE. (= truth.t_at_least)
- AllOf/AnyOf: FALSE/TRUE dominates, then INDETERMINATE; empty AllOf TRUE,
  empty AnyOf FALSE. (= truth.t_all / t_any)
- All three copies evaluate with counters=None, so counter atoms are
  INDETERMINATE inside the witness; all visit EVERY operand (no
  short-circuit), so every leaf is annotated.
"""

from __future__ import annotations

import random
from typing import Any

from construct.arc.conditions import (
    UNRESOLVED, AllOf, AnyOf, AtLeast, BeatAchieved, ClockFired, EventRow, Expr,
    InFrame, Located, Not, Occurred, PacingCounters, Quantity, StateIs,
    TurnsElapsed, TurnsQuiet, evaluate, explain,
)
from construct.arc.drift import (
    _clock_firing_event, _driving_entities, _forcing_clocks_false, _leaf_key,
    _witness_leaves, closure_witness_of,
)
from construct.arc.truth import Truth

# ---------------------------------------------------------------------------
# REFERENCE: the three pre-refactor copies from construct/arc/drift.py (HEAD
# before the F4 refactor), verbatim apart from the `_ref_` rename.
# ---------------------------------------------------------------------------

def _ref_true_leaves(expr: Expr, reads: Any, out_true: list, out_unknown: list,
                 out_false: list) -> Truth:
    """Walk `expr` recording the DECIDING leaves per shape (§2): AnyOf records
    its TRUE branches' leaves; AllOf all leaves; AtLeast the satisfied leaves;
    Not records the negated subtree's evaluation (cr D2 finding 5: a FALSE
    leaf under a Not is what MADE the Not true — it persists in
    `false_leaves`, so a `Not(StateIs(...))` closure witness is never empty).
    UNKNOWN/INDETERMINATE atoms are recorded as UNKNOWN wherever encountered.
    Returns the node's own three-valued truth (identical to `evaluate` — the
    walk IS an evaluation, just one that remembers)."""
    if isinstance(expr, Not):
        # the child's leaves record under their OWN truth; the flip is above them
        v = _ref_true_leaves(expr.operand, reads, out_true, out_unknown, out_false)
        return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE}.get(
            v, Truth.INDETERMINATE)
    if isinstance(expr, (AllOf, AnyOf, AtLeast)):
        verdicts = [_ref_true_leaves(op, reads, out_true, out_unknown, out_false)
                    for op in expr.operands]
        if isinstance(expr, AllOf):
            if any(v is Truth.FALSE for v in verdicts):
                return Truth.FALSE
            if any(v is Truth.INDETERMINATE for v in verdicts):
                return Truth.INDETERMINATE
            return Truth.TRUE
        if isinstance(expr, AnyOf):
            if any(v is Truth.TRUE for v in verdicts):
                return Truth.TRUE
            if any(v is Truth.INDETERMINATE for v in verdicts):
                return Truth.INDETERMINATE
            return Truth.FALSE
        trues = sum(1 for v in verdicts if v is Truth.TRUE)
        unknowns = sum(1 for v in verdicts if v is Truth.INDETERMINATE)
        if trues >= expr.k:
            return Truth.TRUE
        if trues + unknowns >= expr.k:
            return Truth.INDETERMINATE
        return Truth.FALSE
    # an atom leaf: evaluate it once and remember where it landed.
    verdict = evaluate(expr, reads)
    leaf: dict = {"kind": type(expr).__name__, "key": _leaf_key(expr)}
    if getattr(expr, "entity", None):
        # the addressed entity, machine-readable (cr round-3 blocker 2: a
        # holder named by a TRUE D-HARD leaf cannot prove an alternative road)
        leaf["entity"] = expr.entity
    if verdict is Truth.TRUE:
        if isinstance(expr, ClockFired):
            leaf["clock_id"] = expr.clock_id
            leaf["firing_event"] = _clock_firing_event(reads, expr)
        out_true.append(leaf)
    elif verdict is Truth.INDETERMINATE:
        out_unknown.append(leaf)
    else:
        out_false.append(leaf)  # persists the Not-negated subtree (finding 5)
    return verdict


def _ref_clocks_false(expr: Expr, reads: Any) -> Truth:
    """`evaluate` with every ClockFired leaf FORCED FALSE — the clock-necessity
    probe (§2): if the closure still stands without any clock, the clock was
    incidental and the closure is NOT clock-caused."""
    if isinstance(expr, ClockFired):
        return Truth.FALSE
    if isinstance(expr, Not):
        v = _ref_clocks_false(expr.operand, reads)
        return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE}.get(
            v, Truth.INDETERMINATE)
    if isinstance(expr, AllOf):
        vs = [_ref_clocks_false(op, reads) for op in expr.operands]
        if any(v is Truth.FALSE for v in vs):
            return Truth.FALSE
        if any(v is Truth.INDETERMINATE for v in vs):
            return Truth.INDETERMINATE
        return Truth.TRUE
    if isinstance(expr, AnyOf):
        vs = [_ref_clocks_false(op, reads) for op in expr.operands]
        if any(v is Truth.TRUE for v in vs):
            return Truth.TRUE
        if any(v is Truth.INDETERMINATE for v in vs):
            return Truth.INDETERMINATE
        return Truth.FALSE
    if isinstance(expr, AtLeast):
        vs = [_ref_clocks_false(op, reads) for op in expr.operands]
        trues = sum(1 for v in vs if v is Truth.TRUE)
        unknowns = sum(1 for v in vs if v is Truth.INDETERMINATE)
        if trues >= expr.k:
            return Truth.TRUE
        if trues + unknowns >= expr.k:
            return Truth.INDETERMINATE
        return Truth.FALSE
    return evaluate(expr, reads)


def _ref_driving_entities(expr: Expr, reads: Any, want: Truth) -> set[str]:
    """The entities whose leaves PARTICIPATE IN PROVING `evaluate(expr) is
    want` — polarity-aware (cr round-4 blocker 1: a TRUE `Not(StateIs(...))`
    closure is driven by its FALSE child leaf; unioning all false leaves
    would over-invalidate compound shapes where many FALSE branches are
    non-deciding). Shape semantics mirror the witness walker's:

    - Not flips the wanted polarity onto its child;
    - AllOf proving TRUE: every operand participates; proving FALSE: only
      the FALSE operands (the deciders);
    - AnyOf proving TRUE: only the TRUE operands; proving FALSE: every
      operand (all had to be false);
    - AtLeast proving TRUE: the satisfied operands; proving FALSE: the
      unsatisfied ones.

    Returns the addressed entities of the participating atoms; empty when
    the expression does not in fact evaluate to `want`."""
    flip = {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE}
    if isinstance(expr, Not):
        return _ref_driving_entities(expr.operand, reads, flip.get(want, want))
    if isinstance(expr, (AllOf, AnyOf, AtLeast)):
        out: set[str] = set()
        for op in expr.operands:
            v = evaluate(op, reads)
            if isinstance(expr, AllOf):
                take = (want is Truth.TRUE) or (v is Truth.FALSE)
            elif isinstance(expr, AnyOf):
                take = (want is Truth.FALSE) or (v is Truth.TRUE)
            else:  # AtLeast
                take = v is want
            if take:
                # in every take-branch the child's contributing verdict IS
                # the wanted polarity (AllOf-TRUE: all children TRUE;
                # AllOf-FALSE: the FALSE deciders; AnyOf mirrored; AtLeast
                # by construction) — so the want passes through unchanged.
                out |= _ref_driving_entities(op, reads, want)
        return out
    # atom: participates iff it actually evaluates to the wanted polarity
    if evaluate(expr, reads) is want and getattr(expr, "entity", None):
        return {expr.entity}
    return set()


def _ref_closure_witness_of(unreachable_if: Expr, reads: Any, turn: int) -> dict:
    """The closure witness (§2), computed AT CLOSE TIME against the SAME reads
    that closed the beat — later classification never re-evaluates a moved
    world. Records: the deciding TRUE leaves (per-shape semantics), UNKNOWN
    leaves, each TRUE ClockFired leaf's exact causal firing-event id, and the
    clock-NECESSITY verdict (`clock_caused`: TRUE ClockFired present AND the
    expression with every clock leaf forced FALSE no longer evaluates TRUE)."""
    out_true: list = []
    out_unknown: list = []
    out_false: list = []
    _ref_true_leaves(unreachable_if, reads, out_true, out_unknown, out_false)
    has_true_clock = any(l.get("kind") == "ClockFired" for l in out_true)
    clock_caused = bool(
        has_true_clock
        and _ref_clocks_false(unreachable_if, reads) is not Truth.TRUE)
    return {
        "true_leaves": out_true,
        "unknown_leaves": out_unknown,
        "false_leaves": out_false,
        # the polarity-aware invalidation set (cr round-4 blocker 1): the
        # entities whose leaves PROVED the closure, whatever their sign —
        # a dead holder cannot carry the clue past his own death even when
        # his death registered as a FALSE leaf under a Not.
        "driving_entities": sorted(
            _ref_driving_entities(unreachable_if, reads, Truth.TRUE)),
        "clock_caused": clock_caused,
        "firing_events": [l["firing_event"] for l in out_true
                          if l.get("kind") == "ClockFired"
                          and l.get("firing_event")],
        "turn": turn,
    }


# ---------------------------------------------------------------------------
# Randomized worlds and expressions
# ---------------------------------------------------------------------------

_ENTITIES = ("person:a", "person:b", "item:c", "place:d", "")
_ATTRS = ("role", "fuel")
_STATE_VALUES = (UNRESOLVED, None, 1, 2, "x", 3.5, "7", True)
_PLACES = ("place:d", "place:e", "place:f")
_CLOCKS = ("clock:c0", "clock:c1", "clock:c2")
_BEATS = ("beat:b0", "beat:b1")
_KINDS = ("k0", "k1", "clock_fired")
_CMPS = (">=", ">", "<=", "<", "==", "!=")


class _FakeReads:
    """A seeded random WorldReads: every table is drawn once from `rng`, so a
    seed fully determines the world."""

    def __init__(self, rng: random.Random) -> None:
        self._entities = {e for e in _ENTITIES if rng.random() < 0.7}
        self._state = {
            (e, a): rng.choice(_STATE_VALUES)
            for e in _ENTITIES for a in _ATTRS if rng.random() < 0.8}
        for b in _BEATS:
            if rng.random() < 0.6:
                self._state[(b, "status")] = rng.choice(("achieved", "pending"))
        self._chains = {
            e: ([] if rng.random() < 0.2 else rng.sample(_PLACES, rng.randint(1, 3)))
            for e in _ENTITIES if rng.random() < 0.7}
        self._frame_rows = {
            (e, a, v) for e in _ENTITIES for a in _ATTRS for v in (1, "x")
            if rng.random() < 0.3}
        self._events: list[EventRow] = []
        for i in range(rng.randint(0, 7)):
            kind = rng.choice(_KINDS)
            if kind == "clock_fired":
                agents = tuple(rng.sample(_CLOCKS, rng.randint(1, 2)))
            else:
                agents = tuple(rng.sample(_ENTITIES[:4], rng.randint(0, 2)))
            self._events.append(EventRow(
                event_id=f"event:{i}", kind=kind, agents=agents,
                patients=tuple(rng.sample(_ENTITIES[:4], rng.randint(0, 1))),
                at=rng.choice((None, 0, 1, 2, 3, 4))))

    def has_entity(self, entity: str) -> bool:
        return entity in self._entities

    def state(self, entity: str, attribute: str, *, frame: str = "canon") -> object:
        return self._state.get((entity, attribute))

    def location_chain(self, entity: str) -> list[str] | None:
        return self._chains.get(entity)

    def assertion_in_frame(self, frame, entity, attribute, value) -> bool:
        return (entity, attribute, value) in self._frame_rows

    def events(self, *, kind=None, participant=None, since=None, until=None,
               frame="canon") -> list[EventRow]:
        out = []
        for r in self._events:
            if kind is not None and r.kind != kind:
                continue
            if since is not None and (r.at is None or r.at < since):
                continue
            if until is not None and (r.at is None or r.at > until):
                continue
            out.append(r)
        return out


def _rand_atom(rng: random.Random):
    e = rng.choice(_ENTITIES)
    a = rng.choice(_ATTRS)
    pick = rng.randrange(10)
    if pick == 0:
        return StateIs(e, a, rng.choice((1, 2, "x")))
    if pick == 1:
        return Located(e, rng.choice(_PLACES))
    if pick == 2:
        return InFrame("plot:main", e, a, rng.choice((1, "x")))
    if pick == 3:
        return Occurred(
            rng.choice(_KINDS[:2]),
            tuple(rng.sample(_ENTITIES[:4], rng.randint(0, 2))),
            since=rng.choice((None, 1)), until=rng.choice((None, 3)),
            min_count=rng.randint(1, 2))
    if pick == 4:
        return BeatAchieved(rng.choice(_BEATS))
    if pick in (5, 6):  # clocks weigh double: they are the interesting leaf
        return ClockFired(rng.choice(_CLOCKS), n=rng.randint(1, 2))
    if pick == 7:
        return rng.choice((TurnsElapsed, TurnsQuiet))(rng.randint(0, 6))
    return Quantity(e, a, rng.choice(_CMPS), rng.choice((0, 1, 2, 3.5, 7)))


def _rand_expr(rng: random.Random, depth: int) -> Expr:
    if depth <= 0 or rng.random() < 0.25:
        return _rand_atom(rng)
    shape = rng.randrange(4)
    if shape == 0:
        return Not(_rand_expr(rng, depth - 1))
    ops = tuple(_rand_expr(rng, depth - 1) for _ in range(rng.randint(0, 4)))
    if shape == 1:
        return AllOf(ops)
    if shape == 2:
        return AnyOf(ops)
    return AtLeast(rng.randint(0, 4), ops)


_N_CASES = 6000


def _cases():
    for seed in range(_N_CASES):
        rng = random.Random(seed)
        yield seed, _rand_expr(rng, rng.randint(1, 5)), _FakeReads(rng), rng


def test_new_fold_matches_each_old_copy():
    """Old `_true_leaves` / `_evaluate_clocks_false` / `_driving_entities` /
    `closure_witness_of` vs the explain-based fold, over `_N_CASES` random
    (expression, world) pairs."""
    seen_root: set[Truth] = set()
    seen_clock_caused: set[bool] = set()
    nonempty_driving = 0
    for seed, expr, reads, _rng in _cases():
        ctx = f"seed={seed} expr={expr!r}"

        # copy 1: the witness leaf walk (+ its own returned verdict)
        ref_t: list = []
        ref_u: list = []
        ref_f: list = []
        ref_verdict = _ref_true_leaves(expr, reads, ref_t, ref_u, ref_f)
        tree = explain(expr, reads)
        new_t: list = []
        new_u: list = []
        new_f: list = []
        _witness_leaves(tree, reads, new_t, new_u, new_f)
        assert (new_t, new_u, new_f) == (ref_t, ref_u, ref_f), ctx
        assert tree.verdict is ref_verdict, ctx
        seen_root.add(ref_verdict)

        # copy 2: the clock-necessity probe
        probe = explain(expr, reads, leaf=_forcing_clocks_false).verdict
        assert probe is _ref_clocks_false(expr, reads), ctx

        # copy 3: polarity-aware driving entities, for every polarity
        for want in (Truth.TRUE, Truth.FALSE, Truth.INDETERMINATE):
            got = _driving_entities(tree, want)
            assert got == _ref_driving_entities(expr, reads, want), (ctx, want)
        nonempty_driving += bool(_driving_entities(tree, Truth.TRUE))

        # the assembled witness, byte for byte
        ref_w = _ref_closure_witness_of(expr, reads, turn=seed)
        new_w = closure_witness_of(expr, reads, turn=seed)
        assert new_w == ref_w, ctx
        seen_clock_caused.add(new_w["clock_caused"])

    # the generator really exercised the interesting space
    assert seen_root == set(Truth)
    assert seen_clock_caused == {True, False}
    assert nonempty_driving > _N_CASES // 20


def test_explain_verdict_equals_evaluate_with_and_without_counters():
    for seed, expr, reads, rng in _cases():
        counters = rng.choice((
            None, PacingCounters(turns_elapsed=rng.randint(0, 8),
                                 turns_quiet=rng.randint(0, 8))))
        assert explain(expr, reads, counters).verdict is evaluate(
            expr, reads, counters), f"seed={seed} expr={expr!r}"


def test_explain_tree_shape_mirrors_the_expression():
    expr = AtLeast(1, (Not(StateIs("person:a", "role", 1)), AllOf(()),
                       ClockFired("clock:c0")))
    tree = explain(expr, _FakeReads(random.Random(0)))
    assert tree.expr is expr
    assert [type(c.expr) for c in tree.children] == [Not, AllOf, ClockFired]
    assert len(tree.children[0].children) == 1
    assert tree.children[1].children == ()
    assert tree.children[1].verdict is Truth.TRUE  # empty AllOf


def test_leaf_override_skips_the_read_and_only_touches_listed_atoms():
    class _Boom(_FakeReads):
        def events(self, **_kw):
            raise AssertionError("an overridden ClockFired must not read events")

    reads = _Boom(random.Random(1))
    expr = AnyOf((ClockFired("clock:c0"), Not(ClockFired("clock:c1"))))
    t = explain(expr, reads, leaf=_forcing_clocks_false)
    assert [c.verdict for c in t.children] == [Truth.FALSE, Truth.TRUE]
    assert t.verdict is Truth.TRUE


def test_bad_quantity_comparator_raises_through_every_path():
    import pytest
    bad = Quantity("person:a", "fuel", "~", 1)
    reads = _FakeReads(random.Random(2))
    reads._entities.add("person:a")
    reads._state[("person:a", "fuel")] = 2
    for fn in (lambda: evaluate(bad, reads), lambda: explain(bad, reads),
               lambda: closure_witness_of(bad, reads, 0)):
        with pytest.raises(ValueError):
            fn()
