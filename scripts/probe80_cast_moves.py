"""Task #80 live acceptance — the CAST-MOVES licensed movement lane, real CodexProvider.

Test bar 11 (docs/design/CAST-MOVES.md): a staged two-NPC scene where the prose moves
one out and one in across three turns, presence tracking both. The staging seeds the
fiction so movement is NATURAL (Edda about to leave for the well; Garrick due in from
the yard) — the player observes without engaging either NPC, so rule 5 licenses the
departures the narrator authors.

Usage:  .venv/bin/python scripts/probe80_cast_moves.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("probe80")

TS = int(time.time())
LOG_PATH = Path(f"logs/probe80-{TS}.md")
LOG_PATH.parent.mkdir(exist_ok=True)
_lines: list[str] = []

NAME = "probe80_castmoves"


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
    from construct.arc.conditions import StateIs, TurnsQuiet
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
              stance="fiction", title="Harrow Grange", attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:grange", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:grange", "attribute": "name", "value": "Harrow Grange", "timeless": True},
        {"entity": "place:kitchen", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:kitchen", "attribute": "name", "value": "the back kitchen", "timeless": True},
        {"entity": "place:kitchen", "attribute": "in", "value": "place:grange", "timeless": True},
        {"entity": "place:kitchen", "attribute": "description",
         "value": "A low back kitchen with a range fire, damp boots by the wall, one door to the yard.", "timeless": True},
        {"entity": "place:yard", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:yard", "attribute": "name", "value": "the yard", "timeless": True},
        {"entity": "place:yard", "attribute": "in", "value": "place:grange", "timeless": True},
        {"entity": "place:well_house", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:well_house", "attribute": "name", "value": "the well house", "timeless": True},
        {"entity": "place:well_house", "attribute": "in", "value": "place:grange", "timeless": True},
        # the player
        {"entity": "person:vale", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:vale", "attribute": "name", "value": "Vale", "timeless": True},
        {"entity": "person:vale", "attribute": "in", "value": "place:kitchen"},
        {"entity": "person:vale", "attribute": "role", "value": "a surveyor lodging the night", "timeless": True},
        # NPC 1 — present, ABOUT TO LEAVE (the out-mover)
        {"entity": "person:edda", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:edda", "attribute": "name", "value": "Edda", "timeless": True},
        {"entity": "person:edda", "attribute": "in", "value": "place:kitchen"},
        {"entity": "person:edda", "attribute": "role", "value": "the housemaid", "timeless": True},
        # NPC 2 — off-scene, DUE IN (the in-mover)
        {"entity": "person:garrick", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:garrick", "attribute": "name", "value": "Garrick", "timeless": True},
        {"entity": "person:garrick", "attribute": "in", "value": "place:yard"},
        {"entity": "person:garrick", "attribute": "role", "value": "the groundskeeper", "timeless": True},
        # NPC 3 — present ANCHOR (keeps only_one False so Edda can be unengaged)
        {"entity": "person:nan", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:nan", "attribute": "name", "value": "Nan", "timeless": True},
        {"entity": "person:nan", "attribute": "in", "value": "place:kitchen"},
        {"entity": "person:nan", "attribute": "role", "value": "the cook, mending by the lamp", "timeless": True},
    ])

    refusal_clock = Clock(
        "clock:refusal_main", TurnsQuiet(30),
        effects=({"entity": "event:night_ends", "attribute": "kind",
                  "value": "refusal_conclusion", "caused_by": "arc:main"},),
        bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape(
        "shape:main", "vigil",
        ("person:vale", "drive:see_the_night_out", "fear:the_grange_unquiet"),
        world_condition=StateIs("person:vale", "role", "settled"),
        premise=StateIs("person:vale", "kind", "person"),
        refusal_variant_id="shape:refused_main")
    beat = Beat("beat:settle_in", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=StateIs("person:vale", "role", "settled"))
    arc = Arc("arc:main", "person:vale", shape, (beat,), (), refusal_clock,
              1, ("beat:settle_in",),
              {Phase.SETUP: 3, Phase.RISING: 4, Phase.CRISIS: 2,
               Phase.CLIMAX: 2, Phase.FALLING: 1})
    items = arc_io.arc_to_items(arc) + arc_io.index_items(arc)
    items += arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main")
    w.porcelain.ingest_structured(items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame=SESSION)
    w.close()

    path.with_suffix(".meta.json").write_text(json.dumps({
        "title": "Harrow Grange", "protagonist": "person:vale",
        "stance": "fiction", "mode": "pure", "scenario_mode": "endless",
        "style": ("Rural nocturne, plain prose. The household MOVES: Edda the housemaid "
                  "is just gathering her shawl to go out to the well house; Garrick the "
                  "groundskeeper is due in from the yard any moment, stamping the cold off. "
                  "Let comings and goings happen naturally in the narration — and when a "
                  "task calls someone away, they GO, decisively, the narration naming "
                  "where (the well house, the yard), never lingering at thresholds."),
        "intro": ("You are Vale, a surveyor lodging the night at Harrow Grange. You sit "
                  "by the range fire in the back kitchen with Nan the cook, who is mending "
                  "by the lamp. Edda the housemaid is gathering her shawl to fetch water "
                  "from the well house; through the window you can see Garrick the "
                  "groundskeeper crossing the yard toward the door."),
        "goal_statement": "",
        "arc_scope": ["person:vale", "person:edda", "person:garrick", "person:nan",
                      "place:kitchen", "place:yard", "place:well_house", "place:grange"],
        "main_arc": "arc:main", "arc_ids": ["arc:main"],
    }, indent=2))
    _log(f"  [author] world written to {path}")


def _turn(s, move: str, label: str):
    _log(f"\n  > {label}")
    _log(f"    PLAYER: {move!r}")
    r = s.turn(move)
    s.flush_settle()  # the lane runs in the DEFERRED settle — join it before reading
    t = r.trace
    _log(f"    PROSE (first 400): {(r.prose or '')[:400]!r}")
    _log(f"    trace.cast_moves      = {getattr(t, 'cast_moves', None)}")
    _log(f"    trace.cast_move_drops = {getattr(t, 'cast_move_drops', None)}")
    _log(f"    trace.npcs_present    = {getattr(t, 'npcs_present', 'n/a')}")
    _flush()
    return r


def main() -> None:
    _log("=" * 70)
    _log("PROBE #80 — CAST-MOVES live acceptance (test bar 11)")
    _log("=" * 70)
    _author()

    from construct.session import Session
    from construct.provider import CodexProvider

    s = Session.open(NAME, provider=CodexProvider(), player_id="probe80", fresh=True)
    p = s._world.porcelain  # probe-only reach; Session keeps no public world handle

    def _where(pid: str) -> str:
        try:
            return (p.locate(pid) or ["?"])[0]
        except Exception as exc:  # noqa: BLE001
            return f"locate-failed: {exc}"

    _log(f"\n  CANON BEFORE: edda@{_where('person:edda')} garrick@{_where('person:garrick')}")

    all_moves: list = []
    all_drops: list = []
    # The four agreed bar-11 probes (cr <f8409447…>/<9b9d5c06…>): T1 = clean arrival
    # via the origin-restatement tie-break; T2 = stay-by-hearth negative (present cast
    # texture must mint NO departure); T3 = rule-5 engaged-dismissal drop; T4 = the
    # lone-passive departure (two other NPCs present, Edda unengaged) — a bound exit to
    # the canon well house tracks, a wholly novel destination is the ACCEPTED false
    # negative (telemetry, no event).
    for i, (move, label) in enumerate([
        ("I call toward the yard door: 'Come in out of the cold, man!'",
         "T1: invite the arrival (tie-break probe)"),
        ("I ask Nan whether the morning water is drawn yet.",
         "T2: engage NAN — Edda (unengaged) has her reason to go"),
        ("I sit back and watch the fire a while.",
         "T3: fully passive — the exit may land here if not at T2"),
        ("I look about the kitchen and note who is still with me.",
         "T4: presence check — the departed stay departed"),
    ], start=1):
        r = _turn(s, move, label)
        all_moves.extend(getattr(r.trace, "cast_moves", []) or [])
        all_drops.extend(getattr(r.trace, "cast_move_drops", []) or [])
        _log(f"    CANON AFTER T{i}: edda@{_where('person:edda')} "
             f"garrick@{_where('person:garrick')}")
    edda_final, garrick_final = _where("person:edda"), _where("person:garrick")
    s.close()

    _log("\n  VERDICT:")
    out_moves = [m for m in all_moves if m[1] == "person:edda"
                 and (m[0] == "unbound_exit"
                      or (m[0] == "bound_move" and m[2] not in ("", "place:kitchen")))]
    in_moves = [m for m in all_moves if m[1] == "person:garrick"
                and m[0] == "bound_move" and m[2] == "place:kitchen"]
    rule5 = [d for d in all_drops if d[0] == "person:edda" and d[2] == "engaged_this_turn"]
    if rule5:
        _log("  RULE 5 LIVE — Edda's same-turn narrated exit while engaged was DROPPED"
             f" ({rule5}); presence-holds held.")
    _log(f"  committed lane moves: {all_moves}")
    _log(f"  edda final: {edda_final}  garrick final: {garrick_final}")
    if all_moves:
        _log("  LANE LIVE — narrator-authored movement committed through the licensed lane"
             f" ({len(out_moves)} edda / {len(in_moves)} garrick).")
        if in_moves and garrick_final == "place:kitchen":
            _log("  ARRIVAL TRACKED — Garrick's narrated entry is canon presence truth.")
        if out_moves:
            _log("  DEPARTURE TRACKED (LANE-OWNED) — a committed transition out of the "
                 f"scene: {out_moves}")
        else:
            _log("  DEPARTURE NOT OBSERVED through the lane this run (same-scene "
                 "restatements and the dismissal channel do NOT count).")
    else:
        _log("  LANE QUIET — the narrator authored no extractable movement this run;")
        _log("  inspect the prose + drops above (drops show gate reasons if candidates arose).")
    _flush()
    print(f"\nlog: {LOG_PATH}")


if __name__ == "__main__":
    main()
