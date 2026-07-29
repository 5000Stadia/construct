"""Cohort output-schema self-consistency (pbeo review 2026-07-28, Item 4).

pbeo's exact failure mode — a field the schema REQUIRES that every few-shot
EXAMPLE omits — has no surface in Construct: cohort examples are prose inside
prompt strings, not structured payloads handed to the model. The automatable
cousin that DOES apply is the mechanical check pbeo actually advocated: run a
guard against the schema itself rather than a reviewer's attention.

This pins the one class of schema bug that is silently latent otherwise — a
``required`` field the ``properties`` block never describes, so the model is told
to emit a field the schema can't validate (or a typo'd requirement). It walks
every ``*_SCHEMA`` constant in ``construct.cohorts`` recursively (nested objects
and array ``items`` included).
"""

import construct.cohorts as cohorts


def _walk_object_schemas(node, path):
    """Yield (path, required_set, property_names) for every object-typed schema
    reachable from `node` (recursing through properties and array items)."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            props = node.get("properties") or {}
            yield path, set(node.get("required") or []), set(props.keys())
        for key, value in node.items():
            yield from _walk_object_schemas(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk_object_schemas(value, f"{path}[{i}]")


def _schema_constants():
    for name in dir(cohorts):
        if name.endswith("SCHEMA"):
            obj = getattr(cohorts, name)
            if isinstance(obj, dict):
                yield name, obj


def test_there_are_schema_constants_to_check():
    # guard against the walker silently finding nothing (a passing check that
    # checks nothing is worse than no check — pbeo lesson 4).
    names = [n for n, _ in _schema_constants()]
    assert len(names) >= 30, names


def test_every_required_field_is_declared_in_properties():
    """No cohort schema may require a field its `properties` block doesn't
    describe, at any nesting depth."""
    offenders = []
    for name, schema in _schema_constants():
        for path, required, props in _walk_object_schemas(schema, name):
            missing = required - props
            if missing:
                offenders.append(f"{path}: required-not-in-properties {sorted(missing)}")
    assert not offenders, "schema self-inconsistency:\n" + "\n".join(offenders)
