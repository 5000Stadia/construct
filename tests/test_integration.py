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
from construct.arc.conditions import InFrame, Occurred, TurnsQuiet
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.provider import StubProvider, task_of
from construct.turnloop import run_turn

PLAYER = "person:player"
PLAYER_FRAME = f"knows:{PLAYER}"


#: A canned `estimate_elapsed` response (the per-turn diegetic-time cohort) for
#: multi-turn StubProvider queues that would otherwise misalign.
_EST = {"advance_minutes": 5, "jump_to_phase": "", "jump_days": 0, "reason": "a look"}


def _narrate_prompt(provider):
    """The most recent NARRATE/open-scene prompt — identified by 'narrator' (the
    per-turn diegetic-time `estimate_elapsed` cohort now also runs and would
    otherwise be `calls[-1]`)."""
    narrate = [c[0] for c in provider.calls if "narrator" in c[0].lower()]
    return narrate[-1] if narrate else provider.calls[-1][0]


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
    # Explicit-abandonment refusal (Cx 176/178) — the production shape; never a turn counter.
    refusal = Clock("clock:refusal", Occurred("event:abandoned"),
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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},                       # classify
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
        narrate_prompt = _narrate_prompt(provider)
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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You take in the cold study."},
        ])
        result = run_turn(world, arc, provider, "I look around.", turn=1)
        narrate_prompt = _narrate_prompt(provider)
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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "Quiet."},
        ])
        result = run_turn(world, arc, provider, "I wait.", turn=1)
        assert "PINNED AWARENESS" not in _narrate_prompt(provider)
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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You sense a motive; a lamp sputters in the corner."},
        ])
        result = run_turn(world, arc, provider, "I press her on why.", turn=1,
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        # the arc key is NOT canonized — the narrator can't hand the answer
        assert world.porcelain.state("fact:motive", "reason")["status"] != "known"
        assert ("fact:motive", "reason") in result.trace.quarantined
        # ordinary new fact still promotes (improv not strangled)
        assert world.porcelain.state("obj:lamp", "kind")["status"] == "known"

    def test_protected_same_value_restatement_is_quarantined_not_mirrored(self, world):
        # Cx 022 blocking #1 (the live leak): the mystery's answer is ALREADY canon
        # (fact:secret culprit = person:rival) but the player has NOT discovered it
        # (it is not in their knowledge frame). If the narrator merely RESTATES it
        # (SAME value), the old gate slipped it past the contradiction check and
        # promoted+MIRRORED it into knows:<player> — handing over the solution. The
        # strict protected gate quarantines it: canon unchanged, player still ignorant.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})                      # player input
        world._extractions.append({"items": [                         # narrator prose
            {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "It dawns on you: the rival is plainly behind it."},
        ])
        result = run_turn(world, arc, provider, "I muse aloud about who did it.", turn=1,
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        # canon is unchanged (it was already person:rival) ...
        assert world.porcelain.state("fact:secret", "culprit")["fact"]["value"] == "person:rival"
        # ... but the PLAYER never learned it — the leak vector (_mirror_rows into
        # the player frame) is closed, even for a same-value restatement.
        assert world.porcelain.state(
            "fact:secret", "culprit", frame=PLAYER_FRAME)["status"] != "known"
        assert ("fact:secret", "culprit") in result.trace.quarantined

    def test_protected_fact_already_earned_still_promotes(self, world):
        # The strict gate must NOT block LEGITIMATE discovery: a protected fact the
        # player has ALREADY earned (it is in their knowledge frame → briefing_keys)
        # is licensed, so the narrator restating it promotes normally — discovery and
        # its echoes are never strangled.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([  # the player has discovered it — it is in their frame
            {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
        ], frame=PLAYER_FRAME)
        world._extractions.append({"items": []})
        world._extractions.append({"items": [
            {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You lay out the case against the rival you already know is guilty."},
        ])
        result = run_turn(world, arc, provider, "I confront the rival.", turn=1,
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert ("fact:secret", "culprit") not in result.trace.quarantined

    def test_protected_question_is_deflected_not_improvised(self, world):
        # Cx 022 blocking #2: a QUESTION the player frame can't answer falls through
        # to the narrator to IMPROVISE — but if it reaches for the hidden answer,
        # improvisation could brush the secret. Such a question is DEFLECTED instead:
        # the briefing gets the WITHHELD directive, never the affirming improv one.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append(  # ask plan: unresolvable → no facts → falls through
            {"refer_targets": [], "keys": [], "wants_location": False})
        world._extractions.append({"items": []})                      # player input
        world._extractions.append({"items": []})                      # narrator prose
        provider = StubProvider([
            {"kind": "question", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "The clerk only shrugs; the record is silent on that."},
        ])
        result = run_turn(world, arc, provider, "Who is the culprit, really?", turn=1,
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        narrate_prompt = _narrate_prompt(provider)
        assert "WITHHELD QUESTION" in narrate_prompt
        assert "UNDER-DETERMINED QUESTION" not in narrate_prompt
        assert result.trace.adjudication.startswith("deflect")

    def test_ordinary_underdetermined_question_still_improvises(self, world):
        # The deflection must be SURGICAL: an innocent under-determined question (no
        # secret vocabulary) still gets the affirming improv directive, so the world
        # answers what a resident would plainly know (the founder's north star).
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append(
            {"refer_targets": [], "keys": [], "wants_location": False})
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "question", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "The nearest canteen is two corridors over, past the pumps."},
        ])
        result = run_turn(world, arc, provider, "Where's the closest place to eat?",
                          turn=1, scope=["fact:secret", PLAYER, "place:study"])
        narrate_prompt = _narrate_prompt(provider)
        assert "UNDER-DETERMINED QUESTION" in narrate_prompt
        assert "WITHHELD QUESTION" not in narrate_prompt

    def test_render_extraction_failure_does_not_sink_turn(self, world):
        # The play harness caught this: a SchemaViolation in the post-render prose
        # extraction was sinking already-delivered turns. The prose is the deliverable;
        # extraction is bookkeeping → it must FAIL-OPEN (ship prose, skip the commit).
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})  # player-input extraction
        real_ingest = world.porcelain.ingest

        def boom(text, **kw):
            if kw.get("frame") == "proposed:main":      # the render staging ingest
                raise RuntimeError("schema violation (simulated)")
            return real_ingest(text, **kw)

        world.porcelain.ingest = boom
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You read the worn ledger by lamplight."},
        ])
        result = run_turn(world, arc, provider, "I read the ledger.", turn=1)
        assert "worn ledger" in result.prose          # prose STILL ships
        assert any("post_extract" in d for d in result.trace.dropped_cohorts)  # logged fail-open
        world.porcelain.ingest = real_ingest

    def test_narrator_phantom_is_never_canonized(self, world):
        # Harness bug: the extraction minted a phantom `person:narrator` (from pronouns)
        # and located the ledger IN it, breaking adjudication. The gate drops any row that
        # IS the narrator phantom or locates something in it; ordinary facts still promote.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})                      # player input
        world._extractions.append({"items": [                         # render prose
            {"entity": "person:narrator", "attribute": "kind", "value": "person"},
            {"entity": "obj:ledger", "attribute": "in", "value": "person:narrator"},
            {"entity": "obj:lamp", "attribute": "kind", "value": "object"},  # ordinary
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You study the desk by lamplight."},
        ])
        result = run_turn(world, arc, provider, "I study the desk.", turn=1,
                          scope=["obj:ledger", PLAYER, "place:study"])
        assert world.porcelain.state("person:narrator", "kind")["status"] != "known"
        led = world.porcelain.state("obj:ledger", "in")
        assert led["status"] != "known" or led["fact"]["value"] != "person:narrator"
        assert world.porcelain.state("obj:lamp", "kind")["status"] == "known"  # ordinary promotes

    def test_player_takes_object_records_possession(self, world):
        # Founder's ledger bug: taking an object must record it HELD (obj.in = player), so
        # the adjudicator and narrator agree the player has it — not lose it to a phantom.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([
            {"entity": "obj:spoon", "attribute": "kind", "value": "object", "timeless": True},
            {"entity": "obj:spoon", "attribute": "in", "value": "place:study"},
            {"entity": "obj:spoon", "attribute": "name", "value": "brass spoon"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "takes": "the brass spoon"},
            {"prose": "You lift the brass spoon and tuck it away."},
        ])
        result = run_turn(world, arc, provider, "I pick up the brass spoon.", turn=1,
                          scope=["obj:spoon", PLAYER, "place:study"])
        assert result.trace.took == "obj:spoon"
        assert world.porcelain.state("obj:spoon", "in")["fact"]["value"] == PLAYER

    def test_conclusory_commitment_terminates_with_grade(self, world):
        # Phase 3 win-model: at the conclusory scene (climax-ready) the player's decisive
        # commitment is JUDGED once → a graded outcome that ENDS the story (win_loss) and
        # is recorded for the epilogue.
        from construct.arc.executor import turn_time
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured(  # climax-ready (earned) — beat achieved
            [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
              "valid_from": turn_time(3)}], frame="plot:main")
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "accuses the rival"},
            {"grade": "vindicated", "rationale": "matches the culprit"},   # judge_commitment
            {"prose": "You name the rival; the room stills."},
        ])
        result = run_turn(world, arc, provider, "I accuse the rival, citing the ledger.",
                          turn=5, scenario_mode="win_loss",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert result.trace.commitment_grade == "vindicated"
        assert result.trace.terminal is True and result.trace.outcome == "won"
        assert world.porcelain.state(f"claim:{PLAYER}", "grade")["fact"]["value"] == "vindicated"

    def test_wrong_commitment_still_terminates(self, world):
        # "Player may be wrong": a WRONG accusation still ENDS the story (the wrong person
        # goes down); the grade is wrong → outcome lost, the twist lands at the epilogue.
        from construct.arc.executor import turn_time
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured(
            [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
              "valid_from": turn_time(3)}], frame="plot:main")
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "accuses the clerk"},
            {"grade": "wrong", "rationale": "the clerk is not the culprit"},
            {"prose": "You name the clerk; the order is signed."},
        ])
        result = run_turn(world, arc, provider, "I accuse the clerk.", turn=5,
                          scenario_mode="win_loss",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert result.trace.commitment_grade == "wrong"
        assert result.trace.terminal is True and result.trace.outcome == "lost"
        # the epilogue plays the TWIST (Phase 4) on a wrong commitment
        prompt = _narrate_prompt(provider)
        assert "THE TWIST" in prompt and "Sherlock" in prompt

    def test_pillar_arc_concludes_as_coverage_effect(self, world):
        # CONCLUSION AS EFFECT (STORY-SHAPES §0a): a pillar-bearing arc concludes with a
        # coverage-driven OUTCOME_SHAPE on the trace, and the epilogue narrates the EFFECT
        # of the causes (not "you won/lost"). Sound coverage → triumph.
        import dataclasses
        from construct.arc.executor import turn_time
        from construct.arc.grammar import Pillar
        pillar = Pillar("pillar:culprit", "who did it", required=True,
                        genuine_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit",
                                            "person:rival"))
        arc = dataclasses.replace(make_arc(), pillars=(pillar,))
        seed_arc(world, arc)
        # climax-ready (earned) AND the genuine cause established in the player frame
        world.porcelain.ingest_structured(
            [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
              "valid_from": turn_time(3)}], frame="plot:main")
        world.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
            frame=PLAYER_FRAME)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([                       # NO judge stub — pillar grade is effect-derived
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "accuses the rival"},
            {"prose": "You name the rival; the truth lands."},
        ])
        result = run_turn(world, arc, provider, "I accuse the rival.", turn=5,
                          scenario_mode="win_loss",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert result.trace.terminal is True
        # the EFFECT of sound coverage — never a win/lose verdict; grade is the effect (slice 2)
        assert result.trace.conclusion_shape == "triumph"
        assert result.trace.commitment_grade == "vindicated"
        assert "judge_commitment:cheap" not in result.trace.cohort_calls
        assert result.trace.conclusion_basis
        prompt = _narrate_prompt(provider)
        assert "EFFECT" in prompt and "triumph" in prompt

    def test_commitment_bounces_on_incomplete_required_coverage(self, world):
        # COMMITMENT-AS-EFFECT slice 1 (Cx 105): a voluntary conclusive commitment with a REQUIRED
        # pillar still UNFILLED must BOUNCE — non-terminal, BEFORE the judge and any commitment rows.
        import dataclasses
        from construct.arc.grammar import Pillar
        pillar = Pillar("pillar:culprit", "who did it", required=True,
                        genuine_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"))
        arc = dataclasses.replace(make_arc(), pillars=(pillar,))
        seed_arc(world, arc)
        # NOTE: the genuine fact is NOT in the player frame → coverage incomplete (unfilled).
        world._extractions.extend([{"items": []}, {"items": []}])
        provider = StubProvider([                       # NO judge_commitment stub — bounce skips it
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "accuses the rival"},
            {"prose": "You point at the rival — but you have not shown how."},
        ])
        result = run_turn(world, arc, provider, "I accuse the rival.", turn=5,
                          scenario_mode="win_loss",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        # bounced: non-terminal, no judge, no grade, no commitment/terminal rows
        assert result.trace.commitment_bounced is True
        assert result.trace.terminal is False and not result.trace.outcome
        assert result.trace.commitment_grade == ""
        assert "judge_commitment:cheap" not in result.trace.cohort_calls
        rd = PorcelainWorldReads(world)
        assert rd.state("claim:person:player", "grade") is None     # no commitment row persisted
        assert not rd.events(kind="commitment", frame="session:main")
        # the narrator is told to render "not yet," never an ending
        assert "DOES NOT LAND" in _narrate_prompt(provider)

    def test_complete_coverage_still_lands_the_commitment(self, world):
        # Guard the gate doesn't block VALID commitments: with the required pillar covered
        # (complete + sound), the commitment LANDS — grade is the coverage EFFECT (vindicated),
        # NO LLM judge call (slice 2), terminal won.
        import dataclasses
        from construct.arc.grammar import Pillar
        pillar = Pillar("pillar:culprit", "who did it", required=True,
                        genuine_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"))
        arc = dataclasses.replace(make_arc(), pillars=(pillar,))
        seed_arc(world, arc)
        world.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
            frame=PLAYER_FRAME)  # coverage now complete + sound
        world._extractions.extend([{"items": []}, {"items": []}])
        provider = StubProvider([                       # NO judge stub — effect-derived grade
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "accuses the rival"},
            {"prose": "You name the rival; it holds."},
        ])
        result = run_turn(world, arc, provider, "I accuse the rival.", turn=5,
                          scenario_mode="win_loss",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert result.trace.commitment_bounced is False
        assert result.trace.terminal is True and result.trace.outcome == "won"
        assert result.trace.commitment_grade == "vindicated"
        assert "judge_commitment:cheap" not in result.trace.cohort_calls

    def test_sound_coverage_grades_vindicated_without_the_llm_judge(self, world):
        # COMMITMENT-AS-EFFECT slice 2: a SOUND solve grades 'vindicated' DETERMINISTICALLY from
        # coverage — no LLM judge call, and the persisted receipt agrees (no grade/conclusion seam).
        # (Supersedes the old Cx-093 "reconcile a wishy-washy judge grade" path — the judge is gone.)
        import dataclasses
        from construct.arc.grammar import Pillar
        pillar = Pillar("pillar:culprit", "who did it", required=True,
                        genuine_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"))
        arc = dataclasses.replace(make_arc(), pillars=(pillar,))
        seed_arc(world, arc)
        world.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
            frame=PLAYER_FRAME)
        world._extractions.extend([{"items": []}, {"items": []}])
        provider = StubProvider([                       # NO judge stub
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "names the killer"},
            {"prose": "You lay out the case; the rival is named."},
        ])
        result = run_turn(world, arc, provider, "I lay out the case and name the killer.", turn=5,
                          scenario_mode="win_loss",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert result.trace.conclusion_shape == "triumph"
        assert result.trace.commitment_grade == "vindicated"
        assert result.trace.outcome == "won" and result.trace.terminal is True
        assert "judge_commitment:cheap" not in result.trace.cohort_calls
        assert PorcelainWorldReads(world).state("claim:person:player", "grade") == "vindicated"

    def test_complete_but_false_coverage_lands_hollow_wrong(self, world):
        # COMMITMENT-AS-EFFECT slice 2 (Cx 107 hardening — a non-farce false-but-complete case):
        # the player built the case on a RED HERRING (a required pillar covered FALSE). Coverage is
        # complete (so it lands, not bounce) but UNSOUND → an unjust/mistaken conviction: grade
        # 'wrong', conclusion_shape wrong_case, terminal — no LLM judge call. (peril_redemption
        # polarity, NOT farce — false coverage is a wrong case here, not the comic engine.)
        import dataclasses
        from construct.arc.grammar import Pillar
        pillar = Pillar("pillar:culprit", "who did it", required=True,
                        genuine_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"),
                        false_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:clerk"))
        arc = dataclasses.replace(make_arc(), pillars=(pillar,))
        seed_arc(world, arc)
        # the player believes the RED HERRING (false coverage), not the genuine cause:
        world.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:clerk"}],
            frame=PLAYER_FRAME)
        world._extractions.extend([{"items": []}, {"items": []}])
        provider = StubProvider([                       # NO judge stub — effect-derived
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "accuses the clerk"},
            {"prose": "You name the clerk; the order is signed — but it will not hold."},
        ])
        result = run_turn(world, arc, provider, "I accuse the clerk.", turn=5,
                          scenario_mode="win_loss", cost_disposition="peril_redemption",
                          scope=["fact:secret", "person:clerk", "person:rival", PLAYER, "place:study"])
        assert result.trace.commitment_bounced is False        # complete → it lands
        assert result.trace.commitment_grade == "wrong"        # hollow/unjust (the wrong_case flag)
        assert result.trace.conclusion_shape == "bittersweet"  # the hollow-conviction epilogue shape
        assert result.trace.terminal is True and result.trace.outcome == "lost"
        assert "judge_commitment:cheap" not in result.trace.cohort_calls

    def test_hollow_landing_writes_culprit_at_large_canon_fallout(self, world):
        # COMMITMENT-AS-EFFECT slice 3 (Cx 105 #5): a hollow/unjust landing writes a CONCRETE canon
        # consequence (the real culprit walks free) — next-episode fuel — and the protagonist's frame
        # does NOT get it (the knowledge gap: they believe they convicted rightly).
        import dataclasses
        from construct.cast import CastNode
        from construct.arc.grammar import Pillar
        pillar = Pillar("pillar:culprit", "who did it", required=True,
                        genuine_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"),
                        false_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:clerk"))
        arc = dataclasses.replace(make_arc(), pillars=(pillar,))
        seed_arc(world, arc)
        world.porcelain.ingest_structured(   # the player believes the RED HERRING (false coverage)
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:clerk"}],
            frame=PLAYER_FRAME)
        # person:rival (the REAL culprit) is at place:flat in the fixture → not present (no npc_turn)
        cast = {"person:rival": CastNode("person:rival", "suspect", "the rival", is_culprit=True)}
        world._extractions.extend([{"items": []}, {"items": []}])
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "accuses the clerk"},
            {"prose": "You name the clerk; the real one slips away."},
        ])
        result = run_turn(world, arc, provider, "I accuse the clerk.", turn=5, cast=cast,
                          scenario_mode="win_loss", cost_disposition="peril_redemption",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert result.trace.terminal is True and result.trace.commitment_grade == "wrong"
        # the concrete canon consequence: the real culprit walks free (next-episode fuel)
        assert ("person:rival", "brought_to_justice", "false") in result.trace.main_fallout
        rd = PorcelainWorldReads(world)
        assert rd.state("person:rival", "brought_to_justice") == "false"  # CANON
        # the knowledge gap: the protagonist's frame does NOT hold it (they think they won)
        assert not rd.assertion_in_frame(PLAYER_FRAME, "person:rival", "brought_to_justice", "false")

    def test_farce_all_false_concludes_warm_no_twist(self, world):
        # Cx 027 blocker 3: a fully-live FARCE (every required pillar false-filled) is a WARM
        # comic triumph — NOT a costly comeuppance (false != cost here) and NOT a wrong-case
        # twist. cost_disposition='fail_forward' must reach `triumph` and suppress the twist.
        import dataclasses
        from construct.arc.executor import turn_time
        from construct.arc.grammar import Pillar
        mixup = Pillar("pillar:mixup", "the mistaken identity", required=True,
                       false_via=InFrame(PLAYER_FRAME, "fact:mixup", "live", "true"))
        arc = dataclasses.replace(make_arc(), pillars=(mixup,))
        seed_arc(world, arc)
        world.porcelain.ingest_structured(
            [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
              "valid_from": turn_time(3)}], frame="plot:main")
        # the comic engine is LIVE (the false-fill is success fuel, not a cost)
        world.porcelain.ingest_structured(
            [{"entity": "fact:mixup", "attribute": "live", "value": "true"}], frame=PLAYER_FRAME)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([                       # NO judge stub — effect-derived grade
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "plays along as the Duke"},
            {"prose": "The king roars with laughter; the pig is knighted."},
        ])
        result = run_turn(world, arc, provider, "I lean into the mix-up at dinner.", turn=5,
                          scenario_mode="win_loss", cost_disposition="fail_forward",
                          scope=["fact:mixup", PLAYER, "place:study"])
        assert result.trace.terminal is True
        assert result.trace.conclusion_shape == "triumph"  # warm, not costly_victory
        # fail_forward honored: a live comic blowup is effect-sound → vindicated, never wrong_case
        assert result.trace.commitment_grade == "vindicated"
        assert "judge_commitment:cheap" not in result.trace.cohort_calls
        prompt = _narrate_prompt(provider)
        assert "THE TWIST" not in prompt  # a triumphant farce must not trip the wrong-case twist

    def test_rocky_sound_coverage_plus_result_event_loss_live(self, world):
        # Cx 027 blocker 2 + the 131/132 CONSOLIDATION: Contest reads the LITERAL result ALONGSIDE
        # coverage — now a declared canon Occurred RESULT-EVENT (not a bespoke scoreboard entity).
        # Sound proof + a LOSS result-event must render costly_victory ("proved himself, lost the
        # decision"). This is the proof of the new `_literal_result` event-reader.
        import dataclasses
        from construct.arc.executor import turn_time
        from construct.arc.grammar import Pillar
        proof = Pillar("pillar:proof", "proved on the standard", required=True,
                       genuine_via=InFrame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival"))
        arc = dataclasses.replace(make_arc(), pillars=(proof,))
        seed_arc(world, arc)
        world.porcelain.ingest_structured(
            [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
              "valid_from": turn_time(3)}], frame="plot:main")
        world.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
            frame=PLAYER_FRAME)
        # the LITERAL result: a canon Occurred event of the arc's declared LOSS kind (the match was
        # lost) — ordinary canon, read via the event log, never the internal won/lost receipt.
        world.porcelain.ingest_structured(
            [{"entity": "event:bout_main", "attribute": "kind", "value": "bout_lost_main",
              "valid_from": turn_time(4)}])
        result_events = {"win": ("bout_won_main",), "loss": ("bout_lost_main",)}
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([                       # NO judge stub — effect-derived grade
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "goes the distance"},
            {"prose": "The bell rings; you are still standing."},
        ])
        result = run_turn(world, arc, provider, "I go the distance.", turn=5,
                          scenario_mode="win_loss", result_events=result_events,
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert result.trace.terminal is True
        assert result.trace.conclusion_shape == "costly_victory"  # proved himself, lost the bout
        assert "judge_commitment:cheap" not in result.trace.cohort_calls

    def test_interview_delivery_surfaces_a_clue_into_the_player_frame(self, world):
        # STORY-SHAPES §8: questioning a PRESENT cast member surfaces its authorized clue
        # into knows:<protagonist>, advancing pillar coverage — the live mechanism.
        from construct.cast import CastNode, Clue
        arc = make_arc()
        seed_arc(world, arc)
        # a fresh witness in the player's room (no prior `in` to conflict with), holding a
        # clue (the motive), revealable on questioning
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        ])
        cast = {"person:witness": CastNode("person:witness", "witness", "the witness",
                holds_clues=(
            Clue("clue:motive", "pillar:motive", ("fact:motive", "is", "debt"),
                 coverage_effect="genuine", reveal_condition="none"),))}
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": True, "intent": "deflect",
             "line_hint": ""},                                   # present witness: npc_turn (folded)
            {"prose": "The witness hesitates, then admits the debt that drove it."},
        ])
        result = run_turn(world, arc, provider, "I press the witness about money.", turn=2,
                          cast=cast, scope=["person:witness", PLAYER, "place:study"])
        assert "clue:motive" in result.trace.learned_clues
        # the fact is now in the player's knowledge frame
        assert PorcelainWorldReads(world).assertion_in_frame(
            PLAYER_FRAME, "fact:motive", "is", "debt")
        # the narrator was briefed to deliver it in character this turn
        prompt = _narrate_prompt(provider)
        assert "LEARNED THIS TURN" in prompt

    # ---- TOPIC-AWARE interview delivery (BEAT-DELIVERY half 2, Cx 125) -------------------
    def _witness_two_clues(self, world):
        """A present witness holding TWO fresh genuine clues: a decoy (authored FIRST) and
        the secret the make_arc CLIMAX beat gates on (authored SECOND). Returns the cast."""
        from construct.cast import CastNode, Clue
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        ])
        return {"person:witness": CastNode("person:witness", "witness", "the witness",
                holds_clues=(
            Clue("clue:decoy", "pillar:motive", ("fact:other", "is", "noise"),
                 coverage_effect="genuine", reveal_condition="none"),
            Clue("clue:secret", "pillar:motive", ("fact:secret", "culprit", "person:rival"),
                 coverage_effect="genuine", reveal_condition="none")))}

    def test_topic_aware_delivery_picks_the_questioned_clue_and_fires_the_beat(self, world):
        # The holder has two fresh eligible clues; the classifier's asks_targets picks the one
        # the question pursues (the secret, authored SECOND) — NOT the authored-first decoy — and
        # the CLIMAX beat gated on that fact fires the SAME turn.
        arc = make_arc(); seed_arc(world, arc)
        cast = self._witness_two_clues(world)
        world._extractions.append({"items": []}); world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "asks_targets": ["ask_1"]},   # ask_1 = the secret (2nd clue)
            {"acts": False, "action": "", "speaks": True, "intent": "deflect", "line_hint": ""},
            {"prose": "Pressed on who is behind it, the witness names the rival."},
        ])
        result = run_turn(world, arc, provider,
                          "I press the witness about who is really behind this.",
                          turn=2, cast=cast, scope=["person:witness", PLAYER, "place:study"])
        assert result.trace.learned_clues == ["clue:secret"]   # questioned one, not the decoy
        R = PorcelainWorldReads(world)
        assert R.assertion_in_frame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival")
        assert not R.assertion_in_frame(PLAYER_FRAME, "fact:other", "is", "noise")
        assert "beat:discover" in result.trace.beats_achieved  # the gated beat fired this turn

    def test_empty_asks_targets_keeps_legacy_authored_order(self, world):
        # No asks_targets (generic question / old schema) → today's first-by-rank behavior:
        # the authored-FIRST clue (the decoy) is delivered, unchanged.
        arc = make_arc(); seed_arc(world, arc)
        cast = self._witness_two_clues(world)
        world._extractions.append({"items": []}); world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},                               # no asks_targets at all
            {"acts": False, "action": "", "speaks": True, "intent": "deflect", "line_hint": ""},
            {"prose": "The witness offers what they will."},
        ])
        result = run_turn(world, arc, provider, "I talk to the witness.",
                          turn=2, cast=cast, scope=["person:witness", PLAYER, "place:study"])
        assert result.trace.learned_clues == ["clue:decoy"]    # legacy authored-first, unchanged

    def test_pressure_gate_stays_authoritative_over_asks_targets(self, world):
        # The classifier may TARGET a pressure-gated clue, but a non-pressing interaction must
        # not deliver it — the deterministic reveal gate stays authoritative (Cx 125 blocker 1).
        from construct.cast import CastNode, Clue
        arc = make_arc(); seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        ])
        cast = {"person:witness": CastNode("person:witness", "witness", "the witness",
                holds_clues=(
            Clue("clue:secret", "pillar:motive", ("fact:secret", "culprit", "person:rival"),
                 coverage_effect="genuine", reveal_condition="pressure"),))}
        world._extractions.append({"items": []}); world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "asks_targets": ["ask_0"]},    # targets the pressure clue...
            {"acts": False, "action": "", "speaks": True, "intent": "deflect", "line_hint": ""},
            {"prose": "You exchange pleasantries with the witness."},
        ])
        result = run_turn(world, arc, provider, "I nod politely and settle in.",  # NOT pressing
                          turn=2, cast=cast, scope=["person:witness", PLAYER, "place:study"])
        assert result.trace.learned_clues == []                # gate withheld it
        assert "beat:discover" not in result.trace.beats_achieved

    def test_already_learned_target_falls_back_to_next_fresh(self, world):
        # If the targeted clue is already in the player frame, it's filtered by the gate; the
        # selection then falls back to the next fresh eligible clue (Cx 125: skip learned → next).
        from construct.cast import CastNode, Clue
        arc = make_arc(); seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        ])
        # pre-seed the FIRST clue's fact into the player frame (already learned)
        world.porcelain.ingest_structured(
            [{"entity": "fact:seen", "attribute": "is", "value": "prior"}], frame=PLAYER_FRAME)
        cast = {"person:witness": CastNode("person:witness", "witness", "the witness",
                holds_clues=(
            Clue("clue:seen", "pillar:motive", ("fact:seen", "is", "prior"),
                 coverage_effect="genuine", reveal_condition="none"),
            Clue("clue:secret", "pillar:motive", ("fact:secret", "culprit", "person:rival"),
                 coverage_effect="genuine", reveal_condition="none")))}
        world._extractions.append({"items": []}); world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "asks_targets": ["ask_0"]},    # targets the ALREADY-LEARNED clue
            {"acts": False, "action": "", "speaks": True, "intent": "deflect", "line_hint": ""},
            {"prose": "The witness goes on."},
        ])
        result = run_turn(world, arc, provider, "I ask the witness about what they saw.",
                          turn=2, cast=cast, scope=["person:witness", PLAYER, "place:study"])
        assert result.trace.learned_clues == ["clue:secret"]   # skipped learned → next fresh

    def test_move_and_ask_in_one_turn_falls_back_to_legacy_order(self, world):
        # v1 semantics (Cx 125): candidates are assembled from the ENTRY scene, before movement.
        # A same-turn "go to X and ask them" therefore cannot be topic-steered — the moved-to
        # holder wasn't a candidate — so delivery falls back to authored order. Documented, not
        # accidental: even with asks_targets set, the authored-FIRST clue is delivered.
        from construct.cast import CastNode, Clue
        arc = make_arc(); seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:pantry", "attribute": "kind", "value": "room",
             "timeless": True, "aliases": ["the pantry"]},
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:pantry"},
        ])
        cast = {"person:witness": CastNode("person:witness", "witness", "the witness",
                holds_clues=(
            Clue("clue:decoy", "pillar:motive", ("fact:other", "is", "noise"),
                 coverage_effect="genuine", reveal_condition="none"),
            Clue("clue:secret", "pillar:motive", ("fact:secret", "culprit", "person:rival"),
                 coverage_effect="genuine", reveal_condition="none")))}
        world._extractions.append({"items": []}); world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the pantry", "requires": [], "needs_test": False,
             "uncertain_of": "", "asks_targets": ["ask_1"]},    # would WANT the secret...
            {"acts": False, "action": "", "speaks": True, "intent": "deflect", "line_hint": ""},
            {"prose": "You find the witness in the pantry; they say their piece."},
        ])
        result = run_turn(world, arc, provider,
                          "I go to the pantry and ask the witness who is behind this.",
                          turn=2, cast=cast,
                          scope=["person:witness", PLAYER, "place:study", "place:pantry"])
        # moved + delivered, but NOT topic-steered (the moved-to holder had no entry candidate)
        assert world.porcelain.locate(PLAYER)[0] == "place:pantry"
        assert result.trace.learned_clues == ["clue:decoy"]    # legacy authored-first

    def test_npc_turn_returns_combined_shape(self):
        # TURN-LATENCY Lever 4: the folded cohort returns the union of the old
        # npc_world_action + npc_intent shapes in a single call.
        from construct import cohorts
        provider = StubProvider([
            {"acts": True, "action": "the witness rises", "speaks": True,
             "intent": "warn the detective", "line_hint": "clipped"},
        ])
        out = cohorts.npc_turn(provider, "person:witness", "{}", "{}", "person:pc")
        assert set(out) == {"acts", "action", "speaks", "intent", "line_hint"}
        assert out["acts"] is True and out["action"] == "the witness rises"
        assert out["speaks"] is True and out["intent"] == "warn the detective"

    def test_present_npc_yields_exactly_one_npc_turn_call(self, world):
        # TURN-LATENCY Lever 4: a present NPC produces ONE npc_turn:<id> cohort call
        # (was npc_action:<id> + npc_intent:<id>), and the speak-intent still reaches
        # the narrator briefing.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": True, "intent": "deflect",
             "line_hint": "wary"},                               # the single folded call
            {"prose": "The witness eyes you warily."},
        ])
        result = run_turn(world, arc, provider, "I look at the witness.", turn=2,
                          scope=["person:witness", PLAYER, "place:study"])
        npc_calls = [c for c in result.trace.cohort_calls if c.startswith("npc_")]
        assert npc_calls == ["npc_turn:person:witness:cheap"]
        # present-cast briefing names the NPC (de-leaked id) + their want (Cx 091 #1)
        assert "witness: wants deflect" in _narrate_prompt(provider)

    def test_silent_present_npc_is_still_named_in_the_briefing(self, world):
        # Cx 091 #1 (continuity): a present NPC who does NOT speak this turn must still be named
        # as present, so the narrator can't erase them ("the doctor is the only one here") against
        # the cold open. Two present people; one speaks, one is silent — BOTH appear.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "name", "value": "Hobbes", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
            {"entity": "person:silent", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:silent", "attribute": "name", "value": "Julian", "timeless": True},
            {"entity": "person:silent", "attribute": "in", "value": "place:study"},
        ])
        world._extractions.extend([{"items": []}, {"items": []}])
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": True, "intent": "warn you",
             "line_hint": ""},                                   # person:silent (1st in scope order)
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},  # witness silent
            {"prose": "The study holds its breath."},
        ])
        result = run_turn(world, arc, provider, "I survey the study.", turn=2,
                          scope=["person:silent", "person:witness", PLAYER, "place:study"])
        prompt = _narrate_prompt(provider)
        # BOTH present people are named — the silent one explicitly kept in the scene
        assert "Hobbes" in prompt and "Julian" in prompt
        assert "present, silent for now" in prompt  # the silent-NPC continuity guard fired

    def test_examine_delivery_surfaces_an_object_clue_into_the_player_frame(self, world):
        # EXAMINE-CHANNEL.md: closely INSPECTING a present clue-bearing OBJECT surfaces its
        # evidentiary fact into knows:<protagonist> — the EXAMINE-channel analogue of ASK.
        from construct.cast import CastNode, Clue, cast_seed_plan
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "obj:bag", "attribute": "kind", "value": "object", "timeless": True},
            {"entity": "obj:bag", "attribute": "in", "value": "place:study"},
        ])
        cast = {"obj:bag": CastNode("obj:bag", "evidence", "the doctor's bag", holds_clues=(
            Clue("clue:vial", "pillar:means", ("fact:means", "is", "vial_missing"),
                 coverage_effect="genuine", reveal_condition="scrutiny"),))}
        # NO knows:obj frame is ever seeded for an object holder (Cx 073)
        assert all(not f.startswith("knows:obj") for f, _ in cast_seed_plan(tuple(cast.values())))
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You open the bag; a vial slot sits conspicuously empty."},
        ])
        result = run_turn(world, arc, provider, "I examine the doctor's bag closely.", turn=1,
                          cast=cast, scope=["obj:bag", PLAYER, "place:study"])
        assert "clue:vial" in result.trace.learned_clues
        assert PorcelainWorldReads(world).assertion_in_frame(
            PLAYER_FRAME, "fact:means", "is", "vial_missing")

    def test_is_scrutiny_catches_look_closely(self):
        # Cx 083: "look closely/carefully at X" is scrutiny (spec named it), but a bare glance is not.
        from construct.turnloop import _is_scrutiny
        assert _is_scrutiny("i examine the doctor's bag closely")
        assert _is_scrutiny("i inspect the bag")
        assert _is_scrutiny("i look closely at the bag")
        assert _is_scrutiny("i study the bag carefully")
        assert not _is_scrutiny("i look around the room")
        assert not _is_scrutiny("i notice the bag on the table")

    def test_examine_glance_and_plain_object_surface_nothing(self, world):
        # A GLANCE (no inspect verb) does not earn the scrutiny clue; and a plain object that
        # isn't a cast node yields no pillar fact (the narrator renders it as atmosphere).
        from construct.cast import CastNode, Clue
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "obj:bag", "attribute": "kind", "value": "object", "timeless": True},
            {"entity": "obj:bag", "attribute": "in", "value": "place:study"},
        ])
        cast = {"obj:bag": CastNode("obj:bag", "evidence", "the doctor's bag", holds_clues=(
            Clue("clue:vial", "pillar:means", ("fact:means", "is", "vial_missing"),
                 reveal_condition="scrutiny"),))}
        world._extractions.extend([{"items": []}, {"items": []}])
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "Your eyes pass over the table and the bag upon it."},
        ])
        # a glance ("notice"/"see") has no examine verb → not scrutiny → no delivery
        r = run_turn(world, arc, provider, "I take in the room and notice the bag on the table.",
                     turn=1, cast=cast, scope=["obj:bag", PLAYER, "place:study"])
        assert "clue:vial" not in r.trace.learned_clues
        assert not PorcelainWorldReads(world).assertion_in_frame(
            PLAYER_FRAME, "fact:means", "is", "vial_missing")

    def test_discovery_writes_offscene_whereabouts_and_briefs_the_lead(self, world):
        # INVESTIGATION-SHAPE.md §3c: a delivered clue that NAMES an off-scene suspect makes
        # their whereabouts player-known (frame entitlement) and briefs the lead, so the
        # player can go visit them. The off-scene suspect's place is canon (layer 1).
        from construct.cast import CastNode, Clue
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        ])
        # the present witness holds a clue NAMING the off-scene suspect (their id is the fact's
        # entity); the off-scene node carries their canonical place.
        cast = {
            "person:witness": CastNode("person:witness", "witness", "the witness",
                presence="at_scene", first_witness=True, holds_clues=(
                Clue("clue:lead", "pillar:motive", ("person:bell", "seen_near", "place:study"),
                     coverage_effect="genuine", reveal_condition="none"),)),
            "person:bell": CastNode("person:bell", "suspect", "the captain",
                presence="offscene", location="place:bell_cottage", is_culprit=True),
        }
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": True, "intent": "tell",
             "line_hint": ""},                                   # witness npc_turn (folded)
            {"prose": "The witness says Bell was seen near here, then nods toward his cottage."},
        ])
        result = run_turn(world, arc, provider, "I ask the witness who else was about.", turn=2,
                          cast=cast, scope=["person:witness", PLAYER, "place:study"])
        # the off-scene suspect's whereabouts is now in the player's frame (entitlement)
        assert "person:bell" in result.trace.discovered
        assert PorcelainWorldReads(world).assertion_in_frame(
            PLAYER_FRAME, "person:bell", "whereabouts", "place:bell_cottage")
        # and the narrator was briefed to offer the lead
        assert "A LEAD OPENS" in _narrate_prompt(provider)

    def test_weave_governance_peppers_a_hooked_card(self, world):
        # CARD-WEAVING.md / Cx 039: with an un-played hooked card (pressure-gated, so the
        # player's non-pressing turn doesn't surface it), the weave governor may pepper the
        # HOOK — a directive woven at a seam — and the card is marked hook_proposed (the
        # floor accrues). Supersedes the old passive "PEOPLE WORTH PRESSING" nudge.
        from construct.cast import CastNode, Clue
        from construct.arc.executor import SESSION
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "name", "value": "Hobbes", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        ])
        cast = {"person:witness": CastNode("person:witness", "witness", "the witness",
                holds_clues=(
            Clue("clue:motive", "pillar:motive", ("fact:motive", "is", "debt"),
                 coverage_effect="genuine", reveal_condition="pressure",
                 hook_text="Hobbes keeps starting a sentence about the will he can't finish"),))}
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": True, "intent": "wait",
             "line_hint": ""},                                   # witness npc_turn (folded)
            {"decision": "pepper_hook", "card_id": "clue:motive",  # weave_pick
             "seam_hint": "as you scan the room", "directive": "Hobbes falters mid-sentence"},
            {"prose": "Hobbes opens his mouth, then thinks better of it."},
        ])
        result = run_turn(world, arc, provider, "I take in the room and the faces.", turn=2,
                          cast=cast, scope=["person:witness", PLAYER, "place:study"])
        assert result.trace.learned_clues == []          # pressure-gated; the FACT stays withheld
        assert result.trace.weave_decision == "pepper_hook"
        assert result.trace.weave_card == "clue:motive"
        prompt = _narrate_prompt(provider)
        # the woven directive carries the AUTHORED hook_text (not the model's free directive)
        assert "WEAVE THIS IN" in prompt
        assert "Hobbes keeps starting a sentence about the will" in prompt
        # the model's free directive is NOT forwarded (safety: hook only)
        assert "Hobbes falters mid-sentence" not in prompt
        # pepper_hook must instruct NOT to state the underlying fact (the safety seam)
        assert "do NOT state the underlying fact" in prompt
        # the hook is marked proposed (the floor accrues across turns)
        assert PorcelainWorldReads(world).state(
            "card:clue:motive", "weave_state", frame=SESSION) == "hook_proposed"

    def test_deliver_card_cannot_leak_an_unearned_clue(self, world):
        # Cx 041 BLOCKING fix: deliver_card on a pressure-gated clue the player did NOT earn
        # must not voice/promote the fact. Two guards: (1) deliver_card demotes to pepper_hook
        # when the fact isn't in the player frame; (2) the pillar clue fact is now a protected
        # key, so even a narrator restatement is quarantined — never canon, never knows:player.
        import dataclasses
        from construct.cast import CastNode, Clue
        from construct.arc.executor import SESSION
        from construct.arc.grammar import Pillar
        pillar = Pillar("pillar:motive", "the motive", required=True,
                        genuine_via=InFrame(PLAYER_FRAME, "fact:motive", "is", "debt"))
        arc = dataclasses.replace(make_arc(), pillars=(pillar,))
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"},
        ])
        cast = {"person:witness": CastNode("person:witness", "witness", "the witness",
                holds_clues=(
            Clue("clue:motive", "pillar:motive", ("fact:motive", "is", "debt"),
                 coverage_effect="genuine", reveal_condition="pressure",
                 hook_text="the witness keeps starting a sentence about the will he can't finish"),))}
        world._extractions.append({"items": []})                       # player input
        world._extractions.append({"items": [                          # narrator tries to voice it
            {"entity": "fact:motive", "attribute": "is", "value": "debt"}]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": True, "intent": "wait",
             "line_hint": ""},                                   # npc_turn (folded)
            {"decision": "deliver_card", "card_id": "clue:motive",  # weave_pick — UNEARNED
             # both the free directive AND a malicious seam_hint try to smuggle the fact:
             "seam_hint": "as the witness confesses the debt was the motive",
             "directive": "the witness BLURTS that the debt did it"},
            {"prose": "The witness wavers, on the edge of speech."},
        ])
        result = run_turn(world, arc, provider, "I glance around the study.", turn=2,
                          cast=cast, scope=["person:witness", "fact:motive", PLAYER, "place:study"])
        # deliver_card was demoted (the fact wasn't earned)
        assert result.trace.weave_decision == "pepper_hook"
        assert result.trace.learned_clues == []
        prompt = _narrate_prompt(provider)
        # NO free model prose reaches the weave directive — neither the unsafe `directive`
        # NOR a malicious `seam_hint`; only the authored safe hook is woven (Cx 045 hardening)
        assert "BLURTS that the debt" not in prompt
        assert "confesses the debt was the motive" not in prompt  # malicious seam_hint stripped
        assert "starting a sentence about the will he can't finish" in prompt
        # and the narrator's restatement is quarantined — not canon, not in the player frame
        assert world.porcelain.state("fact:motive", "is")["status"] != "known"
        assert not PorcelainWorldReads(world).assertion_in_frame(
            PLAYER_FRAME, "fact:motive", "is", "debt")

    def test_commitment_before_climax_does_not_conclude(self, world):
        # The commitment is EARNED, never turn 1: commits=True but NOT climax-ready → no
        # judge call, no termination (the player jumped the gun).
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "accuses the rival"},
            {"prose": "You blurt an accusation; nothing locks — you've barely arrived."},
        ])
        result = run_turn(world, arc, provider, "I accuse the rival immediately.", turn=1,
                          scenario_mode="win_loss",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert result.trace.commitment_grade == ""        # not judged (not earned)
        assert result.trace.terminal is False

    def test_holdmode_briefing_is_a_foreshadowing_card_plus_neutral(self, world):
        # CARD MODEL (STORY-SHAPES.md — supersedes the structural-absence pass): in
        # hold-mode the narrator IS given the hidden destination, but framed as a card to
        # FORESHADOW toward (weave clues, never blurt), NOT as a vault. It rides with the
        # neutral-narrator discipline. The answer reaching the briefing no longer leaks
        # because the player frame is clean (seed fix), the gate backstops, and the
        # narrator is told to lay a trail, never hand it over.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You scan the shelves."},
        ])
        result = run_turn(world, arc, provider, "I look over the records.", turn=1)
        prompt = _narrate_prompt(provider)
        # the DM gets the destination AS A CARD — present, with the don't-blurt discipline
        assert "THE HIDDEN DESTINATION" in prompt and "FORESHADOW toward it" in prompt
        assert "never blurt" in prompt.lower() or "hand it over" in prompt.lower()
        # neutral-narrator discipline rides alongside — neutrality is EPISTEMIC (about
        # the answer), NOT a flattening of human feeling (founder calibration)
        assert "NEUTRAL ON THE ANSWER" in prompt
        assert "A PEOPLED WORLD" in prompt and "full emotion" in prompt
        # the gate is still the commit backstop (audit clean — nothing leaked to canon)
        assert result.trace.concealment_audit == "clean"

    def test_convergence_act_one_plants_without_relocating(self, world):
        # CONVERGENCE-TO-CONCLUSION: a fresh arc (no beats achieved) is Act I — the
        # briefing gets a gentle convergence pull, NOT the relocate-the-climax push.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You take in the study."},
        ])
        result = run_turn(world, arc, provider, "I look around.", turn=1)
        prompt = _narrate_prompt(provider)
        assert "CONVERGENCE" in prompt and "ACT I" in prompt
        assert "RELOCATE" not in prompt
        assert result.trace.act == "I"

    def test_convergence_act_two_relocates_when_climax_ready(self, world):
        # Climax-ready (the climax_ready_beat is achieved) → Act II: the briefing now
        # tells the narrator to converge hard and RELOCATE the pivotal beat to wherever
        # the player is — without revealing the answer.
        from construct.arc.executor import turn_time
        arc = make_arc()
        seed_arc(world, arc)
        # Mark the climax-ready beat achieved — with a later valid_from so it
        # supersedes the seeded `pending` (as beat_pass does). climax_ready → Act II;
        # the world_condition (culprit in the PLAYER frame) is NOT satisfied, so the
        # arc is NOT concluded — exactly the "primed but not over" state.
        world.porcelain.ingest_structured(
            [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
              "valid_from": turn_time(3)}], frame="plot:main")
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You press on."},
        ])
        result = run_turn(world, arc, provider, "I keep digging.", turn=5,
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        prompt = _narrate_prompt(provider)
        assert "CONVERGENCE" in prompt and "ACT II" in prompt
        assert "RELOCATE" in prompt and "AT HAND" in prompt
        assert result.trace.act == "II"

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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "You look about the study."},
        ])
        run_turn(world, arc, provider, "I look around.", turn=1)
        narrate_prompt = _narrate_prompt(provider)
        assert "FEATURES OF THIS PLACE" in narrate_prompt
        assert "place:study_alcove" in narrate_prompt
        assert "shadowed recess" in narrate_prompt  # the feature's feel surfaced

    def test_furnish_is_memoized(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.extend([{"items": []}] * 4)
        # Each turn: classify → narrate. Diegetic time is now DETERMINISTIC for ordinary turns
        # (TURN-LATENCY Lever C) — "look around" needs no estimate_elapsed model call.
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""}, {"prose": "You look around."},
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""}, {"prose": "You look around again."},
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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""}, {"prose": "You take the rampway down."},
        ])
        result = run_turn(world, arc, provider, "I walk down the rampway.", turn=1)
        assert result.trace.concealment_audit == "clean"

    def test_exit_intent_short_circuits_with_flag(self, world):
        # classify → exit: the turn does NOT advance the world; it flags the
        # transport to confirm leaving (GAME-TYPES/exit flow).
        arc = make_arc()
        seed_arc(world, arc)
        provider = StubProvider([{"kind": "exit", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""}])
        r = run_turn(world, arc, provider, "can we do a new story?", turn=1)
        assert r.exit_requested is True
        assert r.prose == ""

    def test_ooc_is_answered_by_conduit_and_short_circuits(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        # classify → ooc, then the Conduit host reply (no narration cohort = the
        # world does not advance on an OOC turn).
        provider = StubProvider([
            {"kind": "ooc", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"reply": "No — you haven't met the win or loss condition yet."},
        ])
        result = run_turn(world, arc, provider, "have I won yet?", turn=1)
        assert result.prose.startswith("Conduit:")
        assert "win or loss condition" in result.prose


def test_names_entity_matches_narrated_names():
    # castdemo live-run finding (Cx 032 Q1): the player-agent addresses suspects by their
    # NARRATED names; the id-stem alone missed them. _names_entity now also matches the
    # significant tokens of the NPC's `name` fact (honorifics/articles dropped).
    from construct.turnloop import _names_entity
    # by narrated surname / role despite an opaque id
    assert _names_entity("person:butler", "i press hobbes about the study",
                         name="Hobbes, the butler")
    assert _names_entity("person:heir", "i ask the nephew about the will",
                         name="Julian, the disinherited nephew")
    assert _names_entity("person:doctor", "i question dr. ames about the vial",
                         name="Dr. Ames, the family physician")
    # id-stem still works without a name
    assert _names_entity("person:clerk", "i talk to the clerk")
    # honorifics/articles alone do NOT match (no false hit on 'the'/'dr')
    assert not _names_entity("person:doctor", "the man by the door", name="Dr. Ames")
    # an unrelated input matches nobody
    assert not _names_entity("person:heir", "i examine the clock", name="Julian, the nephew")
    # role-address by synonym engages the right NPC ('Doctor' for a family physician)
    assert _names_entity("person:orme", "doctor, when did you last see him?",
                         role="family physician")
    # WHOLE-TOKEN matching (Cx 049): substring 'doc' must NOT hit 'documents', so examining
    # documents near a present doctor does NOT falsely engage him and leak a clue.
    assert not _names_entity("person:orme", "i examine the documents on the desk",
                             role="family physician")
    assert not _names_entity("person:orme", "i study the physiology textbook",
                             role="family physician")
    # ROLE tokens are address-filtered to role-NOUN heads (Cx 051): a descriptor in the
    # surface_role (the victim's name, a place/scandal, a generic 'family') must NOT engage
    # the NPC, or an unrelated probe surfaces their clue unearned.
    assert not _names_entity("person:parker", "who saw sir julian before dinner?",
                             role="Sir Julian's valet")
    assert not _names_entity("person:celia", "what happened at market dalling?",
                             role="young gentlewoman connected to the old Market Dalling scandal")
    assert not _names_entity("person:orme", "what does the family know?",
                             role="family physician")
    # but the genuine role-noun head DOES address them
    assert _names_entity("person:parker", "valet, where were you at nine?",
                         role="Sir Julian's valet")
    assert _names_entity("person:celia", "i turn to the gentlewoman",
                         role="young gentlewoman connected to the scandal")


def test_colocated_is_containment_aware():
    # Founder NPC-liveness bug: NPCs the cold open narrates as present were going
    # inert because presence demanded an exact `in == scene` match. _colocated is
    # containment-aware: an NPC inside the player's scene (the anchor case — player
    # at the colony level, clerk in a room within it) now counts as present.
    from construct.turnloop import _colocated
    player = ["place:anchor", "place:flats"]
    # the live anchor bug: clerk deep inside the player's scene → present
    assert _colocated(["place:office", "place:tier", "place:anchor", "place:flats"],
                      "place:anchor", player) is True
    # exact same immediate place → present
    assert _colocated(["place:study", "place:hall"], "place:study",
                      ["place:study", "place:hall"]) is True
    # an unrelated room (no shared containment) → NOT present
    assert _colocated(["place:flat"], "place:study", ["place:study"]) is False
    # NPC whose immediate place sits on the player's chain (coarser-grain area) → present
    assert _colocated(["place:anchor", "place:flats"], "place:desk",
                      ["place:desk", "place:office", "place:anchor"]) is True
    # no location at all (the Cray data-gap case) → never present
    assert _colocated([], "place:anchor", player) is False


def test_parallel_preserves_order_and_isolates_failures():
    # Cx 022 #5 (NPC parallel determinism): _parallel runs the per-NPC cohort
    # thunks concurrently but MUST return results positionally aligned to the input
    # (so zip(npcs, results) is correct), and a thunk that raises yields its
    # exception in-place (callers fail-open per NPC) without sinking the batch.
    from construct.turnloop import _parallel

    def mk(i):
        def f():
            if i == 2:
                raise ValueError(f"boom-{i}")
            return i * 10
        return f

    out = _parallel([mk(0), mk(1), mk(2), mk(3)])
    assert out[0] == 0 and out[1] == 10 and out[3] == 30   # order preserved
    assert isinstance(out[2], ValueError)                   # failure isolated in slot
    # the single-thunk fast path also isolates a raise (no thread pool)
    assert isinstance(_parallel([mk(2)])[0], ValueError)
    assert _parallel([]) == []


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


# ---- STAGING-AFTERMATH-SCATTER / entry-epoch (obs #3 half 3, Cx 127) ----------------------

def test_compute_entry_epoch_above_aftermath_and_noop_when_low():
    from construct.arc.executor import TURN_EPOCH, compute_entry_epoch

    class _Row:
        def __init__(self, vf): self.valid_from = vf

    class _Buf:
        def __init__(self, vfs): self._vfs = vfs
        def all_rows(self): return [_Row(v) for v in self._vfs]

    class _W:
        def __init__(self, vfs): self.buffer = _Buf(vfs)

    # an aftermath calendar-year row (1974) → epoch strictly above it
    assert compute_entry_epoch(_W([1.0, 5.0, 1974.0])) > 1974.0
    # one-timeframe world (all rows below TURN_EPOCH) → no-op at TURN_EPOCH
    assert compute_entry_epoch(_W([1.0, 5.0, None])) == TURN_EPOCH
    assert compute_entry_epoch(_W([])) == TURN_EPOCH


def test_turn_time_honors_entry_epoch_contextvar():
    from construct.arc import executor
    from construct.arc.executor import TURN_EPOCH, set_entry_epoch, turn_time
    assert turn_time(0) == TURN_EPOCH          # default — unchanged
    tok = executor._ENTRY_EPOCH.set(TURN_EPOCH)  # capture to restore
    try:
        set_entry_epoch(3000.0)
        assert turn_time(0) == 3000.0 and turn_time(2) == 3002.0
        set_entry_epoch(500.0)                 # never lowers below TURN_EPOCH
        assert turn_time(0) == TURN_EPOCH
    finally:
        executor._ENTRY_EPOCH.reset(tok)


def test_entry_epoch_staging_wins_over_aftermath_and_live_supersedes(world):
    # The obs #3 scatter repro: an aftermath `in` row exists at a calendar-year valid_from;
    # opening staging committed on the entry axis WINS the current fold; a live turn still
    # supersedes the opening. (Default-epoch reads here would serve the aftermath.)
    from construct.arc import executor
    from construct.arc.executor import (
        TURN_EPOCH, compute_entry_epoch, set_entry_epoch, turn_time,
    )
    world.ingest_structured([
        {"entity": "place:scene", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:hospital", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:trail", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:guide", "attribute": "kind", "value": "person", "timeless": True},
        # AFTERMATH: the source prose narrated the guide ending up in hospital, at a calendar year
        {"entity": "person:guide", "attribute": "in", "value": "place:hospital",
         "value_type": "entity", "valid_from": 1974.0},
    ])
    assert world.porcelain.locate("person:guide")[0] == "place:hospital"  # aftermath currently wins
    tok = executor._ENTRY_EPOCH.set(TURN_EPOCH)
    try:
        epoch = compute_entry_epoch(world)
        assert epoch > 1974.0
        set_entry_epoch(epoch)
        # opening staging on the entry axis
        world.ingest_structured([
            {"entity": "person:guide", "attribute": "in", "value": "place:scene",
             "value_type": "entity", "valid_from": turn_time(0)},
        ])
        assert world.porcelain.locate("person:guide")[0] == "place:scene"  # staging wins
        # a live turn still supersedes the opening (the world can reach the aftermath in play)
        world.ingest_structured([
            {"entity": "person:guide", "attribute": "in", "value": "place:trail",
             "value_type": "entity", "valid_from": turn_time(1)},
        ])
        assert world.porcelain.locate("person:guide")[0] == "place:trail"
    finally:
        executor._ENTRY_EPOCH.reset(tok)


def test_literal_result_reads_declared_result_events(world):
    # Consolidation (131/132): the Contest literal result is a declared canon Occurred EVENT,
    # read via the event log — no bespoke scoreboard entity. None when nothing is declared.
    from construct.adapter import PorcelainWorldReads
    from construct.turnloop import _literal_result
    R = PorcelainWorldReads(world)
    assert _literal_result(R, None) is None                       # no axis declared
    re = {"win": ("bout_won",), "loss": ("bout_lost",)}
    assert _literal_result(R, re) is None                         # declared, but nothing fired yet
    world.porcelain.ingest_structured(
        [{"entity": "event:b1", "attribute": "kind", "value": "bout_lost", "valid_from": 1100.0}])
    assert _literal_result(R, re) == "loss"
    world.porcelain.ingest_structured(
        [{"entity": "event:b2", "attribute": "kind", "value": "bout_won", "valid_from": 1200.0}])
    assert _literal_result(R, re) == "win"                        # most-recent wins on no tie


def test_literal_result_participant_scoping_is_collision_proof():
    # Cx 132 #4 / 134: a global event `kind` must be scoped by participants (ALL-of across
    # agents∪patients). A same-kind event for a DIFFERENT contestant must not cross-fire.
    from construct.arc.conditions import EventRow
    from construct.turnloop import _literal_result
    from tests.fixtureworld import FixtureWorld
    re = {"win": ("bout_won",), "loss": ("bout_lost",), "participants": ("person:rocky",)}
    # rocky lost his bout — scoped match
    w_match = FixtureWorld(event_log={"canon": [
        EventRow("event:b1", "bout_lost", agents=("person:rocky",), at=1)]})
    assert _literal_result(w_match, re) == "loss"
    # a same-kind loss for a DIFFERENT fighter must NOT register as rocky's result
    w_other = FixtureWorld(event_log={"canon": [
        EventRow("event:b9", "bout_lost", agents=("person:clubber",), at=1)]})
    assert _literal_result(w_other, re) is None
    # participant as a patient also counts (agents ∪ patients)
    w_patient = FixtureWorld(event_log={"canon": [
        EventRow("event:b2", "bout_won", patients=("person:rocky",), at=2)]})
    assert _literal_result(w_patient, re) == "win"


def test_pacing_fold_is_epoch_invariant_under_raised_epoch(world):
    # The riskiest seam of the entry-epoch surgery: counters_from_session folds turns
    # RELATIVE to current_epoch() (turns_elapsed = #turn events; turns_quiet = turns since
    # the last beat/arc-touch mark). Under a RAISED epoch the absolute stamps are large; the
    # fold must still produce the same relative counts as at the default epoch.
    from construct.arc import executor
    from construct.arc.executor import (
        SESSION, TURN_EPOCH, counters_from_session, set_entry_epoch, turn_time,
    )
    arc = make_arc()

    def _stamp(epoch_label):
        # 3 turn events + a beat_achieved mark at turn 2, all on the active epoch axis
        for n in (1, 2, 3):
            world.ingest_structured(
                [{"entity": f"event:turn_{epoch_label}_{n}", "attribute": "kind",
                  "value": "turn", "valid_from": turn_time(n)}], frame=SESSION)
        world.ingest_structured(
            [{"entity": f"event:beat_{epoch_label}", "attribute": "kind",
              "value": "beat_achieved", "valid_from": turn_time(2)}], frame=SESSION)

    tok = executor._ENTRY_EPOCH.set(TURN_EPOCH)
    try:
        # baseline at the default epoch
        _stamp("base")
        base = counters_from_session(PorcelainWorldReads(world), arc)
        assert base.turns_elapsed == 3 and base.turns_quiet == 1  # last mark at turn 2 of 3
        # raise the epoch far above any calendar year; the SAME relative shape must hold
        set_entry_epoch(50000.0)
        _stamp("hi")
        hi = counters_from_session(PorcelainWorldReads(world), arc)
        # 6 turn events now (3 base + 3 hi); last mark is the hi beat at hi-epoch turn 2,
        # so turns_quiet folds against the CURRENT epoch (the base marks are below it).
        assert hi.turns_elapsed == 6
        assert hi.turns_quiet == 4  # 6 elapsed - last hi mark at relative turn 2
    finally:
        executor._ENTRY_EPOCH.reset(tok)


def test_clean_prose_strips_leaked_json_meta_tail():
    # The play harness caught the model spilling its JSON wrapper + reasoning into the
    # prose value. _clean_prose truncates at the first control/meta marker; clean prose
    # is untouched.
    from construct.cohorts import _clean_prose
    leaked = ('You study the desk; the ledger lies open and dry. should have its own '
              'log and seal."}    _久久爱=final elọpọ? Wait final schema expected JSON object')
    out = _clean_prose(leaked)
    assert out.endswith("log and seal.")
    assert "final schema" not in out and '"}' not in out
    # a second observed shape (meta phrase mid-tail)
    assert _clean_prose('I see none on this strip."}-vesm JSON includes maybe invalid').endswith("strip.")
    # SMART-quote + brace tail (live whodunit Turn 6): the closing quote was a curly ” so the
    # old straight-quote marker '"}' missed it; bare-brace cut catches it now.
    smart = ('“The only person I can place there that night is the doctor. I saw him enter '
             'alone. I heard no study bell after dinner.”} swineneＰＣＴＳＴＲ? 北京赛车开? '
             'Wait final has weird? Actually final JSON has extra? It ends with')
    out_s = _clean_prose(smart)
    assert out_s.endswith("after dinner.”")
    assert "swinene" not in out_s and "final JSON" not in out_s and "}" not in out_s
    # clean prose is a no-op (no braces in fiction prose)
    clean = "You step into the vault. Dust hangs in the lamp-light; the clerk does not look up."
    assert _clean_prose(clean) == clean


def test_render_leash_keeps_cast_distinct():
    # Cray/clerk conflation bug (founder live feedback): the narrator merged two distinct
    # established characters under an ambiguous player reference. The render leash now
    # binds the narrator to keep the established cast distinct and resolve ambiguous
    # references to it, never fabricating an identity-merge.
    from construct.cohorts import RENDER_LEASH
    assert "DISTINCT CAST" in RENDER_LEASH
    assert "never invent that one character is secretly another" in RENDER_LEASH


def test_author_intro_cohort():
    # The thematic introduction: premise/stakes in voice that GROUNDS the player —
    # but NO objective/aim line (founder 2026-06-22: the call to action arises in
    # play, never a game-y banner). The aim is no longer injected into the prompt.
    from construct.cohorts import author_intro
    prov = StubProvider([{"intro": "Rain on a drowned port; the ledgers lie."}])
    out = author_intro(prov, "DIGEST", theme="truth vs scarcity",
                       style="terse noir", aim="name who falsified the meter")
    assert "drowned port" in out["intro"]
    prompt = prov.calls[0][0]
    assert "do NOT end on an objective" in prompt            # no closing aim line
    assert "name who falsified the meter" not in prompt      # aim not injected
    assert "do NOT reveal" in prompt                         # spoilers still forbidden


def test_conditional_player_ingest_skips_extraction_when_no_assert(world):
    # TURN-LATENCY Lever A-lite (Cx 077/079): when classify says the input can't assert/reveal a
    # fact (pure look), SKIP the expensive player-input extraction. Movement/take still ride
    # moves_to/takes; protected-key licensing is unaffected (no facts asserted this turn).
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": []})  # ONLY the post-render extraction is consumed
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "asserts_or_reveals": False},
        {"prose": "You take in the quiet room."},
    ])
    r = run_turn(world, arc, provider, "I look around the room.", turn=1)
    assert any("player_ingest (skipped" in d for d in r.trace.dropped_cohorts)
    # default-TRUE keeps extraction when the field is absent (old stubs / uncertainty)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider2 = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "You pry the panel loose."},
    ])
    r2 = run_turn(world, arc, provider2, "I pry the loose panel open.", turn=2)
    assert not any("player_ingest (skipped" in d for d in r2.trace.dropped_cohorts)


def test_play_style_directive_in_briefing(world):
    # The game-type directive (GAME-TYPES.md) rides in the narrator briefing every
    # turn — a maintained instruction, not a toggle matrix.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "You look."},
    ])
    run_turn(world, arc, provider, "I look around.", turn=1,
             play_style="PLAY STYLE — MYSTERY: compress travel; dwell on clues.")
    np = _narrate_prompt(provider)
    assert "PLAY STYLE — MYSTERY" in np and "dwell on clues" in np


def test_style_overlay_in_briefing(world):
    # The world-level voice overlay rides into the narrator's briefing every turn.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "You look."},
    ])
    run_turn(world, arc, provider, "I look around.", turn=1,
             style="terse 1920s harbor-noir; rain-slick, cynical")
    narrate_prompt = _narrate_prompt(provider)
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
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "You name the rival; the meter's truth is out."},
    ])
    result = run_turn(world, arc, provider, "I name the culprit.", turn=1,
                      scenario_mode="win_loss")
    assert result.trace.terminal is True
    narrate_prompt = _narrate_prompt(provider)
    assert "EPILOGUE" in narrate_prompt
    assert "person:rival" in narrate_prompt   # the cast (a fate for each)
    assert "THE TRUTH" in narrate_prompt       # concealment lifts at the curtain
    # E2 (Cx 139 #2 / 141): on a close turn the epilogue OWNS the render — the player's act FOLDS
    # into the denouement, it does NOT compete via "render exactly this, no more" (which beat the
    # epilogue and left the curtain unrendered).
    assert "render exactly this, no more" not in narrate_prompt
    assert "FOLDS INTO" in narrate_prompt      # the final-act-folds-into-the-close directive


def test_commitment_owned_climax_is_ready_not_terminal(world):
    # Cx 141 (E1): for a COMMITMENT-owned shape (deduction/contest/…), achieving world_condition is
    # READINESS for the reckoning, NOT the close — the procedural climax must not terminate; the
    # player's conclusory commitment owns the curtain. (The audit-office falter.)
    from construct.turnloop import terminal_outcome
    arc = make_arc()
    seed_arc(world, arc)
    # world_condition (fact:secret culprit=rival) is MET — but the player has not reckoned.
    world.porcelain.ingest_structured(
        [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
        frame=PLAYER_FRAME)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},   # NOT a reckoning
        {"prose": "You lay the evidence out on the table; the room reads what it means."}])
    r = run_turn(world, arc, provider, "I lay out all the evidence on the table.", turn=3,
                 scenario_mode="win_loss", terminal_owner="commitment",
                 scope=["fact:secret", "person:rival", PLAYER, "place:study"])
    assert r.trace.terminal is False                       # readiness, NOT the close
    assert r.trace.concluded is False                      # no premature conclusion marker
    assert terminal_outcome(PorcelainWorldReads(world)) is None
    assert "DECISIVE MOMENT IS WITHIN REACH" in _narrate_prompt(provider)  # steered toward the curtain
    # now the player RECKONS → the commitment owns the curtain → terminal
    world._extractions.extend([{"items": []}, {"items": []}])
    provider2 = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": True, "commitment": "accuses the rival"},
        {"grade": "vindicated", "rationale": "the evidence matches"},   # judge_commitment
        {"prose": "You name the rival; the truth lands and the case closes."}])
    r2 = run_turn(world, arc, provider2, "I accuse the rival, naming them the culprit.", turn=4,
                  scenario_mode="win_loss", terminal_owner="commitment",
                  scope=["fact:secret", "person:rival", PLAYER, "place:study"])
    assert r2.trace.terminal is True                       # the accusation closes it


def test_no_deadline_ready_arc_never_force_concludes(world):
    # Founder ruling 2026-06-25 / Cx 173: turns are FREE. A commitment-owned arc with NO authored
    # deadline that is READY (sound proof) but uncommitted NEVER force-concludes — not after 2 turns,
    # not after 30, not after 300. Only the player's commitment (or an authored deadline) closes it.
    # (Replaces the retired post-climax-expiry / missed-reckoning behavior.)
    from construct.turnloop import terminal_outcome

    class _Steady(StubProvider):
        # A resilient stub that answers by prompt shape (never a fixed queue to desync over N
        # turns): the player keeps NOT committing, every turn.
        def __init__(self):
            super().__init__([])

        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            self.calls.append((prompt, schema, tier))
            if prompt.startswith("Classify the lifetime"):
                return {"durability": "STATE", "confidence": 0.9}
            if task_of(prompt) == "cls":
                return {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
                        "uncertain_of": "", "commits": False, "commitment": ""}
            if task_of(prompt) == "nar":
                return {"prose": "You turn the pieces over once more, in no hurry."}
            if task_of(prompt) == "ndg":
                return {"thread": "", "directive": ""}
            return {"items": []}   # extraction and any other cohort

    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured(
        [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
        frame=PLAYER_FRAME)   # world_condition MET → readiness, but the player won't reckon
    prov = _Steady()
    world._extractions.extend([{"items": []}] * 40)   # engine extraction queue (2/turn)
    # Many non-commitment turns while ready — the noir detective thinking it over, well past BOTH
    # the retired K=4 post-climax window AND the old TurnsQuiet(15) refusal window. None may close it.
    for t in range(3, 22):
        r = run_turn(world, arc, prov, "I study the evidence again and say nothing yet.", turn=t,
                     scenario_mode="win_loss", terminal_owner="commitment",
                     scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        assert r.trace.terminal is False, f"turn {t} force-concluded — turns must never close the arc"
        assert r.trace.outcome is None
        assert "clock:refusal" not in (r.trace.clocks_fired or [])   # never fires on quiet turns
    assert terminal_outcome(PorcelainWorldReads(world)) is None   # still open after 19 ready turns
    # Cx 178: inspect the RAW append log, not just the folded state — a fabricated turn-count
    # `refusal_conclusion` would breach the mesh invariant even if the fold reads `unknown`. Assert
    # NO refusal firing event and NO `event:world_concludes` row was ever appended.
    raw = list(world.buffer.visible())
    assert not [row for row in raw if row.entity == "event:world_concludes"], \
        "a refusal_conclusion was fabricated into canon on quiet turns"
    assert not [row for row in raw
                if row.entity.startswith("event:refusal_fired")], "the refusal clock fired on turns"


def test_decisive_loss_event_concludes_without_commitment(world):
    # Founder ruling 2026-06-25 ("IT closes it"): a story ends on its NARRATIVE decisive event,
    # authored per-story — not a mechanic. The BODYGUARD case: "IT" = the protectee's life. The
    # player leaves; the world causes the death (an authored `failure_when` Occurred event); that
    # closes the arc in failure WITHOUT any commitment, no time, no investigation to continue.
    # Proves the decisive-event model works for a NON-time, NON-investigation story via existing
    # failure_when + the 1a commitment-owned-evaluates-failure_when-directly change.
    import dataclasses as _dc
    from construct.arc.executor import turn_time
    arc = _dc.replace(make_arc(),
                      failure_when=Occurred("protectee_killed"))   # Occurred matches by event KIND
    seed_arc(world, arc)
    # The world causes the decisive loss (the unmasked killer strikes after the player walked away):
    # a canon event of the authored loss KIND.
    world.porcelain.ingest_structured(
        [{"entity": "event:the_killing", "attribute": "kind", "value": "protectee_killed",
          "valid_from": turn_time(2)}])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},   # NOT a commitment
        {"prose": "Too late — the shot has already been fired."}])
    r = run_turn(world, arc, provider, "I step out into the corridor for air.", turn=2,
                 scenario_mode="win_loss", terminal_owner="commitment",
                 scope=["fact:secret", "person:rival", PLAYER, "place:study"])
    assert r.trace.terminal is True              # the decisive loss event closes it — no commitment
    assert r.trace.outcome == "lost"


def test_build_arc_lowers_time_deadline_proposal():
    # Cx 182 #1: a model proposal carrying a time_deadline must survive _build_arc into
    # Arc.failure_when as the diegetic-clock Quantity (the authoring path, not just the lowerer).
    from construct.game import _build_arc
    from construct.arc.conditions import Quantity
    proposal = {
        "protagonist": "person:p", "delta_type": "drive_inverted",
        "tension": ["person:p", "drive:haste", "drive:care"],
        "beats": [{"id": "beat:ready", "phase": "climax", "weight": "required",
                   "kind": "event_occurs", "entity": "feast_served", "attribute": "", "value": ""}],
        "failure_when": {"kind": "time_deadline", "deadline_minutes": 60},
    }
    arc = _build_arc(proposal)
    assert arc.failure_when == Quantity("time:elapsed", "elapsed_minutes", ">=", 60.0)


def test_time_deadline_arc_advances_clock_before_conclusion():
    # Cx 173 #3: a time-deadline arc must advance diegetic time BEFORE the conclusion check (so a
    # big-jump wait crosses same-turn); a non-deadline arc keeps the post-render estimate. This gate
    # (_has_time_deadline) is what routes it — assert it detects only time-deadline failure_when.
    import dataclasses as _dc
    from construct.turnloop import _has_time_deadline
    from construct.game import _failure_expr
    time_arc = _dc.replace(make_arc(),
                           failure_when=_failure_expr({"kind": "time_deadline",
                                                       "deadline_minutes": 60}, PLAYER_FRAME))
    assert _has_time_deadline(time_arc) is True           # → early advance (same-turn crossing)
    event_arc = _dc.replace(make_arc(), failure_when=Occurred("protectee_killed"))
    assert _has_time_deadline(event_arc) is False         # event loss → post-render, unchanged
    assert _has_time_deadline(make_arc()) is False         # no failure_when → unchanged


def test_authored_time_deadline_concludes_lost(world):
    # Increment 2 (King's dinner / Batman): when a story authored time as part of its thread, the
    # deadline is a `Quantity` over the diegetic clock (time:elapsed.elapsed_minutes) in
    # `failure_when`. Once in-world time crosses it, the commitment-owned arc concludes LOST — the
    # fiction's clock ran out, the decisive moment passed. (Crossed-deadline conclusion; the
    # same-turn commit ORDERING is increment 2b.)
    import dataclasses as _dc
    from construct.game import _failure_expr
    deadline = _failure_expr({"kind": "time_deadline", "deadline_minutes": 60}, PLAYER_FRAME)
    arc = _dc.replace(make_arc(), failure_when=deadline)
    seed_arc(world, arc)
    # In-world time has passed the deadline (a long wait / the King has arrived). Seed with the
    # kind row the production clock now writes, so time:elapsed is a known entity for Quantity.
    world.porcelain.ingest_structured(
        [{"entity": "time:elapsed", "attribute": "kind", "value": "clock", "timeless": True},
         {"entity": "time:elapsed", "attribute": "elapsed_minutes", "value": 90,
          "value_type": "literal"}])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "The hour has come and gone; it is too late now."}])
    r = run_turn(world, arc, provider, "I keep fussing with the table settings.", turn=4,
                 scenario_mode="win_loss", terminal_owner="commitment",
                 scope=[PLAYER, "place:study"])
    assert r.trace.terminal is True       # the diegetic deadline closed it
    assert r.trace.outcome == "lost"


def test_epilogue_prose_mints_no_canon_aliases(world):
    # Cx 189 #1/#4: on a TERMINAL/curtain turn the narrator's fate-summary prose ("...walks back into
    # the rain with his name cleared") must NOT be promoted into canon — that pollution became EP2
    # character NAMES ("With His Name Cleared"). The post-render gate drops all promotion on an
    # epilogue turn. The damning-alias extraction is staged but never reaches canon.
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured(
        [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
        frame=PLAYER_FRAME)   # ready → the accusation will conclude
    world._extractions.append({"items": []})                       # player-input extraction
    world._extractions.append({"items": [                          # post-render epilogue extraction
        {"entity": "person:rival", "attribute": "alias", "value": "with his name cleared"}]})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": True, "commitment": "accuses the rival"},
        {"grade": "vindicated", "rationale": "the evidence matches"},
        {"prose": "You name the rival; they are taken out into the rain with their name cleared."}])
    r = run_turn(world, arc, provider, "I accuse the rival, naming them the culprit.", turn=4,
                 scenario_mode="win_loss", terminal_owner="commitment",
                 scope=["fact:secret", "person:rival", PLAYER, "place:study"])
    assert r.trace.terminal is True
    # the epilogue's descriptive alias was NOT canonized
    st = world.porcelain.state("person:rival", "alias")
    assert st["status"] == "unknown" or st.get("fact", {}).get("value") != "with his name cleared"
    assert not [row for row in world.buffer.visible(frame="canon")
                if row.entity == "person:rival" and row.attribute == "alias"
                and row.value == "with his name cleared"]


def test_counter_refusal_clock_suppressed_at_runtime(world):
    # Cx 178 defense-in-depth: a PERSISTED / hand-authored old-shape TurnsQuiet REFUSAL clock must
    # NOT fire at runtime — clock_pass suppresses it so no fabricated `refusal_conclusion` ever
    # enters canon, even for worlds authored before the explicit-abandonment reshape.
    import dataclasses as _dc
    from construct.arc.conditions import PacingCounters
    from construct.arc.executor import clock_pass
    old_refusal = Clock("clock:refusal", TurnsQuiet(1),
                        effects=({"entity": "event:world_concludes", "attribute": "kind",
                                  "value": "refusal_conclusion"},),
                        bound_to="arc:main", rung=Rung.REFUSAL)
    arc = _dc.replace(make_arc(), refusal_clock=old_refusal)
    seed_arc(world, arc)
    fired = clock_pass(world, arc, PorcelainWorldReads(world),
                       PacingCounters(turns_elapsed=9, turns_quiet=9), turn=9)
    assert "clock:refusal" not in fired                       # the counter refusal is suppressed
    assert world.porcelain.state("event:world_concludes", "kind")["status"] == "unknown"
    assert not [r for r in world.buffer.visible() if r.entity == "event:world_concludes"]


def test_world_event_owned_still_terminates_on_world_condition(world):
    # Cx 141 #3: the per-shape split must NOT regress world-event-owned / legacy arcs — a
    # world_event terminal_owner (the default) still ends directly on world_condition.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": [
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}]})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "The world tips into its ending."}])
    r = run_turn(world, arc, provider, "I trip the final mechanism.", turn=2,
                 scenario_mode="win_loss", terminal_owner="world_event")  # the default
    assert r.trace.terminal is True                        # world event ends directly — unchanged


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
        {"kind": "action", "moves_to": "the flat", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "You cross to the flat."},
    ])
    run_turn(world, arc, provider, "I leave the study and go to the flat.", turn=1)
    assert world.porcelain.locate(PLAYER)[0] == "place:flat"  # superseded move


def test_movement_to_a_person_redirects_to_their_place(world):
    # INVESTIGATION-SHAPE.md §3c / Cx 057: "go to Parker" must travel to Parker's PLACE,
    # never set the protagonist `in` a person entity.
    arc = make_arc()
    seed_arc(world, arc)
    world.ingest_structured([
        {"entity": "person:parker", "attribute": "kind", "value": "person",
         "timeless": True, "aliases": ["parker"]},
        {"entity": "place:pantry", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:parker", "attribute": "in", "value": "place:pantry"},
    ])
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "parker", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "You go find Parker in the pantry."},
    ])
    run_turn(world, arc, provider, "I go to Parker.", turn=1)
    # moved to Parker's PLACE, not 'into' the person
    assert world.porcelain.locate(PLAYER)[0] == "place:pantry"


def test_adapt_genuine_writes_clue_through_the_authorized_doorway(world):
    # NARRATION-DISCIPLINE.md make-it-real (Cx 087): a genuine adaptation writes the pursued
    # detail into knows:<protagonist> via the SAME learn_clue_items shape + a hidden plot: receipt.
    from construct.arc.adapt import apply_adaptation
    seed_arc(world, make_arc())
    dec = {"lane": "genuine", "pillar_id": "pillar:means", "reason": "the wet ring proves a glass",
           "fact": ["fact:means", "is", "glass_was_here"]}
    res = apply_adaptation(world, dec, protagonist=PLAYER, turn=3, reads=PorcelainWorldReads(world))
    assert res["applied"] and res["lane"] == "genuine"
    rd = PorcelainWorldReads(world)
    assert rd.assertion_in_frame(PLAYER_FRAME, "fact:means", "is", "glass_was_here")
    # the audit receipt is a HIDDEN plot-frame event (provenance), not a canon/player-frame fact
    recs = rd.events(kind="improv_adaptation", frame="plot:main")
    assert any(e.event_id == "event:adapt_3" for e in recs)
    # and the budget ledger advanced (session frame, hidden)
    from construct.arc.adapt import adaptations_used
    assert adaptations_used(rd) == 1


def test_make_it_real_reroutes_a_pursued_thread_to_an_unfilled_pillar(world):
    # NARRATION-DISCIPLINE.md slice 3 (Cx 087): the player CLOSELY pursues an UN-AUTHORED detail
    # (examines_target set, names no cast holder). With an unfilled required pillar, the host
    # reroutes — writes that pillar's authored GENUINE clue fact into the player frame and briefs
    # the narrator to render it as the player's OWN deduction. Route-flex, never answer-flex.
    import dataclasses
    from construct.cast import CastNode, Clue
    from construct.arc.grammar import Pillar
    pillar = Pillar("pillar:means", "the means", required=True,
                    genuine_via=InFrame(PLAYER_FRAME, "fact:means", "is", "vial_missing"))
    arc = dataclasses.replace(make_arc(), pillars=(pillar,))
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "obj:bag", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:bag", "attribute": "in", "value": "place:study"},
    ])
    # the authored genuine clue lives on the bag (NO hook_text → weave governance is skipped)
    cast = {"obj:bag": CastNode("obj:bag", "evidence", "the doctor's bag", holds_clues=(
        Clue("clue:vial", "pillar:means", ("fact:means", "is", "vial_missing"),
             coverage_effect="genuine", reveal_condition="scrutiny"),))}
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": "",
         "examines_target": "the damp ring on the sideboard"},          # un-authored pursuit
        {"lane": "genuine", "pillar_id": "pillar:means",                 # adapt_decision
         "reason": "a damp ring with no glass implies a poured drink was removed → the means"},
        {"prose": "You crouch by the sideboard; the ring is fresh, and you realize a glass "
                  "stood here and was taken — something was administered."},               # narrate
    ])
    result = run_turn(world, arc, provider, "I examine the damp ring on the sideboard closely.",
                      turn=4, cast=cast, scope=["obj:bag", PLAYER, "place:study"])
    # the pursued thread became the path to the unfilled cause — the pillar's authored fact landed
    assert ("genuine", "pillar:means") in result.trace.adapted
    rd = PorcelainWorldReads(world)
    assert rd.assertion_in_frame(PLAYER_FRAME, "fact:means", "is", "vial_missing")
    # coverage actually advanced (the case can now land via the player's OWN route)
    from construct.arc.executor import coverage_summary
    assert "pillar:means" in coverage_summary(rd, arc)["genuine"]
    # the narrator was briefed to render it as their own deduction (make-it-real directive present)
    assert "MAKE IT REAL" in _narrate_prompt(provider)


def test_make_it_real_skips_a_generic_look_around(world):
    # Cx 087 guard: a generic look-around (no examines_target) must NOT trigger adaptation —
    # we adapt PURSUIT of a specific detail, never every atmospheric glance.
    import dataclasses
    from construct.cast import CastNode, Clue
    from construct.arc.grammar import Pillar
    pillar = Pillar("pillar:means", "the means", required=True,
                    genuine_via=InFrame(PLAYER_FRAME, "fact:means", "is", "vial_missing"))
    arc = dataclasses.replace(make_arc(), pillars=(pillar,))
    seed_arc(world, arc)
    cast = {"obj:bag": CastNode("obj:bag", "evidence", "the doctor's bag", holds_clues=(
        Clue("clue:vial", "pillar:means", ("fact:means", "is", "vial_missing"),
             coverage_effect="genuine", reveal_condition="scrutiny"),))}
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([                                            # NO examines_target
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": "", "examines_target": ""},
        {"prose": "The study is quiet; shelves, a cold hearth, the desk by the window."},
    ])
    result = run_turn(world, arc, provider, "I glance around the study.", turn=2,
                      cast=cast, scope=["obj:bag", PLAYER, "place:study"])
    assert result.trace.adapted == []   # no adapt_decision call was made (queue not consumed)
    assert not PorcelainWorldReads(world).assertion_in_frame(
        PLAYER_FRAME, "fact:means", "is", "vial_missing")


def test_make_it_real_skips_the_authored_holder(world):
    # Cx 089 #1: a close inspection of the ACTUAL authored object holder goes through EXAMINE
    # delivery — it must NOT trigger make-it-real (no adapt:cheap call, no short-circuited gate).
    import dataclasses
    from construct.cast import CastNode, Clue
    from construct.arc.grammar import Pillar
    pillar = Pillar("pillar:means", "the means", required=True,
                    genuine_via=InFrame(PLAYER_FRAME, "fact:means", "is", "vial_missing"))
    arc = dataclasses.replace(make_arc(), pillars=(pillar,))
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "obj:bag", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:bag", "attribute": "in", "value": "place:study"},
    ])
    cast = {"obj:bag": CastNode("obj:bag", "evidence", "the doctor's bag", holds_clues=(
        Clue("clue:vial", "pillar:means", ("fact:means", "is", "vial_missing"),
             coverage_effect="genuine", reveal_condition="scrutiny"),))}
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([                                # examines the AUTHORED bag
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": "",
         "examines_target": "the doctor's bag"},
        {"prose": "You open the bag; a vial slot sits conspicuously empty."},
    ])
    result = run_turn(world, arc, provider, "I examine the doctor's bag closely.", turn=2,
                      cast=cast, scope=["obj:bag", PLAYER, "place:study"])
    # normal EXAMINE delivery handled it — make-it-real never ran (no adapt:cheap call)
    assert "clue:vial" in result.trace.learned_clues
    assert result.trace.adapted == []
    assert "adapt:cheap" not in result.trace.cohort_calls


def test_adapt_rejects_unknown_lane(world):
    # Cx 089 #2: a buggy/new caller passing an unknown lane declines to atmosphere — it must
    # NEVER fall through to a write.
    from construct.arc.adapt import apply_adaptation
    seed_arc(world, make_arc())
    res = apply_adaptation(world, {"lane": "frobnicate", "fact": ["fact:x", "is", "y"]},
                           protagonist=PLAYER, turn=1, reads=PorcelainWorldReads(world))
    assert not res["applied"] and res["lane"] == "rejected_unknown_lane"
    assert not PorcelainWorldReads(world).assertion_in_frame(PLAYER_FRAME, "fact:x", "is", "y")


def test_adapt_red_herring_without_debunker_declines(world):
    # A false path WITHOUT a reachable debunker is the dead-end problem relabeled (Cx 087) → decline.
    from construct.arc.adapt import apply_adaptation
    seed_arc(world, make_arc())
    dec = {"lane": "red_herring", "pillar_id": "pillar:means",
           "fact": ["fact:means", "is", "blamed_widow"], "debunker_fact": None}
    res = apply_adaptation(world, dec, protagonist=PLAYER, turn=1, reads=PorcelainWorldReads(world))
    assert not res["applied"] and res["lane"] == "rejected_no_debunker"
    assert not PorcelainWorldReads(world).assertion_in_frame(PLAYER_FRAME, "fact:means", "is", "blamed_widow")


def test_adapt_decline_and_plot_supersede_are_noops(world):
    # decline = atmosphere (fail-open); plot_supersede = deferred (never silently mutate the solve).
    from construct.arc.adapt import apply_adaptation
    seed_arc(world, make_arc())
    rd = PorcelainWorldReads(world)
    assert apply_adaptation(world, {"lane": "decline"}, protagonist=PLAYER, turn=1, reads=rd)["applied"] is False
    sup = apply_adaptation(world, {"lane": "plot_supersede", "fact": ["f", "a", "v"]},
                           protagonist=PLAYER, turn=1, reads=rd)
    assert not sup["applied"] and sup["lane"] == "deferred_plot_supersede"


def test_adapt_budget_caps_adaptations(world):
    # Make-it-real is budgeted (the generator's pacing lesson) — beyond the cap, decline.
    from construct.arc.adapt import ADAPT_BUDGET, apply_adaptation
    seed_arc(world, make_arc())
    for i in range(ADAPT_BUDGET):
        r = apply_adaptation(world, {"lane": "genuine", "pillar_id": "p",
                                     "fact": [f"fact:x{i}", "is", "y"]},
                             protagonist=PLAYER, turn=i + 1, reads=PorcelainWorldReads(world))
        assert r["applied"]
    over = apply_adaptation(world, {"lane": "genuine", "pillar_id": "p",
                                    "fact": ["fact:over", "is", "y"]},
                            protagonist=PLAYER, turn=99, reads=PorcelainWorldReads(world))
    assert not over["applied"] and over["lane"] == "budget_exhausted"


def test_movement_to_undiscovered_offscene_target_is_blocked(world):
    # Cx 061 #3: canon referability is not player entitlement. Moving to an OFFSCENE cast
    # member's place before learning their whereabouts must be blocked (no teleport via a
    # guessed/known alias); once discovered, the move is allowed.
    from construct.cast import CastNode
    arc = make_arc()
    seed_arc(world, arc)
    world.ingest_structured([
        {"entity": "place:cottage", "attribute": "kind", "value": "room",
         "timeless": True, "aliases": ["the cottage"]},
        {"entity": "person:bell", "attribute": "kind", "value": "person",
         "timeless": True, "aliases": ["bell", "captain bell"]},
        {"entity": "person:bell", "attribute": "in", "value": "place:cottage"},
    ])
    cast = {"person:bell": CastNode("person:bell", "suspect", "the captain",
            presence="offscene", location="place:cottage", is_culprit=True)}
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "the cottage", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "You don't yet know where to find the cottage."},
    ])
    result = run_turn(world, arc, provider, "I go to the cottage.", turn=1, cast=cast,
                      scope=["person:bell", PLAYER, "place:study"])
    # blocked — the player has not learned Bell's whereabouts; no teleport
    assert world.porcelain.locate(PLAYER)[0] != "place:cottage"
    assert result.trace.movement_status == "undiscovered"

    # the PERSON-target path is gated too ("go to Bell" before discovery) — Cx 063 note
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider_p = StubProvider([
        {"kind": "action", "moves_to": "bell", "requires": [], "needs_test": False, "uncertain_of": ""},
        {"prose": "You don't yet know where Bell is."},
    ])
    res_p = run_turn(world, arc, provider_p, "I go to Bell.", turn=2, cast=cast,
                     scope=["person:bell", PLAYER, "place:study"])
    assert world.porcelain.locate(PLAYER)[0] != "place:cottage"
    assert res_p.trace.movement_status == "undiscovered"

    # now the player LEARNS the whereabouts → the route is entitled → the move lands
    world.porcelain.ingest_structured(
        [{"entity": "person:bell", "attribute": "whereabouts", "value": "place:cottage",
          "value_type": "entity"}], frame=PLAYER_FRAME)
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider2 = StubProvider([
        {"kind": "action", "moves_to": "the cottage", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        # the move lands → Bell (at place:cottage) becomes present, so npc cohorts run:
        {"acts": False, "action": "", "speaks": True, "intent": "wait",
         "line_hint": ""},                                    # bell npc_turn (folded)
        {"prose": "You make your way to the cottage; Bell is here."},
    ])
    run_turn(world, arc, provider2, "I go to the cottage.", turn=2, cast=cast,
             scope=["person:bell", PLAYER, "place:study", "place:cottage"])
    assert world.porcelain.locate(PLAYER)[0] == "place:cottage"


def test_adjudication_denies_phantom_key(world):
    arc = make_arc()
    seed_arc(world, arc)
    provider = StubProvider([
        {"kind": "action", "moves_to": "",
         "requires": ["the iron vault key"], "needs_test": False, "uncertain_of": ""},          # classify
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
        {"kind": "action", "moves_to": "", "requires": ["the brass key"], "needs_test": False, "uncertain_of": ""},
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
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
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

    def test_hidden_terms_are_only_the_answers_not_the_premise(self, world):
        from construct.game import _hidden_terms
        terms = _hidden_terms(world, self._proposal("anything"))
        # ONLY the player_learns VALUE (the answer to discover) is a spoiler.
        assert "rival" in terms
        # the PREMISE is free for the aim to name (a genre-true goal SHOULD —
        # 'lift the blight', 'name the culprit', 'explore the study'): the beat
        # SUBJECT, its attribute, and the canon setting are NOT forbidden.
        assert "secret" not in terms    # the beat subject entity (premise)
        assert "culprit" not in terms   # the beat attribute (a genre word)
        assert "study" not in terms and "flat" not in terms  # canon setting

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
        # a genre-true aim naming the PREMISE/subject now passes (the fix — this
        # used to fall back to boilerplate because 'secret'/'study' were forbidden)
        premise = "uncover the secret at the heart of the study"
        assert _player_goal(self._proposal(premise), world) == premise
        # leaks the discovered ANSWER (the culprit) → fail-closed to the default
        leaky = "prove that person:rival did it"
        assert _player_goal(self._proposal(leaky), world) == _DEFAULT_GOAL
        # empty/absent → default, never crashes
        assert _player_goal(self._proposal(""), world) == _DEFAULT_GOAL

    def test_player_goal_honors_user_chosen_win(self, world):
        from construct.game import _player_goal, _DEFAULT_GOAL
        # the player co-authored their aim (no authored goal) → use THEIRS
        p = self._proposal("")
        assert _player_goal(p, world, win_direction="slay the dragon and free the vale") \
            == "slay the dragon and free the vale"
        # but even the player's own framing can't spell out the discovered answer
        assert _player_goal(p, world, win_direction="prove the rival did it") == _DEFAULT_GOAL


def test_convergence_directive_builds_suspense_amplified_for_peril():
    # founder: "don't forget tension, raised stakes, suspense build-up before the conclusive
    # scene — especially peril/thriller". Act II carries a rising-stakes clause; peril amplifies it.
    from construct.turnloop import _convergence_directive
    from construct.arc.grammar import Phase
    _act, peril_ii = _convergence_directive(Phase.CRISIS, ready=False, peril=True)
    assert _act == "II"
    assert "BUILD THE SUSPENSE" in peril_ii and "tighten the screws" in peril_ii
    assert "dread" in peril_ii  # the thriller amplification
    _act2, calm_ii = _convergence_directive(Phase.CRISIS, ready=False, peril=False)
    assert "MOUNT" in calm_ii and "gathering to a head" in calm_ii   # general build-up
    assert "tighten the screws" not in calm_ii                       # not the peril amplifier
    # Act I plants the stakes (a current under it), not the full build-up
    _acti, peril_i = _convergence_directive(Phase.SETUP, ready=False, peril=True)
    assert _acti == "I" and "STAKES register" in peril_i
    # Act III hands off to the epilogue (no convergence directive)
    assert _convergence_directive(Phase.FALLING, ready=False, peril=True)[1] == ""


def test_place_holder_self_edge_is_present_and_delivers_on_examine(world):
    # Cx 113 #1: a place: HOLDER that authors its own id as location (self-edge) must still be
    # PRESENT and deliver via EXAMINE. cast_location_plan anchors the self-edge to the scene, so
    # _present() sees it and scrutiny surfaces its clue into knows:<protagonist>.
    from construct.cast import CastNode, Clue, cast_location_plan
    arc = make_arc()
    seed_arc(world, arc)
    # a Discovery-style site holder whose authored location IS itself (the self-edge bug)
    cast = {"place:cisterns": CastNode("place:cisterns", "site", "the cisterns", presence="nearby",
            location="place:cisterns", holds_clues=(
        Clue("clue:purpose", "pillar:purpose", ("fact:purpose", "is", "memory_chambers"),
             coverage_effect="genuine", reveal_condition="scrutiny"),))}
    # stage via cast_location_plan (the fix anchors the self-edge to the scene place:study) + admit
    # the holder as canon (kind), exactly as the session-zero path does
    world.porcelain.ingest_structured(
        cast_location_plan(tuple(cast.values()), "place:study"))
    world.porcelain.ingest_structured(
        [{"entity": "place:cisterns", "attribute": "kind", "value": "place", "timeless": True}])
    # the anchor landed: the site is located within the scene (not a dropped self-edge)
    assert world.porcelain.locate("place:cisterns")  # non-empty chain → present
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": "", "examines_target": "the cisterns"},
        {"prose": "You crouch to the resonant water tanks and read the law-songs cut into them."},
    ])
    result = run_turn(world, arc, provider, "I study the cisterns closely.", turn=2,
                      cast=cast, scope=["place:cisterns", PLAYER, "place:study"])
    assert "clue:purpose" in result.trace.learned_clues
    assert PorcelainWorldReads(world).assertion_in_frame(
        PLAYER_FRAME, "fact:purpose", "is", "memory_chambers")


def _arc_with_occurred_beat(kind="deed_done"):
    """make_arc() + one pending OPTIONAL Occurred(kind) act-beat (EVENT-OCCURS-FIRING tests)."""
    import dataclasses
    from construct.arc.grammar import Beat, Phase, Weight
    from construct.arc.conditions import Occurred
    base = make_arc()
    od = Beat("beat:deed", Phase.RISING, Weight.OPTIONAL, achievable_via=Occurred(kind=kind))
    return dataclasses.replace(base, beats=(*base.beats, od))


def test_event_occurs_beat_fires_and_achieves_on_success(world):
    # EVENT-OCCURS-FIRING (Cx 115): a successful action that the detector flags writes the authored
    # canon event (caused_by an action event) → Occurred true → beat_pass achieves the beat THIS turn.
    arc = _arc_with_occurred_beat()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"occurred": ["deed_done"]},                       # detect_events
        {"prose": "You abandon the cargo; the party stays on the cord."},
    ])
    result = run_turn(world, arc, provider, "I cut the ore loose to keep us together.", turn=2,
                      scope=[PLAYER, "place:study"])
    assert result.trace.events_fired == ["deed_done"]
    assert "detect_events:cheap" in result.trace.cohort_calls
    assert "beat:deed" in result.trace.beats_achieved            # achieved same turn
    rd = PorcelainWorldReads(world)
    assert rd.events(kind="deed_done")                           # binding canon event
    assert rd.events(kind="player_action")                       # the action-event anchor
    # the causality edge is visible through the EVENT LENS (Cx 117 — an event-entity row, not item metadata)
    assert rd.events(kind="deed_done")[0].caused_by == ("event:action_2",)
    assert "WHAT JUST HAPPENED" in _narrate_prompt(provider)     # surfaced as binding


def test_fire_event_occurs_only_kinds_restricts_candidates(world):
    # Result-event minting (131/132 Contest half): the failure-tier path restricts minting to the
    # declared loss-kinds via `only_kinds`, so an ordinary Occurred beat the detector also flags is
    # NOT canonized (ordinary beats keep the success-only rule; only the declared result-event mints).
    import dataclasses
    from construct.arc.conditions import Occurred
    from construct.arc.grammar import Beat, Phase, Weight
    from construct.turnloop import TurnTrace, _fire_event_occurs
    base = make_arc()
    arc = dataclasses.replace(base, beats=(*base.beats,
        Beat("beat:loss", Phase.CLIMAX, Weight.OPTIONAL, achievable_via=Occurred("bout_lost")),
        Beat("beat:other", Phase.RISING, Weight.OPTIONAL, achievable_via=Occurred("other_deed"))))
    seed_arc(world, arc)
    provider = StubProvider([{"occurred": ["bout_lost", "other_deed"]}])  # detector flags BOTH
    trace = TurnTrace(turn=2)
    fired = _fire_event_occurs(world, world.porcelain, PorcelainWorldReads(world), [arc],
                               provider, "the final blow lands against me", "terrible_failure", 2,
                               trace, PLAYER, only_kinds={"bout_lost"})
    assert fired == ["bout_lost"]                                # only the declared loss-kind
    R = PorcelainWorldReads(world)
    assert R.events(kind="bout_lost") and not R.events(kind="other_deed")


def test_result_event_loss_not_minted_before_result_moment(world, monkeypatch):
    # Cx 132 #2: a failure-tier loss result-event must NOT canonize EARLY — gated to the active
    # result moment (a conclusory commit, or the arc's late phase). An early failed action with the
    # arc still in SETUP and no commit must not mint the declared loss.
    import dataclasses
    from construct import resolution
    from construct.arc.conditions import Occurred
    from construct.arc.grammar import Beat, Phase, Weight
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    base = make_arc()
    arc = dataclasses.replace(base, beats=(*base.beats,
        Beat("beat:loss", Phase.CLIMAX, Weight.OPTIONAL, achievable_via=Occurred("bout_lost_main"))))
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([                       # NO detect_events stub — the gate must block it
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": True,
         "uncertain_of": "risky", "commits": False, "commitment": ""},
        {"prose": "You swing early and miss; the bout is far from decided."}])
    result = run_turn(world, arc, provider, "I throw an early jab.", turn=2,
                      result_events={"win": ("bout_won_main",), "loss": ("bout_lost_main",)},
                      scope=[PLAYER, "place:study"])
    assert result.trace.adjudication == "test:terrible_failure"
    assert "bout_lost_main" not in (result.trace.events_fired or [])
    assert not PorcelainWorldReads(world).events(kind="bout_lost_main")  # gate blocked the early loss


def test_event_occurs_no_fire_on_failure_tier(world, monkeypatch):
    # Cx 115/117: an uncertain action resolving to a FAILURE tier must NOT fire the beat — no
    # detector call, no canon event (a failed attempt can't canonize the act).
    from construct import resolution
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = _arc_with_occurred_beat()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([                              # NO detect_events stub — must not be called
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": True,
         "uncertain_of": "the slope may give", "commits": False, "commitment": ""},
        {"prose": "You reach to cut the ore loose, but the footing slides out from under you."},
    ])
    result = run_turn(world, arc, provider, "I try to cut the ore loose.", turn=2,
                      scope=[PLAYER, "place:study"])
    assert result.trace.adjudication == "test:terrible_failure"
    assert result.trace.events_fired == []
    assert "detect_events:cheap" not in result.trace.cohort_calls
    assert not PorcelainWorldReads(world).events(kind="deed_done")


def test_event_occurs_no_fire_when_detector_says_none(world):
    # near-miss: the detector returns nothing → no event, beat stays pending (fail-open).
    arc = _arc_with_occurred_beat()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"occurred": []},                                  # detector: nothing happened
        {"prose": "You consider cutting the ore loose, but don't."},
    ])
    result = run_turn(world, arc, provider, "I think about cutting the ore loose.", turn=2,
                      scope=[PLAYER, "place:study"])
    assert result.trace.events_fired == []
    assert "beat:deed" not in result.trace.beats_achieved
    assert not PorcelainWorldReads(world).events(kind="deed_done")


def test_event_occurs_no_detector_call_without_candidates(world):
    # no pending Occurred beat → no detector call at all (no added latency on deduction arcs).
    arc = make_arc()  # no Occurred beats
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([                              # NO detect_events stub
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "You look around."},
    ])
    result = run_turn(world, arc, provider, "I look around.", turn=2, scope=[PLAYER, "place:study"])
    assert result.trace.events_fired == []
    assert "detect_events:cheap" not in result.trace.cohort_calls


def test_event_occurs_already_achieved_offers_no_candidate(world):
    # dedupe by status: an already-achieved Occurred beat is not a candidate → no detector call.
    from construct.arc.executor import turn_time
    arc = _arc_with_occurred_beat()
    seed_arc(world, arc)
    world.porcelain.ingest_structured(
        [{"entity": "beat:deed", "attribute": "status", "value": "achieved",
          "valid_from": turn_time(1)}], frame="plot:main")
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([                              # NO detect_events stub (no candidates)
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "You act."},
    ])
    result = run_turn(world, arc, provider, "I cut the ore loose again.", turn=3,
                      scope=[PLAYER, "place:study"])
    assert "detect_events:cheap" not in result.trace.cohort_calls
    assert result.trace.events_fired == []


def test_terminal_outcome_scoped_past_episode_boundary():
    # CONCLUDE→CONTINUE: a prior episode's win/loss receipt must not freeze the next episode.
    # terminal_outcome reads receipts only SINCE the latest episode_start boundary marker.
    from construct.arc.conditions import EventRow
    from construct.turnloop import terminal_outcome
    from tests.fixtureworld import FixtureWorld
    S = "session:main"
    w = FixtureWorld(event_log={S: [EventRow("event:o1", "arc_won", at=5.0)]})
    assert terminal_outcome(w) == "won"            # episode 1 ended (no boundary yet)
    w.event_log[S].append(EventRow("event:ep2", "episode_start", at=10.0))
    assert terminal_outcome(w) is None             # episode 2 live — prior receipt behind boundary
    w.event_log[S].append(EventRow("event:o2", "arc_lost", at=14.0))
    assert terminal_outcome(w) == "lost"           # episode 2's own ending counts


class TestWorldReshape:
    """WORLD-CHANGING AGENCY (flag-gated): an earned, uncertain act reshapes canon
    pre-render; the sanctioned rows promote past the protected-key gate; flag-off is
    fully inert. (docs/design/WORLD-CHANGING-AGENCY.md; Cx 204/205.)"""

    def test_flag_on_commits_and_licenses_a_protected_key(self, world, monkeypatch):
        from construct.arc.executor import arc_protected_keys
        monkeypatch.setenv("CONSTRUCT_WORLD_RESHAPE", "1")
        monkeypatch.setattr("construct.resolution.draw_tier",
                            lambda *a, **k: "complete_success")
        arc = make_arc()
        assert ("fact:secret", "culprit") in arc_protected_keys(arc)  # the target IS protected
        seed_arc(world, arc)
        # the narrator's prose restates the reshaped (protected) fact → it must PROMOTE
        world._extractions.append({"items": [
            {"entity": "fact:secret", "attribute": "culprit", "value": "person:newculprit"}]})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": True,
             "uncertain_of": "whether the truth itself can be rewritten"},          # classify
            {"is_reshape": True, "slug": "culprit_rewritten",
             "target": {"entity": "fact:secret", "attribute": "culprit",
                        "value": "person:newculprit"},
             "restage": [], "frame_knowledge": [], "consequence": [],
             "summary": "Reality bends — the rival was never the one."},            # propose_reshape
            # author_replan fires on the landed reshape; a beatless proposal → no_replacement,
            # so the arc does NOT swap and the protected-key gate is exercised on arc:main.
            {"protagonist": PLAYER, "delta_type": "desire_at_cost",
             "tension": [PLAYER, "drive:comfort", "drive:truth"], "beats": [],
             "hook": "nothing coherent to chase"},                                  # author_replan (gen)
            {"prose": "The world reshapes; it was person:newculprit all along."},   # narrate
        ])
        result = run_turn(world, arc, provider,
                          "I will the truth itself to change.", turn=1)
        trace = result.trace
        assert "bends" in trace.reshape                              # narrator briefed
        assert trace.replanned == ""                                 # no_replacement → arc unchanged
        assert "arc:main" in trace.arc_fallout                       # explicit old-main-arc fallout fired
        # the reshaped protected key COMMITTED to canon (append, current read flips)...
        assert world.porcelain.state(
            "fact:secret", "culprit")["fact"]["value"] == "person:newculprit"
        # ...and the narrator's restatement PROMOTED past the protected gate (licensed),
        # rather than being quarantined as an unearned protected-key assertion.
        assert ("fact:secret", "culprit") not in trace.quarantined
        assert ("fact:secret", "culprit") not in trace.contradictions

    def test_flag_on_landed_reshape_replans_the_main_arc(self, world, monkeypatch):
        # The full step-4 path: a landed reshape → author_replan returns a coherent arc →
        # replan_main_arc swaps the live main arc mid-story (fresh id, no episode boundary).
        from construct.arc import io as arc_io
        monkeypatch.setenv("CONSTRUCT_WORLD_RESHAPE", "1")
        monkeypatch.setattr("construct.resolution.draw_tier",
                            lambda *a, **k: "complete_success")
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": True,
             "uncertain_of": "whether the victim can be brought back"},             # classify
            {"is_reshape": True, "slug": "victim_revived",
             "target": {"entity": "person:rival", "attribute": "alive", "value": "true"},
             "restage": [], "frame_knowledge": [], "consequence": [],
             # restage the revived NPC — an entity the replacement arc below does NOT reference,
             # so the scope refresh (Cx 215/216 #2) must pull it in from the committed rows.
             "restage": [{"entity": "person:rival", "attribute": "in", "value": "place:study"}],
             "summary": "The victim draws breath — the case is no longer a murder."},  # propose_reshape
            {"protagonist": PLAYER, "delta_type": "desire_at_cost",
             "tension": [PLAYER, "drive:doubt", "drive:resolve"],
             "beats": [{"id": "beat:confront_attacker", "phase": "climax",
                        "weight": "required", "kind": "event_occurs",
                        "entity": "attacker_named", "attribute": "", "value": ""}],
             "hook": "Now: who tried to kill him?"},                                # author_replan (gen)
            {"prose": "He breathes. The question changes: who wanted him dead?"},    # narrate
        ])
        result = run_turn(world, arc, provider, "I pour everything into reviving him.", turn=1)
        assert result.trace.replanned == "arc:replan_1"             # the arc re-aimed mid-story
        # the new main arc is installed (mid-episode; no episode boundary)
        reads = PorcelainWorldReads(world)
        assert arc_io.main_arc_from_frame(reads) == "arc:replan_1"
        assert not reads.events(kind="episode_start", frame="session:main")
        # the restaged revived NPC is committed + locatable (carried by the refreshed scope)
        assert world.porcelain.state("person:rival", "alive")["fact"]["value"] == "true"
        assert "place:study" in (reads.location_chain("person:rival") or [])

    def test_flag_off_is_inert(self, world, monkeypatch):
        monkeypatch.setattr("construct.resolution.draw_tier",
                            lambda *a, **k: "complete_success")
        # no CONSTRUCT_WORLD_RESHAPE → apply_reshape returns None; the turn is normal.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": True,
             "uncertain_of": "whether the truth can be rewritten"},               # classify
            {"prose": "You strain against the truth, but it is what it is."},      # narrate
        ])
        result = run_turn(world, arc, provider, "I will the truth to change.", turn=1)
        assert result.trace.reshape == ""                            # no reshape fired
        assert world.porcelain.state(
            "fact:secret", "culprit")["fact"]["value"] == "person:rival"  # untouched

    def test_flag_on_failure_tier_commits_consequence_without_flipping_target(self, world, monkeypatch):
        # Cx 207 note #1: integrated proof that a FAILURE tier commits a concrete
        # consequence but does NOT flip the target fact ("however it lands").
        monkeypatch.setenv("CONSTRUCT_WORLD_RESHAPE", "1")
        monkeypatch.setattr("construct.resolution.draw_tier",
                            lambda *a, **k: "terrible_failure")
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": True,
             "uncertain_of": "whether the truth can be rewritten"},               # classify
            {"is_reshape": True, "slug": "culprit_rewritten",
             "target": {"entity": "fact:secret", "attribute": "culprit",
                        "value": "person:newculprit"},
             "restage": [], "frame_knowledge": [],
             "consequence": [{"entity": "person:rival", "attribute": "mood",
                              "value": "rattled"}],
             "summary": "The truth resists — but the rival is rattled by the attempt."},  # propose_reshape
            {"prose": "You strain; nothing changes, but the rival looks rattled."},        # narrate
        ])
        result = run_turn(world, arc, provider, "I will the truth to change.", turn=1)
        assert result.trace.reshape                                  # the attempt happened
        # target NOT flipped (failure tier)...
        assert world.porcelain.state(
            "fact:secret", "culprit")["fact"]["value"] == "person:rival"
        # ...but the concrete consequence DID commit upstream
        assert world.porcelain.state("person:rival", "mood")["fact"]["value"] == "rattled"
