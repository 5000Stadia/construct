"""Construct's attribute-semantics rule for pattern-buffer's RFC-001
`attribute_default` hook (PB letter 042).

A live-IF host's domain vocabulary is MODEL-MINTED at play time — the
extractor invents relations like `contains`, `has_part`, `took_up_with`
as the story moves. The inherently many-valued ones (a container holds
many things; a person acquires many objects; you know many people) must
ACCUMULATE, not last-write — otherwise data is silently dropped (the
five-cigarette tin keeping one). The engine can't know which model-minted
relation is many-valued; this rule states it once at the ingest boundary
and the engine records it on first sight (genesis-forward, immutable
after).

Conservative by design: only relations that are *inherently* one-subject-
many-objects are declared set-valued; everything else keeps the engine's
functional default (so a misjudged `status`/`role` can't accumulate stale
values). Easy to extend as play surfaces new vocabulary.
"""

from __future__ import annotations

#: Inherently many-valued domain relations (subject → many objects).
SET_VALUED_DOMAIN = frozenset({
    # container / composition, parent-side
    "contains", "has_part", "has", "holds", "comprises", "includes",
    "encloses", "stores", "contained",
    # possession / acquisition
    "took_up_with", "gave", "carries", "owns", "possesses", "keeps",
    "took", "received", "acquired", "stole",
    # association (genuinely plural)
    "knows", "allied_with", "met", "employs", "trusts", "serves_under",
})

#: Traversal-policy attributes (RFC-003 route()) — declared STRUCTURAL (no
#: model classification) + set-valued (a portal kind blocks on several states).
POLICY_STRUCTURAL_SET_VALUED = frozenset({"blocks_when_state", "blocks_when_relation"})

#: Immutable arc-bookkeeping ENUMS — declared STRUCTURAL so they fold
#: deterministically and never reach the durability model. The model can
#: nondeterministically classify a standing value like `rung="refusal"` as EVENT
#: ("the refusal was *rung*" reads as an occurrence), and an EVENT verdict
#: ERASES the row from every fold (state/current_state/materialize) while it
#: lingers in the raw buffer — silently dropping a beat/clock at world scale
#: (PB 066, confirmed). `is_structural` short-circuits to CONSTITUTIVE before
#: any model call, so these can't be flipped. MUTABLE arc attrs (`status`,
#: `phase`) are deliberately excluded — they legitimately change.
ARC_STRUCTURAL_ENUMS = frozenset({
    "rung", "rearm", "beat_phase", "weight", "delta_type", "refusal_variant",
    "scope_kind",
})


def attribute_default(attribute: str) -> dict | None:
    """The engine consults this for an attribute with no explicit
    declaration. Return set-valued arity for inherently many-valued
    domain relations; None (engine default: functional/last-write) for
    everything else. Engine-structural attributes (`in`, `connects_to`,
    `kind`, …) are never in our set, so the built-in semantics stand.

    The traversal-policy attributes are declared STRUCTURAL + set-valued: a
    portal kind blocks on several states (route() must see them all), and
    structural-ness keeps `_declare_traversal_policy`'s rows from triggering a
    per-row classifier MODEL call at build time — which on a flaky provider can
    hang the whole build (the traversal-policy wedge, 2026-06). No model = no
    hang; the classifier treats a structural attribute as constitutive."""
    if attribute in POLICY_STRUCTURAL_SET_VALUED:
        return {"structural": True, "arity": "set_valued"}
    if attribute in ARC_STRUCTURAL_ENUMS:
        return {"structural": True}
    if attribute in SET_VALUED_DOMAIN:
        return {"arity": "set_valued"}
    return None
