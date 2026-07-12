"""Re-run ONLY the chapter-2 transition leg against the milestone campaign's
run-1 world (bodycase, player 'critic') — its chapter concluded properly but
the ch2 build died on a Codex transport error, leaving the seam untested.

Reuses the critic harness's own leg machinery (player_move with the CH2
addendum, file_feedback into logs/critic/) so the judgment standard is
identical to a full campaign run.

Usage:  .venv/bin/python scripts/ch2_leg_rerun.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

# import the harness AS RUN for bodycase/standard (its module globals drive
# player_move + file_feedback); argv untouched → SCENARIO=bodycase, MODE=standard
import scripts.critic_harness as ch

from construct.provider import CodexProvider
from construct.session import Session

TS = int(time.time())
LOG = Path(f"logs/critic-ch2rerun-bodycase-{TS}.md")
_parts: list[str] = []


def w(text: str) -> None:
    print(text, flush=True)
    _parts.append(text)
    LOG.write_text("\n".join(_parts) + "\n")


def main() -> None:
    prov = CodexProvider()
    pid = "critic"

    # verify the chapter really concluded (the leg's own gate)
    s = Session.open("bodycase", player_id=pid, provider=prov)
    from construct.adapter import PorcelainWorldReads
    from construct.arc.executor import arc_concluded
    from construct.turnloop import terminal_outcome
    reads = PorcelainWorldReads(s._world)
    ended = terminal_outcome(reads) is not None or arc_concluded(reads, s._arc)
    # chapter-1 tail for the player-agent's memory of what actually happened
    try:
        import json
        raw = reads.state("session:transcript", "recent", frame="session:main")
        entries = json.loads(raw) if raw else []
        story = "\n\n".join(f"> You: {e.get('player','')}\n\n{e.get('prose','')}"
                            for e in entries[-4:])
    except Exception:  # noqa: BLE001
        story = "(chapter one concluded: the Bluegate Yard case was pursued to its end)"
    s.close()
    if not ended:
        w("chapter 1 did NOT conclude in this world — aborting (wrong fixture)")
        sys.exit(2)

    w(f"# CH2 TRANSITION LEG (re-run) — bodycase/{pid} — {TS}\n")
    filed = 0
    from construct.game import continue_episode
    meta2 = continue_episode("bodycase", prov, player_id=pid,
                             on_stage=lambda m: w(f"*build: {m}*"))
    s2 = Session.open("bodycase", player_id=pid, provider=prov)
    if meta2.get("continuation_intro"):
        s2._meta["continuation_intro"] = meta2["continuation_intro"]
    ch2_open = s2.opening()
    w("## CH2 OPENING\n\n" + ch2_open + "\n")
    story2 = story[-2500:] + "\n\n===== CHAPTER 2 BEGINS =====\n\n" + ch2_open
    for j, st in enumerate(["F", "K", "F", "P", "F", "K"], 1):
        try:
            mv = ch.player_move(story2[-5000:], st, ch2=True)
            inp = (mv.get("input") or "").strip() or "I look around."
            note = (mv.get("feedback") or "").strip()
        except Exception as exc:  # noqa: BLE001
            inp, note = "I look around.", ""
            w(f"\n*(player-agent fell back: {exc})*")
        if note:
            fb = ch.file_feedback(f"(ch2 transition) {note}", story2,
                                  "ch2rerun-bodycase", 100 + j)
            filed += 1
            w(f"\n> 🧪 **CRITIC FEEDBACK (ch2 t{j}):** {note}\n> _(filed: {fb})_\n")
        try:
            r2 = s2.turn(inp)
            s2.flush_settle()
            w(f"\n## CH2 Turn {j} [{st}]\n\n> **Player:** {inp}\n")
            w((r2.prose or "(empty)") + "\n")
            story2 += f"\n\n> You: {inp}\n\n{r2.prose}"
        except Exception as exc:  # noqa: BLE001
            w(f"\n## CH2 Turn {j} — ENGINE ERROR: {exc}\n")
    s2.close()
    w(f"\n**CH2 leg complete — {filed} feedback note(s) filed.**\nLOG: {LOG}")


if __name__ == "__main__":
    main()
