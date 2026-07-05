"""Deepen the flagship's suspect web (founder greenlight, 2026-07-05).

The eval found The Rain in Bluegate Yard structurally a TWO-HORSE RACE (Bell the
fall guy, Liddell the answer) — exemplary investigation, thin whodunit field. This
augmentation adds two SUSPECT-GRADE characters woven into the existing fabric
(both guilty of SOMETHING, both viable for the murder until specific pillar facts
exonerate them — the Christie move):

- **Silas Crane**, publican of the Crown and Anchor: fences pilfered warehouse
  goods; withholds Bell's exoneration to protect his own trade; offers a free red
  herring (the "rival messenger quarrel").
- **Tobias Flint**, Liddell's night-watchman: leaves the river-stair door unbolted
  on ring nights and the victim had caught him at it; holds the timing fact that
  breaks Liddell's alibi — and a boat-cloak stranger story to cover himself.

All clues map to the EXISTING four pillars (new voices for the same truths —
solvability unchanged); two new false-coverage clues widen the misdirection field.
NON-DESTRUCTIVE: originals backed up as *.pre-deepen. Deterministic — no model.
Usage: .venv/bin/python scripts/deepen_bodycase.py [name]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

NAME = sys.argv[1] if len(sys.argv) > 1 else "bodycase"
ROOT = Path(__file__).resolve().parent.parent
WORLD = ROOT / "worlds" / f"{NAME}.world"
META = ROOT / "worlds" / f"{NAME}.meta.json"

CRANE = {
    "id": "person:silas_crane",
    "shape_role": "suspect",
    "surface_role": ("publican of the Crown and Anchor, genial to a fault and "
                     "listening to everything — a receiver of quietly pilfered "
                     "warehouse goods who would rather hang a stranger than open "
                     "his cellar books"),
    "presence": "nearby",
    "location": "place:crown_and_anchor",
    "first_witness": False,
    "is_culprit": False,
    "clues": [
        {"clue_id": "clue:crane_bell_alibi",
         "pillar_id": "pillar:alibis_contradictions",
         "fact": {"entity": "person:jonas_bell", "attribute": "alibi_witnessed",
                  "value": ("dead drunk in the Crown and Anchor taproom until well "
                            "past one, watched the whole time by the publican who "
                            "never said so")},
         "hook_text": ("Crane polishes a glass that is already clean. Pressed on "
                       "Jonas Bell, his geniality thins: admitting Bell never left "
                       "the taproom means admitting what hours the Crown truly "
                       "keeps, and for whom."),
         "coverage_effect": "genuine", "is_red_herring": False,
         "reveal_mode": "pressed", "reveal_condition": "pressure"},
        {"clue_id": "clue:crane_rival_quarrel",
         "pillar_id": "pillar:victim_last_errand",
         "fact": {"entity": "fact:rival_quarrel", "attribute": "claimed",
                  "value": ("a rival messenger quarreled with the dead man over "
                            "money in the taproom that evening — so Crane tells "
                            "it, freely and twice")},
         "hook_text": ("Unprompted, Crane leans in with the story of a quarrel — "
                       "a rival messenger, raised voices, money on the table. He "
                       "offers it a little too readily, the way a man hands you "
                       "a lantern pointed away from his own door."),
         "coverage_effect": "false", "is_red_herring": True,
         "reveal_mode": "volunteered", "reveal_condition": "none",
         "debunked_by": "clue:crane_token_worth"},
        {"clue_id": "clue:crane_token_worth",
         "pillar_id": "pillar:motive_sample_token",
         "fact": {"entity": "fact:token_inquiry", "attribute": "asked_at_taproom",
                  "value": ("the victim, sober and careful, asked the publican "
                            "what a warehouse sample token would fetch from the "
                            "right buyer")},
         "hook_text": ("Cornered on the token, Crane's hands stop moving. Yes — "
                       "the boy asked what such a thing might FETCH. And Crane, "
                       "who knows exactly what such things fetch and from whom, "
                       "told him to take it back where it came from."),
         "coverage_effect": "genuine", "is_red_herring": False,
         "reveal_mode": "pressed", "reveal_condition": "pressure"},
    ],
}

FLINT = {
    "id": "person:tobias_flint",
    "shape_role": "suspect",
    "surface_role": ("Liddell's night-watchman at the warehouse, a careful man "
                     "with lamp-scalded eyes — paid twice: once by wages, once by "
                     "not seeing which crates walk on late nights; the dead "
                     "messenger had caught him at it"),
    "presence": "nearby",
    "location": "place:liddell_warehouse",
    "first_witness": False,
    "is_culprit": False,
    "clues": [
        {"clue_id": "clue:flint_unbolted_door",
         "pillar_id": "pillar:opportunity_warehouse_route",
         "fact": {"entity": "person:arthur_liddell", "attribute": "standing_order",
                  "value": ("the river-stair door left unbolted on late working "
                            "nights, by his own quiet instruction — anyone who "
                            "knew could pass from the yard to the scales unseen")},
         "hook_text": ("Flint's lamp shakes, just once. The bolt on the river "
                       "door — he oils it, he does not throw it. Not on the late "
                       "nights. Whose instruction that is, he will only say with "
                       "the yard empty and Clara between him and the water."),
         "coverage_effect": "genuine", "is_red_herring": False,
         "reveal_mode": "pressed", "reveal_condition": "pressure"},
        {"clue_id": "clue:flint_boat_cloak",
         "pillar_id": "pillar:opportunity_warehouse_route",
         "fact": {"entity": "fact:boat_cloak_stranger", "attribute": "claimed",
                  "value": ("a stranger in a boat-cloak stood at the Wapping "
                            "stairs near midnight — so Flint swears, though the "
                            "fog that night would have hidden a mast at ten paces")},
         "hook_text": ("Asked who used the stairs, Flint produces a stranger — "
                       "boat-cloak, broad hat, no face. The figure arrives in his "
                       "telling exactly where his own rounds should have been."),
         "coverage_effect": "false", "is_red_herring": True,
         "reveal_mode": "volunteered", "reveal_condition": "none",
         "debunked_by": "clue:flint_liddell_return"},
        {"clue_id": "clue:flint_liddell_return",
         "pillar_id": "pillar:alibis_contradictions",
         "fact": {"entity": "person:arthur_liddell", "attribute": "seen_returning",
                  "value": ("back at the warehouse gate near half past twelve, "
                            "keys in hand, though he swore to the bureau he left "
                            "at eleven and never returned")},
         "hook_text": ("What breaks Flint at last is not the door but the gate: "
                       "he logged Mr. Liddell IN, half past twelve, because "
                       "logging is the one honesty he has left — and the page "
                       "with that line has since been torn out."),
         "coverage_effect": "genuine", "is_red_herring": False,
         "reveal_mode": "pressed", "reveal_condition": "pressure"},
    ],
}

CANON_ROWS = [
    {"entity": "person:silas_crane", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:silas_crane", "attribute": "name", "value": "Silas Crane"},
    {"entity": "person:silas_crane", "attribute": "role",
     "value": "publican of the Crown and Anchor"},
    {"entity": "person:silas_crane", "attribute": "in", "value": "place:crown_and_anchor",
     "value_type": "entity"},
    {"entity": "person:tobias_flint", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:tobias_flint", "attribute": "name", "value": "Tobias Flint"},
    {"entity": "person:tobias_flint", "attribute": "role",
     "value": "night-watchman at the Liddell warehouse"},
    {"entity": "person:tobias_flint", "attribute": "in", "value": "place:liddell_warehouse",
     "value_type": "entity"},
]

KNOWS = {
    "person:silas_crane": [
        {"attribute": "self_regard",
         "value": "a house is only as safe as what its cellar can't say"},
        {"attribute": "relationship_to_person:jonas_bell",
         "value": "a regular he half-pities and wholly uses — Bell's tab is paid in errands"},
        {"attribute": "relationship_to_person:arthur_liddell",
         "value": "the man whose goods pass through the cellar; they do not drink together in public"},
    ],
    "person:tobias_flint": [
        {"attribute": "self_regard",
         "value": "keeps the log honest because everything else about the nights is not"},
        {"attribute": "relationship_to_person:arthur_liddell",
         "value": "his employer twice over — wages and silence — and lately his fear"},
    ],
    "knows:protagonist": [  # Clara's ground with the new faces (the #75 discipline)
        {"entity": "person:clara_vale",
         "attribute": "relationship_to_person:silas_crane",
         "value": "the publican who keeps the bureau's runners fed and hears the docks talk first"},
        {"entity": "person:clara_vale",
         "attribute": "relationship_to_person:tobias_flint",
         "value": "the night-watchman you've passed on rounds — civil, tired, always glancing at the river door"},
    ],
}


def main() -> None:
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    _rule = rule_classifier_fallback()

    def _fallback(prompt: str, schema: dict):
        if prompt.startswith("Classify the lifetime"):
            return _rule(prompt, schema)   # inline durability stays honest
        return {"items": []}

    # ---- backups (never destructive) ----
    for f in (WORLD, META):
        bak = f.with_suffix(f.suffix + ".pre-deepen")
        if not bak.exists():
            shutil.copyfile(f, bak)
            print(f"backup: {bak.name}")

    # ---- meta: append the two suspects ----
    meta = json.loads(META.read_text())
    cast_list = meta["cast"]["cast"]
    have = {c["id"] for c in cast_list}
    pillar_ids = {p["id"] for p in meta["cast"]["pillars"]}
    for entry in (CRANE, FLINT):
        for cl in entry["clues"]:
            assert cl["pillar_id"] in pillar_ids, f"unknown pillar {cl['pillar_id']}"
        if entry["id"] not in have:
            cast_list.append(entry)
            print(f"meta: added {entry['id']} ({len(entry['clues'])} clues)")
    scope = meta.get("arc_scope") or []
    for pid in ("person:silas_crane", "person:tobias_flint"):
        if pid not in scope:
            scope.append(pid)
    meta["arc_scope"] = scope
    META.write_text(json.dumps(meta, indent=1))

    # ---- world: canon rows + knows frames ----
    w = World(WORLD, world_id=f"w:{NAME}", stance="fiction",
              model=StubModel(fallback=_fallback))
    w.porcelain.ingest_structured(CANON_ROWS)
    for pid in ("person:silas_crane", "person:tobias_flint"):
        rows = [{"entity": pid, **r} for r in KNOWS[pid]]
        w.porcelain.ingest_structured(rows, frame=f"knows:{pid}")
    w.porcelain.ingest_structured(KNOWS["knows:protagonist"],
                                  frame="knows:person:clara_vale")
    # verify before sealing
    for pid, loc in (("person:silas_crane", "place:crown_and_anchor"),
                     ("person:tobias_flint", "place:liddell_warehouse")):
        chain = w.porcelain.locate(pid)
        assert chain and chain[0] == loc, f"{pid} not placed: {chain}"
    w.close()

    # ---- summary ----
    suspects = [c["id"] for c in cast_list
                if c.get("shape_role") == "suspect" or c.get("is_culprit")]
    herring_holders = [c["id"] for c in cast_list
                       if any(cl.get("coverage_effect") == "false"
                              for cl in c.get("clues") or [])]
    total = sum(len(c.get("clues") or []) for c in cast_list)
    print(f"\nDEEPENED: {len(cast_list)} cast · {len(suspects)} suspect-grade "
          f"({', '.join(s.split(':')[1] for s in suspects)})")
    print(f"clues: {total} total · false-coverage holders: "
          f"{', '.join(h.split(':')[1] for h in herring_holders)}")


if __name__ == "__main__":
    main()
