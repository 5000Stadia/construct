"""Cheap live validation of the author-insist signature channel (GENRE-SIGNATURE-ELEMENTS.md):
ONE live author_cast call on a deduction theme — does the generated cast actually SHIP the
signature (a strong red herring + a live-reachable cross-suspicion edge), and does the lint pass?
No 30-min generate-build; one model call. (Narrator-emphasize is unit-tested in shape_directive.)

Run:  PYTHONPATH=. .venv/bin/python scripts/signature_live_check.py
"""
from __future__ import annotations

import json
import os

from construct.provider import CodexProvider
from construct import cohorts
from construct.cast import cast_from_proposal, check_solvability, validate_signature_support
from construct.story_shapes import author_signature_directive, shapes_for

# Genre presets — GENRE=deduction|bond (default deduction). Per-genre rollout (full steam).
_PRESETS = {
    "deduction": {
        "game_types": ["mystery_whodunnit"], "prot": "person:inspector",
        "people": ["person:butler", "person:heir", "person:doctor", "person:widow"],
        "digest": ("Brackenmere Hall, a country house at night. Lord Brackenmere has been found "
                   "dead in his study. Present: Hobbes the butler, Julian the disinherited heir, "
                   "Dr. Ames the family physician, and Lady Brackenmere the widow."),
        "theme": "a classic country-house murder — who killed Lord Brackenmere, and how"},
    "bond": {
        "game_types": ["romance"], "prot": "person:player",
        "people": ["person:mara", "person:innkeeper", "person:rival"],
        "digest": ("A rain-locked coastal inn over one long week. The player and Mara, a "
                   "lighthouse keeper's widow who guards herself, keep crossing paths; the "
                   "innkeeper and an old rival of Mara's are also about."),
        "theme": "a slow-burn romance between the player and Mara, guarded by old grief"},
}
GENRE = os.environ.get("GENRE", "deduction")
P = _PRESETS[GENRE]
GAME_TYPES, PROT, PEOPLE, DIGEST, THEME = (P["game_types"], P["prot"], P["people"],
                                           P["digest"], P["theme"])


def main() -> None:
    prov = CodexProvider()
    shape = (shapes_for(GAME_TYPES) or {}).get("shape") or GENRE
    sig = author_signature_directive(GAME_TYPES)
    print(f"=== GENRE {GENRE} → shape {shape} ===")
    print("=== AUTHOR-INSIST DIRECTIVE FED TO author_cast ===\n" + sig + "\n")
    prop = cohorts.author_cast(prov, DIGEST, THEME, shape, PROT, PEOPLE,
                               signature_directive=sig)
    cast, specs = cast_from_proposal(prop)
    req = [pid for pid, _l, r in specs if r]
    known = set(PEOPLE) | {PROT} | {c.surface_fact[0] for n in cast for c in n.holds_clues}
    # require_staging for deduction so this is a real ATTEMPT-1 check (the build gate uses it):
    solv = check_solvability(req, cast, known_ids=known, require_staging=(shape == "deduction"))
    sig_problems = validate_signature_support([shape], cast)

    print(f"=== AUTHORED {len(specs)} pillars, {len(cast)} cast members ===")
    for n in cast:
        print(f"- {n.node_id} ({n.shape_role}, culprit={n.is_culprit}):")
        for c in n.holds_clues:
            rh = " [RED HERRING]" if c.is_red_herring else ""
            print(f"    {c.clue_id} -> {c.pillar_id} [{c.coverage_effect}/{c.reveal_condition}]"
                  f"{rh}: {c.surface_fact}")
    print(f"\nsolvability problems: {solv or 'NONE'}")
    print(f"SIGNATURE LINT: {sig_problems or 'PASS — red herring + live cross-suspicion edge present'}")


if __name__ == "__main__":
    main()
