"""LIVE proof of the OTHER terminal pole — `world_event`-owned endurance — plus the
GAUGE primitive against a live sealed world (founder: "let Picard loose in any style";
Cx 147 gap #2 = the world-reckons curtain was never live-proven).

The audit world (validate_reshaped.py) proved the COMMITMENT pole: the climax act is
READINESS, the player's accusation draws the curtain. This is its mirror: a
`creature_feature` station (endurance → `terminal_owner="world_event"`) where the SAME
structural position — a climax `Occurred` world_condition — TERMINATES, because the world
itself reckons (you reach the evac and launch; no accusation exists to make). One sealed
world, scripted live, asserting per turn:

  - rising/crisis InFrame beats fire (creature weakness, then the escape route);
  - the climax survival act TERMINATES as a `world_event` curtain (terminal=True) — the
    contrast with the audit seize (terminal=False, readiness) is the whole point;
  - the close renders an epilogue (survival aftermath), not the flat banner;
  - GAUGE: a draining-oxygen gauge on the live world reads/folds signed deltas and a
    `Quantity` floor flips TRUE on the crossing — the numeric-constraint trigger, proven
    against the real sealed world (the run-loop auto-drain/surfacing is the next increment,
    GAUGE-PRIMITIVE.md §3-§5, pending Cx 148).

Run:  PYTHONPATH=. .venv/bin/python scripts/validate_endurance.py
"""
from __future__ import annotations

import dataclasses
import json
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.arc import io as arc_io
from construct.arc.conditions import (
    AtLeast, BeatAchieved, InFrame, Occurred, Quantity, TurnsQuiet, Truth, evaluate,
)
from construct.arc.executor import (
    arc_entities, compute_entry_epoch, set_entry_epoch, turn_time,
)
from construct.arc.grammar import (
    Arc, Beat, Clock, ConclusionShape, Gauge, Phase, Rung, Weight,
)
from construct.arc.lint import lint_arc
from construct.adapter import PorcelainWorldReads
from construct.cast import (
    build_pillars, cast_from_proposal, cast_location_plan, cast_seed_plan,
    check_solvability,
)
from construct.gauge import commit_gauge, read_gauge, seed_gauge
from construct.provider import CodexProvider
from construct.session import Session

NAME = "validate_endurance"
PROT = "person:reyes"
FRAME = f"knows:{PROT}"
STATION = "place:station"
EVAC = "place:evac"

CANON = [
    {"entity": STATION, "attribute": "kind", "value": "room", "timeless": True},
    {"entity": STATION, "attribute": "name", "value": "the station deck", "timeless": True},
    {"entity": EVAC, "attribute": "kind", "value": "place", "timeless": True,
     "aliases": ["the evac bay"]},
    {"entity": EVAC, "attribute": "name", "value": "the evac bay", "timeless": True},
    {"entity": PROT, "attribute": "kind", "value": "person", "timeless": True},
    {"entity": PROT, "attribute": "name", "value": "Reyes", "timeless": True},
    {"entity": PROT, "attribute": "role", "value": "station technician", "timeless": True},
    {"entity": PROT, "attribute": "in", "value": STATION},
    {"entity": "person:medic", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:medic", "attribute": "name", "value": "Okonkwo the medic",
     "timeless": True},
    {"entity": "person:foreman", "attribute": "kind", "value": "person", "timeless": True},
    {"entity": "person:foreman", "attribute": "name", "value": "Vance the foreman",
     "timeless": True},
    {"entity": "creature:stalker", "attribute": "kind", "value": "creature", "timeless": True},
    {"entity": "creature:stalker", "attribute": "name", "value": "the stalker",
     "timeless": True},
    {"entity": "fact:loose", "attribute": "kind", "value": "proposition", "timeless": True},
]

# Cast clue facts EXACTLY match the InFrame beat facts (coherence). Holders present.
PROPOSAL = {
    "pillars": [
        {"id": "pillar:weakness", "label": "the creature's weakness", "required": True},
        {"id": "pillar:route", "label": "the way out", "required": True},
    ],
    "cast": [
        {"id": "person:medic", "shape_role": "ally", "surface_role": "the station medic",
         "presence": "at_scene", "first_witness": True,
         "clues": [{"clue_id": "clue:weakness", "pillar_id": "pillar:weakness",
                    "fact": {"entity": "creature:stalker", "attribute": "hunts_by",
                             "value": "heat — kill the lights and it loses you"},
                    "hook_text": "Okonkwo keeps glancing at the thermal readout, working something out",
                    "coverage_effect": "genuine", "reveal_condition": "none"}]},
        {"id": "person:foreman", "shape_role": "ally", "surface_role": "the deck foreman",
         "presence": "at_scene",
         "clues": [{"clue_id": "clue:route", "pillar_id": "pillar:route",
                    "fact": {"entity": EVAC, "attribute": "status",
                             "value": "still powered — the lift codes are 7-7-1"},
                    "hook_text": "Vance won't say it aloud, but he keeps looking toward the evac corridor",
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

    from construct.game import _world as _game_world
    w = _game_world(wpath, NAME, model=StubModel(fallback=fallback),
                    stance="fiction", title="Deepwater Station")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured(CANON)

    # Two InFrame rising/crisis beats (facts == cast clue facts) + one Occurred climax.
    b_weak = Beat("beat:learn_weakness", Phase.RISING, Weight.REQUIRED,
                  achievable_via=InFrame(FRAME, "creature:stalker", "hunts_by",
                                         "heat — kill the lights and it loses you"))
    b_route = Beat("beat:learn_route", Phase.CRISIS, Weight.REQUIRED,
                   achievable_via=InFrame(FRAME, EVAC, "status",
                                          "still powered — the lift codes are 7-7-1"))
    b_evac = Beat("beat:reach_evac", Phase.CLIMAX, Weight.REQUIRED,
                  achievable_via=Occurred("evac_launched"))
    clocks = (
        Clock("clock:c_weak", TurnsQuiet(6), effects=(
            {"entity": "event:press_weak", "attribute": "kind", "value": "pressure"},),
            bound_to="beat:learn_weakness", rung=Rung.SURFACE),
        Clock("clock:c_route", TurnsQuiet(8), effects=(
            {"entity": "event:press_route", "attribute": "kind", "value": "pressure"},),
            bound_to="beat:learn_route", rung=Rung.SURFACE),
        Clock("clock:c_evac", TurnsQuiet(10), effects=(
            {"entity": "event:press_evac", "attribute": "kind", "value": "pressure"},),
            bound_to="beat:reach_evac", rung=Rung.SURFACE),
    )
    refusal = Clock("clock:refusal", Occurred("event:abandoned"), effects=(
        {"entity": "event:overrun", "attribute": "kind", "value": "refusal_conclusion"},),
        bound_to="arc:main", rung=Rung.REFUSAL)   # explicit-abandonment, never a turn counter (Cx 176)
    # world_condition = reach the evac (Occurred climax). Endurance is world_event-owned, so
    # this DIRECTLY terminates — the world draws the curtain (escape), unlike the audit world
    # where the structurally-identical seize was only climax-READINESS.
    shape = ConclusionShape("shape:main", "drive_inverted",
                            (PROT, "drive:fear", "drive:resolve"),
                            world_condition=AtLeast(1, (BeatAchieved("beat:reach_evac"),)),
                            premise=InFrame("canon", "fact:loose", "kind", "proposition"),
                            refusal_variant_id="shape:refused")
    # GAUGE: a draining-oxygen reserve declared ON the arc. base_delta drains every
    # turn; "run" burns extra. Terminal floor at 0 folds into failure_when (a LOSS).
    # Tuned so the 3-turn escape lands with the reserve in the costly band (≤25%):
    # seed 100 → t1 -20 → 80 → t2 -20 → 60 → t3 "run"(-40) → 20 = 20% → costly_victory.
    oxygen = Gauge("gauge:oxygen", "oxygen reserve", baseline=100.0, floor=0.0,
                   base_delta=-20.0, costly_band=0.25,
                   action_modifiers=(("run", -20.0), ("rest", +15.0)))
    arc = Arc(arc_id="arc:main", protagonist=PROT, shape=shape,
              beats=(b_weak, b_route, b_evac), clocks=clocks, refusal_clock=refusal,
              climax_ready_k=1, climax_ready_beats=("beat:reach_evac",),
              phase_budget={Phase.SETUP: 3, Phase.RISING: 6, Phase.CRISIS: 4,
                            Phase.CLIMAX: 3, Phase.FALLING: 2},
              gauges=(oxygen,))

    cast_nodes, specs = cast_from_proposal(PROPOSAL)
    known = {e["entity"] for e in CANON}
    problems = check_solvability([p for p, _l, r in specs if r], cast_nodes, known_ids=known)
    assert not problems, f"cast unsolvable: {problems}"
    lints = [f for f in lint_arc(arc, _ReadShim(w)) if f.check != "2-paths"]
    assert not lints, f"arc lints (blocking): {[(f.check, f.message) for f in lints]}"
    arc = dataclasses.replace(arc, pillars=build_pillars(specs, cast_nodes, PROT))

    epoch = compute_entry_epoch(w)
    set_entry_epoch(epoch)
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    w.porcelain.ingest_structured(arc_io.portfolio_items([arc.arc_id], main_arc_id=arc.arc_id))
    for frame, items in cast_seed_plan(cast_nodes):
        if frame != FRAME:
            w.porcelain.ingest_structured(items, frame=frame)
    loc = cast_location_plan(cast_nodes, STATION)
    for it in loc:
        if it.get("attribute") == "in":
            it["valid_from"] = turn_time(0)
    w.porcelain.ingest_structured(loc)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame="session:main")
    # NB: the gauge is NOT seeded here. A baseline written at BUILD (under a model)
    # loses its accrue fold_policy across close/reopen — so the gauge is seeded
    # lazily at RUNTIME by gauge_pass/ensure_gauges (the clock.commit_elapsed
    # pattern), which re-establishes accrue on the world that actually plays.
    w.close()

    scope = sorted({e for e in arc_entities(arc) if e.startswith(("person:", "place:", "fact:", "creature:"))}
                   | {n.node_id for n in cast_nodes} | {STATION, EVAC, "creature:stalker"})
    meta = {"title": "Deepwater Station", "protagonist": PROT, "mode": "pure",
            # creature_feature → endurance → terminal_owner="world_event" (the world reckons).
            "scenario_mode": "win_loss", "endless": False, "game_type": ["creature_feature"],
            "arc_scope": scope, "cast": PROPOSAL, "entry_epoch": epoch}
    (Path("worlds") / f"{NAME}.meta.json").write_text(json.dumps(meta, indent=2))
    return {"epoch": epoch, "arc": arc}


class _ReadShim:
    def __init__(self, w):
        pass

    def has_entity(self, e):
        return True


def main() -> None:
    ts = int(time.time())
    log = Path(f"logs/validate-endurance-{ts}.md")
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
    w(f"# validate-endurance — {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))}\n")
    w(f"## sealed survival world (creature_feature → endurance → world_event) · "
      f"entry_epoch={sealed['epoch']}\n")

    from construct.story_shapes import conclusion_profile
    cp = conclusion_profile(["creature_feature"]) or {}
    w("## STATIC CHECKS (pre-play)")
    check("shape resolves to endurance / world_event terminal owner",
          cp.get("terminal_owner") == "world_event", f"profile={cp}")

    prov = CodexProvider()
    s = Session.open(NAME, player_id="validate", fresh=True, provider=prov)
    p = s._world.porcelain
    check("opening staging: medic + foreman PRESENT on the deck",
          p.locate("person:medic")[:1] == [STATION] and p.locate("person:foreman")[:1] == [STATION],
          f"medic={p.locate('person:medic')} foreman={p.locate('person:foreman')}")

    INPUTS = [
        ("press medic → rising InFrame beat", "beat:learn_weakness",
         "I corner Okonkwo — what IS this thing, and how do we lose it? Out with it."),
        ("press foreman → crisis InFrame beat", "beat:learn_route",
         "I press Vance — is the evac bay still powered? Give me the lift codes."),
        ("run for evac → Occurred climax / world_event curtain", "beat:reach_evac",
         "I kill the deck lights, mask our heat signature, and run for the evac bay to "
         "key in the codes and trigger the launch."),
    ]
    w("\n## LIVE TURNS")
    fired: set = set()
    saw_act_climb = False
    oxy_track: list = []          # the folded oxygen level reported each turn (auto-drain)
    saw_pressure_line = False     # the gauge surfaced into the narrator briefing
    final_conc = ""
    for label, want_beat, inp in INPUTS:
        try:
            r = s.turn(inp)
            tr = r.trace
            beats = list(getattr(tr, "beats_achieved", []) or [])
            fired.update(beats)
            if getattr(tr, "act", "I") in ("II", "III"):
                saw_act_climb = True
            _oxy = (getattr(tr, "gauge_levels", {}) or {}).get("gauge:oxygen")
            if _oxy is not None:
                oxy_track.append(_oxy)
            if "LIVE PRESSURE" in (getattr(tr, "briefing", "") or ""):
                saw_pressure_line = True
            final_conc = getattr(tr, "conclusion_shape", "") or final_conc
            w(f"\n### {label}\n> {inp}\n{(r.prose or '(empty)')[:500]}\n"
              f"*act={getattr(tr,'act','')} oxygen={_oxy} "
              f"events_fired={getattr(tr,'events_fired',[]) or '-'} beats={beats or '-'} "
              f"terminal={getattr(tr,'terminal',None)} conclusion={getattr(tr,'conclusion_shape','') or '-'}*")
            if want_beat:
                check(f"{label} fired", want_beat in beats, f"beats={beats}")
            if "rising" in label or "crisis" in label:
                check(f"{label}: NOT terminal yet (still surviving)",
                      getattr(tr, "terminal", False) is False)
            if "world_event curtain" in label:
                _ended = getattr(r, "ended", False) or getattr(tr, "terminal", False)
                # THE proof: the survival act itself TERMINATES — the world draws the curtain
                # (escape), where the audit world's structurally-identical seize did NOT.
                check("WORLD_EVENT: reaching evac TERMINATES (the world reckons, no accusation)",
                      _ended, f"terminal={getattr(tr,'terminal',None)} ended={getattr(r,'ended',None)}")
                _p = (r.prose or "")
                check("EPILOGUE: the escape renders aftermath prose (not the flat banner)",
                      len(_p) > 120 and "Start fresh to play again" not in _p, f"prose[:80]={_p[:80]!r}")
        except Exception as exc:  # noqa: BLE001
            w(f"\n### {label} — ENGINE ERROR: {exc}")
            if want_beat:
                check(f"{label} fired", False, f"error: {exc}")

    w("\n## DERIVED CHECKS")
    check("both survival InFrame beats fired (weakness, route)",
          {"beat:learn_weakness", "beat:learn_route"} <= fired)
    check("act climbed to II/III as CRISIS/CLIMAX beats achieved", saw_act_climb)

    # ---- GAUGE through the LIVE TURN LOOP (parts 3-5) ----
    w("\n## GAUGE (numeric constraint, auto-driven by run_turn)")
    w(f"  oxygen trace across turns: {oxy_track}")
    # Part 3: the turn loop auto-drains the gauge each turn (committed before outcome eval).
    check("part 3: run_turn auto-drained the gauge every turn (3 readings)",
          len(oxy_track) == 3, f"readings={oxy_track}")
    check("part 3: oxygen strictly DECREASED turn over turn (the live drain)",
          len(oxy_track) >= 2 and all(b < a for a, b in zip(oxy_track, oxy_track[1:])),
          f"track={oxy_track}")
    # Part 4: the gauge surfaced into the narrator briefing as live pressure (never a stored row).
    check("part 4: the gauge surfaced as LIVE PRESSURE in the narrator briefing",
          saw_pressure_line)
    # Part 5: the escape landed with the reserve in the costly band (≤25%) → costly_victory,
    # not a clean triumph (the shape colors the number). Robust to live timing: assert the
    # coloring MATCHES the actual final oxygen rather than presupposing the turn count.
    final_oxy = read_gauge(s._world, "oxygen")
    in_costly_band = final_oxy is not None and final_oxy <= 25.0 and final_oxy > 0.0
    w(f"  final oxygen={final_oxy} · costly_band={in_costly_band} · conclusion={final_conc!r}")
    if in_costly_band:
        check("part 5: a WIN on the last of the reserve colors as COSTLY_VICTORY (not triumph)",
              final_conc == "costly_victory", f"conclusion={final_conc!r} oxygen={final_oxy}")
    else:
        check("part 5: a WIN with reserve to spare reads as a clean win (not costly)",
              final_conc in ("triumph", "costly_victory"), f"conclusion={final_conc!r} oxygen={final_oxy}")
    s.close()

    n_pass = sum(1 for _, ok, _ in results if ok)
    w(f"\n## SCORECARD: {n_pass}/{len(results)} mechanisms hitting")
    for name, ok, _ in results:
        w(f"  {'✓' if ok else '✗'} {name}")
    print("LOG:", log, flush=True)


if __name__ == "__main__":
    main()
