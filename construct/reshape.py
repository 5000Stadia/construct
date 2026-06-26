"""World-changing agency — the pure canon-reshape commit helper.

When an EARNED, sanctioned, miraculous player act reshapes the world (revive the
dead, undo a loss), the host commits the change UPSTREAM through the ingest
doorway — the narrator never writes it (see `docs/design/WORLD-CHANGING-AGENCY.md`).
This module is the pure commit: given a `ReshapePlan` (assembled pre-render from
classify + resolution tier + plausibility, in a later flag-gated step), it

  • APPENDS the new current state — it never RETRACTS lived canon (Cx 198 #2:
    retraction hides a row even from historical as-of reads, which is wrong for a
    fact that was true in lived play; the prior truth must still fold for reads
    before this turn);
  • mints a canon reshape EVENT with an explicit `caused_by` causality row;
  • re-stages any entity the change brings into play (a revived NPC becomes
    locatable);
  • seeds ONLY scoped, justified knowledge into the entity's `knows:<npc>` frame
    (never a blanket mirror of hidden truth).

It reads no prose and calls no model — deterministic. It is inert until a trigger
builds a plan (a later step), so adding it changes no shipped behaviour.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from construct.arc.executor import turn_time

logger = logging.getLogger(__name__)

#: Resolution tiers that LAND the target reshape. The other two tiers commit a
#: consequence WITHOUT flipping the target ("however it lands" — every tier writes
#: a real consequence, none is a flat refusal; ACTION-RESOLUTION.md).
LANDING_TIERS = frozenset({"complete_success", "success_cost"})


@dataclass
class ReshapePlan:
    """A sanctioned canon reshape, assembled BEFORE narration. Carries only
    structured rows — the helper never reads prose. `state_rows`/`restage_rows`/
    `frame_rows` apply only when the drawn tier LANDS; `consequence_rows` apply on
    any tier (the cost of a costly landing, or the fallout of a failure)."""

    slug: str                                                    # → event:reshaped_<slug>
    action_event: str = ""                                       # caused_by anchor (event:action_N)
    tier: str = "complete_success"                               # the drawn resolution tier
    state_rows: list[dict] = field(default_factory=list)         # APPENDED new current state
    restage_rows: list[dict] = field(default_factory=list)       # canon re-staging (location, …)
    consequence_rows: list[dict] = field(default_factory=list)   # adverse/cost rows (any tier)
    frame_rows: list[dict] = field(default_factory=list)         # scoped knowledge; each has "frame"
    summary: str = ""                                            # host directive (prose must match); never stored

    @property
    def landed(self) -> bool:
        return self.tier in LANDING_TIERS


@dataclass
class ReshapeResult:
    event_id: str
    landed: bool
    canon_rows: list[dict]
    frame_rows: list[dict]


def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c == "_") else "_" for c in (text or "").lower()]
    return "".join(keep).strip("_") or "reshape"


def plan_from_proposal(proposal: dict, *, tier: str, action_event: str = "",
                       turn: int = 0) -> ReshapePlan | None:
    """Bridge a reshape-proposal cohort's output to a typed `ReshapePlan` (the
    deterministic layer between the model call and `reshape_canon`, mirroring
    `cast.cast_from_proposal`). Fail-soft: a proposal with no usable target state
    change returns None (the turn then plays normally — no reshape); malformed
    optional rows are dropped, never crash.

    Expected proposal shape (the cohort fills it; all fail-soft)::

        {"slug": "angus_revived",
         "target": {"entity": "person:angus", "attribute": "alive", "value": "true"},
         "restage": [{"entity": "person:angus", "attribute": "in", "value": "place:oil_store"}],
         "frame_knowledge": [{"npc": "person:angus", "entity": "fact:attacker",
                              "attribute": "identity", "value": "person:niall"}],
         "consequence": [{"entity": "person:angus", "attribute": "condition", "value": "fading"}],
         "summary": "Angus draws breath and lives."}
    """
    if not isinstance(proposal, dict):
        return None
    tgt = proposal.get("target") or {}
    e, a, v = tgt.get("entity"), tgt.get("attribute"), tgt.get("value")
    if not (e and a and v is not None):
        return None  # no concrete target state change → not a reshape; play normally

    def _rows(items: object) -> list[dict]:
        out: list[dict] = []
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            re_, ra, rv = it.get("entity"), it.get("attribute"), it.get("value")
            if re_ and ra and rv is not None:
                out.append({"entity": re_, "attribute": ra, "value": str(rv)})
        return out

    frame_rows: list[dict] = []
    for fk in (proposal.get("frame_knowledge") or []):
        if not isinstance(fk, dict):
            continue
        npc = fk.get("npc") or fk.get("frame")
        fe, fa, fv = fk.get("entity"), fk.get("attribute"), fk.get("value")
        if not (npc and fe and fa and fv is not None):
            continue
        frame = npc if str(npc).startswith("knows:") else f"knows:{npc}"
        frame_rows.append({"frame": frame, "entity": fe, "attribute": fa, "value": str(fv)})

    slug = _slug(proposal.get("slug") or f"{e}_{a}")
    return ReshapePlan(
        slug=slug,
        action_event=action_event or (f"event:action_{turn}" if turn else ""),
        tier=tier,
        state_rows=[{"entity": e, "attribute": a, "value": str(v)}],
        restage_rows=_rows(proposal.get("restage")),
        consequence_rows=_rows(proposal.get("consequence")),
        frame_rows=frame_rows,
        summary=(proposal.get("summary") or "").strip(),
    )


def reshape_canon(world: Any, plan: ReshapePlan, *, turn: int) -> ReshapeResult:
    """Commit a sanctioned reshape to canon, UPSTREAM and deterministically.

    APPENDS the reshaped current state at `turn_time(turn)` (historical as-of reads
    still serve the prior truth); mints the canon reshape event + an explicit
    `caused_by` row; re-stages + seeds scoped frames. On a NON-landing tier the
    target state/restage/frame rows are skipped — only `consequence_rows` commit
    (the attempt still shaped the world).

    Fail-closed (Cx 200): every `frame_row` MUST carry a scoped `knows:<npc>` frame.
    A missing/None frame would let PB write the seeded knowledge to canon (a hidden
    fact leaking out of the witness's head). The whole plan is validated BEFORE any
    commit, so an invalid plan can never partially write."""
    for fr in plan.frame_rows:
        frame = fr.get("frame")
        if not frame or not str(frame).startswith("knows:"):
            raise ValueError(
                "reshape_canon: every frame_row must carry a scoped 'knows:<npc>' frame; "
                f"got {frame!r}. Refusing to commit — scoped witness knowledge must never "
                "leak to canon.")
    vf = turn_time(turn)
    event_id = f"event:reshaped_{plan.slug}"
    canon: list[dict] = [
        {"entity": event_id, "attribute": "kind", "value": "canon_reshape", "valid_from": vf},
    ]
    if plan.action_event:
        # Explicit causality ROW (Cx 117): item-level `caused_by` isn't surfaced by
        # events().caused_by, so the event→action link is written as its own row.
        canon.append({"entity": event_id, "attribute": "caused_by", "value": plan.action_event,
                      "value_type": "entity", "valid_from": vf})
    body = (plan.state_rows + plan.restage_rows if plan.landed else []) + plan.consequence_rows
    for row in body:
        r = dict(row)
        r.setdefault("valid_from", vf)
        r.setdefault("caused_by", event_id)
        canon.append(r)
    world.porcelain.ingest_structured(canon)

    committed_frames: list[dict] = []
    if plan.landed:
        for fr in plan.frame_rows:
            frame = fr.get("frame")
            item = {k: v for k, v in fr.items() if k != "frame"}
            item.setdefault("valid_from", vf)
            item.setdefault("caused_by", event_id)
            world.porcelain.ingest_structured([item], frame=frame)
            committed_frames.append({**item, "frame": frame})

    logger.info("canon reshape: %s tier=%s landed=%s (%d canon rows, %d frame rows) caused_by %s",
                event_id, plan.tier, plan.landed, len(canon), len(committed_frames), plan.action_event)
    return ReshapeResult(event_id=event_id, landed=plan.landed,
                         canon_rows=canon, frame_rows=committed_frames)
