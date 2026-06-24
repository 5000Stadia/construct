"""adapt_pursued_improv_thread — the host/arc doorway that turns a player-PURSUED, un-authored
clue-shaped detail into something that SERVES the conclusive direction (NARRATION-DISCIPLINE.md /
[[improv-serves-the-destination]]; Cx 085/086/087 GREEN).

This is HOST/ARC authority, NOT narrator permission and NOT a new PB primitive — it applies an
authorized DECISION through the SAME frame/write discipline as clue delivery + the generator's
audit: a learned fact reaches `knows:<protagonist>` only via the `learn_clue_items` shape; all
bookkeeping lives in hidden `plot:`/`session:` rows. The narrator never self-promotes prose into
evidence; the hidden answer is never minted here.

Three lanes (Cx 086) — only lanes 1 (and its decline) live here; the destructive lane is the
turn loop's world-reaction path, not adaptation:
  - genuine        → the pursued detail becomes a real clue for an EXISTING pillar.
  - red_herring    → a false lead, REQUIRING a reachable debunker (else it's a dead-end relabeled).
  - plot_supersede → arc-repair-class (a new required pillar / changed answer) — DEFERRED to v2;
                     declined here so it never silently mutates the solve.
  - decline        → treat as atmosphere (fail-open; never a turn failure, never canon promotion).

The DECISION (which lane, which pillar, the fact) is produced upstream (a cohort, later slice);
this op validates + applies it.
"""
from __future__ import annotations

import logging
from typing import Any

from construct.arc.executor import PLOT, SESSION, turn_time

logger = logging.getLogger(__name__)

#: Per-playthrough cap on adaptations — keeps make-it-real from becoming a fact-faucet
#: (the generator's pacing lesson). Beyond this, pursued threads decline to atmosphere.
ADAPT_BUDGET = 4

#: The only lanes the doorway will act on (Cx 089 #2 — keep it narrow as callers grow).
_KNOWN_LANES = frozenset({"genuine", "red_herring", "plot_supersede", "decline"})


def adaptations_used(reads: Any) -> int:
    """How many improv threads have already been adapted this playthrough (the budget read) —
    the literal count on the hidden `adapt:ledger/used` session row; fail-open to 0."""
    try:
        v = reads.state("adapt:ledger", "used", frame=SESSION)
    except Exception:
        return 0
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def _record(world: Any, *, turn: int, lane: str, pillar_id: str, reason: str,
            new_used: int) -> None:
    """Audit receipt (hidden) — provenance for the adaptation + the budget count. plot:/session:
    only, never canon/player-frame (those get only the authorized learned fact)."""
    eid = f"event:adapt_{turn}"
    world.porcelain.ingest_structured([
        {"entity": eid, "attribute": "kind", "value": "improv_adaptation",
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "lane", "value": lane, "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "pillar", "value": pillar_id or "",
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "reason", "value": (reason or "")[:200],
         "valid_from": turn_time(turn)},
    ], frame=PLOT)
    # budget count (session) — the literal running total of applied adaptations
    world.porcelain.ingest_structured([
        {"entity": "adapt:ledger", "attribute": "used", "value": int(new_used),
         "valid_from": turn_time(turn)},
    ], frame=SESSION)


def apply_adaptation(world: Any, decision: dict, *, protagonist: str, turn: int,
                     reads: Any) -> dict:
    """Apply an authorized adaptation DECISION through the host/arc doorway. Returns a result
    dict {applied, lane, learned, reason}; ALWAYS fail-open (never raises into the turn — a bad
    decision declines to atmosphere, never an emergency canon write).

    decision: {"lane": genuine|red_herring|plot_supersede|decline,
               "pillar_id": str, "fact": [e,a,v], "debunker_fact": [e,a,v]|None, "reason": str}
    """
    lane = (decision or {}).get("lane") or "decline"
    pillar_id = (decision or {}).get("pillar_id") or ""
    reason = (decision or {}).get("reason") or ""
    fact = (decision or {}).get("fact")
    result = {"applied": False, "lane": lane, "learned": [], "reason": reason}

    # Narrow the doorway (Cx 089 #2): only the known lanes may apply. An unknown lane string
    # (a new/buggy caller) declines to atmosphere rather than falling through to a write.
    if lane not in _KNOWN_LANES:
        logger.info("adapt: unknown lane %r — declining to atmosphere", lane)
        return {**result, "lane": "rejected_unknown_lane", "applied": False}
    if lane == "decline":
        return {**result, "lane": "decline"}
    if lane == "plot_supersede":
        # arc-repair-class (new required pillar / changed answer) — DEFERRED to v2 so it can never
        # silently mutate the solve. Decline (atmosphere) rather than mint structure unsafely.
        logger.info("adapt: plot_supersede declined (v2, arc-repair not yet built)")
        return {**result, "lane": "deferred_plot_supersede", "applied": False}
    used = adaptations_used(reads)
    if used >= ADAPT_BUDGET:
        logger.info("adapt: budget exhausted (%d) — declining to atmosphere", ADAPT_BUDGET)
        return {**result, "lane": "budget_exhausted", "applied": False}

    # genuine / red_herring both need a 3-part fact to write into the player frame.
    if not (isinstance(fact, (list, tuple)) and len(fact) == 3 and all(fact)):
        logger.info("adapt: malformed fact %r — declining", fact)
        return {**result, "lane": "rejected_bad_fact", "applied": False}

    if lane == "red_herring":
        deb = (decision or {}).get("debunker_fact")
        if not (isinstance(deb, (list, tuple)) and len(deb) == 3 and all(deb)):
            # A false path WITHOUT a reachable debunker is the dead-end problem relabeled (Cx 087).
            logger.info("adapt: red_herring without a debunker fact — declining")
            return {**result, "lane": "rejected_no_debunker", "applied": False}

    try:
        e, a, v = fact[0], fact[1], str(fact[2])
        world.porcelain.ingest_structured(
            [{"entity": e, "attribute": a, "value": v}],
            frame=f"knows:{protagonist}", classify="batch")
        _record(world, turn=turn, lane=lane, pillar_id=pillar_id, reason=reason,
                new_used=used + 1)
        return {"applied": True, "lane": lane, "learned": [[e, a, v]], "reason": reason}
    except Exception as exc:  # fail-open: a write hiccup declines, never sinks the turn
        logger.warning("adapt: write failed (%s) — declining to atmosphere", exc)
        return {**result, "lane": "write_failed", "applied": False}
