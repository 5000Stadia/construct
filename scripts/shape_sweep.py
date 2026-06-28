"""#33 per-genre richness sweep — the 7 shapes not yet live-exercised. For each, build a
representative world (fast interview/brief path, forced game_type) and play a few genre-neutral
turns, logging opening + prose + a per-turn diagnostic so the SHAPE's experience can be graded
(does it stage right, is the cast/situation present, does the genre-faithful texture show).
"""
from __future__ import annotations
import logging, time, traceback
from pathlib import Path
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.game import create_scenario_from_interview, scenario_path, slot_path
from construct.provider import CodexProvider
from construct.session import Session

# (name, game_type → shape, one-line brief)
SHAPES = [
    ("sw_bond", "romance", "A slow-burn romance between two people thrown together by a long winter in a remote lighthouse station."),
    ("sw_contest", "duel_standoff", "A lone fighter arrives in a frontier town for a reckoning — a duel at dusk that the whole town is bracing for."),
    ("sw_gambit", "heist", "A small crew has one night to lift a guarded relic from a glittering, well-watched vault."),
    ("sw_discovery", "exploration_discovery", "An expedition descends into an uncharted ruin where every chamber hides a secret and a hazard."),
    ("sw_mastery", "stewardship_management", "A new steward must bring a failing estate back to life across one hard, decisive season."),
    ("sw_farce", "mistaken_identity", "A nobody is mistaken for a visiting dignitary and must keep up the act through a chaotic state banquet."),
    ("sw_transformation", "redemption_quest", "A disgraced figure, once feared, sets out to make amends and become someone the world can forgive."),
]
MOVES = [
    "I take in where I am — the place, the hour, who is here with me — and get my bearings.",
    "I turn to the nearest person and engage them about what's happening and what they want of me.",
    "I take a concrete first step on the most pressing thread in front of me.",
]
prov = CodexProvider()

for name, gt, brief in SHAPES:
    OUT = Path("logs") / f"shapesweep-{name}.md"
    buf: list[str] = []
    def w(s, _b=buf, _o=OUT):
        _b.append(s); _o.write_text("\n".join(_b)); print(s, flush=True)
    # fresh
    for suf in (".world", ".meta.json", ".images.json"):
        scenario_path(name).with_suffix(suf).unlink(missing_ok=True)
    w(f"# SHAPE SWEEP — {name} (game_type={gt})\n\n_brief: {brief}_\n")
    t0 = time.time()
    try:
        meta = create_scenario_from_interview(name, brief, prov, game_types=[gt])
        w(f"*(built in {time.time()-t0:.0f}s)*  title={meta.get('title')!r} "
          f"game_type={meta.get('game_type')!r} protagonist={meta.get('protagonist')!r}\n")
    except Exception as exc:
        w(f"*** BUILD FAILED: {exc} ***\n" + traceback.format_exc()[:1500])
        continue
    try:
        s = Session.open(name, player_id="sweep", fresh=True, provider=prov)
        w("## OPENING\n" + s.opening() + "\n")
        for i, mv in enumerate(MOVES, 1):
            r = s.turn(mv)
            t = r.trace
            loc = s._display_name(s.location()) if s.location() else "(nowhere)"
            present = s._present_people(s._establishing_anchors()[1])[0]
            w(f"\n## turn {i}\n> **Player:** {mv}\n")
            w(f"_loc: {loc} · present: {present or '—'} · pacing: {getattr(t,'pacing',None)}_\n")
            w((r.prose or "(empty)") + "\n")
        s.close()
    except Exception as exc:
        w(f"*** PLAY FAILED: {exc} ***\n" + traceback.format_exc()[:1500])
    w("\n--- END ---")
    print(f"  -> {OUT}")
print("\nSWEEP COMPLETE")
