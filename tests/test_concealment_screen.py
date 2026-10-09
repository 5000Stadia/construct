"""Concealment vocabulary (arc.executor): the protagonist's own name is never concealed by
the placeholder premise, genuinely hidden facts stay concealed, and the leak screen is
punctuation-proof."""

from construct.arc.conditions import InFrame, Occurred, StateIs
from construct.arc.executor import arc_protected_keys, concealed_tokens, value_leaks
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight

PROT = "person:edith_marlowe"


def _arc(premise) -> Arc:
    cond = InFrame(f"knows:{PROT}", "fact:secret", "culprit", "person:rival")
    beat = Beat("beat:learn", Phase.CLIMAX, Weight.REQUIRED, achievable_via=cond)
    shape = ConclusionShape(
        "shape:main", "drive_inverted", (PROT, "drive:a", "drive:b"),
        world_condition=cond, premise=premise, refusal_variant_id="shape:refused")
    refusal = Clock("clock:refusal", Occurred("event:abandoned"),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    return Arc(arc_id="arc:main", protagonist=PROT, shape=shape, beats=(beat,),
               clocks=(), refusal_clock=refusal,
               climax_ready_k=1, climax_ready_beats=("beat:learn",))


def test_placeholder_premise_does_not_conceal_the_protagonists_name():
    # game._build_arc stamps StateIs(protagonist, "kind", "person") on EVERY arc.
    arc = _arc(StateIs(PROT, "kind", "person"))
    keys = arc_protected_keys(arc)
    assert (PROT, "kind") not in keys
    toks = concealed_tokens(keys)
    assert "edith" not in toks and "marlowe" not in toks
    assert not value_leaks("Edith Marlowe has been your oldest friend", toks)
    # the real hidden answer is still concealed
    assert ("fact:secret", "culprit") in keys
    assert value_leaks("she knows who the culprit is", toks)


def test_genuine_protagonist_secret_stays_concealed():
    # A premise that genuinely turns on the protagonist is NOT the placeholder.
    arc = _arc(StateIs(PROT, "secret_parentage", "person:the_duke"))
    keys = arc_protected_keys(arc)
    assert (PROT, "secret_parentage") in keys
    toks = concealed_tokens(keys)
    assert "parentage" in toks
    assert value_leaks("a rumour about her parentage", toks)
    # same entity and attribute as the placeholder but a different value: kept
    assert (PROT, "kind") in arc_protected_keys(_arc(StateIs(PROT, "kind", "changeling")))


def test_placeholder_on_another_entity_is_not_special_cased():
    arc = _arc(StateIs("person:stranger", "kind", "person"))
    assert ("person:stranger", "kind") in arc_protected_keys(arc)


def test_value_leaks_is_punctuation_proof():
    toks = {"culprit", "hatchet"}
    for text in ("he named the culprit, then left", "the culprit.", "(culprit)",
                 "the hatchet; the rope", "'hatchet'", "the culprit!"):
        assert value_leaks(text, toks), text
    # id-style text and plain text still behave
    assert value_leaks("fact:culprit", toks)
    assert value_leaks("the_hatchet", toks)
    assert not value_leaks("he named nobody, then left", toks)
    assert not value_leaks("anything at all", set())
