"""DRIFT D2 live acceptance — absence-consequence, real CodexProvider.

The spec's own D2 close-out (DRIFT-HANDLING.md §7): skip the meeting with a
deadline clock; find the window closed without you. The appointment clock
fires after three quiet turns and CLOSES the required delivery beat
(clock-caused, witnessed); the firing turn is suppressed; the NEXT quiet turn
classifies D-MISSED and commits the moment event + the host-built lapse
predicate (+ the authored on_expiry outcome, verbatim) + the durable pending
callback. The player then walks to the mill — the touch — and the callback
surfaces into the narration, once.

Usage:  .venv/bin/python scripts/probe_d2_absence.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("probe_d2")

TS = int(time.time())
LOG_PATH = Path(f"logs/probe_d2-{TS}.md")
LOG_PATH.parent.mkdir(exist_ok=True)
_lines: list[str] = []

NAME = "probe_d2_absence"


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
    from construct.arc.conditions import ClockFired, InFrame, Occurred, TurnsQuiet
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
        unreachable_if=ClockFired("clock:appointment"),
    )
    appointment = Clock(
        "clock:appointment", TurnsQuiet(3),
        effects=({"entity": "event:appointment_passed", "attribute": "kind",
                  "value": "appointment_passed"},),
        bound_to="beat:discover", rung=Rung.SURFACE)
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
        beats=(discover,), clocks=(appointment,), refusal_clock=refusal,
        climax_ready_k=1, climax_ready_beats=("beat:discover",),
        phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                      Phase.CLIMAX: 2, Phase.FALLING: 2},
    )
    from construct.arc.drift import on_expiry_items
    items = arc_io.arc_to_items(arc) + arc_io.index_items(arc)
    items += arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main")
    w.porcelain.ingest_structured(items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame=SESSION)
    # the occurrence license lives in the PLOT frame (clock:<id>/on_expiry) —
    # the first run authored it into canon by mistake and the license never read
    w.porcelain.ingest_structured(on_expiry_items(
        "clock:appointment",
        "the mill accounts were sealed for the magistrate, unread"),
        frame="plot:main")
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
    _log("PROBE D2 — DRIFT absence-consequence live acceptance (spec §7 D2)")
    _log("=" * 70)
    _author()

    from construct.session import Session
    from construct.provider import CodexProvider

    s = Session.open(NAME, provider=CodexProvider(), player_id="probe_d2", fresh=True)
    p = s._world.porcelain  # probe-only reach

    def _where(pid: str) -> str:
        try:
            return (p.locate(pid) or ["?"])[0]
        except Exception as exc:  # noqa: BLE001
            return f"locate-failed: {exc}"

    _log(f"\n  CANON BEFORE: miller@{_where('person:miller')}")

    turns = [
        ("I nurse my ale and let the first hour slide by.", "T1: quiet"),
        ("I watch the rain and keep my seat.", "T2: quiet"),
        ("I let another stretch of the morning pass.",
         "T3: quiet (the appointment clock fires; suppressed)"),
        ("I stir myself and think about the day.",
         "T4: quiet (classify D-MISSED; commit)"),
        ("I ask Sef what he makes of the weather.",
         "T5: unrelated engagement (no touch — silent)"),
        ("I finally walk down to the wet mill.", "T6: the walk"),
        ("I look about the mill for the miller.",
         "T7: post-touch (no re-fire; the callback surfaced on the walk turn)"),
    ]
    surfaced_turn = None
    committed_turn = None
    for i, (move, label) in enumerate(turns, start=1):
        r = _turn(s, move, label)
        t = r.trace
        _log(f"    absence={getattr(t, 'absence_consequences', None)} "
             f"callbacks={getattr(t, 'callbacks', None)} "
             f"closed={getattr(t, 'beats_closed', None)}")
        if getattr(t, "absence_consequences", None) and committed_turn is None:
            committed_turn = i
            _log(f"\n  ABSENCE COMMITTED at T{i}: {t.absence_consequences}")
        if getattr(t, "callbacks", None) and surfaced_turn is None:
            surfaced_turn = i
            _log(f"\n  CALLBACK SURFACED at T{i}: {t.callbacks}")
    outcome = p.state("place:mill", "missed_moment_outcome")
    noted = p.state("person:miller", "noted_absence")
    s.close()

    _log("\n  VERDICT:")
    _log(f"  committed_turn={committed_turn} surfaced_turn={surfaced_turn}")
    _log(f"  miller.noted_absence: {noted.get('status')} = "
         f"{(noted.get('fact') or {}).get('value')!r}")
    _log(f"  mill.missed_moment_outcome: {outcome.get('status')} = "
         f"{(outcome.get('fact') or {}).get('value')!r}")
    if committed_turn and noted.get("status") == "known":
        _log("  D2 LIVE — the window closed without the player: the lapse is canon "
             "(host predicate); the authored outcome is "
             + ("recorded VERBATIM; " if outcome.get("status") == "known"
                else "MISSING (inspect the license read); ")
             + ("the callback SURFACED on touch." if surfaced_turn else
                "the callback is pending (touch not yet made)."))
    else:
        _log("  NOT OBSERVED — inspect the traces above (suppression turn, "
             "classification gates, cohort declines).")
    _flush()
    print(f"\nlog: {LOG_PATH}")


if __name__ == "__main__":
    main()
