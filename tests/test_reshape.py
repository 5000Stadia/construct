"""World-changing agency — the pure canon-reshape commit helper.

Covers the helper-level guardrails from Cx 198: append (not retract) lived canon,
a caused_by reshape event, scoped re-staging + frame knowledge, and the tier→land
mapping (success lands; failure commits a consequence without flipping the target).
Deterministic — no model, no prose.
"""

import pytest
from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import PorcelainWorldReads
from construct.arc.executor import turn_time
from construct.reshape import (
    ReshapePlan, apply_reshape, plan_from_proposal, reshape_canon)


_REVIVE_PROPOSAL = {
    "is_reshape": True, "slug": "angus_revived",
    "target": {"entity": "person:angus", "attribute": "alive", "value": "true"},
    "restage": [{"entity": "person:angus", "attribute": "in", "value": "place:oil_store"}],
    "frame_knowledge": [{"npc": "person:angus", "entity": "fact:attacker",
                         "attribute": "identity", "value": "person:niall"}],
    "consequence": [], "summary": "Angus draws breath and lives.",
}


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
        {"entity": "person:angus", "attribute": "name", "value": "Angus", "timeless": True},
        {"entity": "person:angus", "attribute": "alive", "value": "false", "valid_from": turn_time(0)},
        {"entity": "person:niall", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:niall", "attribute": "name", "value": "Niall", "timeless": True},
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
    # APPEND, not retract (Cx 198 #2): a historical as-of read BEFORE the reshape
    # turn still folds to dead; only the current read is alive.
    assert w.porcelain.state("person:angus", "alive",
                             as_of=turn_time(0))["fact"]["value"] == "false"
    assert w.porcelain.state("person:angus", "alive")["fact"]["value"] == "true"
    # and the original 'dead' row is still physically in the log (not retracted).
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


def test_reshape_fails_closed_on_an_unscoped_frame_row_committing_nothing(tmp_path):
    # Cx 200: a frame_row missing its scoped 'knows:<npc>' frame must NOT leak the
    # hidden fact to canon — the helper rejects the whole plan before any commit.
    w = _world(tmp_path / "rf.world")
    plan = _revive_plan()
    plan.frame_rows = [{"entity": "fact:attacker", "attribute": "identity",
                        "value": "person:niall"}]  # no 'frame' → would default to canon
    with pytest.raises(ValueError):
        reshape_canon(w, plan, turn=5)
    reads = PorcelainWorldReads(w)
    assert reads.state("fact:attacker", "identity") is None          # NOT leaked to canon
    assert reads.state("person:angus", "alive") == "false"           # nothing committed at all
    assert not reads.events(kind="canon_reshape")                    # no partial write
    w.close()


def test_plan_from_proposal_returns_none_without_a_concrete_target():
    # No usable target state change → not a reshape; the turn plays normally.
    assert plan_from_proposal({}, tier="complete_success") is None
    assert plan_from_proposal({"target": {"entity": "x"}}, tier="complete_success") is None
    assert plan_from_proposal("not a dict", tier="complete_success") is None


def test_propose_reshape_cohort_flows_through_to_a_commit(tmp_path):
    # The cohort proposes a structured reshape; it must flow cleanly through
    # plan_from_proposal -> reshape_canon (the model→typed→canon chain).
    from construct import cohorts
    from construct.provider import StubProvider
    p = StubProvider([{
        "is_reshape": True, "slug": "angus_revived",
        "target": {"entity": "person:angus", "attribute": "alive", "value": "true"},
        "restage": [{"entity": "person:angus", "attribute": "in", "value": "place:oil_store"}],
        "frame_knowledge": [{"npc": "person:angus", "entity": "fact:attacker",
                             "attribute": "identity", "value": "person:niall"}],
        "consequence": [], "summary": "Angus draws a ragged breath and lives.",
    }])
    proposal = cohorts.propose_reshape(
        p, action="I pour everything into reviving him", scene="the oil store",
        canon="person:angus.alive = false", outcome="complete_success")
    assert proposal["is_reshape"] is True
    plan = plan_from_proposal(proposal, tier="complete_success", turn=5)
    assert plan is not None and plan.slug == "angus_revived"
    w = _world(tmp_path / "c.world")
    reshape_canon(w, plan, turn=5)
    reads = PorcelainWorldReads(w)
    assert reads.state("person:angus", "alive") == "true"
    assert reads.state("fact:attacker", "identity", frame="knows:person:angus") == "person:niall"
    w.close()


def test_apply_reshape_off_by_default_is_a_no_op(tmp_path):
    # Flag off → no reshape, regardless of what the (unused) provider would say.
    from construct.provider import StubProvider
    w = _world(tmp_path / "off.world")
    res = apply_reshape(w, StubProvider([_REVIVE_PROPOSAL]),
                        action="I revive him", scene="oil store",
                        canon="angus dead", tier="complete_success", turn=5, enabled=False)
    assert res is None
    assert PorcelainWorldReads(w).state("person:angus", "alive") == "false"  # untouched
    w.close()


def test_apply_reshape_enabled_commits_the_change(tmp_path):
    from construct.provider import StubProvider
    w = _world(tmp_path / "on.world")
    res = apply_reshape(w, StubProvider([_REVIVE_PROPOSAL]),
                        action="I pour everything into reviving him", scene="oil store",
                        canon="person:angus.alive = false", tier="complete_success",
                        turn=5, enabled=True)
    assert res is not None and res.landed is True
    assert res.summary == "Angus draws breath and lives."     # briefing directive for the narrator
    assert PorcelainWorldReads(w).state("person:angus", "alive") == "true"
    w.close()


def test_apply_reshape_canonicalizes_a_bare_target_id(tmp_path):
    # Cx 226: the cohort may propose a BARE id ('angus') when the world's victim is the
    # canonical 'person:angus'. apply_reshape must canonicalize via world.refer before
    # commit, so the reshaped state lands on ONE id, not a coreferent alias.
    from construct.provider import StubProvider
    w = _world(tmp_path / "canon.world")
    bare = dict(_REVIVE_PROPOSAL)
    bare["target"] = {"entity": "angus", "attribute": "alive", "value": "true"}  # bare, no prefix
    bare["restage"] = [{"entity": "angus", "attribute": "in", "value": "place:oil_store"}]
    bare["frame_knowledge"] = []
    res = apply_reshape(w, StubProvider([bare]), action="I revive him", scene="oil store",
                        canon="person:angus.alive=false", tier="complete_success",
                        turn=5, enabled=True)
    assert res is not None and res.landed
    reads = PorcelainWorldReads(w)
    assert reads.state("person:angus", "alive") == "true"   # landed on the CANONICAL id
    assert reads.state("angus", "alive") is None            # NOT on the bare alias
    w.close()


def test_apply_reshape_canonicalizes_a_bare_relation_value(tmp_path):
    # Cx 228: a relation VALUE that names an existing entity (a bare witness 'niall')
    # is canonicalized too — not just the row subject — so the reference can't scatter
    # onto an alias. A literal state value ('true') resolves to no entity → kept as-is.
    from construct.provider import StubProvider
    w = _world(tmp_path / "val.world")
    prop = dict(_REVIVE_PROPOSAL)
    prop["frame_knowledge"] = [{"npc": "person:angus", "entity": "fact:attacker",
                                "attribute": "identity", "value": "niall"}]  # bare value
    res = apply_reshape(w, StubProvider([prop]), action="I revive him", scene="oil store",
                        canon="", tier="complete_success", turn=5, enabled=True)
    assert res is not None and res.landed
    reads = PorcelainWorldReads(w)
    assert reads.state("person:angus", "alive") == "true"   # literal value kept (not canonicalized)
    # the witness fact's VALUE is canonicalized to the real person id, not the bare alias
    assert reads.state("fact:attacker", "identity",
                       frame="knows:person:angus") == "person:niall"
    w.close()


def test_apply_reshape_returns_none_when_cohort_declines(tmp_path):
    from construct.provider import StubProvider
    w = _world(tmp_path / "decline.world")
    res = apply_reshape(w, StubProvider([{"is_reshape": False, "slug": "", "target": {},
                                          "restage": [], "frame_knowledge": [],
                                          "consequence": [], "summary": ""}]),
                        action="I look around", scene="oil store", canon="",
                        tier="complete_success", turn=5, enabled=True)
    assert res is None
    assert PorcelainWorldReads(w).state("person:angus", "alive") == "false"
    w.close()


def test_apply_reshape_fails_open_on_a_provider_error(tmp_path):
    class _Boom:
        def complete(self, *a, **k):
            raise RuntimeError("model down")
    w = _world(tmp_path / "boom.world")
    # a provider that raises must not sink the turn — returns None, world untouched
    res = apply_reshape(w, _Boom(), action="I revive him", scene="oil store",
                        canon="", tier="complete_success", turn=5, enabled=True)
    assert res is None
    assert PorcelainWorldReads(w).state("person:angus", "alive") == "false"
    w.close()


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
