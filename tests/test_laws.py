"""WORLD LAWS (#105, WORLD-LAWS.md, Cx 470) — the register gate, the
deterministic lint, the single-source renders, and the authoring loop."""

from construct import laws as laws_mod
from construct.laws import (
    FAMILY_PALETTE,
    allowed_registers,
    discovered_laws,
    embodiment_rows,
    law_lines,
    law_rows,
    laws_block,
    laws_from_meta,
    lint_laws,
    understood_laws,
)


def _law(**over) -> dict:
    base = {
        "name": "The Ledger of Hours", "register": "systemic",
        "rule": "every favor owed is recorded and must be repaid in kind",
        "cost_limit": "a debt unpaid compounds; defaulters lose standing",
        "embodiment": "the Clerks of the Ledger; the debtor courts",
        "texture": "ledger-slips, the phrase 'hours owed', ink-stained thumbs",
        "nearest_borrowed_shape": "a guild economy",
        "changed_consequence": "social rank is a running balance — a pauper "
                               "holding favors outranks an idle lord",
        "disclosure": "understood",
    }
    base.update(over)
    return base


class TestPaletteData:
    def test_palette_covers_every_card_family(self):
        # Cx 470 ruling 1: the palette is CANONICAL DATA beside the taxonomy —
        # a new family added to the cards must take a palette stance too.
        from construct.play_styles_data import STYLE_CARDS
        card_families = {c["family"] for c in STYLE_CARDS.values()}
        assert card_families == set(FAMILY_PALETTE)

    def test_real_register_never_allows_metaphysical_or_delta(self):
        # Test bar: a REAL Professional/Procedural build (A Few Good Men) may
        # author only sharpened-real registers — never the Force.
        allowed = allowed_registers(["Professional & Procedural Competence"], "real")
        assert "metaphysical" not in allowed and "delta" not in allowed
        assert "systemic" in allowed
        # even a mythic family is stripped to real-Earth registers in REAL
        allowed = allowed_registers(["Mythic, Spiritual & Symbolic"], "real")
        assert "metaphysical" not in allowed and "delta" not in allowed

    def test_alternate_adds_delta_keeps_earth_discipline(self):
        # Test bar: an ALTERNATE Earth authors its divergence AS a delta law;
        # bare metaphysical stays out (the delta itself carries the strange).
        allowed = allowed_registers(["Investigation & Epistemics"], "alternate")
        assert "delta" in allowed and "metaphysical" not in allowed

    def test_secondary_mythic_expects_metaphysical(self):
        allowed = allowed_registers(["Mythic, Spiritual & Symbolic"], "secondary")
        assert "metaphysical" in allowed
        assert "delta" not in allowed  # delta is the alternate-Earth register

    def test_secondary_rarely_family_keeps_domain_respect(self):
        # Sleepless in Seattle as a secondary world still gets no power system:
        # 'rarely'/'no' families exclude metaphysical even when invented.
        allowed = allowed_registers(["Social, Relationship & Intimacy"], "secondary")
        assert "metaphysical" not in allowed
        allowed = allowed_registers(["Professional & Procedural Competence"], "secondary")
        assert "metaphysical" not in allowed

    def test_no_family_falls_back_to_reality_defaults(self):
        assert allowed_registers([], "real") == {"systemic", "social", "environmental"}
        assert "delta" in allowed_registers([], "alternate")
        assert "metaphysical" in allowed_registers([], "secondary")


class TestLint:
    ALLOWED = {"systemic", "social", "environmental"}

    def test_clean_law_passes(self):
        assert lint_laws([_law()], self.ALLOWED) == []

    def test_register_gate_rejects_metaphysical_in_real(self):
        problems = lint_laws([_law(register="metaphysical")], self.ALLOWED)
        assert any("not permitted" in p for p in problems)

    def test_missing_part_flagged(self):
        problems = lint_laws([_law(cost_limit="")], self.ALLOWED)
        assert any("COST_LIMIT" in p for p in problems)

    def test_common_noun_name_rejected(self):
        problems = lint_laws([_law(name="the magic")], self.ALLOWED)
        assert any("proper" in p for p in problems)

    def test_calibration_copy_rejected(self):
        problems = lint_laws([_law(name="The Code")], self.ALLOWED)
        assert any("calibration" in p for p in problems)

    def test_texture_only_consequence_rejected(self):
        # Cx 470 ruling 2: 'changed_consequence == texture' is the shallow
        # deterministic half of the anti-trope bar.
        problems = lint_laws([_law(changed_consequence=_law()["texture"])],
                             self.ALLOWED)
        assert any("restates the TEXTURE" in p for p in problems)

    def test_borrowed_shape_needs_changed_consequence(self):
        problems = lint_laws([_law(changed_consequence="")], self.ALLOWED)
        assert any("changed_consequence" in p for p in problems)

    def test_disclosure_required(self):
        problems = lint_laws([_law(disclosure="")], self.ALLOWED)
        assert any("disclosure" in p for p in problems)

    def test_more_than_four_laws_rejected(self):
        five = [_law(name=f"The Rite of {n}") for n in
                ("Ash", "Salt", "Iron", "Glass", "Bone")]
        problems = lint_laws(five, self.ALLOWED)
        assert any("1-4" in p for p in problems)

    def test_no_laws_is_clean(self):
        assert lint_laws([], self.ALLOWED) == []


class TestRenders:
    def test_laws_block_carries_all_five_parts(self):
        block = laws_block([_law()])
        for frag in ("The Ledger of Hours", "systemic", "must be repaid",
                     "COST/LIMIT", "EMBODIED BY", "TEXTURE"):
            assert frag in block

    def test_disclosure_split(self):
        laws = [_law(), _law(name="The Undertow", disclosure="discovered")]
        assert [law["name"] for law in understood_laws(laws)] == ["The Ledger of Hours"]
        assert [law["name"] for law in discovered_laws(laws)] == ["The Undertow"]
        # briefing lane: the hidden law binds silently under the weave directive
        lane = law_lines(laws)
        assert lane.index("The Ledger of Hours") < lane.index("STILL UNDISCOVERED")
        assert "The Undertow" in lane.split("STILL UNDISCOVERED")[1]
        # adjudication block: the hidden law is tagged, still fully present
        assert "UNDISCOVERED" in laws_block(laws)

    def test_empty_laws_render_empty(self):
        assert laws_block([]) == "" and law_lines([]) == ""


class TestCanonRows:
    def test_law_rows_explicit_and_boring(self):
        rows = law_rows([_law()])
        by_attr = {r["attribute"]: r for r in rows}
        assert by_attr["kind"]["value"] == "world_law"
        assert by_attr["kind"]["entity"] == "law:the_ledger_of_hours"
        for attr in ("name", "register", "rule", "cost_limit", "texture",
                     "disclosure"):
            assert attr in by_attr

    def test_embodiment_rows_filter_unknown_targets(self):
        laws = [_law()]
        links = [{"law": "The Ledger of Hours", "embodied_by": "person:clerk"},
                 {"law": "The Ledger of Hours", "embodied_by": "person:ghost"},
                 {"law": "No Such Law", "embodied_by": "person:clerk"}]
        rows = embodiment_rows(laws, links, {"person:clerk"})
        assert len(rows) == 1
        assert rows[0] == {"entity": "law:the_ledger_of_hours",
                           "attribute": "embodied_by", "value": "person:clerk",
                           "value_type": "entity", "timeless": True}

    def test_laws_from_meta_tolerant(self):
        assert laws_from_meta(None) == []
        assert laws_from_meta({"laws": "garbage"}) == []
        assert laws_from_meta({"laws": [_law(), "junk"]}) == [_law()]


class TestAuthoringLoop:
    def test_lint_failure_retries_then_ships_clean(self):
        # _author_world_laws: attempt 1 fails the register gate (metaphysical
        # in a REAL world), the feedback retry ships a systemic law; the
        # critic's silent default passes it.
        from construct.game import _author_world_laws
        from construct.provider import StubProvider
        provider = StubProvider([
            {"reality_register": "real", "laws": [_law(register="metaphysical")]},
            {"reality_register": "real", "laws": [_law()]},
        ])
        laws, reality = _author_world_laws(
            provider, "a courtroom drama", "real",
            [])
        assert reality == "real"
        assert [law["name"] for law in laws] == ["The Ledger of Hours"]

    def test_no_laws_is_an_honest_answer(self):
        from construct.game import _author_world_laws
        from construct.provider import StubProvider
        provider = StubProvider([{"reality_register": "real", "laws": []}])
        laws, reality = _author_world_laws(provider, "a quiet afternoon", "real", [])
        assert laws == [] and reality == "real"

    def test_author_failure_fails_open(self):
        from construct.game import _author_world_laws
        from construct.provider import StubProvider
        laws, reality = _author_world_laws(
            StubProvider([{"unexpected": True}]), "x", "secondary", [])
        assert laws == [] and reality == "secondary"


class TestCriticExhaustion:
    # Cx 475 blocker: the critic's semantic judgment is never bypassed by
    # retry exhaustion — a survivor needs lint AND a passing critic verdict.

    def _author(self, name="The Ledger of Hours"):
        return {"reality_register": "real", "laws": [_law(name=name)]}

    def test_critic_rejects_all_retries_ships_no_laws(self):
        from construct.game import _author_world_laws
        from construct.provider import StubProvider
        reject = {"verdicts": [{"name": "The Ledger of Hours", "passes": False,
                                "problem": "a guild economy wearing new words"}]}
        provider = StubProvider([self._author(), dict(reject),
                                 self._author(), dict(reject),
                                 self._author(), dict(reject)])
        laws, reality = _author_world_laws(provider, "a trade city", "real", [])
        assert laws == []                       # lint-clean but critic-rejected
        assert reality == "real"

    def test_partial_critic_pass_ships_only_the_pass(self):
        from construct.game import _author_world_laws
        from construct.provider import StubProvider
        two = {"reality_register": "real",
               "laws": [_law(), _law(name="The Salt Concord",
                                     rule="no violence between salt-sharers",
                                     changed_consequence="hospitality is a "
                                                         "weaponizable jurisdiction")]}
        verdict = {"verdicts": [
            {"name": "The Ledger of Hours", "passes": True, "problem": ""},
            {"name": "The Salt Concord", "passes": False,
             "problem": "guest-right re-textured"}]}
        provider = StubProvider([dict(two), dict(verdict),
                                 dict(two), dict(verdict),
                                 dict(two), dict(verdict)])
        laws, _ = _author_world_laws(provider, "a trade city", "real", [])
        assert [law["name"] for law in laws] == ["The Ledger of Hours"]


class TestRealityLine:
    def test_reality_line_per_register(self):
        from construct.laws import reality_line
        assert "REAL" in reality_line("real")
        assert "ALTERNATE" in reality_line("alternate")
        assert "police that seam" in reality_line("alternate")
        assert "SECONDARY" in reality_line("secondary")
        assert reality_line("") == "" and reality_line("dreamlike") == ""
