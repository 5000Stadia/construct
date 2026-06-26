"""FINAL EXHAUSTIVE end-to-end test (founder: "one final exhaustive test", "Both").

The one path every hand-authored harness this session deliberately bypassed: the REAL
auto-build pipeline, played unscripted to a conclusion, then continued to episode 2.

  1. BUILD a fresh world via `create_scenario_from_generated` (the production
     generate-then-ingest the transport uses) — cast authoring, solvability gate,
     staging, the lot. Stages logged as they fire.
  2. PLAY it AT LENGTH with the mixed LLM player-agent (follow-thread / lived-knowledge
     / push-edges / resolve), logging the full transcript + per-turn traces.
  3. CONCLUDE-then-CONTINUE: author episode 2 from the prior adventure, play a few turns.

The transcript is written to logs/final-exhaustive-*.md for the dual review-score
(C + Cx grade the experience as exemplary live fiction). Live CodexProvider throughout.

Run:  PYTHONPATH=. .venv/bin/python scripts/final_exhaustive.py
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.game import (
    continue_episode, create_scenario_from_generated, slot_path, _unpublish_scenario,
)
from construct.provider import CodexProvider
from construct.session import Session
from construct.transport_core import _humanize_stage

NAME = "final_exhaustive"
PLAYER = "final"
SEED = ("a noir murder mystery in a rain-soaked harbor city; a dead shipping clerk, "
        "a falsified manifest, a handful of people with reasons to lie")
WIN = "uncover who killed the clerk and name them"
PLAY_AS = "a tired harbor-precinct detective"

#: F follow-thread · K lived-knowledge · P push-edges (stress coherence) · C resolve.
SCHEDULE = ["F", "K", "F", "P", "F", "F", "K", "F", "P", "F", "F", "C"]
EP2_SCHEDULE = ["F", "K", "F"]

_STANCE = {
    "F": ("FOLLOW THE THREAD — pursue what seems interesting or off. You do NOT know the "
          "answer; you are discovering it. Investigate, examine, read records, question "
          "people, form your OWN hunches from what you've seen — and follow them."),
    "P": ("PUSH THE EDGES — deliberately go OFF the expected path. Try something the story "
          "did not set up, ask for things that may not exist, change the subject. You are "
          "stress-testing the world's improvisation, NOT serving the plot this turn."),
    "K": ("DRAW ON YOUR LIVED KNOWLEDGE — you have LIVED this life; you plausibly know "
          "things the story hasn't spelled out. Ask about/act on local geography, the "
          "people and your history with them, routines, how the trade really works."),
    "C": ("RESOLVE — commit to your CONCLUSION based ONLY on what you've actually learned "
          "(you may be wrong — fine). State who you believe is behind it and act on it "
          "(accuse, confront, decide). Do not hedge; make the call."),
}
_SCHEMA = {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]}

prov = CodexProvider()


def player_move(story_tail: str, stance: str) -> str:
    prompt = (
        "You are the PLAYER of a text interactive fiction — you control the protagonist "
        "('you'). You are COLD to the PLOT (discover the solution like a first-time player) "
        "but your CHARACTER has LIVED this life (you may draw on that lived knowledge).\n"
        f"STORY SO FAR (most recent — ALL you know):\n{story_tail}\n\n"
        f"YOUR STANCE THIS TURN: {_STANCE[stance]}\n\n"
        "Write ONLY the player's input — one natural action/line/question, first person or "
        "imperative, 1-2 sentences. No meta, no quotes.")
    return asyncio.run(prov.complete(prompt, _SCHEMA, tier="cheap"))["input"].strip()


def _play(s, w, schedule, story: str, label: str) -> str:
    for i, stance in enumerate(schedule, 1):
        try:
            inp = player_move(story[-4500:], stance)
        except Exception as exc:  # noqa: BLE001
            inp = "I take stock and consider my next move."
            w(f"\n*(player-agent fell back: {exc})*")
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            tr = r.trace
            w(f"\n## {label} turn {i} [{stance}] ({wall:.0f}s)\n")
            w(f"> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            if tr is not None:
                concl = getattr(tr, "conclusion_shape", "")
                w(f"*trace: act={tr.act} pacing={getattr(tr,'pacing','')} "
                  f"learned={getattr(tr,'learned_clues',[]) or '-'} "
                  f"beats={getattr(tr,'beats_achieved',[]) or '-'} "
                  f"terminal={getattr(tr,'terminal',None)} "
                  f"{('conclusion='+concl+' ('+getattr(tr,'conclusion_basis','')+')') if concl else ''} "
                  f"time={getattr(tr,'time_now','')!r} moved={getattr(tr,'movement_status','') or '-'}*\n")
            story += f"\n\n> You: {inp}\n\n{r.prose}"
            if getattr(r, "ended", False):
                w(f"\n*(— {label} reached a terminal conclusion at turn {i} —)*\n")
                break
        except Exception as exc:  # noqa: BLE001
            w(f"\n## {label} turn {i} [{stance}] — ENGINE ERROR: {exc}\n")
    return story


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/final-exhaustive-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    w(f"# FINAL EXHAUSTIVE — real build + play + continue — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")

    # clean any prior run
    try:
        _unpublish_scenario(NAME)
        if slot_path(NAME, PLAYER).exists():
            slot_path(NAME, PLAYER).unlink()
    except Exception:
        pass

    # 1. BUILD (real pipeline)
    w("## BUILD (real generate-then-ingest)\n")
    t0 = time.perf_counter()
    try:
        create_scenario_from_generated(
            NAME, prov, seed=SEED, endless=False, win_direction=WIN, play_as=PLAY_AS,
            on_stage=lambda m: w(f"  · {_humanize_stage(m) or m}"))
        w(f"\n*(build completed in {time.perf_counter()-t0:.0f}s)*\n")
    except Exception as exc:  # noqa: BLE001
        w(f"\n### BUILD FAILED: {exc}\n")
        print("LOG:", log, flush=True)
        return

    # 2. PLAY at length
    s = Session.open(NAME, player_id=PLAYER, fresh=True, provider=prov, mode_override="win_loss")
    opening = s.opening()
    w("## OPENING\n\n" + (opening or "(empty)") + "\n")
    story = _play(s, w, SCHEDULE, opening or "", "EP1")
    s.close()

    # 3. CONCLUDE → CONTINUE to episode 2
    w("\n## CONTINUATION (conclude → next chapter)\n")
    try:
        cont = continue_episode(NAME, prov, player_id=PLAYER, on_stage=lambda m: w(f"  · {m}"))
        s2 = Session.open(NAME, player_id=PLAYER, fresh=False, provider=prov)
        if cont.get("continuation_intro"):
            s2._meta["continuation_intro"] = cont["continuation_intro"]
        opening2 = s2.opening()
        w(f"\n### EPISODE 2 — main_arc={cont.get('main_arc','?')}\n\n" + (opening2 or "(empty)") + "\n")
        _play(s2, w, EP2_SCHEDULE, opening2 or "", "EP2")
        s2.close()
    except Exception as exc:  # noqa: BLE001
        w(f"\n### CONTINUATION ERROR: {exc}\n")

    # cleanup the throwaway scenario
    try:
        _unpublish_scenario(NAME)
        if slot_path(NAME, PLAYER).exists():
            slot_path(NAME, PLAYER).unlink()
    except Exception:
        pass
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
