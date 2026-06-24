"""Live play harness — an LLM player-agent works through the fiction AT LENGTH,
alternating *follow-the-thread* and *push-the-edges*, logging the full transcript +
per-turn traces so the writing/engagement can be assessed (founder ask, 2026-06-22).

The player-agent is deliberately mixed: it pursues the apparent plot on F turns and
deliberately wanders / stress-tests world coherence on P turns, then attempts to
resolve on the final C turn — exercising both "serve the plot" and "improvise away
from it". Runs against the live CodexProvider; logs progressively to logs/.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

# Surface engine tracebacks (Session.turn logs via logger.exception on a degraded turn) so
# the run log captures the REAL error, not just the harness's downstream symptom.
logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

#: The scenario to play — argv[1] overrides (so the harness can drive a freshly-built world).
SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "anchor"
#: F = follow the plot thread; P = push the edges (off-plot, stress coherence);
#: K = draw on the character's lived knowledge (tests the engine's "approximate what
#: this character would know" improv); C = move to resolve/conclude. ~18 = "at length".
SCHEDULE = ["F", "K", "F", "P", "F", "K", "P", "F", "F", "K",
            "F", "P", "F", "K", "F", "P", "F", "C"]

_STANCE = {
    "F": ("FOLLOW THE THREAD — pursue what seems interesting or off. You do NOT know "
          "the answer; you are discovering it. Investigate, examine things, read "
          "records, question the people, form your OWN hunches from what you've "
          "actually seen — and follow them, even if they might be wrong."),
    "P": ("PUSH THE EDGES — deliberately go OFF the expected path. Wander somewhere "
          "tangential, try something the story did not set up, test whether the world "
          "stays coherent (ask for things that may not exist, attempt the unusual, "
          "change the subject, leave). You are stress-testing the world's improvisation, "
          "NOT serving the plot this turn."),
    "K": ("DRAW ON YOUR LIVED KNOWLEDGE — you have LIVED this life; you plausibly know "
          "things the story hasn't spelled out. Ask about or act on such knowledge: "
          "local geography ('where's the nearest place to eat / drink / sleep?'), the "
          "people and your standing or history with them, daily routines, who owes whom, "
          "how the trade really works, your own past here. You are testing whether the "
          "world fills in what your character would obviously know, plausibly and in-"
          "world — NOT uncovering the plot."),
    "C": ("RESOLVE — commit to your CONCLUSION based ONLY on what you have actually "
          "learned in play (you may well be wrong — that's fine). State who/what you "
          "believe is behind it and act on it (accuse, confront, decide). Do not "
          "hedge; make the call."),
}

_SCHEMA = {"type": "object", "properties": {"input": {"type": "string"}},
           "required": ["input"]}

prov = CodexProvider()


def player_move(story_tail: str, stance: str) -> str:
    prompt = (
        "You are the PLAYER of a text interactive fiction — you control the protagonist "
        "('you'). Two things shape what you know:\n"
        "  • You are COLD to the PLOT — you do NOT know the solution, who is behind "
        "anything, or what you are 'supposed' to do. Discover that like a real "
        "first-time player, from what the story actually shows you.\n"
        "  • But your CHARACTER has LIVED this life — so you plausibly know your own "
        "world: your background, the local geography, the people and your history with "
        "them, the routines, how things work. You may draw on and ask about that lived "
        "knowledge (the world should fill it in), WITHOUT knowing the hidden plot.\n"
        "Read the story so far, then decide your protagonist's NEXT move.\n\n"
        f"STORY SO FAR (most recent — this is ALL you know):\n{story_tail}\n\n"
        f"YOUR STANCE THIS TURN: {_STANCE[stance]}\n\n"
        "Write ONLY the player's input — one natural action, line of dialogue, or "
        "question, as a person would type it (first person or imperative, 1-2 sentences). "
        "No meta, no quotes, just the input.")
    return asyncio.run(prov.complete(prompt, _SCHEMA, tier="cheap"))["input"].strip()


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/harness-{ts}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    s = Session.open(SCENARIO, player_id="harness", fresh=True, provider=prov)
    w(f"# Play harness — {SCENARIO} — {len(SCHEDULE)} turns\n")
    opening = s.opening()
    w("## OPENING\n\n" + opening + "\n")
    story = opening

    for i, stance in enumerate(SCHEDULE, 1):
        try:
            inp = player_move(story[-4500:], stance)
        except Exception as exc:  # noqa: BLE001
            inp = "I take stock of the room and consider my next move."
            w(f"\n*(player-agent fell back: {exc})*")
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            tr = r.trace
            if tr is None:  # the session degraded this turn — r.prose carries the real error
                w(f"\n## Turn {i} [{stance}] ({wall:.0f}s) — SESSION DEGRADED\n")
                w(f"> **Player:** {inp}\n")
                w((r.prose or "(no prose)") + "\n")
                story += f"\n\n> You: {inp}\n\n{r.prose}"
                continue
            npcs = [c for c in tr.cohort_calls if c.startswith("npc")]
            w(f"\n## Turn {i} [{stance}] ({wall:.0f}s)\n")
            w(f"> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            learned = getattr(tr, "learned_clues", [])
            concl = getattr(tr, "conclusion_shape", "")
            weave = getattr(tr, "weave_decision", "")
            w(f"*trace: act={tr.act} pacing={tr.pacing} adj={tr.adjudication} "
              f"audit={tr.concealment_audit} npcs={npcs or '-'} "
              f"weave={weave or '-'}{('/' + tr.weave_card) if getattr(tr, 'weave_card', '') else ''} "
              f"learned_clues={learned or '-'} "
              f"{('conclusion=' + concl + ' (' + getattr(tr, 'conclusion_basis', '') + ')') if concl else ''} "
              f"time={tr.time_now!r} moved={tr.movement_status or '-'} "
              f"reveals={tr.reveals or '-'} dropped={tr.dropped_cohorts or '-'}*\n")
            story += f"\n\n> You: {inp}\n\n{r.prose}"
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} [{stance}] — ENGINE ERROR: {exc}\n")
    s.close()
    w("\n--- END ---")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
