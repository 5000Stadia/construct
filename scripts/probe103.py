"""Task #103 live probe batch — three probes, real CodexProvider.

PROBE A: settlement vocabulary (village room vs cross-settlement journey)
PROBE B: wrapper-world edge (ship — rooms inside decks inside wrapper)
PROBE C: SECONDARY-register world laws (mythic realm with metaphysical law)

Usage:  .venv/bin/python scripts/probe103.py [--probe A|B|C]
        (no flag = run all three in sequence)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("probe103")

TS = int(time.time())
LOG_PATH = Path(f"logs/probe103-{TS}.md")
LOG_PATH.parent.mkdir(exist_ok=True)

_lines: list[str] = []


def _log(*parts: str) -> None:
    msg = " ".join(str(p) for p in parts)
    print(msg, flush=True)
    _lines.append(msg)


def _flush() -> None:
    LOG_PATH.write_text("\n".join(_lines) + "\n")


# ── helpers ─────────────────────────────────────────────────────────────────

def _trace_summary(trace) -> dict:
    """Pull the five fields we care about from a TurnTrace (or None)."""
    if trace is None:
        return {"deliberating": "N/A", "journey_est": "N/A",
                "time_advanced": "N/A", "movement_status": "N/A",
                "distance_unknown": "N/A"}
    return {
        "deliberating":     getattr(trace, "deliberating", ""),
        "journey_est":      getattr(trace, "journey_est", -1),
        "time_advanced":    getattr(trace, "time_advanced", 0),
        "movement_status":  getattr(trace, "movement_status", ""),
        "distance_unknown": getattr(trace, "distance_unknown", ""),
    }


def _do_turn(session, move: str, label: str) -> dict:
    _log(f"\n  > {label!r}")
    _log(f"    PLAYER: {move!r}")
    r = session.turn(move)
    t = _trace_summary(r.trace)
    _log(f"    PROSE (first 200): {(r.prose or '')[:200]!r}")
    _log(f"    trace.deliberating = {t['deliberating']!r}")
    _log(f"    trace.journey_est  = {t['journey_est']}")
    _log(f"    trace.time_advanced= {t['time_advanced']}")
    _log(f"    trace.movement_status = {t['movement_status']!r}")
    _log(f"    trace.distance_unknown= {t['distance_unknown']!r}")
    _log(f"    r.ok = {getattr(r, 'ok', True)}")
    _flush()
    return t


def _wipe(name: str) -> None:
    """Delete all scenario files (world + meta + play slot) for a fresh probe."""
    worlds = Path("worlds")
    for p in worlds.glob(f"{name}*"):
        p.unlink(missing_ok=True)


# ── PROBE A — settlement vocabulary ─────────────────────────────────────────

PROBE_A_NAME = "probe103_settlement"

def _author_probe_a() -> None:
    """
    Topology:
      place:region  (no parent)
        place:greendale        (village — parent: region)
          place:cottar_house   (house — parent: greendale)
            place:kitchen      (room — parent: cottar_house)  ← player starts here
          place:village_square (room — parent: greendale)
        place:aldmere          (distant town — parent: region; no shared parent with kitchen)
    """
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from construct.semantics import attribute_default
    from construct.arc import io as arc_io
    from construct.arc.conditions import StateIs, Quantity
    from construct.arc.executor import PLOT, SESSION, turn_time
    from construct.arc.grammar import Arc, Beat, Clock, Phase, Weight, ConclusionShape
    from construct.clock import ELAPSED_ENTITY, ELAPSED_ATTR

    _wipe(PROBE_A_NAME)
    path = Path(f"worlds/{PROBE_A_NAME}.world")
    meta_path = path.with_suffix(".meta.json")

    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id=f"w:{PROBE_A_NAME}",
              model=StubModel(fallback=fallback),
              stance="fiction", title="The Village & Aldmere",
              attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)

    # ── geography ──────────────────────────────────────────────────────────
    items = [
        # region (root)
        {"entity": "place:region",       "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:region",       "attribute": "name",        "value": "The Veld Region", "timeless": True},
        # greendale village (in region)
        {"entity": "place:greendale",    "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:greendale",    "attribute": "name",        "value": "Greendale village", "timeless": True},
        {"entity": "place:greendale",    "attribute": "in",          "value": "place:region", "timeless": True},
        # cottar house (in greendale)
        {"entity": "place:cottar_house", "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:cottar_house", "attribute": "name",        "value": "Cottar House", "timeless": True},
        {"entity": "place:cottar_house", "attribute": "in",          "value": "place:greendale", "timeless": True},
        # kitchen (in cottar_house) ← player start
        {"entity": "place:kitchen",      "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:kitchen",      "attribute": "name",        "value": "the kitchen", "timeless": True},
        {"entity": "place:kitchen",      "attribute": "in",          "value": "place:cottar_house", "timeless": True},
        {"entity": "place:kitchen",      "attribute": "description", "value": "A low-beamed kitchen smelling of woodsmoke.", "timeless": True},
        # village square (sibling to cottar_house inside greendale)
        {"entity": "place:village_square", "attribute": "kind",      "value": "place",   "timeless": True},
        {"entity": "place:village_square", "attribute": "name",      "value": "the village square", "timeless": True},
        {"entity": "place:village_square", "attribute": "in",        "value": "place:greendale", "timeless": True},
        # aldmere (distant settlement, also in region but no shared parent with kitchen/house)
        {"entity": "place:aldmere",      "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:aldmere",      "attribute": "name",        "value": "the town of Aldmere", "timeless": True},
        {"entity": "place:aldmere",      "attribute": "in",          "value": "place:region", "timeless": True},
        {"entity": "place:aldmere",      "attribute": "description", "value": "A market town two days' walk from Greendale.", "timeless": True},
        # player
        {"entity": "person:trav",        "attribute": "kind",        "value": "person",  "timeless": True},
        {"entity": "person:trav",        "attribute": "name",        "value": "Trav",    "timeless": True},
        {"entity": "person:trav",        "attribute": "in",          "value": "place:kitchen"},
        {"entity": "person:trav",        "attribute": "role",        "value": "a wanderer passing through", "timeless": True},
    ]
    w.ingest_structured(items)

    # ── arc with a time-based deadline so deliberation can fire ───────────
    # failure_when: elapsed >= 240 min (4 hours) — tight enough that a 2-day
    # journey to Aldmere (~2880 min) would clearly exceed the budget.
    # We use Quantity directly in the arc grammar.
    from construct.arc.conditions import TurnsQuiet
    from construct.arc.grammar import Rung
    deadline_expr = Quantity(ELAPSED_ENTITY, ELAPSED_ATTR, ">=", 240.0)

    refusal_clock = Clock(
        "clock:refusal_main",
        TurnsQuiet(20),
        effects=({"entity": "event:missed_deadline", "attribute": "kind",
                  "value": "refusal_conclusion",
                  "caused_by": "arc:main"},),
        bound_to="arc:main",
        rung=Rung.REFUSAL,
    )
    main_shape = ConclusionShape(
        "shape:main", "escape",
        ("person:trav", "drive:reach_aldmere", "fear:being_late"),
        world_condition=StateIs("person:trav", "role", "arrived"),
        premise=StateIs("person:trav", "kind", "person"),
        refusal_variant_id="shape:refused_main",
    )
    main_beat = Beat(
        "beat:arrive",
        Phase.CLIMAX,
        Weight.REQUIRED,
        achievable_via=StateIs("person:trav", "role", "arrived"),
    )
    main_arc = Arc(
        "arc:main", "person:trav", main_shape,
        (main_beat,), (),
        refusal_clock,
        1,                 # climax_ready_k
        ("beat:arrive",),  # climax_ready_beats
        {Phase.SETUP: 3, Phase.RISING: 4, Phase.CRISIS: 2,
         Phase.CLIMAX: 2, Phase.FALLING: 1},
        failure_when=deadline_expr,
    )

    arc_items = arc_io.arc_to_items(main_arc) + arc_io.index_items(main_arc)
    arc_items += arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main")
    w.porcelain.ingest_structured(arc_items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}],
        frame=SESSION,
    )
    w.close()

    meta_path.write_text(json.dumps({
        "title":          "The Village & Aldmere",
        "protagonist":    "person:trav",
        "stance":         "fiction",
        "mode":           "pure",
        "scenario_mode":  "win_loss",
        "style":          "Rural, grounded. Plain prose.",
        "intro":          ("You stand in Cottar House's kitchen in Greendale village. "
                           "The town of Aldmere waits two days' walk away — "
                           "and you must be there by nightfall."),
        "goal_statement": "reach Aldmere before the deadline",
        "arc_scope":      ["person:trav", "place:kitchen", "place:cottar_house",
                           "place:greendale", "place:aldmere", "place:region"],
        "main_arc":       "arc:main",
        "arc_ids":        ["arc:main"],
    }, indent=2))
    _log(f"  [author_probe_a] world written to {path}")


def run_probe_a() -> None:
    _log("\n" + "="*70)
    _log("PROBE A — settlement vocabulary edge")
    _log("="*70)
    _log("Topology: kitchen < cottar_house < greendale < region")
    _log("          aldmere < region  (no shared parent below region)")
    _log("Arc deadline: 240 min elapsed")

    try:
        _author_probe_a()
    except Exception as exc:
        _log(f"  [FAIL] world authoring failed: {exc}")
        _flush()
        return

    from construct.session import Session
    from construct.provider import CodexProvider

    try:
        s = Session.open(PROBE_A_NAME, provider=CodexProvider(),
                         player_id="probe103a", fresh=True)
    except Exception as exc:
        _log(f"  [FAIL] session open failed: {exc}")
        _flush()
        return

    # Turn 1: same-house step — must NOT hold for deliberation
    t1 = _do_turn(s, "I walk to the kitchen.", "T1: same-place no-op")
    delib1 = bool(t1["deliberating"])
    _log(f"  → deliberating: {delib1} (expected: False for same-room no-op)")

    # Turn 2: cross-settlement journey — SHOULD hold (or commit with huge est)
    t2 = _do_turn(s, "I set out for Aldmere.", "T2: cross-settlement journey")
    delib2 = bool(t2["deliberating"])
    _log(f"  → deliberating: {delib2} (expected: True — journey exceeds budget)")
    _log(f"  → journey_est: {t2['journey_est']} (the cost estimate, if held)")

    # Turn 3: accept the journey — estimate must be REUSED, not re-priced
    t3 = _do_turn(s, "Yes — I make the journey.", "T3: accept/confirm journey")
    _log(f"  → journey_est reused: {t3['journey_est']} (should equal T2 est if it was cached)")
    _log(f"  → time_advanced: {t3['time_advanced']}")

    s.close()

    # Verdict
    _log("\n  PROBE A VERDICT:")
    if not delib1 and delib2:
        _log("  EDGE HOLDS — T1 (local step) did not deliberate; T2 (cross-settlement) held.")
    elif not delib1 and not delib2:
        _log("  EDGE MISS — T2 (cross-settlement to Aldmere) did NOT trigger deliberation.")
        _log("  Either the deadline is not read, the farness logic sees them as near, or")
        _log("  the estimator priced the move under 240 min. Raw trace above.")
    elif delib1:
        _log("  EDGE MISS — T1 (same-room step) wrongly triggered deliberation.")
    _flush()


# ── PROBE B — wrapper-world edge ─────────────────────────────────────────────

PROBE_B_NAME = "probe103_wrapper"

def _author_probe_b() -> None:
    """
    Topology (wrapper ship):
      place:the_station  (wrapper — no parent)
        place:upper_deck   (deck A — in: the_station)
          place:bridge     (room — in: upper_deck) ← player start
          place:lab        (room — in: upper_deck)
        place:engine_deck  (deck B — in: the_station)
          place:engine_room (room — in: engine_deck)
    """
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from construct.semantics import attribute_default
    from construct.arc import io as arc_io
    from construct.arc.conditions import StateIs
    from construct.arc.executor import PLOT, SESSION, turn_time
    from construct.arc.conditions import TurnsQuiet
    from construct.arc.grammar import Arc, Beat, Clock, Phase, Weight, ConclusionShape, Rung

    _wipe(PROBE_B_NAME)
    path = Path(f"worlds/{PROBE_B_NAME}.world")
    meta_path = path.with_suffix(".meta.json")

    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id=f"w:{PROBE_B_NAME}",
              model=StubModel(fallback=fallback),
              stance="fiction", title="The Station",
              attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)

    items = [
        # wrapper
        {"entity": "place:the_station", "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:the_station", "attribute": "name",        "value": "Relay Station Seven", "timeless": True},
        {"entity": "place:the_station", "attribute": "description", "value": "A deep-space relay station, six decks of cold metal.", "timeless": True},
        # upper_deck
        {"entity": "place:upper_deck",  "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:upper_deck",  "attribute": "name",        "value": "upper deck", "timeless": True},
        {"entity": "place:upper_deck",  "attribute": "in",          "value": "place:the_station", "timeless": True},
        # bridge (in upper_deck) ← player start
        {"entity": "place:bridge",      "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:bridge",      "attribute": "name",        "value": "the bridge", "timeless": True},
        {"entity": "place:bridge",      "attribute": "in",          "value": "place:upper_deck", "timeless": True},
        {"entity": "place:bridge",      "attribute": "description", "value": "Consoles dark, the main viewscreen cracked.", "timeless": True},
        # lab (in upper_deck — sibling to bridge)
        {"entity": "place:lab",         "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:lab",         "attribute": "name",        "value": "the lab", "timeless": True},
        {"entity": "place:lab",         "attribute": "in",          "value": "place:upper_deck", "timeless": True},
        # engine_deck (sibling to upper_deck inside the_station)
        {"entity": "place:engine_deck", "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:engine_deck", "attribute": "name",        "value": "engine deck", "timeless": True},
        {"entity": "place:engine_deck", "attribute": "in",          "value": "place:the_station", "timeless": True},
        # engine_room (in engine_deck)
        {"entity": "place:engine_room", "attribute": "kind",        "value": "place",   "timeless": True},
        {"entity": "place:engine_room", "attribute": "name",        "value": "the engine room", "timeless": True},
        {"entity": "place:engine_room", "attribute": "in",          "value": "place:engine_deck", "timeless": True},
        {"entity": "place:engine_room", "attribute": "description", "value": "Massive coolant loops hum in the dark.", "timeless": True},
        # player
        {"entity": "person:eng",        "attribute": "kind",        "value": "person",  "timeless": True},
        {"entity": "person:eng",        "attribute": "name",        "value": "Asha",    "timeless": True},
        {"entity": "person:eng",        "attribute": "in",          "value": "place:bridge"},
        {"entity": "person:eng",        "attribute": "role",        "value": "the station's sole survivor", "timeless": True},
    ]
    w.ingest_structured(items)

    # Simple arc — no deadline (deliberation should NEVER fire without one)
    refusal_clock_b = Clock(
        "clock:refusal_main",
        TurnsQuiet(20),
        effects=({"entity": "event:station_lost", "attribute": "kind",
                  "value": "refusal_conclusion",
                  "caused_by": "arc:main"},),
        bound_to="arc:main",
        rung=Rung.REFUSAL,
    )
    main_shape = ConclusionShape(
        "shape:main", "escape",
        ("person:eng", "drive:restore_power", "fear:dying_alone"),
        world_condition=StateIs("person:eng", "role", "escaped"),
        premise=StateIs("person:eng", "kind", "person"),
        refusal_variant_id="shape:refused_main",
    )
    main_beat = Beat(
        "beat:power_on",
        Phase.CLIMAX,
        Weight.REQUIRED,
        achievable_via=StateIs("person:eng", "role", "escaped"),
    )
    main_arc = Arc(
        "arc:main", "person:eng", main_shape,
        (main_beat,), (),
        refusal_clock_b,
        1, ("beat:power_on",),
        {Phase.SETUP: 3, Phase.RISING: 4, Phase.CRISIS: 2,
         Phase.CLIMAX: 2, Phase.FALLING: 1},
    )

    arc_items = arc_io.arc_to_items(main_arc) + arc_io.index_items(main_arc)
    arc_items += arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main")
    w.porcelain.ingest_structured(arc_items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}],
        frame=SESSION,
    )
    w.close()

    meta_path.write_text(json.dumps({
        "title":          "The Station",
        "protagonist":    "person:eng",
        "stance":         "fiction",
        "mode":           "pure",
        "scenario_mode":  "win_loss",
        "style":          "Claustrophobic sci-fi, terse.",
        "intro":          "You are alone on the bridge of Relay Station Seven. The station is dying.",
        "goal_statement": "restore power and escape",
        "arc_scope":      ["person:eng", "place:bridge", "place:upper_deck",
                           "place:the_station", "place:engine_deck", "place:engine_room"],
        "main_arc":       "arc:main",
        "arc_ids":        ["arc:main"],
    }, indent=2))
    _log(f"  [author_probe_b] world written to {path}")


def run_probe_b() -> None:
    _log("\n" + "="*70)
    _log("PROBE B — wrapper-world edge")
    _log("="*70)
    _log("Topology: bridge < upper_deck < the_station")
    _log("          engine_room < engine_deck < the_station")
    _log("No arc deadline → deliberation must NEVER fire on any internal move.")

    try:
        _author_probe_b()
    except Exception as exc:
        _log(f"  [FAIL] world authoring failed: {exc}")
        _flush()
        return

    from construct.session import Session
    from construct.provider import CodexProvider

    try:
        s = Session.open(PROBE_B_NAME, provider=CodexProvider(),
                         player_id="probe103b", fresh=True)
    except Exception as exc:
        _log(f"  [FAIL] session open failed: {exc}")
        _flush()
        return

    # Turn 1: cross-deck (different immediate parent) — should NOT deliberate
    # (no deadline anyway); farness = UNKNOWN (different sibling chains)
    t1 = _do_turn(s, "I go down to the engine deck.", "T1: cross-deck (bridge → engine_deck area)")
    delib1 = bool(t1["deliberating"])
    _log(f"  → deliberating: {delib1} (expected: False — no deadline active)")
    _log(f"  → distance_unknown: {t1['distance_unknown']!r}")
    _log(f"  → movement_status: {t1['movement_status']!r}")

    # Turn 2: same-deck step — should be near (siblings share upper_deck)
    # The player may now be in engine_room or engine_deck; try to move to
    # the engine room (same deck)
    t2 = _do_turn(s, "I step into the engine room.", "T2: same-deck step")
    delib2 = bool(t2["deliberating"])
    _log(f"  → deliberating: {delib2} (expected: False)")
    _log(f"  → distance_unknown: {t2['distance_unknown']!r}")
    _log(f"  → movement_status: {t2['movement_status']!r}")

    s.close()

    _log("\n  PROBE B VERDICT:")
    if not delib1 and not delib2:
        near_cross_deck = not t1["distance_unknown"]
        _log(f"  No deliberation on either move (correct — no deadline).")
        _log(f"  T1 cross-deck distance_unknown: {t1['distance_unknown']!r}")
        _log(f"  T2 same-deck distance_unknown: {t2['distance_unknown']!r}")
        if t1["distance_unknown"] and not t2["distance_unknown"]:
            _log("  EDGE HOLDS — cross-deck correctly reads as UNKNOWN; same-deck as near.")
        elif not t1["distance_unknown"]:
            _log("  NOTE: cross-deck move also read as near (shared wrapper parent may have")
            _log("  matched at pre_chain[1] == _dchain[1] level). Check code: if both decks")
            _log("  share the_station at index 2, the sibling check (pre_chain[1]==_dchain[1])")
            _log("  fires at depth 1 (upper_deck vs engine_deck) — they differ, so nearness is")
            _log("  NOT wrongly triggered. distance_unknown should be set. INVESTIGATE.")
        elif t2["distance_unknown"]:
            _log("  EDGE MISS — same-deck step wrongly read as UNKNOWN distance.")
    else:
        _log(f"  EDGE MISS — unexpected deliberation fired (delib1={delib1}, delib2={delib2}).")
        _log("  (No deadline was authored; deliberation must be unreachable.)")
    _flush()


# ── PROBE C — SECONDARY-register world laws ───────────────────────────────────

PROBE_C_NAME = "probe103_mythic"

def run_probe_c() -> None:
    _log("\n" + "="*70)
    _log("PROBE C — SECONDARY-register world laws (mythic realm + metaphysical law)")
    _log("="*70)

    from construct.game import create_scenario_from_generated
    from construct.provider import CodexProvider

    _wipe(PROBE_C_NAME)

    SEED = (
        "An invented mythic realm where the dead lend their strength to the "
        "living through sworn bonds — high fantasy, its own cosmology. "
        "The Bond of the Shade is the governing force: a sworn compact between "
        "a living champion and a named ancestor shade. Strength flows freely "
        "while the bond holds; call on the dead WITHOUT a sworn bond and the "
        "shade's strength corrodes the caller, turning their own will against them. "
        "The player is a newly-sworn champion whose bond-shade is a legendary "
        "warrior — entering the world at the first test of the bond."
    )

    try:
        meta = create_scenario_from_generated(
            PROBE_C_NAME,
            CodexProvider(),
            seed=SEED,
            endless=False,
            play_as="the newly-sworn champion",
            reality_register="secondary",
            on_stage=lambda m: _log(f"  [STAGE] {m}"),
        )
    except Exception as exc:
        _log(f"  [FAIL] create_scenario_from_generated failed: {exc}")
        import traceback
        _log(traceback.format_exc())
        _flush()
        return

    _log(f"\n  BUILD COMPLETE: title={meta.get('title')!r}")
    _log(f"  reality_register: {meta.get('reality_register')!r}")
    laws = meta.get("laws") or []
    _log(f"  laws authored: {len(laws)}")
    for law in laws:
        _log(f"    LAW: {law.get('name')!r} [{law.get('register')}] {law.get('disclosure')!r}")
        _log(f"         rule: {law.get('rule', '')[:150]}")
        _log(f"         cost: {law.get('cost_limit', '')[:100]}")

    metaphysical_laws = [l for l in laws if l.get("register") == "metaphysical"]
    _log(f"\n  metaphysical laws present: {len(metaphysical_laws)} (expected ≥1 for SECONDARY+mythic)")

    # 3 live turns
    from construct.session import Session

    try:
        s = Session.open(PROBE_C_NAME, provider=CodexProvider(),
                         player_id="probe103c", fresh=True)
    except Exception as exc:
        _log(f"  [FAIL] session open failed: {exc}")
        _flush()
        return

    # T1: opening — does it ground an 'understood' law naturally?
    t1 = _do_turn(s, "I take stock of my bond and what it means.",
                  "T1: open + laws grounding")
    # T2: attempt something the law's cost forbids (unsworn call)
    t2 = _do_turn(s,
                  ("I reach out and call on the strength of the dead without "
                   "invoking my sworn bond — just a raw pull on their power."),
                  "T2: forbidden unsworn call — expect diegetic refusal/cost")
    # T3: ordinary in-law action (using the sworn bond correctly)
    t3 = _do_turn(s,
                  "I invoke my sworn bond with my ancestor shade, drawing on "
                  "their strength for the trial ahead.",
                  "T3: proper in-law bonded call — expect success")
    s.close()

    # Verdict
    _log("\n  PROBE C VERDICT:")
    has_meta = bool(metaphysical_laws)
    _log(f"  metaphysical law present: {has_meta}")
    _log(f"  T1 prose (law grounding): {(t1.get('prose', '') if isinstance(t1, dict) else '')[:200]!r}")
    _log("  T2/T3 qualitative assessment: check prose above for diegetic refusal (T2) vs success (T3).")
    if has_meta:
        _log("  SECONDARY register ALLOWS metaphysical — law-gate PASSES.")
    else:
        _log("  EDGE MISS: no metaphysical law authored despite SECONDARY+mythic seed.")
    _flush()


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", choices=["A", "B", "C"], default=None,
                    help="run a single probe (default: all)")
    args = ap.parse_args()

    _log(f"# Probe #103 batch — {TS}")
    _log(f"## Log path: {LOG_PATH}")

    if args.probe in (None, "A"):
        run_probe_a()
    if args.probe in (None, "B"):
        run_probe_b()
    if args.probe in (None, "C"):
        run_probe_c()

    _log(f"\n## Done. Log: {LOG_PATH.resolve()}")
    _flush()
    print(f"\nLog written to: {LOG_PATH.resolve()}", flush=True)


if __name__ == "__main__":
    main()
