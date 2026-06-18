"""Arc ↔ plot-frame serialization.

The arc IS `plot:` rows (ARC-LAYER §2); the CLI is one-shot per turn, so
the Arc object is reconstructed each turn from the frame. Condition
expressions serialize to JSON strings stored as assertion values.
"""

from __future__ import annotations

import json
from dataclasses import fields

from construct.arc import conditions as C
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Pin, Rung, Weight

#: The pin fields persisted as plot rows / cache keys (one row per field).
_PIN_FIELDS = ("scope_kind", "subject_entity", "directive", "subject_attribute",
               "anchor", "valid_from", "valid_to", "severity")

_ATOM_TYPES = {
    "state_is": C.StateIs, "located": C.Located, "in_frame": C.InFrame,
    "occurred": C.Occurred, "beat_achieved": C.BeatAchieved,
    "clock_fired": C.ClockFired, "turns_elapsed": C.TurnsElapsed,
    "turns_quiet": C.TurnsQuiet,
}
_TYPE_NAMES = {v: k for k, v in _ATOM_TYPES.items()}


def expr_to_obj(expr: C.Expr) -> dict:
    if isinstance(expr, C.Not):
        return {"op": "not", "operand": expr_to_obj(expr.operand)}
    if isinstance(expr, C.AllOf):
        return {"op": "all_of", "operands": [expr_to_obj(o) for o in expr.operands]}
    if isinstance(expr, C.AnyOf):
        return {"op": "any_of", "operands": [expr_to_obj(o) for o in expr.operands]}
    if isinstance(expr, C.AtLeast):
        return {"op": "at_least", "k": expr.k,
                "operands": [expr_to_obj(o) for o in expr.operands]}
    name = _TYPE_NAMES[type(expr)]
    payload = {f.name: getattr(expr, f.name) for f in fields(expr)}
    for key, val in payload.items():
        if isinstance(val, tuple):
            payload[key] = list(val)
    return {"op": name, **payload}


def expr_from_obj(obj: dict) -> C.Expr:
    op = obj["op"]
    if op == "not":
        return C.Not(expr_from_obj(obj["operand"]))
    if op == "all_of":
        return C.AllOf(tuple(expr_from_obj(o) for o in obj["operands"]))
    if op == "any_of":
        return C.AnyOf(tuple(expr_from_obj(o) for o in obj["operands"]))
    if op == "at_least":
        return C.AtLeast(obj["k"], tuple(expr_from_obj(o) for o in obj["operands"]))
    cls = _ATOM_TYPES[op]
    kwargs = {k: v for k, v in obj.items() if k != "op"}
    for key, val in kwargs.items():
        if isinstance(val, list):
            kwargs[key] = tuple(val)
    return cls(**kwargs)


def arc_to_items(arc: Arc, frame: str = "plot:main") -> list[dict]:
    """Flatten an Arc into ingest_structured items for the plot frame.

    Provenance note: session-zero authoring is `stated` (the default the
    gate applies to authoring-time structured items)."""
    items: list[dict] = [
        {"entity": arc.arc_id, "attribute": "kind", "value": "arc", "timeless": True},
        {"entity": arc.arc_id, "attribute": "protagonist", "value": arc.protagonist,
         "timeless": True},
        {"entity": arc.arc_id, "attribute": "climax_ready_k",
         "value": arc.climax_ready_k, "timeless": True},
        {"entity": arc.arc_id, "attribute": "climax_ready_beats",
         "value": json.dumps(list(arc.climax_ready_beats)), "timeless": True},
        {"entity": arc.arc_id, "attribute": "phase_budget",
         "value": json.dumps({p.value: n for p, n in arc.phase_budget.items()}),
         "timeless": True},
        {"entity": arc.arc_id, "attribute": "phase", "value": Phase.SETUP.value},
    ]
    if arc.failure_when is not None:
        items.append({"entity": arc.arc_id, "attribute": "failure_when",
                      "value": json.dumps(expr_to_obj(arc.failure_when)),
                      "timeless": True})
    shape = arc.shape
    items += [
        {"entity": shape.shape_id, "attribute": "kind", "value": "conclusion_shape",
         "timeless": True},
        {"entity": shape.shape_id, "attribute": "delta_type", "value": shape.delta_type,
         "timeless": True},
        {"entity": shape.shape_id, "attribute": "tension",
         "value": json.dumps(list(shape.tension)), "timeless": True},
        {"entity": shape.shape_id, "attribute": "world_condition",
         "value": json.dumps(expr_to_obj(shape.world_condition)), "timeless": True},
        {"entity": shape.shape_id, "attribute": "premise",
         "value": json.dumps(expr_to_obj(shape.premise)), "timeless": True},
        {"entity": shape.shape_id, "attribute": "refusal_variant",
         "value": shape.refusal_variant_id, "timeless": True},
        {"entity": arc.arc_id, "attribute": "conclusion_shape", "value": shape.shape_id,
         "timeless": True},
    ]
    for beat in arc.beats:
        items += [
            {"entity": beat.beat_id, "attribute": "kind", "value": "beat", "timeless": True},
            {"entity": beat.beat_id, "attribute": "part_of", "value": arc.arc_id,
             "timeless": True},
            {"entity": beat.beat_id, "attribute": "beat_phase", "value": beat.phase.value,
             "timeless": True},
            {"entity": beat.beat_id, "attribute": "weight", "value": beat.weight.value,
             "timeless": True},
            {"entity": beat.beat_id, "attribute": "achievable_via",
             "value": json.dumps(expr_to_obj(beat.achievable_via)), "timeless": True},
            {"entity": beat.beat_id, "attribute": "status", "value": "pending"},
        ]
        if beat.unreachable_if is not None:
            items.append({"entity": beat.beat_id, "attribute": "unreachable_if",
                          "value": json.dumps(expr_to_obj(beat.unreachable_if)),
                          "timeless": True})
        if beat.correlates is not None:
            items.append({"entity": beat.beat_id, "attribute": "correlates",
                          "value": json.dumps(list(beat.correlates)), "timeless": True})
    for clock in tuple(arc.clocks) + (arc.refusal_clock,):
        items += clock_to_items(clock, arc.arc_id)
    for pin in arc.pins:
        items += pin_to_items(pin, arc.arc_id)
    return [dict(item, frame=frame) for item in items]


def pin_to_items(pin: Pin, arc_id: str) -> list[dict]:
    """A pin as plot rows (host-owned frame; never canon). One row per
    field that is set — absent optional fields simply aren't written."""
    items = [{"entity": pin.pin_id, "attribute": "kind", "value": "pin", "timeless": True},
             {"entity": pin.pin_id, "attribute": "part_of", "value": arc_id, "timeless": True}]
    for field_name in _PIN_FIELDS:
        val = getattr(pin, field_name)
        if val is not None:
            items.append({"entity": pin.pin_id, "attribute": field_name,
                          "value": val, "timeless": True})
    return items


def _pin_from_reads(get, pin_id: str) -> Pin:
    """Reconstruct one Pin from its plot rows."""
    return Pin(
        pin_id=pin_id,
        scope_kind=get(pin_id, "scope_kind"),
        subject_entity=get(pin_id, "subject_entity"),
        directive=get(pin_id, "directive"),
        subject_attribute=get(pin_id, "subject_attribute"),
        anchor=get(pin_id, "anchor"),
        valid_from=_as_float(get(pin_id, "valid_from")),
        valid_to=_as_float(get(pin_id, "valid_to")),
        severity=_as_float(get(pin_id, "severity")) or 1.0,
    )


def _as_float(v) -> float | None:
    return None if v is None else float(v)


def clock_to_items(clock: Clock, arc_id: str) -> list[dict]:
    items = [
        {"entity": clock.clock_id, "attribute": "kind", "value": "clock", "timeless": True},
        {"entity": clock.clock_id, "attribute": "part_of", "value": arc_id, "timeless": True},
        {"entity": clock.clock_id, "attribute": "fires_when",
         "value": json.dumps(expr_to_obj(clock.fires_when)), "timeless": True},
        {"entity": clock.clock_id, "attribute": "effects",
         "value": json.dumps(list(clock.effects)), "timeless": True},
        {"entity": clock.clock_id, "attribute": "rearm", "value": clock.rearm,
         "timeless": True},
        {"entity": clock.clock_id, "attribute": "status", "value": "armed"},
    ]
    if clock.bound_to:
        items.append({"entity": clock.clock_id, "attribute": "bound_to",
                      "value": clock.bound_to, "timeless": True})
    if clock.rung:
        items.append({"entity": clock.clock_id, "attribute": "rung",
                      "value": clock.rung.value, "timeless": True})
    return items


def arc_from_frame(reads, arc_id: str = "arc:main", frame: str = "plot:main") -> Arc:
    """Reconstruct the Arc from plot-frame folds (one-shot CLI re-entry)."""

    def get(entity, attribute):
        return reads.state(entity, attribute, frame=frame)

    shape_id = get(arc_id, "conclusion_shape")
    shape = ConclusionShape(
        shape_id=shape_id,
        delta_type=get(shape_id, "delta_type"),
        tension=tuple(json.loads(get(shape_id, "tension"))),
        world_condition=expr_from_obj(json.loads(get(shape_id, "world_condition"))),
        premise=expr_from_obj(json.loads(get(shape_id, "premise"))),
        refusal_variant_id=get(shape_id, "refusal_variant"),
    )
    beat_ids = json.loads(get(arc_id, "beat_index") or "[]")
    beats = []
    for bid in beat_ids:
        unreachable = get(bid, "unreachable_if")
        correlates = get(bid, "correlates")
        beats.append(Beat(
            beat_id=bid,
            phase=Phase(get(bid, "beat_phase")),
            weight=Weight(get(bid, "weight")),
            achievable_via=expr_from_obj(json.loads(get(bid, "achievable_via"))),
            unreachable_if=expr_from_obj(json.loads(unreachable)) if unreachable else None,
            correlates=tuple(json.loads(correlates)) if correlates else None,
        ))
    clock_ids = json.loads(get(arc_id, "clock_index") or "[]")
    clocks, refusal = [], None
    for cid in clock_ids:
        rung_val = get(cid, "rung")
        fires_when = get(cid, "fires_when")
        effects = get(cid, "effects")
        if fires_when is None or effects is None:
            # A broken escalation clock degrades pacing, not coherence —
            # fail open LOUDLY and keep playing; the refusal clock below
            # stays fatal (it is the universal backstop).
            import logging
            logging.getLogger(__name__).error(
                "clock %s has incomplete plot rows (fires_when=%s effects=%s) — skipped",
                cid, fires_when is not None, effects is not None)
            continue
        clock = Clock(
            clock_id=cid,
            fires_when=expr_from_obj(json.loads(fires_when)),
            effects=tuple(json.loads(effects)),
            bound_to=get(cid, "bound_to"),
            rung=Rung(rung_val) if rung_val else None,
            rearm=get(cid, "rearm") or "once",
        )
        if clock.rung is Rung.REFUSAL:
            refusal = clock
        else:
            clocks.append(clock)
    if refusal is None:
        raise ValueError(f"{arc_id}: no refusal clock in {frame} — arc is corrupt")
    failure_raw = get(arc_id, "failure_when")
    pin_ids = json.loads(get(arc_id, "pin_index") or "[]")
    pins = tuple(_pin_from_reads(get, pid) for pid in pin_ids)
    return Arc(
        arc_id=arc_id,
        protagonist=get(arc_id, "protagonist"),
        shape=shape,
        beats=tuple(beats),
        clocks=tuple(clocks),
        refusal_clock=refusal,
        climax_ready_k=int(get(arc_id, "climax_ready_k")),
        climax_ready_beats=tuple(json.loads(get(arc_id, "climax_ready_beats"))),
        phase_budget={Phase(k): v for k, v in
                      json.loads(get(arc_id, "phase_budget") or "{}").items()},
        failure_when=expr_from_obj(json.loads(failure_raw)) if failure_raw else None,
        pins=pins,
    )


def arc_to_cache(arc: Arc) -> dict:
    """Host-side cache of the IMMUTABLE arc structure (exprs, ids,
    bindings). Beat/clock STATUSES are never cached — they live in
    `plot:` and are read live. The cache is derived and disposable
    (rebuildable from the frame via arc_from_frame); it exists because
    reconstructing from ~40 point reads costs minutes at play-world
    scale (engine read-path scaling, reported to PB)."""
    return {
        "arc_id": arc.arc_id,
        "protagonist": arc.protagonist,
        "shape": {
            "shape_id": arc.shape.shape_id,
            "delta_type": arc.shape.delta_type,
            "tension": list(arc.shape.tension),
            "world_condition": expr_to_obj(arc.shape.world_condition),
            "premise": expr_to_obj(arc.shape.premise),
            "refusal_variant_id": arc.shape.refusal_variant_id,
        },
        "beats": [{
            "beat_id": b.beat_id, "phase": b.phase.value, "weight": b.weight.value,
            "achievable_via": expr_to_obj(b.achievable_via),
            "unreachable_if": expr_to_obj(b.unreachable_if) if b.unreachable_if else None,
            "correlates": list(b.correlates) if b.correlates else None,
        } for b in arc.beats],
        "clocks": [_clock_to_cache(c) for c in arc.clocks],
        "refusal_clock": _clock_to_cache(arc.refusal_clock),
        "climax_ready_k": arc.climax_ready_k,
        "climax_ready_beats": list(arc.climax_ready_beats),
        "phase_budget": {p.value: n for p, n in arc.phase_budget.items()},
        "failure_when": expr_to_obj(arc.failure_when) if arc.failure_when else None,
        "pins": [{f: getattr(p, f) for f in ("pin_id", *_PIN_FIELDS)} for p in arc.pins],
    }


def _clock_to_cache(c: Clock) -> dict:
    return {
        "clock_id": c.clock_id, "fires_when": expr_to_obj(c.fires_when),
        "effects": list(c.effects), "bound_to": c.bound_to,
        "rung": c.rung.value if c.rung else None, "rearm": c.rearm,
    }


def _clock_from_cache(d: dict) -> Clock:
    return Clock(
        clock_id=d["clock_id"], fires_when=expr_from_obj(d["fires_when"]),
        effects=tuple(d["effects"]), bound_to=d.get("bound_to"),
        rung=Rung(d["rung"]) if d.get("rung") else None,
        rearm=d.get("rearm", "once"),
    )


def arc_from_cache(d: dict) -> Arc:
    shape = d["shape"]
    return Arc(
        arc_id=d["arc_id"], protagonist=d["protagonist"],
        shape=ConclusionShape(
            shape_id=shape["shape_id"], delta_type=shape["delta_type"],
            tension=tuple(shape["tension"]),
            world_condition=expr_from_obj(shape["world_condition"]),
            premise=expr_from_obj(shape["premise"]),
            refusal_variant_id=shape["refusal_variant_id"],
        ),
        beats=tuple(Beat(
            beat_id=b["beat_id"], phase=Phase(b["phase"]), weight=Weight(b["weight"]),
            achievable_via=expr_from_obj(b["achievable_via"]),
            unreachable_if=expr_from_obj(b["unreachable_if"]) if b.get("unreachable_if") else None,
            correlates=tuple(b["correlates"]) if b.get("correlates") else None,
        ) for b in d["beats"]),
        clocks=tuple(_clock_from_cache(c) for c in d["clocks"]),
        refusal_clock=_clock_from_cache(d["refusal_clock"]),
        climax_ready_k=d["climax_ready_k"],
        climax_ready_beats=tuple(d["climax_ready_beats"]),
        phase_budget={Phase(k): v for k, v in d.get("phase_budget", {}).items()},
        failure_when=expr_from_obj(d["failure_when"]) if d.get("failure_when") else None,
        pins=tuple(Pin(**p) for p in d.get("pins", [])),
    )


def index_items(arc: Arc, frame: str = "plot:main") -> list[dict]:
    """Beat/clock indexes so reconstruction never scans the frame."""
    return [
        {"entity": arc.arc_id, "attribute": "beat_index",
         "value": json.dumps([b.beat_id for b in arc.beats]),
         "timeless": True, "frame": frame},
        {"entity": arc.arc_id, "attribute": "clock_index",
         "value": json.dumps([c.clock_id for c in arc.clocks] + [arc.refusal_clock.clock_id]),
         "timeless": True, "frame": frame},
        # The pin discovery index (Cx 062 #1): the turn loop reads candidate
        # pin ids from here, never a host-side log scan.
        {"entity": arc.arc_id, "attribute": "pin_index",
         "value": json.dumps([p.pin_id for p in arc.pins]),
         "timeless": True, "frame": frame},
    ]
