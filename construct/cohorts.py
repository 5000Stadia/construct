"""The Quiet Cohort calls (TURN-LOOP §2-3) and the narrator.

Each cohort is a single-purpose provider call: selectively invoked,
fail-open (the caller decides; see turnloop), silent. Tier assignment
per the founder's table: cheap for parse/extract/select, good ("main")
ONLY for the narrator and NPC engines.
"""

from __future__ import annotations

import logging

from construct.provider import Provider, complete_sync

logger = logging.getLogger(__name__)

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string",
                 "enum": ["action", "question", "ooc", "declaration"]},
        "moves_to": {"type": "string",
                     "description": "if the action moves the player to a "
                                    "place, that place exactly as the player "
                                    "named it; empty string otherwise"},
        "requires": {"type": "array", "items": {"type": "string"},
                     "description": "specific items the player claims to USE "
                                    "or produce FROM THEIR POSSESSION for "
                                    "this action ('the iron vault key'); "
                                    "empty for actions needing nothing "
                                    "specific (walking, talking, looking)"},
    },
    "required": ["kind", "moves_to", "requires"],
}

NPC_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "acts": {"type": "boolean"},
        "action": {"type": "string",
                   "description": "third-person factual description of the physical act; empty if acts=false"},
    },
    "required": ["acts", "action"],
}

NPC_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "speaks": {"type": "boolean"},
        "intent": {"type": "string",
                   "description": "what the character wants from this exchange; empty if silent"},
        "line_hint": {"type": "string", "description": "optional voice flavor"},
    },
    "required": ["speaks", "intent", "line_hint"],
}

NUDGE_SCHEMA = {
    "type": "object",
    "properties": {"thread": {"type": "string"},
                   "directive": {"type": "string"}},
    "required": ["thread", "directive"],
}

NARRATE_SCHEMA = {
    "type": "object",
    "properties": {"prose": {"type": "string"}},
    "required": ["prose"],
}

KNOWS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "attribute": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["entity", "attribute", "value"],
        }},
    },
    "required": ["facts"],
}


def seed_knows(provider: Provider, character: str, digest: str) -> dict:
    """Author a character's private knowledge frame at story start —
    frame-scoped secrecy (P4): each character knows ONLY what's in their
    frame, so the engine they're handed cannot leak what they never
    learned. Character understanding → good tier."""
    return complete_sync(provider,
        f"You are authoring the private knowledge frame of {character} at the "
        f"start of the story. A person knows a GREAT DEAL about their own "
        f"world — be generous within plausibility. INCLUDE: everything about "
        f"{character} themselves (role, history, relationships, what they "
        f"carry); the people, places, and objects they'd know through their "
        f"role and daily life; events they took part in or witnessed; and any "
        f"secret THEY THEMSELVES hold. EXCLUDE only what this character "
        f"genuinely could not know: other characters' private secrets, events "
        f"they were absent for, and mysteries not yet solved (a guilty party "
        f"knows their own guilt; an investigator does NOT yet know whodunit). "
        f"Aim for as many true facts as the digest plausibly supports — a thin "
        f"frame makes a lifeless character. Draw entity/attribute/value "
        f"triples from the world digest, using the EXACT entity ids shown.\n\n"
        f"WORLD DIGEST:\n{digest}\n\nCHARACTER: {character}",
        KNOWS_SCHEMA, tier="main")

RENDER_LEASH = (
    "THE RENDER LEASH (binding): describe only what the briefing supports. "
    "Introduce NO new named entities, NO new events, NO facts beyond the "
    "briefing. Dress ambiguity as ambiance, never as information. If the "
    "player probes something the briefing does not cover, narrate honest "
    "uncertainty (the world will resolve it next turn). Stay in voice; "
    "second person present tense for the player."
)


def player_constraint(protagonist: str) -> str:
    """The player-character boundary (letter 025 — binding on every
    nudge and render): the arc pushes the world AT the player; it cannot
    move them."""
    return (
        f"THE PLAYER CHARACTER (hard constraint): {protagonist} IS the "
        f"player — always and only 'you', second person. NEVER script, "
        f"author, or invent {protagonist}'s actions, words, reactions, "
        f"gestures, or internal state — their actions are EXACTLY what the "
        f"player's input states, nothing more. NEVER render {protagonist} "
        f"in third person and NEVER place them in the scene as a separate "
        f"character. The world and other characters act TO and AROUND "
        f"'you'; only the player moves 'you'."
    )


def classify(provider: Provider, player_input: str) -> dict:
    """Returns {kind, moves_to} — movement intent rides the same call
    (letter 026: extraction alone misses relocations; the host commits
    them through the gate deterministically)."""
    return complete_sync(provider,
        f"Classify this player input from an interactive-fiction session "
        f"by INTENT, not punctuation.\n"
        f"- action: the character does, says, or OBSERVES something in the "
        f"world. Looking around, examining, scanning a vista — observation "
        f"is an action even phrased as a question ('what do I see around "
        f"me?' = action).\n"
        f"- question: a factual query to the record or the character's own "
        f"memory about world state, NOT an in-scene act ('is the door "
        f"locked?', 'where did I leave my spoon?').\n"
        f"- ooc: out-of-character/meta (save, help, complaints)\n"
        f"- declaration: the player authors a fact into the world (co-author move)\n\n"
        f"Additionally: if the action MOVES the player somewhere, set "
        f"moves_to to the destination exactly as the player named it "
        f"('the wellhead', 'my quarters'); otherwise empty string. Walking "
        f"off within the same place is not a move.\n"
        f"Additionally: list in `requires` any specific item the player "
        f"claims to use or produce from their possession (keys, tools, "
        f"documents) — the world will verify they actually hold it. Empty "
        f"for actions needing nothing specific.\n\n"
        f"INPUT: {player_input}",
        CLASSIFY_SCHEMA, tier="cheap")


def npc_world_action(provider: Provider, npc_id: str, sheet: str, scene: str,
                     protagonist: str) -> dict:
    return complete_sync(provider,
        f"You are {npc_id}. CHARACTER SHEET (your knowledge and dispositions — "
        f"you know NOTHING beyond this):\n{sheet}\n\nCURRENT SCENE:\n{scene}\n\n"
        f"Decide whether this character takes a PHYSICAL action right now "
        f"(moving, taking, doing — not talking), driven by their OWN "
        f"dispositions. Most turns: acts=false. Your action may never "
        f"include, script, or presume anything done or said by "
        f"{protagonist} (the player's character).",
        NPC_ACTION_SCHEMA, tier="main")


def npc_intent(provider: Provider, npc_id: str, sheet: str, scene: str,
               protagonist: str) -> dict:
    return complete_sync(provider,
        f"You are {npc_id}. CHARACTER SHEET (your entire knowledge — "
        f"you know NOTHING beyond this):\n{sheet}\n\nCURRENT SCENE:\n{scene}\n\n"
        f"Decide whether this character speaks this turn and what they want. "
        f"Never speak or act FOR {protagonist} (the player's character).",
        NPC_INTENT_SCHEMA, tier="main")


def nudge_pick(provider: Provider, rung: str, threads: list[str], scene: str,
               protagonist: str) -> dict:
    return complete_sync(provider,
        f"You are a story navigator. Escalation rung: {rung}.\n"
        f"Unwalked story threads (the player has not seen these):\n"
        + "\n".join(f"- {t}" for t in threads)
        + f"\n\nCURRENT SCENE:\n{scene}\n\n{player_constraint(protagonist)}\n\n"
        f"Pick the ONE thread that fits this scene most naturally and write "
        f"a one-line directive for how the world surfaces it diegetically. "
        f"The directive may author ONLY what OTHER entities and the world do "
        f"to or around the player (press, arrive, glare, refuse to leave, "
        f"surface a record) — never what the player does, says, feels, or "
        f"decides. Pressure, not puppetry.",
        NUDGE_SCHEMA, tier="cheap")


def narrate(provider: Provider, briefing: str, protagonist: str) -> str:
    result = complete_sync(provider,
        f"You are the narrator of a text construct.\n\nBRIEFING (everything "
        f"you know — there is nothing else):\n{briefing}\n\n{RENDER_LEASH}\n\n"
        f"{player_constraint(protagonist)}\n\n"
        f"A pacing directive, if present, describes what the WORLD does; if "
        f"any part of it would script the player, render only the world's "
        f"side of it and leave the player's response to the player.\n\n"
        f"Render this turn: 1-3 paragraphs.",
        NARRATE_SCHEMA, tier="main")
    return result["prose"]
