"""Gauges — numeric quantities as live dramatic constraints (GAUGE-PRIMITIVE.md).

A gauge is an ordinary `accrue` attribute (`gauge_level` on a `gauge:<slug>`
entity, declared in `semantics.ACCRUE_ATTRS`): a baseline literal plus signed
per-turn deltas the engine folds into a running total — "math off the model"
(the same substrate diegetic time rides, Kernos steer 074; PB ADOPTION §Numeric
quantities). Unlike monotonic story-time, a gauge moves BOTH ways: oxygen drains
(−) and a sealed vent slows the drain, a tank refuels (+); the bus burns fuel.

The host reads the folded total straight off `state()` (an accrue attribute folds
to `fact.value`) and an arc's `conditions.Quantity` atom triggers on it crossing a
line — so a beat, clock, `world_condition`, or refusal clock can fire on "oxygen
at 0" / "speed below 50". Surfacing the live number to the player and choosing the
per-turn delta are turn-loop concerns (see GAUGE-PRIMITIVE.md §3–§4); this module
is only the canon storage seam, mirroring `clock.commit_elapsed`.

The engine never reads a gauge as anything but a number; "the tank is *tense*" is
never a stored row (the membrane — derived drama stays recomputable).
"""
from __future__ import annotations

import dataclasses
import logging

LEVEL_ATTR = "gauge_level"   # declared fold_policy=accrue in semantics.py
LABEL_ATTR = "gauge_label"   # human phrasing for narrator surfacing (literal)
FLOOR_ATTR = "gauge_floor"   # optional terminal/clamp bound (literal)
CEILING_ATTR = "gauge_ceiling"

_log = logging.getLogger(__name__)


def gauge_id(slug: str) -> str:
    """Canonical id for a named gauge (`oxygen` -> `gauge:oxygen`)."""
    return slug if slug.startswith("gauge:") else f"gauge:{slug}"


def _state_value(porcelain, entity: str, attribute: str, *, as_of: float | None = None):
    try:
        st = porcelain.state(entity, attribute, as_of=as_of)
    except Exception:  # noqa: BLE001 — a frontier/unknown gauge reads as absent
        return None
    if isinstance(st, dict) and st.get("status") in ("known", "conflicted"):
        return (st.get("fact") or {}).get("value")
    return None


def read_gauge(world, slug: str, *, as_of: float | None = None) -> float | None:
    """The gauge's current folded total, or None if never seeded. `as_of` (Cx 259): read at
    the play horizon. Gauges are host-authored at build/play coordinates (never source-stamped),
    so this is a no-op for horizon worlds — bound for a uniformly horizon-disciplined turn path."""
    total = _state_value(world.porcelain, gauge_id(slug), LEVEL_ATTR, as_of=as_of)
    if isinstance(total, bool):
        return None
    if isinstance(total, (int, float)):
        return float(total)
    try:
        return float(str(total))
    except (TypeError, ValueError):
        return None


def seed_gauge(world, slug: str, baseline: float, *, label: str | None = None,
               floor: float | None = None, ceiling: float | None = None) -> None:
    """Establish a gauge's starting level (idempotent baseline) plus optional
    narrator label and floor/ceiling bounds. Call AT RUNTIME (via `ensure_gauges`
    on the reopened world), NEVER at build/staging: an accrue baseline written at
    build loses its fold_policy across close/reopen and the gauge stops folding
    deltas (the false-green bug). Runtime seeding re-establishes accrue."""
    gid = gauge_id(slug)
    rows: list[dict] = []
    if _state_value(world.porcelain, gid, "kind") is None:
        rows.append({"entity": gid, "attribute": "kind", "value": "gauge",
                     "timeless": True})
    if _state_value(world.porcelain, gid, LEVEL_ATTR) is None:
        rows.append({"entity": gid, "attribute": LEVEL_ATTR,
                     "value": float(baseline), "value_type": "literal"})
    if label is not None:
        rows.append({"entity": gid, "attribute": LABEL_ATTR, "value": label,
                     "timeless": True})
    if floor is not None:
        rows.append({"entity": gid, "attribute": FLOOR_ATTR, "value": float(floor),
                     "timeless": True})
    if ceiling is not None:
        rows.append({"entity": gid, "attribute": CEILING_ATTR, "value": float(ceiling),
                     "timeless": True})
    if rows:
        world.porcelain.ingest_structured(rows)


def commit_gauge(world, slug: str, delta: float) -> None:
    """Append a SIGNED change to the gauge (drain negative, replenish positive).
    Seeds a 0 baseline if the gauge was never established."""
    if not delta:
        return
    gid = gauge_id(slug)
    if _state_value(world.porcelain, gid, LEVEL_ATTR) is None:
        world.porcelain.ingest_structured(
            [{"entity": gid, "attribute": "kind", "value": "gauge", "timeless": True},
             {"entity": gid, "attribute": LEVEL_ATTR, "value": 0.0,
              "value_type": "literal"}])
    world.porcelain.ingest_structured(
        [{"entity": gid, "attribute": LEVEL_ATTR, "value": float(delta),
          "value_type": "delta"}])
    _log.debug("gauge %s %+g -> %s", gid, delta, read_gauge(world, slug))


# -- turn orchestration (GAUGE-PRIMITIVE.md §3-§5) --------------------------

def gauge_delta_for(gauge, action: str) -> float:
    """The signed per-turn delta for one gauge: the deterministic `base_delta`
    drift plus every `action_modifiers` keyword present in the player's action
    (cheap substring match, no model call — running burns air, resting buys it
    back). Part 3's model residual, when added, sums on top of this."""
    a = (action or "").lower()
    return gauge.base_delta + sum(d for kw, d in gauge.action_modifiers
                                  if kw.lower() in a)


def ensure_gauges(world, arc) -> None:
    """Seed each declared gauge's baseline if it isn't established yet — AT RUNTIME,
    on the live (reopened) world. This is load-bearing, not cosmetic: an `accrue`
    fold_policy applied to a baseline written at BUILD time (under a model) is lost
    across close/reopen, so the gauge would silently stop folding deltas. Seeding
    at runtime (the `clock.commit_elapsed` pattern) re-establishes accrue on the
    world that actually plays. NEVER seed a gauge baseline at build/staging."""
    for g in getattr(arc, "gauges", ()):
        if read_gauge(world, g.gauge_id) is None:
            seed_gauge(world, g.gauge_id, g.baseline, label=g.label,
                       floor=g.floor, ceiling=g.ceiling)


def gauge_pass(world, arc, action: str, *, as_of: float | None = None) -> dict[str, float]:
    """Drain/replenish every gauge by its delta and return the new folded levels.
    MUST run before `beat_pass`/`arc_outcome`/`clock_pass` so a crossed floor is
    visible to terminal/beat evaluation the SAME turn (Cx 150). Seeds lazily on
    first touch (`ensure_gauges`) so accrue is established at runtime. `as_of`: read
    the post-commit level at the play horizon (Cx 259)."""
    ensure_gauges(world, arc)
    levels: dict[str, float] = {}
    for g in getattr(arc, "gauges", ()):
        commit_gauge(world, g.gauge_id, gauge_delta_for(g, action))
        levels[g.gauge_id] = read_gauge(world, g.gauge_id, as_of=as_of)
    return levels


def gauge_floor_expr(arc):
    """`Quantity(<= floor)` over every terminal gauge, OR-combined — the LOSS
    terminal contribution. None when no gauge is terminal."""
    from construct.arc.conditions import AnyOf, Quantity
    floors = [Quantity(g.gauge_id, LEVEL_ATTR, "<=", g.floor)
              for g in getattr(arc, "gauges", ()) if g.terminal_on_floor]
    if not floors:
        return None
    return floors[0] if len(floors) == 1 else AnyOf(tuple(floors))


def apply_gauge_terminals(arc):
    """Return the arc with terminal gauge floors folded into `failure_when` (the
    LOSS path — never `world_condition`, which is the won path; Cx 149/151). The
    gauge DECLARATION is the source of truth; the floor is derived in each load,
    so a stored arc never double-writes it."""
    from construct.arc.conditions import AnyOf
    fe = gauge_floor_expr(arc)
    if fe is None:
        return arc
    combined = fe if arc.failure_when is None else AnyOf((arc.failure_when, fe))
    return dataclasses.replace(arc, failure_when=combined)


def gauge_urgency(gauge, level: float) -> float:
    """Fraction of the gauge's range still in hand, clamped [0,1]: 1.0 at the
    baseline, 0.0 at the floor. The host's stable salience signal (Cx 150:
    distance_to_floor / range), recomputed each turn, never stored."""
    rng = gauge.baseline - gauge.floor
    if rng <= 0:
        return 0.0
    return max(0.0, min(1.0, (level - gauge.floor) / rng))


def gauge_lines(arc, world, *, as_of: float | None = None) -> list[tuple]:
    """`(gauge, level, urgency)` for every readable gauge — the input the turn
    loop turns into an ephemeral pin line. Derived live; never canon."""
    out = []
    for g in getattr(arc, "gauges", ()):
        lvl = read_gauge(world, g.gauge_id, as_of=as_of)
        if lvl is not None:
            out.append((g, lvl, gauge_urgency(g, lvl)))
    return out


def gauge_coloring(arc, world, *, as_of: float | None = None) -> str | None:
    """`"costly"` when any terminal gauge sits at/below its `costly_band` — a WIN
    earned on the last of the reserve reads as a costly victory, not a clean one
    (part 5; the band→outcome map is per-shape config that may override this)."""
    for g in getattr(arc, "gauges", ()):
        if not g.terminal_on_floor:
            continue
        lvl = read_gauge(world, g.gauge_id, as_of=as_of)
        if lvl is not None and gauge_urgency(g, lvl) <= g.costly_band:
            return "costly"
    return None
