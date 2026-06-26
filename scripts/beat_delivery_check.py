"""Cheap live validation of BEAT-DELIVERY-COHERENCE (obs #3): ONE live author_cast call,
given a set of InFrame rising-beat targets — does the generated cast now ship a clue whose
`fact` matches each REQUIRED target (so the beat can fire), and does validate_beat_delivery
pass? No 30-min build; one model call. Mirrors signature_live_check.py.

Run:  GENRE=endurance PYTHONPATH=. .venv/bin/python scripts/beat_delivery_check.py
"""
from __future__ import annotations

import json
import os

from construct import cohorts
from construct.cast import cast_from_proposal, check_solvability, validate_beat_delivery
from construct.provider import CodexProvider
from construct.story_shapes import author_signature_directive, shapes_for

# Per-genre: the digest/people + a few InFrame rising-beat targets the arc author would emit
# (entity/attribute/value referencing the canon people, ordered SETUP→RISING→CRISIS), so we can
# prove the cast author now makes each REQUIRED one deliverable.
_PRESETS = {
    "endurance": {
        "game_types": ["wilderness_survival"], "prot": "person:player",
        "people": ["person:guide", "person:companion"],
        "digest": ("A small party stranded after a crash in a frozen pass — dwindling supplies, "
                   "a storm closing in, the guide injured, one companion losing nerve."),
        "theme": "survive the descent before the cold and the dark take them",
        "beats": [
            {"entity": "person:guide", "attribute": "leg_condition", "value": "broken",
             "phase": "setup", "required": True, "beat_id": "beat:reckon_guide_leg"},
            {"entity": "person:companion", "attribute": "morale", "value": "breaking",
             "phase": "rising", "required": True, "beat_id": "beat:companion_cracks"},
            {"entity": "person:guide", "attribute": "warns", "value": "the_high_route_kills",
             "phase": "crisis", "required": True, "beat_id": "beat:guide_warns_route"},
        ]},
    "bond": {
        "game_types": ["romance"], "prot": "person:player",
        "people": ["person:mara", "person:innkeeper", "person:rival"],
        "digest": ("A rain-locked coastal inn over one long week. The player and Mara, a "
                   "lighthouse keeper's widow who guards herself, keep crossing paths; the "
                   "innkeeper and an old rival of Mara's are also about."),
        "theme": "a slow-burn romance between the player and Mara, guarded by old grief",
        "beats": [
            {"entity": "person:mara", "attribute": "guards", "value": "grief_for_late_husband",
             "phase": "setup", "required": True, "beat_id": "beat:see_her_grief"},
            {"entity": "person:rival", "attribute": "claims", "value": "old_promise_from_mara",
             "phase": "rising", "required": True, "beat_id": "beat:the_obstacle"},
            {"entity": "person:mara", "attribute": "confides", "value": "the_night_he_drowned",
             "phase": "crisis", "required": True, "beat_id": "beat:she_opens_up"},
        ]},
}
GENRE = os.environ.get("GENRE", "endurance")


def main() -> None:
    p = _PRESETS[GENRE]
    prof = shapes_for(p["game_types"])
    shape = prof["shape"]
    shapes = [prof["shape"], *prof["secondary"]]
    sig = author_signature_directive(p["game_types"])
    prov = CodexProvider()
    print(f"# beat-delivery check — {GENRE} (shape={shape})\n")
    print("REQUIRED beat targets the cast must make deliverable:")
    for b in p["beats"]:
        print(f"  - ({b['entity']}, {b['attribute']}, {b['value']})  [{b['phase']}]")
    prop = cohorts.author_cast(prov, p["digest"], p["theme"], shape, p["prot"],
                               p["people"], signature_directive=sig,
                               beat_targets=p["beats"])
    cast, specs = cast_from_proposal(prop)
    req = [pid for pid, _l, r in specs if r]
    known = {p["prot"], *p["people"], *{n.node_id for n in cast}}
    print(f"\nauthored {len(cast)} cast member(s), {len(specs)} pillar(s)\n")
    # Show, per target, whether a clue surfaces it
    want = {(b["entity"], b["attribute"], str(b["value"])): b["beat_id"] for b in p["beats"]}
    surfaced = {tuple(str(x) for x in c.surface_fact) for n in cast for c in n.holds_clues}
    print("BEAT DELIVERY (does a clue surface each target?):")
    for fact, bid in want.items():
        hit = fact in surfaced
        print(f"  [{'OK ' if hit else 'MISS'}] {bid}: {fact}")
    print("\nvalidate_beat_delivery problems:", validate_beat_delivery(p["beats"], cast) or "NONE")
    print("check_solvability problems:", check_solvability(req, cast, known_ids=known) or "NONE")
    # Dump the cast clues for eyeballing the juice + coreference
    print("\n--- CAST ---")
    for n in cast:
        print(f"{n.node_id} [{n.presence}] — {n.surface_role}")
        for c in n.holds_clues:
            print(f"    {c.surface_fact}  ({c.coverage_effect}/{c.reveal_condition})"
                  f"  «{c.hook_text[:80]}»")


if __name__ == "__main__":
    main()
