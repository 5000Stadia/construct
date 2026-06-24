"""Feel the Foyer (character creation) live, without a real world/ingest.

Drives `foyer_step` with the live CodexProvider through a scripted character
phase — including the founder's rule-of-cool negotiation (Smash Bros in a
medieval realm) — printing the GUEST/CONSTRUCT exchange and the character sheet
it assembles. Stops at `done` (no ingest, no cold open).

    python scripts/foyer_demo.py
"""

from __future__ import annotations

import sys

from construct.foyer import CharacterSheet, foyer_step
from construct.provider import CodexProvider

ROLE = "an apprentice mage at the Hollow Conservatory of esoteric arts"
ANCHORS = [
    "Maon — the severe master who taught you your first true sigil; prizes and "
    "distrusts you in equal measure",
    "a sibling who left the Conservatory years ago under a cloud no one names",
]
DEFAULTS = {"name": "Coren", "gender": "unspecified", "background":
            "a ward of the Conservatory since childhood"}

SCRIPT = [
    "call me Wren, she/her",
    "you pick my background",
    "oh, and I had a rivalry with the head of the rival house",
    "also — start me off playing Super Smash Brothers in my dorm with my friend Greg",
    "no, keep everything high-fantasy, but say I have the only working TV in the kingdom and it plays it",
    "perfect, that's everything — let's begin",
]


def main(argv: list[str]) -> int:
    script = argv[1:] or SCRIPT
    provider = CodexProvider()
    sheet = CharacterSheet()
    history: list[str] = []

    print("=== Foyer demo (no world/ingest) ===")
    print(f"ROLE: {ROLE}\n")
    for msg in script:
        print(f"GUEST: {msg}")
        result = foyer_step(provider, sheet, "\n".join(history[-12:]), msg,
                            role=ROLE, anchors=ANCHORS, defaults=DEFAULTS)
        print(f"CONSTRUCT: {result.reply}\n")
        history += [f"GUEST: {msg}", f"CONSTRUCT: {result.reply}"]
        if result.done:
            break
    print("--- the character sheet the Foyer would ingest ---")
    print(sheet.summary() or "(empty)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
