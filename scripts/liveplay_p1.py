"""LIVE-PLAY demo for Living-World Generator P1 (logged for the founder).

Hand-authors a compact noir fiction world with TWO arcs — a MAIN arc (name who
falsified the harbor manifest) and a SIDE arc (the clerk's missing-dockworker
case) — then plays it LIVE through the real narrator (CodexProvider). Mid-session
the ledger scandal breaks, which forecloses the clerk's side case: it goes
`incompletable`, emits FALLOUT (a standing canon consequence), and the world
acknowledges it diegetically WITHOUT dead-ending. Play continues on the main arc.

Everything is appended to a timestamped transcript under logs/.
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

DET = "person:detective"
DET_FRAME = f"knows:{DET}"
CLERK = "person:clerk"
HARBORMASTER = "person:harbormaster"
DOCKWORKER = "person:dockworker"
LEDGER = "fact:ledger"

STYLE = ("Rain-soaked harbor noir. Short, weather-bitten sentences; salt and "
         "diesel and wet newsprint. Wry, tired, exact. Let silences carry weight.")
INTRO = ("The harbor precinct keeps the rain out and little else. A manifest was "
         "falsified the night the Mary Rel went down, and someone signed it. "
         "Find the hand that held the pen.")


def author_world(path: Path) -> None:
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id="w:harbor", model=StubModel(fallback=fallback),
              stance="fiction", title="The Mary Rel Manifest")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:precinct", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:precinct", "attribute": "description",
         "value": "A harbor police office. Rain on the glass, a tin ashtray, "
                  "the smell of wet rope.", "timeless": True},
        {"entity": DET, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": DET, "attribute": "in", "value": "place:precinct"},
        {"entity": CLERK, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": CLERK, "attribute": "in", "value": "place:precinct"},
        {"entity": CLERK, "attribute": "role", "value": "records clerk", "timeless": True},
        {"entity": HARBORMASTER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": DOCKWORKER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": DOCKWORKER, "attribute": "status", "value": "missing"},
        {"entity": LEDGER, "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": LEDGER, "attribute": "falsified_by", "value": HARBORMASTER},
    ])

    # MAIN arc: the detective (player) learns who falsified the manifest.
    main_beat = Beat("beat:name_the_hand", Phase.CLIMAX, Weight.REQUIRED,
                     achievable_via=InFrame(DET_FRAME, LEDGER, "falsified_by", HARBORMASTER))
    main_refusal = Clock("clock:refusal", TurnsQuiet(15),
                         effects=({"entity": "event:world_concludes", "attribute": "kind",
                                   "value": "refusal_conclusion"},),
                         bound_to="arc:main", rung=Rung.REFUSAL)
    main_shape = ConclusionShape(
        "shape:main", "desire_at_cost", (DET, "drive:truth", "drive:peace"),
        world_condition=InFrame(DET_FRAME, LEDGER, "falsified_by", HARBORMASTER),
        premise=InFrame("canon", LEDGER, "falsified_by", HARBORMASTER),
        refusal_variant_id="shape:refused")
    main = Arc(arc_id="arc:main", protagonist=DET, shape=main_shape, beats=(main_beat,),
               clocks=(), refusal_clock=main_refusal, climax_ready_k=1,
               climax_ready_beats=("beat:name_the_hand",),
               phase_budget={Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3,
                             Phase.CLIMAX: 2, Phase.FALLING: 2})

    # SIDE arc: the clerk's missing-dockworker case. If the manifest scandal
    # breaks first, the harbormaster bolts and the trail goes cold — the case
    # becomes INCOMPLETABLE. Per-arc refusal id (the collision fix). Short fuse
    # so the backstop expires within the live session.
    side_beat = Beat("beat:find_dockworker_side", Phase.CLIMAX, Weight.REQUIRED,
                     achievable_via=StateIs(DOCKWORKER, "status", "found"),
                     unreachable_if=StateIs(LEDGER, "exposed", "yes"))
    # Fuse of 3 quiet turns: long enough that the side arc does NOT time out on
    # its own during the early turns — its death is DRIVEN by the scandal
    # (the foreclosed required beat + the backstop registered as fired in
    # break_the_scandal), so it lands as `incompletable`, not a quiet `lost`.
    side_refusal = Clock("clock:refusal_side", TurnsQuiet(3),
                         effects=({"entity": "event:world_concludes_side",
                                   "attribute": "kind", "value": "refusal_conclusion"},),
                         bound_to="arc:side", rung=Rung.REFUSAL)
    side_shape = ConclusionShape(
        "shape:side", "desire_at_cost", (CLERK, "drive:duty", "drive:fear"),
        world_condition=StateIs(DOCKWORKER, "status", "found"),
        premise=StateIs(CLERK, "kind", "person"),
        refusal_variant_id="shape:refused")
    side = Arc(arc_id="arc:side", protagonist=CLERK, shape=side_shape, beats=(side_beat,),
               clocks=(), refusal_clock=side_refusal, climax_ready_k=1,
               climax_ready_beats=("beat:find_dockworker_side",),
               phase_budget={Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3,
                             Phase.CLIMAX: 2, Phase.FALLING: 2})

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
        "title": "The Mary Rel Manifest", "protagonist": DET, "stance": "fiction",
        "mode": "pure", "scenario_mode": "win_loss", "style": STYLE, "intro": INTRO,
        "goal_statement": "name the hand that falsified the manifest",
        "arc_scope": [DET, CLERK, HARBORMASTER, DOCKWORKER, LEDGER, "place:precinct"],
        "main_arc": "arc:main", "arc_ids": ["arc:main", "arc:side"],
    }, indent=2))


def break_the_scandal(world) -> None:
    """A world development between turns: the ledger scandal breaks. This
    forecloses the clerk's side case (unreachable_if) and the per-arc refusal
    backstop is registered as fired — so the side arc reads INCOMPLETABLE next
    tick. Stands in for a clock/NPC move; deterministic so the demo lands."""
    p = world.porcelain
    p.ingest_structured([{"entity": LEDGER, "attribute": "exposed", "value": "yes",
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
    from construct.provider import CodexProvider

    worlds = Path("worlds"); worlds.mkdir(exist_ok=True)
    logs = Path("logs"); logs.mkdir(exist_ok=True)
    ts = os.environ.get("LIVEPLAY_TS", "manual")
    log = logs / f"liveplay-p1-{ts}.md"
    spath = worlds / "harbor.world"
    if spath.exists():
        spath.unlink()
    spath.with_suffix(".meta.json").unlink(missing_ok=True)
    for slot in worlds.glob("harbor.play*.world"):
        slot.unlink()
    author_world(spath)

    out = log.open("w")

    def w(line=""):
        out.write(line + "\n"); out.flush()

    w("# Live-play — Living-World Generator P1")
    w()
    w("A hand-authored noir world with a **main arc** (name who falsified the "
      "manifest) and a **side arc** (the clerk's missing-dockworker case), played "
      "LIVE through the real narrator. Mid-session the scandal breaks and the side "
      "case becomes **incompletable** — watch the world acknowledge it and keep "
      "going (no game-over).")
    w()

    provider = CodexProvider()
    s = Session.open("harbor", player_id="founder", fresh=True, provider=provider)
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
              f"`beats_closed={t.beats_closed}` · `clocks_fired={t.clocks_fired}` · "
              f"`outcome={t.outcome}` · `ended={reply.ended}`")
        else:
            w(f"(turn did not complete: ok={reply.ok})")
        w()
        return reply

    try:
        play(1, "I go to the clerk's desk and read over the manifest she left out.")
        # The world turns: the scandal breaks between turns.
        break_the_scandal(s._world)
        play(2, "I ask the clerk what she makes of the morning papers.",
             note="Overnight the manifest scandal hits the front page — the "
                  "harbormaster bolts, and the clerk's missing-dockworker case "
                  "goes cold (the side arc becomes incompletable).")
        play(3, "I let it sit, then keep working the manifest angle.",
             note="Play continues — the dead side thread is NOT a game-over.")
        play(4, "I pull the deep drawer and check the countersignature on the "
                "manifest against the harbormaster's logbook.",
             note="An investigative action on the main arc — the hunt goes on.")
    finally:
        w("## State at close")
        w("```")
        from construct.adapter import PorcelainWorldReads
        reads = PorcelainWorldReads(s._world)
        p = s._world.porcelain
        # The fallout canon consequence (a TRUE world-fact, caused_by the terminal).
        terms = [e.event_id for e in reads.events(kind="arc_terminal")]
        w(f"arc_terminal events (fallout anchors): {terms}")
        st = p.state(CLERK, "desire_unresolved")
        w(f"clerk.desire_unresolved (fallout consequence): {st.get('status')} "
          f"-> {st.get('fact', {}).get('value') if st.get('status')=='known' else None}")
        side_life = p.state("arc:side", "lifecycle", frame=PLOT)
        w(f"arc:side lifecycle (persisted): {side_life.get('fact', {}).get('value')}")
        # Membrane: the derived notions must NOT be canon rows.
        for forbidden in ("dramatic_tension", "known_by", "active_thread_count"):
            stf = p.state(CLERK, forbidden)
            w(f"MEMBRANE check — clerk.{forbidden} in canon: {stf.get('status')} "
              f"(expect not 'known')")
        w("```")
        s.close()
    out.close()
    print(str(log))


if __name__ == "__main__":
    main()
