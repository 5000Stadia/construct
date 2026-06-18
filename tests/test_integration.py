"""Integration: the host over a real pattern-buffer World — adapter,
arc round-trip, and one full turn through the DAG. Zero live model
calls: engine extraction via patternbuffer's StubModel, host cohorts
via StubProvider."""

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import PorcelainWorldReads
from construct.arc import io as arc_io
from construct.arc.conditions import InFrame, TurnsQuiet
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.provider import StubProvider
from construct.turnloop import run_turn

PLAYER = "person:player"
PLAYER_FRAME = f"knows:{PLAYER}"


@pytest.fixture
def world(tmp_path):
    # Classify prompts go to the rule classifier; extraction prompts pop
    # a dedicated FIFO — inline classification stays ON, so every row
    # (including session-frame event rows) gets its durability class.
    extractions: list[dict] = []
    rule = rule_classifier_fallback()

    def fallback(prompt: str, schema: dict):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        if prompt.startswith("Resolve an unestablished aspect"):
            return {"items": [{"value": "A worn stone chamber, shelf-lined, "
                                        "lit by one shuttered lamp."}]}
        if extractions:
            return extractions.pop(0)
        raise AssertionError(f"unscripted model call: {prompt[:80]!r}")

    stub = StubModel(fallback=fallback)
    w = World(tmp_path / "t.world", world_id="w:t", model=stub,
              stance="fiction", title="Integration Test World")
    w._extractions = extractions
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:study"},
        {"entity": "person:rival", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:rival", "attribute": "in", "value": "place:flat"},
        {"entity": "place:flat", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition",
         "timeless": True},
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
    ])
    w.ingest_structured([
        {"entity": PLAYER, "attribute": "in", "value": "place:study"},
    ], frame=PLAYER_FRAME)
    yield w
    w.close()


def make_arc() -> Arc:
    discover = Beat(
        "beat:discover", Phase.CLIMAX, Weight.REQUIRED,
        achievable_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"),
    )
    clock = Clock("clock:escalate", TurnsQuiet(4),
                  effects=({"entity": "event:pressure", "attribute": "kind",
                            "value": "pressure"},),
                  bound_to="beat:discover", rung=Rung.SURFACE)
    refusal = Clock("clock:refusal", TurnsQuiet(15),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape(
        "shape:main", "drive_inverted", (PLAYER, "drive:comfort", "drive:truth"),
        world_condition=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"),
        premise=InFrame("canon", "fact:secret", "culprit", "person:rival"),
        refusal_variant_id="shape:refused",
    )
    return Arc(
        arc_id="arc:main", protagonist=PLAYER, shape=shape,
        beats=(discover,), clocks=(clock,), refusal_clock=refusal,
        climax_ready_k=1, climax_ready_beats=("beat:discover",),
        phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                      Phase.CLIMAX: 2, Phase.FALLING: 2},
    )


def seed_arc(world, arc: Arc) -> None:
    world.porcelain.ingest_structured(
        arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    from construct.arc.executor import turn_time
    world.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(0)},
    ], frame="session:main")


class TestAdapter:
    def test_reads(self, world):
        reads = PorcelainWorldReads(world)
        assert reads.has_entity(PLAYER)
        assert not reads.has_entity("person:ghost")
        assert reads.state("fact:secret", "culprit") == "person:rival"
        assert reads.state("fact:secret", "smell") is None
        assert reads.location_chain(PLAYER)[0] == "place:study"
        assert reads.assertion_in_frame(PLAYER_FRAME, PLAYER, "in", "place:study")
        assert not reads.assertion_in_frame(PLAYER_FRAME, "fact:secret",
                                            "culprit", "person:rival")


class TestArcRoundTrip:
    def test_arc_persists_and_reconstructs(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        rebuilt = arc_io.arc_from_frame(PorcelainWorldReads(world))
        assert rebuilt.protagonist == arc.protagonist
        assert [b.beat_id for b in rebuilt.beats] == ["beat:discover"]
        assert rebuilt.beats[0].achievable_via == arc.beats[0].achievable_via
        assert rebuilt.refusal_clock.clock_id == "clock:refusal"
        assert rebuilt.shape.delta_type == "drive_inverted"
        assert rebuilt.phase_budget[Phase.SETUP] == 5

    def test_plot_frame_absent_from_canon(self, world):
        seed_arc(world, make_arc())
        snap = world.porcelain.snapshot([PLAYER, "fact:secret"])
        assert all(not f["entity"].startswith(("beat:", "clock:", "arc:", "shape:"))
                   for f in snap["facts"])


class TestFullTurn:
    def test_one_turn_through_the_dag(self, world):
        arc = make_arc()
        seed_arc(world, arc)

        # Engine extraction responses: the player's action discovers the
        # culprit (canon row, mirrored into knows:player), then the
        # post-render ingest extracts nothing new.
        world._extractions.append({"items": [
            {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
        ]})
        world._extractions.append({"items": []})

        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": []},                       # classify
            {"prose": "The ledger tells you everything: the rival did it."},
        ])

        result = run_turn(world, arc, provider, "I examine the ledger closely.", turn=1)

        assert "rival did it" in result.prose
        trace = result.trace
        assert trace.classified == "action"
        assert trace.beats_achieved == ["beat:discover"]   # beat fired this turn
        assert trace.briefing_frames == [PLAYER_FRAME]
        assert trace.concealment_audit == "clean"
        assert trace.irony_delta_size >= 0
        # Scene furnishing (letter 020 finding B): the study got invented
        # detail under canon, memoized, mirrored into the player frame.
        assert trace.furnished == ["place:study·description"]
        # The player-character boundary (letter 025): the narrate prompt
        # carries the hard identity constraint.
        narrate_prompt = provider.calls[-1][0]
        assert "THE PLAYER CHARACTER (hard constraint)" in narrate_prompt
        assert PLAYER in narrate_prompt
        st = world.porcelain.state("place:study", "description")
        assert st["status"] == "known" and "stone chamber" in st["fact"]["value"]
        assert world.porcelain.state(
            "place:study", "description", frame=PLAYER_FRAME)["status"] == "known"
        # the turn row landed in the session frame
        turns = world.porcelain.events(kind="turn", frame="session:main")
        assert len(turns) == 2  # turn_0 + this one
        # beat status persisted in plot:
        st = world.porcelain.state("beat:discover", "status", frame="plot:main")
        assert st["status"] == "known" and st["fact"]["value"] == "achieved"

    def test_furnish_is_memoized(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.extend([{"items": []}] * 4)
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": []}, {"prose": "You look around."},
            {"kind": "action", "moves_to": "", "requires": []}, {"prose": "You look around again."},
        ])
        r1 = run_turn(world, arc, provider, "I look around.", turn=1)
        r2 = run_turn(world, arc, provider, "I look around once more.", turn=2)
        assert r1.trace.furnished == ["place:study·description"]
        assert r2.trace.furnished == []  # memoized: stable on return

    def test_player_introduced_entities_are_licensed(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        # The post-render ingest re-extracts an entity the PLAYER named
        # ("the rampway") — licensed, not a leak (letter 011 finding 1).
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "obj:rampway", "attribute": "kind", "value": "ramp"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": []}, {"prose": "You take the rampway down."},
        ])
        result = run_turn(world, arc, provider, "I walk down the rampway.", turn=1)
        assert result.trace.concealment_audit == "clean"

    def test_ooc_short_circuits(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        provider = StubProvider([{"kind": "ooc", "moves_to": "", "requires": []}])
        result = run_turn(world, arc, provider, "save and quit please", turn=1)
        assert "out of character" in result.prose


def test_names_protagonist_guard():
    from construct.turnloop import names_protagonist
    assert names_protagonist("Allocation Officer Marn straightens.", "person:marn")
    assert names_protagonist("Marn's stare hardens", "person:marn")
    assert not names_protagonist("you set the slip down and walk off", "person:marn")
    assert not names_protagonist("the runner remarks on the harness", "person:marn")


def test_movement_relocates_player(world):
    arc = make_arc()
    seed_arc(world, arc)
    # "the flat" resolves deterministically (unique alias) via refer tier-1.
    world.ingest_structured([
        {"entity": "place:flat", "attribute": "kind", "value": "room",
         "timeless": True, "aliases": ["the flat"]},
    ])
    world._extractions.append({"items": []})   # player-action extraction
    world._extractions.append({"items": []})   # post-render extraction
    provider = StubProvider([
        {"kind": "action", "moves_to": "the flat", "requires": []},
        {"prose": "You cross to the flat."},
    ])
    run_turn(world, arc, provider, "I leave the study and go to the flat.", turn=1)
    assert world.porcelain.locate(PLAYER)[0] == "place:flat"  # superseded move


def test_adjudication_denies_phantom_key(world):
    arc = make_arc()
    seed_arc(world, arc)
    provider = StubProvider([
        {"kind": "action", "moves_to": "",
         "requires": ["the iron vault key"]},          # classify
        {"prose": "Your pocket holds no such key; the vault stays shut."},
    ])
    result = run_turn(world, arc, provider,
                      "I take the iron vault key from my pocket and unlock the vault.",
                      turn=1)
    assert result.trace.adjudication.startswith("denied:")
    assert "no such key" in result.prose
    # the phantom action never entered canon
    assert world.porcelain.state("obj:iron_vault_key", "kind")["status"] == "unknown"


def test_adjudication_allows_held_item(world):
    arc = make_arc()
    seed_arc(world, arc)
    world.ingest_structured([
        {"entity": "obj:brass_key", "attribute": "kind", "value": "key",
         "timeless": True, "aliases": ["the brass key"]},
        {"entity": "obj:brass_key", "attribute": "in", "value": PLAYER},
    ])
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": ["the brass key"]},
        {"prose": "You turn the brass key; the lock gives."},
    ])
    result = run_turn(world, arc, provider, "I unlock the chest with the brass key.",
                      turn=1)
    assert result.trace.adjudication == "allowed"
    assert "lock gives" in result.prose


def test_reveal_beat_correlates_at_achievement(world):
    """AKA-CORRELATION-V1 host consumption (element 3): a beat with `correlates`
    fires the reveal on achievement — the two entities become facets of one
    identity AS-OF that turn, without merging; before the reveal they read
    separate (the mystery holds)."""
    from dataclasses import replace

    from construct.arc.executor import beat_pass, turn_time

    p = world.porcelain
    # The figure the rival turns out to be — its own facts, separately tracked.
    world.ingest_structured([
        {"entity": "person:masked", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:masked", "attribute": "seen_at", "value": "place:flat"},
    ])
    # Make the reveal beat achievable: the trigger sits in the player frame.
    world.ingest_structured([
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
    ], frame=PLAYER_FRAME)
    reveal = Beat("beat:reveal", Phase.CLIMAX, Weight.REQUIRED,
                  achievable_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"),
                  correlates=("person:rival", "person:masked"))
    arc = replace(make_arc(), beats=(reveal,), climax_ready_beats=("beat:reveal",))
    seed_arc(world, arc)
    reads = PorcelainWorldReads(world)
    T = 3
    # Before the reveal fires: not correlated.
    assert p.correlations("person:rival", as_of=turn_time(T)) == []

    achieved, closed, revealed = beat_pass(world, arc, reads, turn=T)
    assert "beat:reveal" in achieved
    assert ("person:rival", "person:masked") in revealed

    # After (as-of the reveal): correlated, and the union reaches the facet's fact.
    assert "person:masked" in p.correlations("person:rival", as_of=turn_time(T))
    assert p.state_union("person:rival", "seen_at", as_of=turn_time(T))["status"] == "known"
    # As-of BEFORE the reveal's valid_from: no leak — the mystery stays intact.
    assert p.correlations("person:rival", as_of=turn_time(T) - 1) == []


def test_reveal_field_round_trips_through_arc_store(world):
    # The `correlates` field survives both arc persistence paths.
    from dataclasses import replace

    reveal = Beat("beat:reveal", Phase.CLIMAX, Weight.REQUIRED,
                  achievable_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"),
                  correlates=("person:rival", "person:masked"))
    arc = replace(make_arc(), beats=(reveal,), climax_ready_beats=("beat:reveal",))
    # cache path
    assert arc_io.arc_from_cache(arc_io.arc_to_cache(arc)).beats[0].correlates == \
        ("person:rival", "person:masked")
    # frame path
    seed_arc(world, arc)
    rebuilt = arc_io.arc_from_frame(PorcelainWorldReads(world))
    assert rebuilt.beats[0].correlates == ("person:rival", "person:masked")


def _drive_winning_turn(world, scenario_mode):
    """Run the culprit-discovery turn (satisfies world_condition → won) under a
    given scenario_mode; returns the TurnResult."""
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": [
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
    ]})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": []},
        {"prose": "You name the rival; the meter's truth is out and the settlement breathes."},
    ])
    return run_turn(world, arc, provider, "I examine the ledger.", turn=1,
                    scenario_mode=scenario_mode)


def test_win_loss_terminates_strictly(world):
    """WIN-LOSS §10 / founder ruling: in win_loss the outcome ends the scenario —
    trace.terminal + a one-time SESSION receipt readable by the transport."""
    from construct.turnloop import terminal_outcome

    result = _drive_winning_turn(world, scenario_mode="win_loss")
    assert result.trace.outcome == "won"
    assert result.trace.terminal is True
    assert terminal_outcome(PorcelainWorldReads(world)) == "won"


def test_endless_never_terminates(world):
    """Strictly win_loss: endless (and freeplay) reach the outcome but DON'T
    terminate — endless live fiction carries on."""
    from construct.turnloop import terminal_outcome

    result = _drive_winning_turn(world, scenario_mode="endless")
    assert result.trace.outcome == "won"          # classified
    assert result.trace.terminal is False          # but not terminal
    assert terminal_outcome(PorcelainWorldReads(world)) is None


def test_arc_outcome_won_lost_none_and_tiebreak(world):
    """WIN-LOSS §10 / Cx 063: arc_outcome is total, won-first. None when neither;
    lost when the refusal clock fired; won when the destination holds — even on
    the same tick the refusal fired (won wins the tie, protecting agency)."""
    from construct.arc.executor import arc_outcome

    arc = make_arc()
    reads = PorcelainWorldReads(world)
    # Neither destination nor failure terminal.
    assert arc_outcome(reads, arc) is None
    # Refusal clock fired → lost.
    world.ingest_structured([
        {"entity": "event:refusal_fired", "attribute": "kind", "value": "clock_fired"},
        {"entity": "event:refusal_fired", "attribute": "agent", "value": "clock:refusal",
         "value_type": "entity"},
    ], frame="plot:main")
    assert arc_outcome(reads, arc) == "lost"
    # Destination reached even with refusal fired → won (won wins the tie).
    world.ingest_structured([
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
    ], frame=PLAYER_FRAME)
    assert arc_outcome(reads, arc) == "won"
