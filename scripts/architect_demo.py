"""Feel the Construct dialogue live, without triggering a real build.

Drives `architect_step` with the live CodexProvider through a scripted arrival
(or messages passed on argv), printing the GUEST/CONSTRUCT exchange, the tool
calls the agent emitted, and — on begin_build — the assembled brief it WOULD
hand to the generator. It stops at the brief (no ~16-min build), so this is a
fast way to tune the voice + convergence (CONSTRUCT-DIALOGUE.md, build order §1).

    python scripts/architect_demo.py
    python scripts/architect_demo.py "a gritty colonial-survival saga" "I'm the doctor" "give me a real ending" "go"
"""

from __future__ import annotations

import sys

from construct.architect import BUILD, LOAD, ArchitectState, architect_step
from construct.provider import CodexProvider

#: A default scripted arrival (the design doc's example, plus a T-Rex).
DEFAULT_SCRIPT = [
    "something like a noir mystery but on a space station",
    "can I be the station's AI?",
    "a real case — what happens if I lose?",
    "oh, and put a T-Rex with a machine gun somewhere aboard",
    "that's everything, go",
]

#: The library a real Atrium would offer to pick_world.
WORLDS = ["anchor"]


def main(argv: list[str]) -> int:
    script = argv[1:] or DEFAULT_SCRIPT
    provider = CodexProvider()
    state = ArchitectState()
    history_lines: list[str] = []

    print("=== Construct dialogue demo (no build is triggered) ===\n")
    for msg in script:
        print(f"GUEST: {msg}")
        history = "\n".join(history_lines[-12:])
        result = architect_step(provider, state, history, msg, WORLDS)
        print(f"CONSTRUCT: {result.reply}")
        history_lines += [f"GUEST: {msg}", f"CONSTRUCT: {result.reply}"]
        if result.outcome == BUILD:
            print("\n--- begin_build → the brief Construct would cook ---")
            for k, v in (result.brief or {}).items():
                print(f"  {k}: {v!r}")
            return 0
        if result.outcome == LOAD:
            print(f"\n--- pick_world → would open existing world: {result.world} ---")
            return 0
        print()
    print("(dialogue ended without a terminal action — brief so far)")
    print(state.summary() or "(empty)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
