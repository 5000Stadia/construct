"""Hand-authored deduction world with a genuine CROSS-SUSPICION WEB + a resolvable deduction
game_type (so `shape_directive` fires the EMBODY-THE-GENRE block) — the reliable vehicle to
LIVE-confirm the narrator-emphasize signature channel (GENRE-SIGNATURE-ELEMENTS.md): does the
narrator lean into suspects pointing at one another + red herrings across turns?

Cast (4 suspects, all at_scene) carries cross-edges (clues whose fact references ANOTHER member),
corroborating/contradicting alibis, and two strong red herrings with a reachable debunker.
Deterministic; no authoring model calls. Solvable + passes signature lint + staging.

Run:  .venv/bin/python scripts/cross_suspicion_demo.py [name]
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
    validate_signature_support,
)

NAME = sys.argv[1] if len(sys.argv) > 1 else "crossweb"
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
    "person:widow": "Lady Brackenmere, the widow",
}
for sid, desc in PEOPLE.items():
    CANON += [
        {"entity": sid, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": sid, "attribute": "name", "value": desc, "timeless": True,
         "aliases": [sid.split(":", 1)[-1], desc.split(",", 1)[0]]},
    ]

# A cross-suspicion WEB: nearly every clue's fact names ANOTHER cast member. Two strong red
# herrings (false) both debunked by the genuine means clue (pressure-reachable). Culprit = doctor.
PROPOSAL = {
    "pillars": [
        {"id": "pillar:motive", "label": "the killer's motive", "required": True},
        {"id": "pillar:means", "label": "the means of death", "required": True},
        {"id": "pillar:opportunity", "label": "the opportunity", "required": True},
    ],
    "cast": [
        {"id": "person:butler", "shape_role": "witness", "surface_role": "butler",
         "presence": "at_scene", "first_witness": True, "clues": [
            {"clue_id": "clue:opportunity", "pillar_id": "pillar:opportunity",
             "fact": {"entity": "person:doctor", "attribute": "summoned_to_study",
                      "value": "Lord Brackenmere rang for Dr. Ames into the study just before the alarm"},
             "hook_text": "Hobbes keeps glancing at the study door, half-saying who he let in",
             "coverage_effect": "genuine", "reveal_condition": "none"},
            {"clue_id": "clue:motive_overheard", "pillar_id": "pillar:motive",
             "fact": {"entity": "person:doctor", "attribute": "threatened_exposure",
                      "value": "the lord told Dr. Ames the dispensary accounts would go to the magistrate"},
             "hook_text": "Hobbes overheard a hard word between the lord and the doctor he won't repeat",
             "coverage_effect": "genuine", "reveal_condition": "pressure"}]},
        {"id": "person:heir", "shape_role": "suspect", "surface_role": "disinherited nephew",
         "presence": "at_scene", "clues": [
            {"clue_id": "clue:doctor_alone", "pillar_id": "pillar:opportunity",
             "fact": {"entity": "person:doctor", "attribute": "alone_with_victim",
                      "value": "Julian saw Ames alone with the lord through the glass after Ames claimed he'd left"},
             "hook_text": "Julian resents the doctor and lets slip what he saw through the conservatory",
             "coverage_effect": "genuine", "reveal_condition": "pressure"},
            {"clue_id": "clue:rh_widow", "pillar_id": "pillar:motive",
             "fact": {"entity": "person:widow", "attribute": "apparent_gain",
                      "value": "Julian insists the widow inherits everything and wanted the old man dead"},
             "hook_text": "Julian is eager — too eager — to point the finger at Lady Brackenmere",
             "coverage_effect": "false", "is_red_herring": True,
             "reveal_condition": "none", "debunked_by": "clue:means_vial"}]},
        {"id": "person:doctor", "shape_role": "suspect", "surface_role": "family physician",
         "presence": "at_scene", "is_culprit": True, "clues": [
            {"clue_id": "clue:rh_natural", "pillar_id": "pillar:means",
             "fact": {"entity": "fact:means", "attribute": "claimed", "value": "natural causes"},
             "hook_text": "the doctor is calm, rehearsed, and keeps his bag close",
             "coverage_effect": "false", "is_red_herring": True,
             "reveal_condition": "none", "debunked_by": "clue:means_vial"}]},
        {"id": "person:widow", "shape_role": "suspect", "surface_role": "the widow",
         "presence": "at_scene", "clues": [
            {"clue_id": "clue:means_vial", "pillar_id": "pillar:means",
             "fact": {"entity": "person:doctor", "attribute": "removed_vial",
                      "value": "Lady Brackenmere saw Ames slip a brown vial and a syringe from his bag into his coat"},
             "hook_text": "Lady Brackenmere watched the doctor's hands at his bag after dinner",
             "coverage_effect": "genuine", "reveal_condition": "pressure"},
            {"clue_id": "clue:motive_letters", "pillar_id": "pillar:motive",
             "fact": {"entity": "person:doctor", "attribute": "feared_letters",
                      "value": "the lord sealed letters about Ames's accounts to be posted at breakfast"},
             "hook_text": "the widow saw letters sealed and a name spoken she'd rather not say",
             "coverage_effect": "genuine", "reveal_condition": "pressure"}]},
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
    sig = validate_signature_support(["deduction"], cast_nodes)
    if problems or sig:
        raise SystemExit(f"UNSOLVABLE/UNSIGNED (fix the script): solvability={problems} signature={sig}")
    print("signature lint: PASS (strong red herrings + live cross-suspicion web)")
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
        # RESOLVABLE deduction game_type so shape_directive fires the EMBODY-THE-GENRE block:
        "game_type": ["mystery_whodunnit"], "arc_scope": scope, "cast": PROPOSAL,
    }
    (Path("worlds") / f"{NAME}.meta.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote worlds/{NAME}.world — cross-suspicion web, game_type=mystery_whodunnit "
          f"(EMBODY block will fire). culprit person:doctor.")


if __name__ == "__main__":
    main()
