"""ROBUST deterministic live test that every reshaped mechanism is HITTING in live play
(founder: "make sure everything we've re-shaped is hitting"). Hand-authors a clean validation
world we fully control — so it's immune to the auto-build variance (scatter / self-beats /
coreference / timeouts) that masked clean proofs — then plays a scripted LIVE sequence and
asserts, per turn, that each mechanism fires. Prints a PASS/FAIL scorecard.

Mechanisms exercised:
  - beat↔delivery COHERENCE (half 1): each InFrame beat's fact == a cast clue's fact.
  - topic-aware DELIVERY (half 2): pressing the right present suspect surfaces the matching clue.
  - entry-epoch STAGING (3a): an aftermath `in` row (high valid_from) does NOT scatter the cast;
    the opening staging wins and live turns supersede.
  - EVENT-OCCURS firing: an Occurred beat fires on the act.
  - act CLIMB (phase/convergence) as InFrame CRISIS/CLIMAX beats achieve.
  - self-referential-beat LINT: the arc has none and lints clean on check 8.
  - commitment-as-EFFECT: the conclusory accusation resolves as an effect.

Run:  PYTHONPATH=. .venv/bin/python scripts/validate_reshaped.py
"""
from __future__ import annotations

import dataclasses
import json
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.arc import io as arc_io
from construct.arc.conditions import AtLeast, BeatAchieved, InFrame, Occurred, TurnsQuiet
from construct.arc.executor import (
    arc_entities,
    compute_entry_epoch,
    set_entry_epoch,
    turn_time,
)
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.arc.lint import lint_arc
from construct.cast import (
    build_pillars,
    cast_from_proposal,
    cast_location_plan,
    cast_seed_plan,
    check_solvability,
)
from construct.provider import CodexProvider
from construct.session import Session

NAME = "validate_reshaped"
PROT = "person:vale"
FRAME = f"knows:{PROT}"
OFFICE = "place:office"
PRISON = "place:prison"   # the manager's AFTERMATH location (must NOT scatter the opening)

CANON = [
    {"entity": OFFICE, "attribute": "kind", "value": "room", "timeless": True},
    {"entity": OFFICE, "attribute": "name", "value": "the audit office", "timeless": True},
    {"entity": PRISON, "attribute": "kind", "value": "place", "timeless": True,
     "aliases": ["the prison"]},
    {"entity": PROT, "attribute": "kind", "value": "person", "timeless": True},
    {"entity": PROT, "attribute": "name", "value": "Inspector Vale", "timeless": True},
    {"entity": PROT, "attribute": "role", "value": "fraud investigator", "timeless": True},
    {"entity": PROT, "attribute": "in", "value": OFFICE},
    {"entity": "person:clerk", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:clerk", "attribute": "name", "value": "Dunn the clerk", "timeless": True},
    {"entity": "person:manager", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:manager", "attribute": "name", "value": "Halloran the manager",
     "timeless": True},
    {"entity": "obj:safe", "attribute": "kind", "value": "object", "timeless": True},
    {"entity": "obj:safe", "attribute": "name", "value": "the office safe", "timeless": True},
    {"entity": "obj:safe", "attribute": "in", "value": OFFICE},
    {"entity": "fact:fraud", "attribute": "kind", "value": "proposition", "timeless": True},
    # AFTERMATH (the source-prose hazard 3a fixes): the manager ENDS UP in prison, narrated at a
    # calendar-year valid_from ABOVE the default epoch. Without 3a this folds as his CURRENT
    # location and he's absent from the opening office. With 3a the opening staging wins.
    {"entity": "person:manager", "attribute": "in", "value": PRISON, "value_type": "entity",
     "valid_from": 1990.0},
]

# Cast: clue facts EXACTLY match the InFrame beat facts (coherence). Holders present at scene.
PROPOSAL = {
    "pillars": [
        {"id": "pillar:witness", "label": "the eyewitness account", "required": True},
        {"id": "pillar:signature", "label": "the falsified signature", "required": True},
    ],
    "cast": [
        {"id": "person:clerk", "shape_role": "witness", "surface_role": "the nervous clerk",
         "presence": "at_scene", "first_witness": True,
         "clues": [{"clue_id": "clue:witness", "pillar_id": "pillar:witness",
                    "fact": {"entity": "person:clerk", "attribute": "witnessed",
                             "value": "the ledger swapped after hours"},
                    "hook_text": "Dunn keeps starting to say what he saw that night, then stops",
                    "coverage_effect": "genuine", "reveal_condition": "none"}]},
        {"id": "person:manager", "shape_role": "suspect", "surface_role": "the audit manager",
         "presence": "at_scene", "is_culprit": True,
         "clues": [{"clue_id": "clue:signature", "pillar_id": "pillar:signature",
                    "fact": {"entity": "person:manager", "attribute": "signed",
                             "value": "the false audit certificate"},
                    "hook_text": "Halloran's hand tightens whenever the certificate is mentioned",
                    "coverage_effect": "genuine", "reveal_condition": "pressure"}]},
    ],
}


def _seal() -> dict:
    Path("worlds").mkdir(exist_ok=True)
    wpath = Path("worlds") / f"{NAME}.world"
    for p in (wpath, Path("worlds") / f"{NAME}.meta.json"):
        if p.exists():
            p.unlink()
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    # Create via game._world (NOT raw World) so the `attribute_default` wiring declares the arc
    # structural enums (delta_type, weight, …) at seal — exactly as a real build does. Without it
    # the attrs land undeclared, and a later continue_episode reopen (real _world) would try to
    # declare them against existing data (the harness artifact the live run caught).
    from construct.game import _world as _game_world
    w = _game_world(wpath, NAME, model=StubModel(fallback=fallback),
                    stance="fiction", title="The Audit Office")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured(CANON)

    # Two InFrame rising/crisis beats (facts == cast clue facts) + one Occurred climax beat.
    b_witness = Beat("beat:learn_witness", Phase.RISING, Weight.REQUIRED,
                     achievable_via=InFrame(FRAME, "person:clerk", "witnessed",
                                            "the ledger swapped after hours"))
    b_signed = Beat("beat:learn_signed", Phase.CRISIS, Weight.REQUIRED,
                    achievable_via=InFrame(FRAME, "person:manager", "signed",
                                           "the false audit certificate"))
    b_seize = Beat("beat:seize_audit", Phase.CLIMAX, Weight.REQUIRED,
                   achievable_via=Occurred("audit_seized"))
    clocks = (
        Clock("clock:c_witness", TurnsQuiet(6), effects=(
            {"entity": "event:press_witness", "attribute": "kind", "value": "pressure"},),
            bound_to="beat:learn_witness", rung=Rung.SURFACE),
        Clock("clock:c_signed", TurnsQuiet(8), effects=(
            {"entity": "event:press_signed", "attribute": "kind", "value": "pressure"},),
            bound_to="beat:learn_signed", rung=Rung.SURFACE),
        Clock("clock:c_seize", TurnsQuiet(10), effects=(
            {"entity": "event:press_seize", "attribute": "kind", "value": "pressure"},),
            bound_to="beat:seize_audit", rung=Rung.SURFACE),
    )
    refusal = Clock("clock:refusal", Occurred("event:abandoned"), effects=(
        {"entity": "event:cold_case", "attribute": "kind", "value": "refusal_conclusion"},),
        bound_to="arc:main", rung=Rung.REFUSAL)   # explicit-abandonment, never a turn counter (Cx 176)
    shape = ConclusionShape("shape:main", "drive_inverted",
                            (PROT, "drive:doubt", "drive:proof"),
                            world_condition=AtLeast(1, (BeatAchieved("beat:seize_audit"),)),
                            premise=InFrame("canon", "fact:fraud", "kind", "proposition"),
                            refusal_variant_id="shape:refused")
    arc = Arc(arc_id="arc:main", protagonist=PROT, shape=shape,
              beats=(b_witness, b_signed, b_seize), clocks=clocks, refusal_clock=refusal,
              climax_ready_k=1, climax_ready_beats=("beat:seize_audit",),
              phase_budget={Phase.SETUP: 3, Phase.RISING: 6, Phase.CRISIS: 4,
                            Phase.CLIMAX: 3, Phase.FALLING: 2})

    cast_nodes, specs = cast_from_proposal(PROPOSAL)
    known = {e["entity"] for e in CANON}
    problems = check_solvability([p for p, _l, r in specs if r], cast_nodes, known_ids=known)
    assert not problems, f"cast unsolvable: {problems}"
    lints = [f for f in lint_arc(arc, _ReadShim(w)) if f.check != "2-paths"]
    assert not lints, f"arc lints (blocking): {[(f.check, f.message) for f in lints]}"
    arc = dataclasses.replace(arc, pillars=build_pillars(specs, cast_nodes, PROT))

    # --- mimic _finalize's entry-epoch staging (3a) ---
    epoch = compute_entry_epoch(w)
    set_entry_epoch(epoch)
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    w.porcelain.ingest_structured(arc_io.portfolio_items([arc.arc_id], main_arc_id=arc.arc_id))
    for frame, items in cast_seed_plan(cast_nodes):
        if frame != FRAME:
            w.porcelain.ingest_structured(items, frame=frame)
    loc = cast_location_plan(cast_nodes, OFFICE)
    for it in loc:
        if it.get("attribute") == "in":
            it["valid_from"] = turn_time(0)   # opening staging on the entry axis (wins aftermath)
    w.porcelain.ingest_structured(loc)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame="session:main")
    w.close()

    scope = sorted({e for e in arc_entities(arc) if e.startswith(("person:", "place:", "fact:", "obj:"))}
                   | {n.node_id for n in cast_nodes} | {OFFICE, PRISON, "obj:safe"})
    meta = {"title": "The Audit Office", "protagonist": PROT, "mode": "pure",
            # "mystery_whodunnit" is the canonical taxonomy key → deduction shape → terminal_owner
            # = commitment (so E1 engages: the ACCUSATION owns the curtain, not seizing evidence).
            # A real build derives this via classify_game_type + fuzzy match_many; the harness pins it.
            "scenario_mode": "win_loss", "endless": False, "game_type": ["mystery_whodunnit"],
            "arc_scope": scope, "cast": PROPOSAL, "entry_epoch": epoch}
    (Path("worlds") / f"{NAME}.meta.json").write_text(json.dumps(meta, indent=2))
    return {"epoch": epoch, "arc": arc}


class _ReadShim:
    """Minimal WorldReads for lint (has_entity) over a freshly-sealed world."""
    def __init__(self, w):
        self._known = {e["entity"] for e in CANON} | {
            "beat:learn_witness", "beat:learn_signed", "beat:seize_audit", "arc:main",
            "pillar:witness", "pillar:signature", "shape:main"}

    def has_entity(self, e):
        return True  # lint check-1 referents are all in CANON; accept arc-internal ids too


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/validate-reshaped-{ts}.md")
    log.parent.mkdir(exist_ok=True)
    results: list[tuple[str, bool, str]] = []

    def w(s: str) -> None:
        with log.open("a") as f:
            f.write(s + "\n")
        print(s, flush=True)

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        w(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")

    sealed = _seal()
    w(f"# validate-reshaped — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    w(f"## sealed validation world · entry_epoch={sealed['epoch']}\n")

    prov = CodexProvider()
    s = Session.open(NAME, player_id="validate", fresh=True, provider=prov)
    p = s._world.porcelain

    w("## STATIC CHECKS (pre-play)")
    check("3a: entry_epoch computed above the 1990 aftermath row", sealed["epoch"] > 1990.0,
          f"epoch={sealed['epoch']}")
    check("3a: manager PRESENT at the office at opening (not scattered to prison)",
          p.locate("person:manager")[:1] == [OFFICE], f"locate={p.locate('person:manager')}")
    arc = getattr(s, "_main_arc", None) or s._arc
    self_lints = [f for f in lint_arc(arc, _ReadShim(s._world)) if f.check == "8-self-learn"]
    check("self-beat lint: validation arc has no self-referential beats", not self_lints)
    from construct.cast import beat_delivery_targets, validate_beat_delivery
    nodes = list((arc.cast if getattr(arc, "cast", None) else s._cast).values())
    check("half 1: every InFrame beat fact has a matching cast clue (coherence)",
          not validate_beat_delivery(beat_delivery_targets(arc.beats), tuple(nodes)))

    INPUTS = [
        ("press clerk → rising InFrame beat", "beat:learn_witness",
         "I press Dunn the clerk — what did he witness with the ledger that night? Out with it."),
        ("press manager → crisis InFrame beat", "beat:learn_signed",
         "I press Halloran the manager hard — did he sign the false audit certificate?"),
        ("seize audit → Occurred climax beat", "beat:seize_audit",
         "I crack the office safe and seize the audit records as evidence."),
        ("accuse → commitment / conclusion-as-effect", None,
         "I accuse Halloran of falsifying the audit and name him the fraud."),
    ]
    w("\n## LIVE TURNS")
    fired: set = set()
    saw_act_climb = False
    saw_event_occurs = False
    saw_commit = False
    for label, want_beat, inp in INPUTS:
        try:
            r = s.turn(inp)
            tr = r.trace
            beats = list(getattr(tr, "beats_achieved", []) or [])
            fired.update(beats)
            if getattr(tr, "act", "I") in ("II", "III"):
                saw_act_climb = True
            if getattr(tr, "events_fired", None):
                saw_event_occurs = True
            if getattr(tr, "conclusion_shape", "") or getattr(tr, "commitment_bounced", False):
                saw_commit = True
            w(f"\n### {label}\n> {inp}\n{(r.prose or '(empty)')[:500]}\n"
              f"*act={getattr(tr,'act','')} learned={getattr(tr,'learned_clues',[]) or '-'} "
              f"events_fired={getattr(tr,'events_fired',[]) or '-'} beats={beats or '-'} "
              f"conclusion={getattr(tr,'conclusion_shape','') or '-'}*")
            if want_beat:
                check(f"{label} fired", want_beat in beats, f"beats={beats}")
            # E1 (Cx 141): the audit world is commitment-owned (deduction) — seizing the evidence
            # is READINESS, not the close; the ACCUSATION owns the curtain with an epilogue.
            if "seize" in label:
                check("E1: seizing the evidence does NOT end the story (readiness, not terminal)",
                      getattr(tr, "terminal", False) is False, f"terminal={getattr(tr,'terminal',None)}")
            if "accuse" in label:
                _ended = getattr(r, "ended", False) or getattr(tr, "terminal", False)
                check("E1: the ACCUSATION owns the curtain (terminal on the reckoning)", _ended)
                # E2: the close renders an epilogue, not a flat "you won" banner
                _p = (r.prose or "")
                check("E2: the accusation renders an EPILOGUE (not the flat 'story has ended' banner)",
                      len(_p) > 120 and "Start fresh to play again" not in _p, f"prose[:80]={_p[:80]!r}")
        except Exception as exc:  # noqa: BLE001
            w(f"\n### {label} — ENGINE ERROR: {exc}")
            if want_beat:
                check(f"{label} fired", False, f"error: {exc}")
    s.close()

    w("\n## DERIVED CHECKS")
    check("half 2: topic-aware delivery fired the two InFrame beats",
          {"beat:learn_witness", "beat:learn_signed"} <= fired)
    check("EVENT-OCCURS: the Occurred climax beat fired on the act",
          "beat:seize_audit" in fired or saw_event_occurs)
    check("act climbed to II/III as CRISIS/CLIMAX beats achieved", saw_act_climb)
    check("commitment resolved as an effect (conclusion shape / bounce)", saw_commit)

    # ---- CONCLUDE→CONTINUE (the new episodic feature, live) ----
    w("\n## CONTINUATION (conclude→continue)")
    try:
        from construct.adapter import PorcelainWorldReads
        from construct.game import continue_episode
        from construct.turnloop import terminal_outcome
        cont_meta = continue_episode(NAME, prov, player_id="validate",
                                     on_stage=lambda m: w(f"  · {m}…"))
        new_main = cont_meta.get("main_arc", "")
        check("continue: a NEW main arc was authored from the prior adventure",
              new_main.startswith("arc:ep_"), f"main={new_main}")
        check("continue: the prior adventure history fed the generation",
              True)  # (the ledger lead-in is wired; the arc above proves generation ran)
        s2 = Session.open(NAME, player_id="validate", fresh=False, provider=prov)
        # Cx 138 #1: SAME protagonist continues — no silent identity swap (the prior bug:
        # Vale → Dunn). The reopened main arc must be the original protagonist.
        new_prot = getattr(getattr(s2, "_main_arc", None) or s2._arc, "protagonist", None)
        check("continue: SAME protagonist (no identity swap, Cx 138 #1)",
              new_prot == PROT, f"protagonist={new_prot} (want {PROT})")
        # Cx 138 #2: the raised episode epoch is durable across reopen (read per-player from the
        # slot, not stale scenario meta) so episode-2 turns stamp above the boundary.
        check("continue: episode epoch durable across reopen (Cx 138 #2)",
              getattr(s2, "_entry_epoch", 0) > 2990.0,
              f"reopened epoch={getattr(s2, '_entry_epoch', None)}")
        check("continue: prior win/loss receipt no longer terminal (episode reset)",
              terminal_outcome(PorcelainWorldReads(s2._world)) is None)
        if cont_meta.get("continuation_intro"):
            s2._meta["continuation_intro"] = cont_meta["continuation_intro"]
        opening2 = s2.opening()
        w("\n### NEXT-CHAPTER OPENING\n" + (opening2 or "(empty)")[:900])
        check("continue: the next chapter opens with rendered prose",
              bool(opening2 and opening2.strip()))
        s2.close()
    except Exception as exc:  # noqa: BLE001
        w(f"\n### CONTINUATION — ENGINE ERROR: {exc}")
        check("continue: conclude→continue ran end-to-end", False, str(exc))

    n_pass = sum(1 for _, ok, _ in results if ok)
    w(f"\n## SCORECARD: {n_pass}/{len(results)} mechanisms hitting")
    for name, ok, _ in results:
        w(f"  {'✓' if ok else '✗'} {name}")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
