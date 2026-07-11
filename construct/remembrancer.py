"""The Remembrancer (#97, REMEMBRANCER.md, Cx 434) — the protagonist's own memory as a
turn participant.

Two halves live here, both deterministic (the model calls are in `cohorts`):

1. `build_sheet` — the SCREENED `knows:<prot>` digest `memory_turn` reads. The same
   concealment discipline as every render surface (journal, briefing): build-stamped
   protected keys and concealed-vocabulary values never reach a model whose output is
   rendered; rows LEARNED IN PLAY are earned and show.

2. `commit_declared_memory` — the retcon half's authority layer (Cx 434 constraint 3:
   `knows:<prot>` is not harmless storage — it drives pillar coverage, clue learning,
   and promotion licensing). Declared autobiography commits freely; world claims become
   framed BELIEFS that can never satisfy arc coverage; protected/concealed material is
   screened at STORAGE time (the game.py relationship-seeding precedent); attribute
   collisions quarantine — the FIRST established value stands and the tension is
   returned for the Remembrancer to reflect in fiction, never a silent overwrite.
   A declared past PERSON with a proper personal name is admitted as a minimal
   OFFSCENE canon stub through the #98 gate (kind/name/role only — never `in`, never
   presence, never a current action).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from construct import cohorts
from construct.resolve import is_proper_named

logger = logging.getLogger(__name__)

#: sheet rows beyond this are dropped freshest-last (the sheet is a digest, not the ledger)
_SHEET_ROWS = 40
#: machinery rows the mind doesn't "remember" (mirrors the notebook's skip set)
_SKIP_ATTRS = {"kind", "alias", "in", "feel", "current_occupant", "known_as"}


def build_sheet(world: Any, protagonist: str, arc: Any,
                horizon: float | None = None) -> str:
    """The screened `knows:<prot>` digest — deterministic, no model calls. Returns
    'entity · attribute · value' lines, freshest last (recency reads naturally)."""
    from construct.arc.executor import (
        arc_protected_keys, concealed_tokens, turn_time, value_leaks,
    )
    from construct.adapter import PorcelainWorldReads as _PWR
    protected = arc_protected_keys(arc, _PWR(world, horizon=horizon))
    concealed = concealed_tokens(protected)
    stamp = turn_time(0)
    latest: dict[tuple[str, str], Any] = {}
    from construct.adapter import frame_facts
    for r in frame_facts(world, f"knows:{protagonist}"):
        ent, attr = str(r.entity), str(r.attribute)
        if attr in _SKIP_ATTRS:
            continue
        vf = getattr(r, "valid_from", None) or 0.0
        if horizon is not None and vf > horizon:
            continue  # beyond the play horizon
        if vf <= stamp:  # build-stamped: the concealment screen applies
            if (ent, attr) in protected or value_leaks(str(r.value or ""), concealed):
                continue
        prev = latest.get((ent, attr))
        if prev is None or (getattr(prev, "valid_from", None) or 0.0) <= vf:
            latest[(ent, attr)] = r
    rows = sorted(latest.values(),
                  key=lambda r: (getattr(r, "valid_from", None) or 0.0))[-_SHEET_ROWS:]
    return "\n".join(f"{r.entity} · {r.attribute} · {r.value}" for r in rows)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s[:40] or "unnamed"


def _existing_value(world: Any, entity: str, attribute: str, frame: str) -> str | None:
    """The latest visible value for (entity, attribute) in `frame`, or None."""
    best, best_vf = None, -1.0
    try:
        from construct.adapter import frame_facts
        for r in frame_facts(world, frame, entity=entity, attribute=attribute):
            vf = getattr(r, "valid_from", None) or 0.0
            if vf >= best_vf:
                best, best_vf = str(r.value), vf
    except Exception:  # noqa: BLE001
        return None
    return best


def commit_declared_memory(world: Any, provider: Any, player_input: str,
                           protagonist: str, arc: Any, turn: int) -> tuple[list[str], list[tuple]]:
    """The retcon commit channel (Cx 434 constraints 3-5). Extract the declaration's
    claims, then apply the deterministic authority rules and WRITE:

    - self claims → `knows:<prot>` rows on the protagonist (autobiography is theirs
      to author), UNLESS (a) the (entity, attribute) is arc-protected or the value
      brushes concealed vocabulary → screened at storage (never written), or (b) a
      DIFFERENT value already stands in canon or prior declarations → quarantined,
      the first value stands, a tension line returns for in-fiction reflection.
    - world claims → a `believes_*` row on the PROTAGONIST — a framed belief that can
      never satisfy arc coverage (conditions target real entities/attributes), same
      protected/concealed screen.
    - named past people → proper-name gate (#98's `is_proper_named`): a minimal
      OFFSCENE canon stub (kind/name/role) + a relationship row in the player frame.
      Descriptive figures never mint.

    Returns (tensions, receipts) — tensions are founder-voiced collision lines for
    `memory_turn`/the briefing; receipts are (id, attribute, reason) for the trace."""
    from construct.arc.executor import (
        arc_protected_keys, concealed_tokens, turn_time, value_leaks,
    )
    frame = f"knows:{protagonist}"
    from construct.adapter import PorcelainWorldReads as _PWR
    protected = arc_protected_keys(arc, _PWR(world))
    concealed = concealed_tokens(protected)
    tensions: list[str] = []
    receipts: list[tuple] = []
    try:
        out = cohorts.extract_memory_claims(provider, player_input, protagonist)
    except Exception as exc:  # noqa: BLE001 — a failed extraction never sinks the turn
        logger.warning("declared-memory extraction failed: %s", exc)
        return [], [("memory", "extract", f"failed ({exc})")]

    rows: list[dict] = []
    canon_rows: list[dict] = []
    # ---- named past people: the #98 stub gate, offscene only ------------------------
    known_people: dict[str, str] = {}
    for p in (out.get("people") or []):
        name = str(p.get("name") or "").strip()
        relation = str(p.get("relation") or "").strip()
        if not is_proper_named(name):
            receipts.append((name or "(unnamed)", "person", "memory_person_denied"))
            continue
        if value_leaks(name + " " + relation, concealed):
            receipts.append((name, "person", "memory_screened"))
            continue
        pid = f"person:{_slug(name)}"
        if _existing_value(world, pid, "name", "canon") is None:
            canon_rows += [
                {"entity": pid, "attribute": "kind", "value": "person",
                 "valid_from": turn_time(turn)},
                {"entity": pid, "attribute": "name", "value": name,
                 "valid_from": turn_time(turn)},
            ]
            if relation:
                canon_rows.append({"entity": pid, "attribute": "role",
                                   "value": relation, "valid_from": turn_time(turn)})
            receipts.append((pid, "person", "memory_person_stubbed"))
        else:
            receipts.append((pid, "person", "memory_person_bound"))
        if relation:
            rows.append({"entity": protagonist,
                         "attribute": f"relationship_to_{pid}",
                         "value": relation, "valid_from": turn_time(turn)})
        known_people[name.lower()] = pid

    # ---- claims: autobiography commits; beliefs frame; collisions quarantine --------
    for c in (out.get("claims") or []):
        about = str(c.get("about") or "self")
        subject = str(c.get("subject") or "").strip()
        attr = _slug(str(c.get("attribute") or ""))
        value = str(c.get("value") or "").strip()
        if not attr or not value:
            continue
        if about == "world":
            # a framed BELIEF on the protagonist — never a row on the world entity,
            # so it can never satisfy coverage or license a protected key.
            attr = f"believes_{_slug(subject)}_{attr}" if subject else f"believes_{attr}"
        target = protagonist
        if (target, attr) in protected or value_leaks(value, concealed):
            receipts.append((target, attr, "memory_screened"))
            continue
        # collision: canon first, then prior self-declarations (Cx 434 constraint 5)
        prior = (_existing_value(world, target, attr, "canon")
                 or _existing_value(world, target, attr, frame))
        if prior is not None and prior.strip().lower() != value.lower():
            tensions.append(
                f"{attr.replace('_', ' ')}: '{prior}' is what stands — the new "
                f"recollection says '{value}', and it sits oddly")
            receipts.append((target, attr, "memory_collision_quarantined"))
            continue
        rows.append({"entity": target, "attribute": attr, "value": value,
                     "valid_from": turn_time(turn)})
        receipts.append((target, attr, "memory_declared"))

    try:
        if canon_rows:
            world.porcelain.ingest_structured(canon_rows)  # offscene stubs — canon
        if rows:
            world.porcelain.ingest_structured(rows, frame=frame)
    except Exception as exc:  # noqa: BLE001
        logger.warning("declared-memory commit failed: %s", exc)
        receipts.append(("memory", "commit", f"failed ({exc})"))
    return tensions, receipts
