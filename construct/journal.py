"""The case-board journal (#83, founder-endorsed): the protagonist's own `knows:` frame
rendered as their diegetic notebook — suspects, places, things, what they have learned.

Session-scale memory is otherwise the PLAYER's problem (eval finding: 8 clues held only in
context; humans across sessions lose the thread). The notebook is the honest recap surface:
it reads ONLY the protagonist's frame (no spoiler surface — the character can't note what
they never learned), deterministically (zero model calls, zero cost, no invention), and it
never runs a turn or advances time.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

#: Frame rows that are machinery or render seasoning, not something the character would
#: write in a notebook: typing (`kind`), reference plumbing (`alias`, `known_as`), volatile
#: position (`in`, `current_occupant`), and the narrator's flavor pins (`feel`).
_SKIP_ATTRS = {"kind", "alias", "in", "feel", "current_occupant", "known_as"}

_ENTITY_ID = re.compile(r"^[a-z_]+:[\w-]+$")


def _humanize(entity_id: str) -> str:
    return entity_id.split(":", 1)[-1].replace("_", " ").title()


def _attr_label(attribute: str) -> str:
    if attribute.startswith("relationship_to_"):
        return "to you"
    return attribute.replace("_", " ")


def render_journal(rows: Iterable[Any], protagonist: str,
                   name_of: Callable[[str], str | None] | None = None,
                   header: str = "", per_entity: int = 5,
                   settled: set | None = None) -> str:
    """Format the protagonist's knows-frame rows as their notebook. Pure function over
    row objects (entity/attribute/value/valid_from) — deterministic, no reads, no model.

    Keeps the LATEST value per (entity, attribute); drops machinery rows (`_SKIP_ATTRS`)
    and raw graph links (values that are bare entity ids); shows freshest knowledge first
    (people you learned about most recently top their section — the trail as it grew)."""
    latest: dict[tuple[str, str], Any] = {}
    for r in rows:
        ent, attr = str(getattr(r, "entity", "")), str(getattr(r, "attribute", ""))
        if not ent or not attr or attr in _SKIP_ATTRS:
            continue
        val = getattr(r, "value", None)
        if val is None or _ENTITY_ID.match(str(val).strip()):
            continue  # graph plumbing, not notebook prose
        vf = getattr(r, "valid_from", None) or 0.0
        prev = latest.get((ent, attr))
        if prev is None or (getattr(prev, "valid_from", None) or 0.0) <= vf:
            latest[(ent, attr)] = r

    by_entity: dict[str, list[Any]] = {}
    for (ent, _attr), r in latest.items():
        by_entity.setdefault(ent, []).append(r)

    def _name(ent: str) -> str:
        nm = name_of(ent) if name_of else None
        return str(nm) if nm else _humanize(ent)

    def _freshness(ent: str) -> float:
        return max((getattr(r, "valid_from", None) or 0.0) for r in by_entity[ent])

    def _entry(ent: str, bullet: str = "•") -> list[str]:
        rs = sorted(by_entity[ent], key=lambda r: (getattr(r, "valid_from", None) or 0.0),
                    reverse=True)[:per_entity]
        # #96 S3 (Cx 414): a SETTLED entity's evidence is closed history, never an active
        # lead — the notebook says so plainly (the crew remembers its own resolutions).
        _tag = " — settled (a past chapter's answer)" if ent in (settled or set()) else ""
        lines = [f"{bullet} {_name(ent)}{_tag}"]
        lines += [f"    {_attr_label(str(r.attribute))}: {str(r.value).strip()}" for r in rs]
        return lines

    people = sorted((e for e in by_entity if e.startswith("person:") and e != protagonist),
                    key=_freshness, reverse=True)
    places = sorted((e for e in by_entity if e.startswith("place:")),
                    key=_freshness, reverse=True)
    things = sorted((e for e in by_entity if e.startswith("obj:")),
                    key=_freshness, reverse=True)
    other = sorted((e for e in by_entity
                    if not e.startswith(("person:", "place:", "obj:")) and e != protagonist),
                   key=_freshness, reverse=True)

    out: list[str] = [f"📓 {header}" if header else "📓 Your notebook"]
    if protagonist in by_entity:
        out.append("")
        out += _entry(protagonist, bullet="YOU —")
    for title, ents in (("PEOPLE", people), ("PLACES", places),
                        ("THINGS", things), ("ALSO NOTED", other)):
        if not ents:
            continue
        out += ["", title]
        for e in ents:
            out += _entry(e)
    if len(out) <= 1:
        out.append("")
        out.append("(Nothing noted yet — the world will fill these pages as you learn it.)")
    return "\n".join(out)
