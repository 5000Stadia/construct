"""Pinned-awareness resolution (PINNED-AWARENESS spec, reviews 060/062/063).

A pin is foregrounded every turn its scope is active. This module is the
pure host recipe over already-computed turn reads — no engine primitive
(PB 063), no I/O of its own. The turn loop computes the protagonist's
containment ancestry ONCE, the scene's present entities, and a single
`awareness_as_of`, then calls `resolve_active_pins`; the result is ordered
deterministically for the briefing's PINS block.

Discipline baked in:
- one `awareness_as_of` drives every scope test (Kernos 060 #2, Cx 062 #2);
- region membership is O(1) against the precomputed ancestry set, never a
  per-pin `locate` walk (Kernos 060 #2);
- salience is normalized [0,1] per kind with a deterministic cross-kind
  tie-break (Kernos 060 #4): temporal-urgent > social-presence > region-law;
- `spent` pins are excluded permanently — distinct from out-of-scope, which
  returns (Kernos 060 #6);
- salience is disposable ranking, never written as truth (RFC-002, Cx).
"""

from __future__ import annotations

from dataclasses import dataclass

from construct.arc.grammar import Pin

# Cross-kind tie-break bands (lower sorts earlier in the PINS block).
_BAND = {"temporal": 0, "social": 1, "region": 2}


@dataclass(frozen=True)
class ActivePin:
    """A pin resolved active this turn, with its ranking inputs."""

    pin: Pin
    salience: float  # normalized [0,1]
    band: int        # cross-kind tie-break band

    @property
    def subject_key(self) -> tuple[str, str | None]:
        """(entity, attribute) — used to dedupe against the scene read."""
        return (self.pin.subject_entity, self.pin.subject_attribute)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _temporal_salience(pin: Pin, as_of: float) -> float | None:
    """Countdown salience rising toward the deadline; None if inactive.
    Handles the degenerate windows Cx 062 flagged: open/zero windows,
    not-yet-started, already-expired."""
    vf, vt = pin.valid_from, pin.valid_to
    if vf is not None and as_of < vf:
        return None  # not started
    if vt is not None and as_of >= vt:
        return None  # expired
    sev = _clamp01(pin.severity)
    if vt is None:
        return sev  # open-ended → steady at its severity
    start = vf if vf is not None else as_of  # no start → treat as just-begun
    window = vt - start
    if window <= 0:
        return sev  # degenerate window → fully urgent (clamped by severity)
    return _clamp01(sev * (1.0 - (vt - as_of) / window))


def resolve_active_pins(
    pins,
    *,
    ancestry: set[str],
    present_entities: set[str],
    as_of: float,
    spent: set[str] | None = None,
) -> list[ActivePin]:
    """Return the pins active this turn, ordered for the briefing (band, then
    salience desc, then pin_id for stability). `ancestry` is the protagonist's
    containment chain as a set; `present_entities` are the scene's occupants;
    `as_of` is the single awareness coordinate; `spent` are permanently
    resolved pins (excluded). A `social` pin whose `anchor` names a group
    rather than a single present entity simply never matches here — group
    presence is deferred (Cx 062 #4), not silently scanned."""
    spent = spent or set()
    active: list[ActivePin] = []
    for pin in pins:
        if pin.pin_id in spent:
            continue
        if pin.scope_kind == "region":
            if pin.anchor and pin.anchor in ancestry:
                active.append(ActivePin(pin, _clamp01(0.4 * pin.severity), _BAND["region"]))
        elif pin.scope_kind == "social":
            if pin.anchor and pin.anchor in present_entities:
                active.append(ActivePin(pin, _clamp01(pin.severity), _BAND["social"]))
        elif pin.scope_kind == "temporal":
            sal = _temporal_salience(pin, as_of)
            if sal is not None:
                active.append(ActivePin(pin, sal, _BAND["temporal"]))
    active.sort(key=lambda a: (a.band, -a.salience, a.pin.pin_id))
    return active
