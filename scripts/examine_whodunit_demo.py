"""Hand-author a whodunit whose MEANS pillar is coverable ONLY by EXAMINING a physical object
(the doctor's bag — an object `scrutiny` clue), so solving requires the EXAMINE channel
(EXAMINE-CHANNEL.md acceptance). Motive + opportunity ride ASK (questioning the cast); means
rides EXAMINE. Deterministic; no authoring model calls.

Run:  .venv/bin/python scripts/examine_whodunit_demo.py [name]
Then: .venv/bin/python scripts/play_harness.py <name>
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.arc import io as arc_io
from construct.arc.conditions import AtLeast, BeatAchieved, InFrame, TurnsQuiet
from construct.arc.executor import arc_entities, turn_time
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.cast import (
    build_pillars,
    cast_from_proposal,
    cast_location_plan,
    cast_seed_plan,
    check_solvability,
)

NAME = sys.argv[1] if len(sys.argv) > 1 else "examinewho"
PROT = "person:inspector"
FRAME = f"knows:{PROT}"
PARLOR = "place:parlor"

CANON = [
    {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
    {"entity": "place:hall", "attribute": "name", "value": "Brackenmere Hall", "timeless": True},
    {"entity": PARLOR, "attribute": "kind", "value": "room", "timeless": True},
    {"entity": PARLOR, "attribute": "name", "value": "the parlor", "timeless": True},
    {"entity": PARLOR, "attribute": "in", "value": "place:hall"},
    {"entity": PROT, "attribute": "kind", "value": "person", "timeless": True},
    {"entity": PROT, "attribute": "name", "value": "Inspector Vane", "timeless": True},
    {"entity": PROT, "attribute": "role", "value": "investigator", "timeless": True},
    {"entity": PROT, "attribute": "in", "value": PARLOR},
    {"entity": "person:lord", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:lord", "attribute": "name", "value": "Lord Brackenmere", "timeless": True},
    {"entity": "person:lord", "attribute": "condition", "value": "dead"},
]
PEOPLE = {
    "person:butler": "Hobbes, the butler",
    "person:heir": "Julian, the disinherited nephew",
    "person:doctor": "Dr. Ames, the family physician",
}
for sid, desc in PEOPLE.items():
    stem = sid.split(":", 1)[-1]
    CANON += [
        {"entity": sid, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": sid, "attribute": "name", "value": desc, "timeless": True,
         "aliases": [stem, desc.split(",", 1)[0]]},
    ]
# the doctor's BAG — a physical object, examinable at the scene; holds the MEANS evidence.
CANON += [
    {"entity": "obj:bag", "attribute": "kind", "value": "object", "timeless": True},
    {"entity": "obj:bag", "attribute": "name", "value": "the doctor's bag", "timeless": True,
     "aliases": ["bag", "doctor's bag", "medical bag"]},
]

PROPOSAL = {
    "pillars": [
        {"id": "pillar:motive", "label": "the killer's motive", "required": True},
        {"id": "pillar:means", "label": "the means of death", "required": True},
        {"id": "pillar:opportunity", "label": "the opportunity", "required": True},
    ],
    "cast": [
        {"id": "person:butler", "shape_role": "witness", "surface_role": "butler",
         "presence": "at_scene", "first_witness": True,
         "clues": [{"clue_id": "clue:opportunity", "pillar_id": "pillar:opportunity",
                    "fact": {"entity": "person:doctor", "attribute": "seen_entering",
                             "value": "the study alone at ten, the night of the death"},
                    "hook_text": "Hobbes keeps glancing at the study door, half-saying who he saw",
                    "coverage_effect": "genuine", "reveal_condition": "none"}]},
        {"id": "person:heir", "shape_role": "suspect", "surface_role": "disinherited nephew",
         "presence": "at_scene",
         "clues": [{"clue_id": "clue:motive", "pillar_id": "pillar:motive",
                    "fact": {"entity": "fact:motive", "attribute": "established",
                             "value": "the doctor was quietly written back into the will last week"},
                    "hook_text": "the heir is bitter the will kept changing and won't say who gained",
                    "coverage_effect": "genuine", "reveal_condition": "pressure"}]},
        {"id": "person:doctor", "shape_role": "suspect", "surface_role": "family physician",
         "presence": "at_scene", "is_culprit": True,
         "clues": [{"clue_id": "clue:denial", "pillar_id": "pillar:means",
                    "fact": {"entity": "fact:means", "attribute": "claimed", "value": "natural causes"},
                    "hook_text": "the doctor is calm, almost rehearsed, and keeps his bag close",
                    "coverage_effect": "false", "is_red_herring": True,
                    "reveal_condition": "none", "debunked_by": "clue:means"}]},
        # THE MEANS — on the OBJECT, earned ONLY by close inspection (EXAMINE channel):
        {"id": "obj:bag", "shape_role": "evidence", "surface_role": "the doctor's bag",
         "presence": "at_scene",
         "clues": [{"clue_id": "clue:means", "pillar_id": "pillar:means",
                    "fact": {"entity": "fact:means", "attribute": "established",
                             "value": "a digitalis vial is missing from its slot in the doctor's bag"},
                    "hook_text": "the doctor's bag sits open, one loop conspicuously empty",
                    "coverage_effect": "genuine", "reveal_condition": "scrutiny"}]},
    ],
}


def main() -> None:
    Path("worlds").mkdir(exist_ok=True)
    wpath = Path("worlds") / f"{NAME}.world"
    if wpath.exists():
        wpath.unlink()
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    w = World(wpath, world_id=f"w:{NAME}", model=StubModel(fallback=fallback),
              stance="fiction", title="A Death at Brackenmere")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured(CANON)

    beat = Beat("beat:name_culprit", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame(FRAME, "fact:verdict", "named", "the doctor"))
    refusal = Clock("clock:refusal", TurnsQuiet(20),
                    effects=({"entity": "event:cold_case", "attribute": "kind",
                              "value": "refusal_conclusion"},), bound_to="arc:main",
                    rung=Rung.REFUSAL)
    shape = ConclusionShape("shape:main", "drive_inverted",
                            (PROT, "drive:certainty", "drive:truth"),
                            world_condition=AtLeast(1, (BeatAchieved("beat:name_culprit"),)),
                            premise=InFrame("canon", "person:lord", "condition", "dead"),
                            refusal_variant_id="shape:refused")
    arc = Arc(arc_id="arc:main", protagonist=PROT, shape=shape, beats=(beat,), clocks=(),
              refusal_clock=refusal, climax_ready_k=1, climax_ready_beats=("beat:name_culprit",),
              phase_budget={Phase.SETUP: 4, Phase.RISING: 6, Phase.CRISIS: 3,
                            Phase.CLIMAX: 2, Phase.FALLING: 2})

    cast_nodes, specs = cast_from_proposal(PROPOSAL)
    req = [pid for pid, _l, r in specs if r]
    known = {e["entity"] for e in CANON}
    problems = check_solvability(req, cast_nodes, known_ids=known, require_staging=True)
    if problems:
        raise SystemExit(f"EXAMINE DEMO IS UNSOLVABLE (fix the script): {problems}")
    arc = dataclasses.replace(arc, pillars=build_pillars(specs, cast_nodes, PROT))

    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    w.porcelain.ingest_structured(arc_io.portfolio_items([arc.arc_id], main_arc_id=arc.arc_id))
    for frame, items in cast_seed_plan(cast_nodes):
        if frame != FRAME:
            w.porcelain.ingest_structured(items, frame=frame)
    w.porcelain.ingest_structured(cast_location_plan(cast_nodes, PARLOR))
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame="session:main")
    w.close()

    scope = sorted({e for e in arc_entities(arc) if e.startswith(("person:", "place:", "fact:", "obj:"))}
                   | {n.node_id for n in cast_nodes} | {PARLOR})
    meta = {
        "title": "A Death at Brackenmere", "protagonist": PROT, "mode": "pure",
        "scenario_mode": "win_loss", "endless": False,
        "game_type": ["mystery"], "arc_scope": scope, "cast": PROPOSAL,
    }
    (Path("worlds") / f"{NAME}.meta.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote worlds/{NAME}.world — means is on obj:bag (scrutiny); solving REQUIRES "
          f"examining the bag (EXAMINE channel). culprit person:doctor.")


if __name__ == "__main__":
    main()
