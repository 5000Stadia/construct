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
    surprise_offer: list[str] = field(default_factory=list)   # host-rolled shape awaiting the guest's yes
    surprise_declined: list[str] = field(default_factory=list)  # families the guest waved off this session

    def summary(self) -> str:
        """The brief rendered for the agent — fresh each turn (the Cognitive-UI
        principle), so it never re-asks what's already gathered."""
        lines: list[str] = []
        if self.surprise_offer:
            from construct.play_styles import names as _gt_names
            lines.append(
                "HOST-ROLLED PROPOSAL awaiting the guest's word: "
                + " + ".join(_gt_names(self.surprise_offer))
                + " (they accept → begin_build; they want another roll → "
                  "reroll_surprise; they redirect with their own idea → ordinary "
                  "tools, the proposal dissolves)")
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
                "game_types": list(self.game_types),
                "surprise_offer": list(self.surprise_offer),
                "surprise_declined": list(self.surprise_declined)}

    @classmethod
    def from_dict(cls, data: dict | None) -> "ArchitectState":
        data = data or {}
        return cls(elements=list(data.get("elements") or []),
                   play_as=data.get("play_as") or "",
                   mode=data.get("mode") or "",
                   win_direction=data.get("win_direction") or "",
                   game_types=list(data.get("game_types") or []),
                   surprise_offer=list(data.get("surprise_offer") or []),
                   surprise_declined=list(data.get("surprise_declined") or []))

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
    show_styles: bool = False     # the host should append the 155-shape wall (founder 2026-07-05)


def _surprise_draw(catalog: dict | None, declined: list[str] | None = None) -> list[str]:
    """FOUNDER (2026-07-05, "is the default story option murder mystery?"): a full
    'choose for me' must range across the WHOLE game-type taxonomy — never the
    model's prior, which converges on murder mysteries when handed an empty brief.
    The HOST draws: a random FAMILY (uniform across families, so the big
    Investigation family can't dominate by card count), then a random card within
    it — excluding families already represented in the guest's library, so a
    collection grows BREADTH — plus a secondary card from a different family (the
    architect's own compound-play guidance). Real dice, host-side."""
    import json as _json
    import random

    from construct.play_styles_data import STYLE_CARDS
    represented: set[str] = set()
    try:
        from construct.game import scenario_path
        for name in (catalog or {}):
            mp = scenario_path(name).with_suffix(".meta.json")
            if mp.exists():
                for gt in (_json.loads(mp.read_text()).get("game_type") or []):
                    c = STYLE_CARDS.get(gt)
                    if c:
                        represented.add(c["family"])
    except Exception:  # noqa: BLE001 — exclusion is enrichment, never a gate
        represented = set()
    families: dict[str, list[str]] = {}
    for key, c in STYLE_CARDS.items():
        families.setdefault(c["family"], []).append(key)
    represented |= set(declined or [])
    fresh = sorted(f for f in families if f not in represented) or sorted(families)
    fam = random.choice(fresh)
    primary = random.choice(sorted(families[fam]))
    others = sorted(f for f in families if f != fam)
    picks = [primary]
    if others:
        picks.append(random.choice(sorted(families[random.choice(others)])))
    return picks


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
    show_styles = False

    for action in turn.get("actions") or []:
        tool = action.get("tool")
        detail = str(action.get("detail") or "").strip()
        if tool == "add_element":
            if detail:
                state.elements.append(detail)
                state.surprise_offer = []  # the guest took the wheel — the roll dissolves
        elif tool == "reroll_surprise":
            # the guest waved off the rolled shape — remember the family, roll fresh,
            # and ASK again (founder: candid "how does an X sound?").
            from construct.play_styles import names as _gt_names2
            from construct.play_styles_data import STYLE_CARDS as _SC
            for k in state.surprise_offer:
                fam = (_SC.get(k) or {}).get("family")
                if fam and fam not in state.surprise_declined:
                    state.surprise_declined.append(fam)
            state.surprise_offer = _surprise_draw(catalog, state.surprise_declined)
            _nm = _gt_names2(state.surprise_offer)
            reply = (f"Another roll, then — how does {_nm[0].lower()}"
                     + (f" with a thread of {_nm[1].lower()}" if len(_nm) > 1 else "")
                     + " sound? Or once more, if that one doesn't sing.")
            logger.info("surprise re-rolled: %s (declined families %s)",
                        state.surprise_offer, state.surprise_declined)
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
                state.surprise_offer = []  # a chosen shape outranks the roll
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
            if not state.elements and not state.game_types:
                from construct.play_styles import names as _gt_names
                if state.surprise_offer:
                    # the guest heard the roll and said yes — build the offered shape
                    drawn = list(state.surprise_offer)
                    brief["game_types"] = drawn
                    brief["premise"] = (
                        "A surprise commission — the dice have chosen the SHAPE OF "
                        "PLAY: " + " blended with ".join(_gt_names(drawn)) +
                        ". Build a world that makes that shape sing — any era, "
                        "setting, and culture that serves it best; range boldly. Do "
                        "NOT default to a detective's murder case unless the drawn "
                        "shape demands one.")
                    logger.info("surprise build accepted: %s", drawn)
                else:
                    # PURE delegation with nothing offered yet: roll — then ASK
                    # candidly (founder 2026-07-05: "how does an X sound?") instead
                    # of building unseen. The build waits for the guest's yes.
                    drawn = _surprise_draw(catalog, state.surprise_declined)
                    state.surprise_offer = drawn
                    outcome, brief = CONTINUE, None
                    _names = _gt_names(drawn)
                    reply = (f"The dice have spoken — how does "
                             f"{_names[0].lower()}"
                             + (f" with a thread of {_names[1].lower()}"
                                if len(_names) > 1 else "")
                             + " sound? Say the word and I'll build it — or "
                               "I'll happily roll again.")
                    logger.info("surprise offer rolled: %s", drawn)
        elif tool == "show_library":
            show_library = True  # host appends the rendered world menu
        elif tool == "show_styles":
            show_styles = True   # host appends the full wall of play-shapes
        elif tool == "chat":
            pass  # just talk; no state change
        else:
            logger.warning("architect: unknown tool %r ignored", tool)

    return ArchitectResult(reply=reply, outcome=outcome, brief=brief, world=world,
                           show_library=show_library, show_styles=show_styles)
