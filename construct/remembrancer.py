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
from typing import Any

from construct import cohorts
from construct.resolve import is_proper_named
from construct.text import slugify

logger = logging.getLogger(__name__)

#: sheet rows beyond this are dropped freshest-last (the sheet is a digest, not the ledger)
_SHEET_ROWS = 40
#: machinery rows the mind doesn't "remember" (mirrors the notebook's skip set)
_SKIP_ATTRS = {"kind", "alias", "in", "feel", "current_occupant", "known_as"}


def _log_number(fact: dict) -> int:
    """A fact's assertion number (the log order); unnumbered sorts last."""
    aid = str((fact.get("provenance") or {}).get("assertion_id") or "")
    return int(aid[2:]) if aid.startswith("a:") and aid[2:].isdigit() else 1 << 60


def _recency_key(fact: dict) -> tuple[float, int]:
    """Freshest-last order: valid_from (timeless reads as 0.0), then log order."""
    return ((fact.get("valid") or [None])[0] or 0.0, _log_number(fact))


def _tied_members(p: Any, frame: str, entity: str, attribute: str,
                  as_of: float | None) -> list[dict]:
    """The members of an OPEN TIE on one functional key, freshest last (`_recency_key`): the
    engine flags the key `conflicted` and names the sides (`state().conflicting`); their
    values are read back with the key-scoped `facts()` scan. [] when the key is not
    actually tied. Used ONLY on keys the engine itself flagged."""
    try:
        st = p.state(entity, attribute, frame, as_of=as_of)
        if st.get("status") != "conflicted":
            return []
        ids = set(st.get("conflicting") or [])
        rows = p.facts(frame, entity=entity, attribute=attribute, as_of=as_of)
    except Exception:  # noqa: BLE001
        return []
    return sorted((r for r in rows
                   if (r.get("provenance") or {}).get("assertion_id") in ids),
                  key=_recency_key)


def frame_knowledge(world: Any, frame: str, *, as_of: float | None = None) -> list:
    """A knowledge frame's whole knowledge as FOLDED truth — pattern-buffer's
    frame-knowledge recipe (ADOPTION.md): `snapshot(entities(F, as_of=h), frame=F,
    as_of=h)`. The engine does the folding the host used to hand-roll over
    `facts(F)` raw rows: identity (`same_as`/merged ids read as one entity), supersession,
    EVENT rows left out of the standing state, evidence rank, timeless rows, and every
    member of a set-valued key. `facts(F)` stays the RAW audited scan; this is the read
    for "what does this frame KNOW".

    Rows come back row-like (`.entity/.attribute/.value/.valid_from/.valid_to/.id`, the
    shape `adapter.frame_facts` presents) so render/screen code reads them unchanged.
    The `as_of` gate applies to the roster AND the fold (None = the timeline head).
    ONE host rule rides on top, only on keys the engine flags `conflicted` (an open tie on a
    functional key — the engine holds the FIRST-asserted side, so a digest that reads as
    "freshest knowledge" would show the stalest, and a lone literal can lose to an entity-id
    link the notebook then drops as plumbing): the FRESHEST tied side stands (latest
    valid_from, then latest-asserted), as the hand-fold always chose. Drop this once the
    engine's tie rule is settled (pattern-buffer audit 2026-10, folds P1-1).
    Fail-open to [] on a read failure — a digest surface never sinks a turn."""
    from types import SimpleNamespace
    p = world.porcelain
    try:
        ents = p.entities(frame, as_of=as_of)
        if not ents:
            return []
        snap = p.snapshot(ents, frame=frame, as_of=as_of)
        if snap.get("error"):
            # snapshot refuses the WHOLE scope if any id is off-grammar / unknown; drop
            # those named by the engine and fold the rest rather than lose the frame.
            bad = set(snap.get("bad") or [])
            ents = [e for e in ents if e not in bad]
            snap = p.snapshot(ents, frame=frame, as_of=as_of) if ents else {}
        facts = snap.get("facts") or []
    except Exception:  # noqa: BLE001
        logger.warning("frame_knowledge(%s) read failed", frame, exc_info=True)
        return []
    facts = list(facts)
    for ent, attr in (snap.get("conflicted") or []):
        tied = _tied_members(p, frame, ent, attr, as_of)
        if tied:
            latest = dict(tied[-1], entity=ent)
            facts = [f for f in facts
                     if not (f["entity"] == ent and f["attribute"] == attr)] + [latest]
    # The fold serves rows attribute-sorted; restore LOG order (assertion id) so tie-breaks
    # downstream (a notebook's per-entity cap on equal valid_from) keep the order they had.
    out = []
    for f in sorted(facts, key=_log_number):
        valid = f.get("valid") or [None, None]
        out.append(SimpleNamespace(
            entity=f["entity"], attribute=f["attribute"], value=f["value"],
            valid_from=valid[0], valid_to=valid[1],
            id=(f.get("provenance") or {}).get("assertion_id")))
    return out


def build_sheet(world: Any, protagonist: str, arc: Any,
                horizon: float | None = None) -> str:
    """The screened `knows:<prot>` digest — deterministic, no model calls. Returns
    'entity · attribute · value' lines, freshest last (recency reads naturally).
    Reads the frame's FOLDED knowledge (`frame_knowledge`, the engine's recipe) at the
    play horizon; the concealment screen then applies per surviving row."""
    from construct.arc.executor import (
        arc_protected_keys, concealed_tokens, turn_time, value_leaks,
    )
    from construct.adapter import PorcelainWorldReads as _PWR
    protected = arc_protected_keys(arc, _PWR(world, horizon=horizon))
    concealed = concealed_tokens(protected)
    stamp = turn_time(0)
    kept: list[Any] = []
    for r in frame_knowledge(world, f"knows:{protagonist}", as_of=horizon):
        ent, attr = str(r.entity), str(r.attribute)
        if attr in _SKIP_ATTRS:
            continue
        vf = getattr(r, "valid_from", None) or 0.0
        if vf <= stamp:  # build-stamped: the concealment screen applies
            if (ent, attr) in protected or value_leaks(str(r.value or ""), concealed):
                continue
        kept.append(r)
    rows = sorted(kept, key=lambda r: (getattr(r, "valid_from", None) or 0.0))[-_SHEET_ROWS:]
    return "\n".join(f"{r.entity} · {r.attribute} · {r.value}" for r in rows)


def _slug(text: str) -> str:
    return slugify(text or "")[:40] or "unnamed"


def _standing_values(world: Any, entity: str, attribute: str, frame: str) -> list[str]:
    """Every value that STANDS for (entity, attribute) in `frame`, freshest last
    (`_recency_key`) — the engine's folded answer (frame-knowledge recipe: `snapshot([entity],
    frame=frame)`), so identity, supersession and set members are the engine's, not a
    hand-fold over raw rows. Every side of an open tie stands (see `frame_knowledge`). [] when nothing stands (or the entity is unknown / the read fails)."""
    p = world.porcelain
    try:
        # the single-key fold resolves identity (a merged alias id reads as its
        # canonical entity) and names the canonical id + attribute it served
        st = p.state(entity, attribute, frame)
        if not isinstance(st, dict) or st.get("status") not in ("known", "conflicted"):
            return []
        head = st.get("fact") or {}
        if head.get("attribute") != attribute:
            return []   # the engine canonicalized the attribute name: a different relation
        if st["status"] == "conflicted":
            tied = _tied_members(p, frame, head["entity"], attribute, None)
            if tied:
                return [str(f["value"]) for f in tied]
        snap = p.snapshot([entity], frame=frame)
        members = sorted((f for f in (snap.get("facts") or [])
                          if f.get("entity") == head["entity"]
                          and f.get("attribute") == attribute), key=_recency_key)
        vals = [str(f["value"]) for f in members] or [str(head.get("value"))]
    except Exception:  # noqa: BLE001
        return []
    return vals


def _existing_value(world: Any, entity: str, attribute: str, frame: str) -> str | None:
    """The value that stands for (entity, attribute) in `frame`, or None — the freshest
    standing one when a key holds several (see `_standing_values` for all of them)."""
    vals = _standing_values(world, entity, attribute, frame)
    return vals[-1] if vals else None


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
        # (a set-valued key can hold several standing members: the new value collides
        # only when it is NONE of them.)
        standing = (_standing_values(world, target, attr, "canon")
                    or _standing_values(world, target, attr, frame))
        prior = next((v for v in standing if v.strip().lower() == value.lower()),
                     standing[-1] if standing else None)
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
