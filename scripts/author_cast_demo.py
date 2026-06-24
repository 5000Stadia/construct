"""Hand-author a small, pillar-bearing whodunit `.world` — the cast-path acceptance target
(Cx 036: validate cast→interview→coverage→conclusion WITHOUT the 30-min generate tax).

Deterministic: no authoring model calls. Builds canon + a pillar-bearing arc + a solvable
cast (3 required pillars, genuine clues all none/pressure-reachable, one red herring with a
reachable debunker) exactly the way the FIXED `_finalize_scenario` would seal one — so the
harness/bot can open it and play the real path. Writes worlds/<name>.world + .meta.json.

Run:  .venv/bin/python scripts/author_cast_demo.py [name]
Then: .venv/bin/python scripts/play_harness.py <name>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.arc import io as arc_io
from construct.arc.conditions import AtLeast, BeatAchieved, InFrame, TurnsQuiet
from construct.arc.executor import arc_entities, turn_time
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.cast import build_pillars, cast_from_proposal, cast_seed_plan, check_solvability

NAME = sys.argv[1] if len(sys.argv) > 1 else "castdemo"
PROT = "person:inspector"
FRAME = f"knows:{PROT}"
PARLOR = "place:parlor"

# --- the canon: a country-house murder, suspects gathered in the parlor with the player ---
CANON = [
    {"entity": "place:hall", "attribute": "kind", "value": "place", "timeless": True},
    {"entity": "place:hall", "attribute": "name", "value": "Brackenmere Hall", "timeless": True},
    {"entity": PARLOR, "attribute": "kind", "value": "room", "timeless": True},
    {"entity": PARLOR, "attribute": "name", "value": "the parlor", "timeless": True},
    {"entity": PARLOR, "attribute": "in", "value": "place:hall"},
    {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
    {"entity": "place:study", "attribute": "name", "value": "the study", "timeless": True},
    {"entity": "place:study", "attribute": "in", "value": "place:hall"},
    {"entity": PROT, "attribute": "kind", "value": "person", "timeless": True},
    {"entity": PROT, "attribute": "name", "value": "Inspector Vane", "timeless": True},
    {"entity": PROT, "attribute": "role", "value": "investigator", "timeless": True},
    {"entity": PROT, "attribute": "in", "value": PARLOR},
    {"entity": "person:lord", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:lord", "attribute": "name", "value": "Lord Brackenmere", "timeless": True},
    {"entity": "person:lord", "attribute": "condition", "value": "dead"},
    {"entity": "person:lord", "attribute": "in", "value": "place:study"},
]
# the five suspects, all PRESENT in the parlor (so interview delivery can fire)
SUSPECTS = {
    "person:heir": "Julian, the disinherited nephew",
    "person:doctor": "Dr. Ames, the family physician",
    "person:butler": "Hobbes, the butler",
    "person:widow": "Lady Brackenmere, the widow",
    "person:cook": "Mrs. Tilling, the cook",
}
for sid, desc in SUSPECTS.items():
    CANON += [
        {"entity": sid, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": sid, "attribute": "name", "value": desc, "timeless": True},
        {"entity": sid, "attribute": "in", "value": PARLOR},
    ]

# --- the cast proposal (the shape author_cast emits): 3 pillars, genuine clues none/pressure,
#     one strong red herring (the widow) with a reachable debunker (the cook) ---
PROPOSAL = {
    "pillars": [
        {"id": "pillar:motive", "label": "the killer's motive", "required": True},
        {"id": "pillar:means", "label": "the means of death", "required": True},
        {"id": "pillar:opportunity", "label": "the opportunity", "required": True},
    ],
    "cast": [
        {"id": "person:heir", "shape_role": "suspect", "surface_role": "disinherited nephew",
         "clues": [{"clue_id": "clue:motive", "pillar_id": "pillar:motive",
                    "fact": {"entity": "fact:motive", "attribute": "established",
                             "value": "the heir was cut from the will the day before"},
                    "coverage_effect": "genuine", "reveal_condition": "none"}]},
        {"id": "person:doctor", "shape_role": "suspect", "surface_role": "physician",
         "clues": [{"clue_id": "clue:means", "pillar_id": "pillar:means",
                    "fact": {"entity": "fact:means", "attribute": "established",
                             "value": "a vial of digitalis is missing from the doctor's bag"},
                    "coverage_effect": "genuine", "reveal_condition": "pressure"}]},
        {"id": "person:butler", "shape_role": "witness", "surface_role": "butler",
         "clues": [{"clue_id": "clue:opportunity", "pillar_id": "pillar:opportunity",
                    "fact": {"entity": "fact:opportunity", "attribute": "established",
                             "value": "the study was unlocked for a private visitor at ten"},
                    "coverage_effect": "genuine", "reveal_condition": "none"}]},
        {"id": "person:widow", "shape_role": "suspect", "surface_role": "the widow",
         "clues": [{"clue_id": "clue:herring", "pillar_id": "pillar:means",
                    "fact": {"entity": "fact:means", "attribute": "blamed", "value": "the widow"},
                    "coverage_effect": "false", "is_red_herring": True,
                    "reveal_condition": "none", "debunked_by": "clue:alibi"}]},
        {"id": "person:cook", "shape_role": "witness", "surface_role": "cook",
         "clues": [{"clue_id": "clue:alibi", "pillar_id": "pillar:means",
                    "fact": {"entity": "fact:means", "attribute": "cleared",
                             "value": "the widow was in the kitchen all evening"},
                    "coverage_effect": "genuine", "reveal_condition": "none"}]},
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

    # the arc: the climax beat is naming the culprit; pillars are the causes
    beat = Beat("beat:name_culprit", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame(FRAME, "fact:verdict", "named", "the heir"))
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
    problems = check_solvability(req, cast_nodes, known_ids=known)
    if problems:
        raise SystemExit(f"DEMO CAST IS UNSOLVABLE (fix the script): {problems}")
    import dataclasses
    arc = dataclasses.replace(arc, pillars=build_pillars(specs, cast_nodes, PROT))

    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    w.porcelain.ingest_structured(
        arc_io.portfolio_items([arc.arc_id], main_arc_id=arc.arc_id))
    for frame, items in cast_seed_plan(cast_nodes):
        if frame != FRAME:  # never pre-seed the player with the answers
            w.porcelain.ingest_structured(items, frame=frame)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame="session:main")
    w.close()

    scope = sorted({e for e in arc_entities(arc) if e.startswith(("person:", "place:", "fact:"))}
                   | {n.node_id for n in cast_nodes})
    meta = {
        "title": "A Death at Brackenmere", "protagonist": PROT, "mode": "pure",
        "scenario_mode": "win_loss", "endless": False,
        "game_type": ["mystery_whodunnit", "detective_procedural"],
        "arc_scope": scope, "cast": PROPOSAL,
        "goal_statement": "find who killed Lord Brackenmere and name them",
        "intro": ("Brackenmere Hall, the night of the storm. Lord Brackenmere lies dead in "
                  "his study, and the household is gathered in the parlor — the nephew, the "
                  "physician, the butler, the widow, the cook. You are Inspector Vane. "
                  "Someone here did it; the truth is in what they let slip."),
        "style": ("A drawing-room mystery — wry, observant, fair-play. Let each suspect be a "
                  "person under pressure; the clues come out in their words when you press."),
    }
    Path("worlds") / f"{NAME}.world"  # noqa
    (Path("worlds") / f"{NAME}.meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Authored worlds/{NAME}.world — pillars={[p.pillar_id for p in arc.pillars]} "
          f"cast={[n.node_id for n in cast_nodes]} scope={len(scope)} solvable=YES")


if __name__ == "__main__":
    main()
