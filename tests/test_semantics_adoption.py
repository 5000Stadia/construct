"""RFC-001 adoption (PB 042): Construct's attribute_default rule makes
model-minted set-valued domain relations accumulate instead of
last-write — the cigarette-tin data-loss fix, verified end to end."""

from construct.game import _world
from construct.semantics import SET_VALUED_DOMAIN, attribute_default


def test_rule_is_conservative():
    assert attribute_default("contains") == {"arity": "set_valued"}
    assert attribute_default("has_part") == {"arity": "set_valued"}
    # functional/ambiguous attributes stay the engine default (None)
    assert attribute_default("status") is None
    assert attribute_default("in") is None          # containment core, untouched
    assert attribute_default("role") is None


def test_traversal_policy_attrs_are_structural_set_valued():
    # RFC-003 route() policy attributes: structural (no model classification)
    # + set-valued (route() needs all block-states). Structural is the bit that
    # keeps _declare_traversal_policy from calling the model at build time.
    for attr in ("blocks_when_state", "blocks_when_relation"):
        assert attribute_default(attr) == {"structural": True, "arity": "set_valued"}


def test_declare_traversal_policy_makes_no_model_call(tmp_path):
    # Regression for the build wedge (2026-06): declaring the policy on a world
    # with NO model must not raise / hang — structural attrs skip the classifier
    # model call. And the policy must be readable set-valued for route().
    from construct.game import (TRAVERSAL_BLOCK_STATES, _declare_traversal_policy)
    w = _world(tmp_path / "trav.world", "trav", model=None)  # None: a model call would raise
    try:
        _declare_traversal_policy(w)                          # must not raise
        states = {r.value for r in w.buffer.visible()
                  if r.entity == "traversal:door" and r.attribute == "blocks_when_state"}
        assert len(states) == len(TRAVERSAL_BLOCK_STATES)     # all coexist (set-valued)
    finally:
        w.close()


def test_set_valued_relation_keeps_all_members(tmp_path):
    # The five-cigarette tin: under last-write it kept one; with the rule
    # declaring `contains` set-valued, all five survive.
    w = _world(tmp_path / "tin.world", "tin", model=None)
    try:
        w.ingest_structured([
            {"entity": "obj:tin", "attribute": "kind", "value": "tin", "timeless": True},
            {"entity": "obj:cig1", "attribute": "kind", "value": "cig", "timeless": True},
            {"entity": "obj:cig2", "attribute": "kind", "value": "cig", "timeless": True},
            {"entity": "obj:cig3", "attribute": "kind", "value": "cig", "timeless": True},
            {"entity": "obj:tin", "attribute": "contains", "value": "obj:cig1", "value_type": "entity"},
            {"entity": "obj:tin", "attribute": "contains", "value": "obj:cig2", "value_type": "entity"},
            {"entity": "obj:tin", "attribute": "contains", "value": "obj:cig3", "value_type": "entity"},
        ])
        st = w.porcelain.state("obj:tin", "contains")
        # set-valued fold exposes all members (engine returns them in
        # `values`; tolerate either values-list or a multi-member shape).
        fact = st.get("fact") or {}
        members = fact.get("values")
        if members is None:                # fall back to snapshot membership
            snap = w.porcelain.snapshot(["obj:tin"])
            members = [f["value"] for f in snap.get("facts", [])
                       if f["entity"] == "obj:tin" and f["attribute"] == "contains"]
        assert set(members) == {"obj:cig1", "obj:cig2", "obj:cig3"}
    finally:
        w.close()
