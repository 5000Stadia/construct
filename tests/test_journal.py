"""The case-board notebook (#83): pure-formatter tests for construct/journal.py —
the protagonist's `knows:` frame rendered as their diegetic notebook."""

from dataclasses import dataclass

from construct.journal import render_journal

PROT = "person:vale"


@dataclass
class Row:
    entity: str
    attribute: str
    value: str
    valid_from: float | None = None


def test_sections_skip_machinery_and_graph_links():
    rows = [
        Row(PROT, "role", "detective of the bureau", 1.0),
        Row(PROT, "kind", "person", 1.0),                       # machinery — skipped
        Row("person:reed", "role", "your senior partner", 1.0),
        Row("person:reed", "alias", "the old hand", 1.0),       # machinery — skipped
        Row("person:reed", "feel", "weathered authority", 1.0),  # flavor pin — skipped
        Row("person:reed", "knows_place", "place:yard", 1.0),   # bare entity id — skipped
        Row("place:yard", "description", "a rain-wet yard off the highway", 1.0),
        Row("obj:token", "significance", "found under the body", 2.0),
    ]
    out = render_journal(rows, PROT)
    assert "YOU — Vale" in out and "detective of the bureau" in out
    assert "PEOPLE" in out and "Reed" in out and "your senior partner" in out
    assert "PLACES" in out and "rain-wet yard" in out
    assert "THINGS" in out and "found under the body" in out
    assert "the old hand" not in out and "weathered authority" not in out
    assert "place:yard" not in out and "person" != out  # no machinery, no bare ids


def test_latest_value_wins_and_fresh_entities_lead():
    rows = [
        Row("person:reed", "standing", "trusts you", 1.0),
        Row("person:reed", "standing", "doubts you now", 5.0),   # supersedes
        Row("person:bell", "account", "claims he was at the pub", 9.0),
    ]
    out = render_journal(rows, PROT)
    assert "doubts you now" in out and "trusts you" not in out
    # Bell (learned at 9.0) tops the PEOPLE section — freshest first
    assert out.index("Bell") < out.index("Reed")


def test_display_names_and_empty_frame():
    rows = [Row("person:reed", "role", "partner", 1.0)]
    out = render_journal(rows, PROT, name_of=lambda e: "Edmund Reed"
                         if e == "person:reed" else None)
    assert "• Edmund Reed" in out
    empty = render_journal([], PROT, header="Day 1 | the study")
    assert "Day 1 | the study" in empty and "Nothing noted yet" in empty
