"""THE CHAPTER BRIDGE, B1 (docs/design/CHAPTER-BRIDGE-B1.md r3, R36): how a chapter ended,
in one word, from facts already recorded — so the next chapter can answer it.

    abandoned  the chapter ended through the refusal clock (the player walked away)
    elsewhere  the main arc at the end was adopted from a tangent (the player's own
               direction), or the terminal location lies in grown territory outside the arc
    wrong      grade wrong, a failure shape, or any other loss
    right      otherwise, on a win (partial / pyrrhic stay shades on `grade`)

Pure, deterministic, no model calls. Death has its own permanence path (no category).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CATEGORIES = ("abandoned", "elsewhere", "wrong", "right")
_FAILURE_SHAPES = frozenset({"failure", "quiet_failure"})


def adopted_from_tangent(reads: Any, arc_id: str) -> bool:
    """The arc became main by tangent adoption (tangent.ADOPTION_RECEIPT_KIND receipt)."""
    from construct.arc.executor import SESSION
    from construct.tangent import ADOPTION_RECEIPT_KIND
    try:
        for ev in reads.events(kind=ADOPTION_RECEIPT_KIND, frame=SESSION):
            if reads.state(ev.event_id, "new_main", frame=SESSION) == arc_id:
                return True
    except Exception:  # noqa: BLE001 — an unreadable receipt is simply not adoption
        logger.debug("adoption receipt unreadable", exc_info=True)
    return False


def in_grown_territory(reads: Any, arc: Any, place: str | None) -> bool:
    """The place's containment chain holds a grown `region:` the arc never references."""
    if not place:
        return False
    from construct.arc.concealment import arc_entities
    try:
        chain = [place] + list(reads.location_chain(place) or [])
        scope = arc_entities(arc, reads)
    except Exception:  # noqa: BLE001
        return False
    return any(str(c).startswith("region:") and c not in scope for c in chain)


def outcome_category(reads: Any, arc: Any, *, refusal_fired: bool, outcome: str | None,
                     grade: str = "", outcome_shape: str = "",
                     terminal_location: str | None = None) -> str:
    if refusal_fired:
        return "abandoned"
    if adopted_from_tangent(reads, arc.arc_id) or in_grown_territory(reads, arc,
                                                                    terminal_location):
        return "elsewhere"
    if grade == "wrong" or outcome_shape in _FAILURE_SHAPES or outcome != "won":
        return "wrong"
    return "right"


# ---- the continuation's deterministic accountings (B1 changes 3-5) -------------------------

def check_threads(proposal: dict, n_threads: int, arc: Any,
                  hook_ids: list[str] | None = None) -> list[str]:
    """Change 3: every numbered personal thread disposed EXACTLY once — no index out of range,
    no disposition other than carried/closed, no extras — and a `carried` one names an id or
    beat of the new arc (or an ADMITTED hook-cast person)."""
    disp_all = list(proposal.get("thread_disposition") or [])
    if n_threads <= 0:
        return ([f"{len(disp_all)} thread disposition(s) given, but there are no personal "
                 "threads"] if disp_all else [])
    from construct.arc.concealment import arc_entities
    seen: dict[int, dict] = {}
    problems = []
    for d in disp_all:
        if not isinstance(d, dict):
            problems.append(f"a thread disposition is not an object ({d!r})")
            continue
        i = d.get("index")
        if type(i) is not int:   # bool and float excluded: malformed output never coerces
            problems.append(f"a thread disposition has no valid integer index ({i!r})")
            continue
        if not 0 <= i < n_threads:
            problems.append(f"thread index {i} is out of range (0..{n_threads - 1})")
            continue
        if d.get("disposition") not in ("carried", "closed"):
            problems.append(f"thread {i}: disposition must be carried or closed, not "
                            f"{d.get('disposition')!r}")
            continue
        if i in seen:
            problems.append(f"thread {i} disposed twice")
        seen[i] = d
    missing = [i for i in range(n_threads) if i not in seen]
    if missing:
        problems.append(f"personal thread(s) {missing} have no disposition (carry or close "
                        "each one)")
    named = arc_entities(arc) | {b.beat_id for b in arc.beats} | set(hook_ids or ())
    for i, d in seen.items():
        if 0 <= i < n_threads and d.get("disposition") == "carried" and not any(
                tok in str(d.get("how") or "") for tok in named if tok):
            problems.append(f"thread {i} is 'carried' but names no beat, id or hook-cast "
                            "person of the new chapter")
    return problems


def closed_threads(proposal: dict, threads: list[dict]) -> list[str]:
    """The threads the author closed, as settled-history lines."""
    out = []
    for d in proposal.get("thread_disposition") or []:
        try:
            i = int((d or {}).get("index"))
        except (TypeError, ValueError):
            continue
        if (d or {}).get("disposition") == "closed" and 0 <= i < len(threads):
            out.append(f"{threads[i].get('thread', '')} — closed by the author: "
                       f"{(d.get('how') or '').strip()}")
    return out


def check_response(proposal: dict, reads: Any, arc: Any, category: str,
                   hook_ids: list[str] | None = None) -> list[str]:
    """Change 4: the chapter answers the outcome, grounded at the horizon and in the arc.
    No recorded outcome (no receipt: a legacy or never-concluded slot) → nothing to answer."""
    if not category:
        return []
    from construct.arc.concealment import arc_entities
    r = proposal.get("responds_to_outcome") or {}
    how = str(r.get("how") or "").strip()
    ids = [str(i) for i in (r.get("ids") or []) if i]
    hook = set(hook_ids or ())   # ADMITTED hook-cast ids only (their `in` row will commit)
    in_arc = arc_entities(arc) | hook
    grounded = [i for i in ids if i in in_arc and (i in hook or _has(reads, i))]
    if not how or not grounded:
        return [f"the next chapter must answer the outcome ({category}): give "
                "`responds_to_outcome` a `how` and at least one id that exists now and "
                "appears in your beats or hook_cast"]
    return []


def _has(reads: Any, entity: str) -> bool:
    try:
        return bool(reads.has_entity(entity))
    except Exception:  # noqa: BLE001
        return False


def rederive_node(node: Any, reads: Any, door_place: str | None) -> Any:
    """B1 r3: a node's presence/location as the world holds them at the horizon — the
    authored chapter-1 values go stale over a chapter."""
    import dataclasses
    try:
        chain = reads.location_chain(node.node_id) or []
    except Exception:  # noqa: BLE001
        chain = []
    loc = str(chain[0]) if chain else ""
    presence = ("at_scene" if loc and loc == door_place else "nearby" if loc else "offscene")
    return dataclasses.replace(node, location=loc, presence=presence)


def build_episode_cast(proposal: dict, arc: Any, base_cast: tuple, reads: Any, *,
                       door_place: str | None, hook_ids: list[str],
                       protagonist: str) -> tuple[tuple, list[str]]:
    """Change 5: the episode cast — chapter 1's nodes plus the new clue holders — re-derived
    at the horizon and validated for EVERY InFrame beat on the protagonist's frame."""
    import dataclasses
    from construct.arc.conditions import InFrame
    from construct.cast import CastNode, Clue, beat_delivery_targets, validate_beat_delivery
    problems: list[str] = []
    nodes = {n.node_id: rederive_node(n, reads, door_place) for n in base_cast}
    beats = {b.beat_id: b for b in arc.beats}
    for c in proposal.get("clues") or []:
        c = c or {}
        bid, holder = str(c.get("beat_id") or ""), str(c.get("holder") or "")
        cond = str(c.get("reveal_condition") or "none")
        # `_build_arc` suffixes each authored beat id per arc (beat:x → beat:x_<arc>): the
        # author names its own id, so resolve it to the built beat.
        b = beats.get(bid) or next((v for k, v in beats.items() if k.startswith(bid + "_")),
                                   None)
        if b is None or not isinstance(b.achievable_via, InFrame):
            problems.append(f"clue for {bid!r}: not a player_learns beat of this chapter")
            continue
        if cond not in ("none", "pressure"):
            problems.append(f"clue for {bid}: reveal_condition {cond!r} — a person tells "
                            "only when asked (none) or pressed (pressure)")
            continue
        if not holder.startswith("person:") or not (holder in hook_ids or _has(reads, holder)):
            problems.append(f"clue for {bid}: holder {holder!r} is not a person present in "
                            "the world now or in your hook_cast")
            continue
        av = b.achievable_via
        clue = Clue(clue_id=f"clue:{bid.split(':', 1)[-1]}", pillar_id=f"pillar:{arc.arc_id}",
                    surface_fact=(av.entity, av.attribute, str(av.value)),
                    reveal_condition=cond)
        if holder in hook_ids:
            base = nodes.get(holder) or CastNode(holder)
            node = dataclasses.replace(base, presence="at_scene",
                                       location=door_place or base.location)
        else:
            node = nodes.get(holder) or rederive_node(CastNode(holder), reads, door_place)
        nodes[holder] = dataclasses.replace(node, holds_clues=tuple(node.holds_clues)
                                            + (clue,))
    cast = tuple(nodes.values())
    targets = [t for t in beat_delivery_targets(arc.beats)
               if beats[t["beat_id"]].achievable_via.frame == f"knows:{protagonist}"]
    for prob in validate_beat_delivery(targets, cast, include_optional=True):
        problems.append(prob + " (chapter 2: name a holder in `clues`)")
    return cast, problems


def cast_blob(cast: tuple) -> dict:
    """The episode cast as the cast-proposal JSON `cast_from_proposal` reads back."""
    return {"cast": [{
        "id": n.node_id, "shape_role": n.shape_role, "surface_role": n.surface_role,
        "presence": n.presence, "location": n.location,
        "first_witness": n.first_witness, "is_culprit": n.is_culprit,
        "pronouns": n.pronouns,
        "clues": [{"clue_id": c.clue_id, "pillar_id": c.pillar_id,
                   "fact": {"entity": c.surface_fact[0], "attribute": c.surface_fact[1],
                            "value": c.surface_fact[2]},
                   "coverage_effect": c.coverage_effect, "is_red_herring": c.is_red_herring,
                   "reveal_mode": c.reveal_mode, "reveal_condition": c.reveal_condition,
                   "debunked_by": c.debunked_by, "hook_text": c.hook_text}
                  for c in n.holds_clues]} for n in cast]}
