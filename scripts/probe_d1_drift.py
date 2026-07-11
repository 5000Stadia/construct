"""DRIFT D1 live acceptance — relocate-the-beat, real CodexProvider.

The spec's own D1 close-out (DRIFT-HANDLING.md §7): dodge a staged clue-holder,
wander, watch the mechanic arrive. Staging: the ledger clue lives with the
miller at the mill; the player never goes — they settle into the taproom and
let the afternoon drain away. Once the rung ladder reaches CONFRONT (9
sustained-quiet turns) AND the world has been development-quiet 240+ diegetic
minutes, R2 should relocate the beat: the miller travels INTO the taproom in
canon (commit-before-directive), and the narration stages the arrival.

Usage:  .venv/bin/python scripts/probe_d1_drift.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("probe_d1")

TS = int(time.time())
LOG_PATH = Path(f"logs/probe_d1-{TS}.md")
LOG_PATH.parent.mkdir(exist_ok=True)
_lines: list[str] = []

NAME = "probe_d1_drift"


def _log(*parts) -> None:
    msg = " ".join(str(p) for p in parts)
    print(msg, flush=True)
    _lines.append(msg)


def _flush() -> None:
    LOG_PATH.write_text("\n".join(_lines) + "\n")


def _wipe() -> None:
    for p in Path("worlds").glob(f"{NAME}*"):
        p.unlink(missing_ok=True)


def _author() -> None:
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from construct.semantics import attribute_default
    from construct.arc import io as arc_io
    from construct.arc.conditions import InFrame, Occurred
    from construct.arc.executor import SESSION, turn_time
    from construct.arc.grammar import (Arc, Beat, Clock, ConclusionShape, Phase,
                                       Rung, Weight)

    _wipe()
    path = Path(f"worlds/{NAME}.world")
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id=f"w:{NAME}", model=StubModel(fallback=fallback),
              stance="fiction", title="The Wet Mill", attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:village", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:village", "attribute": "name", "value": "Bracken village", "timeless": True},
        {"entity": "place:taproom", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:taproom", "attribute": "name", "value": "the taproom", "timeless": True},
        {"entity": "place:taproom", "attribute": "in", "value": "place:village", "timeless": True},
        {"entity": "place:taproom", "attribute": "description",
         "value": "The inn's low taproom: settle fire, rain on the panes, a few corner tables.",
         "timeless": True},
        {"entity": "place:mill", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:mill", "attribute": "name", "value": "the wet mill", "timeless": True},
        {"entity": "place:mill", "attribute": "in", "value": "place:village", "timeless": True},
        # the player
        {"entity": "person:vale", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:vale", "attribute": "name", "value": "Vale", "timeless": True},
        {"entity": "person:vale", "attribute": "in", "value": "place:taproom"},
        {"entity": "person:vale", "attribute": "role",
         "value": "an assessor sent to settle the mill accounts", "timeless": True},
        # the clue-holder, staged AWAY at the mill
        {"entity": "person:miller", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:miller", "attribute": "name", "value": "Aldous the miller", "timeless": True},
        {"entity": "person:miller", "attribute": "in", "value": "place:mill"},
        {"entity": "person:miller", "attribute": "role", "value": "the miller", "timeless": True},
        {"entity": "person:miller", "attribute": "drive",
         "value": "to be seen honest before the assessor's report is written", "timeless": True},
        {"entity": "person:miller", "attribute": "fear",
         "value": "the shortfall being pinned on him alone", "timeless": True},
        # a present non-cast anchor with a spine
        {"entity": "person:keeper", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:keeper", "attribute": "name", "value": "Sef the innkeeper", "timeless": True},
        {"entity": "person:keeper", "attribute": "in", "value": "place:taproom"},
        {"entity": "person:keeper", "attribute": "role", "value": "the innkeeper", "timeless": True},
        {"entity": "person:keeper", "attribute": "drive",
         "value": "to keep the inn out of the mill quarrel", "timeless": True},
        # the hidden premise fact (the beat's mechanic; the player must LEARN it)
        {"entity": "fact:shortfall", "attribute": "culprit", "value": "person:factor",
         "timeless": True},
        {"entity": "person:factor", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:factor", "attribute": "name", "value": "the grain factor", "timeless": True},
        {"entity": "person:factor", "attribute": "in", "value": "place:village"},
    ])

    discover = Beat(
        "beat:discover", Phase.CLIMAX, Weight.REQUIRED,
        achievable_via=InFrame("knows:person:vale", "fact:shortfall", "culprit",
                               "person:factor"),
    )
    refusal = Clock("clock:refusal", Occurred("event:abandoned"),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape(
        "shape:main", "desire_at_cost",
        ("person:vale", "drive:the_truth_of_the_books", "fear:a_false_report"),
        world_condition=InFrame("knows:person:vale", "fact:shortfall", "culprit",
                                "person:factor"),
        premise=InFrame("canon", "fact:shortfall", "culprit", "person:factor"),
        refusal_variant_id="shape:refused",
    )
    arc = Arc(
        arc_id="arc:main", protagonist="person:vale", shape=shape,
        beats=(discover,), clocks=(), refusal_clock=refusal,
        climax_ready_k=1, climax_ready_beats=("beat:discover",),
        phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                      Phase.CLIMAX: 2, Phase.FALLING: 2},
    )
    items = arc_io.arc_to_items(arc) + arc_io.index_items(arc)
    items += arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main")
    w.porcelain.ingest_structured(items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame=SESSION)
    w.close()

    path.with_suffix(".meta.json").write_text(json.dumps({
        "title": "The Wet Mill", "protagonist": "person:vale",
        "stance": "fiction", "mode": "pure", "scenario_mode": "endless",
        "style": ("Rain-country procedural, plain prose. The village keeps its own "
                  "hours; people cross the green on their errands."),
        "intro": ("You are Vale, an assessor sent to settle the wet mill's accounts — "
                  "a shortfall someone will answer for. Aldous the miller waits at the "
                  "mill with the ledgers. You, however, have taken a corner table in "
                  "the taproom, where Sef the innkeeper minds the fire."),
        "goal_statement": "learn who is behind the mill shortfall",
        "arc_scope": ["person:vale", "person:miller", "person:keeper", "person:factor",
                      "place:taproom", "place:mill", "place:village", "fact:shortfall"],
        "main_arc": "arc:main", "arc_ids": ["arc:main"],
        "cast": {
            "pillars": [{"id": "pillar:books", "label": "the mill books",
                         "required": True}],
            "cast": [{
                "id": "person:miller",
                "location": "place:mill",
                "surface_role": "the miller with the ledgers",
                "clues": [{
                    "clue_id": "clue:ledger", "pillar_id": "pillar:books",
                    "fact": {"entity": "fact:shortfall", "attribute": "culprit",
                             "value": "person:factor"},
                }],
            }],
        },
    }, indent=2))
    _log(f"  [author] world written to {path}")


def _turn(s, move: str, label: str):
    _log(f"\n  > {label}")
    _log(f"    PLAYER: {move!r}")
    r = s.turn(move)
    s.flush_settle()
    t = r.trace
    _log(f"    PROSE (first 300): {(r.prose or '')[:300]!r}")
    _log(f"    drift={getattr(t, 'drift', None)} relocations={getattr(t, 'relocations', None)}")
    if getattr(t, "relocate_directive", ""):
        _log(f"    DIRECTIVE: {t.relocate_directive!r}")
    _log(f"    time_advanced={getattr(t, 'time_advanced', 0)} "
         f"nudge={getattr(t, 'nudge', '')!r}")
    _flush()
    return r


def main() -> None:
    _log("=" * 70)
    _log("PROBE D1 — DRIFT relocate-the-beat live acceptance (spec §7 D1)")
    _log("=" * 70)
    _author()

    from construct.session import Session
    from construct.provider import CodexProvider

    s = Session.open(NAME, provider=CodexProvider(), player_id="probe_d1", fresh=True)
    p = s._world.porcelain  # probe-only reach

    def _where(pid: str) -> str:
        try:
            return (p.locate(pid) or ["?"])[0]
        except Exception as exc:  # noqa: BLE001
            return f"locate-failed: {exc}"

    _log(f"\n  CANON BEFORE: miller@{_where('person:miller')}")

    # The dodge: the player settles in and lets hours pass; ~10 quiet turns so
    # the rung ladder reaches CONFRONT (9 sustained-quiet turns) while the
    # diegetic wait opens the 240-minute quiet gate.
    moves = [
        ("I settle into the corner table and let the afternoon drain away over "
         "a slow ale — hours of it.", "T1: the long wait (diegetic hours)"),
        ("I watch the rain runnel down the panes.", "T2: quiet"),
        ("I listen to the fire settle.", "T3: quiet"),
        ("I turn my empty cup slowly on the table.", "T4: quiet"),
        ("I doze a little in the warmth.", "T5: quiet"),
        ("I wait out the grey evening as it comes on — a couple more hours.",
         "T6: second wait"),
        ("I study the grain of the tabletop.", "T7: quiet"),
        ("I stretch my legs by the fire.", "T8: quiet"),
        ("I sit back down and watch the door.", "T9: quiet"),
        ("I let the evening carry on around me.", "T10: quiet"),
        ("I stay where I am a while longer.", "T11: quiet"),
        ("I glance about the taproom.", "T12: quiet (the arrival window)"),
    ]
    relocated_turn = None
    for i, (move, label) in enumerate(moves, start=1):
        r = _turn(s, move, label)
        if getattr(r.trace, "relocations", None):
            relocated_turn = i
            _log(f"\n  RELOCATION FIRED at T{i}: {r.trace.relocations}")
            _log(f"  miller now @ {_where('person:miller')}")
            # one more turn: the arrival should be STAGED in prose and presence
            r2 = _turn(s, "I look up at who has come in.", f"T{i+1}: the arrival beat")
            break
    miller_final = _where("person:miller")
    s.close()

    _log("\n  VERDICT:")
    _log(f"  relocated_turn={relocated_turn} miller_final={miller_final}")
    if relocated_turn and miller_final == "place:taproom":
        _log("  D1 LIVE — the dodged mechanic ARRIVED: the miller relocated into the "
             "taproom in canon (commit-before-directive), the directive staged it.")
    elif relocated_turn:
        _log("  PARTIAL — a relocation committed but the carrier's final canon "
             "location is unexpected; inspect above.")
    else:
        _log("  NOT OBSERVED — no relocation fired; inspect drift/rung/quiet traces "
             "above (gates may not have opened: check time_advanced sums vs 240 and "
             "the quiet-turn count vs 9).")
    _flush()
    print(f"\nlog: {LOG_PATH}")


if __name__ == "__main__":
    main()
