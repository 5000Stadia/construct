"""Pinned-awareness resolver (PINNED-AWARENESS spec) — the Cx 062 acceptance
list: expired/future absent, active present sharing one as_of, region
inheritance, entity-presence, spent exclusion, salience clamps + ordering.
"""

from construct.arc.grammar import Pin
from construct.pins import resolve_active_pins


def _region(anchor="place:luna", sev=1.0):
    return Pin("pin:gravity", "region", "place:luna", "gravity is half here",
               subject_attribute="gravity", anchor=anchor, severity=sev)


def _temporal(vf=0.0, vt=10.0, sev=1.0):
    return Pin("pin:bomb", "temporal", "fact:bomb", "a device counts down",
               subject_attribute="armed", valid_from=vf, valid_to=vt, severity=sev)


def _social(anchor="person:guard"):
    return Pin("pin:guard", "social", "person:guard", "the guard takes offense easily",
               subject_attribute="mood", anchor=anchor)


ANCESTRY = {"place:cabin", "place:luna"}  # protagonist is in a Luna cabin
PRESENT = {"person:guard", "person:player"}


def _ids(active):
    return [a.pin.pin_id for a in active]


class TestActivity:
    def test_region_active_iff_anchor_in_ancestry(self):
        active = resolve_active_pins([_region()], ancestry=ANCESTRY,
                                     present_entities=set(), as_of=5.0)
        assert _ids(active) == ["pin:gravity"]
        # anchor not in the chain → inactive (out of scope, returns later)
        off = resolve_active_pins([_region(anchor="place:mars")], ancestry=ANCESTRY,
                                  present_entities=set(), as_of=5.0)
        assert off == []

    def test_temporal_window_gates_on_shared_as_of(self):
        pin = [_temporal(vf=0.0, vt=10.0)]
        assert _ids(resolve_active_pins(pin, ancestry=set(), present_entities=set(),
                                        as_of=5.0)) == ["pin:bomb"]
        # future (not started) and expired both absent
        assert resolve_active_pins(pin, ancestry=set(), present_entities=set(),
                                   as_of=-1.0) == []
        assert resolve_active_pins(pin, ancestry=set(), present_entities=set(),
                                   as_of=10.0) == []  # vt is exclusive

    def test_social_active_iff_entity_present(self):
        assert _ids(resolve_active_pins([_social()], ancestry=set(),
                                        present_entities=PRESENT, as_of=5.0)) == ["pin:guard"]
        assert resolve_active_pins([_social(anchor="person:absent")], ancestry=set(),
                                   present_entities=PRESENT, as_of=5.0) == []

    def test_spent_pins_are_excluded(self):
        active = resolve_active_pins([_region()], ancestry=ANCESTRY,
                                     present_entities=set(), as_of=5.0,
                                     spent={"pin:gravity"})
        assert active == []


class TestSalience:
    def test_temporal_rises_toward_deadline_and_clamps(self):
        pin = _temporal(vf=0.0, vt=10.0, sev=1.0)
        early = resolve_active_pins([pin], ancestry=set(), present_entities=set(),
                                    as_of=1.0)[0].salience
        late = resolve_active_pins([pin], ancestry=set(), present_entities=set(),
                                   as_of=9.0)[0].salience
        assert 0.0 <= early < late <= 1.0

    def test_degenerate_windows_are_safe(self):
        # zero-width window → fully urgent (clamped by severity)
        zero = Pin("pin:z", "temporal", "fact:z", "now", valid_from=5.0,
                   valid_to=5.0, severity=1.0)
        assert resolve_active_pins([zero], ancestry=set(), present_entities=set(),
                                   as_of=5.0) == []  # vt exclusive → not active at vt
        # open-ended (no valid_to) → steady at severity while started
        openp = Pin("pin:o", "temporal", "fact:o", "ongoing", valid_from=0.0,
                    valid_to=None, severity=0.7)
        s = resolve_active_pins([openp], ancestry=set(), present_entities=set(),
                                as_of=100.0)[0].salience
        assert abs(s - 0.7) < 1e-9

    def test_region_salience_never_exceeds_one(self):
        s = resolve_active_pins([_region(sev=10.0)], ancestry=ANCESTRY,
                                present_entities=set(), as_of=5.0)[0].salience
        assert 0.0 <= s <= 1.0


class TestOrdering:
    def test_cross_kind_band_order_is_deterministic(self):
        # temporal (urgent) before social before region (law)
        pins = [_region(), _social(), _temporal(vf=0.0, vt=10.0)]
        active = resolve_active_pins(pins, ancestry=ANCESTRY,
                                     present_entities=PRESENT, as_of=9.0)
        assert _ids(active) == ["pin:bomb", "pin:guard", "pin:gravity"]
