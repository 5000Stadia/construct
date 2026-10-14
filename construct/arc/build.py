"""Arc construction from an authoring proposal (arc.md F2 / world.md F5).

The arc grammar's constructor, moved out of `game.py` unchanged: the model-facing
`ARC_SCHEMA`, the proposal -> `Arc` builder (`_build_arc`, also exposed as `build_arc`),
the refusal-clock synthesis (`refusal_clock_for`) and the small expression helpers the
builder uses. Pure moves; `game.py` re-exports every name so existing importers and
test patches keep working.
"""

from __future__ import annotations

from typing import Any

from construct.arc.conditions import (
    AtLeast,
    BeatAchieved,
    InFrame,
    Occurred,
    Quantity,
    StateIs,
    TurnsQuiet,
)
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.text import slugify_keep_underscores


ARC_SCHEMA = {
    "type": "object",
    "properties": {
        "protagonist": {"type": "string", "description": "entity id, e.g. person:joel"},
        "theme": {"type": "string", "description": "the pitchable theme, one line"},
        "goal_statement": {"type": "string",
                           "description": "ONE vivid player-facing line of aspiration "
                           "for win_loss mode — the AIM in THIS world's genre. NAME the "
                           "premise stakes (the dragon, the blight, the missing child, "
                           "the locked heart); a beloved archetype is GOOD, not a flaw "
                           "— 'solve the mystery and name the killer', 'slay the dragon "
                           "and free the vale', 'win her heart across the years', 'bring "
                           "the fort through the monsoon alive'. Reveal the PROBLEM, "
                           "never the SOLUTION: no whodunit answer, no mechanism, no "
                           "specific hidden fact the player must discover."},
        "failure_when": {
            "type": "object",
            "description": "OPTIONAL loss terminal for win_loss mode — the story's DECISIVE failure "
            "event, authored from what THIS story is about ('IT'). Three kinds: 'event_occurs' = a "
            "decisive loss event (e.g. 'alarm_raised', 'player_unmasked', the protectee killed) — "
            "give a plausible event kind. 'player_learns' = a damning fact entering the player frame. "
            "'time_deadline' = ONLY when time is genuinely part of THIS story's thread (a bomb timer, "
            "the King arriving, a tide, dawn execution) — set `deadline_minutes` to the IN-WORLD "
            "minutes until the deadline; NEVER for a leisurely investigation/mystery, where time is "
            "pedantic. Omit `failure_when` entirely when the story has no decisive failure event (it "
            "simply stays open until the player concludes). Turns NEVER force a close.",
            "properties": {
                "kind": {"type": "string",
                         "enum": ["player_learns", "event_occurs", "time_deadline"]},
                "entity": {"type": "string",
                           "description": "event_occurs: the event kind; "
                                          "player_learns: the fact/entity id"},
                "attribute": {"type": "string", "description": "player_learns only"},
                "value": {"type": "string", "description": "player_learns only"},
                "deadline_minutes": {"type": "integer",
                                     "description": "time_deadline only: in-world minutes until "
                                                    "the fiction's clock runs out"},
            },
        },
        "delta_type": {"type": "string",
                       "enum": ["drive_inverted", "desire_at_cost", "desire_renounced",
                                "identity_accepted", "homecoming_changed"]},
        "tension": {"type": "array", "items": {"type": "string"},
                    "description": "[entity, stronger_drive, weaker_drive]"},
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "beat:<slug>"},
                    "phase": {"type": "string",
                              "enum": ["setup", "rising", "crisis", "climax", "falling"]},
                    "weight": {"type": "string", "enum": ["required", "optional"]},
                    "kind": {"type": "string", "enum": ["player_learns", "event_occurs"]},
                    "entity": {"type": "string",
                               "description": "for player_learns: the fact/entity id; "
                                              "for event_occurs: the event kind"},
                    "attribute": {"type": "string",
                                  "description": "player_learns only: the attribute"},
                    "value": {"type": "string",
                              "description": "player_learns only: the value"},
                },
                "required": ["id", "phase", "weight", "kind", "entity", "attribute", "value"],
            },
        },
    },
    "required": ["protagonist", "theme", "delta_type", "tension", "beats"],
}


def _slug(s: str) -> str:
    """Conform an id segment to the frozen porcelain id grammar
    (^[a-z][a-z0-9_]*:[a-z0-9_:]+$) — model proposals love hyphens."""
    return slugify_keep_underscores(s)


#: Event kinds the host reserves (R40 abandonment, R42 speech): never an authored beat's kind.
_RESERVED_EVENT_KINDS = frozenset({"player_speech"})


def _beat_expr(beat: dict, player_frame: str):
    if beat["kind"] == "player_learns":
        return InFrame(player_frame, beat["entity"], beat["attribute"], beat["value"])
    kind = str(beat["entity"])
    if kind in _RESERVED_EVENT_KINDS or kind.startswith("event:abandoned"):
        # a failed attempt, retried like any unbuildable proposal (UTTERANCE-NOT-FACT r2)
        raise ValueError(f"event kind {kind!r} is reserved by the host")
    return Occurred(kind)


def _failure_expr(spec: dict | None, player_frame: str):
    """Convert the optional authored loss terminal into an Expr, tolerantly. The loss is the
    story's DECISIVE failure event (founder "IT closes it"), authored per-story:
      - `time_deadline`: a fiction clock ran out (King's dinner, the bomb) → a `Quantity` over the
        diegetic story-clock (`time:elapsed.elapsed_minutes`). Authored ONLY when time is part of
        the thread; the deadline is in IN-WORLD MINUTES, never turns.
      - `event_occurs`: a decisive loss event (the protectee killed, the alarm raised) → `Occurred`.
      - `player_learns`: a damning fact entering the player frame → `InFrame`.
    A malformed/partial spec yields None (no authored loss; the story just stays open) — never a
    build-time crash."""
    if not spec:
        return None
    if spec.get("kind") == "time_deadline":
        mins = spec.get("deadline_minutes", spec.get("deadline_elapsed_minutes"))
        if not isinstance(mins, (int, float)) or isinstance(mins, bool) or mins <= 0:
            return None
        from construct.clock import ELAPSED_ATTR, ELAPSED_ENTITY
        return Quantity(ELAPSED_ENTITY, ELAPSED_ATTR, ">=", float(mins))
    if not spec.get("entity"):
        return None
    if spec.get("kind") == "player_learns":
        if not (spec.get("attribute") and spec.get("value")):
            return None
        return InFrame(player_frame, spec["entity"], spec["attribute"], spec["value"])
    return Occurred(spec["entity"])


def refusal_clock_for(arc_id: str) -> Clock:
    """The explicit-abandonment refusal clock for `arc_id` (main or side arc), extracted
    verbatim from `_build_arc` so the clock's shape lives in one named place."""
    is_main = arc_id == "arc:main"
    slug = arc_id.split(":", 1)[1]
    # The refusal clock is NO LONGER a quiet-turn timer (founder ruling 2026-06-25 / Cx 176): turns
    # never force a close, and a turn-count refusal would even write a fabricated `refusal_conclusion`
    # into canon. It is now an EXPLICIT-ABANDONMENT clock — it fires only when an
    # `event:abandoned_<arc>` occurrence is committed (the player decisively walks away / refuses, a
    # negative commitment), never on silence/contemplation. Absent that event it never fires, so a
    # no-deadline story stays open indefinitely and nothing fabricated enters the log.
    refusal_id = "clock:refusal" if is_main else f"clock:refusal_{slug}"
    concludes = "event:world_concludes" if is_main else f"event:world_concludes_{slug}"
    abandon = "event:abandoned" if is_main else f"event:abandoned_{slug}"
    refusal = Clock(clock_id=refusal_id, fires_when=Occurred(abandon),
                    effects=({"entity": concludes, "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to=arc_id, rung=Rung.REFUSAL)
    return refusal


def _is_placeholder_premise(atom: Any, protagonist: str | None) -> bool:
    """True for `_build_arc`'s always-true PLACEHOLDER premise
    `StateIs(<protagonist>, "kind", "person")`. It carries no answered question, so it must
    never enter a chapter's settled (closed) history — otherwise the protagonist is recorded
    as "a past chapter's answer" and the notebook prints `YOU — <name> — settled`."""
    return (bool(protagonist)
            and getattr(atom, "entity", None) == protagonist
            and getattr(atom, "attribute", None) == "kind"
            and getattr(atom, "value", None) == "person")


def _build_arc(proposal: dict, arc_id: str = "arc:main") -> Arc:
    """Build an Arc from an authoring proposal. `arc_id` defaults to the main
    arc; a non-main (side) arc gets a per-arc refusal-clock id so two arcs never
    collide on `clock:refusal` in the shared `plot:main` frame (the one real
    multi-arc collision — LIVING-WORLD-GENERATOR P1)."""
    is_main = arc_id == "arc:main"
    slug = arc_id.split(":", 1)[1]
    # Non-main arcs suffix their beat ids with the arc slug so two arcs sharing
    # `plot:main` never collide on a beat status row (and the escalation/pressure
    # clock ids derived from the beat id inherit that uniqueness). The main arc
    # keeps bare `beat:<slug>` ids — byte-for-byte the pre-portfolio behavior.
    bsuffix = "" if is_main else f"_{slug}"
    protagonist = proposal["protagonist"]
    player_frame = f"knows:{protagonist}"
    beats = []
    for b in proposal["beats"]:
        raw = b["id"].split(":", 1)[-1]
        beats.append(Beat(
            beat_id=f"beat:{_slug(raw)}{bsuffix}",
            phase=Phase(b["phase"]),
            weight=Weight(b["weight"]),
            achievable_via=_beat_expr(b, player_frame),
        ))
    climax = [b.beat_id for b in beats if b.phase in (Phase.CLIMAX, Phase.CRISIS)] \
        or [beats[-1].beat_id]
    k = max(1, min(2, len(climax) - 1)) if len(climax) > 1 else 1
    shape = ConclusionShape(
        shape_id=f"shape:{slug}",
        delta_type=proposal["delta_type"],
        tension=tuple(proposal["tension"][:3]) if len(proposal["tension"]) >= 3
        else (protagonist, "drive:a", "drive:b"),
        world_condition=AtLeast(k, tuple(BeatAchieved(bid) for bid in climax)),
        premise=StateIs(protagonist, "kind", "person"),
        refusal_variant_id="shape:refused",
    )
    clocks = tuple(
        Clock(clock_id=f"clock:escalate_{b.beat_id.split(':', 1)[1]}",
              fires_when=TurnsQuiet(4 + 2 * i),
              effects=({"entity": f"event:pressure_{b.beat_id.split(':', 1)[1]}",
                        "attribute": "kind", "value": "pressure"},),
              bound_to=b.beat_id,
              rung=(Rung.SURFACE, Rung.DRAW, Rung.CONVERGE)[min(i, 2)])
        for i, b in enumerate(beats) if b.weight is Weight.REQUIRED
    )
    # Explicit-abandonment refusal clock (never a quiet-turn timer) — see refusal_clock_for.
    refusal = refusal_clock_for(arc_id)
    failure_when = _failure_expr(proposal.get("failure_when"), player_frame)
    return Arc(
        arc_id=arc_id, protagonist=protagonist, shape=shape,
        beats=tuple(beats), clocks=clocks, refusal_clock=refusal,
        climax_ready_k=k, climax_ready_beats=tuple(climax),
        phase_budget={Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3,
                      Phase.CLIMAX: 2, Phase.FALLING: 2},
        failure_when=failure_when,
    )


build_arc = _build_arc
