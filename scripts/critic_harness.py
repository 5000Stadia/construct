"""CRITIC HARNESS (founder 2026-07-02): an LLM player-agent primed to PLAY WELL and
CRITIQUE like the founder does — watching for narrative-immersion detractors and
accuracy breakers, and filing its own /feedback when one genuinely lands.

Differences from play_harness.py:
- The move call returns {input, feedback}: `feedback` is EMPTY unless the agent was
  genuinely pulled out of the story; a non-empty note is written to logs/critic/ in the
  SAME format the live /feedback command produces (note + last few turns), tagged
  `critic`, so the operator triages them through the one pipeline.
- The primer teaches critique CALIBRATION: breakage vs taste, and citing the exact
  contradicting lines.

Operator discipline (the founder's instruction): every filed feedback is INDEPENDENTLY
VERIFIED against engine truth (slot reads, traces) before anything is 'fixed'.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)s %(name)s: %(message)s")

from construct.provider import CodexProvider
from construct.session import Session

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "bodycase"
MODE = (sys.argv[2] if len(sys.argv) > 2 else "standard").lower()  # standard | offpath
SCHEDULE = ["F", "K", "F", "P", "F", "K", "P", "F", "F", "K",
            "F", "P", "F", "K", "F", "P", "F", "C"]
#: OFF-THE-BEATEN-PATH (founder): learn the world briefly, then COMMIT to a tangent of
#: the player's own devising and live it; take a plainly unwise turn or two; conclude on
#: the tangent's own terms. The milestone under test: the world stays cohesive and
#: ENGAGING whatever path the player chooses.
OFFPATH_SCHEDULE = ["F", "K", "T", "T", "B", "T", "K", "T", "T", "B",
                    "T", "P", "T", "T", "T", "T", "T", "C"]
#: GENRE-SHIFT (founder): COMPLETE the presented story while persistently CURVING it
#: toward an alternative story type, so chapter 2 should reshape/blend to that type.
#: Interleaves genuine plot pursuit (F/K) with the curve (R); concludes the story (C).
GENRESHIFT_SCHEDULE = ["F", "R", "K", "R", "F", "R", "F", "R", "K", "R",
                       "F", "R", "K", "R", "F", "R", "F", "C"]

_STANCE = {
    "F": ("FOLLOW THE THREAD — pursue what seems interesting or off. You do NOT know "
          "the answer; discover it like a first-time player and follow your own hunches."),
    "P": ("PUSH THE EDGES — go OFF the expected path this turn. Try something the story "
          "did not set up; test whether the world stays coherent."),
    "K": ("DRAW ON YOUR LIVED KNOWLEDGE — ask about or act on things your character "
          "would plausibly know (geography, people, routines, your own past here)."),
    "C": ("RESOLVE — bring YOUR story to a head on its own terms, based only on what "
          "actually happened in play. If you followed the presented plot, conclude it; "
          "if you lived your own tangent, commit to where IT has led. Don't hedge."),
    "T": ("LIVE YOUR TANGENT — this is YOUR story now, not the one presented. Pursue "
          "the personal thread you chose (see YOUR CHOSEN PATH) with full commitment: "
          "court them, build it, chase it. The presented plot may knock; answer only "
          "if it genuinely tempts your character."),
    "B": ("TAKE THE BAD PATH — do the obviously unwise thing that appeals to your "
          "character right now (provoke the wrong person, spend what you can't spare, "
          "trust the untrustworthy, go where you were warned not to). Not suicidal — "
          "unwise. You are testing whether consequences land honestly and the story "
          "stays engaging."),
    "R": ("CURVE IT — make THIS turn's move in a way that pulls the story's TONE and "
          "TYPE toward YOUR CHOSEN ALTERNATIVE shape (flirt and let feeling steer you; "
          "bring levity or mischief; crave the road and risk) while STILL addressing the "
          "plot at hand. Both at once — serve the presented story AND bend it your way."),
}

GENRESHIFT_PRIMER = """
YOUR DUAL AIM (genre-shift mode): you ARE here to genuinely play and COMPLETE the
presented story — pursue its plot, engage its people, bring it to a real resolution.
AND, threaded through everything you do, you are CURVING the whole story toward a
DIFFERENT story type than the one presented. In your first two turns choose ONE
alternative shape true to your character — a ROMANCE (court someone present; let feeling
steer you), a COMEDY (levity, mischief, slapstick), or an ADVENTURE (crave travel, risk,
the open road) — name it to yourself and thread it through EVERY turn after: not INSTEAD
of the plot, but woven INTO how you pursue it. Address the story at hand while
persistently, unmistakably leaning it your way, so that by the end an onlooker would say
"this is still the presented story — but it has clearly become [presented] + [your
alternative]." Do NOT abandon the plot (that is a different mode); the test is whether a
story you genuinely completed, but visibly colored, is NOTICED at the chapter seam.
Your critic hat watches that seam most of all: when chapter 2 opens, did the world notice
where you took the whole story — is chapter 2 reshaped or BLENDED toward your alternative
type (a mystery gone lighter; an investigation now also a romance), or did it snap back
to the original genre as if your steering never happened? A chapter 2 that ignores the
direction you clearly pulled the entire first chapter is THE finding to file.
"""

OFFPATH_PRIMER = """
YOUR CHOSEN PATH (off-the-beaten-path mode): you are NOT here to serve the presented
plot. Within your first three turns, CHOOSE a personal tangent the story did not offer —
a romance with someone present, a rivalry, a business venture, a pilgrimage, an
expedition of your own devising — something true to your character but OUTSIDE the
story's primary focus. Name it to yourself and COMMIT: pursue it wholeheartedly for the
rest of the run. Let the presented plot pull at you without letting it own you.
Your critique hat watches for exactly this mode's failures: the world stonewalling your
path, serving it with empty filler instead of real texture (people without lives, doors
without rooms), railroading you back to the plot, or letting your bad-path choices float
free of honest consequence. A world that makes YOUR chosen story rich — that is the win;
file when it refuses or hollows out.
"""

CH2_CRITIC_ADDENDUM = """
THE CHAPTER TRANSITION (you just crossed from one story into the next — judge the seam):
- Did chapter 1 get an OUTRO and chapter 2 a fresh HOOK, or did you just get dropped in?
- Does the new chapter's history match what ACTUALLY happened in chapter 1 — or does it
  claim outcomes, reputations, or closures you never earned ("the case came good")?
- Time and place: did the world move honestly (a new hour, back at your base), and do
  you carry ONLY what you actually had? Anything minted into your pockets is a breaker.
- Are the people the opening stages REAL — can you speak to them next turn?
- RICHNESS: is this second story as authored and specific as the first — its own case
  with its own texture — or thinner, derivative, a re-tread wearing new names? A second
  chapter that only manages continuity bookkeeping without fresh invention is a finding
  worth filing (say so plainly: "coherent but thin," with what's missing).
"""

CRITIC_PRIMER = """
YOU ARE ALSO A DISCERNING CRITIC (a second hat, worn silently while you play).
You know good interactive fiction from the inside, and you notice when the dream breaks.
Watch for these ACCURACY BREAKERS and IMMERSION DETRACTORS as you read each reply:

CONTINUITY & WORLD TRUTH
- A person, object, or place contradicting what the story already established (someone
  reintroduced with a different role/rank/job; an object teleporting or duplicating;
  a place changing its geography).
- Characters present who shouldn't be (departed people lingering, strangers speaking
  uninvited) or absent who should be (someone you brought along vanishing; someone the
  scene introduced evaporating a turn later).
- Time and weather doing impossible things (night to noon in a step; a deadline that
  stops mattering).
- WHERE ARE YOU? Track your location like a stage manager: if the narration has you
  inspecting or conversing somewhere you never traveled to, snaps you back to an earlier
  room without a journey, or a character is suddenly "still by the desk" in a scene they
  never entered — that is a break, file it.
- Knowledge from nowhere: a character knowing something they could not have witnessed
  or been told — including YOUR character 'remembering' things never established.
- Identity drift: a character's gender, pronouns, name, rank, or age shifting between
  turns ("her stool" in one scene, "his ear" in the next) — file it with both lines.

CONVERSATION & CRAFT
- Someone re-recognizing a name or fact already established — especially one they
  raised themselves ("X? I know that name!" from the person who introduced X).
- Facts or dialogue repeating as if new; your question answered with a recital of
  what was already said; the same phrase recited verbatim across turns.
- The narrator re-describing an unchanged scene, re-preaching stakes, offering menus
  of suggested actions, or reciting the theme as a moral.
- Your action narrated as done when it plainly didn't happen, or refused without any
  in-world reason.

CALIBRATION — this is the part that makes you useful:
- File feedback ONLY when you are genuinely pulled out of the story. A matter of taste
  (you'd have phrased it differently) is NOT feedback. A one-off stylistic tic is NOT
  feedback. A real contradiction, a vanished companion, a re-recognized name — those are.
- When you do file, CITE THE EVIDENCE: quote the earlier line and the contradicting
  line, in a sentence or two, the way a sharp playtester writes a bug note.
- Filing nothing for many turns straight is a perfectly good result.
- NEVER let the critic hat leak into your PLAYER input — your move stays fully
  in-character; the feedback note is a separate out-of-band channel.
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "input": {"type": "string",
                  "description": "the player's next move, fully in-character"},
        "feedback": {"type": "string",
                     "description": "EMPTY almost always. Non-empty ONLY for a genuine "
                                    "immersion detractor or accuracy breaker, written as "
                                    "a sharp playtester's bug note citing the exact "
                                    "contradicting lines."},
    },
    "required": ["input", "feedback"],
}

prov = CodexProvider()
# logs/critic/, NOT dev_inbox/ — the legacy channel is RETIRED (AgentPost
# migration directive); critic feedback is an operator-triage artifact and
# lives with the run logs.
FB_DIR = Path("logs/critic")


def player_move(story_tail: str, stance: str, ch2: bool = False) -> dict:
    prompt = (
        "You are the PLAYER of a text interactive fiction — you control the protagonist "
        "('you'). You are COLD to the plot (discover it like a first-time player) but "
        "your CHARACTER has lived this life (draw on their plausible knowledge).\n"
        + CRITIC_PRIMER
        + (OFFPATH_PRIMER if MODE == "offpath"
           else GENRESHIFT_PRIMER if MODE == "genreshift" else "")
        + (CH2_CRITIC_ADDENDUM if ch2 else "") +
        f"\nSTORY SO FAR (most recent — this is ALL you know):\n{story_tail}\n\n"
        f"YOUR STANCE THIS TURN: {_STANCE[stance]}\n\n"
        "Return your next player input (one natural action, line of dialogue, or "
        "question, 1-2 sentences, no meta) and — separately — your critic's feedback "
        "note (empty unless something genuinely broke).")
    return asyncio.run(prov.complete(prompt, _SCHEMA, tier="cheap"))


def file_feedback(note: str, story_tail: str, scenario: str, turn: int) -> str:
    """Write the note in the live /feedback pipeline's format, tagged critic."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = FB_DIR / f"feedback-{ts}-critic-{scenario}-t{turn}.md"
    path.write_text(
        f"# Live feedback — critic:{scenario}\n\n**When:** {ts} (turn {turn})\n\n"
        f"## Note\n\n{note}\n\n## Last few turns\n\n{story_tail[-3500:]}\n")
    return str(path)


_PID = "critic" if MODE == "standard" else f"critic_{MODE}"
_SCHED = (OFFPATH_SCHEDULE if MODE == "offpath"
          else GENRESHIFT_SCHEDULE if MODE == "genreshift" else SCHEDULE)


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/critic-{MODE}-{SCENARIO}-{ts}.md")
    log.parent.mkdir(exist_ok=True)
    FB_DIR.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    s = Session.open(SCENARIO, player_id=_PID, fresh=True, provider=prov)
    w(f"# Critic harness — {SCENARIO} — mode={MODE} — {len(_SCHED)} turns\n")
    opening = s.opening()
    w("## OPENING\n\n" + opening + "\n")
    story = opening
    filed = 0

    for i, stance in enumerate(_SCHED, 1):
        try:
            mv = player_move(story[-5000:], stance)
            inp = (mv.get("input") or "").strip() or "I take stock and consider my next move."
            note = (mv.get("feedback") or "").strip()
        except Exception as exc:  # noqa: BLE001
            inp, note = "I take stock and consider my next move.", ""
            w(f"\n*(player-agent fell back: {exc})*")
        if note:
            fb = file_feedback(note, story, f"{MODE}-{SCENARIO}", i)
            filed += 1
            w(f"\n> 🧪 **CRITIC FEEDBACK (turn {i}):** {note}\n> _(filed: {fb})_\n")
        try:
            t0 = time.perf_counter()
            r = s.turn(inp)
            wall = time.perf_counter() - t0
            w(f"\n## Turn {i} [{stance}] ({wall:.0f}s)\n\n> **Player:** {inp}\n")
            w((r.prose or "(empty)") + "\n")
            story += f"\n\n> You: {inp}\n\n{r.prose}"
            if r.ended:
                w("\n**— chapter ended —**\n")
                break
        except Exception as exc:  # noqa: BLE001
            w(f"\n## Turn {i} [{stance}] — ENGINE ERROR: {exc}\n")
    # one final critique pass over the whole tail (the ending is where it counts)
    try:
        mv = player_move(story[-6000:], "F")
        note = (mv.get("feedback") or "").strip()
        if note:
            fb = file_feedback("(post-run review) " + note, story, f"{MODE}-{SCENARIO}", 99)
            filed += 1
            w(f"\n> 🧪 **CRITIC FEEDBACK (post-run):** {note}\n> _(filed: {fb})_\n")
    except Exception:  # noqa: BLE001
        pass
    # ---- CHAPTER-2 LEG (founder: judge the transition — does richness degrade under
    # coherence maintenance?): if the story LANDED, roll into the next episode the way
    # the transport would, and play several turns with the ch2 critique addendum on.
    _ended = False
    try:
        from construct.adapter import PorcelainWorldReads
        from construct.arc.executor import arc_concluded
        from construct.turnloop import terminal_outcome
        _reads = PorcelainWorldReads(s._world)
        _ended = terminal_outcome(_reads) is not None or arc_concluded(_reads, s._arc)
    except Exception as exc:  # noqa: BLE001
        w(f"\n*(continuation check failed: {exc})*")
    s.close()
    if _ended:
        w("\n\n# ===== CHAPTER 2 (critic transition leg) =====\n")
        try:
            from construct.game import continue_episode
            meta2 = continue_episode(SCENARIO, prov, player_id=_PID,
                                     on_stage=lambda m: w(f"*build: {m}*"))
            s2 = Session.open(SCENARIO, player_id=_PID, provider=prov)
            if meta2.get("continuation_intro"):
                s2._meta["continuation_intro"] = meta2["continuation_intro"]
            ch2_open = s2.opening()
            w("## CH2 OPENING\n\n" + ch2_open + "\n")
            story2 = story[-2500:] + "\n\n===== CHAPTER 2 BEGINS =====\n\n" + ch2_open
            # genre-shift mode keeps CURVING in ch2 so the seam is judged for reshape/blend
            _ch2_sched = (["R", "F", "R", "K", "R", "F"] if MODE == "genreshift"
                          else ["F", "K", "F", "P", "F", "K"])
            for j, st in enumerate(_ch2_sched, 1):
                try:
                    mv = player_move(story2[-5000:], st, ch2=True)
                    inp = (mv.get("input") or "").strip() or "I look around."
                    note = (mv.get("feedback") or "").strip()
                except Exception as exc:  # noqa: BLE001
                    inp, note = "I look around.", ""
                    w(f"\n*(player-agent fell back: {exc})*")
                if note:
                    fb = file_feedback(f"(ch2 transition) {note}", story2, f"{MODE}-{SCENARIO}",
                                       100 + j)
                    filed += 1
                    w(f"\n> 🧪 **CRITIC FEEDBACK (ch2 t{j}):** {note}\n> _(filed: {fb})_\n")
                try:
                    r2 = s2.turn(inp)
                    w(f"\n## CH2 Turn {j} [{st}]\n\n> **Player:** {inp}\n")
                    w((r2.prose or "(empty)") + "\n")
                    story2 += f"\n\n> You: {inp}\n\n{r2.prose}"
                except Exception as exc:  # noqa: BLE001
                    w(f"\n## CH2 Turn {j} — ENGINE ERROR: {exc}\n")
            s2.close()
        except Exception as exc:  # noqa: BLE001
            w(f"\n*(ch2 leg failed: {exc})*")
    else:
        w("\n*(chapter did not land a conclusion — no ch2 leg this run)*")
    w(f"\n**Run complete — {filed} feedback note(s) filed.**\nLOG: {log}")


if __name__ == "__main__":
    main()
