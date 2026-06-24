"""Multi-arc portfolio + arc lifecycle (LIVING-WORLD-GENERATOR P1).

Covers: the `arc:*` registry round-trip (portfolio_items / portfolio_from_frame),
the lifecycle classification (won/lost/cancelled/incompletable/active) including
the hard rule `incompletable` is repair-exhausted and never first-unreachable,
the fallout canon consequence (with the membrane invariant: no derived
`dramatic_tension`/`known_by`/`active_thread_count` rows), and the turn-loop
wiring (a side arc dies without ending the scenario; the main arc still ends it).
"""

import json

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import PorcelainWorldReads
from construct.arc import io as arc_io
from construct.arc.conditions import InFrame, StateIs, TurnsQuiet
from construct.arc.executor import (
    PLOT,
    arc_lifecycle,
    emit_fallout,
    stored_lifecycle,
    turn_time,
)
from construct.arc.grammar import (
    Arc,
    Beat,
    Clock,
    ConclusionShape,
    Phase,
    Rung,
    Weight,
)
from construct.provider import StubProvider, task_of
from construct.turnloop import run_turn

PLAYER = "person:player"
PLAYER_FRAME = f"knows:{PLAYER}"
RIVAL = "person:rival"


def _main_arc() -> Arc:
    """The terminal-bearing main arc: the player names the culprit."""
    beat = Beat("beat:discover", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", RIVAL))
    refusal = Clock("clock:refusal", TurnsQuiet(15),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape(
        "shape:main", "drive_inverted", (PLAYER, "drive:comfort", "drive:truth"),
        world_condition=InFrame(PLAYER_FRAME, "fact:secret", "culprit", RIVAL),
        premise=InFrame("canon", "fact:secret", "culprit", RIVAL),
        refusal_variant_id="shape:refused")
    return Arc(arc_id="arc:main", protagonist=PLAYER, shape=shape, beats=(beat,),
               clocks=(), refusal_clock=refusal, climax_ready_k=1,
               climax_ready_beats=("beat:discover",),
               phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                             Phase.CLIMAX: 2, Phase.FALLING: 2})


def _side_arc() -> Arc:
    """An NPC-driven side arc: the rival means to bury the secret. Its required
    beat carries an `unreachable_if` so the path can be foreclosed; its refusal
    clock has the per-arc id (never `clock:refusal`) — the multi-arc collision fix."""
    beat = Beat("beat:bury", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=StateIs("fact:secret", "buried", "yes"),
                unreachable_if=StateIs("fact:secret", "exposed", "yes"))
    refusal = Clock("clock:refusal_side", TurnsQuiet(15),
                    effects=({"entity": "event:world_concludes_side",
                              "attribute": "kind", "value": "refusal_conclusion"},),
                    bound_to="arc:side", rung=Rung.REFUSAL)
    shape = ConclusionShape(
        "shape:side", "desire_at_cost", (RIVAL, "drive:greed", "drive:fear"),
        world_condition=StateIs("fact:secret", "buried", "yes"),
        premise=StateIs(RIVAL, "kind", "person"),
        refusal_variant_id="shape:refused")
    return Arc(arc_id="arc:side", protagonist=RIVAL, shape=shape, beats=(beat,),
               clocks=(), refusal_clock=refusal, climax_ready_k=1,
               climax_ready_beats=("beat:bury",),
               phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                             Phase.CLIMAX: 2, Phase.FALLING: 2})


def _world(path, *, side: bool = True) -> World:
    """A tiny two-arc world with the portfolio manifest written."""
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id="w:portfolio", model=StubModel(fallback=fallback),
              stance="fiction", title="Portfolio Test World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:study"},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": "fact:secret", "attribute": "culprit", "value": RIVAL},
        {"entity": RIVAL, "attribute": "kind", "value": "person", "timeless": True},
    ])
    main, sidearc = _main_arc(), _side_arc()
    arcs = [main, sidearc] if side else [main]
    items = []
    for a in arcs:
        items += arc_io.arc_to_items(a) + arc_io.index_items(a)
    items += arc_io.portfolio_items([a.arc_id for a in arcs], main_arc_id="arc:main")
    w.porcelain.ingest_structured(items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame="session:main")
    return w


def _fire_refusal(w: World, clock_id: str, turn: int = 1) -> None:
    """Inject a clock_fired event the way clock_pass does (the refusal backstop
    expiring), so ClockFired(clock_id) reads TRUE without 15 quiet turns."""
    fid = f"event:{clock_id.split(':', 1)[1]}_fired_{turn}"
    w.porcelain.ingest_structured([
        {"entity": fid, "attribute": "kind", "value": "clock_fired",
         "valid_from": turn_time(turn)},
        {"entity": fid, "attribute": "agent", "value": clock_id,
         "value_type": "entity", "valid_from": turn_time(turn)},
    ], frame=PLOT)


def _close_beat(w: World, beat_id: str, turn: int = 1) -> None:
    w.porcelain.ingest_structured([
        {"entity": beat_id, "attribute": "status", "value": "closed",
         "valid_from": turn_time(turn)},
    ], frame=PLOT)


# --- io: the registry round-trip ----------------------------------------

def test_portfolio_roundtrip(tmp_path):
    w = _world(tmp_path / "p.world")
    reads = PorcelainWorldReads(w)
    assert arc_io.arc_ids_from_frame(reads) == ["arc:main", "arc:side"]
    assert arc_io.main_arc_from_frame(reads) == "arc:main"
    arcs = arc_io.portfolio_from_frame(reads)
    by_id = {a.arc_id: a for a in arcs}
    assert set(by_id) == {"arc:main", "arc:side"}
    # The per-arc refusal id round-trips distinctly (the collision fix).
    assert by_id["arc:main"].refusal_clock.clock_id == "clock:refusal"
    assert by_id["arc:side"].refusal_clock.clock_id == "clock:refusal_side"
    assert by_id["arc:side"].beats[0].beat_id == "beat:bury"
    w.close()


def test_pillars_roundtrip_frame_and_cache(tmp_path):
    """Cx 027 blocker 1: Arc.pillars must persist through BOTH load paths. Build an arc
    with pillars (genuine + false Exprs), serialize to the frame and to the cache, and
    confirm both reconstruct the pillars intact (the conclusion-as-effect path depends on
    pillars surviving a reload)."""
    from construct.arc.grammar import Pillar
    main = _main_arc()
    pillars = (
        Pillar("pillar:motive", "the motive", required=True,
               genuine_via=InFrame(PLAYER_FRAME, "fact:motive", "known", "true"),
               false_via=InFrame(PLAYER_FRAME, "fact:motive", "blamed", "person:porter")),
        Pillar("pillar:mood", "ambience", required=False),  # no Exprs, optional
    )
    import dataclasses
    arc = dataclasses.replace(main, pillars=pillars)

    # --- frame round-trip ---
    w = World(tmp_path / "pil.world", world_id="w:pil",
              model=StubModel(fallback=rule_classifier_fallback), stance="fiction",
              title="Pillar World")
    w.ingestor.cursor.advance(1.0)
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    rebuilt = arc_io.arc_from_frame(PorcelainWorldReads(w))
    assert [p.pillar_id for p in rebuilt.pillars] == ["pillar:motive", "pillar:mood"]
    pm = rebuilt.pillars[0]
    assert pm.label == "the motive" and pm.required is True
    assert pm.genuine_via is not None and pm.false_via is not None
    assert rebuilt.pillars[1].required is False and rebuilt.pillars[1].genuine_via is None
    w.close()

    # --- cache round-trip ---
    cached = arc_io.arc_from_cache(arc_io.arc_to_cache(arc))
    assert [p.pillar_id for p in cached.pillars] == ["pillar:motive", "pillar:mood"]
    assert cached.pillars[0].false_via is not None
    assert cached.pillars[1].genuine_via is None and cached.pillars[1].required is False


def test_synth_refusal_is_per_arc(tmp_path):
    """The reconstruction fallback (`_synth_refusal`) mints a per-arc refusal id,
    so a side arc whose refusal rows drop never collides with the main arc's
    `clock:refusal` in the shared frame (Codex review finding)."""
    assert arc_io._synth_refusal("arc:main").clock_id == "clock:refusal"
    assert arc_io._synth_refusal("arc:side").clock_id == "clock:refusal_side"
    w = _world(tmp_path / "sr.world")
    w.close()


def test_single_arc_world_fails_open(tmp_path):
    """A world with no portfolio manifest is a single-arc portfolio (backward
    compat) — arc_ids_from_frame fails open to ['arc:main']."""
    w = _world(tmp_path / "s.world", side=False)
    reads = PorcelainWorldReads(w)
    assert arc_io.arc_ids_from_frame(reads) == ["arc:main"]
    assert [a.arc_id for a in arc_io.portfolio_from_frame(reads)] == ["arc:main"]
    w.close()


# --- executor: lifecycle classification ---------------------------------

def test_incompletable_never_first_unreachable(tmp_path):
    """A required beat closed while the refusal clock is still ARMED is NOT
    incompletable — the hard rule (PB letter 072 §5)."""
    w = _world(tmp_path / "i.world")
    side = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}["arc:side"]
    _close_beat(w, "beat:bury")  # required beat foreclosed, but no refusal yet
    assert arc_lifecycle(PorcelainWorldReads(w), side) == "active"
    w.close()


def test_incompletable_when_repair_exhausted(tmp_path):
    """Required beat closed AND the refusal backstop fired → incompletable."""
    w = _world(tmp_path / "i2.world")
    side = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}["arc:side"]
    _close_beat(w, "beat:bury")
    _fire_refusal(w, "clock:refusal_side")
    assert arc_lifecycle(PorcelainWorldReads(w), side) == "incompletable"
    w.close()


def test_lost_on_refusal_without_closed_beat(tmp_path):
    """Refusal fired with no foreclosed required beat → lost (a timeout), not
    incompletable."""
    w = _world(tmp_path / "l.world")
    side = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}["arc:side"]
    _fire_refusal(w, "clock:refusal_side")
    assert arc_lifecycle(PorcelainWorldReads(w), side) == "lost"
    w.close()


def test_won_when_world_condition_holds(tmp_path):
    w = _world(tmp_path / "won.world")
    side = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}["arc:side"]
    w.porcelain.ingest_structured(
        [{"entity": "fact:secret", "attribute": "buried", "value": "yes"}])
    assert arc_lifecycle(PorcelainWorldReads(w), side) == "won"
    w.close()


# --- executor: fallout + the membrane -----------------------------------

def test_fallout_writes_canon_consequence_with_membrane_held(tmp_path):
    w = _world(tmp_path / "f.world")
    side = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}["arc:side"]
    fo = emit_fallout(w, side, "incompletable", turn=1)
    p = w.porcelain
    # (1) a TRUE canon world-consequence row exists on the tension entity.
    st = p.state(fo.entity, fo.attribute)
    assert st["status"] == "known" and st["fact"]["value"] == fo.value
    assert fo.entity == RIVAL  # tension[0]
    # (2) the terminal event exists (the caused_by anchor / situation-lens hook).
    terms = [e.event_id for e in PorcelainWorldReads(w).events(kind="arc_terminal")]
    assert fo.term_id in terms
    # (3) MEMBRANE: the derived notions are NEVER written as canon rows.
    for forbidden in ("dramatic_tension", "known_by", "active_thread_count"):
        assert p.state(fo.entity, forbidden)["status"] != "known"
        assert p.state(side.arc_id, forbidden)["status"] != "known"
    # (4) a human directive is produced for the narrator (not stored).
    assert fo.directive and RIVAL not in fo.directive  # humanized, no raw id
    w.close()


# --- turn loop: per-arc wiring ------------------------------------------

class _StubTurnProvider(StubProvider):
    """Routes the run_turn cohorts (classify / narrate / nudge / npc) on prompt
    shape; defaults are permissive so a minimal world never wedges."""

    def __init__(self):
        super().__init__([])

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if prompt.startswith("Classify the lifetime"):
            return {"durability": "STATE", "confidence": 0.9}
        if prompt.startswith("Extract world-state"):
            return {"items": []}
        if prompt.startswith("Resolve an unestablished aspect"):
            return {"items": [{"value": "A lamplit study."}]}
        if task_of(prompt) == "cls":
            return {"kind": "action", "moves_to": "", "requires": []}
        if task_of(prompt) == "ndg":
            return {"thread": "", "directive": ""}
        if task_of(prompt) == "nar":
            return {"prose": "The study holds, lamplit and certain."}
        return {"items": []}


def test_side_arc_death_does_not_end_scenario(tmp_path):
    """A side arc reaching a terminal emits fallout + is acknowledged, but the
    scenario does NOT end (no arc_won/arc_lost receipt; ended stays False)."""
    w = _world(tmp_path / "t.world")
    main = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    side = main["arc:side"]
    # Pre-seed the side arc into the incompletable condition for this turn.
    _close_beat(w, "beat:bury")
    _fire_refusal(w, "clock:refusal_side")
    result = run_turn(w, main["arc:main"], _StubTurnProvider(),
                      "I search the study.", turn=1, scenario_mode="win_loss",
                      side_arcs=[side], generate=False)
    trace = result.trace
    assert trace.terminal is False  # the MAIN arc is still active
    assert "arc:side" in trace.arc_fallout
    # The side arc's terminal is persisted (so re-entry never re-fires).
    assert stored_lifecycle(PorcelainWorldReads(w), side) == "incompletable"
    # A fallout canon consequence was written; the scenario has no terminal receipt.
    from construct.turnloop import terminal_outcome
    assert terminal_outcome(PorcelainWorldReads(w)) is None
    assert PorcelainWorldReads(w).events(kind="arc_terminal")
    w.close()


def test_side_arc_terminal_fires_once(tmp_path):
    """Re-entry on an already-concluded side arc does not re-fire fallout."""
    w = _world(tmp_path / "once.world")
    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    side = by_id["arc:side"]
    _close_beat(w, "beat:bury")
    _fire_refusal(w, "clock:refusal_side")
    run_turn(w, by_id["arc:main"], _StubTurnProvider(), "I look.", turn=1,
             scenario_mode="win_loss", side_arcs=[side], generate=False)
    n_terms = len(PorcelainWorldReads(w).events(kind="arc_terminal"))
    r2 = run_turn(w, by_id["arc:main"], _StubTurnProvider(), "I look again.", turn=2,
                  scenario_mode="win_loss", side_arcs=[side], generate=False)
    assert r2.trace.arc_fallout == []  # already concluded — not re-reported
    assert len(PorcelainWorldReads(w).events(kind="arc_terminal")) == n_terms
    w.close()


def test_main_arc_terminal_still_ends_scenario(tmp_path):
    """Regression guard: the MAIN arc reaching its destination ends the win_loss
    scenario (the existing behavior, now in the portfolio loop)."""
    w = _world(tmp_path / "m.world")
    by_id = {a.arc_id: a for a in arc_io.portfolio_from_frame(PorcelainWorldReads(w))}
    # Satisfy the main world_condition (player knows the culprit).
    w.porcelain.ingest_structured(
        [{"entity": "fact:secret", "attribute": "culprit", "value": RIVAL}],
        frame=PLAYER_FRAME)
    result = run_turn(w, by_id["arc:main"], _StubTurnProvider(),
                      "I name the culprit.", turn=1, scenario_mode="win_loss",
                      side_arcs=[by_id["arc:side"]], generate=False)
    assert result.trace.terminal is True
    assert result.trace.outcome == "won"
    from construct.turnloop import terminal_outcome
    assert terminal_outcome(PorcelainWorldReads(w)) == "won"
    w.close()
