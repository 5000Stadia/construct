"""Game-type directives loaded from the curated taxonomy (GAME-TYPES.md), incl.
MIXING a primary + secondary type into one blended directive."""

from construct import play_styles


def test_taxonomy_loaded():
    from construct.play_styles_data import STYLE_CARDS
    assert len(STYLE_CARDS) >= 150
    assert "heist" in STYLE_CARDS and "mystery_whodunnit" in STYLE_CARDS


def test_single_type_returns_its_directive():
    d = play_styles.directive_for("heist")
    assert d and d.startswith("PLAY STYLE — HEIST")


def test_unknown_or_empty_is_free_improvised():
    assert play_styles.directive_for(None) is None
    assert play_styles.directive_for("not_a_type") is None
    assert play_styles.directive_for([]) is None


def test_mix_blends_multiple_directives():
    d = play_styles.directive_for(["heist", "social_deduction_impostor_hunt"])
    assert d is not None
    assert "BLENDS" in d                       # the blend preamble
    assert "PLAY STYLE — HEIST" in d           # both directives present
    assert d.count("PLAY STYLE —") >= 2


def test_mix_drops_unknowns_and_dedupes():
    keys = play_styles.resolve(["heist", "heist", "nonsense", "mystery_whodunnit"])
    assert keys == ["heist", "mystery_whodunnit"]


def test_names_are_human_facing():
    assert play_styles.names(["heist"]) == ["Heist"]
