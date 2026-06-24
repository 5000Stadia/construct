"""LIVE-PLAY demo for Living-World Generator P2a (logged for the founder).

A FANTASY world (deliberately NOT a detective story — the goal-shape differs from
Sherlock: here it is "lift the blight from the vale," not "name a culprit"). A
main arc + a side arc (the miller's missing son). Mid-session the blight reaches
the grove, foreclosing the son's trail: the side arc goes incompletable, emits
fallout — and the OPPORTUNISTIC DM GENERATOR mints a fresh, genre-appropriate side
thread LIVE from that fallout, surfaced to the player as a diegetic hook.

Demonstrates: (1) genre-agnostic arc/goal shaping, (2) P2a regeneration with the
six guards, (3) the generated arc grounded in the world's own entities/voice.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.arc import io as arc_io
from construct.arc.conditions import InFrame, StateIs, TurnsQuiet
from construct.arc.executor import PLOT, turn_time
from construct.arc.grammar import (
    Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight,
)
from construct.semantics import attribute_default

WARDEN = "person:eldra"          # the player — a hedge-warden of the vale
WF = f"knows:{WARDEN}"
MILLER = "person:miller"
REEVE = "person:reeve"
SON = "person:son"
BLIGHT = "fact:blight"
RELIC = "obj:relic"

STYLE = ("High-fantasy folktale, plain and earthy. Old words, green silences, the "
         "weight of weather and root. Wonder under dread; never modern, never wry.")
INTRO = ("The blight came to the vale with the first cold rain — leaves gone black, "
         "wells turned bitter, the old grove muttering in its sleep. They sent for "
         "the warden. Lift the blight, or the vale dies with the year.")


def author_world(path: Path) -> None:
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    # Author with the SAME attribute-semantics rule production uses (game._world):
    # this declares the structural arc enums (delta_type/rung/…) at session zero so
    # they persist, and the P2 generator can mint a new arc mid-play on reopen
    # without re-declaring semantics over folded data.
    w = World(path, world_id="w:vale", model=StubModel(fallback=fallback),
              stance="fiction", title="The Blight on the Vale",
              attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:vale", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:vale", "attribute": "description",
         "value": "A narrow green valley under a low grey sky, the hedges going "
                  "black at their roots.", "timeless": True},
        {"entity": "place:grove", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": WARDEN, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": WARDEN, "attribute": "in", "value": "place:vale"},
        {"entity": WARDEN, "attribute": "role", "value": "hedge-warden", "timeless": True},
        {"entity": MILLER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": MILLER, "attribute": "in", "value": "place:vale"},
        {"entity": MILLER, "attribute": "role", "value": "the vale's miller", "timeless": True},
        {"entity": MILLER, "attribute": "drive", "value": "drive:protect_kin"},
        {"entity": MILLER, "attribute": "fear", "value": "fear:losing_the_boy"},
        {"entity": REEVE, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": REEVE, "attribute": "in", "value": "place:vale"},
        {"entity": REEVE, "attribute": "role", "value": "the vale reeve", "timeless": True},
        {"entity": REEVE, "attribute": "drive", "value": "drive:keep_order"},
        {"entity": SON, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": SON, "attribute": "status", "value": "lost_in_the_grove"},
        {"entity": BLIGHT, "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": BLIGHT, "attribute": "cure", "value": "moonwater"},
        {"entity": RELIC, "attribute": "kind", "value": "object", "timeless": True},
        {"entity": RELIC, "attribute": "note", "value": "a cracked warding-stone"},
    ])

    # MAIN arc: lift the blight (a FANTASY goal — the warden learns the cure).
    main_beat = Beat("beat:learn_the_cure", Phase.CLIMAX, Weight.REQUIRED,
                     achievable_via=InFrame(WF, BLIGHT, "cure", "moonwater"))
    main_refusal = Clock("clock:refusal", TurnsQuiet(15),
                         effects=({"entity": "event:world_concludes", "attribute": "kind",
                                   "value": "refusal_conclusion"},),
                         bound_to="arc:main", rung=Rung.REFUSAL)
    main_shape = ConclusionShape(
        "shape:main", "desire_renounced", (WARDEN, "drive:mercy", "drive:fear"),
        world_condition=InFrame(WF, BLIGHT, "cure", "moonwater"),
        premise=InFrame("canon", BLIGHT, "cure", "moonwater"),
        refusal_variant_id="shape:refused")
    main = Arc("arc:main", WARDEN, main_shape, (main_beat,), (), main_refusal, 1,
               ("beat:learn_the_cure",),
               {Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3, Phase.CLIMAX: 2,
                Phase.FALLING: 2})

    # SIDE arc: the miller's lost son. If the blight reaches the grove first, the
    # trail is lost — the case becomes INCOMPLETABLE. Per-arc refusal id; short fuse.
    side_beat = Beat("beat:find_the_boy_side", Phase.CLIMAX, Weight.REQUIRED,
                     achievable_via=StateIs(SON, "status", "found"),
                     unreachable_if=StateIs(BLIGHT, "reached_grove", "yes"))
    side_refusal = Clock("clock:refusal_side", TurnsQuiet(3),
                         effects=({"entity": "event:world_concludes_side",
                                   "attribute": "kind", "value": "refusal_conclusion"},),
                         bound_to="arc:side", rung=Rung.REFUSAL)
    side_shape = ConclusionShape(
        "shape:side", "desire_at_cost", (MILLER, "drive:protect_kin", "fear:losing_the_boy"),
        world_condition=StateIs(SON, "status", "found"),
        premise=StateIs(MILLER, "kind", "person"),
        refusal_variant_id="shape:refused")
    side = Arc("arc:side", MILLER, side_shape, (side_beat,), (), side_refusal, 1,
               ("beat:find_the_boy_side",),
               {Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3, Phase.CLIMAX: 2,
                Phase.FALLING: 2})

    items = []
    for a in (main, side):
        items += arc_io.arc_to_items(a) + arc_io.index_items(a)
    items += arc_io.portfolio_items(["arc:main", "arc:side"], main_arc_id="arc:main")
    w.porcelain.ingest_structured(items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame="session:main")
    w.close()

    import json
    path.with_suffix(".meta.json").write_text(json.dumps({
        "title": "The Blight on the Vale", "protagonist": WARDEN, "stance": "fiction",
        "mode": "pure", "scenario_mode": "win_loss", "style": STYLE, "intro": INTRO,
        "goal_statement": "lift the blight before the vale dies with the year",
        "arc_scope": [WARDEN, MILLER, REEVE, SON, BLIGHT, RELIC, "place:vale", "place:grove"],
        "main_arc": "arc:main", "arc_ids": ["arc:main", "arc:side"],
    }, indent=2))


def blight_reaches_grove(world) -> None:
    """A world development between turns: the blight reaches the grove. This
    forecloses the miller's missing-son thread and registers its refusal backstop
    as spent — so the side arc reads INCOMPLETABLE next tick, which fuels the DM
    generator. Stands in for a clock/NPC move; deterministic so the demo lands."""
    p = world.porcelain
    p.ingest_structured([{"entity": BLIGHT, "attribute": "reached_grove", "value": "yes",
                          "valid_from": turn_time(1)}])
    fid = "event:refusal_side_fired_1"
    p.ingest_structured([
        {"entity": fid, "attribute": "kind", "value": "clock_fired",
         "valid_from": turn_time(1)},
        {"entity": fid, "attribute": "agent", "value": "clock:refusal_side",
         "value_type": "entity", "valid_from": turn_time(1)},
    ], frame=PLOT)


def main() -> None:
    from construct import Session
    from construct.adapter import PorcelainWorldReads
    from construct.provider import CodexProvider

    worlds = Path("worlds"); worlds.mkdir(exist_ok=True)
    logs = Path("logs"); logs.mkdir(exist_ok=True)
    ts = os.environ.get("LIVEPLAY_TS", "manual")
    log = logs / f"liveplay-p2-{ts}.md"
    spath = worlds / "vale.world"
    if spath.exists():
        spath.unlink()
    spath.with_suffix(".meta.json").unlink(missing_ok=True)
    for slot in worlds.glob("vale.play*.world"):
        slot.unlink()
    author_world(spath)

    out = log.open("w")

    def w(line=""):
        out.write(line + "\n"); out.flush()

    w("# Live-play — Living-World Generator P2a (a FANTASY world)")
    w()
    w("A high-fantasy world (goal: *lift the blight* — a different shape than a "
      "detective's *name the culprit*). A main arc + a side arc (the miller's lost "
      "son). Mid-session the blight reaches the grove, the son's trail goes cold "
      "(**incompletable**), and the **opportunistic DM generator** mints a fresh, "
      "in-genre side thread LIVE from that fallout — surfaced as a diegetic hook.")
    w()

    provider = CodexProvider()
    s = Session.open("vale", player_id="founder", fresh=True, provider=provider)
    w("## Opening")
    w("```")
    w(s.opening())
    w("```")
    w()

    def play(n, text, note=None):
        if note:
            w(f"> _{note}_")
            w()
        w(f"### Turn {n}")
        w(f"**You:** {text}")
        w()
        reply = s.turn(text)
        w(f"**Narrator:** {reply.prose}")
        w()
        t = reply.trace
        if t:
            w(f"`lifecycle={t.lifecycle}` · `arc_fallout={t.arc_fallout}` · "
              f"`generated={t.generated}` · `beats_closed={t.beats_closed}` · "
              f"`ended={reply.ended}`")
        else:
            w(f"(turn did not complete: ok={reply.ok})")
        w()
        return reply

    try:
        play(1, "I walk the blackened hedgerow and read the sickness in the leaves.")
        blight_reaches_grove(s._world)
        play(2, "I find the miller and ask after his boy.",
             note="Overnight the blight reaches the grove — the miller's son is "
                  "lost to it (side arc → incompletable). Watch for BOTH the "
                  "fallout acknowledgment AND a NEW thread the world throws up.")
        play(3, "I take the miller's grief in, then turn back to the blight itself.",
             note="The world keeps moving — any new thread is live now, not a game-over.")
        play(4, "I kneel by the bitter well and search my craft for what would cleanse it.")
    finally:
        w("## State at close")
        w("```")
        reads = PorcelainWorldReads(s._world)
        p = s._world.porcelain
        ids = arc_io.arc_ids_from_frame(reads)
        w(f"portfolio arc ids: {ids}")
        gen_ids = [a for a in ids if a.startswith("arc:gen_")]
        for gid in gen_ids:
            prov = p.state(gid, "generated_from", frame=PLOT)
            depth = p.state(gid, "gen_depth", frame=PLOT)
            w(f"  generated {gid}: from={prov.get('fact', {}).get('value')} "
              f"depth={depth.get('fact', {}).get('value')}")
        attempts = [e.event_id for e in reads.events(kind="generation_attempt", frame="session:main")]
        declines = [(e.event_id) for e in reads.events(kind="generation_declined", frame="session:main")]
        w(f"generation attempts: {attempts}")
        w(f"generation declines: {declines}")
        side_life = p.state("arc:side", "lifecycle", frame=PLOT)
        w(f"arc:side lifecycle: {side_life.get('fact', {}).get('value')}")
        # Membrane: generated bookkeeping is NOT canon.
        for gid in gen_ids:
            cst = p.state(gid, "generated")  # canon read
            w(f"MEMBRANE — {gid}.generated in canon: {cst.get('status')} (expect not 'known')")
        w("```")
        s.close()
    out.close()
    print(str(log))


if __name__ == "__main__":
    main()
