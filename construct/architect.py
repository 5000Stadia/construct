"""The Construct dialogue — the holodeck-arrival tool loop (host side).

The conversational session-zero (`docs/design/CONSTRUCT-DIALOGUE.md`): the guest
talks naturally, the `architect_turn` cohort interprets intent into TOOL CALLS,
and this module executes them against an accumulating brief, looping across the
guest's messages until they're satisfied. Then it hands the assembled brief to
the build path (`game.create_scenario_from_*`) or routes to an existing world.

The cohort is the only model call; everything here is deterministic host logic
(stub-testable). Kernos's lesson: render the state FRESH for the agent each turn
(`ArchitectState.summary`), don't blind-accumulate the raw transcript.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from construct import cohorts
from construct.provider import Provider

logger = logging.getLogger(__name__)

#: A turn outcome. "continue" keeps the dialogue open; "build" hands a brief to
#: the generator; "load" opens an existing world fresh; "resume" reopens the
#: guest's saved game where they left off. Terminal outcomes end the Atrium.
CONTINUE, BUILD, LOAD, RESUME = "continue", "build", "load", "resume"


@dataclass
class ArchitectState:
    """The brief assembled through the dialogue. Pure data; the transport
    persists it per player so the conversation survives a restart."""

    elements: list[str] = field(default_factory=list)
    play_as: str = ""
    mode: str = ""            # "win_loss" | "endless" | "" (not yet chosen)
    win_direction: str = ""   # the hidden destination direction (win_loss only)
    game_types: list[str] = field(default_factory=list)  # taxonomy keys (primary + secondaries)

    def summary(self) -> str:
        """The brief rendered for the agent — fresh each turn (the Cognitive-UI
        principle), so it never re-asks what's already gathered."""
        lines: list[str] = []
        if self.elements:
            lines.append("World so far: " + "; ".join(self.elements))
        if self.play_as:
            lines.append(f"Playing as: {self.play_as}")
        if self.mode == "win_loss":
            lines.append("Ending: a story that builds to a win/loss"
                         + (f" (direction: {self.win_direction})"
                            if self.win_direction else ""))
        elif self.mode == "endless":
            lines.append("Ending: open-ended / freeplay (no win or loss)")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for per-player persistence (registry `creation` blob)."""
        return {"elements": list(self.elements), "play_as": self.play_as,
                "mode": self.mode, "win_direction": self.win_direction,
                "game_types": list(self.game_types)}

    @classmethod
    def from_dict(cls, data: dict | None) -> "ArchitectState":
        data = data or {}
        return cls(elements=list(data.get("elements") or []),
                   play_as=data.get("play_as") or "",
                   mode=data.get("mode") or "",
                   win_direction=data.get("win_direction") or "",
                   game_types=list(data.get("game_types") or []))

    def to_brief(self) -> dict:
        """The build inputs — what `create_scenario_from_generated` consumes.
        `mode` defaults to endless (the safe default) if the dialogue never
        settled an ending."""
        return {
            "premise": " — ".join(self.elements),
            "play_as": self.play_as,
            "mode": self.mode or "endless",
            "win_direction": self.win_direction if self.mode == "win_loss" else "",
            "game_types": list(self.game_types),
        }


@dataclass
class ArchitectResult:
    """What one dialogue step returns to the transport: the line to speak, the
    outcome, and (on a terminal outcome) the brief to build or world to load."""

    reply: str
    outcome: str = CONTINUE
    brief: dict | None = None     # outcome == BUILD
    world: str | None = None      # outcome == LOAD or RESUME
    show_library: bool = False    # the host should append the rendered world menu


def _resolve_world(detail: str, worlds: list[str], catalog: dict | None) -> str | None:
    """Map a pick_world `detail` to a canonical scenario name. Accepts the name
    directly, or a spoken TITLE from the catalog (case-insensitive). Returns None
    if it matches nothing in the library (never route to an invented name)."""
    if detail in worlds:
        return detail
    low = detail.strip().lower()
    for name, title in (catalog or {}).items():
        t = str(title).lower()
        if low and (low == t or low == name.lower() or low in t):
            return name
    return None


def architect_step(provider: Provider, state: ArchitectState, history: str,
                   user_msg: str, worlds: list[str],
                   resumable: str = "", catalog: dict | None = None) -> ArchitectResult:
    """One turn of the Construct dialogue: call the cohort, apply the tool calls
    it emitted to `state`, and return the reply + outcome. `state` is mutated in
    place (the transport persists it). The FIRST terminal action (begin_build /
    a valid pick_world / resume) wins the turn; later terminals are ignored.
    `resumable` (if set) is the world the guest may `resume`; `catalog` maps
    scenario name → display title so a guest can pick a world by its title."""
    turn = cohorts.architect_turn(provider, history, state.summary(), user_msg,
                                  worlds, resumable=resumable, catalog=catalog)
    reply = str(turn.get("reply") or "").strip()
    outcome, brief, world = CONTINUE, None, None
    show_library = False

    for action in turn.get("actions") or []:
        tool = action.get("tool")
        detail = str(action.get("detail") or "").strip()
        if tool == "add_element":
            if detail:
                state.elements.append(detail)
        elif tool == "set_role":
            if detail:
                state.play_as = detail
        elif tool == "set_game_type":
            # Resolve the free label to a taxonomy key; keep a primary + up to two
            # secondaries (a compound). Unknown labels are dropped (free improvised).
            from construct import play_styles
            k = play_styles.match(detail)
            if k and k not in state.game_types and len(state.game_types) < 3:
                state.game_types.append(k)
        elif tool == "set_ending":
            mode = action.get("mode") or ""
            if mode in ("win_loss", "endless"):
                state.mode = mode
                state.win_direction = detail if mode == "win_loss" else ""
        elif tool == "pick_world":
            # Universal front door — resolve to a real library world (by name or
            # spoken title); never invent one. First valid pick ends the turn.
            picked = _resolve_world(detail, worlds, catalog)
            if outcome == CONTINUE and picked:
                outcome, world = LOAD, picked
        elif tool == "resume":
            # Only if the guest actually has a saved game (never fabricate one).
            if outcome == CONTINUE and resumable:
                outcome, world = RESUME, resumable
        elif tool == "begin_build":
            # The guest is satisfied → cook with everything brought. begin_build
            # outranks a same-turn pick_world (an explicit "go" is a build).
            outcome, brief, world = BUILD, state.to_brief(), None
        elif tool == "show_library":
            show_library = True  # host appends the rendered world menu
        elif tool == "chat":
            pass  # just talk; no state change
        else:
            logger.warning("architect: unknown tool %r ignored", tool)

    return ArchitectResult(reply=reply, outcome=outcome, brief=brief, world=world,
                           show_library=show_library)
