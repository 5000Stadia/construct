"""Story-shape layer (STORY-SHAPES.md): every game type resolves to one of the nine
blendable shapes, with the Cx-025 corrections (Mythic/Moral → Transformation), and the
romance 'no-clues' falsifier holds (Bond withholds intimacy, not an answer)."""
from construct import story_shapes as ss
from construct.play_styles_data import STYLE_CARDS

_SCHEMA_KEYS = {"medium", "withheld_kind", "commitment_kind", "judgment_type", "payoff_kind"}


def test_all_nine_shapes_have_full_schema():
    assert len(ss.SHAPES) == 9
    for name, prof in ss.SHAPES.items():
        assert _SCHEMA_KEYS <= set(prof), f"{name} missing schema keys"


def test_every_family_maps_to_a_valid_shape():
    families = {c["family"] for c in STYLE_CARDS.values()}
    assert len(families) == 19
    for fam in families:
        shape = ss.FAMILY_SHAPE.get(fam)
        assert shape in ss.SHAPES, f"family {fam!r} → {shape!r} not a valid shape"


def test_every_game_type_resolves_to_a_shape():
    for key in STYLE_CARDS:
        prof = ss.shape_for(key)
        assert prof and prof["shape"] in ss.SHAPES, f"{key} did not resolve"


def test_romance_is_bond_with_no_clue_trail():
    # The falsifier (founder): romance must NOT be a clue-trail. Bond withholds the
    # unearned intimacy, never "the answer," and its medium is emotional beats.
    prof = ss.shape_for("romance")
    assert prof["shape"] == "bond"
    assert prof["withheld_kind"] == "unearned_intimacy"
    assert "clue" not in prof["medium"].lower() and "evidence" not in prof["medium"].lower()
    assert prof["commitment_kind"] == "relational_state"   # not a claim:fact


def test_cx_corrections_mythic_and_moral_are_transformation():
    # Cx 025: Mythic (rite/fate/ordeal) and Moral/Psych drama are Transformation,
    # NOT Discovery/Bond.
    assert ss.shape_for("rite_of_passage")["shape"] == "transformation"
    moral = [k for k, v in STYLE_CARDS.items()
             if v["family"] == "Moral, Psychological & Literary Drama"]
    assert moral and ss.shape_for(moral[0])["shape"] == "transformation"


def test_mystery_is_deduction_and_blends_with_gambit():
    assert ss.shape_for("mystery_whodunnit")["shape"] == "deduction"
    # anchor's compound: mystery + political intrigue → deduction primary, gambit secondary
    blend = ss.shapes_for(["mystery_whodunnit", "political_intrigue"])
    assert blend["shape"] == "deduction"
    assert "gambit" in blend["secondary"]


def test_unknown_type_is_none():
    assert ss.shape_for("not_a_real_type") is None
    assert ss.shapes_for(["not_a_real_type"]) is None
    assert ss.shapes_for([]) is None


def test_shape_directive_is_genre_appropriate():
    # romance → bond discipline, NO clue language (the falsifier in directive form)
    rom = ss.shape_directive("romance")
    assert "bond" in rom.lower() and "rings hollow" in rom.lower()
    assert "lay a trail of clues" not in rom.lower()   # the deduction line is absent
    # mystery → clue/answer discipline
    myst = ss.shape_directive("mystery_whodunnit")
    assert "clues" in myst.lower() and "hidden answer" in myst.lower()
    # blend names both shapes
    blend = ss.shape_directive(["mystery_whodunnit", "political_intrigue"])
    assert "deduction" in blend and "gambit" in blend
    # unknown → empty
    assert ss.shape_directive("nope") == ""
