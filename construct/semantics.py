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


def attribute_default(attribute: str) -> dict | None:
    """The engine consults this for an attribute with no explicit
    declaration. Return set-valued arity for inherently many-valued
    domain relations; None (engine default: functional/last-write) for
    everything else. Engine-structural attributes (`in`, `connects_to`,
    `kind`, …) are never in our set, so the built-in semantics stand."""
    if attribute in SET_VALUED_DOMAIN:
        return {"arity": "set_valued"}
    return None
