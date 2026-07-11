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
    """Fake porcelain: logs every `ingest_structured` call; `receipt_queue` answers calls
    in order (else every row is confirmed by default, echoing entity/attribute back as PB's
    real receipt rows do). The lane's horizon-bound read verbs are table-driven stand-ins:
    `place_heads` = the identity-resolved canon place roster (`entities`), `closures[eid]` =
    the id's identity-closure entity set (`facts(entity=…)` — a same_as alias's closure
    contains its head), `chains[eid]` = the containment chain (`locate`)."""

    def __init__(self, *, place_heads=("place:study", "place:flat"),
                 closures: dict | None = None, chains: dict | None = None) -> None:
        self.calls: list[tuple[list[dict], str]] = []
        self.receipt_queue: list[_FakeReceipt] = []
        self.place_heads = list(place_heads)
        self.closures = dict(closures or {})
        self.chains = dict(chains or {})

    def ingest_structured(self, rows, classify: str = "inline", **_kw):
        rows = list(rows)
        self.calls.append((rows, classify))
        if self.receipt_queue:
            return self.receipt_queue.pop(0)
        return _FakeReceipt([{"entity": r["entity"], "attribute": r["attribute"]} for r in rows])

    def entities(self, frame: str, prefix: str | None = None, as_of=None) -> list[str]:
        return [e for e in self.place_heads if prefix is None or e.startswith(prefix)]

    def facts(self, frame: str, entity: str | None = None, as_of=None, **_kw) -> list[dict]:
        return [{"entity": e} for e in self.closures.get(entity, [entity])]

    def locate(self, entity: str, as_of=None) -> list[str]:
        return list(self.chains.get(entity, []))


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
    assert cands == [{"kind": "bound_move", "person": "person:maud",
                      "destination": "place:flat", "via": None}]
    assert drops == []
    assert filtered == []  # the move row is pulled OUT of ordinary promotion


def test_partition_subject_drop_row_is_nothing():
    # 2c-a: a row whose SUBJECT dropped is nothing — never a candidate.
    canon_rows = [{"entity": "person:ghost", "attribute": "in", "value": "place:flat"}]
    outcomes = [_outcome(0, None, "dropped", "dropped", raw_value="place:flat")]
    _filtered, cands, drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    assert cands == [] and drops == []


def test_partition_destination_drop_never_creates_a_candidate():
    # §1.3 NARROWING (bar-11 live defect, cr <f8409447…>): a fully-DROPPED destination
    # ("by the hearth" / "the passage beyond") NEVER creates an exit candidate — live
    # fiction proved it is as often a within-scene position as an exit. Telemetry only.
    canon_rows = [{"entity": "person:nell", "attribute": "in", "value": "somewhere_unbound"}]
    outcomes = [_outcome(0, "person:nell", "bound", "dropped", raw_value="somewhere unbound")]
    _filtered, cands, drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    assert cands == []
    assert drops == [("person:nell", "", "ambiguous_unbound_destination")]


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
    _filtered, cands, drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    # nell's fully-dropped destination is telemetry-only (§1.3); reed's bound_non_place
    # destination survives as a candidate CARRYING its resolved via for the lane's
    # verified-container check.
    assert cands == [{"kind": "unbound_exit", "person": "person:reed",
                      "destination": None, "via": "obj:box"}]
    assert ("person:nell", "", "ambiguous_unbound_destination") in drops


def test_partition_destination_bound_to_non_place_reclassifies_unbound_exit():
    # 2c-d: the destination BOUND (resolve.py's own outcome says "bound"), but to a
    # NON-place (a person) — the lane's OWN fold check reclassifies as unbound exit,
    # never a bound move.
    canon_rows = [{"entity": "person:maud", "attribute": "in", "value": "person:reed"}]
    outcomes = [_outcome(0, "person:maud", "bound", "bound",
                         resolved_value="person:reed", raw_value="person:reed")]
    _filtered, cands, _drops = _partition_cast_moves(
        [], canon_rows, outcomes, scene=SCENE)
    assert cands == [{"kind": "unbound_exit", "person": "person:maud",
                      "destination": None, "via": "person:reed"}]


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
        p.receipt_queue = list(receipts) if isinstance(receipts, list) else [receipts]
    _run_cast_moves_lane(
        p, live_reads=reads, trace=trace, turn=turn, protagonist=protagonist,
        scene=scene, present=lambda e: e in present_ids, engaged_this_turn=engaged,
        candidates=candidates, horizon=None)
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
        {"kind": "unbound_exit", "person": "person:maud", "destination": None,
         "via": "obj:cart"},
        {"kind": "unbound_exit", "person": "person:nell", "destination": None,
         "via": "obj:cart"},
    ]
    p = _FakeP(chains={"obj:cart": ["place:flat"]})
    trace, p = _lane(cands, present_ids={"person:maud", "person:nell"},
                     engaged=frozenset({"person:maud"}), p=p)
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
    p = _FakeP(chains={"obj:cart": ["place:flat"]})
    trace, p = _lane(
        [{"kind": "unbound_exit", "person": "person:nell", "destination": None,
          "via": "obj:cart"}],
        present_ids={"person:nell"}, p=p)
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


# ---- BLOCKER 1 (cr review of 831eb30): destination presence matches _present's spatial
#      semantics — nested child places and same_as aliases of the scene are within-scene ----

def test_nested_child_destination_is_arrival_class_no_departure():
    # reviewer-reproduced: Maud present in the study moves to place:alcove NESTED UNDER
    # the study — within-scene motion is arrival-class; the old direct id compare minted
    # a false departed_scene(patient=scene) that suppressed someone still here.
    p = _FakeP(place_heads=("place:study", "place:flat", "place:alcove"),
               chains={"place:alcove": ["place:study"]})
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:alcove"}],
        present_ids={"person:maud"}, p=p)
    assert trace.cast_moves == [("bound_move", "person:maud", "place:alcove")]
    [(rows, _cl)] = p.calls                    # ONE ingest call: the move — no event batch
    assert "caused_by" not in rows[0]
    assert not any(r.get("value") == "departed_scene" for r in rows)
    assert trace.cast_move_drops == []


def test_same_as_alias_scene_destination_is_arrival_class_no_departure():
    # a destination bound to a same_as ALIAS of the current scene: the identity-closure
    # fold recognizes the scene head — no departure, no event (the alias id's closure
    # carries the head's id).
    p = _FakeP(closures={"place:study_room": ["place:study_room", "place:study"]})
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud",
          "destination": "place:study_room"}],
        present_ids={"person:maud"}, p=p)
    assert trace.cast_moves == [("bound_move", "person:maud", "place:study_room")]
    [(rows, _cl)] = p.calls
    assert "caused_by" not in rows[0]
    assert not any(r.get("value") == "departed_scene" for r in rows)


def test_rule3_unknown_head_destination_rejected_never_minted():
    # rule 3 re-verify (+ horizon KIND oracle): a destination whose RESOLVED HEAD has no
    # place rows at the horizon (future-only, or simply unknown) is REJECTED — the raw
    # `place:` prefix is not placeness; nothing is committed.
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:ghost"}],
        present_ids={"person:maud"})
    assert trace.cast_moves == []
    assert trace.cast_move_drops == [("person:maud", "place:ghost", "unknown_destination")]
    assert p.calls == []


def test_rule3_alias_destination_head_qualifies_as_place():
    # the alias KIND oracle: the destination id is a raw same_as alias; its HEAD is in
    # the horizon-bound place roster — the closure fold licenses it.
    p = _FakeP(closures={"place:old_flat": ["place:old_flat", "place:flat"]})
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:old_flat"}],
        present_ids={"person:maud"}, p=p)
    assert ("bound_move", "person:maud", "place:old_flat") in trace.cast_moves
    assert not any(reason == "unknown_destination"
                   for (_pp, _dd, reason) in trace.cast_move_drops)


# ---- BLOCKER 2 (cr review of 831eb30): event commits are receipt-confirmed ------------

def test_unbound_exit_unconfirmed_event_is_not_reported_committed():
    # reviewer-reproduced: fail-open ingest returns an empty receipt without raising —
    # the unbound exit changed nothing durable and must NOT count committed.
    p = _FakeP(chains={"obj:cart": ["place:flat"]})
    trace, p = _lane(
        [{"kind": "unbound_exit", "person": "person:nell", "destination": None,
          "via": "obj:cart"}],
        present_ids={"person:nell"}, p=p,
        receipts=_FakeReceipt(rows=[]))            # the event batch confirms nothing
    assert trace.cast_moves == []
    assert ("person:nell", "", "event_unconfirmed") in trace.cast_move_drops


def test_bound_departure_event_unconfirmed_move_still_counts_failure_recorded():
    # the location move receipt-confirmed and stays committed; the second-stage event
    # failing is recorded explicitly — never a silent claim of the complete pair; no retry.
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"}],
        present_ids={"person:maud"},
        receipts=[
            _FakeReceipt(rows=[{"entity": "person:maud", "attribute": "in"}]),  # move OK
            _FakeReceipt(rows=[]),                                              # event fails
        ])
    assert ("bound_move", "person:maud", "place:flat") in trace.cast_moves
    assert ("person:maud", "place:flat", "event_unconfirmed") in trace.cast_move_drops
    assert len(p.calls) == 2                       # move batch + ONE event attempt, no retry


# ---- BLOCKER 3 (cr review of 831eb30): per-person candidate normalization -------------

def test_exact_duplicate_candidates_collapse_to_one_commit():
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"},
         {"kind": "bound_move", "person": "person:maud", "destination": "place:flat"}],
        present_ids={"person:maud"})
    assert trace.cast_moves == [("bound_move", "person:maud", "place:flat")]
    move_rows = p.calls[0][0]
    assert len(move_rows) == 1                                          # ONE move row
    event_rows = p.calls[1][0]
    assert sum(1 for r in event_rows if r["attribute"] == "kind") == 1  # ONE event triple


def test_conflicting_destinations_for_one_person_fail_closed():
    # two receipt-confirmable moves for one person would mint a same-valid-time location
    # conflict — the lane has no basis to pick a winner; drop ALL of that person's
    # candidates, telemetry only.
    p = _FakeP(place_heads=("place:study", "place:flat", "place:annex"))
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"},
         {"kind": "bound_move", "person": "person:maud", "destination": "place:annex"}],
        present_ids={"person:maud"}, p=p)
    assert trace.cast_moves == []
    assert trace.cast_move_drops == [("person:maud", "", "ambiguous_multiple_moves")]
    assert p.calls == []


def test_conflicting_kinds_for_one_person_fail_closed():
    # a bound move beside an unbound exit for the SAME person is the same ambiguity —
    # fail closed, never commit either shape.
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"},
         {"kind": "unbound_exit", "person": "person:maud", "destination": None}],
        present_ids={"person:maud"})
    assert trace.cast_moves == []
    assert trace.cast_move_drops == [("person:maud", "", "ambiguous_multiple_moves")]
    assert p.calls == []


def test_origin_restatement_tiebreak_licenses_the_sole_transition():
    # §2b (bar-11 finding 2, cr <f8409447…>): natural arrival prose extracts the
    # destination AND a restated origin. Exactly two BOUND candidates, exactly one
    # restating the person's current immediate location at _h -> discard the
    # restatement, license the other through every ordinary check. ORDER-INDEPENDENT.
    restate = {"kind": "bound_move", "person": "person:maud", "destination": "place:study"}
    move = {"kind": "bound_move", "person": "person:maud", "destination": "place:flat"}
    for cands in ([restate, move], [move, restate]):
        p = _FakeP(chains={"person:maud": ["place:study"]})
        trace, p = _lane([dict(c) for c in cands], present_ids={"person:maud"}, p=p)
        assert trace.cast_moves == [("bound_move", "person:maud", "place:flat")], cands
        assert not any(d[2] == "ambiguous_multiple_moves" for d in trace.cast_move_drops)
        move_rows = p.calls[0][0]
        assert [r["value"] for r in move_rows if r["attribute"] == "in"] == ["place:flat"]


def test_tiebreak_counterexamples_stay_fail_closed():
    # every non-matching shape remains ambiguous_multiple_moves: two NON-current
    # destinations (known origin), three candidates, an unbound member in the pair.
    known_origin = {"person:maud": ["place:study"]}
    two_noncurrent = [
        {"kind": "bound_move", "person": "person:maud", "destination": "place:flat"},
        {"kind": "bound_move", "person": "person:maud", "destination": "place:annex"},
    ]
    three = two_noncurrent + [
        {"kind": "bound_move", "person": "person:maud", "destination": "place:study"}]
    with_unbound = [
        {"kind": "bound_move", "person": "person:maud", "destination": "place:study"},
        {"kind": "unbound_exit", "person": "person:maud", "destination": None,
         "via": "obj:cart"},
    ]
    for cands in (two_noncurrent, three, with_unbound):
        p = _FakeP(place_heads=("place:study", "place:flat", "place:annex"),
                   chains={"person:maud": ["place:study"], "obj:cart": ["place:flat"]})
        trace, p = _lane([dict(c) for c in cands], present_ids={"person:maud"}, p=p)
        assert trace.cast_moves == [], cands
        assert ("person:maud", "", "ambiguous_multiple_moves") in trace.cast_move_drops
        assert p.calls == []


def test_verified_exit_rejections_person_no_chain_colocated():
    # §1.3 unit battery: person destination / no location chain / colocated with the
    # scene — each reason-tagged, no event ever.
    cases = [
        ("person:reed", {}, "person_destination"),
        ("obj:mist", {}, "no_location_chain"),
        ("obj:hearth", {"obj:hearth": [SCENE]}, "colocated_destination"),
    ]
    for via, chains, reason in cases:
        p = _FakeP(chains=chains)
        trace, p = _lane(
            [{"kind": "unbound_exit", "person": "person:maud", "destination": None,
              "via": via}],
            present_ids={"person:maud"}, p=p)
        assert trace.cast_moves == [], via
        assert (("person:maud", via, reason) in trace.cast_move_drops), (via, reason)
        assert p.calls == []


def test_normalization_is_per_person_other_cast_unaffected():
    # one person's ambiguity never blocks another's clean move in the same batch.
    p = _FakeP(chains={"obj:cart": ["place:flat"]})
    trace, p = _lane(
        [{"kind": "bound_move", "person": "person:maud", "destination": "place:flat"},
         {"kind": "unbound_exit", "person": "person:maud", "destination": None,
          "via": "obj:cart"},
         {"kind": "unbound_exit", "person": "person:nell", "destination": None,
          "via": "obj:cart"}],
        present_ids={"person:maud", "person:nell"}, p=p)
    assert ("person:maud", "", "ambiguous_multiple_moves") in trace.cast_move_drops
    assert trace.cast_moves == [("unbound_exit", "person:nell", "")]


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
        # THE LEVER, END TO END (cr oracle): a re-entry briefing's situation lens must
        # light "Maud left" — the served away-`in` row's caused_by walks back to the
        # departed_scene event, whose EVENT rows surface in the snapshot.
        snap = world.porcelain.snapshot(["person:maud"], lens="situation")
        assert any(str(f["entity"]).startswith("event:departed_maud")
                   and f["attribute"] == "kind" and f["value"] == "departed_scene"
                   for f in snap.get("facts", [])), \
            "situation lens must surface the departure for re-entry coherence"

    def test_situation_lens_negative_control_no_caused_by_no_surface(self, world):
        # THE NEGATIVE CONTROL (cr re-review blocker): the exact twin of the positive
        # lever assertion above — same served away-`in` fact, same departed_scene event
        # rows, but the `in` row carries NO item-level caused_by. The situation lens
        # must EXCLUDE the event: this proves the positive test exercises the causal
        # lever itself, not incidental event retrieval.
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        from construct.arc.executor import turn_time as _tt
        ev = "event:departed_maud_2"
        world.porcelain.ingest_structured([
            {"entity": ev, "attribute": "kind", "value": "departed_scene",
             "valid_from": _tt(2)},
            {"entity": ev, "attribute": "agent", "value": "person:maud",
             "value_type": "entity", "valid_from": _tt(2)},
            {"entity": ev, "attribute": "patient", "value": "place:study",
             "value_type": "entity", "valid_from": _tt(2)},
            # the away-`in` row, WITHOUT caused_by — the one difference from the lane's
            # bound-departure commit.
            {"entity": "person:maud", "attribute": "in", "value": "place:flat",
             "value_type": "entity", "valid_from": _tt(2)},
        ], classify="rules")
        assert world.porcelain.locate("person:maud")[0] == "place:flat"  # served truth
        snap = world.porcelain.snapshot(["person:maud"], lens="situation")
        assert not any(str(f["entity"]).startswith("event:departed_maud")
                       for f in snap.get("facts", [])), \
            "without the caused_by lever the situation lens must NOT surface the event"

    def test_unbound_exit_the_maid_slips_out(self, world):
        # test bar 2b, NARROWED (§1.3, bar-11 live defect): a wholly-unbound destination
        # ("the passage beyond") is now an ACCEPTED FALSE NEGATIVE — no candidate, no
        # event, telemetry only ("by the hearth" is indistinguishable without semantics;
        # a false departed_scene is durable negative presence). The verified-container
        # twin below is the licensed exit path.
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
        assert r.trace.cast_moves == []                       # accepted false negative
        assert ("person:maud", "", "ambiguous_unbound_destination") in r.trace.cast_move_drops
        evs = PorcelainWorldReads(world).events(kind="departed_scene")
        assert not any("person:maud" in e.agents for e in evs)  # NO false departure
        assert world.porcelain.locate("person:maud")[0] == "place:study"

    def test_verified_container_exit_licenses_event_only(self, world):
        # §1.3: the destination binds to a physical NON-person object provably located
        # OUTSIDE the scene at _h — the ONE surviving event-only exit shape.
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")
        world.porcelain.ingest_structured([
            {"entity": "obj:well_cart", "attribute": "kind", "value": "cart", "timeless": True},
            {"entity": "obj:well_cart", "attribute": "name", "value": "the well cart"},
            {"entity": "obj:well_cart", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:maud", "attribute": "in", "value": "the well cart",
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
                {"prose": "Maud climbs onto the well cart and is gone."},
            ])
            r = run_turn(world, arc, provider, "I look over the desk.", turn=2,
                         scope=[PLAYER, "place:study", "obj:well_cart",
                                "person:maud", "person:nell"])
        finally:
            mp.undo()
        assert ("unbound_exit", "person:maud", "") in r.trace.cast_moves
        evs = PorcelainWorldReads(world).events(kind="departed_scene")
        assert any("person:maud" in e.agents for e in evs)
        # canon location UNCHANGED — stale by design (world-tick's to move later)
        assert world.porcelain.locate("person:maud")[0] == "place:study"

    def test_within_scene_position_never_a_departure(self, world):
        # §1.3 stay-by-hearth negative, the LIVE defect exactly: an object colocated
        # with the scene ("by the hearth") must never produce a departed_scene.
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")
        world.porcelain.ingest_structured([
            {"entity": "obj:hearth", "attribute": "kind", "value": "hearth", "timeless": True},
            {"entity": "obj:hearth", "attribute": "name", "value": "the hearth"},
            {"entity": "obj:hearth", "attribute": "in", "value": "place:study",
             "value_type": "entity"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:maud", "attribute": "in", "value": "the hearth",
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
                {"prose": "Maud stays by the hearth, saying nothing."},
            ])
            r = run_turn(world, arc, provider, "I look over the desk.", turn=2,
                         scope=[PLAYER, "place:study", "obj:hearth",
                                "person:maud", "person:nell"])
        finally:
            mp.undo()
        assert r.trace.cast_moves == []
        assert ("person:maud", "obj:hearth", "colocated_destination") in r.trace.cast_move_drops
        evs = PorcelainWorldReads(world).events(kind="departed_scene")
        assert not any("person:maud" in e.agents for e in evs)

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

    def test_nested_child_destination_no_false_departure_end_to_end(self, world):
        # BLOCKER 1, the reviewer's reproduced scenario against a REAL world: Maud present
        # in the study narrated moving to place:alcove NESTED UNDER the study — the move
        # commits but NO departed_scene event may appear (a false one at the same
        # coordinate as the new in-row suppressed someone still here).
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:alcove", "attribute": "kind", "value": "alcove",
             "timeless": True},
            {"entity": "place:alcove", "attribute": "in", "value": "place:study",
             "value_type": "entity"},
        ])
        _seed_person(world, "person:maud", "Maud", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")  # 2nd NPC: no only_one
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:maud", "attribute": "in", "value": "place:alcove",
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
                {"prose": "Maud steps into the alcove, still within earshot."},
            ])
            r = run_turn(world, arc, provider, "I read by the fire.", turn=2,
                         scope=[PLAYER, "place:study", "place:alcove",
                                "person:maud", "person:nell"])
        finally:
            mp.undo()
        assert ("bound_move", "person:maud", "place:alcove") in r.trace.cast_moves
        assert world.porcelain.locate("person:maud")[0] == "place:alcove"
        # the critical negative: NO departed_scene event — she is still within the scene
        evs = PorcelainWorldReads(world).events(kind="departed_scene")
        assert not any("person:maud" in e.agents for e in evs)

    def test_horizon_oracle_future_kind_place_cannot_license_bound_move(self, world):
        # bar 10, the KIND case (cr oracle addition): a place whose EVERY row is stamped
        # beyond the play horizon does not exist at `_h` — it can neither bind (the
        # resolver's candidate roster is horizon-bound) nor pass the lane's rule-3 head
        # re-verify. Under the §1.3 narrowing the unbindable destination is telemetry
        # only: no bound move, no event, nobody relocates, nothing minted.
        from construct.arc.executor import turn_time
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")  # 2nd NPC: no only_one
        world.porcelain.ingest_structured([
            {"entity": "place:future_hall", "attribute": "kind", "value": "hall",
             "valid_from": turn_time(999)},
            {"entity": "place:future_hall", "attribute": "name", "value": "Future Hall",
             "valid_from": turn_time(999)},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:maud", "attribute": "in", "value": "place:future_hall",
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
                {"prose": "Maud slips away toward the far hall."},
            ])
            r = run_turn(world, arc, provider, "I study the papers.", turn=2,
                         scope=[PLAYER, "place:study", "person:maud", "person:nell"],
                         horizon=turn_time(2))
        finally:
            mp.undo()
        assert r.trace.cast_moves == []                      # nothing licensed at all
        assert ("person:maud", "", "ambiguous_unbound_destination") in r.trace.cast_move_drops
        evs = PorcelainWorldReads(world).events(kind="departed_scene")
        assert not any("person:maud" in e.agents for e in evs)
        assert world.porcelain.locate("person:maud")[0] == "place:study"  # never relocated

    def test_only_one_addressed_engagement_protects_departure(self, world):
        # rule 5's only_one addressing source (cr oracle addition): the SOLE present NPC
        # questioned WITHOUT being named is still addressed — her narrated same-turn exit
        # is blocked (presence-holds).
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "person:maud", "attribute": "in", "value": "place:flat",
             "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "She answers curtly, then edges toward the flat."},
        ])
        r = run_turn(world, arc, provider, "What did you see out there?", turn=2,
                     scope=[PLAYER, "place:study", "place:flat", "person:maud"])
        assert not any(m[1] == "person:maud" for m in r.trace.cast_moves)
        assert ("person:maud", "place:flat", "engaged_this_turn") in r.trace.cast_move_drops
        assert world.porcelain.locate("person:maud")[0] == "place:study"

    def test_vocative_addressed_engagement_protects_departure(self, world):
        # rule 5's vocative addressing source (cr oracle addition): 'Chief!' resolves to
        # the canon title-holder — addressed without her name; her same-turn narrated exit
        # is blocked while the unaddressed second NPC's licenses.
        arc = make_arc()
        seed_arc(world, arc)
        _seed_person(world, "person:maud", "Maud", "place:study")
        _seed_person(world, "person:nell", "Nell", "place:study")
        world.porcelain.ingest_structured([
            {"entity": "person:maud", "attribute": "title", "value": "chief"},
        ])
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
                {"prose": "The chief stays at your elbow; Nell slips out to the flat."},
            ])
            r = run_turn(world, arc, provider, "Chief, what were your orders?", turn=2,
                         scope=[PLAYER, "place:study", "place:flat",
                                "person:maud", "person:nell"])
        finally:
            mp.undo()
        assert not any(m[1] == "person:maud" for m in r.trace.cast_moves)
        assert any(d[0] == "person:maud" and d[2] == "engaged_this_turn"
                   for d in r.trace.cast_move_drops)
        assert ("bound_move", "person:nell", "place:flat") in r.trace.cast_moves
        assert world.porcelain.locate("person:maud")[0] == "place:study"
