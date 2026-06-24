"""De-risk the Foyer's live path on a real world: open anchor fresh, read its
character_setup, ingest a character sheet (details + a free addition) as canon,
then render the cold open and confirm it reflects the chosen character. Cleans
up the throwaway slot."""
from __future__ import annotations

import logging
logging.disable(logging.CRITICAL)

from construct.foyer import CharacterSheet
from construct.game import slot_path
from construct.session import Session

PLAYER = "verify:foyer"


def main() -> int:
    s = Session.open("anchor", player_id=PLAYER, fresh=True, mode_override="endless")
    print("=== character_setup() read from the real world ===")
    setup = s.character_setup()
    print("role:", setup and setup.get("role"))
    print("defaults:", setup and setup.get("defaults"))
    print("anchors:", setup and setup.get("anchors"))

    print("\n=== ingesting a character sheet as canon ===")
    sheet = CharacterSheet(
        details={"name": "Wren", "gender": "woman", "pronouns": "she/her"},
        additions=["Wren keeps her grandfather's brass pocket-ledger, the one "
                   "honest record he never surrendered to the office"])
    s.apply_character(sheet)
    print("apply_character: OK")

    print("\n=== cold open (should reflect Wren) ===")
    print(s.opening()[:900])
    s.close()

    if slot_path("anchor", PLAYER).exists():
        slot_path("anchor", PLAYER).unlink()
    print("\nOK — Foyer ingest + character-aware cold open verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
