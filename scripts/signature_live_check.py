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
    "endurance": {
        "game_types": ["wilderness_survival"], "prot": "person:player",
        "people": ["person:guide", "person:companion"],
        "digest": ("A small party stranded after a crash in a frozen pass — dwindling supplies, "
                   "a storm closing in, the guide injured, one companion losing nerve."),
        "theme": "survive the descent before the cold and the dark take them"},
    "contest": {
        "game_types": ["tactical_combat"], "prot": "person:player",
        "people": ["person:rival_captain", "person:second", "person:trainer"],
        "digest": ("A martial tournament in a hard mountain city. The player faces a feared rival "
                   "captain across escalating bouts; a wily second and a grizzled trainer circle."),
        "theme": "win the championship against a worthy rival, the hard way"},
    "gambit": {
        "game_types": ["heist"], "prot": "person:player",
        "people": ["person:fixer", "person:inside_man", "person:mark"],
        "digest": ("A vault job against a corrupt financier's private bank. A nervous fixer, an "
                   "inside man with cold feet, and a mark who holds leverage over one of the crew."),
        "theme": "pull off the heist — the plan, the complications, the twist"},
    "discovery": {
        "game_types": ["exploration_discovery"], "prot": "person:player",
        "people": ["person:guide", "person:scholar"],
        "digest": ("An expedition into a vast ruined city beneath the ice, older than any record. "
                   "A local guide who fears it and a scholar who wants to claim it accompany you."),
        "theme": "uncover what the dead city was — and what it costs to understand"},
    "mastery": {
        "game_types": ["stewardship_management"], "prot": "person:player",
        "people": ["person:mentor", "person:apprentice", "person:inspector"],
        "digest": ("A failing clockwork workshop the player has inherited — debts, a skeptical "
                   "mentor, a raw apprentice, and a guild inspector who will judge the work."),
        "theme": "bring the workshop up to the guild's standard before the inspection"},
    "farce": {
        "game_types": ["farce_cover_up"], "prot": "person:player",
        "people": ["person:spouse", "person:boss", "person:neighbor"],
        "digest": ("A dinner party where one small lie about a borrowed car spirals — a suspicious "
                   "spouse, the boss who owns the car, and a nosy neighbor who saw everything."),
        "theme": "keep the cover-up from collapsing as the complications snowball"},
    "transformation": {
        "game_types": ["moral_dilemma_crucible"], "prot": "person:player",
        "people": ["person:tempter", "person:conscience", "person:wronged"],
        "digest": ("A once-honest official offered a corrupt bargain that would save their family "
                   "but doom another — a smooth tempter, an old friend who'd be wronged, the past self."),
        "theme": "who the player becomes through the defining choice"},
}


def run_one(prov, genre: str, w) -> None:
    P = _PRESETS[genre]
    game_types, prot, people, digest, theme = (P["game_types"], P["prot"], P["people"],
                                               P["digest"], P["theme"])
    shape = (shapes_for(game_types) or {}).get("shape") or genre
    sig = author_signature_directive(game_types)
    w(f"\n\n========== GENRE {genre} → shape {shape} ==========")
    w("--- AUTHOR-INSIST DIRECTIVE ---\n" + sig)
    prop = cohorts.author_cast(prov, digest, theme, shape, prot, people, signature_directive=sig)
    cast, specs = cast_from_proposal(prop)
    req = [pid for pid, _l, r in specs if r]
    known = set(people) | {prot} | {c.surface_fact[0] for n in cast for c in n.holds_clues}
    solv = check_solvability(req, cast, known_ids=known, require_staging=(shape == "deduction"))
    sig_problems = validate_signature_support([shape], cast)
    w(f"--- AUTHORED {len(specs)} pillars, {len(cast)} cast ---")
    for n in cast:
        w(f"- {n.node_id} ({n.shape_role}, culprit={n.is_culprit}, presence={n.presence}):")
        for c in n.holds_clues:
            rh = " [RH]" if c.is_red_herring else ""
            w(f"    {c.clue_id} -> {c.pillar_id} [{c.coverage_effect}/{c.reveal_condition}]{rh}: "
              f"{c.surface_fact}")
    w(f"solvability: {solv or 'NONE'}")
    w(f"signature lint (deduction-only; [] = n/a for this shape): {sig_problems or 'OK'}")


def main() -> None:
    import time
    genre = os.environ.get("GENRE", "deduction")
    genres = ([g for g in _PRESETS if g not in ("deduction", "bond")] if genre == "sweep"
              else list(_PRESETS) if genre == "all" else [genre])
    from pathlib import Path
    log = Path(f"logs/signature-sweep-{int(time.time()) if False else genre}.md")
    log.parent.mkdir(exist_ok=True)

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    prov = CodexProvider()
    for g in genres:                       # SERIAL — no concurrent live calls (contention lesson)
        try:
            run_one(prov, g, w)
        except Exception as exc:  # noqa: BLE001
            w(f"\n[{g}] ERROR: {exc}")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
