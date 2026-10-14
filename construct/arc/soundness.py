"""Story soundness (docs/design/STORY-SOUNDNESS.md r4, R35): can this story be finished?

A deterministic producer FIXED POINT over the arc — the delete-relaxation reachability idea
from classical planning (Helmert 2009; ideas only, no code taken). Start from what is true at
the horizon, repeatedly add whatever an ordinary write path of the code (P0-P8) could make
true, stop at the fixed point; then again with the reshape "miracle" channel (P10).

    produced by P0-P8              → fine
    only once P10 is added         → S12 (the story needs a miracle)
    by neither                     → S1 / S2 (unproducible by any modelled write path)

Over-approximate by construction (deletions ignored, `Not` counted as produced). Every
finding is ADVISORY in r4: the pass reports and is calibrated; nothing gates on it. No model
calls. Pure over (arc, cast, protagonist, reads); `world` (a HorizonView or raw World) only
for the future-only checks S4 / S9.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from construct.arc.conditions import (
    AllOf, AnyOf, AtLeast, BeatAchieved, ClockFired, InFrame, Located, Not, Occurred,
    Quantity, StateIs, Truth, TurnsElapsed, TurnsQuiet, atoms_of, evaluate,
)
from construct.arc.grammar import Arc, Weight

logger = logging.getLogger(__name__)

CANDIDATE_FATAL = "candidate-fatal"
ADVISORY = "advisory"
SEVERITY = {"S1": CANDIDATE_FATAL, "S2": CANDIDATE_FATAL, "S4": CANDIDATE_FATAL,
            "S12": CANDIDATE_FATAL}

#: The clock time attribute that only ever advances (P8).
_ELAPSED = ("time:elapsed", "elapsed_minutes")


@dataclass(frozen=True)
class SoundnessFinding:
    code: str
    subject: str
    message: str
    witness: tuple[str, ...] = ()

    @property
    def severity(self) -> str:
        return SEVERITY.get(self.code, ADVISORY)

    def line(self) -> str:
        w = ("; ".join(self.witness)) if self.witness else ""
        return f"{self.code} [{self.severity}] {self.subject}: {self.message}" + (
            f" — {w}" if w else "")


@dataclass
class SoundnessReport:
    layers: dict = field(default_factory=dict)          # atom key → first layer (P0-P8)
    findings: list = field(default_factory=list)

    def codes(self) -> list[str]:
        return [f.code for f in self.findings]

    def lines(self) -> list[str]:
        return [f.line() for f in self.findings]


def _key(atom: Any) -> str:
    return repr(atom)


def _is_bare_occurred_beat(arcs: Iterable[Arc], atom: Occurred) -> bool:
    return any(isinstance(b.achievable_via, Occurred) and b.achievable_via == atom
               for a in arcs for b in a.beats)


class _Producers:
    """The ordinary producers P0-P8 (and P10 when `miracle`), as one closure."""

    def __init__(self, arcs: list[Arc], cast: tuple, protagonist: str, reads: Any,
                 horizon: float | None, *, miracle: bool) -> None:
        self.arcs, self.cast, self.prot = arcs, cast, protagonist
        self.reads, self.h, self.miracle = reads, horizon, miracle
        self.beats = {b.beat_id: b for a in arcs for b in a.beats}
        self.clocks = {c.clock_id: c for a in arcs for c in a.clocks}
        self.layers: dict[str, int] = {}
        self.fired: set[str] = set()                     # clock ids produced
        self.effect_rows: list[tuple] = []               # (e, a, v) of produced clocks
        self.deliverable = self._deliverable_facts()

    # -- static facts -------------------------------------------------------------------
    def _deliverable_facts(self) -> set[tuple]:
        """P1: (e, a, v) carried by a live clue on a physically reachable holder that can
        act at the horizon (objects and places always can)."""
        from construct.arc.executor import person_can_act
        from construct.cast import _live_reachable, _reachable_nodes
        reach = _reachable_nodes(self.cast) if self.cast else set()
        out = set()
        for node in self.cast or ():
            if node.node_id not in reach:
                continue
            if node.node_id.startswith("person:"):
                try:
                    if not person_can_act(self.reads, node.node_id):
                        continue
                except Exception:  # noqa: BLE001 — unreadable liveness: not a producer
                    continue
            for c in node.holds_clues:
                if _live_reachable(c):
                    out.add(tuple(c.surface_fact))
        return out

    def _true_at_h(self, atom: Any) -> bool:
        if isinstance(atom, (TurnsElapsed, TurnsQuiet)):
            return False
        try:
            return evaluate(atom, self.reads) is Truth.TRUE
        except Exception:  # noqa: BLE001 — an unreadable atom is simply not P0-true
            return False

    def _exists(self, entity: str) -> bool:
        try:
            return bool(self.reads.has_entity(entity))
        except Exception:  # noqa: BLE001
            return False

    def _window_open(self, atom: Occurred) -> bool:
        return atom.until is None or self.h is None or atom.until >= self.h

    # -- one atom ---------------------------------------------------------------------------
    def atom_produced(self, atom: Any) -> bool:
        """Produced so far: in the layered set, or a kind that is always produced."""
        if isinstance(atom, (TurnsElapsed, TurnsQuiet)):                 # P5 counters
            return True
        if isinstance(atom, Quantity) and (atom.entity, atom.attribute) == _ELAPSED:
            return True                                                   # P8 time
        return _key(atom) in self.layers

    def _rule(self, atom: Any) -> bool:
        """Can a producer make `atom` true, given only what earlier rounds produced?"""
        if isinstance(atom, InFrame):
            if (atom.frame == f"knows:{self.prot}"
                    and (atom.entity, atom.attribute, atom.value) in self.deliverable):
                return True                                               # P1
            return self.miracle and atom.frame.startswith("knows:")       # P10
        if isinstance(atom, Located):
            if atom.entity == self.prot and atom.place.startswith("place:"):
                return True                                               # P2
            if atom.entity.startswith("obj:") and self._exists(atom.entity) and (
                    atom.place == self.prot or atom.place.startswith("place:")):
                return True                                               # P3
            if (atom.entity, "in", atom.place) in self.effect_rows:
                return True                                               # P6
            return self.miracle                                           # P10 restage
        if isinstance(atom, StateIs):
            if (atom.entity, atom.attribute, atom.value) in self.effect_rows:
                return True                                               # P6
            return self.miracle                                           # P10
        if isinstance(atom, Quantity):
            if atom.frame == "canon" and any((e, a) == (atom.entity, atom.attribute)
                                             for e, a, _v in self.effect_rows):
                return True                                               # P6 (monotone)
            return self.miracle and atom.frame == "canon"                 # P10
        if isinstance(atom, Occurred):
            if not self._window_open(atom):
                return False
            if (not set(atom.participants) - {self.prot} and atom.min_count <= 1
                    and _is_bare_occurred_beat(self.arcs, atom)):
                return True                                               # P4 detector
            if not atom.participants and atom.min_count <= 1 and any(
                    a == "kind" and v == atom.kind for _e, a, v in self.effect_rows):
                return True                                               # P6 clock event
            return self.miracle                                           # P10 consequence
        if isinstance(atom, BeatAchieved):
            b = self.beats.get(atom.beat_id)
            return b is not None and self.expr_produced(b.achievable_via)  # P7
        if isinstance(atom, ClockFired):
            c = self.clocks.get(atom.clock_id)
            if c is None or atom.clock_id not in self.fired:
                return False
            return atom.n <= 1 or getattr(c, "rearm", "") == "repeat"     # P5
        return False

    def expr_produced(self, expr: Any) -> bool:
        if isinstance(expr, Not):
            return True                       # the relaxation can't prove a negation
        if isinstance(expr, AllOf):
            return all(self.expr_produced(o) for o in expr.operands)
        if isinstance(expr, AnyOf):
            return any(self.expr_produced(o) for o in expr.operands)
        if isinstance(expr, AtLeast):
            return sum(self.expr_produced(o) for o in expr.operands) >= expr.k
        return self.atom_produced(expr)

    # -- the fixed point, in rounds (each round builds only on earlier rounds) -------------
    def run(self, conditions: list[Any]) -> None:
        atoms = {_key(a): a for c in conditions for a in atoms_of(c)}
        for k, a in atoms.items():
            if self._true_at_h(a):
                self.layers[k] = 0                                        # P0
        layer = 0
        while True:
            layer += 1
            new_atoms = [k for k, a in atoms.items()
                         if k not in self.layers and self._rule(a)]
            new_clocks = [c for c in self.clocks.values()
                          if c.clock_id not in self.fired and self.expr_produced(c.fires_when)]
            if not new_atoms and not new_clocks:
                break
            for k in new_atoms:
                self.layers[k] = layer
            for c in new_clocks:                                          # P5 → P6
                self.fired.add(c.clock_id)
                for item in c.effects or ():
                    self.effect_rows.append((item.get("entity"), item.get("attribute"),
                                             item.get("value")))


def _witness(p: _Producers, expr: Any) -> tuple[str, ...]:
    """Why each unproduced atom of `expr` isn't produced (short, factual)."""
    out = []
    for a in atoms_of(expr):
        if p.atom_produced(a):
            continue
        if isinstance(a, Occurred):
            if not p._window_open(a):
                why = f"its window closed (until {a.until}) before the horizon"
            elif set(a.participants) - {p.prot} or a.min_count > 1 or \
                    not _is_bare_occurred_beat(p.arcs, a):
                why = ("the event detector only writes protagonist-only bare-beat events, "
                       f"and no clock effect writes kind={a.kind}")
            else:
                why = f"no clock effect writes kind={a.kind}"
            out.append(f"Occurred({a.kind}): {why}")
        elif isinstance(a, InFrame):
            if a.frame == f"knows:{p.prot}":
                out.append(f"InFrame({a.entity} · {a.attribute} · {a.value}): no live clue "
                           "on a reachable holder able to act carries it")
            else:
                out.append(f"InFrame({a.frame}, {a.entity} · {a.attribute}): not true at "
                           "the horizon, and nothing writes that frame")
        elif isinstance(a, StateIs):
            out.append(f"StateIs({a.entity} · {a.attribute} · {a.value}): not true at the "
                       "horizon, and no clock effect writes it")
        elif isinstance(a, Located):
            out.append(f"Located({a.entity}, {a.place}): not there at the horizon, and no "
                       "clock effect moves it")
        elif isinstance(a, BeatAchieved):
            out.append(f"BeatAchieved({a.beat_id}): that beat is unproducible")
        elif isinstance(a, ClockFired):
            out.append(f"ClockFired({a.clock_id}): its fires_when is unproducible")
        else:
            out.append(f"{type(a).__name__}: no producer")
    return tuple(out)


def analyse(arc: Arc, cast: tuple | list, protagonist: str, reads: Any, *,
            horizon: float | None = None, world: Any = None, kind: str = "fresh",
            reshape: bool | None = None, side_arcs: Iterable[Arc] = (),
            goal_statement: str = "", hook_ids: Iterable[str] = ()) -> SoundnessReport:
    """The R35 pass over one arc. `kind` is "fresh" or "continuation" (S4 vs S9)."""
    from construct.reshape import reshape_enabled
    if reshape is None:
        reshape = reshape_enabled()
    arcs = [arc, *side_arcs]
    cast = tuple(cast or ())
    conditions = [b.achievable_via for b in arc.beats]
    conditions += [c.fires_when for a in arcs for c in a.clocks]
    for x in (arc.shape.world_condition, getattr(arc, "failure_when", None)):
        if x is not None:
            conditions.append(x)
    ordinary = _Producers(arcs, cast, protagonist, reads, horizon, miracle=False)
    ordinary.run(conditions)
    miracle = None
    if reshape:
        miracle = _Producers(arcs, cast, protagonist, reads, horizon, miracle=True)
        miracle.run(conditions)
    rep = SoundnessReport(layers=dict(ordinary.layers))

    def verdict(expr: Any) -> str:
        if ordinary.expr_produced(expr):
            return "ok"
        return "miracle" if (miracle and miracle.expr_produced(expr)) else "none"

    for b in arc.beats:
        v = verdict(b.achievable_via)
        if v == "ok":
            continue
        req = b.weight is Weight.REQUIRED
        if v == "miracle":
            code = "S12" if req else "S5"
            msg = "reachable only through a reshape (needs a miracle)"
        else:
            code = "S1" if req else "S5"
            msg = "unproducible by every modelled write path"
        rep.findings.append(SoundnessFinding(code, b.beat_id, msg,
                                             _witness(ordinary, b.achievable_via)))
    wc = arc.shape.world_condition
    v = verdict(wc)
    if v != "ok":
        rep.findings.append(SoundnessFinding(
            "S12" if v == "miracle" else "S2", "world_condition",
            "the chapter can't be won" + (" without a reshape" if v == "miracle" else ""),
            _witness(ordinary, wc)))
    fw = getattr(arc, "failure_when", None)
    if fw is not None and verdict(fw) != "ok":
        rep.findings.append(SoundnessFinding("S10", "failure_when",
                                             "the chapter can't be lost (noted, not wrong)"))
    rep.findings += _dead_holders(arc, cast, protagonist, reads)
    rep.findings += _future_only(arc, cast, world, kind, hook_ids)
    rep.findings += _orphan_clues(arc, cast, kind)
    rep.findings += _unplaced_cast(cast, reads, ordinary)
    rep.findings += _improv_places(arc, protagonist, ordinary)
    if not getattr(arc.shape, "tension", None) and not goal_statement.strip():
        rep.findings.append(SoundnessFinding("S11", arc.arc_id, "no tension and no goal"))
    return rep


def _dead_holders(arc: Arc, cast: tuple, prot: str, reads: Any) -> list:
    """S3: a required InFrame beat whose matching live clues' holders all can't act."""
    from construct.arc.executor import person_can_act
    from construct.cast import _live_reachable
    out = []
    for b in arc.beats:
        if b.weight is not Weight.REQUIRED:
            continue
        for a in atoms_of(b.achievable_via):
            if not (isinstance(a, InFrame) and a.frame == f"knows:{prot}"):
                continue
            holders = [n.node_id for n in cast for c in n.holds_clues
                       if _live_reachable(c)
                       and tuple(c.surface_fact) == (a.entity, a.attribute, a.value)]
            people = [h for h in holders if h.startswith("person:")]
            if people and len(people) == len(holders):
                try:
                    alive = [h for h in people if person_can_act(reads, h)]
                except Exception:  # noqa: BLE001
                    continue
                if not alive:
                    out.append(SoundnessFinding(
                        "S3", b.beat_id, "every live holder of its clue is unable to act at "
                        "the horizon (a reshape revival could still change that)",
                        tuple(people)))
    return out


def _future_only(arc: Arc, cast: tuple, world: Any, kind: str,
                 hook_ids: Iterable[str] = ()) -> list:
    """S4 (continuation) / S9 (fresh): beat referents, EVERY cast member (clue-less staged
    presences included — cr code review) and hook-cast ids, future-only at the horizon."""
    if world is None:
        return []
    from construct.adapter import IdentityUnavailable, is_future_only
    from construct.arc.lint import _entity_referents
    ids = {e for b in arc.beats for a in atoms_of(b.achievable_via)
           for e in _entity_referents(a)}
    ids |= {n.node_id for n in cast} | {str(i) for i in hook_ids}
    out = []
    for e in sorted(i for i in ids if i and ":" in i):
        try:
            if is_future_only(world, e):
                out.append(SoundnessFinding(
                    "S4" if kind == "continuation" else "S9", e,
                    "exists only past the horizon (the hidden story's future)"))
        except IdentityUnavailable as exc:
            out.append(SoundnessFinding("S9", e, f"presence unreadable ({exc})"))
    return out


def _orphan_clues(arc: Arc, cast: tuple, kind: str = "fresh") -> list:
    """S7: a genuine clue whose fact feeds no beat and no pillar (Chekhov).

    Calibration (run 9/10 archives): skipped for a CONTINUATION — the play-time cast there is
    chapter 1's, whose clues served chapter 1's pillars, so every one reads as orphaned (noise
    until B1's episode cast). A clue that NAMES another cast member is exempt: it is a
    discovery-chain edge (`_reachable_nodes`), its job is reachability, not a pillar."""
    if kind == "continuation":
        return []
    members = {n.node_id for n in cast}
    used = set()
    exprs = [b.achievable_via for b in arc.beats]
    for p in getattr(arc, "pillars", ()) or ():
        exprs += [x for x in (getattr(p, "genuine_via", None), getattr(p, "false_via", None))
                  if x is not None]
    for e in exprs:
        for a in atoms_of(e):
            if isinstance(a, InFrame):
                used.add((a.entity, a.attribute, a.value))
    return [SoundnessFinding("S7", c.clue_id if hasattr(c, "clue_id") else n.node_id,
                             "a genuine clue that feeds no beat and no pillar")
            for n in cast for c in n.holds_clues
            if c.coverage_effect == "genuine" and not c.is_red_herring
            and tuple(c.surface_fact) not in used
            and not ({c.surface_fact[0], c.surface_fact[2]} & (members - {n.node_id}))]


def _unplaced_cast(cast: tuple, reads: Any, p: _Producers) -> list:
    """S8: a cast person with no location at the horizon and nothing that places them."""
    out = []
    for n in cast:
        if not n.node_id.startswith("person:"):
            continue
        try:
            if reads.location_chain(n.node_id):
                continue
        except Exception:  # noqa: BLE001
            continue
        if any(e == n.node_id and a == "in" for e, a, _v in p.effect_rows):
            continue
        out.append(SoundnessFinding("S8", n.node_id, "no location at the horizon, and "
                                                     "nothing places them"))
    return out


def _improv_places(arc: Arc, prot: str, p: _Producers) -> list:
    """S6: a beat that needs the protagonist at a place that doesn't exist at the horizon."""
    out = []
    for b in arc.beats:
        for a in atoms_of(b.achievable_via):
            if isinstance(a, Located) and a.entity == prot and not p._exists(a.place):
                out.append(SoundnessFinding("S6", b.beat_id,
                                            f"relies on improvising {a.place} into being"))
    return out


def report_to_log(rep: SoundnessReport, where: str, arc_id: str) -> None:
    """Advisory only (r4): log every finding and record it on the timing log."""
    from construct import timing
    for f in rep.findings:
        (logger.warning if f.severity == CANDIDATE_FATAL else logger.info)(
            "soundness [%s] %s: %s", where, arc_id, f.line())
    try:
        timing.record("soundness", where=where, arc=arc_id, codes=rep.codes(),
                      findings=rep.lines())
    except Exception:  # noqa: BLE001 — reporting never sinks a build
        logger.debug("soundness timing record skipped", exc_info=True)
