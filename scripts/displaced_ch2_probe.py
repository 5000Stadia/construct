"""The DISPLACED-CONCLUSION continuation probe (founder, 2026-07-12).

The sharpest test of the conclude->continue engine yet: chapter 1 must END
notably far from its original location AND off its implied expected
conclusion; chapter 2 must then handle the notable transition — opening
where the player actually ended, with a PIVOTED goal series whose setting
and style feel SUPPORTED by the player's chapter-1 decisions.

The founder's archetype, run literally:
  CH1  a prison break — the expected shape is "get out"; the critic-player
       escapes and then keeps going: real distance, a new region, and a
       conclusion committed IN the new place on the player's own terms.
  CH2  the continuation should become hide-AND-integrate in that society —
       a completely different setting and goal series, earned not asserted.

Reuses the critic harness's player-agent + feedback machinery so judgments
land in the one triage pipeline (logs/critic/).

Usage:  .venv/bin/python scripts/displaced_ch2_probe.py [skip-build]
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

import scripts.critic_harness as ch
from construct.provider import CodexProvider
from construct.session import Session

NAME = "ironhold"
PID = "critic_displaced"
TS = int(time.time())
LOG = Path(f"logs/critic-displaced-{NAME}-{TS}.md")
_parts: list[str] = []

SEED = ("A grim river-fortress prison, Ironhold, on a cold northern frontier: "
        "the protagonist is a wrongly-condemned cartwright due to hang within "
        "days. Guards with routines, a laundry barge, a chaplain with doubts, "
        "one loyal friend inside. The story of getting OUT.")

#: CH1 stances: follow the escape, then DISPLACE — the founder's bar is that
#: the ending is committed far away, off the implied "you got out" beat.
CH1_SCHEDULE = [
    ("F", None), ("F", None), ("K", None), ("F", None), ("P", None),
    ("F", None), ("F", None),
    ("D", "PUT REAL DISTANCE BEHIND YOU — you are out (or nearly); do not "
          "linger at the prison or return home. Travel HARD toward somewhere "
          "genuinely new: downriver, over the border, a city where nobody "
          "knows your face. Commit to the journey as its own drama."),
    ("D", "KEEP GOING — arrive somewhere NOTABLY different from Ironhold: a "
          "different society, different work, different rules. Ground "
          "yourself in it: who is here, what do they need, what could a "
          "person like you become?"),
    ("D", "SETTLE INTO THE NEW PLACE — take an action that plants a root: "
          "lodging, work, a name you'll go by, a person you'll trust."),
    ("C", "RESOLVE — conclude YOUR story ON YOUR OWN TERMS, IN THIS NEW "
          "PLACE. Not the story the prison implied (cleared name, revenge, "
          "homecoming) — the story you actually lived: the one who got away "
          "and chose a new life. Commit to it plainly."),
]

#: CH2 addendum: the founder's three bars, judged on top of the standard seam.
DISPLACED_CH2_ADDENDUM = """
THE DISPLACED TRANSITION (this continuation followed a chapter that ENDED far
from where it began — judge these three bars hard, file if any fails):
- WHERE: does chapter 2 open where you actually ENDED — the new place — or
  did it teleport you back toward the original setting/home base? Any
  unexplained snap-back is a breaker; file it with the two locations.
- GOAL PIVOT: is the new chapter's goal series genuinely NEW and fitting the
  situation you created (hiding, integrating, building a life, the past
  reaching for you) — or does it re-run the old story's goals in new paint?
- SUPPORTED STYLE: does the new place's texture (society, work, faces,
  stakes) feel like it GREW from your decisions — the trade you took, the
  name you gave, the people you trusted — or is it generic scenery that
  ignores what you planted?
"""


def w(text: str) -> None:
    print(text, flush=True)
    _parts.append(text)
    LOG.write_text("\n".join(_parts) + "\n")


def _move(story_tail: str, stance_key: str, custom: str | None,
          ch2: bool = False) -> dict:
    """The harness's player_move, with our displacement stances injected."""
    if custom is not None:
        ch._STANCE["D"] = custom
        if stance_key == "C":
            ch._STANCE["C"] = custom
    if ch2:
        old = ch.CH2_CRITIC_ADDENDUM
        ch.CH2_CRITIC_ADDENDUM = old + DISPLACED_CH2_ADDENDUM
        try:
            return ch.player_move(story_tail, stance_key, ch2=True)
        finally:
            ch.CH2_CRITIC_ADDENDUM = old
    return ch.player_move(story_tail, stance_key)


def main() -> None:
    prov = CodexProvider()
    filed = 0

    if "skip-build" not in sys.argv:
        w(f"# DISPLACED-CONCLUSION PROBE — {NAME} — {TS}\n")
        w("## BUILD (prison-break world, win_loss: escape)\n")
        from construct.game import ViabilityError, create_scenario_from_generated
        try:
            create_scenario_from_generated(
                NAME, prov, seed=SEED, endless=False,
                win_direction="escape Ironhold before the hanging",
                on_stage=lambda m: w(f"*build: {m}*"))
        except ViabilityError as exc:
            w(f"BUILD NOT VIABLE: {'; '.join(exc.problems)}")
            sys.exit(2)

    s = Session.open(NAME, player_id=PID, provider=prov, fresh=True,
                     mode_override="win_loss")
    opening = s.opening()
    w("## CH1 OPENING\n\n" + opening + "\n")
    story = opening
    for i, (st, custom) in enumerate(CH1_SCHEDULE, 1):
        try:
            mv = _move(story[-5000:], st if custom is None else ("C" if st == "C" else "D"),
                       custom)
            inp = (mv.get("input") or "").strip() or "I keep moving."
            note = (mv.get("feedback") or "").strip()
        except Exception as exc:  # noqa: BLE001
            inp, note = "I keep moving.", ""
            w(f"\n*(player-agent fell back: {exc})*")
        if note:
            fb = ch.file_feedback(note, story, f"displaced-{NAME}", i)
            filed += 1
            w(f"\n> 🧪 **CRITIC FEEDBACK (t{i}):** {note}\n> _(filed: {fb})_\n")
        t0 = time.time()
        r = s.turn(inp)
        s.flush_settle()
        w(f"\n## Turn {i} [{st}] ({int(time.time() - t0)}s)\n\n> **Player:** {inp}\n")
        w((r.prose or "(empty)") + "\n")
        story += f"\n\n> You: {inp}\n\n{r.prose}"
        if getattr(r, "ended", False):
            w("\n*(story reached its terminal)*")
            break

    # where did chapter 1 actually END? (evidence for the WHERE bar)
    from construct.adapter import PorcelainWorldReads
    from construct.arc.executor import arc_concluded
    from construct.turnloop import terminal_outcome
    reads = PorcelainWorldReads(s._world)
    prot = s._arc.protagonist
    end_loc = (s._world.porcelain.locate(prot) or ["?"])[0]
    ended = terminal_outcome(reads) is not None or arc_concluded(reads, s._arc)
    w(f"\n**CH1 END STATE:** protagonist at `{end_loc}`; concluded={ended}")
    s.close()

    if not ended:
        w("\n*(chapter 1 did not land a conclusion — no ch2 leg; probe INCOMPLETE)*")
        w(f"\n**Probe halted — {filed} feedback note(s) filed.**\nLOG: {LOG}")
        sys.exit(1)

    w("\n\n# ===== CHAPTER 2 (the displaced transition) =====\n")
    from construct.game import continue_episode
    meta2 = continue_episode(NAME, prov, player_id=PID,
                             on_stage=lambda m: w(f"*build: {m}*"))
    s2 = Session.open(NAME, player_id=PID, provider=prov)
    if meta2.get("continuation_intro"):
        s2._meta["continuation_intro"] = meta2["continuation_intro"]
    ch2_open = s2.opening()
    w("## CH2 OPENING\n\n" + ch2_open + "\n")
    open_loc = (s2._world.porcelain.locate(s2._arc.protagonist) or ["?"])[0]
    w(f"**CH2 OPEN STATE:** protagonist at `{open_loc}` "
      f"(ch1 ended at `{end_loc}`)\n")
    story2 = story[-2500:] + "\n\n===== CHAPTER 2 BEGINS =====\n\n" + ch2_open
    for j, st in enumerate(["F", "K", "F", "P", "F", "K"], 1):
        try:
            mv = _move(story2[-5000:], st, None, ch2=True)
            inp = (mv.get("input") or "").strip() or "I look around."
            note = (mv.get("feedback") or "").strip()
        except Exception as exc:  # noqa: BLE001
            inp, note = "I look around.", ""
            w(f"\n*(player-agent fell back: {exc})*")
        if note:
            fb = ch.file_feedback(f"(displaced ch2) {note}", story2,
                                  f"displaced-{NAME}", 100 + j)
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
    w(f"\n**Probe complete — {filed} feedback note(s) filed.**\nLOG: {LOG}")


if __name__ == "__main__":
    main()
