"""Arc ↔ plot-frame serialization.

The arc IS `plot:` rows (ARC-LAYER §2); the CLI is one-shot per turn, so
the Arc object is reconstructed each turn from the frame. Condition
expressions serialize to JSON strings stored as assertion values.
"""

from __future__ import annotations

import json
from dataclasses import fields

from construct.arc import conditions as C
from construct.arc.grammar import (
    Arc, Beat, Clock, ConclusionShape, Gauge, Phase, Pillar, Pin, Rung, Weight,
)

#: The pin fields persisted as plot rows / cache keys (one row per field).
_PIN_FIELDS = ("scope_kind", "subject_entity", "directive", "subject_attribute",
               "anchor", "valid_from", "valid_to", "severity")

#: Attributes whose value is an opaque JSON blob the host round-trips verbatim
#: (serialized exprs, lists, dicts). They MUST be stored `literal` — left
#: untyped, the ingest classifier mis-types a blob like `{"op":"occurred",...}`
#: as an `entity`, and at world scale the identity-reconcile pass then
#: resolves/drops it, silently losing a beat/clock. (Root-caused on a fresh
#: `anchor` re-seal: `beat:truth_costs_protection` dropped. Pinning literal
#: keeps these blobs opaque — never classified, never identity-merged.)
_JSON_BLOB_ATTRS = frozenset({
    "climax_ready_beats", "phase_budget", "failure_when", "tension",
    "world_condition", "premise", "achievable_via", "unreachable_if",
    "correlates", "fires_when", "effects", "beat_index", "clock_index",
    "pin_index", "arc_ids", "pillar_index", "genuine_via", "false_via",
    "gauge_index", "action_modifiers",
})

#: The portfolio manifest entity — one row listing the active `arc:*` ids plus
#: which one is the main (terminal-bearing) arc. The registry is "more named
#: rows in `plot:main`", NOT a per-arc frame (every beat/clock/pin already
#: namespaces by `arc_id` and statuses key by globally-unique entity id, so N
#: arcs coexist in one frame). Absent → a single-arc world (backward compat).
_PORTFOLIO = "arc:portfolio"


def _with_frame_and_types(items: list[dict], frame: str) -> list[dict]:
    """Stamp the frame and pin JSON-blob attributes to `literal` value_type."""
    out = []
    for item in items:
        item = dict(item, frame=frame)
        if item["attribute"] in _JSON_BLOB_ATTRS and "value_type" not in item:
            item["value_type"] = "literal"
        out.append(item)
    return out

_ATOM_TYPES = {
    "state_is": C.StateIs, "located": C.Located, "in_frame": C.InFrame,
    "occurred": C.Occurred, "beat_achieved": C.BeatAchieved,
    "clock_fired": C.ClockFired, "turns_elapsed": C.TurnsElapsed,
    "turns_quiet": C.TurnsQuiet, "quantity": C.Quantity,
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
    for pillar in arc.pillars:
        items += pillar_to_items(pillar, arc.arc_id)
    for gauge in arc.gauges:
        items += gauge_to_items(gauge, arc.arc_id)
    return _with_frame_and_types(items, frame)


def pillar_to_items(pillar: Pillar, arc_id: str) -> list[dict]:
    """A pillar as plot rows (host-owned frame; never canon — STORY-SHAPES §0a/§8).
    One entity per pillar (`kind=pillar`, `part_of=arc_id`), mirroring beats/pins.
    `required` is stored as a "true"/"false" string (no bare-bool value ambiguity);
    `genuine_via`/`false_via` ride the same Expr-JSON path as beats (pinned literal)."""
    items = [
        {"entity": pillar.pillar_id, "attribute": "kind", "value": "pillar", "timeless": True},
        {"entity": pillar.pillar_id, "attribute": "part_of", "value": arc_id, "timeless": True},
        {"entity": pillar.pillar_id, "attribute": "label", "value": pillar.label,
         "timeless": True},
        {"entity": pillar.pillar_id, "attribute": "required",
         "value": "true" if pillar.required else "false", "timeless": True},
    ]
    if pillar.genuine_via is not None:
        items.append({"entity": pillar.pillar_id, "attribute": "genuine_via",
                      "value": json.dumps(expr_to_obj(pillar.genuine_via)), "timeless": True})
    if pillar.false_via is not None:
        items.append({"entity": pillar.pillar_id, "attribute": "false_via",
                      "value": json.dumps(expr_to_obj(pillar.false_via)), "timeless": True})
    return items


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
    if pin.escalates:  # written only when true → read back as a clean truthiness
        items.append({"entity": pin.pin_id, "attribute": "escalates",
                      "value": "yes", "timeless": True})
    return items


def gauge_to_items(gauge: Gauge, arc_id: str) -> list[dict]:
    """A gauge as plot rows (host control data; never canon). These rows are the
    arc's DECLARATION of the gauge; the live `gauge_level` accrue total is seeded
    on the same `gauge:<slug>` entity AT RUNTIME (gauge.ensure_gauges), never at
    build — a build-time accrue baseline loses fold_policy across reopen."""
    items = [
        {"entity": gauge.gauge_id, "attribute": "kind", "value": "gauge_decl",
         "timeless": True},
        {"entity": gauge.gauge_id, "attribute": "part_of", "value": arc_id, "timeless": True},
        {"entity": gauge.gauge_id, "attribute": "label", "value": gauge.label,
         "timeless": True},
        {"entity": gauge.gauge_id, "attribute": "baseline", "value": gauge.baseline,
         "timeless": True},
        {"entity": gauge.gauge_id, "attribute": "floor", "value": gauge.floor,
         "timeless": True},
        {"entity": gauge.gauge_id, "attribute": "base_delta", "value": gauge.base_delta,
         "timeless": True},
        {"entity": gauge.gauge_id, "attribute": "terminal_on_floor",
         "value": "true" if gauge.terminal_on_floor else "false", "timeless": True},
        {"entity": gauge.gauge_id, "attribute": "costly_band", "value": gauge.costly_band,
         "timeless": True},
        {"entity": gauge.gauge_id, "attribute": "action_modifiers",
         "value": json.dumps([list(m) for m in gauge.action_modifiers]), "timeless": True},
    ]
    if gauge.ceiling is not None:
        items.append({"entity": gauge.gauge_id, "attribute": "ceiling",
                      "value": gauge.ceiling, "timeless": True})
    return items


def _gauge_from_reads(get, gauge_id: str) -> Gauge:
    """Reconstruct one Gauge from its plot-declaration rows."""
    mods_raw = get(gauge_id, "action_modifiers")
    mods = tuple((kw, float(d)) for kw, d in json.loads(mods_raw)) if mods_raw else ()
    return Gauge(
        gauge_id=gauge_id,
        label=get(gauge_id, "label") or "",
        baseline=_as_float(get(gauge_id, "baseline")) or 0.0,
        floor=_as_float(get(gauge_id, "floor")) or 0.0,
        base_delta=_as_float(get(gauge_id, "base_delta")) or 0.0,
        ceiling=_as_float(get(gauge_id, "ceiling")),
        terminal_on_floor=(get(gauge_id, "terminal_on_floor") or "true") != "false",
        costly_band=_as_float(get(gauge_id, "costly_band")) or 0.25,
        action_modifiers=mods,
    )


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
        escalates=bool(get(pin_id, "escalates")),
    )


def _as_float(v) -> float | None:
    return None if v is None else float(v)


def _synth_refusal(arc_id: str) -> Clock:
    """The canonical refusal-clock fallback (mirrors `game._build_arc`), used when the
    stored refusal rows can't be read back. It is an EXPLICIT-ABANDONMENT clock (founder
    ruling 2026-06-25 / Cx 176): it fires only on an `event:abandoned_<arc>` occurrence
    (the player decisively walks away), NEVER on quiet turns — turns never force a close,
    and a quiet-turn refusal would fabricate a `refusal_conclusion` in canon. The id is
    per-arc so a synthesized side-arc clock never collides with the main one in `plot:main`."""
    is_main = arc_id == "arc:main"
    slug = arc_id.split(":", 1)[1]
    cid = "clock:refusal" if is_main else f"clock:refusal_{slug}"
    concludes = "event:world_concludes" if is_main else f"event:world_concludes_{slug}"
    abandon = "event:abandoned" if is_main else f"event:abandoned_{slug}"
    return Clock(
        clock_id=cid, fires_when=C.Occurred(abandon),
        effects=({"entity": concludes, "attribute": "kind",
                  "value": "refusal_conclusion"},),
        bound_to=arc_id, rung=Rung.REFUSAL)


def _safe_phase(value, bid: str) -> Phase:
    """A beat's phase, tolerant of a missing/invalid stored row. Phase only
    affects pacing/ordering (climax sufficiency is read from a separate index),
    so a bad row must degrade gracefully — fail OPEN loudly to a neutral phase,
    never crash the whole scenario load (the clock-loading discipline applied to
    beats; a real defect surfaced by the loopback self-test against `anchor`)."""
    try:
        return Phase(value)
    except ValueError:
        import logging
        logging.getLogger(__name__).error(
            "beat %s has no valid phase (%r) — defaulting to RISING", bid, value)
        return Phase.RISING


def _safe_weight(value, bid: str) -> Weight:
    """A beat's weight, tolerant of a missing/invalid row — defaults to
    REQUIRED (the safe choice: a beat the arc still expects), loudly."""
    try:
        return Weight(value)
    except ValueError:
        import logging
        logging.getLogger(__name__).error(
            "beat %s has no valid weight (%r) — defaulting to REQUIRED", bid, value)
        return Weight.REQUIRED


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
        achievable = get(bid, "achievable_via")
        if not achievable:
            # A beat with no condition can never be achieved and can't be
            # reconstructed — SKIP it loudly rather than crash the whole load
            # (clock fail-open discipline; surfaced by the loopback self-test
            # against a partially-corrupt `anchor` frame). The refusal clock
            # still backstops; a BeatAchieved ref to a dropped beat stays
            # evaluable (just never true).
            import logging
            logging.getLogger(__name__).error(
                "beat %s has no achievable_via — dropping from the arc", bid)
            continue
        unreachable = get(bid, "unreachable_if")
        correlates = get(bid, "correlates")
        beats.append(Beat(
            beat_id=bid,
            phase=_safe_phase(get(bid, "beat_phase"), bid),
            weight=_safe_weight(get(bid, "weight"), bid),
            achievable_via=expr_from_obj(json.loads(achievable)),
            unreachable_if=expr_from_obj(json.loads(unreachable)) if unreachable else None,
            correlates=tuple(json.loads(correlates)) if correlates else None,
        ))
    clock_ids = json.loads(get(arc_id, "clock_index") or "[]")
    # The refusal clock is ALWAYS appended last (arc_to_items/index_items), so
    # its id is the structural backstop when its `rung` row doesn't materialize
    # (a read-path drop at world scale — see _synth_refusal / PB report).
    refusal_id = clock_ids[-1] if clock_ids else None
    clocks, refusal = [], None
    for cid in clock_ids:
        rung_val = get(cid, "rung")
        fires_when = get(cid, "fires_when")
        effects = get(cid, "effects")
        if fires_when is None or effects is None:
            # A broken escalation clock degrades pacing, not coherence —
            # fail open LOUDLY and keep playing; the refusal backstop below
            # is synthesized if it can't be read.
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
        # rung may not materialize at scale; the last-indexed clock IS the
        # refusal clock by construction, so identify it by position too.
        if clock.rung is Rung.REFUSAL or cid == refusal_id:
            refusal = clock if clock.rung is Rung.REFUSAL else \
                Clock(clock.clock_id, clock.fires_when, clock.effects,
                      bound_to=clock.bound_to, rung=Rung.REFUSAL, rearm=clock.rearm)
        else:
            clocks.append(clock)
    if refusal is None:
        if not clock_ids:
            raise ValueError(f"{arc_id}: no clocks in {frame} — arc is corrupt")
        # The refusal clock's own rows didn't materialize (read-path drop at
        # scale). It is a FIXED backstop, so synthesize the canonical one rather
        # than leave the arc without its universal ender (fail-open, loud).
        import logging
        logging.getLogger(__name__).error(
            "%s: refusal clock rows did not materialize — synthesizing the "
            "canonical refusal backstop", arc_id)
        refusal = _synth_refusal(arc_id)
    failure_raw = get(arc_id, "failure_when")
    pin_ids = json.loads(get(arc_id, "pin_index") or "[]")
    pins = tuple(_pin_from_reads(get, pid) for pid in pin_ids)
    pillar_ids = json.loads(get(arc_id, "pillar_index") or "[]")
    pillars = tuple(_pillar_from_reads(get, pid) for pid in pillar_ids)
    gauge_ids = json.loads(get(arc_id, "gauge_index") or "[]")
    gauges = tuple(_gauge_from_reads(get, gid) for gid in gauge_ids)
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
        pillars=pillars,
        gauges=gauges,
    )


def _pillar_from_reads(get, pillar_id: str) -> Pillar:
    """Reconstruct one Pillar from plot rows (mirrors _pin_from_reads). `required`
    defaults True when the row is absent; `genuine_via`/`false_via` parse via the
    Expr-JSON path when present."""
    g = get(pillar_id, "genuine_via")
    f = get(pillar_id, "false_via")
    return Pillar(
        pillar_id=pillar_id,
        label=get(pillar_id, "label") or "",
        required=(get(pillar_id, "required") or "true") != "false",
        genuine_via=expr_from_obj(json.loads(g)) if g else None,
        false_via=expr_from_obj(json.loads(f)) if f else None,
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
        "pins": [{f: getattr(p, f) for f in ("pin_id", *_PIN_FIELDS, "escalates")}
                 for p in arc.pins],
        "pillars": [{
            "pillar_id": p.pillar_id, "label": p.label, "required": p.required,
            "genuine_via": expr_to_obj(p.genuine_via) if p.genuine_via else None,
            "false_via": expr_to_obj(p.false_via) if p.false_via else None,
        } for p in arc.pillars],
        "gauges": [{
            "gauge_id": g.gauge_id, "label": g.label, "baseline": g.baseline,
            "floor": g.floor, "base_delta": g.base_delta, "ceiling": g.ceiling,
            "terminal_on_floor": g.terminal_on_floor, "costly_band": g.costly_band,
            "action_modifiers": [list(m) for m in g.action_modifiers],
        } for g in arc.gauges],
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
        pillars=tuple(Pillar(
            pillar_id=p["pillar_id"], label=p.get("label", ""),
            required=p.get("required", True),
            genuine_via=expr_from_obj(p["genuine_via"]) if p.get("genuine_via") else None,
            false_via=expr_from_obj(p["false_via"]) if p.get("false_via") else None,
        ) for p in d.get("pillars", [])),
        gauges=tuple(Gauge(
            gauge_id=g["gauge_id"], label=g.get("label", ""), baseline=g["baseline"],
            floor=g["floor"], base_delta=g["base_delta"], ceiling=g.get("ceiling"),
            terminal_on_floor=g.get("terminal_on_floor", True),
            costly_band=g.get("costly_band", 0.25),
            action_modifiers=tuple(tuple(m) for m in g.get("action_modifiers", [])),
        ) for g in d.get("gauges", [])),
    )


def portfolio_items(arc_ids: list[str], main_arc_id: str = "arc:main",
                    frame: str = "plot:main", valid_from: float | None = None) -> list[dict]:
    """The portfolio manifest: which `arc:*` ids are active and which is main.

    Two rows on `arc:portfolio`. `arc_ids` is a JSON list (pinned `literal` via
    `_JSON_BLOB_ATTRS` — the same mis-classification hazard as the discovery
    indexes). A world without this row is a single-arc world (see
    `arc_ids_from_frame`). Session-zero writes them `timeless`.

    CAUTION on mid-play UPDATES (Cx 167): `valid_from` does NOT reliably supersede a
    sealed row — the durability classifier often marks these host-control rows
    CONSTITUTIVE, and a constitutive fold serves the EARLIEST visible row (marking
    the key conflicted), so a later `valid_from`/timeless write is silently ignored
    after reopen. A mid-play writer MUST `world.porcelain.retract(...)` the visible
    `arc:portfolio` rows first, THEN append (see `game.continue_episode`)."""
    if valid_from is None:
        meta = {"timeless": True}
    else:
        meta = {"valid_from": valid_from}
    return _with_frame_and_types([
        {"entity": _PORTFOLIO, "attribute": "arc_ids",
         "value": json.dumps(list(arc_ids)), **meta},
        {"entity": _PORTFOLIO, "attribute": "main_arc",
         "value": main_arc_id, **meta},
    ], frame)


def portfolio_add_items(reads, arc_id: str, frame: str = "plot:main",
                        valid_from: float | None = None) -> list[dict]:
    """Items that add `arc_id` to the live portfolio (idempotent), preserving the
    current main arc. The caller ingests them; with `valid_from` the updated list
    supersedes the sealed one (the P2 generator's mid-play registration)."""
    ids = arc_ids_from_frame(reads, frame=frame)
    if arc_id not in ids:
        ids = ids + [arc_id]
    return portfolio_items(ids, main_arc_id=main_arc_from_frame(reads, frame=frame),
                           frame=frame, valid_from=valid_from)


def arc_ids_from_frame(reads, frame: str = "plot:main") -> list[str]:
    """The active `arc:*` ids. Fail-open to `["arc:main"]` when no portfolio
    manifest exists — a pre-portfolio (single-arc) world plays unchanged."""
    raw = reads.state(_PORTFOLIO, "arc_ids", frame=frame)
    if not raw:
        return ["arc:main"]
    try:
        ids = json.loads(raw)
        return list(ids) if ids else ["arc:main"]
    except (ValueError, TypeError):
        import logging
        logging.getLogger(__name__).error(
            "arc:portfolio.arc_ids is unreadable (%r) — defaulting to single arc", raw)
        return ["arc:main"]


def main_arc_from_frame(reads, frame: str = "plot:main") -> str:
    """The main (terminal-bearing) arc id; fail-open to `arc:main`."""
    return reads.state(_PORTFOLIO, "main_arc", frame=frame) or "arc:main"


def portfolio_from_frame(reads, frame: str = "plot:main") -> list[Arc]:
    """Reconstruct every arc in the portfolio. Each id goes through the
    unchanged per-arc `arc_from_frame` (already `arc_id`-parametric); a broken
    arc is dropped LOUDLY rather than crashing the whole load (the fail-open
    discipline applied at the portfolio level)."""
    arcs = []
    for aid in arc_ids_from_frame(reads, frame=frame):
        try:
            arcs.append(arc_from_frame(reads, arc_id=aid, frame=frame))
        except Exception:  # noqa: BLE001 — one bad arc must not sink the others
            import logging
            logging.getLogger(__name__).exception(
                "arc %s failed to reconstruct — dropping it from the portfolio", aid)
    return arcs


def index_items(arc: Arc, frame: str = "plot:main") -> list[dict]:
    """Beat/clock indexes so reconstruction never scans the frame. These are
    JSON-blob values, pinned `literal` (see `_JSON_BLOB_ATTRS`)."""
    return _with_frame_and_types([
        {"entity": arc.arc_id, "attribute": "beat_index",
         "value": json.dumps([b.beat_id for b in arc.beats]), "timeless": True},
        {"entity": arc.arc_id, "attribute": "clock_index",
         "value": json.dumps([c.clock_id for c in arc.clocks] + [arc.refusal_clock.clock_id]),
         "timeless": True},
        # The pin discovery index (Cx 062 #1): the turn loop reads candidate
        # pin ids from here, never a host-side log scan.
        {"entity": arc.arc_id, "attribute": "pin_index",
         "value": json.dumps([p.pin_id for p in arc.pins]), "timeless": True},
        # The pillar discovery index (STORY-SHAPES §0a/§8): conclusion-as-effect reads
        # the arc's causal pillars from here, never a frame scan.
        {"entity": arc.arc_id, "attribute": "pillar_index",
         "value": json.dumps([p.pillar_id for p in arc.pillars]), "timeless": True},
        # The gauge declaration index (GAUGE-PRIMITIVE.md): the turn loop reads the
        # arc's gauges from here to drain/surface/terminate them.
        {"entity": arc.arc_id, "attribute": "gauge_index",
         "value": json.dumps([g.gauge_id for g in arc.gauges]), "timeless": True},
    ], frame)
