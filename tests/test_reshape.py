"""World-changing agency — the pure canon-reshape commit helper.

Covers the helper-level guardrails from Cx 198: append (not retract) lived canon,
a caused_by reshape event, scoped re-staging + frame knowledge, and the tier→land
mapping (success lands; failure commits a consequence without flipping the target).
Deterministic — no model, no prose.
"""

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import PorcelainWorldReads
from construct.arc.executor import turn_time
from construct.reshape import ReshapePlan, plan_from_proposal, reshape_canon


def _world(path) -> World:
    """A tiny world with a DEAD victim committed as lived canon at turn 0."""
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id="w:reshape", model=StubModel(fallback=fallback),
              stance="fiction", title="Reshape Test World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:oil_store", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:angus", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:angus", "attribute": "alive", "value": "false", "valid_from": turn_time(0)},
    ])
    return w


def _revive_plan(tier="complete_success") -> ReshapePlan:
    return ReshapePlan(
        slug="angus_revived",
        action_event="event:action_5",
        tier=tier,
        state_rows=[{"entity": "person:angus", "attribute": "alive", "value": "true"}],
        restage_rows=[{"entity": "person:angus", "attribute": "in", "value": "place:oil_store"}],
        frame_rows=[
            {"frame": "knows:person:angus", "entity": "fact:attacker",
             "attribute": "kind", "value": "proposition", "timeless": True},
            {"frame": "knows:person:angus", "entity": "fact:attacker",
             "attribute": "identity", "value": "person:niall"},
        ],
        summary="Angus draws breath and lives — and remembers the hands at his throat.",
    )


def test_reshape_appends_new_state_without_retracting_lived_canon(tmp_path):
    w = _world(tmp_path / "r.world")
    reshape_canon(w, _revive_plan(), turn=5)
    reads = PorcelainWorldReads(w)
    assert reads.state("person:angus", "alive") == "true"           # current truth flipped
    # APPEND, not retract (Cx 198 #2): the original 'dead' row must still be in the
    # log, so a historical as-of read before turn 5 still folds to dead.
    dead_rows = [r for r in w.buffer.all_rows()
                 if getattr(r, "attribute", None) == "alive"
                 and getattr(r, "value", None) == "false"]
    assert dead_rows, "the prior 'dead' row must remain (append, not retract)"
    w.close()


def test_reshape_mints_event_with_caused_by_and_restages(tmp_path):
    w = _world(tmp_path / "r2.world")
    res = reshape_canon(w, _revive_plan(), turn=5)
    reads = PorcelainWorldReads(w)
    assert res.event_id == "event:reshaped_angus_revived"
    # the reshape event is a canon event with an explicit caused_by → the action
    evs = reads.events(kind="canon_reshape")
    assert [e.event_id for e in evs] == ["event:reshaped_angus_revived"]
    assert "event:action_5" in evs[0].caused_by
    # re-staged → now locatable in the world
    assert "place:oil_store" in (reads.location_chain("person:angus") or [])
    w.close()


def test_reshape_seeds_only_scoped_witness_knowledge(tmp_path):
    w = _world(tmp_path / "r3.world")
    reshape_canon(w, _revive_plan(), turn=5)
    reads = PorcelainWorldReads(w)
    # the sanctioned witness fact lands in Angus's OWN frame…
    assert reads.state("fact:attacker", "identity",
                       frame="knows:person:angus") == "person:niall"
    # …and does NOT leak into canon (scoped, not a blanket mirror of hidden truth).
    assert reads.state("fact:attacker", "identity") is None
    w.close()


def test_failure_tier_does_not_flip_target_but_commits_consequence(tmp_path):
    w = _world(tmp_path / "r4.world")
    plan = _revive_plan(tier="terrible_failure")
    plan.consequence_rows = [{"entity": "person:angus", "attribute": "condition",
                              "value": "desecrated"}]
    res = reshape_canon(w, plan, turn=5)
    reads = PorcelainWorldReads(w)
    assert res.landed is False
    assert reads.state("person:angus", "alive") == "false"            # target NOT flipped
    assert reads.state("person:angus", "condition") == "desecrated"   # but a consequence landed
    assert reads.events(kind="canon_reshape")                          # the attempt itself is canon
    # a failed attempt seeds no witness frame (no revived entity to know)
    assert reads.state("fact:attacker", "identity", frame="knows:person:angus") is None
    w.close()


def test_success_cost_lands_the_target_and_a_cost(tmp_path):
    w = _world(tmp_path / "r5.world")
    plan = _revive_plan(tier="success_cost")
    plan.consequence_rows = [{"entity": "person:angus", "attribute": "condition", "value": "fading"}]
    res = reshape_canon(w, plan, turn=5)
    reads = PorcelainWorldReads(w)
    assert res.landed is True
    assert reads.state("person:angus", "alive") == "true"     # the miracle lands…
    assert reads.state("person:angus", "condition") == "fading"  # …at a cost
    w.close()


# --- plan_from_proposal: the model→typed bridge (mirrors cast_from_proposal) ---

def test_plan_from_proposal_builds_a_typed_plan_end_to_end(tmp_path):
    proposal = {
        "slug": "angus revived!",
        "target": {"entity": "person:angus", "attribute": "alive", "value": "true"},
        "restage": [{"entity": "person:angus", "attribute": "in", "value": "place:oil_store"}],
        "frame_knowledge": [{"npc": "person:angus", "entity": "fact:attacker",
                             "attribute": "identity", "value": "person:niall"}],
        "summary": "Angus draws breath.",
    }
    plan = plan_from_proposal(proposal, tier="complete_success", turn=5)
    assert plan is not None
    assert plan.slug == "angus_revived"                       # sanitized
    assert plan.action_event == "event:action_5"             # derived from turn
    assert plan.state_rows == [{"entity": "person:angus", "attribute": "alive", "value": "true"}]
    assert plan.frame_rows[0]["frame"] == "knows:person:angus"  # npc → frame
    # it actually commits through the helper
    w = _world(tmp_path / "p.world")
    reshape_canon(w, plan, turn=5)
    assert PorcelainWorldReads(w).state("person:angus", "alive") == "true"
    w.close()


def test_plan_from_proposal_returns_none_without_a_concrete_target():
    # No usable target state change → not a reshape; the turn plays normally.
    assert plan_from_proposal({}, tier="complete_success") is None
    assert plan_from_proposal({"target": {"entity": "x"}}, tier="complete_success") is None
    assert plan_from_proposal("not a dict", tier="complete_success") is None


def test_plan_from_proposal_drops_malformed_optional_rows():
    proposal = {
        "target": {"entity": "person:angus", "attribute": "alive", "value": "true"},
        "restage": [{"entity": "person:angus"}, {"bad": "row"}],     # both malformed
        "frame_knowledge": [{"npc": "person:angus", "entity": "fact:x"}],  # missing attr/value
    }
    plan = plan_from_proposal(proposal, tier="complete_success", action_event="event:action_9")
    assert plan is not None
    assert plan.restage_rows == []        # malformed dropped, no crash
    assert plan.frame_rows == []
    assert plan.action_event == "event:action_9"  # explicit anchor wins
