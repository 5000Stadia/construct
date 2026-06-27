"""Build the three dialed-in baseline SHOWCASE worlds (founder-approved set):
  1. latch     — Victorian locked-room detective (deduction; the cerebral one)
  2. thedeep   — deep-sea survival (endurance; the gauge + clock, the visceral one)
  3. emberroad — high-fantasy quest (journey/hidden-arc; the epic one)

Each via the production generate-then-ingest path, then a quick sanity check (opening
+ a couple of turns) so we know it actually plays. Transcript → logs/presets-build-*.md.
Retiring The Last Honest Meter (anchor) happens AFTER these seal, in a separate step.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.game import create_scenario_from_generated, scenario_path, _unpublish_scenario, slot_path
from construct.provider import CodexProvider
from construct.session import Session
from construct.transport_core import _humanize_stage

PRESETS = [
    {"name": "latch",
     "seed": ("a foggy, gaslit Victorian London. A wealthy financier is found dead in his locked "
              "study — the door bolted and the only window latched from the inside — and his private "
              "ledgers are missing. The household and a few late callers each carried a debt, a "
              "grudge, or a secret, and each has an alibi that almost holds."),
     "win": ("name who killed him and explain how the locked room was done; you lose if you accuse "
             "the wrong person"),
     "play_as": "a sharp consulting detective called in before the police trample the scene",
     "moves": ["I take in the study and the body, then ask who found him and who was in the house tonight.",
               "I examine the latched window and the bolted door closely for how it was really done."]},
    {"name": "thedeep",
     "seed": ("a deep-sea mining station three miles down on the Pacific floor, its cable to the "
              "surface severed by a seabed quake. The emergency lights are failing, the hull groans "
              "under the pressure, the air is running low, and something got inside when the airlock "
              "seal cracked. A handful of crew are left, and not all of them keep their heads."),
     "win": "get yourself and as many of the crew as you can out alive before the air runs out",
     "play_as": "the station's engineer — the one who knows exactly how little air is left",
     "moves": ["I check the air readout and the hull, then rally whoever's still on their feet.",
               "I move to seal the cracked airlock and find out what got in."]},
    {"name": "emberroad",
     "seed": ("a quiet hearth-village at the edge of the known lands. An old relic kept above the "
              "fireplace has begun to wake and burn cold, and word comes that the thing that forged "
              "it is stirring in the mountain to the east. The only road there is long and ill-omened, "
              "with companions to be found and lost along the way."),
     "win": "carry the waking relic to the mountain and decide its fate — and yours",
     "play_as": "an unlikely villager who didn't ask to be the one to go",
     "moves": ["I take the cold-burning relic down and ask the village elder what they know of the mountain.",
               "I set out on the east road, watchful for who or what travels it."]},
]

OUT = Path("logs") / f"presets-build-{int(time.time())}.md"
OUT.parent.mkdir(exist_ok=True)
_buf: list[str] = []


def w(line: str) -> None:
    _buf.append(line)
    OUT.write_text("\n".join(_buf))
    print(line, flush=True)


def main() -> None:
    prov = CodexProvider()
    w("# SHOWCASE PRESETS — build + sanity check\n")
    for spec in PRESETS:
        name = spec["name"]
        w(f"\n# ===== {name} =====\n")
        if scenario_path(name).exists():
            _unpublish_scenario(name)
        for p in (slot_path(name, "preset"),):
            if p.exists():
                p.unlink()
        t0 = time.time()
        try:
            meta = create_scenario_from_generated(
                name, prov, seed=spec["seed"], endless=False,
                win_direction=spec["win"], play_as=spec["play_as"],
                on_stage=lambda m: w("  " + (_humanize_stage(m) or f"· {m}…")))
        except Exception as exc:  # noqa: BLE001
            w(f"\n*** BUILD FAILED for {name}: {exc} ***\n")
            continue
        w(f"\n*(built in {time.time()-t0:.0f}s)*")
        w(f"TITLE: {meta.get('title')!r}   protagonist: {meta.get('protagonist')!r}   "
          f"theme: {meta.get('theme','')!r}   game_type: {meta.get('game_type', meta.get('game_types'))!r}\n")
        try:
            s = Session.open(name, player_id="preset", fresh=True, provider=prov)
            w("## OPENING\n")
            w(s.opening() + "\n")
            for i, inp in enumerate(spec.get("moves", []), 1):
                r = s.turn(inp)
                w(f"\n## {name} turn {i}\n> **Player:** {inp}\n")
                w((r.prose or "(empty)") + "\n")
            s.close()
        except Exception as exc:  # noqa: BLE001
            w(f"\n*** PLAY CHECK FAILED for {name}: {exc} ***\n")
    w("\n--- END ---")
    print(f"\nTranscript: {OUT}")


if __name__ == "__main__":
    main()
