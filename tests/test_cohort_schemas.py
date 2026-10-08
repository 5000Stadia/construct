"""Cohort output-schema self-consistency (pbeo review 2026-07-28, Item 4; audit
2026-10 finding 12).

pbeo's exact failure mode - a field the schema REQUIRES that every few-shot
EXAMPLE omits - has no surface in Construct: cohort examples are prose inside
prompt strings, not structured payloads handed to the model. The automatable
cousin that DOES apply is a mechanical guard run against the schema itself
rather than a reviewer's attention.

The rule lives in ONE place, ``construct.provider.lint_schema`` ("required" names
must appear in "properties", an array must declare "items"); it also runs on
every ``complete_sync`` call. This test only sweeps every ``*SCHEMA`` constant in
``construct.cohorts`` through it, so a defective schema fails here and never on a
live call, and keeps the "the sweep actually found schemas" sanity check.
"""

import construct.cohorts as cohorts
from construct.provider import lint_schema


def _schema_constants():
    for name in dir(cohorts):
        if name.endswith("SCHEMA"):
            obj = getattr(cohorts, name)
            if isinstance(obj, dict):
                yield name, obj


def test_there_are_schema_constants_to_check():
    # guard against the sweep silently finding nothing (a passing check that
    # checks nothing is worse than no check - pbeo lesson 4).
    names = [n for n, _ in _schema_constants()]
    assert len(names) >= 30, names


def test_every_cohort_schema_passes_the_provider_lint():
    """No cohort schema may require a field its `properties` block doesn't
    describe, or declare an array without `items`, at any nesting depth."""
    for name, schema in _schema_constants():
        lint_schema(schema, path=name)
