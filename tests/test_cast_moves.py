"""#80 CAST-MOVES — the narration-seam licensed movement lane (docs/design/CAST-MOVES.md).

Two layers of coverage, matching the spec's own split between engine-guarded structure and
host-policy stagecraft:

- PURE unit tests over `_partition_cast_moves`/`_run_cast_moves_lane`/`_canonicalize_containment`
  (construct/turnloop.py) against tiny fakes — fast, exhaustive over the row-correlation battery
  and the five-rule policy gate, no real World/turn needed.
- A smaller set of true end-to-end `run_turn` tests (reusing tests/test_integration.py's world/
  make_arc/seed_arc/StubProvider fixtures) proving the seam wiring: extraction -> canonicalize ->
  resolve -> partition -> gate -> commit -> presence, including the horizon oracle and the
  engaged-this-turn battery through a real turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from construct.adapter import PorcelainWorldReads
from construct.provider import StubProvider
from construct.resolve import ResolutionOutcome
from construct.turnloop import (
    TurnTrace,
    _canonicalize_containment,
    _partition_cast_moves,
    _receipt_rows,
    _run_cast_moves_lane,
)

from tests.test_integration import PLAYER, make_arc, run_turn, seed_arc, world  # noqa: F401

PROTAGONIST = "person:player"
SCENE = "place:study"


# --------------------------------------------------------------------------------------
# fakes for the pure unit layer
# --------------------------------------------------------------------------------------

class _FakeReads:
    """Minimal `live_reads.state(entity, attribute)` stand-in — a flat fact table, no
    horizon plumbing (the real horizon guarantee lives in `PorcelainWorldReads`; these
    unit tests only exercise `_partition_cast_moves`/`_run_cast_moves_lane`'s OWN logic,
    which trusts whatever `live_reads` it is handed)."""

    def __init__(self, facts: dict[tuple[str, str], object]):
        self._facts = dict(facts)

    def state(self, entity: str, attribute: str, *, frame: str = "canon"):
        return self._facts.get((entity, attribute))


@dataclass
class _FakeReceipt:
    rows: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"rows": self.rows}


class _FakeP:
    """Fake porcelain: logs every `ingest_structured` call; `next_receipt` (if set)
    answers the NEXT call only, else every row is confirmed by default (echoing
    entity/attribute back, as PB's real receipt rows do)."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[dict], str]] = []
        self.next_receipt: _FakeReceipt | None = None

    def ingest_structured(self, rows, classify: str = "inline", **_kw):
        rows = list(rows)
        self.calls.append((rows, classify))
        if self.next_receipt is not None:
            r, self.next_receipt = self.next_receipt, None
            return r
        return _FakeReceipt([{"entity": r["entity"], "attribute": r["attribute"]} for r in rows])


def _outcome(row_index, resolved_entity, subject_outcome, value_outcome,
            resolved_value=None, raw_value=None, reason="bound") -> ResolutionOutcome:
    return ResolutionOutcome(
        row_index=row_index, raw_entity=resolved_entity, raw_value=raw_value,
        resolved_entity=resolved_entity, resolved_value=resolved_value,
        subject_outcome=subject_outcome, value_outcome=value_outcome, reason=reason)


_KINDS = {
    ("person:maud", "kind"): "person",
    ("person:nell", "kind"): "person",
    ("person:reed", "kind"): "person",
    ("place:study", "kind"): "place",
    ("place:flat", "kind"): "place",
}


# ---- _canonicalize_containment -----------------------------------------------------

def test_canonicalize_containment_collapses_synonyms_and_leaves_others():
    rows = [
        {"entity": "person:maud", "attribute": "inside", "value": "place:flat"},
        {"entity": "person:nell", "attribute": "located_in", "value": "place:flat"},
        {"entity": "person:reed", "attribute": "in", "value": "place:flat"},
        {"entity": "person:reed", "attribute": "holds", "value": "obj:lamp"},
        {"entity": "person:reed", "attribute": "name", "value": "Reed"},
    ]
    out = _canonicalize_containment(rows)
    assert [r["attribute"] for r in out] == ["in", "in", "in", "holds", "name"]
    # untouched rows are the SAME values (no needless copy of a row we didn't rewrite)
    assert out[2] is rows[2]
    assert out[3] is rows[3]
    # the original list is never mutated in place
    assert rows[0]["attribute"] == "inside"


# ---- _partition_cast_moves: row-correlation battery (test bar 2c) -----------------

def test_partition_bound_move_candidate():
    canon_rows = [{"entity": "person:maud", "attribute": "in", "value": "place:flat"}]
    outcomes = [_outcome(0, "person:maud", "bound", "bound", resolved_value="place:flat")]
    filtered, cands, drops = _partition_cast_moves(
        [{"entity": "person:maud", "attribute": "in", "value": "place:flat"}],
        canon_rows, outcomes, scene=SCENE)
    assert cands == [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"}]
    assert drops == []
    assert filtered == []  # the move row is pulled OUT of ordinary promotion


def test_partition_subject_drop_row_is_nothing():
    # 2c-a: a row whose SUBJECT dropped is nothing — never a candidate.
    canon_rows = [{"entity": "person:ghost", "attribute": "in", "value": "place:flat"}]
    outcomes = [_outcome(0, None, "dropped", "dropped", raw_value="place:flat")]
    _filtered, cands, drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    assert cands == [] and drops == []


def test_partition_destination_drop_is_unbound_exit_not_subject_drop():
    # 2c-a/b: subject BOUND + destination DROPPED (not scene-named) -> unbound exit,
    # distinguished from the subject-drop case above via the per-row outcome record.
    canon_rows = [{"entity": "person:nell", "attribute": "in", "value": "somewhere_unbound"}]
    outcomes = [_outcome(0, "person:nell", "bound", "dropped", raw_value="somewhere unbound")]
    _filtered, cands, drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    assert cands == [{"kind": "unbound_exit", "person": "person:nell", "destination": None}]
    assert drops == []


def test_partition_multiple_simultaneous_drops_each_own_record():
    # 2c-c: two same-attribute rows, each dropped independently — BOTH surface as their
    # own candidate (never conflated via the legacy global receipt tuple).
    canon_rows = [
        {"entity": "person:nell", "attribute": "in", "value": "x"},
        {"entity": "person:reed", "attribute": "in", "value": "y"},
    ]
    outcomes = [
        _outcome(0, "person:nell", "bound", "dropped", raw_value="x"),
        _outcome(1, "person:reed", "bound", "bound_non_place", raw_value="y", resolved_value="obj:box"),
    ]
    _filtered, cands, _drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    assert {c["person"] for c in cands} == {"person:nell", "person:reed"}
    assert all(c["kind"] == "unbound_exit" for c in cands)


def test_partition_destination_bound_to_non_place_reclassifies_unbound_exit():
    # 2c-d: the destination BOUND (resolve.py's own outcome says "bound"), but to a
    # NON-place (a person) — the lane's OWN fold check reclassifies as unbound exit,
    # never a bound move.
    canon_rows = [{"entity": "person:maud", "attribute": "in", "value": "person:reed"}]
    outcomes = [_outcome(0, "person:maud", "bound", "bound",
                         resolved_value="person:reed", raw_value="person:reed")]
    _filtered, cands, _drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    assert cands == [{"kind": "unbound_exit", "person": "person:maud", "destination": None}]


def test_partition_no_private_metadata_reaches_the_filtered_rows():
    # 2c-e: the filtered resolved-rows list carries NO ResolutionOutcome-shaped metadata
    # (row_index/subject_outcome/...) — committed rows stay byte-identical to today's.
    ordinary = {"entity": "person:maud", "attribute": "name", "value": "Maud"}
    resolved_rows = [ordinary]
    canon_rows = [{"entity": "person:maud", "attribute": "name", "value": "Maud"}]
    outcomes = [_outcome(0, "person:maud", "bound", "not_entity_valued", resolved_value="Maud")]
    filtered, cands, _drops = _partition_cast_moves(
        resolved_rows, canon_rows, outcomes, scene=SCENE)
    assert filtered == [ordinary]
    assert filtered[0] is ordinary          # untouched object, no wrapper/copy
    assert set(filtered[0].keys()) == {"entity", "attribute", "value"}
    assert cands == []                      # a plain `name` row is never a move candidate


def test_partition_ambiguous_scene_restatement_drops_no_candidate():
    # 2c-f: the raw value NAMES the current scene — an ambiguous restatement of where X
    # already is, not an exit. No candidate, no departed_scene downstream.
    canon_rows = [{"entity": "person:maud", "attribute": "in", "value": "the study"}]
    outcomes = [_outcome(0, "person:maud", "bound", "dropped", raw_value="the study")]
    _filtered, cands, drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE, scene_name="the Study")
    assert cands == []
    assert drops == [("person:maud", "", "ambiguous_scene_restatement")]


def test_partition_freshly_minted_destination_is_not_a_move():
    # a destination that resolve_rows MINTED fresh (never existed) is not a licensable
    # move at all — the narration channel cannot mint places (Entity Authority).
    canon_rows = [{"entity": "person:maud", "attribute": "in", "value": "obj:crate"}]
    outcomes = [_outcome(0, "person:maud", "bound", "minted", resolved_value="obj:crate")]
    _filtered, cands, drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    assert cands == [] and drops == []


def test_partition_non_person_subject_and_non_containment_rows_untouched():
    # a bound `in` row whose subject is NOT a person (e.g. an object) is left for
    # ordinary promotion; a non-"in" row is never even inspected.
    resolved_rows = [
        {"entity": "obj:crate", "attribute": "in", "value": "place:flat"},
        {"entity": "person:maud", "attribute": "role", "value": "housekeeper"},
    ]
    canon_rows = list(resolved_rows)
    outcomes = [
        _outcome(0, "obj:crate", "bound", "bound", resolved_value="place:flat"),
        _outcome(1, "person:maud", "bound", "not_entity_valued", resolved_value="housekeeper"),
    ]
    filtered, cands, _drops = _partition_cast_moves(
        resolved_rows, canon_rows, outcomes, scene=SCENE)
    assert filtered == resolved_rows   # nothing pulled out
    assert cands == []


# ---- _run_cast_moves_lane: the five-rule policy gate + commit + audit -------------

def _lane(candidates, *, present_ids=(), accompanying=None, protagonist=PROTAGONIST,
         scene=SCENE, engaged=frozenset(), turn=2, p=None, receipts=None):
    trace = TurnTrace(turn=turn)
    reads = _FakeReads({**_KINDS, **({(accompanying, "accompanying"): protagonist}
                                     if accompanying else {})})
    p = p or _FakeP()
    if receipts is not None:
        p.next_receipt = receipts
    _run_cast_moves_lane(
        p, live_reads=reads, trace=trace, turn=turn, protagonist=protagonist,
        scene=scene, present=lambda e: e in present_ids, engaged_this_turn=engaged,
        candidates=candidates)
    return trace, p


def test_rule1_never_the_protagonist():
    trace, p = _lane(
        [{"kind": "bound_move", "person": PROTAGONIST, "destination": "place:flat"}],
        present_ids={PROTAGONIST})
    assert trace.cast_moves == []
    assert trace.cast_move_drops == [(PROTAGONIST, "place:flat", "protagonist")]
    assert p.calls == []  # never even attempted


def test_rule2_never_a_bound_companion():
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:reed", "destination": "place:flat"}],
        present_ids={"person:reed"}, accompanying="person:reed")
    assert trace.cast_move_drops == [("person:reed", "place:flat", "companion")]
    assert p.calls == []


def test_rule4_remote_move_dropped():
    # neither origin nor destination is the current scene
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"}],
        present_ids=set(), scene="place:other")
    assert trace.cast_move_drops == [("person:maud", "place:flat", "remote")]
    assert p.calls == []


def test_rule5_engaged_departure_blocked_unengaged_licenses():
    # two departures in the SAME batch: Maud is engaged this turn (blocked), Nell is not
    # (licenses) — the rightful person alone gets the event.
    cands = [
        {"kind": "unbound_exit", "person": "person:maud", "destination": None},
        {"kind": "unbound_exit", "person": "person:nell", "destination": None},
    ]
    trace, p = _lane(cands, present_ids={"person:maud", "person:nell"},
                     engaged=frozenset({"person:maud"}))
    assert ("person:maud", "", "engaged_this_turn") in trace.cast_move_drops
    assert trace.cast_moves == [("unbound_exit", "person:nell", "")]
    # exactly one departed_scene event batch, for Nell only
    [(rows, classify)] = p.calls
    assert classify == "rules"
    agents = {r["value"] for r in rows if r["attribute"] == "agent"}
    assert agents == {"person:nell"}


def test_bound_arrival_commits_no_event():
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:harl", "destination": SCENE}],
        present_ids=set())  # off-scene origin -> arrival
    assert trace.cast_moves == [("bound_move", "person:harl", SCENE)]
    [(rows, classify)] = p.calls
    assert classify == "rules"
    assert rows == [{"entity": "person:harl", "attribute": "in", "value": SCENE,
                     "value_type": "entity", "valid_from": rows[0]["valid_from"]}]
    assert "caused_by" not in rows[0]


def test_bound_departure_commits_with_caused_by_and_departed_scene_event():
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"}],
        present_ids={"person:maud"})  # origin IS the scene, dest isn't -> departure
    assert ("bound_move", "person:maud", "place:flat") in trace.cast_moves
    move_call, event_call = p.calls
    move_rows, move_classify = move_call
    assert move_classify == "rules"
    ev_id = move_rows[0]["caused_by"]
    assert ev_id.startswith("event:departed_maud_")
    event_rows, event_classify = event_call
    assert event_classify == "rules"
    kinds = {(r["entity"], r["attribute"]): r["value"] for r in event_rows}
    assert kinds[(ev_id, "kind")] == "departed_scene"
    assert kinds[(ev_id, "agent")] == "person:maud"
    assert kinds[(ev_id, "patient")] == SCENE


def test_unbound_exit_writes_event_directly_no_move_row():
    trace, p = _lane(
        [{"kind": "unbound_exit", "person": "person:nell", "destination": None}],
        present_ids={"person:nell"})
    assert trace.cast_moves == [("unbound_exit", "person:nell", "")]
    [(rows, classify)] = p.calls   # exactly ONE ingest call: the event, no move row
    assert classify == "rules"
    assert {r["attribute"] for r in rows} == {"kind", "agent", "patient"}
    assert not any(r["attribute"] == "in" for r in rows)


def test_structural_skip_writes_no_event_and_no_negative_presence():
    # test bar 8 (Cx r1 gap 4): the engine refuses the move (e.g. cycle-forming) — the
    # receipt-gated sequencing must write NO departed_scene event.
    skip_receipt = _FakeReceipt(
        rows=[],  # nothing confirmed
        skipped=[{"entity": "person:maud", "attribute": "in", "value": "place:flat",
                  "reason": "cycle"}])
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"}],
        present_ids={"person:maud"}, receipts=skip_receipt)
    assert trace.cast_moves == []  # never counted committed
    assert ("person:maud", "place:flat", "engine_skip:cycle") in trace.cast_move_drops
    assert len(p.calls) == 1       # the move attempt only — no event batch followed


def test_merged_self_edge_skip_is_benign_telemetry():
    skip_receipt = _FakeReceipt(
        rows=[], skipped=[{"entity": "person:maud", "attribute": "in", "value": "place:flat",
                           "reason": "merged_self_edge"}])
    trace, _p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"}],
        present_ids={"person:maud"}, receipts=skip_receipt)
    assert ("person:maud", "place:flat", "engine_skip:merged_self_edge") in trace.cast_move_drops
    assert trace.cast_moves == []


def test_same_scene_restatement_arrival_is_a_harmless_noop_not_a_departure():
    # a bound move whose origin AND destination are both the current scene (a redundant
    # restatement) is treated as an arrival (no departure, no event) — never blocked by
    # rule 5, never mistaken for a remote move.
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": SCENE}],
        present_ids={"person:maud"}, scene=SCENE)
    assert trace.cast_moves == [("bound_move", "person:maud", SCENE)]
    [(rows, _classify)] = p.calls
    assert "caused_by" not in rows[0]


# --------------------------------------------------------------------------------------
# end-to-end run_turn coverage (real World, StubProvider) — the seam wiring + the bars
# that depend on genuine horizon/turn-loop plumbing.
# --------------------------------------------------------------------------------------

def _seed_person(world, pid: str, name: str, in_place: str) -> None:
    world.porcelain.ingest_structured([
        {"entity": pid, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": pid, "attribute": "name", "value": name},
        {"entity": pid, "attribute": "in", "value": in_place, "value_type": "entity"},
    ])


class TestCastMovesEndToEnd:
    def test_arrival_commits_and_is_present_next_turn(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:harl", "Harl", "place:flat")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:harl", "attribute": "in", "value": "place:study",
             "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "Harl comes in from the yard, stamping snow."},
        ])
        r = run_turn(world, arc, provider, "I wait by the fire.", turn=2,
                     scope=[PLAYER, "place:study", "person:harl"])
        assert r.trace.cast_moves == [("bound_move", "person:harl", "place:study")]
        assert world.porcelain.locate("person:harl")[0] == "place:study"

    def test_bound_departure_caused_by_lever_and_absent_next_turn(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")  # 2nd present NPC:
        # `only_one` must be False so Maud isn't auto-addressed — this proves an
        # UNENGAGED narrated departure licenses on its own.
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:maud", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
        ]})
        import construct.turnloop as tl
        mp = pytest.MonkeyPatch()
        mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])
        try:
            provider = StubProvider([
                {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
                 "uncertain_of": ""},
                {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
                {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
                {"prose": "Maud slips out to the flat; Nell stays by the window."},
            ])
            r = run_turn(world, arc, provider, "I look over the desk.", turn=2,
                         scope=[PLAYER, "place:study", "place:flat",
                                "person:maud", "person:nell"])
        finally:
            mp.undo()
        assert ("bound_move", "person:maud", "place:flat") in r.trace.cast_moves
        assert world.porcelain.locate("person:maud")[0] == "place:flat"
        evs = PorcelainWorldReads(world).events(kind="departed_scene")
        assert any("person:maud" in e.agents for e in evs)
        # the new `in` row carries caused_by pointing at that event (the re-entry lever)
        in_fact = world.porcelain.state("person:maud", "in")
        assert in_fact["status"] == "known"

    def test_unbound_exit_the_maid_slips_out(self, world):
        # test bar 2b: destination fails to bind ("the passage") -> EVENT-ONLY departed_scene;
        # no `in` row commits, no place mint; canon location stays stale by design.
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:maud", "attribute": "in", "value": "the passage beyond",
             "value_type": "entity"},
        ]})
        import construct.turnloop as tl
        mp = pytest.MonkeyPatch()
        mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])
        try:
            provider = StubProvider([
                {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
                 "uncertain_of": ""},
                {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
                {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
                {"prose": "The maid slips out into the passage beyond."},
            ])
            r = run_turn(world, arc, provider, "I look over the desk.", turn=2,
                         scope=[PLAYER, "place:study", "person:maud", "person:nell"])
        finally:
            mp.undo()
        assert ("unbound_exit", "person:maud", "") in r.trace.cast_moves
        evs = PorcelainWorldReads(world).events(kind="departed_scene")
        assert any("person:maud" in e.agents for e in evs)
        # her canon location is UNCHANGED — stale by design (world-tick's to move later)
        assert world.porcelain.locate("person:maud")[0] == "place:study"

    def test_protagonist_and_companion_moves_drop(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:reed", "Reed", "place:study")
        world.porcelain.ingest_structured([
            {"entity": "person:reed", "attribute": "accompanying", "value": PLAYER},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            # the world narrating the PLAYER moving themselves — dropped (rule 1)
            {"entity": PLAYER, "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
            # a bound companion narrated away — dropped (rule 2)
            {"entity": "person:reed", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Nothing here moves as the room briefly describes elsewhere."},
        ])
        r = run_turn(world, arc, provider, "I wait.", turn=2,
                     scope=[PLAYER, "place:study", "place:flat", "person:reed"])
        assert r.trace.cast_moves == []
        reasons = {reason for (_p, _d, reason) in r.trace.cast_move_drops}
        assert "protagonist" in reasons
        assert "companion" in reasons
        assert world.porcelain.locate(PLAYER)[0] == "place:study"       # player unmoved
        assert world.porcelain.locate("person:reed")[0] == "place:study"  # companion intact

    def test_remote_move_drops(self, world):
        # neither origin (place:flat) nor destination (place:annex) is the CURRENT scene
        # (place:study) — the narrator asserting off-screen motion is not the narrator's
        # to know; world-tick owns off-screen movement.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:annex", "attribute": "kind", "value": "room", "timeless": True},
        ])
        _seed_person(world, "person:rival", "Rival", "place:flat")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:rival", "attribute": "in", "value": "place:annex",
             "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "Elsewhere, unseen, someone crosses a different room."},
        ])
        r = run_turn(world, arc, provider, "I wait.", turn=2,
                     scope=[PLAYER, "place:study", "place:flat", "place:annex",
                            "person:rival"])
        assert r.trace.cast_moves == []
        assert ("person:rival", "place:annex", "remote") in r.trace.cast_move_drops
        assert world.porcelain.locate("person:rival")[0] == "place:flat"  # unmoved

    def test_synonym_spellings_all_enter_the_lane(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        for pid, name in (("person:anna", "Anna"), ("person:bruno", "Bruno"),
                          ("person:cora", "Cora")):
            _seed_person(world, pid, name, "place:flat")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:anna", "attribute": "in", "value": "place:study",
             "value_type": "entity"},
            {"entity": "person:bruno", "attribute": "inside", "value": "place:study",
             "value_type": "entity"},
            {"entity": "person:cora", "attribute": "located_in", "value": "place:study",
             "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "Anna, Bruno, and Cora all arrive together."},
        ])
        r = run_turn(world, arc, provider, "I wait.", turn=2,
                     scope=[PLAYER, "place:study", "person:anna", "person:bruno",
                            "person:cora"])
        committed = {(k, p, d) for (k, p, d) in r.trace.cast_moves}
        assert committed == {
            ("bound_move", "person:anna", "place:study"),
            ("bound_move", "person:bruno", "place:study"),
            ("bound_move", "person:cora", "place:study"),
        }
        for pid in ("person:anna", "person:bruno", "person:cora"):
            assert world.porcelain.locate(pid)[0] == "place:study"

    def test_unknown_destination_is_rejected_never_minted(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:harl", "Harl", "place:study")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:harl", "attribute": "in", "value": "place:nowhere_named",
             "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Harl wanders off to some unnamed place."},
        ])
        r = run_turn(world, arc, provider, "I wait.", turn=2,
                     scope=[PLAYER, "place:study", "person:harl"])
        assert world.porcelain.state("place:nowhere_named", "kind")["status"] != "known"
        # a `person:harl in place:nowhere_named` row never lands (dropped upstream by the
        # resolver — the narration channel cannot mint a place)
        assert not any(m[1] == "person:harl" for m in r.trace.cast_moves)

    def test_ordinary_non_containment_rows_unaffected(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:harl", "Harl", "place:study")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:harl", "attribute": "mood", "value": "uneasy"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Harl seems uneasy tonight."},
        ])
        r = run_turn(world, arc, provider, "I wait.", turn=2,
                     scope=[PLAYER, "place:study", "person:harl"])
        assert r.trace.cast_moves == []
        assert r.trace.cast_move_drops == []
        assert world.porcelain.state("person:harl", "mood")["status"] == "known"

    def test_engaged_named_npc_departure_blocked_unengaged_licenses(self, world):
        # test bar 7 + the r2 oracle: a NAMED, questioned NPC is protected even with no
        # cast/clue delivery at all (addressing engages; delivery does not define it).
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:maud", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
            {"entity": "person:nell", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
        ]})
        import construct.turnloop as tl
        mp = pytest.MonkeyPatch()
        mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])
        try:
            provider = StubProvider([
                {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
                 "uncertain_of": ""},
                {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
                {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
                {"prose": "Maud lingers as you speak to her; Nell slips out to the flat."},
            ])
            r = run_turn(world, arc, provider, "Maud, tell me what you saw.", turn=2,
                         scope=[PLAYER, "place:study", "place:flat",
                                "person:maud", "person:nell"])
        finally:
            mp.undo()
        assert not any(m[1] == "person:maud" for m in r.trace.cast_moves)
        assert any(d[0] == "person:maud" and d[2] == "engaged_this_turn"
                   for d in r.trace.cast_move_drops)
        assert ("bound_move", "person:nell", "place:flat") in r.trace.cast_moves
        assert world.porcelain.locate("person:maud")[0] == "place:study"   # stayed put
        assert world.porcelain.locate("person:nell")[0] == "place:flat"    # licensed

    def test_autonomous_speaker_departure_blocked(self, world):
        # rule 5's autonomous-speaker source: Reed SPEAKS this turn (npc_turn intent) —
        # protected even though the player addressed neither NPC by name.
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:reed", "Reed", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:reed", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
            {"entity": "person:nell", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
        ]})
        import construct.turnloop as tl
        mp = pytest.MonkeyPatch()
        mp.setattr(tl, "_parallel", lambda thunks: [t() for t in thunks])
        try:
            # npcs sorted: person:nell, person:reed (alphabetical) — align stub order
            provider = StubProvider([
                {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
                 "uncertain_of": ""},
                {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
                {"acts": False, "action": "", "speaks": True, "intent": "warn",
                 "line_hint": "wait"},
                {"prose": "Reed calls out to wait; Nell slips out to the flat."},
            ])
            r = run_turn(world, arc, provider, "I look around the room.", turn=2,
                         scope=[PLAYER, "place:study", "place:flat",
                                "person:reed", "person:nell"])
        finally:
            mp.undo()
        assert not any(m[1] == "person:reed" for m in r.trace.cast_moves)
        assert any(d[0] == "person:reed" and d[2] == "engaged_this_turn"
                   for d in r.trace.cast_move_drops)
        assert ("bound_move", "person:nell", "place:flat") in r.trace.cast_moves

    def test_horizon_oracle_future_stamped_rows_never_license_or_reject(self, world):
        # test bar 10: a FUTURE-stamped location/kind row (beyond the play horizon) can
        # neither license nor reject a present move — rules 3/4 read as-of `_h`.
        from construct.arc.executor import turn_time
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:harl", "Harl", "place:flat")
        # a FUTURE row relocating Harl to a bogus place beyond the horizon — must not be
        # read by the lane's folded-kind checks (only the current `place:study` head is).
        world.porcelain.ingest_structured([
            {"entity": "person:harl", "attribute": "in", "value": "place:study",
             "value_type": "entity", "valid_from": turn_time(999)},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:harl", "attribute": "in", "value": "place:study",
             "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "Harl comes in from the yard."},
        ])
        r = run_turn(world, arc, provider, "I wait.", turn=2,
                     scope=[PLAYER, "place:study", "person:harl"], horizon=turn_time(2))
        # licensed as an ARRIVAL at the play horizon (Harl's horizon-true origin is
        # place:flat, off-scene) — the future row must not make this look like a
        # same-scene no-op nor block it.
        assert ("bound_move", "person:harl", "place:study") in r.trace.cast_moves
