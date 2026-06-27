"""The Foyer — the character-creation tool loop (host side).

The WHO phase of session-zero (`docs/design/CHARACTER-CREATION.md`): after the
world is built/loaded and before turn one, the guest co-authors who they are and
any last world elements. The `foyer_turn` cohort interprets intent into TOOL
CALLS; this module executes them against an accumulating `CharacterSheet` and
loops until the guest is ready. Then the sheet is ingested as canon before the
cold open. Same agent-with-tools shape as `architect` ([[agent-as-tools-principle]]).

The cohort is the only model call; everything here is deterministic host logic
(stub-testable). The world-anchor read and the chargen→canon ingest live in the
transport layer (CHARACTER-CREATION.md §Build order phases 2-3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from construct import cohorts
from construct.provider import Provider

logger = logging.getLogger(__name__)


@dataclass
class CharacterSheet:
    """The character the guest shapes in the Foyer. `details` holds the structured
    fields (name, gender, pronouns, background, …); `additions` holds free
    history/world elements (the rivalry, the negotiated automata vision-box). Pure
    data; the transport persists it per player so the Foyer survives a restart."""

    details: dict = field(default_factory=dict)
    additions: list = field(default_factory=list)

    def set_detail(self, name: str, value: str) -> None:
        if name and value:
            self.details[name] = value

    def add(self, element: str) -> None:
        if element:
            self.additions.append(element)

    def summary(self) -> str:
        """Rendered for the cohort — fresh each turn, so it never re-asks what's
        already settled (the Cognitive-UI discipline)."""
        lines: list[str] = []
        for k, v in self.details.items():
            lines.append(f"{k}: {v}")
        for a in self.additions:
            lines.append(f"+ {a}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"details": dict(self.details), "additions": list(self.additions)}

    @classmethod
    def from_dict(cls, data: dict | None) -> "CharacterSheet":
        data = data or {}
        return cls(details=dict(data.get("details") or {}),
                   additions=list(data.get("additions") or []))


#: The character-detail fields written straight onto the protagonist as canon.
_DETAIL_ATTRS = ("name", "gender", "pronouns", "background")

#: Fields that MUST be set before the Foyer may finish. The open-conversation
#: capture can miss one (a guest narrates their backstory but never states
#: pronouns), so the host GATES `done` until these are present (founder: "set
#: required criteria for it to hit before we start"). Pronouns drive every later
#: narration, so they're non-negotiable; name anchors the protagonist.
REQUIRED_DETAILS = ("name", "pronouns")


def _ask_required(field: str) -> str:
    """The concise question the host asks when a REQUIRED field is still unset at
    `done` — a single, clear prompt, not a re-interview."""
    if field == "pronouns":
        return ("Before we step in — your pronouns? 1. he/him  2. she/her  "
                "3. they/them or other.")
    if field == "name":
        return "Before we step in — what name shall the world know you by? (or “you decide”)."
    return f"Before we step in — could you settle your {field}?"


def state_value(porcelain: Any, entity: str, attribute: str) -> str | None:
    """The bare canon value for (entity, attribute), or None. `porcelain.state`
    returns a structured `{status, fact:{value}}` dict — unwrap it the way
    `adapter.PorcelainWorldReads.state` does (known/conflicted → the value)."""
    try:
        st = porcelain.state(entity, attribute)
    except Exception:
        return None
    if isinstance(st, dict) and st.get("status") in ("known", "conflicted"):
        return (st.get("fact") or {}).get("value")
    return None


def world_anchors(world: Any, scope: list[str] | None, protagonist: str) -> list[str]:
    """The world's threads tied to the protagonist — the arc-scope entities the
    fiction connected to them (a mentor, an agency, a relative). Read straight
    from canon (the engine is the truth); each rendered as a short anchor line the
    Foyer can surface. Best-effort; never sinks the phase."""
    anchors: list[str] = []
    p = getattr(world, "porcelain", None)
    for entity in (scope or []):
        if entity == protagonist or not p:
            continue
        kind = state_value(p, entity, "kind") or entity.split(":", 1)[0]
        name = (state_value(p, entity, "name")
                or entity.split(":", 1)[-1].replace("_", " "))
        feel = (state_value(p, entity, "role") or state_value(p, entity, "feel")
                or state_value(p, entity, "disposition") or "")
        anchors.append(f"{name} ({kind})" + (f" — {feel}" if feel else ""))
    return anchors


def ingest_character(world: Any, provider: Provider, protagonist: str,
                     sheet: CharacterSheet) -> None:
    """Commit the finished sheet as `stated` canon BEFORE turn one (the engine-
    truth payoff: player-authored elements become structurally-identical canon).
    Protagonist details write directly; free additions are grounded into entities/
    relations via `ingest_additions` and committed through the same doorway."""
    p = world.porcelain
    rows = [{"entity": protagonist, "attribute": k, "value": v}
            for k, v in sheet.details.items()
            if k in _DETAIL_ATTRS and v]
    if rows:
        p.ingest_structured(rows)
    if sheet.additions:
        from construct.game import _world_digest
        try:
            result = cohorts.ingest_additions(provider, sheet.additions,
                                               _world_digest(world), protagonist)
            items = [it for it in (result.get("items") or [])
                     if it.get("entity") and it.get("attribute")]
            if items:
                p.ingest_structured(items)
        except Exception:
            # Fail-open: a grounding miss must not block the story. Keep the
            # additions as plain history facts so the narrator still honors them.
            logger.exception("addition grounding failed; storing as history facts")
            p.ingest_structured([{"entity": protagonist, "attribute": "history",
                                  "value": a} for a in sheet.additions])


@dataclass
class FoyerResult:
    """What one Foyer step returns to the transport: the line to speak, and whether
    the guest is ready to begin (→ ingest the sheet, then the cold open)."""

    reply: str
    done: bool = False


def foyer_open(provider: Provider, *, role: str = "", anchors: list[str] | None = None,
               defaults: dict | None = None, theme: str = "", world_brief: str = "",
               suggested_name: str = "") -> str:
    """The Foyer's opening line — a brief, on-theme welcome that ESTABLISHES THE
    WORLD, then situates the role in it, then invites the guest in (an interview,
    not a wall of text). A synthetic 'arrival' turn; returns just the spoken line.
    The protagonist's NAME is the player's to choose (founder): present them by ROLE
    with the name To-Be-Determined; the authored `suggested_name` is offered as a
    default to keep, never imposed as 'you are <Name>'."""
    keep = (f"They have NO fixed name yet — it is the player's to choose now and it "
            f"will become canon. There is a suggested default they MAY keep: "
            f"'{suggested_name}'. Frame the question as choosing who they are — 'shall "
            f"I call you {suggested_name}, or will you take another name?' — NOT as "
            f"renaming an existing person."
            if suggested_name else
            "Ask the player to choose their name (or let you pick one).")
    r = foyer_step(provider, CharacterSheet(), "",
                   "(The guest has just arrived. Give the D&D-style pregame as a "
                   "BACK-OF-THE-BOOK blurb — concrete, not just mood — in 3-5 "
                   "sentences: FIRST establish the WORLD from THE WORLD brief below — "
                   "WHEN/WHERE (the era and place, concretely) and WHAT THE SYSTEM IS "
                   "(the central institution and what it does to people); THEN place "
                   "the ROLE in that system — the player's function and why it matters "
                   "(present them by that ROLE, NOT by a fixed personal name); THEN ask "
                   "just the FIRST single question — their NAME — framed with a small "
                   "diegetic touch (a sensory beat, e.g. the still-blank name-plate at "
                   f"their station). {keep} One question, not a checklist — the "
                   "interview paints the picture one beat at a time from here.)",
                   role=role, anchors=anchors, defaults=defaults, theme=theme,
                   world_brief=world_brief)
    return r.reply


def foyer_step(provider: Provider, sheet: CharacterSheet, history: str,
               user_msg: str, *, role: str = "", anchors: list[str] | None = None,
               defaults: dict | None = None, theme: str = "",
               world_brief: str = "") -> FoyerResult:
    """One turn of the Foyer: call the cohort, apply the tool calls it emitted to
    `sheet` (mutated in place; the transport persists it), and return the reply +
    whether the guest is ready. `done` wins the turn once present."""
    turn = cohorts.foyer_turn(provider, history, sheet.summary(), user_msg,
                              role, anchors or [], defaults or {}, theme=theme,
                              world_brief=world_brief)
    reply = str(turn.get("reply") or "").strip()
    done = False

    for action in turn.get("actions") or []:
        tool = action.get("tool")
        field_name = str(action.get("field") or "").strip()
        value = str(action.get("value") or "").strip()
        if tool == "set_detail":
            sheet.set_detail(field_name, value)
        elif tool == "add_element":
            sheet.add(value)
        elif tool == "done":
            done = True
        elif tool == "chat":
            pass  # just talk / negotiate; no state change
        else:
            logger.warning("foyer: unknown tool %r ignored", tool)

    # Hard gate: never finish with a REQUIRED field unset, even if the cohort said
    # done — the open conversation may have skipped pronouns. Ask for the missing
    # one and stay in the Foyer (founder).
    if done:
        missing = [f for f in REQUIRED_DETAILS if not sheet.details.get(f)]
        if missing:
            done = False
            ask = _ask_required(missing[0])
            reply = f"{reply}\n\n{ask}" if reply else ask

    return FoyerResult(reply=reply, done=done)
