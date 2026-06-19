"""Integration: the host over a real pattern-buffer World — adapter,
arc round-trip, and one full turn through the DAG. Zero live model
calls: engine extraction via patternbuffer's StubModel, host cohorts
via StubProvider."""

from dataclasses import replace

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

    def test_json_blob_rows_are_pinned_literal(self):
        # Root-caused on a fresh anchor re-seal: a beat's achievable_via JSON
        # blob ({"op":"occurred",...}) was stored value_type=entity, so the
        # identity-reconcile pass dropped it and lost the beat. Every JSON-blob
        # plot row must be pinned `literal` so it's never classified/merged.
        from construct.arc.grammar import Pin
        arc = replace(make_arc(),
                      pins=(Pin("pin:p", "region", "place:x", "d", anchor="place:x"),))
        items = arc_io.arc_to_items(arc) + arc_io.index_items(arc)
        blob_attrs = {"achievable_via", "world_condition", "premise", "tension",
                      "phase_budget", "climax_ready_beats", "fires_when", "effects",
                      "beat_index", "clock_index", "pin_index"}
        seen = set()
        for it in items:
            if it["attribute"] in blob_attrs:
                seen.add(it["attribute"])
                assert it.get("value_type") == "literal", \
                    f"{it['attribute']} not pinned literal: {it.get('value_type')}"
        # the rows that actually bit us must be among those checked
        assert {"achievable_via", "beat_index"} <= seen

    def test_missing_beat_phase_loads_tolerantly(self, world):
        # A real defect surfaced by the loopback self-test: the sealed `anchor`
        # world had a beat with a None phase, and Phase(None) crashed the whole
        # load. arc_from_frame must fail OPEN (default + log), not brick the world.
        from construct.arc.io import _safe_phase, _safe_weight
        from construct.arc.grammar import Phase, Weight
        assert _safe_phase(None, "beat:x") is Phase.RISING
        assert _safe_phase("garbage", "beat:x") is Phase.RISING
        assert _safe_weight(None, "beat:x") is Weight.REQUIRED
        # end-to-end: a frame whose beat lost its phase row still reconstructs
        seed_arc(world, make_arc())
        world.porcelain.ingest_structured(
            [{"entity": "beat:discover", "attribute": "beat_phase", "value": None}],
            frame="plot:main")
        rebuilt = arc_io.arc_from_frame(PorcelainWorldReads(world))
        assert rebuilt.beats[0].phase is Phase.RISING  # defaulted, no crash

    def test_beat_without_condition_is_dropped_not_fatal(self, world):
        # The second anchor defect: a beat with no achievable_via row. It can't
        # be reconstructed, so it is dropped loudly — the load still succeeds.
        arc = make_arc()  # single beat:discover
        seed_arc(world, arc)
        # add a second beat to the index whose achievable_via never got written
        world.porcelain.ingest_structured([
            {"entity": "arc:main", "attribute": "beat_index",
             "value": '["beat:discover", "beat:ghost"]', "timeless": True},
            {"entity": "beat:ghost", "attribute": "beat_phase", "value": "rising"},
            {"entity": "beat:ghost", "attribute": "weight", "value": "required"},
        ], frame="plot:main")
        rebuilt = arc_io.arc_from_frame(PorcelainWorldReads(world))
        ids = [b.beat_id for b in rebuilt.beats]
        assert ids == ["beat:discover"]  # ghost dropped, discover survives

    def test_pins_round_trip_frame_and_cache(self, world):
        from construct.arc.grammar import Pin
        pins = (
            Pin("pin:law", "region", "place:study", "gravity is half here",
                subject_attribute="gravity", anchor="place:study", severity=0.5),
            Pin("pin:bomb", "temporal", "fact:secret", "a device counts down",
                valid_from=1.0, valid_to=9.0, severity=1.0),
            Pin("pin:clue", "social", "person:rival", "won't meet your eye",
                anchor="person:rival", severity=0.6, escalates=True),  # v2 foreshadow
        )
        arc = replace(make_arc(), pins=pins)
        seed_arc(world, arc)
        rebuilt = arc_io.arc_from_frame(PorcelainWorldReads(world))
        assert {p.pin_id for p in rebuilt.pins} == {"pin:law", "pin:bomb", "pin:clue"}
        law = next(p for p in rebuilt.pins if p.pin_id == "pin:law")
        assert law.anchor == "place:study" and law.severity == 0.5
        bomb = next(p for p in rebuilt.pins if p.pin_id == "pin:bomb")
        assert bomb.valid_from == 1.0 and bomb.valid_to == 9.0
        # the escalates flag round-trips (False default + True foreshadow)
        clue = next(p for p in rebuilt.pins if p.pin_id == "pin:clue")
        assert clue.escalates is True and law.escalates is False
        # cache path preserves them too
        cached = arc_io.arc_from_cache(arc_io.arc_to_cache(arc))
        assert {p.pin_id for p in cached.pins} == {"pin:law", "pin:bomb", "pin:clue"}
        assert next(p for p in cached.pins if p.pin_id == "pin:clue").escalates is True
        # no pins → empty tuple through both
        assert arc_io.arc_from_cache(arc_io.arc_to_cache(make_arc())).pins == ()

    def test_failure_when_round_trips_frame_and_cache(self, world):
        from construct.arc.conditions import Occurred
        arc = make_arc()
        arc = replace(arc, failure_when=Occurred("alarm_raised"))
        # frame
        seed_arc(world, arc)
        rebuilt = arc_io.arc_from_frame(PorcelainWorldReads(world))
        assert rebuilt.failure_when == Occurred("alarm_raised")
        # cache
        cached = arc_io.arc_from_cache(arc_io.arc_to_cache(arc))
        assert cached.failure_when == Occurred("alarm_raised")
        # absent failure_when stays None through both paths
        plain = arc_io.arc_from_cache(arc_io.arc_to_cache(make_arc()))
        assert plain.failure_when is None


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

    def test_region_pin_surfaces_in_briefing_without_leaking_metadata(self, world):
        from construct.arc.grammar import Pin
        # player is in place:study; a region pin anchored there is in scope
        arc = replace(make_arc(), pins=(
            Pin("pin:law", "region", "place:study", "the air here is thin and cold",
                subject_attribute="atmosphere", anchor="place:study", severity=0.5),))
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": []},
            {"prose": "You take in the cold study."},
        ])
        result = run_turn(world, arc, provider, "I look around.", turn=1)
        narrate_prompt = provider.calls[-1][0]
        # the directive is woven into the briefing as a PINS block...
        assert "PINNED AWARENESS" in narrate_prompt
        assert "the air here is thin and cold" in narrate_prompt
        # ...but the raw pin metadata (a plot:-frame entity) never leaks as a row
        assert "pin:law ·" not in narrate_prompt
        assert "pin:law" in [pid for pid, _kind, _sal in result.trace.pins]

    def test_no_pins_means_no_pins_block(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": []},
            {"prose": "Quiet."},
        ])
        result = run_turn(world, arc, provider, "I wait.", turn=1)
        assert "PINNED AWARENESS" not in provider.calls[-1][0]
        assert result.trace.pins == []

    def test_ingest_gate_quarantines_contradiction_promotes_new(self, world):
        # GATED-INGEST-COHORT: the narrator improvises freely, but a row that
        # OVERWRITES an established canon value it was NOT shown (a contradiction
        # of un-retrieved truth) is quarantined to proposed:, not committed;
        # genuinely NEW facts (good improv) still promote to canon.
        arc = make_arc()
        seed_arc(world, arc)
        # an established canon fact NOT mirrored to the player frame (so it is
        # not in the briefing the narrator saw — the residual read-gap case)
        world.ingest_structured([{"entity": "obj:ledger", "attribute": "seal",
                                  "value": "intact"}])
        world._extractions.append({"items": []})                      # player input
        world._extractions.append({"items": [                         # narrator prose
            {"entity": "obj:ledger", "attribute": "seal", "value": "broken"},  # contradiction
            {"entity": "obj:candle", "attribute": "kind", "value": "object"},  # new → promote
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": []},
            {"prose": "You study the desk; a candle gutters in the draft."},
        ])
        # scope holds only KNOWN entities; obj:candle is new — the gate picks it
        # up from what the narrator's prose touched, not from the initial scope.
        result = run_turn(world, arc, provider, "I study the desk.", turn=1,
                          scope=["obj:ledger", PLAYER, "place:study"])
        # contradiction quarantined: canon keeps the established value
        assert world.porcelain.state("obj:ledger", "seal")["fact"]["value"] == "intact"
        assert ("obj:ledger", "seal") in result.trace.contradictions
        # new fact promoted (good improv preserved)
        assert world.porcelain.state("obj:candle", "kind")["status"] == "known"

    def test_gate_quarantines_unlicensed_arc_key_promotes_ordinary(self, world):
        # GATED-INGEST slice 2 (momentous default-deny, option A): a NEW, UNLICENSED
        # narrator assertion of an ARC KEY (handing away the answer) is quarantined;
        # ordinary new facts still promote. A legitimately-discovered arc fact (in
        # the player frame → licensed) would promote — this is the unlicensed case.
        from construct.arc.conditions import InFrame
        from construct.arc.grammar import Beat, Phase, Weight
        arc = replace(make_arc(), beats=(
            Beat("beat:motive", Phase.CRISIS, Weight.REQUIRED,
                 achievable_via=InFrame(PLAYER_FRAME, "fact:motive", "reason", "greed")),
        ) + make_arc().beats)
        seed_arc(world, arc)
        world._extractions.append({"items": []})                      # player input
        world._extractions.append({"items": [                         # narrator prose
            {"entity": "fact:motive", "attribute": "reason", "value": "greed"},  # arc key → quarantine
            {"entity": "obj:lamp", "attribute": "kind", "value": "object"},      # ordinary → promote
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": []},
            {"prose": "You sense a motive; a lamp sputters in the corner."},
        ])
        result = run_turn(world, arc, provider, "I press her on why.", turn=1,
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        # the arc key is NOT canonized — the narrator can't hand the answer
        assert world.porcelain.state("fact:motive", "reason")["status"] != "known"
        assert ("fact:motive", "reason") in result.trace.quarantined
        # ordinary new fact still promotes (improv not strangled)
        assert world.porcelain.state("obj:lamp", "kind")["status"] == "known"

    def test_place_features_surface_in_briefing(self, world):
        # PLACE-FEATURE consumption (PB 070): a part_of sub-feature of the scene is
        # pulled into scope + listed for the narrator (its feel surfaces too).
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([
            {"entity": "place:study_alcove", "attribute": "kind", "value": "alcove",
             "timeless": True},
            {"entity": "place:study_alcove", "attribute": "part_of",
             "value": "place:study", "value_type": "entity"},
            {"entity": "place:study_alcove", "attribute": "feel",
             "value": "a shadowed recess"},
        ])
        world.ingest_structured([
            {"entity": "place:study_alcove", "attribute": "feel",
             "value": "a shadowed recess"}], frame=PLAYER_FRAME)
        assert world.porcelain.features("place:study") == ["place:study_alcove"]
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": []},
            {"prose": "You look about the study."},
        ])
        run_turn(world, arc, provider, "I look around.", turn=1)
        narrate_prompt = provider.calls[-1][0]
        assert "FEATURES OF THIS PLACE" in narrate_prompt
        assert "place:study_alcove" in narrate_prompt
        assert "shadowed recess" in narrate_prompt  # the feature's feel surfaced

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


def test_who_knows_inspect(tmp_path, monkeypatch):
    # WHO-KNOWS-INVERSE consumption (PB 071): which characters' frames hold a
    # fact — computed, not stored.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    from construct.game import _world, scenario_path, who_knows_inspect
    w = _world(scenario_path("demo"), "demo", stance="fiction", title="D")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([{"entity": "fact:secret", "attribute": "culprit",
                          "value": "person:rival", "timeless": True}])
    # the guard knows the culprit; the clerk does not
    w.ingest_structured([{"entity": "fact:secret", "attribute": "culprit",
                          "value": "person:rival"}], frame="knows:person:guard")
    w.close()
    r = who_knows_inspect("demo", "fact:secret", "culprit")
    assert "person:guard" in r["characters"]
    assert "person:clerk" not in r["characters"]


def test_arc_protected_keys():
    from construct.arc.executor import arc_protected_keys
    # the arc's load-bearing fact (the destination key) is protected; the gate
    # default-denies an unlicensed narrator assertion of it.
    assert ("fact:secret", "culprit") in arc_protected_keys(make_arc())


def test_author_flavor_cohort():
    # NARRATIVE-FLAVOR-INGEST: the cohort returns a world-level style voice + per
    # entity feels, and is shown the entity ids + digest.
    from construct.cohorts import author_flavor
    prov = StubProvider([{"style": "terse 1920s harbor-noir; rain-slick, cynical",
                          "feels": [{"entity": "person:rival", "feel": "too calm by half",
                                     "clue": True}]}])
    out = author_flavor(prov, "DIGEST: a drowned port.", ["person:rival", "place:study"])
    assert out["style"].startswith("terse") and out["feels"][0]["entity"] == "person:rival"
    prompt = prov.calls[0][0]
    assert "person:rival" in prompt and "WORLD DIGEST" in prompt
    assert prov.calls[0][2] == "main"  # authoring tier


def test_style_overlay_in_briefing(world):
    # The world-level voice overlay rides into the narrator's briefing every turn.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": []},
        {"prose": "You look."},
    ])
    run_turn(world, arc, provider, "I look around.", turn=1,
             style="terse 1920s harbor-noir; rain-slick, cynical")
    narrate_prompt = provider.calls[-1][0]
    assert "STYLE" in narrate_prompt and "harbor-noir" in narrate_prompt
    assert "never new facts" in narrate_prompt  # the voice-not-facts guardrail


def test_terminal_epilogue_names_cast_and_reveals(world):
    # NARRATIVE-FLAVOR-INGEST §3: a win_loss terminal renders a movie-epilogue —
    # names the cast for per-character fates + reveals the truth at the curtain.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": [
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}]})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": []},
        {"prose": "You name the rival; the meter's truth is out."},
    ])
    result = run_turn(world, arc, provider, "I name the culprit.", turn=1,
                      scenario_mode="win_loss")
    assert result.trace.terminal is True
    narrate_prompt = provider.calls[-1][0]
    assert "EPILOGUE" in narrate_prompt
    assert "person:rival" in narrate_prompt   # the cast (a fate for each)
    assert "THE TRUTH" in narrate_prompt       # concealment lifts at the curtain


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


def test_arc_outcome_lost_via_failure_when(world):
    """WIN-LOSS §10: an authored `failure_when` event ends the story in defeat
    even before the refusal clock — but loses the tie to a reached destination."""
    from construct.arc.conditions import Occurred
    from construct.arc.executor import arc_outcome

    arc = replace(make_arc(), failure_when=Occurred("alarm_raised"))
    reads = PorcelainWorldReads(world)
    assert arc_outcome(reads, arc) is None
    # The detection event enters canon (as the narrator would extract it) → lost.
    world.ingest_structured([
        {"entity": "event:caught", "attribute": "kind", "value": "alarm_raised"},
    ])
    assert arc_outcome(reads, arc) == "lost"
    # …but reaching the destination on the same reads still wins (agency).
    world.ingest_structured([
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
    ], frame=PLAYER_FRAME)
    assert arc_outcome(reads, arc) == "won"


class TestGoalStatement:
    """WIN-LOSS §10: the player-facing aim is leak-checked (fail-closed) and
    derived from the hidden destination — never a plot:/canon row."""

    def _proposal(self, goal):
        return {
            "goal_statement": goal,
            "beats": [
                {"kind": "player_learns", "entity": "fact:secret",
                 "attribute": "culprit", "value": "person:rival"},
            ],
        }

    def test_hidden_terms_cover_canon_and_beat_answers(self, world):
        from construct.game import _hidden_terms
        terms = _hidden_terms(world, self._proposal("anything"))
        # local-part tokens of canon ids + beat answer entity/value tokens
        assert {"rival", "secret", "study", "flat"} <= terms
        # the beat ATTRIBUTE ('culprit') is a legitimate genre word for the
        # aim ('name the culprit'), not a spoiler — only who/what is hidden
        assert "culprit" not in terms
        # short tokens dropped as noise
        assert "in" not in terms

    def test_safe_check_is_a_whole_word_disjoint(self):
        from construct.game import _goal_statement_safe
        forbidden = {"rival", "secret"}
        assert _goal_statement_safe("name the one who did it", forbidden)
        assert not _goal_statement_safe("expose the rival", forbidden)
        assert not _goal_statement_safe("", forbidden)
        # substring is NOT a match — whole-word tokens only
        assert _goal_statement_safe("rivalry is not the word", {"rival"})

    def test_player_goal_keeps_clean_and_drops_leaky(self, world):
        from construct.game import _player_goal, _DEFAULT_GOAL
        clean = "solve the mystery and name who is responsible"
        assert _player_goal(self._proposal(clean), world) == clean
        # leaks the culprit's id local-part → fail-closed to the default
        leaky = "prove that person:rival did it"
        assert _player_goal(self._proposal(leaky), world) == _DEFAULT_GOAL
        # empty/absent → default, never crashes
        assert _player_goal(self._proposal(""), world) == _DEFAULT_GOAL
