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
from construct.turnloop import run_turn as _run_turn

# NB the malformed-id / narrator-voice predicate tests moved to tests/test_resolve.py (the predicates
# now live in construct/resolve.py; the promote-gate copies were stripped — verified-then-strip, Cx 313).


def run_turn(*args, **kwargs):
    """Test wrapper: run a full turn INCLUDING the deferred post-narrate `settle`
    bookkeeping (TURN-LATENCY dumbfire). Production runs `settle` post-send in the
    adapter; these turn-loop tests assert on the tail's effects (canon promotion,
    quarantine, mirror, transcript, turn row), so they complete the turn here."""
    result = _run_turn(*args, **kwargs)
    if getattr(result, "settle", None) is not None:
        result.settle()
    return result


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
    w._stub = stub          # expose for model-call assertions (durability-classify counting)
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


class TestSettleDeferral:
    def test_settle_defers_canon_write_until_called(self, world):
        """TURN-LATENCY dumbfire: run_turn returns the prose immediately but HOLDS the
        post-narrate bookkeeping (extract→canon promotion, the turn row) in a `settle`
        callable. The narrator-asserted fact and the turn row land ONLY when settle()
        runs — which the adapter triggers AFTER sending the reply, so the PB writes
        overlap the player reading instead of padding the wait."""
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})                       # player input
        world._extractions.append({"items": [                          # narrator prose
            {"entity": "obj:lamp", "attribute": "kind", "value": "object"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "A lamp sits on the desk, newly noticed."},
        ])
        # NB: the raw run_turn (NOT the settle-completing test wrapper) so we can observe
        # the BEFORE state.
        result = _run_turn(world, arc, provider, "I look at the desk.", turn=1)
        assert "lamp" in result.prose                       # prose ships immediately
        assert callable(result.settle)                      # the LM finalization is deferred
        # The TURN-INTEGRITY RECEIPT is SYNCHRONOUS (durable before sendback): the turn row
        # next_turn_number reads + the archive of what was delivered are present immediately,
        # so a crash in the settle window can never lose/collide the delivered turn.
        assert len(world.porcelain.events(kind="turn", frame="session:main")) == 2  # turn_0 + this
        assert world.porcelain.state(
            "arch:turn_1", "prose", frame="session:main")["status"] == "known"
        # But the LM-bearing finalization (promoting the narrator's new fact to canon) is DEFERRED.
        assert world.porcelain.state("obj:lamp", "kind")["status"] != "known"
        result.settle()
        # AFTER settle: the deferred future-feeding writes have landed
        assert world.porcelain.state("obj:lamp", "kind")["status"] == "known"

    def test_sync_receipt_makes_no_durability_model_call(self, world):
        """Cx 268: the synchronous pre-send receipt/archive must NOT touch the durability
        MODEL (else a model call lands back before the reply ships). It is written with
        `classify="rules"` (deterministic, model=False). Guard the property directly: the
        receipt/archive row shape costs ZERO durability-classifier model calls."""
        def _durability_calls():
            return sum(1 for p, _s in world._stub.calls
                       if p.startswith("Classify the lifetime"))
        rows = [
            {"entity": "event:turn_9", "attribute": "kind", "value": "turn"},
            {"entity": "event:turn_9", "attribute": "pacing", "value": "steady"},
            {"entity": "event:turn_9", "attribute": "player_boundary", "value": "ok"},
            {"entity": "arch:turn_9", "attribute": "player_said", "value": "I look around."},
            {"entity": "arch:turn_9", "attribute": "prose", "value": "A lamp sits there."},
        ]
        before = _durability_calls()
        world.porcelain.ingest_structured(rows, frame="session:main", classify="rules")
        assert _durability_calls() == before        # rules mode → no model call (the fix)


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

    def test_dropping_a_held_object_commits_it_into_the_scene(self, world):
        # FOUNDER cohesion test: "set the letter-opener down" narrated but canon kept it held →
        # it snapped back to the pocket next turn. A drop of a HELD object now commits obj.in =
        # current place, so it STAYS where it was left.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "obj:opener", "attribute": "kind", "value": "object"},
                                 {"entity": "obj:opener", "attribute": "name", "value": "opener"},
                                 {"entity": "obj:opener", "attribute": "in", "value": PLAYER}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "drops": "opener"},
            {"prose": "You set the opener on the desk."},
        ])
        result = run_turn(world, arc, provider, "I set the opener down on the desk.", turn=2,
                          scope=[PLAYER, "obj:opener", "place:study"])
        assert result.trace.dropped == "obj:opener"
        assert world.porcelain.locate("obj:opener")[0] == "place:study"  # left in place, not held

    def test_deterministic_drop_wins_over_player_input_container(self, world):
        # Cx 295 BLOCK: the PLAYER-INPUT extraction runs BEFORE the deterministic drop and may write
        # the held object into a container it names ("set the pencil down on a table" →
        # `obj:pencil in obj:table`, an unlocated furniture entity). That defeated the drop's
        # "is it still held?" check, stranding the object under an unlocated table. The drop now reads
        # the PRE-extraction held view and is authoritative: it commits `obj in pre_scene`.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "obj:pencil", "attribute": "kind", "value": "pencil"},
                                 {"entity": "obj:pencil", "attribute": "name", "value": "pencil"},
                                 {"entity": "obj:pencil", "attribute": "in", "value": PLAYER}])
        # player-input extraction (FIRST) relocates the held pencil into a named, UNLOCATED container
        world._extractions.append({"items": [
            {"entity": "obj:pencil", "attribute": "in", "value": "obj:table"}]})
        world._extractions.append({"items": []})                       # narrator prose
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "drops": "pencil",
             "asserts_or_reveals": True},
            {"prose": "You set the pencil down on a table."},
        ])
        result = run_turn(world, arc, provider, "I set the pencil down on a table.", turn=2,
                          scope=[PLAYER, "obj:pencil", "place:study"])
        assert result.trace.dropped == "obj:pencil"                    # deterministic drop fired
        assert world.porcelain.locate("obj:pencil")[0] == "place:study"  # in the scene, not obj:table

    def test_drop_resolves_to_the_held_twin_not_a_fragmented_namesake(self, world):
        # Cx 297 follow-on (found live): the take-mint made a collision-avoiding twin — the player
        # HOLDS `obj:pencil_1` while a same-named `obj:pencil` sits elsewhere. Global `refer("the
        # pencil")` picked the un-held `obj:pencil`, so the drop's held-check failed and the pencil
        # followed the player. The drop now resolves the phrase against the HELD set first (you can
        # only set down what you hold), so it drops the twin actually in hand.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([
            {"entity": "obj:pencil", "attribute": "kind", "value": "pencil"},      # un-held namesake
            {"entity": "obj:pencil", "attribute": "in", "value": "obj:desk"},
            {"entity": "obj:pencil_1", "attribute": "kind", "value": "pencil"},     # the HELD twin
            {"entity": "obj:pencil_1", "attribute": "in", "value": PLAYER}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "drops": "the pencil"},
            {"prose": "You lay the pencil on the counter."},
        ])
        result = run_turn(world, arc, provider, "I set the pencil down.", turn=2,
                          scope=[PLAYER, "obj:pencil", "obj:pencil_1", "place:study"])
        assert result.trace.dropped == "obj:pencil_1"                    # the HELD twin, not the namesake
        assert world.porcelain.locate("obj:pencil_1")[0] == "place:study"  # left in the scene
        assert PLAYER not in (world.porcelain.locate("obj:pencil_1") or [])  # no longer held

    def test_drop_briefs_narrator_object_no_longer_carried(self, world):
        # Cx 299 non-blocking: after a drop, the narrator re-narrated the dropped object as still
        # pocketed (pulled from transcript memory) because nothing told it the object had left the
        # player's hands. The carry briefing is now EXCLUSIVE and a JUST SET DOWN line names the
        # dropped object + where it stays — so the render doesn't put it back in hand next turn.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "obj:opener", "attribute": "kind", "value": "object"},
                                 {"entity": "obj:opener", "attribute": "name", "value": "opener"},
                                 {"entity": "obj:opener", "attribute": "in", "value": PLAYER},
                                 {"entity": "obj:lamp", "attribute": "kind", "value": "object"},
                                 {"entity": "obj:lamp", "attribute": "name", "value": "lamp"},
                                 {"entity": "obj:lamp", "attribute": "in", "value": PLAYER}])  # still carried
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "drops": "opener"},
            {"prose": "You set the opener on the desk."},
        ])
        result = run_turn(world, arc, provider, "I set the opener down on the desk.", turn=2,
                          scope=[PLAYER, "obj:opener", "obj:lamp", "place:study"])
        assert result.trace.dropped == "obj:opener"
        brief = _narrate_prompt(provider)
        assert "JUST SET DOWN" in brief                    # narrator told it left the hands
        assert "EXCLUSIVE" in brief                         # carry list (still holds lamp) is authoritative

    def test_pronoun_phantom_holder_binds_to_protagonist(self, world):
        # ENTITY-AUTHORITY (Cx 304, pin-9 inversion): extraction minted `obj.in = person:you` (a
        # pronoun phantom). The RESOLVER now binds deixis ("you") to the protagonist at the write
        # boundary, so the row becomes `obj:opener in <protagonist>` (stays held) — not a stranded
        # phantom holder. Outcome preserved; enforcement moved from the gate band-aid to the resolver.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "obj:opener", "attribute": "kind", "value": "object"},
                                 {"entity": "obj:opener", "attribute": "in", "value": PLAYER}])
        world._extractions.append({"items": []})                       # player input
        world._extractions.append({"items": [                          # narrator prose extraction
            {"entity": "obj:opener", "attribute": "in", "value": "person:you", "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You turn the opener over in your hand."},
        ])
        result = run_turn(world, arc, provider, "I consider the opener I'm holding.", turn=2,
                          scope=[PLAYER, "obj:opener", "place:study"])
        assert world.porcelain.state("obj:opener", "in")["fact"]["value"] == PLAYER  # stays held
        assert "deixis_bound" in {r[2] for r in result.trace.resolver}  # resolver bound "you" → protagonist

    def test_malformed_slash_id_dropped_by_resolver(self, world):
        # ENTITY-AUTHORITY (Cx 304, pin-9 inversion): MALFORMED `:/` ids (`person:/you`,
        # `place:/coffee_house`) are dropped by the RESOLVER before staging; a row whose value is
        # malformed drops whole. Outcome: nothing malformed reaches canon.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})                       # player input
        world._extractions.append({"items": [                          # narrator prose extraction
            {"entity": "person:/you", "attribute": "in", "value": "place:/coffee_house", "value_type": "entity"},
            {"entity": "obj:teacup", "attribute": "in", "value": "place:/coffee_house", "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You step into the warm coffee house."},
        ])
        result = run_turn(world, arc, provider, "I go into the coffee house.", turn=2,
                          scope=[PLAYER, "place:study"])
        reads = PorcelainWorldReads(world)
        assert not reads.has_entity("person:/you")                      # never canonized
        assert not reads.has_entity("place:/coffee_house")
        assert not reads.has_entity("obj:teacup")                       # row dropped (malformed value)
        assert "dropped_malformed" in {r[2] for r in result.trace.resolver}

    def test_person_located_in_object_dropped_by_resolver(self, world):
        # ENTITY-AUTHORITY (Cx 304, pin-9 inversion): `protagonist in obj:street` (person located
        # INSIDE an object → the location desync) is dropped by the RESOLVER's kind expectation
        # (`person:*.in` must be a place/person, never obj). Player stays where they were.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "obj:street", "attribute": "kind", "value": "street"},
                                 {"entity": PLAYER, "attribute": "in", "value": "place:study"}])
        world._extractions.append({"items": []})                       # player input
        world._extractions.append({"items": [                          # narrator prose extraction
            {"entity": PLAYER, "attribute": "in", "value": "obj:street", "value_type": "entity"},
        ]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You stand in the wet street."},
        ])
        result = run_turn(world, arc, provider, "I look around the street.", turn=2,
                          scope=[PLAYER, "place:study", "obj:street"])
        assert world.porcelain.state(PLAYER, "in")["fact"]["value"] == "place:study"  # stays put
        assert "kind_mismatch" in {r[2] for r in result.trace.resolver}

    def test_player_self_naming_does_not_mint_a_present_npc(self, world):
        # FOUNDER live bug (2026-06-30, bodycase): "I am Bradford Clemense" minted
        # person:bradford_clemense as a present NPC (the room nodded toward "Bradford" not the player).
        # The PLAYER channel cannot conjure a person by fiat — the row is dropped, no phantom NPC.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": [                          # player-input extraction
            {"entity": "person:bradford_clemense", "attribute": "kind", "value": "person",
             "aliases": ["I", "Bradford Clemense"]},
            {"entity": "person:bradford_clemense", "attribute": "name", "value": "Bradford Clemense"},
        ]})
        world._extractions.append({"items": []})                       # narrator prose
        provider = StubProvider([
            {"kind": "declaration", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "asserts_or_reveals": True},
            {"prose": "The room regards your outburst warily."},
        ])
        run_turn(world, arc, provider, "I am Bradford Clemense as you well know.", turn=2,
                 scope=[PLAYER, "place:study"])
        assert not PorcelainWorldReads(world).has_entity("person:bradford_clemense")  # no phantom NPC

    def test_player_chosen_identity_is_authoritative_in_briefing(self, world):
        # FOUNDER 2026-06-30 ("player name wins, fully"): the player's interview-set identity must be
        # AUTHORITATIVE in the narrate briefing — name + pronouns + background, read from the canon
        # point-read (state()), not the player-frame YOU block. (The dirty-slot stale-name coexistence
        # — where snapshot-collapse mis-picks "Miss Vale" but state() serves the player — is NOT
        # injected here; it's verified on the live bodycase slot, Cx 320/322.)
        arc = make_arc()
        seed_arc(world, arc)
        # canon (where the Foyer writes), read via the folded point-read state() — NOT the player-frame
        # snapshot (which misses these) nor the snapshot-collapse dict (which mis-picks set-valued name;
        # the stale-name divergence is verified on the live bodycase slot — Cx 320).
        world.ingest_structured([
            {"entity": PLAYER, "attribute": "name", "value": "Reese Okonkwo", "valid_from": 0.0},
            {"entity": PLAYER, "attribute": "pronouns", "value": "they/them", "valid_from": 0.0},
            {"entity": PLAYER, "attribute": "background",
             "value": "a night-indexer who took the post to bury a file", "valid_from": 0.0}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You consider the room."},
        ])
        run_turn(world, arc, provider, "I look around.", turn=2, scope=[PLAYER, "place:study"])
        brief = _narrate_prompt(provider)
        assert "THE PLAYER CHARACTER IS Reese Okonkwo" in brief
        assert "they/them" in brief
        assert "night-indexer who took the post to bury a file" in brief  # background carried (canon, not YOU block)
        assert "stale authored default" in brief        # supersession instruction present

    def test_narrator_may_not_relocate_a_held_object(self, world):
        # FOUNDER live cohesion bug: a player-held object relocated by NARRATOR prose into furniture
        # (`obj:pencil in obj:desk`) AND a narrator-phantom variant (`obj:token in
        # person:unknown_narrator`). The phantom-holder row is dropped by the RESOLVER (voice); the
        # held→furniture relocation is caught by the promote-gate held-object guard. Both stay held.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "obj:pencil", "attribute": "kind", "value": "pencil"},
                                 {"entity": "obj:pencil", "attribute": "name", "value": "pencil"},
                                 {"entity": "obj:pencil", "attribute": "in", "value": PLAYER}])
        world._extractions.append({"items": []})                       # player input
        world._extractions.append({"items": [                          # narrator prose extraction
            {"entity": "obj:pencil", "attribute": "in", "value": "obj:desk", "value_type": "entity"},
            {"entity": "obj:token", "attribute": "in", "value": "person:unknown_narrator", "value_type": "entity"},
        ]})
        world.ingest_structured([{"entity": "obj:token", "attribute": "kind", "value": "token"},
                                 {"entity": "obj:token", "attribute": "name", "value": "token"},
                                 {"entity": "obj:token", "attribute": "in", "value": PLAYER}])
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You glance over the desk, the pencil still in your hand."},
        ])
        result = run_turn(world, arc, provider, "I look over my desk.", turn=2,
                          scope=[PLAYER, "obj:pencil", "obj:token", "place:study"])
        assert world.porcelain.state("obj:pencil", "in")["fact"]["value"] == PLAYER  # stays held
        assert world.porcelain.state("obj:token", "in")["fact"]["value"] == PLAYER   # stays held
        assert "dropped_voice" in {r[2] for r in result.trace.resolver}  # phantom holder dropped by resolver
        assert world.porcelain.state("obj:pencil", "in")["fact"]["value"] == PLAYER  # stays held
        assert world.porcelain.state("obj:token", "in")["fact"]["value"] == PLAYER

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

    def test_declaration_commitment_not_denied_in_pure_mode(self, world):
        # #2: a conclusory accusation that parses as a DECLARATION ("It was Julian — he killed
        # his uncle") must NOT be stonewalled by the canon-strict declaration-denial as illegal
        # fact-authoring. With commits=True it is the player NAMING their conclusion — it must
        # reach the commitment path (judge → conclude), not return the "you can't author" message.
        from construct.arc.executor import turn_time
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured(
            [{"entity": "beat:discover", "attribute": "status", "value": "achieved",
              "valid_from": turn_time(3)}], frame="plot:main")
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "declaration", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "names the rival as the killer"},
            {"grade": "vindicated", "rationale": "matches the culprit"},
            {"prose": "You name the rival; the room stills."},
        ])
        result = run_turn(world, arc, provider, "It was the rival. He did it.",
                          turn=5, scenario_mode="win_loss", mode="pure",
                          scope=["fact:secret", "person:rival", PLAYER, "place:study"])
        # NOT the canon-strict denial; the commitment path ran and concluded.
        assert "canon-strict" not in (result.prose or "")
        assert result.trace.commitment and result.trace.terminal is True

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

    def test_npc_turn_directs_present_npc_to_stay_available(self):
        # PRESENCE-HOLD (founder, live): a present NPC must not exit the scene of its own
        # accord before the player can engage — the npc_turn cohort carries the STAY
        # AVAILABLE directive, and the peopled render directive holds presence.
        from construct import cohorts
        provider = StubProvider([
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
        ])
        cohorts.npc_turn(provider, "person:steward", "{}", "{}", "person:pc")
        prompt = provider.calls[-1][0]
        assert "STAY AVAILABLE" in prompt
        assert "do not leave" in prompt.lower() and "self-removal" in prompt.lower()
        # the runtime render directive holds presence on the narrator side too
        assert "PRESENCE HOLDS" in cohorts.WORLD_IS_PEOPLED
        assert "do not arrive and leave in the same breath" in cohorts.WORLD_IS_PEOPLED

    def test_render_leash_carries_object_permanence(self):
        # FOUNDER live bug: the player plucked a fibre off the boy, but later turns kept
        # re-narrating it on his sleeve. The narrator must honor a completed player action
        # on an object (taken/moved/opened) as persistent — CONTINUITY OF STATE.
        from construct import cohorts
        assert "CONTINUITY OF STATE" in cohorts.RENDER_LEASH
        assert "back where it was" in cohorts.RENDER_LEASH
        assert "Honor the player's completed actions" in cohorts.RENDER_LEASH

    def test_render_style_forbids_fixating_on_established_detail(self):
        # FOUNDER live bug: the narrator re-described the same clue (the silk tape / fibre) in
        # florid detail EVERY turn ("why do you keep fixating on it!?"). An established detail is
        # known; don't re-litigate it turn after turn — answer the current question.
        from construct import cohorts
        assert "DON'T FIXATE" in cohorts.RENDER_STYLE
        assert "already seen and engaged" in cohorts.RENDER_STYLE.lower() or \
               "ALREADY seen and engaged" in cohorts.RENDER_STYLE
        assert "ANSWER WHAT THEY ASKED" in cohorts.RENDER_STYLE

    def test_destination_directive_carries_foreshadow_restraint(self, world):
        # FOUNDER live (the "poltergeist fibers everywhere / NPCs acting weird" fixation, mechanical):
        # the foreshadow card must lay the trail SPARINGLY and NOT re-plant a clue the player has
        # already seen — else the narrator re-surfaces the same prop every turn and bends NPCs to it.
        from construct.adapter import PorcelainWorldReads
        from construct.turnloop import _destination_directive
        arc = make_arc()
        seed_arc(world, arc)
        d = _destination_directive(arc, PorcelainWorldReads(world))
        assert "THE HIDDEN DESTINATION" in d        # arc conceals → the card is present
        assert "RESTRAINT" in d
        assert "re-plant" in d
        assert "MOST turns plant nothing new" in d

    def test_taking_an_ordinary_improv_object_grants_world_permanence(self, world):
        # FOUNDER: "a mug from the bar doesn't not exist." A take of an ORDINARY object that
        # isn't an established canon entity mints a fresh obj held by the player — it exists
        # and persists. (The equipment_check gate, manner='take', says ordinary → grant.)
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})       # player input
        world._extractions.append({"items": []})       # post-render
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "takes": "a mug"},
            {"ordinary_equipment": True, "item_id": "obj:mug",
             "reason": "an ordinary mug plainly present"},                  # equipment_check(take)
            {"prose": "You lift a chipped mug from the bar."},
        ])
        result = run_turn(world, arc, provider, "I take a mug from the bar.", turn=2,
                          scope=[PLAYER, "place:study"])
        assert result.trace.took and result.trace.took.startswith("obj:")   # something was granted
        held = world.porcelain.contents(PLAYER)
        assert result.trace.took in held                                    # held by the player now
        assert world.porcelain.state(
            result.trace.took, "in")["fact"]["value"] == PLAYER             # and persisted in canon

    def test_take_binds_a_present_object_not_a_twin(self, world):
        # ENTITY AUTHORITY (Cx 304 minter unification): a take of an object ALREADY present in the
        # scene binds THAT entity instead of minting a sibling. The live twin bug: a scene `obj:pencil`
        # existed but `refer("plain pencil")` missed it by name, so the take minted `obj:pencil_1`. The
        # bounded token matcher now binds the present pencil — no twin, no equipment_check mint call.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "obj:pencil", "attribute": "kind", "value": "object"},
                                 {"entity": "obj:pencil", "attribute": "name", "value": "pencil"},
                                 {"entity": "obj:pencil", "attribute": "in", "value": "place:study"}])
        world._extractions.append({"items": []})       # player input
        world._extractions.append({"items": []})       # post-render
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "takes": "the plain pencil"},
            {"prose": "You pick up the plain pencil from the desk."},   # NB no equipment_check stub:
        ])                                                              # binding must not reach the minter
        result = run_turn(world, arc, provider, "I take the plain pencil.", turn=2,
                          scope=[PLAYER, "obj:pencil", "place:study"])
        assert result.trace.took == "obj:pencil"                        # bound the present object
        assert world.porcelain.state("obj:pencil", "in")["fact"]["value"] == PLAYER  # now held
        reads = PorcelainWorldReads(world)
        assert not reads.has_entity("obj:pencil_1")                     # no twin minted
        assert not reads.has_entity("obj:plain_pencil")

    def test_ambiguous_take_does_not_mint_a_sibling(self, world):
        # Cx 306 blocker 1: two same-named present objects + "take the pencil" must NOT mint a third.
        # The take's bind_or_mint returns ambiguous; the caller must only mint on `_why == "mint"`.
        # No equipment_check stub — reaching the minter would exhaust the queue and error.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([
            {"entity": "obj:pencil_a", "attribute": "kind", "value": "object"},
            {"entity": "obj:pencil_a", "attribute": "name", "value": "pencil"},
            {"entity": "obj:pencil_a", "attribute": "in", "value": "place:study"},
            {"entity": "obj:pencil_b", "attribute": "kind", "value": "object"},
            {"entity": "obj:pencil_b", "attribute": "name", "value": "pencil"},
            {"entity": "obj:pencil_b", "attribute": "in", "value": "place:study"}])
        world._extractions.append({"items": []})       # player input
        world._extractions.append({"items": []})       # post-render
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "takes": "the pencil"},
            {"prose": "You reach toward the pencils on the desk."},
        ])
        result = run_turn(world, arc, provider, "I take the pencil.", turn=2,
                          scope=[PLAYER, "obj:pencil_a", "obj:pencil_b", "place:study"])
        assert not result.trace.took                                     # nothing grabbed (ambiguous)
        reads = PorcelainWorldReads(world)
        assert not reads.has_entity("obj:pencil")                        # no third sibling minted
        assert not reads.has_entity("obj:pencil_1")
        assert any(r[2] == "ambiguous" for r in result.trace.resolver)

    def test_free_text_does_not_retype_or_split_a_place(self, world):
        # Cx 306 blocker 2: the DIRECT player-input path writes resolved rows straight to canon. An
        # extracted `obj:street kind object` while `place:street` exists must NOT retype place:street
        # to "object" nor mint a separate obj:street — the bound-kind drop + no-free-text-place-mint.
        arc = make_arc()
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "place:street", "attribute": "kind", "value": "street"},
                                 {"entity": "place:street", "attribute": "name", "value": "street"}])
        world._extractions.append({"items": [                          # PLAYER-INPUT extraction (direct→canon)
            {"entity": "obj:street", "attribute": "kind", "value": "object"},
        ]})
        world._extractions.append({"items": []})                       # post-render
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "asserts_or_reveals": True},
            {"prose": "You look down the wet street."},
        ])
        run_turn(world, arc, provider, "I study the street.", turn=2,
                 scope=[PLAYER, "place:street"])
        # place:street keeps its kind; never retyped to 'object'; no obj:street twin created
        assert world.porcelain.state("place:street", "kind")["fact"]["value"] == "street"
        assert not PorcelainWorldReads(world).has_entity("obj:street")

    def test_a_load_bearing_take_is_not_minted_by_fiat(self, world):
        # The gate denies a SPECIFIC/load-bearing object: "take the vault key" is not granted
        # into existence — the narrator handles it honestly. No phantom obj is minted.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "takes": "the iron vault key"},
            {"ordinary_equipment": False, "item_id": "", "reason": "load-bearing artifact"},
            {"prose": "There is no such key here to take."},
        ])
        result = run_turn(world, arc, provider, "I take the iron vault key.", turn=2,
                          scope=[PLAYER, "place:study"])
        assert not result.trace.took                                        # nothing granted
        assert not [h for h in world.porcelain.contents(PLAYER) if h.startswith("obj:")]

    def test_secret_take_guard_locks_a_short_protected_object_id(self, world):
        # Cx 272 (the load-bearing bypass): the take grant's deterministic guard must catch a
        # take that NAMES a protected arc object even via a SHORT id ("the map" → obj:map) that
        # slipped the old >3-char token filter — so it can't be minted by fiat past the
        # arc-blind model gate. Also: an ordinary unrelated take is NOT locked.
        from construct.turnloop import _take_touches_secret
        from construct.adapter import PorcelainWorldReads
        from construct.arc.conditions import InFrame
        from construct.arc.grammar import Beat, Phase, Weight
        arc = replace(make_arc(), beats=(
            Beat("beat:find", Phase.CRISIS, Weight.REQUIRED,
                 achievable_via=InFrame(PLAYER_FRAME, "obj:map", "in", "place:study")),
            Beat("beat:cipher", Phase.CRISIS, Weight.REQUIRED,
                 achievable_via=InFrame(PLAYER_FRAME, "fact:secret", "cipher", "red/map")),))
        seed_arc(world, arc)
        world.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "cipher", "value": "red/map"}])
        reads = PorcelainWorldReads(world)
        # entity-id path (short protected object id), with punctuation (Cx 272/274)
        assert _take_touches_secret("the map", arc, reads) is True
        assert _take_touches_secret("the map!", arc, reads) is True
        assert _take_touches_secret("the map?", arc, reads) is True
        assert _take_touches_secret("grab map; now", arc, reads) is True
        # attr/VALUE path with punctuation IN the value ("red/map") — Cx 276
        assert _take_touches_secret("take red map", arc, reads) is True
        assert _take_touches_secret("red/map", arc, reads) is True
        assert _take_touches_secret("red map!", arc, reads) is True
        assert _take_touches_secret("a mug from the bar", arc, reads) is False  # ordinary → free

    def test_carried_objects_surface_to_the_narrator(self, world):
        # Object permanence: what the player holds is told to the narrator, so it can't
        # re-narrate a held thing back where it came from (the fibre-on-the-sleeve bug).
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "obj:lantern", "attribute": "kind", "value": "object", "timeless": True},
            {"entity": "obj:lantern", "attribute": "in", "value": PLAYER, "value_type": "entity"},
            {"entity": "obj:lantern", "attribute": "name", "value": "brass lantern"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You look about the study, the lantern warm in your hand."},
        ])
        run_turn(world, arc, provider, "I look around.", turn=2, scope=[PLAYER, "place:study"])
        prompt = _narrate_prompt(provider)
        assert "WHAT YOU ARE CARRYING" in prompt
        assert "brass lantern" in prompt

    def test_open_scene_grounding_zooms_in_and_holds_the_call(self):
        # CHARACTER-GROUNDING P3: a grounding open zooms into the player's inhabited space and
        # does NOT surface the call-to-action; the non-grounding open lets it arise.
        from construct import cohorts
        prov = StubProvider([{"prose": "You stand in your office, ledgers at your elbow."}])
        cohorts.open_scene(prov, "BRIEF", "person:pc", grounding=True)
        gp = prov.calls[-1][0]
        assert "ZOOM INTO THEIR INHABITED SPACE" in gp
        assert "Do NOT surface the case" in gp
        prov2 = StubProvider([{"prose": "x"}])
        cohorts.open_scene(prov2, "BRIEF", "person:pc", grounding=False)
        assert "LET THE CALL TO ACTION ARISE" in prov2.calls[-1][0]

    def test_grounding_runway_holds_the_call_on_the_first_turn(self, world):
        # CHARACTER-GROUNDING P4: the first play turn briefs the narrator to keep it grounded and
        # hold the inciting incident; a later turn does not.
        arc = make_arc()
        seed_arc(world, arc)
        for _ in range(4):
            world._extractions.append({"items": []})
        prov = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You take in your study, the lamp low."},
        ])
        run_turn(world, arc, prov, "I look around.", turn=1, scope=[PLAYER, "place:study"])
        assert "GROUNDING RUNWAY" in _narrate_prompt(prov)
        prov2 = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "The study again."},
        ])
        run_turn(world, arc, prov2, "I look around.", turn=2, scope=[PLAYER, "place:study"])
        assert "GROUNDING RUNWAY" not in _narrate_prompt(prov2)

    def test_move_to_an_improv_place_commits_the_relocation(self, world):
        # FOUNDER live: "I said I went to Harrow's office" but canon kept me at the post office. A
        # move to a NAMED place that doesn't resolve to canon now MINTS it + commits protagonist.in,
        # so the next turn renders the NEW scene (not the stale prior one with the wrong cast).
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the bell yard office", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
            {"verdict": "new", "match": ""},        # Cx 354 A: semantic bind fires, says new → mint
            {"prose": "You climb the steep stair to the office."},
        ])
        run_turn(world, arc, provider, "I go to the bell yard office.", turn=2,
                 scope=[PLAYER, "place:study"])
        chain = world.porcelain.locate(PLAYER)
        assert chain and chain[0].startswith("place:")
        assert chain[0] != "place:study"          # actually relocated, not stuck at the old scene
        assert "office" in chain[0]

    def test_move_secret_guard_ignores_descriptive_clue_words(self, world):
        # FOUNDER live cohesion bug (2026-06-29): the move-mint reused the broad secret-TAKE guard,
        # whose vocabulary is polluted by common words from DESCRIPTIVE clue values — a clue like
        # "the old lodging house" put "house" in the secret set, blocking walking to a "coffee house".
        # The narrow move guard blocks only the hidden ANSWER's entity-reference identities (the
        # culprit, the lair), never descriptive prose. This contrasts the two guards on the SAME world.
        from construct.turnloop import _take_touches_secret, _move_touches_secret
        from construct.arc.conditions import InFrame
        from construct.arc.grammar import Beat, Phase, Weight
        arc = replace(make_arc(), beats=(
            Beat("beat:hideout", Phase.CRISIS, Weight.REQUIRED,
                 achievable_via=InFrame(PLAYER_FRAME, "fact:hideout", "desc", "the old lodging house")),
        ) + make_arc().beats)
        seed_arc(world, arc)
        world.ingest_structured([{"entity": "fact:hideout", "attribute": "desc",
                                  "value": "the old lodging house"}])
        reads = PorcelainWorldReads(world)
        # the BROAD take-guard over-blocks on the descriptive "house"; the NARROW move-guard does not
        assert _take_touches_secret("the coffee house", arc, reads) is True
        assert _move_touches_secret("the coffee house", arc, reads) is False
        # both still refuse to conjure the hidden ANSWER's place (rival = the entity-ref culprit)
        assert _move_touches_secret("the rival's lair", arc, reads) is True

    def test_move_to_a_fixture_is_in_scene_not_travel(self, world):
        # Cx 325 / blind test: "step to the table" (a FIXTURE of the current scene) must NOT mint
        # place:table and walk the player out — it's in-scene repositioning. The colocated cast stays.
        from construct.turnloop import _dest_head, _FIXTURE_HEADS
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "name", "value": "Maud"},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the table", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": True, "intent": "answer the question",
             "line_hint": ""},                                          # witness npc_turn (she's PRESENT)
            {"prose": "You step to the table; Maud watches."},
        ])
        result = run_turn(world, arc, provider, "I step to the table and ask Maud what I'm looking at.",
                          turn=2, scope=[PLAYER, "person:witness", "place:study"])
        assert result.trace.movement_status == "in_scene"
        assert any(c.startswith("npc_turn") for c in result.trace.cohort_calls)  # witness present + active
        assert world.porcelain.locate(PLAYER)[0] == "place:study"          # did NOT leave the room
        assert not PorcelainWorldReads(world).has_entity("place:table")    # no fixture-place minted
        # the colocated witness stays present (the cast doesn't evaporate)
        assert world.porcelain.locate("person:witness")[0] == "place:study"

    def test_resolved_scene_object_move_does_not_commit_person_in_object(self, world):
        # Cx 327 BLOCK: if a same-scene obj:table already exists, refer("the table") RESOLVES it and
        # the resolved-target branch would commit person:player in obj:table (the person-in-object
        # desync / cast disappearance). The move path now gates commits to place: targets and absorbs
        # a resolved scene-object as in-scene — no location row, the colocated cast stays.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "obj:table", "attribute": "kind", "value": "object", "timeless": True},
            {"entity": "obj:table", "attribute": "name", "value": "table"},
            {"entity": "obj:table", "attribute": "in", "value": "place:study"},
            {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:witness", "attribute": "name", "value": "Maud"},
            {"entity": "person:witness", "attribute": "in", "value": "place:study"}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the table", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": True, "intent": "answer", "line_hint": ""},  # witness
            {"prose": "You go to the table; Maud is here."},
        ])
        result = run_turn(world, arc, provider, "I go to the table.", turn=2,
                          scope=[PLAYER, "obj:table", "person:witness", "place:study"])
        assert world.porcelain.locate(PLAYER)[0] == "place:study"   # NOT in obj:table
        assert result.trace.movement_status == "in_scene"
        assert world.porcelain.locate("person:witness")[0] == "place:study"  # cast stays present

    def test_person_id_fallback_is_title_cased(self):
        # Founder blind test: a nameless `person:` was addressed lowercase ("clara vale"). The slug
        # fallback now Title-Cases person ids (proper names); obj/place stay lowercase for prose.
        from construct.arc.executor import _human
        assert _human("person:clara_vale") == "Clara Vale"
        assert _human("person:edmund_reed") == "Edmund Reed"
        assert _human("obj:brass_token") == "brass token"      # object stays lowercase
        assert _human("place:bluegate_yard") == "bluegate yard"

    def test_dest_head_split(self):
        # head extraction + the block-list: fixtures absorb in-scene; everything else (place heads
        # AND unknown heads) travels, preserving improv travel ("Harrow's office", novel places).
        from construct.turnloop import _dest_head, _FIXTURE_HEADS
        assert _dest_head("the table") == "table" and "table" in _FIXTURE_HEADS
        assert _dest_head("the rain barrel by the shed") == "barrel" and "barrel" in _FIXTURE_HEADS
        # HEAD matters: "back lane by the sheds" → head 'lane' (a place), NOT a fixture → travels
        assert _dest_head("back lane by the warehouse sheds") == "lane"
        assert _dest_head("the coffee house on the corner") == "house"
        assert _dest_head("Harrow's office") == "office"
        assert not ({"lane", "house", "office"} & _FIXTURE_HEADS)        # place heads travel

    def test_move_reuses_authored_place_with_descriptive_kind(self, world):
        # Cx 325: a move to an authored place whose `kind` is DESCRIPTIVE ("yard", not literally
        # "place") must REUSE it, not mint a `_1` duplicate.
        from construct.turnloop import _grant_moved_place
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:bluegate_yard", "attribute": "kind", "value": "murder scene in a rain-wet yard"},
            {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"}])
        got, _seg = _grant_moved_place(world, PLAYER, "bluegate yard", at=2000.0)
        assert got == "place:bluegate_yard"                                 # reused, not bumped
        assert not PorcelainWorldReads(world).has_entity("place:bluegate_yard_1")

    def test_compound_destination_mints_contained_place(self, world):
        # #91 (Cx 387, the probe's parallel office): "the Liddell warehouse, to the foreman's
        # office" must mint the office NESTED IN the established warehouse — never a floating
        # top-level place that strands whoever is really there.
        from construct.turnloop import _embedded_container, _grant_moved_place
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:liddell_warehouse", "attribute": "kind", "value": "warehouse",
             "timeless": True},
            {"entity": "place:liddell_warehouse", "attribute": "name",
             "value": "the Liddell warehouse"},
            {"entity": "person:liddell", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:liddell", "attribute": "in", "value": "place:liddell_warehouse"},
        ])
        roster = [("place:liddell_warehouse", "the Liddell warehouse — warehouse"),
                  ("place:study", "study — room")]
        # the matcher: unique container + the non-matching tail
        assert _embedded_container("the Liddell warehouse, to the foreman's office", roster) \
            == ("place:liddell_warehouse", "the foreman's office")
        assert _embedded_container("the docks", roster) is None              # no brush
        assert _embedded_container("the Liddell warehouse", roster) is None  # IS the container
        got, _seg = _grant_moved_place(world, PLAYER,
                                       "the Liddell warehouse, to the foreman's office",
                                       at=2000.0, roster=roster)
        assert got == "place:foreman_s_office"
        chain = world.porcelain.locate(PLAYER)
        assert chain[0] == "place:foreman_s_office"
        assert "place:liddell_warehouse" in chain          # NESTED, not floating
        # the stranded-NPC failure mode is gone: the man in the warehouse shares the chain
        assert "place:liddell_warehouse" in world.porcelain.locate("person:liddell")

    def test_run_turn_compound_destination_wins_over_container_reuse(self, world):
        # #91 caller-order regression (Cx 390 blocker): on the REAL run_turn path the
        # known-place reuse token-matched the container and flattened the player INTO the
        # warehouse — the office never minted. Compound-contained detection must win:
        # the player ends in the NESTED office, and the man in the warehouse is present.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:liddell_warehouse", "attribute": "kind", "value": "warehouse",
             "timeless": True},
            {"entity": "place:liddell_warehouse", "attribute": "name",
             "value": "the Liddell warehouse"},
            {"entity": "person:liddell", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:liddell", "attribute": "in", "value": "place:liddell_warehouse"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the Liddell warehouse, to the foreman's office",
             "requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
             "commitment": "", "npcs_dismissed": [], "moved_with": [], "joins": []},
            # Liddell is colocated via the containment chain → his npc_turn fires
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "The foreman's office is close and sour with lamp-smoke."},
        ])
        r = run_turn(world, arc, provider,
                     "Reed and I go to the Liddell warehouse, to the foreman's office.",
                     turn=2, scope=[PLAYER, "place:study", "place:liddell_warehouse",
                                    "person:liddell"])
        assert r.trace.movement_status == "clear"
        chain = world.porcelain.locate(PLAYER)
        assert chain[0] == "place:foreman_s_office"            # the durable child scene
        assert "place:liddell_warehouse" in chain              # nested, not flattened
        # the container-only reuse path did NOT fire: the office exists as its own place
        assert PorcelainWorldReads(world).has_entity("place:foreman_s_office")

    def test_run_turn_compound_destination_blocked_route_no_commit(self, world, monkeypatch):
        # #91 caller-level route discipline (Cx 390): a blocked way to the container means
        # the compound move commits NOTHING — no office mint, player stays put.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:liddell_warehouse", "attribute": "kind", "value": "warehouse",
             "timeless": True},
            {"entity": "place:liddell_warehouse", "attribute": "name",
             "value": "the Liddell warehouse"},
        ])
        import construct.turnloop as tl
        monkeypatch.setattr(tl, "_route_obstruction", lambda *a, **k: {
            "status": "blocked", "via": "obj:gate",
            "evidence": [{"entity": "obj:gate", "attribute": "state", "value": "chained"}]})
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the Liddell warehouse, to the foreman's office",
             "requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
             "commitment": "", "npcs_dismissed": [], "moved_with": [], "joins": []},
            {"prose": "The river gate is chained fast."},
        ])
        r = run_turn(world, arc, provider,
                     "Through to the Liddell warehouse, to the foreman's office.",
                     turn=2, scope=[PLAYER, "place:study", "place:liddell_warehouse"])
        assert r.trace.movement_status == "blocked"
        assert world.porcelain.locate(PLAYER)[0] == "place:study"
        assert not PorcelainWorldReads(world).has_entity("place:foreman_s_office")

    def _tick_setup(self, world):
        from construct.cast import CastNode
        world.porcelain.ingest_structured([
            {"entity": "place:market", "attribute": "kind", "value": "market", "timeless": True},
            {"entity": "place:lane", "attribute": "kind", "value": "lane", "timeless": True},
            {"entity": "person:maud", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:maud", "attribute": "in", "value": "place:lane"},
            {"entity": "person:cray", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:cray", "attribute": "in", "value": "place:lane"},
        ])
        from construct.arc.executor import turn_time
        world.porcelain.ingest_structured([
            {"entity": "person:maud", "attribute": "last_seen_min", "value": 100.0,
             "valid_from": turn_time(1)},
            {"entity": "person:cray", "attribute": "last_seen_min", "value": 100.0,
             "valid_from": turn_time(1)},
        ], frame="session:main")
        cast = {
            "person:maud": CastNode("person:maud", surface_role="coster"),
            "person:cray": CastNode("person:cray", surface_role="foreman", is_culprit=True),
        }
        return cast

    def test_world_tick_moves_member_but_never_the_culprit(self, world):
        # #84 (Cx 395/396): an eligible off-screen member moves as ordinary canon; the
        # culprit's move is DROPPED (reachability by construction), never repaired.
        from construct.turnloop import TurnTrace, _world_tick
        arc = make_arc()
        seed_arc(world, arc)
        cast = self._tick_setup(world)
        trace = TurnTrace(turn=3)
        trace.movement_status = "clear"
        provider = StubProvider([{"ticks": [
            {"member": "person:maud", "kind": "moved",
             "detail": "wheeled her barrow across to the market", "moves_to": "place:market",
             "with_member": ""},
            {"member": "person:cray", "kind": "moved", "detail": "slipped off",
             "moves_to": "place:market", "with_member": ""},
        ]}])
        _world_tick(world, world.porcelain, arc, trace, provider, 3, cast=cast, npcs=[],
                    entry_scene="place:lane", scene="place:study",
                    live_reads=PorcelainWorldReads(world), minutes_now=200.0)
        assert world.porcelain.locate("person:maud")[0] == "place:market"
        assert world.porcelain.locate("person:cray")[0] == "place:lane"   # anchored
        assert trace.world_tick == ["person:maud:moved"]

    def test_world_tick_floor_and_unmet_and_leaks(self, world):
        # #84 teeth: below the elapsed floor → no call at all; never-met member → skipped;
        # a leaking `detail` (concealed vocabulary) → that tick dropped, clean one commits.
        from construct.turnloop import TurnTrace, _world_tick
        arc = make_arc()
        seed_arc(world, arc)
        cast = self._tick_setup(world)
        # below the floor: seen 10 minutes ago → the cohort is never consulted
        trace = TurnTrace(turn=3)
        trace.movement_status = "clear"
        provider = StubProvider([])
        _world_tick(world, world.porcelain, arc, trace, provider, 3, cast=cast, npcs=[],
                    entry_scene="place:lane", scene="place:study",
                    live_reads=PorcelainWorldReads(world), minutes_now=110.0)
        assert trace.world_tick == [] and not provider.calls
        # above the floor: the leaking detail ("the culprit…" brushes concealed vocabulary)
        # is dropped; the clean event commits as canon the notebook can never pre-know
        trace2 = TurnTrace(turn=4)
        trace2.movement_status = "clear"
        provider2 = StubProvider([{"ticks": [
            {"member": "person:maud", "kind": "sent_word",
             "detail": "sent word naming the culprit of the affair", "moves_to": "",
             "with_member": ""},
            {"member": "person:cray", "kind": "finished_task",
             "detail": "tallied the day's weights and locked the shed", "moves_to": "",
             "with_member": ""},
        ]}])
        _world_tick(world, world.porcelain, arc, trace2, provider2, 4, cast=cast, npcs=[],
                    entry_scene="place:lane", scene="place:study",
                    live_reads=PorcelainWorldReads(world), minutes_now=200.0)
        assert trace2.world_tick == ["person:cray:finished_task"]
        rows = [r for r in world.buffer.visible()
                if str(r.entity) == "event:tick_cray_4"]
        assert any(r.attribute == "kind" and r.value == "finished_task" for r in rows)
        assert not any(str(r.entity) == "event:tick_maud_4"
                       for r in world.buffer.visible())

    def test_world_tick_plot_only_place_never_a_destination(self, world):
        # Cx 398 blocker 1: `buffer.visible()` without a frame is UNFILTERED — a place that
        # exists only in plot:main must neither reach the prompt as a KNOWN PLACE nor be
        # accepted as a canon movement destination.
        from construct.turnloop import TurnTrace, _world_tick
        arc = make_arc()
        seed_arc(world, arc)
        cast = self._tick_setup(world)
        world.porcelain.ingest_structured(
            [{"entity": "place:vault", "attribute": "kind", "value": "hidden vault",
              "timeless": True}], frame="plot:main")
        trace = TurnTrace(turn=3)
        trace.movement_status = "clear"
        provider = StubProvider([{"ticks": [
            {"member": "person:maud", "kind": "moved", "detail": "slipped into the vault",
             "moves_to": "place:vault", "with_member": ""},
        ]}])
        _world_tick(world, world.porcelain, arc, trace, provider, 3, cast=cast, npcs=[],
                    entry_scene="place:lane", scene="place:study",
                    live_reads=PorcelainWorldReads(world), minutes_now=200.0)
        _wtk = next(p for (p, _s, _t) in provider.calls if task_of(p) == "wtk")
        assert "place:vault" not in _wtk                       # never offered to the model
        assert world.porcelain.locate("person:maud")[0] == "place:lane"   # never moved
        assert trace.world_tick == []

    def test_world_tick_met_with_player_patient_dropped(self, world):
        # Cx 398 blocker 2: off-screen action is never about the player — a met_with whose
        # patient is the protagonist (or any ineligible person) drops the whole meeting.
        from construct.turnloop import TurnTrace, _world_tick
        arc = make_arc()
        seed_arc(world, arc)
        cast = self._tick_setup(world)
        trace = TurnTrace(turn=3)
        trace.movement_status = "clear"
        provider = StubProvider([{"ticks": [
            {"member": "person:maud", "kind": "met_with",
             "detail": "waylaid the detective by the stair", "moves_to": "",
             "with_member": PLAYER},
        ]}])
        _world_tick(world, world.porcelain, arc, trace, provider, 3, cast=cast, npcs=[],
                    entry_scene="place:lane", scene="place:study",
                    live_reads=PorcelainWorldReads(world), minutes_now=200.0)
        assert trace.world_tick == []
        assert not any(str(r.entity).startswith("event:tick_maud")
                       for r in world.buffer.visible())
        # an eligible off-screen patient still commits (person:cray shares the lane)
        trace2 = TurnTrace(turn=4)
        trace2.movement_status = "clear"
        provider2 = StubProvider([{"ticks": [
            {"member": "person:maud", "kind": "met_with",
             "detail": "compared tallies over the barrow", "moves_to": "",
             "with_member": "person:cray"},
        ]}])
        _world_tick(world, world.porcelain, arc, trace2, provider2, 4, cast=cast, npcs=[],
                    entry_scene="place:lane", scene="place:study",
                    live_reads=PorcelainWorldReads(world), minutes_now=200.0)
        assert trace2.world_tick == ["person:maud:met_with"]
        _rows = [r for r in world.buffer.visible()
                 if str(r.entity) == "event:tick_maud_4"]
        assert any(r.attribute == "patient" and r.value == "person:cray" for r in _rows)

    def test_tick_consequences_discovered_not_narrated(self, world):
        # #84 REQUIRED PAIR (Cx 395/396 constraint 1): a tick consequence is DISCOVERED by
        # going there — it is never omniscient narrator fuel from elsewhere.
        arc = make_arc()
        seed_arc(world, arc)
        self._tick_setup(world)
        from construct.arc.executor import turn_time
        # a committed tick: maud moved to the market + a meanwhile event about it
        world.porcelain.ingest_structured([
            {"entity": "person:maud", "attribute": "in", "value": "place:market",
             "value_type": "entity", "valid_from": turn_time(2)},
            {"entity": "event:tick_maud_2", "attribute": "kind", "value": "met_with",
             "valid_from": turn_time(2)},
            {"entity": "event:tick_maud_2", "attribute": "agent", "value": "person:maud",
             "value_type": "entity", "valid_from": turn_time(2)},
            {"entity": "event:tick_maud_2", "attribute": "detail",
             "value": "met the coal factor by the weigh-house", "valid_from": turn_time(2)},
        ])
        _scope = [PLAYER, "place:study", "place:market", "person:maud", "event:tick_maud_2"]
        # NEGATIVE: a turn spent elsewhere — no prompt may carry the off-screen meanwhile
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "The study is quiet."},
        ])
        run_turn(world, arc, provider, "I look over my notes.", turn=3, scope=_scope)
        for (_p, _s, _t) in provider.calls:
            assert "met the coal factor" not in _p
            assert "person:maud · in · place:market" not in _p
        # POSITIVE: going to the market DISCOVERS her — presence renders the changed world
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider2 = StubProvider([
            {"kind": "action", "moves_to": "the market", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Maud is at her barrow by the weigh-house."},
        ])
        r2 = run_turn(world, arc, provider2, "I go to the market.", turn=4, scope=_scope)
        assert world.porcelain.locate(PLAYER)[0] == "place:market"
        _nar = next(p for (p, _s, _t) in reversed(provider2.calls) if task_of(p) == "nar")
        assert "Maud" in _nar.split("PRESENT CHARACTERS")[-1]

    def test_grant_move_blocked_route_to_container_does_not_commit(self, world, monkeypatch):
        # #91 (Cx 387 hard constraint): the mint path obeys the same passability discipline —
        # a blocked route to the embedded container means NO commit, status blocked.
        from construct.turnloop import _grant_moved_place
        import construct.turnloop as tl
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:liddell_warehouse", "attribute": "kind", "value": "warehouse",
             "timeless": True},
            {"entity": "place:liddell_warehouse", "attribute": "name",
             "value": "the Liddell warehouse"},
        ])
        monkeypatch.setattr(tl, "_route_obstruction", lambda *a, **k: {
            "status": "blocked", "via": "obj:gate",
            "evidence": [{"entity": "obj:gate", "attribute": "state", "value": "chained"}]})
        got, seg = _grant_moved_place(
            world, PLAYER, "the Liddell warehouse, to the foreman's office", at=2000.0,
            p=world.porcelain, origin="place:study",
            roster=[("place:liddell_warehouse", "the Liddell warehouse — warehouse")])
        assert got is None and seg and seg["status"] == "blocked"
        assert world.porcelain.locate(PLAYER)[0] == "place:study"   # never moved
        assert not PorcelainWorldReads(world).has_entity("place:foreman_s_office")

    def test_move_definite_description_binds_existing_place_not_mint(self, world):
        # Cx 354 A (founder phantom-scene incident): "the scene of the crime" is a DEFINITE
        # DESCRIPTION of the authored murder-scene place — zero token overlap, so the old path
        # minted place:scene_of_the_crime (a phantom). The semantic bind must travel to the
        # established place instead.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:bluegate_yard", "attribute": "kind",
             "value": "murder scene in a rain-wet yard", "timeless": True},
            {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the scene of the crime", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
            {"verdict": "existing", "match": "place:bluegate_yard"},   # the dst bind
            {"prose": "You step out into the rain toward Bluegate Yard."},
        ])
        run_turn(world, arc, provider, "Shall we see to the scene of the crime?", turn=2,
                 scope=[PLAYER, "place:study", "place:bluegate_yard"])
        chain = world.porcelain.locate(PLAYER)
        assert chain and chain[0] == "place:bluegate_yard"      # bound, traveled
        assert not PorcelainWorldReads(world).has_entity("place:scene_of_the_crime")

    def test_move_definite_description_binds_place_outside_scope(self, world):
        # Cx 356 BLOCKER regression: production bodycase's scope holds NO place:bluegate_yard —
        # the roster must enumerate the WORLD's known places (canon + player frame), not just
        # the turn snapshot scope, or the live incident recurs.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:bluegate_yard", "attribute": "kind",
             "value": "murder scene in a rain-wet yard", "timeless": True},
            {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the scene of the crime", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
            {"verdict": "existing", "match": "place:bluegate_yard"},
            {"prose": "You head out to Bluegate Yard."},
        ])
        # scope deliberately EXCLUDES place:bluegate_yard (the production shape)
        run_turn(world, arc, provider, "Shall we see to the scene of the crime?", turn=2,
                 scope=[PLAYER, "place:study"])
        # the roster offered the world-known place (it reached the dst prompt) and the bind landed
        dst_prompt = next(p for (p, _s, _t) in provider.calls if task_of(p) == "dst")
        assert "place:bluegate_yard" in dst_prompt
        chain = world.porcelain.locate(PLAYER)
        assert chain and chain[0] == "place:bluegate_yard"
        assert not PorcelainWorldReads(world).has_entity("place:scene_of_the_crime")

    def test_episode_doorway_moves_time_and_place(self, world):
        # #88 S4 (Cx 380 blocker): the chapter doorway is ENGINE TRUTH — time jumps to the next
        # phase (elapsed_minutes increases) and the protagonist returns to the prior episode's
        # OPENING place; no items are added. (This test FAILED before the 380 fix: the old leg
        # called the clock API with wrong signatures and the fail-open swallowed it.)
        # NB: built with construct's attribute_default (like production seals) — the accrue
        # fold on elapsed_minutes needs the semantics hook; the plain fixture world lacks it.
        import tempfile
        from pathlib import Path
        from patternbuffer import World
        from patternbuffer.testing import StubModel, rule_classifier_fallback
        from construct.game import _episode_doorway
        from construct.semantics import attribute_default
        from construct.clock import read_clock
        _rule = rule_classifier_fallback()
        w2 = World(Path(tempfile.mkdtemp()) / "door.world", world_id="w:door",
                   stance="fiction", attribute_default=attribute_default,
                   model=StubModel(fallback=lambda p, s: _rule(p, s)
                                   if p.startswith("Classify the lifetime") else {"items": []}))
        w2.ingestor.cursor.advance(1.0)
        w2.ingest_structured([
            {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
            {"entity": "place:far_end", "attribute": "kind", "value": "room", "timeless": True},
            {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
            {"entity": PLAYER, "attribute": "in", "value": "place:study",
             "valid_from": 1000.4},  # the episode-opening place (before epoch+0.5)
        ])
        w2.porcelain.ingest_structured([
            {"entity": PLAYER, "attribute": "in", "value": "place:far_end",
             "valid_from": 1010.0},  # the terminal scene — elsewhere
        ])
        _before = read_clock(w2).minutes
        door = _episode_doorway(w2, PLAYER, 1000.0, 12)
        assert read_clock(w2).minutes > _before             # TIME moved (engine truth)
        assert door == "place:study"                        # the prior opening place
        assert w2.porcelain.locate(PLAYER)[0] == "place:study"      # PLACE moved
        held = w2.porcelain.contents(PLAYER) if hasattr(w2.porcelain, "contents") else []
        assert not held                                      # ITEMS: nothing minted
        w2.close()

    def test_wrong_commitment_records_loss_even_when_frame_knows_truth(self, world):
        # #88 S2 (Cx 375-C, the founder's won-after-wrong bug): the player's frame KNOWS the
        # answer (world_condition satisfied — e.g. via interview delivery), but their ACCUSATION
        # is graded WRONG → the recorded outcome must be arc_lost with the shape attrs; knowing
        # the truth is not accusing rightly.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured(
            [{"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}],
            frame=PLAYER_FRAME)             # world_condition TRUE — old code recorded "won"
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True,
             "commitment": "I accuse the butler to his face"},
            {"grade": "wrong", "rationale": "the butler is innocent; the rival did it"},
            {"prose": "The accusation lands on the wrong man, and the room knows it."},
        ])
        r = run_turn(world, arc, provider, "Butler, you did this — I charge you!", turn=12,
                     scope=[PLAYER, "place:study"], scenario_mode="win_loss")
        assert r.trace.commitment_grade == "wrong"
        assert r.trace.outcome == "lost"                          # the grade decided
        reads = PorcelainWorldReads(world)
        assert reads.events(kind="arc_lost", frame="session:main")   # binary = plumbing only
        assert not reads.events(kind="arc_won", frame="session:main")
        _shape = [(r.attribute, r.value) for r in world.buffer.visible(
            entity="event:arc_outcome_12", frame="session:main")]
        assert ("grade", "wrong") in _shape                       # the SHAPE receipt is durable
        # S1 (#96, Cx 414): a GRADED commitment close keeps the RECKONING beat
        _nar = next(pr for (pr, _s, _t) in reversed(provider.calls) if task_of(pr) == "nar")
        assert "BEAT 1 — THE RECKONING SCENE" in _nar
        assert "BEAT 1 — THE SETTLING" not in _nar

    def test_unstaged_commitment_gets_clarification_beat(self, world):
        # #88A (founder + Cx 375): an underspecified conclusory move gets ONE in-fiction
        # clarification beat — no grade, no receipt; the session remembers it asked, so the
        # NEXT attempt is judged as given (no loop).
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "the rival did it"},
            {"specified": False, "missing": ["audience"],
             "clarification": "Say it to whom? The study is empty."},
            {"prose": "Your words find no one; the study holds only lamplight."},
        ])
        r = run_turn(world, arc, provider, "THE RIVAL DID IT", turn=12,
                     scope=[PLAYER, "place:study"])
        assert r.trace.commitment_clarified          # the beat, not a judgment
        assert not r.trace.commitment_grade
        assert not r.trace.terminal
        nar = next(p for (p, _s, _t) in reversed(provider.calls) if task_of(p) == "nar")
        assert "Say it to whom" in nar
        # second attempt: the receipt suppresses the gate — judged as given (here it BOUNCES on
        # incomplete coverage, which IS a judgment path, not another clarification).
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider2 = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": True, "commitment": "I accuse the rival to his face"},
            {"specified": False, "missing": ["audience"], "clarification": "should not be used"},
            {"prose": "The accusation hangs in the air."},
        ])
        r2 = run_turn(world, arc, provider2, "Rival, you did it — I say it to your face.",
                      turn=13, scope=[PLAYER, "place:study"])
        assert not r2.trace.commitment_clarified     # gate did NOT re-fire

    def test_ingest_raise_never_sinks_the_turn(self, world, monkeypatch):
        # #89 (eval: hedgetest's CLIMAX crashed on a PB declaration raise): any in-turn
        # ingest_structured raise drops its rows LOUDLY and the turn still ships prose.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": [
            {"entity": PLAYER, "attribute": "took", "value": "the digitalis"}]})
        world._extractions.append({"items": []})
        _orig = world.porcelain.ingest_structured

        def _boom(rows, **kw):
            if any(r.get("attribute") == "took" for r in (rows or []) if isinstance(r, dict)):
                raise ValueError("cannot declare semantics for attribute 'took' after "
                                 "folded data already exists (a:952)")
            return _orig(rows, **kw)

        monkeypatch.setattr(world.porcelain, "ingest_structured", _boom)
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "Julian goes pale as the accusation lands."},
        ])
        r = run_turn(world, arc, provider, "Julian, you took the digitalis!", turn=2,
                     scope=[PLAYER, "place:study"])
        assert r.prose                                       # the turn SHIPPED
        assert any("ingest" in d for d in r.trace.dropped_cohorts)   # loudly noted

    def test_seek_a_person_move_travels_to_their_true_place(self, world):
        # Founder live 2026-07-01 ("I go back to where Reed is"): the "where X is" wrapper
        # defeated refer → no travel → the narrator conjured a ghost arrival. The unwrap strips
        # it; the person→place redirect (Cx 003) then carries the player to X's REAL location.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:annex", "attribute": "kind", "value": "room", "timeless": True},
            {"entity": PLAYER, "attribute": "in", "value": "place:annex"},
            {"entity": "person:reed", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:reed", "attribute": "name", "value": "Reed"},
            {"entity": "person:reed", "attribute": "in", "value": "place:study"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "where Reed is", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "You find Reed in the study."},
        ])
        run_turn(world, arc, provider, "I go back to where Reed is.", turn=2,
                 scope=[PLAYER, "place:annex", "place:study", "person:reed"])
        chain = world.porcelain.locate(PLAYER)
        assert chain and chain[0] == "place:study"        # traveled to Reed's true place

    def test_dismissal_and_companion_move_exact_live_turn(self, world):
        # Cx 363/365 test bar #1 (the exact live turn-14 shape): "You two may go… Sir? Shall we
        # see to the scene of the crime?" → Maud/Nell get departed_scene events, Reed's `in`
        # commits WITH the player at the bound destination, and neither dismissed NPC is present
        # in the next turn's briefing.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:bluegate_yard", "attribute": "kind",
             "value": "murder scene in a rain-wet yard", "timeless": True},
            {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"},
            {"entity": "person:maud", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:maud", "attribute": "in", "value": "place:study"},
            {"entity": "person:nell", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:nell", "attribute": "in", "value": "place:study"},
            {"entity": "person:reed", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:reed", "attribute": "in", "value": "place:study"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        _scope = [PLAYER, "place:study", "place:bluegate_yard",
                  "person:maud", "person:nell", "person:reed"]
        # classify: roster is npc_0=maud, npc_1=nell, npc_2=reed (sorted scope order)
        provider = StubProvider([
            {"kind": "action", "moves_to": "the scene of the crime", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": ["npc_0", "npc_1"], "moved_with": ["npc_2"]},
            {"verdict": "existing", "match": "place:bluegate_yard"},
            # Reed arrives WITH the player → he is present at the new scene → npc_turn fires
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Maud takes Nell out into the dark; Reed walks with you to the yard."},
        ])
        r = run_turn(world, arc, provider,
                     "You two may go. Sir? Shall we see to the scene of the crime?",
                     turn=2, scope=_scope)
        assert sorted(r.trace.npcs_departed) == ["person:maud", "person:nell"]
        assert r.trace.npcs_moved_with == ["person:reed"]
        assert world.porcelain.locate(PLAYER)[0] == "place:bluegate_yard"
        assert world.porcelain.locate("person:reed")[0] == "place:bluegate_yard"  # came along
        # next turn: dismissed NPCs are NOT in the briefing; Reed is
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider2 = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Reed crouches by the stain."},
        ])
        r2 = run_turn(world, arc, provider2, "I look around.", turn=3, scope=_scope)
        nar = next(p for (p, _s, _t) in reversed(provider2.calls) if task_of(p) == "nar")
        assert "Maud" not in nar.split("PRESENT CHARACTERS")[-1].split("\n\n")[0]
        assert r2.prose

    def test_dismissed_npc_absent_when_player_stays(self, world):
        # Cx 363 test bar #3 (stay-after-dismissal): player dismisses and REMAINS — the
        # dismissed NPC is absent from presence with NO fake destination minted.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:maud", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:maud", "attribute": "in", "value": "place:study"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": ["npc_0"], "moved_with": []},
            {"prose": "Maud gathers her shawl and goes."},
        ])
        r = run_turn(world, arc, provider, "You may go, Maud.", turn=2,
                     scope=[PLAYER, "place:study", "person:maud"])
        assert r.trace.npcs_departed == ["person:maud"]
        # presence next turn: alone (the departed_scene projection suppresses her)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider2 = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "The room is quieter now."},
        ])
        run_turn(world, arc, provider2, "I look around.", turn=3,
                 scope=[PLAYER, "place:study", "person:maud"])
        nar = next(p for (p, _s, _t) in reversed(provider2.calls) if task_of(p) == "nar")
        assert "PRESENT CHARACTERS: none besides you" in nar   # she's gone, honestly
        # no fake destination: her `in` is untouched (projection, not relocation)
        assert world.porcelain.locate("person:maud")[0] == "place:study"

    def test_companions_do_not_move_on_blocked_route(self, world, monkeypatch):
        # Cx 363 test bar #2: blocked route → player does not move and NO moved_with NPC moves.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:bluegate_yard", "attribute": "kind",
             "value": "murder scene yard", "timeless": True},
            {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"},
            {"entity": "person:reed", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:reed", "attribute": "in", "value": "place:study"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        import construct.turnloop as tl
        monkeypatch.setattr(tl, "_route_obstruction", lambda *a, **k: {
            "status": "blocked", "via": "obj:door1",
            "evidence": [{"entity": "obj:door1", "attribute": "state", "value": "shut"}]})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the scene of the crime", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": [], "moved_with": ["npc_0"]},
            {"verdict": "existing", "match": "place:bluegate_yard"},
            # blocked → player stays at the study WITH Reed → his npc_turn still fires
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "The door will not give."},
        ])
        r = run_turn(world, arc, provider, "Sir? Shall we see to the scene of the crime?",
                     turn=2, scope=[PLAYER, "place:study", "person:reed"])
        assert r.trace.movement_status == "blocked"
        assert r.trace.npcs_moved_with == []                       # nobody companion-committed
        assert world.porcelain.locate(PLAYER)[0] == "place:study"
        assert world.porcelain.locate("person:reed")[0] == "place:study"

    def _seed_reed(self, world):
        world.porcelain.ingest_structured([
            {"entity": "place:bluegate_yard", "attribute": "kind",
             "value": "murder scene yard", "timeless": True},
            {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"},
            {"entity": "person:reed", "attribute": "kind", "value": "person", "timeless": True},
            {"entity": "person:reed", "attribute": "in", "value": "place:study"},
            {"entity": "person:reed", "attribute": "pronouns", "value": "he/him",
             "timeless": True},
        ])

    def test_colocated_person_outside_scope_is_present(self, world):
        # #94 campaign F12 (present-but-unseen): scope is a briefing boundary, not a truth
        # boundary — a person CANONICALLY in the room must be present (candidates + npc
        # turn + briefing) even when the episode scope omits them (the ch2 clerk who was
        # served and then denied while Tin Ear stood colocated the whole run).
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:tin_ear", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:tin_ear", "attribute": "name", "value": "Tin Ear"},
            {"entity": "person:tin_ear", "attribute": "in", "value": "place:study"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Tin Ear slides the ledger across the counter."},
        ])
        # scope OMITS person:tin_ear entirely — canon colocation must carry presence
        r = run_turn(world, arc, provider, "I look over the counter.", turn=2,
                     scope=[PLAYER, "place:study"])
        assert r.prose
        _nar = next(p for (p, _s, _t) in reversed(provider.calls) if task_of(p) == "nar")
        assert "Tin Ear" in _nar.split("PRESENT CHARACTERS")[-1].split("\n\n")[0]

    def test_self_question_routes_addressed_inward(self, world):
        # Founder live 2026-07-03 ("my own memories should answer here"): a question about
        # the player's OWN life is CHECKED at classify (`asks_self`) and routes to their own
        # memory as a BINDING briefing block — outranking the last-speaker convention, even
        # with an NPC present mid-conversation.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "person:julian", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:julian", "attribute": "in", "value": "place:study"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "question", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "", "asks_self": True},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "You had a room at the inn above the coach yard."},
        ])
        r = run_turn(world, arc, provider, "Where did I stay prior?", turn=2,
                     scope=[PLAYER, "place:study", "person:julian"])
        assert r.prose
        _nar = next(p for (p, _s, _t) in reversed(provider.calls) if task_of(p) == "nar")
        assert "ADDRESSED INWARD" in _nar
        assert "their own memory answers" in _nar

    def test_nested_colocated_person_outside_scope_is_present(self, world):
        # #94 F12, Cx 408 yellow: the candidate SOURCE must match the presence AUTHORITY's
        # containment shape — a person in a CHILD place of the player's scene is present
        # even when scope omits both the person and the child place.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            # a child alcove nested INSIDE the player's current scene (the study)
            {"entity": "place:alcove", "attribute": "kind", "value": "alcove",
             "timeless": True},
            {"entity": "place:alcove", "attribute": "in", "value": "place:study",
             "value_type": "entity"},
            {"entity": "person:nested", "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": "person:nested", "attribute": "name", "value": "Nestor"},
            {"entity": "person:nested", "attribute": "in", "value": "place:alcove",
             "value_type": "entity"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Nestor looks up from the alcove."},
        ])
        r = run_turn(world, arc, provider, "I take stock of the room.", turn=2,
                     scope=[PLAYER, "place:study"])
        assert r.prose
        _nar = next(p for (p, _s, _t) in reversed(provider.calls) if task_of(p) == "nar")
        assert "Nestor" in _nar.split("PRESENT CHARACTERS")[-1].split("\n\n")[0]

    def test_invite_then_later_moves_carry_companion(self, world, monkeypatch):
        # #82 (the Reed ping-pong, Cx 372/373): "stick with me" on a NON-move turn commits
        # STANDING `accompanying` canon; EVERY later accepted move then carries the companion
        # with no per-move wording — across multiple turns. (The pacing nudge is patched out —
        # it fires on later quiet turns and would eat queue stubs; not under test here.)
        import construct.cohorts as _ch
        monkeypatch.setattr(_ch, "nudge_pick",
                            lambda *a, **k: {"thread": "", "directive": "The wind shifts."})
        arc = make_arc()
        seed_arc(world, arc)
        self._seed_reed(world)
        _scope = [PLAYER, "place:study", "place:bluegate_yard", "person:reed"]
        # turn 2 — the invitation, no move
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": [], "moved_with": [], "joins": ["npc_0"]},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Reed nods. 'With you, then.'"},
        ])
        r = run_turn(world, arc, provider, "Stick with me, Reed.", turn=2, scope=_scope)
        assert r.trace.npcs_joined == ["person:reed"]
        reads = PorcelainWorldReads(world)
        assert reads.state("person:reed", "accompanying") == PLAYER
        # turn 3 — a plain move, NO companion wording: the standing state carries him
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider2 = StubProvider([
            {"kind": "action", "moves_to": "the yard", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": [], "moved_with": [], "joins": []},
            # "the yard" token-matches place:bluegate_yard deterministically — no referee stub
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "You cross to the yard; Reed keeps pace."},
        ])
        r2 = run_turn(world, arc, provider2, "I head to the yard.", turn=3, scope=_scope)
        assert r2.trace.npcs_moved_with == ["person:reed"]
        assert world.porcelain.locate("person:reed")[0] == "place:bluegate_yard"
        # COMPANION TEXTURE (#85): the standing companion is briefed as a companion, not a
        # bystander — the npc decision knows it, and the narrate briefing tags it.
        _npt = next(p for (p, _s, _t) in provider2.calls if task_of(p) == "npt")
        assert "YOU ARE THE PLAYER'S COMPANION" in _npt
        _nar = next(p for (p, _s, _t) in reversed(provider2.calls) if task_of(p) == "nar")
        assert "[COMPANION — with the player by agreement]" in _nar
        # CAST IDENTITY (#87): the seeded pronouns ride the presence line
        assert "(he/him)" in _nar
        # turn 4 — move again (back): still carried, no wording (survives across turns)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider3 = StubProvider([
            {"kind": "action", "moves_to": "the study", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": [], "moved_with": [], "joins": []},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Back in the study, Reed shakes the rain off."},
        ])
        r3 = run_turn(world, arc, provider3, "Back to the study.", turn=4, scope=_scope)
        assert r3.trace.npcs_moved_with == ["person:reed"]
        assert world.porcelain.locate("person:reed")[0] == "place:study"

    def test_dismissal_clears_standing_companionship(self, world, monkeypatch):
        # #82: dismissal supersedes `accompanying` with the empty literal — a later move
        # carries nobody, and the departed companion stays honestly gone.
        import construct.cohorts as _ch
        monkeypatch.setattr(_ch, "nudge_pick",
                            lambda *a, **k: {"thread": "", "directive": "The wind shifts."})
        arc = make_arc()
        seed_arc(world, arc)
        self._seed_reed(world)
        _scope = [PLAYER, "place:study", "place:bluegate_yard", "person:reed"]
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": [], "moved_with": [], "joins": ["npc_0"]},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Reed falls in beside you."},
        ])
        run_turn(world, arc, provider, "You're with me now, Reed.", turn=2, scope=_scope)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider2 = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": ["npc_0"], "moved_with": [], "joins": []},
            {"prose": "Reed touches his hat and goes."},
        ])
        r2 = run_turn(world, arc, provider2, "That's all for tonight, Reed. You may go.",
                      turn=3, scope=_scope)
        assert r2.trace.npcs_departed == ["person:reed"]
        reads = PorcelainWorldReads(world)
        assert not reads.state("person:reed", "accompanying")   # cleared (empty literal)
        # a later move carries nobody
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider3 = StubProvider([
            {"kind": "action", "moves_to": "the yard", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": [], "moved_with": [], "joins": []},
            {"prose": "You go out to the yard alone."},
        ])
        r3 = run_turn(world, arc, provider3, "I head to the yard.", turn=4, scope=_scope)
        assert r3.trace.npcs_moved_with == []
        assert world.porcelain.locate("person:reed")[0] == "place:study"

    def test_standing_companion_not_carried_on_blocked_route(self, world, monkeypatch):
        # #82: the standing state obeys the same route gate as per-move wording — a blocked
        # move carries nobody.
        import construct.cohorts as _ch
        monkeypatch.setattr(_ch, "nudge_pick",
                            lambda *a, **k: {"thread": "", "directive": "The wind shifts."})
        arc = make_arc()
        seed_arc(world, arc)
        self._seed_reed(world)
        _scope = [PLAYER, "place:study", "place:bluegate_yard", "person:reed"]
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": [], "moved_with": [], "joins": ["npc_0"]},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "Reed falls in beside you."},
        ])
        run_turn(world, arc, provider, "Stay close, Reed.", turn=2, scope=_scope)
        import construct.turnloop as tl
        monkeypatch.setattr(tl, "_route_obstruction", lambda *a, **k: {
            "status": "blocked", "via": "obj:door1",
            "evidence": [{"entity": "obj:door1", "attribute": "state", "value": "shut"}]})
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider2 = StubProvider([
            {"kind": "action", "moves_to": "the scene of the crime", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": "",
             "npcs_dismissed": [], "moved_with": [], "joins": []},
            {"verdict": "existing", "match": "place:bluegate_yard"},
            {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
            {"prose": "The door will not give."},
        ])
        r2 = run_turn(world, arc, provider2, "Through to the scene of the crime.",
                      turn=3, scope=_scope)
        assert r2.trace.movement_status == "blocked"
        assert r2.trace.npcs_moved_with == []
        assert world.porcelain.locate(PLAYER)[0] == "place:study"
        assert world.porcelain.locate("person:reed")[0] == "place:study"

    def test_bound_destination_respects_blocked_route(self, world, monkeypatch):
        # Cx 358 BLOCKER: a semantically BOUND destination must run the same passability gate
        # as ordinary resolved travel — a blocked route (shut door) means NO commit, status
        # "blocked", obstruction on the trace; never a teleport.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:bluegate_yard", "attribute": "kind",
             "value": "murder scene in a rain-wet yard", "timeless": True},
            {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        import construct.turnloop as tl
        _blocked = {"status": "blocked", "via": "obj:door1",
                    "evidence": [{"entity": "obj:door1", "attribute": "state", "value": "shut"}]}
        monkeypatch.setattr(tl, "_route_obstruction", lambda *a, **k: dict(_blocked))
        provider = StubProvider([
            {"kind": "action", "moves_to": "the scene of the crime", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
            {"verdict": "existing", "match": "place:bluegate_yard"},
            {"prose": "The door will not give."},
        ])
        r = run_turn(world, arc, provider, "Shall we see to the scene of the crime?", turn=2,
                     scope=[PLAYER, "place:study"])
        assert r.trace.movement_status == "blocked"
        assert r.trace.movement_obstruction and \
            r.trace.movement_obstruction.get("via") == "obj:door1"
        chain = world.porcelain.locate(PLAYER)
        assert chain and chain[0] == "place:study"       # did NOT teleport through the door

    def test_move_genuinely_new_place_still_mints(self, world):
        # improv-travel preserved: verdict=new falls through to the movement-permanence mint.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:bluegate_yard", "attribute": "kind", "value": "yard",
             "timeless": True},
            {"entity": "place:bluegate_yard", "attribute": "name", "value": "Bluegate Yard"}])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the old mill on the hill", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
            {"verdict": "new", "match": ""},
            {"prose": "You climb to the old mill."},
        ])
        run_turn(world, arc, provider, "I head to the old mill on the hill.", turn=2,
                 scope=[PLAYER, "place:study", "place:bluegate_yard"])
        chain = world.porcelain.locate(PLAYER)
        assert chain and chain[0].startswith("place:") and chain[0] != "place:study"

    def test_alone_scene_briefing_states_no_one_present(self, world):
        # Cx 354 B2 (founder "why are nell and grieves here???"): an EMPTY colocated set must
        # be stated in the narrate briefing so the narrator can't resurrect departed cast.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "The room holds quiet around you."},
        ])
        run_turn(world, arc, provider, "I look around.", turn=2, scope=[PLAYER, "place:study"])
        nar = next(p for (p, _s, _t) in reversed(provider.calls) if task_of(p) == "nar")
        assert "PRESENT CHARACTERS: none besides you" in nar
        assert "Do not stage earlier characters" in nar

    def test_move_deictic_back_is_not_minted(self, world):
        # Cx 288 nit: a deictic/directional move ("go back") must NOT mint `place:back` — the
        # narrator handles it against the real geography.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "back", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You turn back the way you came."},
        ])
        run_turn(world, arc, provider, "I go back.", turn=2, scope=[PLAYER, "place:study"])
        chain = world.porcelain.locate(PLAYER)
        assert chain and chain[0] == "place:study"          # no place:back minted; stayed put
        assert world.porcelain.state("place:back", "kind")["status"] != "known"

    def test_move_to_an_ambiguous_reference_is_not_minted(self, world):
        # Cx 288 #2: an AMBIGUOUS reference (refer underdetermined WITH candidates) must NOT be
        # resolved by slug convention into a mint — PB's reference contract stays honest.
        arc = make_arc()
        seed_arc(world, arc)
        world.porcelain.ingest_structured([
            {"entity": "place:office_a", "attribute": "kind", "value": "room", "timeless": True},
            {"entity": "place:office_a", "attribute": "name", "value": "office"},
            {"entity": "place:office_b", "attribute": "kind", "value": "room", "timeless": True},
            {"entity": "place:office_b", "attribute": "name", "value": "office"},
        ])
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "office", "requires": [], "needs_test": False,
             "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "Which office did you mean?"},
        ])
        run_turn(world, arc, provider, "I go to the office.", turn=2, scope=[PLAYER, "place:study"])
        assert world.porcelain.state("place:office", "kind")["status"] != "known"  # no slug-mint

    def test_unresolved_undiscovered_suspect_location_is_not_minted(self):
        # Cx review #1: the entitlement gate runs only on a RESOLVED target, so a guessed/UNRESOLVED
        # variant of an undiscovered offscene suspect (or their location) must ALSO be denied the
        # move-permanence mint — else the player teleports near them by naming a variant.
        from types import SimpleNamespace
        from construct.turnloop import _names_undiscovered_dest
        node = SimpleNamespace(node_id="person:warden", location="place:keep", surface_role="warden")
        cbi = {"person:warden": node}
        name_of = lambda e: {"person:warden": "Warden Cray", "place:keep": "the old keep"}.get(e, "")
        undiscovered = lambda n: True            # whereabouts not yet learned
        assert _names_undiscovered_dest("the old keep", cbi, undiscovered, name_of) is True  # their place
        assert _names_undiscovered_dest("warden cray's rooms", cbi, undiscovered, name_of) is True  # them
        assert _names_undiscovered_dest("the bell yard office", cbi, undiscovered, name_of) is False  # other
        # once discovered, the gate no longer blocks
        assert _names_undiscovered_dest("the old keep", cbi, lambda n: False, name_of) is False

    def test_match_known_place_reuses_instead_of_minting_a_twin(self):
        # FOUNDER cohesion test bug: "return to my own office" minted a DUPLICATE office instead of
        # reusing the existing one. _match_known_place token-matches a known place so a return home
        # reuses it; an unknown name → None (genuine improv → mint); ambiguous → None (don't guess).
        from types import SimpleNamespace
        from construct.turnloop import _match_known_place
        reads = SimpleNamespace(state=lambda e, a: "room")
        name_of = lambda e: {"place:office": "the office", "place:study": "the study"}.get(e, "")
        cands = {"place:office", "place:study", "person:x"}
        assert _match_known_place("my own office", cands, reads, name_of) == "place:office"
        assert _match_known_place("the bakery on the lane", cands, reads, name_of) is None
        # ambiguous — two places both named "office" → don't guess
        amb = SimpleNamespace(state=lambda e, a: "room")
        assert _match_known_place("office", {"place:office_a", "place:office_b"},
                                  amb, lambda e: "the office") is None

    def test_move_to_a_secret_named_place_is_not_minted(self, world):
        # The concealment guard holds: a move whose name brushes the arc's hidden vocabulary
        # ("the rival's lair" — rival is the protected culprit) is NOT minted by fiat.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "the rival's lair", "requires": [],
             "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
            {"prose": "You cannot simply find your way there."},
        ])
        run_turn(world, arc, provider, "I go to the rival's lair.", turn=2,
                 scope=[PLAYER, "place:study"])
        chain = world.porcelain.locate(PLAYER)
        assert chain and chain[0] == "place:study"   # stayed put — no secret place minted

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
        # present-cast briefing names the NPC (de-leaked id, Title-Cased person name) + want (Cx 091 #1)
        assert "Witness: wants deflect" in _narrate_prompt(provider)

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

    def test_no_automatic_conduit_stays_in_fiction(self, world):
        # Founder 2026-07-01: Conduit speaks ONLY via the explicit /ooc command. A stray
        # classify 'ooc' verdict (legacy stub) must NOT break to the host persona — it falls
        # through to the in-world action/narration path, keeping the player in the fiction. The
        # trigger was an in-character line to a present partner ("do you have any more questions
        # for these two?") getting mis-tagged OOC and answered by the host instead of the character.
        arc = make_arc()
        seed_arc(world, arc)
        provider = StubProvider([
            {"kind": "ooc", "moves_to": "", "requires": [], "needs_test": False, "uncertain_of": ""},
            {"prose": "Reed considers, then shakes his head. \"Nothing more from them for now.\""},
        ])
        result = run_turn(world, arc, provider, "do you have any more questions for these two?",
                          turn=1)
        assert not result.prose.startswith("Conduit:")   # host persona never auto-fires
        assert "conduit" not in " ".join(result.trace.cohort_calls).lower()


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


def test_cast_staging_anchors_to_opening_not_aftermath(world):
    # Cx 255 blocking #1: cast staging must anchor to the protagonist's OPENING location, not
    # the timeline head. A source axis with the protagonist at home (chunk 1) and hospital
    # (chunk 3) must yield an opening scene of `place:home` when located as-of opening_as_of.
    from construct.arc.executor import ENTRY_MARGIN, SOURCE_STEP
    STEP = SOURCE_STEP
    opening_as_of = STEP + ENTRY_MARGIN
    world.ingest_structured([
        {"entity": "place:home", "attribute": "kind", "value": "house", "timeless": True},
        {"entity": "place:hospital", "attribute": "kind", "value": "ward", "timeless": True},
        {"entity": "person:hero", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:hero", "attribute": "in", "value": "place:home",
         "value_type": "entity", "valid_from": STEP},                   # chunk 1: opening
        {"entity": "person:hero", "attribute": "in", "value": "place:hospital",
         "value_type": "entity", "valid_from": 3.0 * STEP},             # chunk 3: aftermath
    ])
    # The head read (the OLD staging anchor) picks the aftermath — the bug.
    assert world.porcelain.locate("person:hero")[0] == "place:hospital"
    # The opening-horizon read (the fix) anchors the opening scene at home.
    assert world.porcelain.locate("person:hero", as_of=opening_as_of)[0] == "place:home"


def test_refer_resolves_aftermath_entity_by_name_so_presence_guard_is_needed(world):
    # Cx 257 fresh-hunt: refer() resolves an entity by its REGISTERED NAME even as-of the
    # opening — tier-1 identity lookup bypasses the as_of candidate filter. This is the exact
    # reason the as_of bind ALONE is insufficient and a horizon-presence guard is required.
    from construct.adapter import PorcelainWorldReads
    from construct.arc.executor import ENTRY_MARGIN, SOURCE_STEP
    STEP = SOURCE_STEP
    opening_as_of = STEP + ENTRY_MARGIN
    world.ingest_structured([
        # a place whose very EXISTENCE (kind+name) is aftermath-stamped (chunk 3)
        {"entity": "place:keepruins", "attribute": "kind", "value": "ruin",
         "valid_from": 3.0 * STEP},
        {"entity": "place:keepruins", "attribute": "name", "value": "the Keep Ruins",
         "valid_from": 3.0 * STEP},
    ])
    # refer matches by name even as-of the opening (tier-1 bypass) — so as_of alone won't deny.
    r = world.refer("the Keep Ruins", frame="canon", as_of=opening_as_of)
    assert getattr(r, "entity_id", None) == "place:keepruins"
    # The horizon-presence guard is what actually denies it: has_entity is horizon-bound, so a
    # future-only entity is ABSENT at the opening (kind row is in its future) — movement/take
    # in run_turn drop the target on exactly this check.
    assert not PorcelainWorldReads(world, horizon=opening_as_of).has_entity("place:keepruins")
    assert PorcelainWorldReads(world).has_entity("place:keepruins")   # head: present


def test_opening_scene_place_falls_back_to_earliest_not_aftermath(world):
    # Cx 261 note: the saga/atmospheric case. The protagonist is NOT placed at the opening
    # horizon (the opening chapter is scene-setting); their earliest source `in` is later than
    # opening_as_of; an even-later aftermath `in` exists. _opening_scene_place must anchor the
    # opening tableau on the EARLIEST source location (their introduction), NEVER the head.
    from construct.game import _opening_scene_place
    from construct.arc.executor import ENTRY_MARGIN, SOURCE_STEP
    STEP = SOURCE_STEP
    opening_as_of = STEP + ENTRY_MARGIN
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "kind", "value": "village", "timeless": True},
        {"entity": "place:road", "attribute": "kind", "value": "road", "timeless": True},
        {"entity": "place:keep_ruins", "attribute": "kind", "value": "ruin", "timeless": True},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        # NO `in` at/below opening_as_of (opening chapter is atmospheric) — first placement is
        # chunk 2 (introduction at home), then the aftermath at chunk 5.
        {"entity": "person:mara", "attribute": "in", "value": "place:harth",
         "value_type": "entity", "valid_from": 2.0 * STEP},
        {"entity": "person:mara", "attribute": "in", "value": "place:keep_ruins",
         "value_type": "entity", "valid_from": 5.0 * STEP},
    ])
    # head = the aftermath (the old, wrong anchor)
    assert world.porcelain.locate("person:mara")[0] == "place:keep_ruins"
    # nothing at the opening horizon
    assert world.porcelain.locate("person:mara", as_of=opening_as_of) == []
    # _opening_scene_place anchors on the EARLIEST source location (their introduction at home)
    assert _opening_scene_place(world, "person:mara", opening_as_of) == "place:harth"
    # legacy (no horizon) falls back to head
    assert _opening_scene_place(world, "person:mara", None) == "place:keep_ruins"


def test_horizon_metadata_coordinates():
    # B' S2: the spaced-axis coordinates. opening sits one margin above chunk 1 (so opening
    # staging supersedes chunk-1 source); the next source chunk is the fail-closed ceiling.
    from construct.arc.executor import ENTRY_MARGIN, SOURCE_STEP, horizon_metadata
    opening, nxt = horizon_metadata(SOURCE_STEP)
    assert opening == SOURCE_STEP + ENTRY_MARGIN
    assert nxt == 2.0 * SOURCE_STEP
    assert opening < nxt                              # opening band sits below the next chunk


def test_porcelain_reads_honor_play_horizon(world):
    # B' S3 / Cx 253 §3: the linchpin. A bible narrates the whole arc — chunk 1 (opening) at
    # SOURCE_STEP, the aftermath at 3*SOURCE_STEP. Reading as-of the OPENING horizon must show
    # the opening state and EXCLUDE every future source row (location AND the attribute axis —
    # the bracelet/aged regression); reading at HEAD (legacy horizon=None) sees the aftermath.
    from construct.adapter import PorcelainWorldReads
    from construct.arc.executor import ENTRY_MARGIN, SOURCE_STEP
    STEP = SOURCE_STEP
    opening_as_of = STEP + ENTRY_MARGIN
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "kind", "value": "village", "timeless": True},
        {"entity": "place:keep_ruins", "attribute": "kind", "value": "ruin", "timeless": True},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        # CHUNK 1 (the opening): Mara at home in Harth, young, no relic yet.
        {"entity": "person:mara", "attribute": "in", "value": "place:harth",
         "value_type": "entity", "valid_from": STEP},
        {"entity": "person:mara", "attribute": "appearance", "value": "young",
         "valid_from": STEP},
        # AFTERMATH (chunk 3): the source narrates her END — at the ruins, aged, the bracelet worn.
        {"entity": "person:mara", "attribute": "in", "value": "place:keep_ruins",
         "value_type": "entity", "valid_from": 3.0 * STEP},
        {"entity": "person:mara", "attribute": "appearance", "value": "aged",
         "valid_from": 3.0 * STEP},
        {"entity": "person:mara", "attribute": "bracelet", "value": "worn",
         "valid_from": 3.0 * STEP},
        # an aftermath EVENT, for the events() horizon check
        {"entity": "event:keep_fell", "attribute": "kind", "value": "collapse",
         "valid_from": 3.0 * STEP},
    ])
    head = PorcelainWorldReads(world)                          # legacy / no horizon = head
    horizon = PorcelainWorldReads(world, horizon=opening_as_of)

    # HEAD sees the aftermath (the staging-aftermath-scatter bug, unfixed by reading head).
    assert head.location_chain("person:mara")[0] == "place:keep_ruins"
    assert head.state("person:mara", "appearance") == "aged"
    assert head.state("person:mara", "bracelet") == "worn"

    # The OPENING horizon excludes ALL future source rows — location, attribute, and the
    # aftermath-ADDED attribute (bracelet) is simply absent at the opening (no unset sentinel).
    assert horizon.location_chain("person:mara")[0] == "place:harth"
    assert horizon.state("person:mara", "appearance") == "young"
    assert horizon.state("person:mara", "bracelet") is None    # the non-location-attr regression

    # events() is horizon-bounded — the aftermath collapse is invisible at the opening.
    assert [e.event_id for e in head.events(kind="collapse")] == ["event:keep_fell"]
    assert horizon.events(kind="collapse") == []

    # assertion_in_frame honors the horizon too (beats/InFrame read the opening, not head).
    assert head.assertion_in_frame("canon", "person:mara", "appearance", "aged")
    assert not horizon.assertion_in_frame("canon", "person:mara", "appearance", "aged")
    assert horizon.assertion_in_frame("canon", "person:mara", "appearance", "young")


def test_live_turn_supersedes_opening_at_the_horizon(world):
    # B' S2/S3: a live turn at opening_as_of + k SUPERSEDES the opening staging (the Cx-127
    # invariant, preserved) AND stays below the next source coordinate, so a read at the
    # advanced horizon shows the live state while still excluding future source.
    from construct.adapter import PorcelainWorldReads
    from construct.arc.executor import ENTRY_MARGIN, SOURCE_STEP
    STEP = SOURCE_STEP
    opening_as_of = STEP + ENTRY_MARGIN
    world.ingest_structured([
        {"entity": "place:harth", "attribute": "kind", "value": "village", "timeless": True},
        {"entity": "place:road", "attribute": "kind", "value": "road", "timeless": True},
        {"entity": "person:mara", "attribute": "kind", "value": "person", "timeless": True},
        # opening staging at opening_as_of
        {"entity": "person:mara", "attribute": "in", "value": "place:harth",
         "value_type": "entity", "valid_from": opening_as_of},
        # a future source chunk at 2*STEP (the ceiling) — must stay excluded throughout
        {"entity": "person:mara", "attribute": "in", "value": "place:keep_ruins",
         "value_type": "entity", "valid_from": 2.0 * STEP},
    ])
    # turn 5: the player walks to the road; stamped within the reserved band.
    world.ingest_structured([
        {"entity": "person:mara", "attribute": "in", "value": "place:road",
         "value_type": "entity", "valid_from": opening_as_of + 5.0},
    ])
    play_horizon = PorcelainWorldReads(world, horizon=opening_as_of + 5.0)
    assert play_horizon.location_chain("person:mara")[0] == "place:road"   # live supersedes
    # the opening horizon still shows the staged opening (the live write is in its future)
    opening = PorcelainWorldReads(world, horizon=opening_as_of)
    assert opening.location_chain("person:mara")[0] == "place:harth"


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
    assert "never invent that one is secretly another" in RENDER_LEASH


def test_render_blocks_stage1_collapsed_shape():
    # Narrator collapse Stage 1 (founder prompt-elegance audit; Cx 245 / K 079 GREEN):
    # the two standing blocks are consolidated — dedup + contradictions fixed — and carry
    # the founder's two new rules, WITHOUT banning ordinary improv or hiding real exits.
    from construct.cohorts import RENDER_LEASH, RENDER_STYLE
    # No narrator option-menus, but real exits/affordances are still scene fact (not hidden).
    assert "NEVER TIP CHOICES" in RENDER_STYLE
    assert "ways out" in RENDER_STYLE
    # Player-is-protagonist + false-premise refusal scoped to SIGNIFICANT/defined referents…
    assert "PLAYER is the protagonist" in RENDER_LEASH
    assert "SIGNIFICANT or already-defined" in RENDER_LEASH
    # …so ordinary grounded improv is explicitly NOT banned (Cx 245 wording guard).
    assert "fair improv" in RENDER_LEASH
    # The two contradictions/overstatements are gone.
    assert "What you make real here becomes part of the world" not in RENDER_LEASH
    assert "ANSWER THIS TURN, do not re-establish" not in RENDER_STYLE
    # DIALOGUE IS SPEECH, NOT THESIS (founder 2026-07-01, "reeds one liner is so lame"):
    # characters never recite the theme as a tidy maxim/epigram — it lives in what they do.
    assert "DIALOGUE IS SPEECH, NOT THESIS" in RENDER_STYLE
    assert "never" in RENDER_STYLE and "epigram" in RENDER_STYLE
    # NO HARD LENGTH BUDGET (founder ruling 2026-07-01): a char cap forced weird include/cut
    # logic ("no room for the better clause"). Inclusion is judged on MERIT — every clause
    # earns its place; elegance is proper details properly presented, not fewer chars. Context
    # overload is guarded editorially (the Cx prompt-elegance reviews), not numerically.


def test_narrate_conditional_blocks_gate():
    # Stage 2: WORLD_IS_PEOPLED / PROTAGONIST_COMPETENCE ride the window only when their
    # flag is set — the narrate() gating mechanism (Cx 247 / K 080).
    from construct.cohorts import narrate
    on = StubProvider([{"prose": "x"}])
    narrate(on, "BRIEFING", "person:p", peopled=True, competence=True)
    p_on = on.calls[-1][0]
    assert "policy-machines" in p_on and "make another character recite" in p_on
    off = StubProvider([{"prose": "x"}])
    narrate(off, "BRIEFING", "person:p", peopled=False, competence=False)
    p_off = off.calls[-1][0]
    assert "policy-machines" not in p_off and "make another character recite" not in p_off


def _solo_classify(**over):
    base = {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
            "uncertain_of": "", "uses_protagonist_knowledge": False}
    base.update(over)
    return base


def test_turn_gates_competence_on_knowledge_move_solo(world):
    # A solo expert move (uses_protagonist_knowledge) keeps competence; no NPCs → peopled off.
    arc = make_arc(); seed_arc(world, arc)
    world._extractions.append({"items": []}); world._extractions.append({"items": []})
    provider = StubProvider([_solo_classify(uses_protagonist_knowledge=True),
                             {"prose": "You reconstruct the mechanism."}])
    run_turn(world, arc, provider, "As the detective, reconstruct how the bolt was worked.", turn=1)
    np = _narrate_prompt(provider)
    assert "make another character recite" in np     # competence ON — capability-dependent move
    assert "policy-machines" not in np         # peopled OFF — solo scene


def test_turn_drops_both_on_solo_idle(world):
    # A solo idle/look turn sheds both blocks (the prompt-mass win).
    arc = make_arc(); seed_arc(world, arc)
    world._extractions.append({"items": []}); world._extractions.append({"items": []})
    provider = StubProvider([_solo_classify(uses_protagonist_knowledge=False),
                             {"prose": "You wait."}])
    run_turn(world, arc, provider, "I wait, watching.", turn=1)
    np = _narrate_prompt(provider)
    assert "make another character recite" not in np  # no capability move
    assert "policy-machines" not in np          # solo


def test_author_intro_cohort():
    # The thematic introduction: premise/stakes in voice that GROUNDS the player —
    # clarity with a stylistic cherry, NO objective/aim BANNER (the call to action
    # arises in play). The aim IS passed as the player's-situation/role context (so the
    # intro names their role, not a wrong character) but explicitly not as a banner.
    from construct.cohorts import author_intro
    prov = StubProvider([{"intro": "Rain on a drowned port; the ledgers lie."}])
    out = author_intro(prov, "DIGEST", theme="truth vs scarcity",
                       style="terse noir", aim="name who falsified the meter")
    assert "drowned port" in out["intro"]
    prompt = prov.calls[0][0]
    assert "do NOT end on an objective" in prompt            # no closing aim banner
    assert "name who falsified the meter" in prompt          # aim = role/situation context
    assert "do NOT restate as an objective banner" in prompt  # …but never as a banner
    assert "SECOND PERSON" in prompt and "Do NOT give them" in prompt  # no baked name
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
    # #88 S3: the close is TWO BEATS — a reckoning scene, then the aftermath (was: "EPILOGUE").
    # S1 (#96, Cx 414): this fixture closes via the WORLD CONDITION (no graded commitment
    # landed), so beat 1 is the SETTLING — no verdict, no judgment scene. The RECKONING
    # branch is pinned on the graded-commitment test.
    assert "BEAT 1 — THE SETTLING" in narrate_prompt
    assert "NO verdict, NO accusation" in narrate_prompt
    assert "BEAT 1 — THE RECKONING SCENE" not in narrate_prompt
    assert "BEAT 2 — THE AFTERMATH" in narrate_prompt
    assert "unexpected BOON" in narrate_prompt          # the founder's mixed-outcome vocabulary
    # S2 (#96, Cx 414): every ending writes deterministic caused-by consequence events
    assert any(c.startswith("word_spreads:") for c in result.trace.consequences)
    assert any(c.startswith("reputation_changes:") for c in result.trace.consequences)
    _cons_rows = [r for r in world.buffer.visible()
                  if str(r.entity).startswith("event:consequence_")]
    assert any(r.attribute == "kind" and r.value == "word_spreads" for r in _cons_rows)
    assert any(r.attribute == "detail" for r in _cons_rows)
    # Cx 420 blocker: causality must live on the EVENT ENTITY (item-level caused_by
    # lands on the assertion row) — events().caused_by carries the terminal receipt.
    from construct.adapter import PorcelainWorldReads as _PWR
    _preads = _PWR(world)
    for _kind in ("word_spreads", "reputation_changes"):
        _evs = _preads.events(kind=_kind)
        assert _evs and any(str(c).startswith("event:arc_outcome_")
                            for c in (_evs[0].caused_by or [])), \
            f"{_kind} event must be caused_by the terminal receipt"
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
        # F12 (present-but-unseen): the rival LIVES in the flat — arriving there, he is
        # honestly present now (colocated ⇒ discovered), so his npc_turn fires.
        {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
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
        # F12: Parker is honestly present at his own pantry when you arrive — npc_turn fires
        {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
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
    # A LOAD-BEARING / specific object is still denied — the equipment grant must NOT
    # mint a vault key by fiat (it would bypass the world's locks).
    arc = make_arc()
    seed_arc(world, arc)
    provider = StubProvider([
        {"kind": "action", "moves_to": "",
         "requires": ["the iron vault key"], "needs_test": False, "uncertain_of": ""},          # classify
        {"ordinary_equipment": False, "item_id": "", "reason": "a specific load-bearing key"},  # equipment_check
        {"prose": "Your pocket holds no such key; the vault stays shut."},
    ])
    result = run_turn(world, arc, provider,
                      "I take the iron vault key from my pocket and unlock the vault.",
                      turn=1)
    assert result.trace.adjudication.startswith("denied:")
    assert "no such key" in result.prose
    # the phantom action never entered canon
    assert world.porcelain.state("obj:iron_vault_key", "kind")["status"] == "unknown"


def test_adjudication_grants_ordinary_role_equipment(world):
    # IMPROV-AND-AUTHORITY (founder): a physician's bag is ordinary role equipment — it
    # is GRANTED (minted + committed), not denied for being unestablished, so the action
    # stands instead of stonewalling on a missing canon object.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": ["my medical bag"],
         "needs_test": False, "uncertain_of": ""},                                              # classify
        {"ordinary_equipment": True, "item_id": "obj:medical_bag",
         "reason": "ordinary physician's equipment"},                                           # equipment_check
        {"prose": "You open your medical bag and set to work."},
    ])
    result = run_turn(world, arc, provider, "I open my medical bag and treat the wound.", turn=1)
    assert result.trace.adjudication == "allowed"          # granted, not denied
    # the equipment was minted as the protagonist's possession (the world adapts)
    assert world.porcelain.state("obj:medical_bag", "kind")["status"] == "known"
    assert PLAYER in (PorcelainWorldReads(world).location_chain("obj:medical_bag") or [])


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


def test_equipment_grant_never_reuses_an_existing_object_id(world):
    # Cx 230: the cohort's item_id is NOT authority. If it returns an EXISTING object id
    # (obj:murder_weapon, elsewhere) for an ordinary bag claim, the grant must NOT touch
    # that object — it mints a fresh host-owned id and allows the action on THAT.
    arc = make_arc()
    seed_arc(world, arc)
    world.ingest_structured([
        {"entity": "obj:murder_weapon", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:murder_weapon", "attribute": "in", "value": "place:study"},
    ])
    world._extractions.append({"items": []})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": ["my medical bag"],
         "needs_test": False, "uncertain_of": ""},                                   # classify
        {"ordinary_equipment": True, "item_id": "obj:murder_weapon",  # malicious/colliding id
         "reason": "ordinary bag"},                                                  # equipment_check
        {"prose": "You open your bag."},                                             # narrate
    ])
    result = run_turn(world, arc, provider, "I open my medical bag.", turn=1)
    reads = PorcelainWorldReads(world)
    assert result.trace.adjudication == "allowed"                  # granted via a FRESH object
    # the established object is UNTOUCHED — still in the study, never moved to the player
    assert reads.location_chain("obj:murder_weapon") == ["place:study"]
    assert world.porcelain.state("obj:murder_weapon", "in")["status"] == "known"  # not conflicted
    # a fresh host-owned bag was minted at the player instead
    assert PLAYER in (reads.location_chain("obj:medical_bag") or [])


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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": True, "reshape_attempt": True,
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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": True, "reshape_attempt": True,
             "uncertain_of": "whether the victim can be brought back"},             # classify
            {"is_reshape": True, "slug": "victim_revived",
             "target": {"entity": "person:rival", "attribute": "alive", "value": "true"},
             # restage the revived NPC — an entity the replacement arc below does NOT reference,
             # so the scope refresh (Cx 215/216 #2) must pull it in from the committed rows.
             "restage": [{"entity": "person:rival", "attribute": "in", "value": "place:study"}],
             "frame_knowledge": [], "consequence": [],
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
        # Explicit OPT-OUT (reshape is ON by default now): the flag disables it even on a
        # genuine reshape_attempt, so a pure-realism world plays byte-for-byte as before.
        monkeypatch.setenv("CONSTRUCT_WORLD_RESHAPE", "0")
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": True,
             "reshape_attempt": True,
             "uncertain_of": "whether the truth can be rewritten"},               # classify
            {"prose": "You strain against the truth, but it is what it is."},      # narrate
        ])
        result = run_turn(world, arc, provider, "I will the truth to change.", turn=1)
        assert result.trace.reshape == ""                            # disabled → no reshape fired
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
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": True, "reshape_attempt": True,
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


# ---------------------------------------------------------------------------
# #95 DEATH & THE TESTAMENT (DEATH-TESTAMENT.md, Cx 422)
# ---------------------------------------------------------------------------

_MORTAL_CLASSIFY = {
    "kind": "action", "moves_to": "", "requires": [], "needs_test": True,
    "uncertain_of": "the drop from the parapet would kill",
    "mortal_risk": True, "commits": False, "commitment": "",
}


def _stage_peril(world, scene="place:study"):
    from construct.arc.executor import turn_time
    world.porcelain.ingest_structured([
        {"entity": "session:peril", "attribute": "scene", "value": scene,
         "valid_from": turn_time(1)},
        {"entity": "session:peril", "attribute": "cause",
         "value": "the drop from the parapet", "valid_from": turn_time(1)},
    ], frame="session:main")


def test_first_mortal_risk_stages_never_kills(world, monkeypatch):
    # Cx 422 bar 1: the FIRST life-risking turn stages (stakes unmistakable, the move
    # lands SHORT of death) even on a forced terrible_failure — never a gotcha.
    from construct import resolution
    from construct.adapter import PorcelainWorldReads as _PWR
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_MORTAL_CLASSIFY),
        {"prose": "The ledge crumbles; you catch the gutter, bloodied but alive."},
    ])
    result = run_turn(world, arc, provider, "I leap across the gap.", turn=2,
                      scope=[PLAYER, "place:study"], death_policy="mortal")
    assert result.trace.peril == "staged"
    assert result.trace.terminal_kind != "died" and not result.trace.terminal
    assert not _PWR(world).events(kind="player_death", frame="session:main")
    _np = _narrate_prompt(provider)
    assert "MORTAL STAKES" in _np and "SHORT of death" in _np
    # the marker persisted for the next turn's standing check
    assert (_PWR(world).state("session:peril", "scene", frame="session:main")
            == "place:study")


def test_staged_mortal_terrible_failure_kills_with_testament(world, monkeypatch):
    # Cx 422 bar 2: staged + mortal_risk + terrible_failure under policy `mortal` →
    # the death receipt owns the terminal; THE FALL + THE TESTAMENT render; `died`
    # consequences are caused_by the DEATH receipt (event-entity row, the 420 lesson).
    from construct import resolution
    from construct.adapter import PorcelainWorldReads as _PWR
    from construct.turnloop import terminal_outcome
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = make_arc()
    seed_arc(world, arc)
    _stage_peril(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_MORTAL_CLASSIFY),
        {"prose": "The gutter gives. The yard comes up. The world goes on without you."},
    ])
    result = run_turn(world, arc, provider, "I press on across the parapet.", turn=2,
                      scope=[PLAYER, "place:study"], death_policy="mortal",
                      scenario_mode="win_loss")
    assert result.trace.terminal is True
    assert result.trace.terminal_kind == "died"
    _preads = _PWR(world)
    assert terminal_outcome(_preads) == "died"
    assert _preads.events(kind="player_death", frame="session:main")
    # no arc_won/arc_lost shape receipt — the death receipt owns the terminal
    assert not _preads.events(kind="arc_won", frame="session:main")
    assert not _preads.events(kind="arc_lost", frame="session:main")
    _np = _narrate_prompt(provider)
    assert "BEAT 1 — THE FALL" in _np and "BEAT 2 — THE TESTAMENT" in _np
    assert "NO rescue invented" in _np
    assert "BEAT 1 — THE RECKONING SCENE" not in _np
    assert "BEAT 1 — THE SETTLING" not in _np
    # died consequences, caused_by the death receipt on the EVENT ENTITY
    assert any(c.startswith("word_spreads:died") for c in result.trace.consequences)
    for _kind in ("word_spreads", "reputation_changes"):
        _evs = _preads.events(kind=_kind)
        assert _evs and any(str(c).startswith("event:player_death_")
                            for c in (_evs[0].caused_by or []))


def test_shielded_policy_wounds_never_kills(world, monkeypatch):
    # Cx 422 bar 3: same staged fatal setup under `shielded` → wound/capture/ruin
    # directive, no death receipt, story continues.
    from construct import resolution
    from construct.adapter import PorcelainWorldReads as _PWR
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = make_arc()
    seed_arc(world, arc)
    _stage_peril(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_MORTAL_CLASSIFY),
        {"prose": "The fall breaks your arm, not your neck."},
    ])
    result = run_turn(world, arc, provider, "I press on across the parapet.", turn=2,
                      scope=[PLAYER, "place:study"], death_policy="shielded")
    assert not result.trace.terminal and result.trace.terminal_kind != "died"
    assert not _PWR(world).events(kind="player_death", frame="session:main")
    _np = _narrate_prompt(provider)
    assert "THE PRICE STOPS SHORT OF DEATH" in _np and "does NOT kill" in _np


def test_premise_policy_folds_death_into_the_premise(world, monkeypatch):
    # Cx 422 bar 4: under `premise` the death is rendered and TRANSFORMED by the
    # story's own premise (the loop resets, the ghost persists) — never terminal.
    from construct import resolution
    from construct.adapter import PorcelainWorldReads as _PWR
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = make_arc()
    seed_arc(world, arc)
    _stage_peril(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_MORTAL_CLASSIFY),
        {"prose": "You die on the yard stones — and wake to the same grey morning."},
    ])
    result = run_turn(world, arc, provider, "I press on across the parapet.", turn=2,
                      scope=[PLAYER, "place:study"], death_policy="premise")
    assert not result.trace.terminal and result.trace.terminal_kind != "died"
    assert not _PWR(world).events(kind="player_death", frame="session:main")
    _np = _narrate_prompt(provider)
    assert "DEATH, TRANSFORMED" in _np and "premise" in _np


def test_death_ends_endless_mode_too(world, monkeypatch):
    # Cx 422 bar 5 (permanence): an endless/freeplay world still STOPS at death.
    from construct import resolution
    from construct.adapter import PorcelainWorldReads as _PWR
    from construct.turnloop import terminal_outcome
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = make_arc()
    seed_arc(world, arc)
    _stage_peril(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_MORTAL_CLASSIFY),
        {"prose": "The river takes you; the town keeps its own hours."},
    ])
    result = run_turn(world, arc, provider, "I press on into the flood.", turn=2,
                      scope=[PLAYER, "place:study"], death_policy="mortal",
                      scenario_mode="endless", endless=True)
    assert result.trace.terminal is True and result.trace.terminal_kind == "died"
    assert terminal_outcome(_PWR(world)) == "died"


def test_peril_clears_on_non_risk_turn_then_restages(world, monkeypatch):
    # Cx 422 bar 8: a non-risk turn releases the peril; a LATER lone mortal-risk turn
    # stages again rather than killing (peril never stalks the player).
    from construct import resolution
    from construct.adapter import PorcelainWorldReads as _PWR
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = make_arc()
    seed_arc(world, arc)
    _stage_peril(world)
    world._extractions.extend([{"items": []}, {"items": []},
                               {"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "mortal_risk": False, "commits": False, "commitment": ""},
        {"prose": "You step back from the edge and breathe."},
        dict(_MORTAL_CLASSIFY),
        {"prose": "You climb out again; the gutter shifts under your weight."},
    ])
    r1 = run_turn(world, arc, provider, "I step back from the edge.", turn=2,
                  scope=[PLAYER, "place:study"], death_policy="mortal")
    assert r1.trace.peril == "cleared"
    assert not (_PWR(world).state("session:peril", "scene",
                                  frame="session:main") or "").strip()
    r2 = run_turn(world, arc, provider, "I climb out onto the parapet again.", turn=3,
                  scope=[PLAYER, "place:study"], death_policy="mortal")
    assert r2.trace.peril == "staged"
    assert r2.trace.terminal_kind != "died"
    assert not _PWR(world).events(kind="player_death", frame="session:main")


# ---------------------------------------------------------------------------
# #93 VOCATIVE TITLE RESOLUTION (Cx 404 C-scope)
# ---------------------------------------------------------------------------

def _chief_and_witness(world, chief_at="place:office"):
    """Canon: a unique title-holder (the chief of police) at `chief_at`, and a
    clue-bearing witness present in the player's study. Returns the cast dict."""
    from construct.cast import CastNode, Clue
    world.porcelain.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:chief", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:chief", "attribute": "name", "value": "Chief Harrow"},
        {"entity": "person:chief", "attribute": "role", "value": "chief of police"},
        {"entity": "person:chief", "attribute": "in", "value": chief_at},
        {"entity": "person:witness", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:witness", "attribute": "in", "value": "place:study"},
    ])
    return {
        "person:witness": CastNode("person:witness", "witness", "the witness",
            holds_clues=(Clue("clue:motive", "pillar:motive", ("fact:motive", "is", "debt"),
                              coverage_effect="genuine", reveal_condition="none"),)),
        "person:chief": CastNode("person:chief", "chief of police", "Chief Harrow",
            holds_clues=(Clue("clue:orders", "pillar:motive", ("fact:orders", "is", "sealed"),
                              coverage_effect="genuine", reveal_condition="none"),)),
    }


def test_vocative_to_absent_title_holder_suppresses_fallback_delivery(world):
    # Cx 404 C: "'Chief!' with the chief absent does not deliver Reed's clue" — the
    # sole-present-NPC fallback must not catch an address to someone who isn't here,
    # and the narrator renders the honest not-here beat.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    cast = _chief_and_witness(world, chief_at="place:office")   # chief NOT in the study
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
        {"prose": "The word hangs in the room; the chief is not here to catch it."},
    ])
    result = run_turn(world, arc, provider, "Chief!", turn=2, cast=cast,
                      scope=["person:witness", "person:chief", PLAYER, "place:study"])
    assert result.trace.vocative.endswith("(ABSENT)")
    assert result.trace.learned_clues == []          # NO clue re-routed to the witness
    assert not _PWR(world).assertion_in_frame(PLAYER_FRAME, "fact:motive", "is", "debt")
    _np = _narrate_prompt(provider)
    assert "CALLED FOR SOMEONE NOT HERE" in _np and "Chief Harrow" in _np
    assert "SPOKEN TO BY TITLE" not in _np


def test_vocative_to_present_title_holder_binds_and_delivers(world):
    # Cx 404 C: 'Chief, …' with the chief PRESENT resolves the address to the canon
    # title-holder — they get the floor (briefing) and their clue is deliverable.
    arc = make_arc()
    seed_arc(world, arc)
    cast = _chief_and_witness(world, chief_at="place:study")    # chief IS here
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"acts": False, "action": "", "speaks": True, "intent": "answer plainly",
         "line_hint": ""},
        {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
        {"prose": "Harrow turns from the window. 'Sealed orders, since you ask.'"},
    ])
    result = run_turn(world, arc, provider, "Chief, what were your orders?", turn=2,
                      cast=cast,
                      scope=["person:witness", "person:chief", PLAYER, "place:study"])
    assert result.trace.vocative.endswith("(present)")
    assert "clue:orders" in result.trace.learned_clues
    _np = _narrate_prompt(provider)
    assert "SPOKEN TO BY TITLE" in _np and "Chief Harrow" in _np


def test_mid_sentence_title_word_is_never_an_address(world):
    # Cx 404 C: address-syntax gate — 'my chief concern' must not resolve as a
    # vocative (no suppression, no binding, ordinary turn).
    arc = make_arc()
    seed_arc(world, arc)
    cast = _chief_and_witness(world, chief_at="place:office")
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"acts": False, "action": "", "speaks": True, "intent": "reassure",
         "line_hint": ""},
        {"prose": "The witness nods along as you lay out your concern."},
    ])
    result = run_turn(world, arc, provider,
                      "My chief concern is the ledger and nothing else.", turn=2,
                      cast=cast,
                      scope=["person:witness", "person:chief", PLAYER, "place:study"])
    assert result.trace.vocative == ""
    _np = _narrate_prompt(provider)
    assert "CALLED FOR SOMEONE NOT HERE" not in _np
    assert "SPOKEN TO BY TITLE" not in _np


def test_vocative_token_forms():
    # the deterministic detector: leading / sole / trailing address forms in;
    # interjections and mid-sentence uses out.
    from construct.turnloop import _vocative_token
    assert _vocative_token("Chief!") == "chief"
    assert _vocative_token("Chief, where were you?") == "chief"
    # Cx 427: interjection lead-ins, case-insensitive, with or without the comma
    assert _vocative_token("Hey, Chief, what were your orders?") == "chief"
    assert _vocative_token("hey, Chief, what were your orders?") == "chief"
    assert _vocative_token("Hey Chief, what were your orders?") == "chief"
    assert _vocative_token("Hey, what's the plan?") == ""
    assert _vocative_token("What do you make of it, Chief?") == "chief"
    assert _vocative_token("Doctor!") == "doctor"
    assert _vocative_token("My chief concern is the ledger.") == ""
    assert _vocative_token("Well, that's odd.") == ""
    assert _vocative_token("I walk to the yard.") == ""


# ---------------------------------------------------------------------------
# #98 FIRST-MENTION PERMANENCE — settle wiring (Cx 415 test bar, wiring layer)
# ---------------------------------------------------------------------------

def test_narrated_named_venue_commits_stub_and_second_mention_binds(world):
    # The founder's Hart-and-Bell case: narrator prose establishes a NAMED venue →
    # a minimal stub commits (kind/name, non-present) and SURVIVES; the next turn's
    # mention BINDS the stub (no duplicate); the player never relocates.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": []})                    # turn 2: player-input extract
    world._extractions.append({"items": [                       # turn 2: post-render extract
        {"entity": "place:hart_and_bell", "attribute": "kind", "value": "inn"},
        {"entity": "place:hart_and_bell", "attribute": "name", "value": "The Hart and Bell"},
        {"entity": "place:hart_and_bell", "attribute": "description",
         "value": "a low coach-yard inn smelling of tallow"},
    ]})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "Before the Hall, you kept a room at The Hart and Bell, above the "
                  "coach yard."},
    ])
    r1 = run_turn(world, arc, provider, "I think back to where I stayed before.",
                  turn=2, scope=[PLAYER, "place:study"])
    assert r1.prose
    p = world.porcelain
    # the stub is REAL and MINIMAL: kind+name, no description, no presence
    assert p.state("place:hart_and_bell", "name")["fact"]["value"] == "The Hart and Bell"
    assert (p.state("place:hart_and_bell", "description").get("fact") or {}) == {} \
        or p.state("place:hart_and_bell", "description").get("status") == "unknown"
    assert p.locate(PLAYER)[0] == "place:study"                 # nobody relocated
    # turn 3: the world mentions it again under a DIFFERENT extraction slug → binds
    world._extractions.append({"items": []})
    world._extractions.append({"items": [
        {"entity": "place:the_hart_and_bell", "attribute": "name",
         "value": "The Hart and Bell"},
        {"entity": "place:the_hart_and_bell", "attribute": "kind", "value": "inn"},
    ]})
    provider2 = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "The Hart and Bell keeps early hours; the ostlers would remember you."},
    ])
    r2 = run_turn(world, arc, provider2, "I recall the inn's mornings.", turn=3,
                  scope=[PLAYER, "place:study"])
    assert r2.prose
    _ents = {str(r.entity) for r in world.buffer.visible()
             if str(r.entity).startswith("place:") and "hart" in str(r.entity)}
    assert _ents == {"place:hart_and_bell"}                     # ONE inn, no twin
    _rcpts = [t for t in (r2.trace.resolver or []) if t[0] == "place:hart_and_bell"]
    assert any(why == "bound" for (_e, _a, why) in _rcpts)


def test_first_risk_shielded_never_stages_or_threatens_death(world, monkeypatch):
    # Cx 426 blocker: a FIRST mortal-risk turn in a `shielded` chapter must not write
    # a lethal-peril marker or tell the narrator death is on the table — the genre
    # decides; the fatal draw caps at wound/capture/ruin.
    from construct import resolution
    from construct.adapter import PorcelainWorldReads as _PWR
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_MORTAL_CLASSIFY),
        {"prose": "The fall breaks your arm, not your neck."},
    ])
    result = run_turn(world, arc, provider, "I leap across the gap.", turn=2,
                      scope=[PLAYER, "place:study"], death_policy="shielded")
    assert result.trace.peril != "staged"
    assert not (_PWR(world).state("session:peril", "scene",
                                  frame="session:main") or "").strip()
    assert not _PWR(world).events(kind="player_death", frame="session:main")
    _np = _narrate_prompt(provider)
    assert "MORTAL STAKES" not in _np and "it can kill" not in _np
    assert "THE PRICE STOPS SHORT OF DEATH" in _np


def test_first_risk_premise_folds_without_staging(world, monkeypatch):
    # Cx 426: a `premise` chapter's first mortal-risk fatal draw folds into the
    # premise directly (the loop IS the safety) — no marker, no death-table staging.
    from construct import resolution
    from construct.adapter import PorcelainWorldReads as _PWR
    monkeypatch.setattr(resolution, "draw_tier", lambda *a, **k: "terrible_failure")
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        dict(_MORTAL_CLASSIFY),
        {"prose": "You die on the stones — and wake to the same grey morning."},
    ])
    result = run_turn(world, arc, provider, "I leap across the gap.", turn=2,
                      scope=[PLAYER, "place:study"], death_policy="premise")
    assert result.trace.peril != "staged"
    assert not (_PWR(world).state("session:peril", "scene",
                                  frame="session:main") or "").strip()
    assert not result.trace.terminal
    _np = _narrate_prompt(provider)
    assert "MORTAL STAKES" not in _np and "DEATH, TRANSFORMED" in _np


def test_vocative_leadin_forms_absent_holder_still_suppresses(world):
    # Cx 427 blocker: 'Hey, Chief, …' with the chief ABSENT must resolve and suppress
    # the sole-present-NPC fallback exactly like the bare form.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    cast = _chief_and_witness(world, chief_at="place:office")
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
        {"prose": "The call goes unanswered; the chief is elsewhere tonight."},
    ])
    result = run_turn(world, arc, provider, "Hey, Chief, what were your orders?",
                      turn=2, cast=cast,
                      scope=["person:witness", "person:chief", PLAYER, "place:study"])
    assert result.trace.vocative.endswith("(ABSENT)")
    assert result.trace.learned_clues == []
    assert not _PWR(world).assertion_in_frame(PLAYER_FRAME, "fact:motive", "is", "debt")
    assert "CALLED FOR SOMEONE NOT HERE" in _narrate_prompt(provider)


def test_vocative_leadin_forms_present_holder_binds(world):
    # Cx 427: the commaed capitalized lead-in binds a PRESENT holder too.
    arc = make_arc()
    seed_arc(world, arc)
    cast = _chief_and_witness(world, chief_at="place:study")
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"acts": False, "action": "", "speaks": True, "intent": "answer", "line_hint": ""},
        {"acts": False, "action": "", "speaks": False, "intent": "", "line_hint": ""},
        {"prose": "Harrow answers without turning from the window."},
    ])
    result = run_turn(world, arc, provider, "Hey Chief, what were your orders?",
                      turn=2, cast=cast,
                      scope=["person:witness", "person:chief", PLAYER, "place:study"])
    assert result.trace.vocative.endswith("(present)")
    assert "clue:orders" in result.trace.learned_clues
    assert "SPOKEN TO BY TITLE" in _narrate_prompt(provider)


def test_frame_only_named_entity_never_enters_the_canon_bind_path(world):
    # Cx 433 blocker regression: a place/person NAMED only in a private frame
    # (knows:/plot:) must not be BOUND by the settle resolver — binding would let
    # full prose rows (description etc.) attach past the stub trim, promoting
    # private memory into world truth. The mention resolves through the STUB gate
    # (minimal rows) instead, and the private frame stays private.
    arc = make_arc()
    seed_arc(world, arc)
    # the inn exists ONLY in the player's memory frame — no canon rows at all
    world.porcelain.ingest_structured([
        {"entity": "place:hart_and_bell", "attribute": "name",
         "value": "The Hart and Bell"},
        {"entity": "place:hart_and_bell", "attribute": "secret",
         "value": "where the letters were exchanged"},
    ], frame=PLAYER_FRAME)
    world._extractions.append({"items": []})
    world._extractions.append({"items": [
        {"entity": "place:hart_and_bell", "attribute": "name",
         "value": "The Hart and Bell"},
        {"entity": "place:hart_and_bell", "attribute": "description",
         "value": "a low coach-yard inn smelling of tallow"},
    ]})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "Talk turns to The Hart and Bell, down in the village."},
    ])
    result = run_turn(world, arc, provider, "I mention the inn.", turn=2,
                      scope=[PLAYER, "place:study"])
    # never BOUND to the frame-only entity (bound would bypass the stub trim)
    _rcpts = [t for t in (result.trace.resolver or [])
              if t[0] == "place:hart_and_bell"]
    assert _rcpts and not any(why == "bound" for (_e, _a, why) in _rcpts)
    # the description never reached canon (stub minimality held)
    _desc = world.porcelain.state("place:hart_and_bell", "description")
    assert not (_desc.get("fact") or {}).get("value")
    # the private frame row is still private, not canon
    _secret = world.porcelain.state("place:hart_and_bell", "secret")
    assert not (_secret.get("fact") or {}).get("value")


# ---------------------------------------------------------------------------
# #97 THE REMEMBRANCER (REMEMBRANCER.md, Cx 434)
# ---------------------------------------------------------------------------

def _mem_classify(**kw):
    base = {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
            "uncertain_of": "", "commits": False, "commitment": ""}
    base.update(kw)
    return base


def test_self_question_is_answered_by_memory_turn_not_an_npc(world):
    # Cx 434 bar: the self-question routes to memory_turn — its stirred memory rides
    # the briefing as second-person interiority alongside ADDRESSED INWARD.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        _mem_classify(asks_self=True),
        {"stirs": True, "memory": "a room above the coach yard, before the Hall",
         "feeling": "familiarity"},
        {"prose": "You remember the room above the coach yard."},
    ])
    result = run_turn(world, arc, provider, "Where did I stay before?", turn=2,
                      scope=[PLAYER, "place:study"])
    assert "memory_turn:cheap" in result.trace.cohort_calls
    assert result.trace.memory.startswith("a room above the coach yard")
    _np = _narrate_prompt(provider)
    assert "YOUR OWN MIND THIS TURN" in _np and "coach yard" in _np
    assert "ADDRESSED INWARD" in _np
    # the memory participant is interiority ONLY — the pin on its contract
    _mem_prompt = next(p for (p, _s, _t) in provider.calls if "OWN MEMORY" in p)
    assert "Never dialogue" in _mem_prompt and "never an action" in _mem_prompt


def test_memory_turn_gated_recall_fires_lookaround_does_not(world):
    # Cx 434 constraint 2: explicit recall fires the participant; a generic
    # look-around never does (no standing vibe trigger).
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []},
                               {"items": []}, {"items": []}])
    provider = StubProvider([
        _mem_classify(recalls=True),
        {"stirs": True, "memory": "rain drying on his coat at the first meeting",
         "feeling": "old caution"},
        {"prose": "The first meeting comes back to you."},
        _mem_classify(),
        {"prose": "The study sits quiet around you."},
    ])
    r1 = run_turn(world, arc, provider, "I think back to our first meeting.", turn=2,
                  scope=[PLAYER, "place:study"])
    assert "memory_turn:cheap" in r1.trace.cohort_calls
    r2 = run_turn(world, arc, provider, "I glance around the room.", turn=3,
                  scope=[PLAYER, "place:study"])
    assert "memory_turn:cheap" not in r2.trace.cohort_calls
    assert r2.trace.memory == ""


def test_declared_memory_commits_frame_rows_and_offscene_person_stub(world):
    # Cx 434 constraints 3+4 / the founder's retcon: "I remember my childhood friend
    # John Johnson…" → knows:<prot> autobiography + a MINIMAL offscene canon person
    # (kind/name/role via the #98 gate — never `in`, never present).
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        _mem_classify(recalls=True, declares_memory=True),
        {"claims": [{"about": "self", "subject": "", "attribute": "childhood_promise",
                     "value": "never to let it happen again"}],
         "people": [{"name": "John Johnson", "relation": "childhood friend"}]},
        {"stirs": True, "memory": "John's face, and the promise", "feeling": "resolve"},
        {"prose": "The promise surfaces whole, with John's face attached."},
    ])
    result = run_turn(world, arc, provider,
                      "I remember my childhood friend John Johnson. I promised I "
                      "would never let this happen again.", turn=2,
                      scope=[PLAYER, "place:study"])
    p = world.porcelain
    # the offscene stub: minimal, real, NOT placed anywhere
    assert p.state("person:john_johnson", "name")["fact"]["value"] == "John Johnson"
    assert p.state("person:john_johnson", "role")["fact"]["value"] == "childhood friend"
    assert not (p.state("person:john_johnson", "in").get("fact") or {}).get("value")
    # the autobiography is frame truth
    assert _PWR(world).assertion_in_frame(
        PLAYER_FRAME, PLAYER, "childhood_promise", "never to let it happen again")
    assert _PWR(world).assertion_in_frame(
        PLAYER_FRAME, PLAYER, "relationship_to_person:john_johnson", "childhood friend")
    assert any(why == "memory_person_stubbed"
               for (_e, _a, why) in (result.trace.resolver or []))


def test_declared_world_claim_becomes_belief_never_canon_or_coverage(world):
    # Cx 434 constraint 3: "I remember the mayor confessing" must not write canon,
    # satisfy pillar coverage, or license a protected key; concealed-vocabulary
    # values are screened at STORAGE time.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        _mem_classify(recalls=True, declares_memory=True),
        {"claims": [
            {"about": "world", "subject": "the mayor", "attribute": "confessed",
             "value": "to the whole affair, years ago"},
            # brushes the arc's concealed vocabulary (the hidden culprit) → screened
            {"about": "world", "subject": "", "attribute": "culprit",
             "value": "person:rival was the culprit all along"},
        ], "people": []},
        {"prose": "The recollection settles uneasily."},
    ])
    result = run_turn(world, arc, provider,
                      "I remember the mayor confessing to the whole affair.", turn=2,
                      scope=[PLAYER, "place:study"])
    reads = _PWR(world)
    # a BELIEF on the protagonist — never a row on a world entity
    assert reads.assertion_in_frame(
        PLAYER_FRAME, PLAYER, "believes_the_mayor_confessed", "to the whole affair, years ago")
    assert not (world.porcelain.state("person:mayor", "confessed").get("fact") or {})
    # arc coverage untouched: the world_condition fact never entered the frame
    assert not reads.assertion_in_frame(PLAYER_FRAME, "fact:secret", "culprit", "person:rival")
    assert result.trace.outcome is None                    # nothing concluded
    # the concealed-vocabulary claim was screened at storage
    assert any(why == "memory_screened" for (_e, _a, why) in (result.trace.resolver or []))


def test_declared_memory_collision_quarantines_first_value_stands(world):
    # Cx 434 constraint 5 / the founder's Westminster-Lancaster rule: a direct
    # attribute collision quarantines — the FIRST establishment stands, the tension
    # surfaces in fiction, never a silent overwrite.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []},
                               {"items": []}, {"items": []}])
    provider = StubProvider([
        _mem_classify(recalls=True, declares_memory=True),
        {"claims": [{"about": "self", "subject": "", "attribute": "childhood_home",
                     "value": "Westminster"}], "people": []},
        {"prose": "Westminster, in the narrow years."},
        _mem_classify(recalls=True, declares_memory=True),
        {"claims": [{"about": "self", "subject": "", "attribute": "childhood_home",
                     "value": "Lancaster"}], "people": []},
        {"stirs": True, "memory": "Westminster is what you remember",
         "feeling": "unease"},
        {"prose": "Lancaster sits oddly against what you remember."},
    ])
    run_turn(world, arc, provider, "I think back to my childhood home in Westminster.",
             turn=2, scope=[PLAYER, "place:study"])
    r2 = run_turn(world, arc, provider, "I think back to my childhood home in Lancaster.",
                  turn=3, scope=[PLAYER, "place:study"])
    reads = _PWR(world)
    assert reads.assertion_in_frame(PLAYER_FRAME, PLAYER, "childhood_home", "Westminster")
    assert not reads.assertion_in_frame(PLAYER_FRAME, PLAYER, "childhood_home", "Lancaster")
    assert any(why == "memory_collision_quarantined"
               for (_e, _a, why) in (r2.trace.resolver or []))
    _np = _narrate_prompt(provider)
    assert "THE MEMORY SITS ODDLY" in _np and "Westminster" in _np


def test_declaration_kind_memory_still_commits(world):
    # Cx 439 #1: the most literal retcon parse — classify says kind=declaration —
    # must NOT take the canon-strict denial; the guarded memory channel runs.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        _mem_classify(kind="declaration", recalls=True, declares_memory=True),
        {"claims": [{"about": "self", "subject": "", "attribute": "childhood_promise",
                     "value": "never to let it happen again"}],
         "people": [{"name": "John Johnson", "relation": "childhood friend"}]},
        {"prose": "The promise surfaces whole, with John's face attached."},
    ])
    result = run_turn(world, arc, provider,
                      "I remember my childhood friend John Johnson. I promised I "
                      "would never let this happen again.", turn=2,
                      scope=[PLAYER, "place:study"], mode="pure")
    assert "canon-strict" not in result.prose               # never the generic denial
    assert world.porcelain.state("person:john_johnson", "name")["fact"]["value"] \
        == "John Johnson"
    assert _PWR(world).assertion_in_frame(
        PLAYER_FRAME, PLAYER, "childhood_promise", "never to let it happen again")


def test_declaration_kind_collision_still_quarantines(world):
    # Cx 439 #1 (second regression): the Westminster/Lancaster rule holds when the
    # colliding declaration parses as kind=declaration.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []},
                               {"items": []}, {"items": []}])
    provider = StubProvider([
        _mem_classify(kind="declaration", recalls=True, declares_memory=True),
        {"claims": [{"about": "self", "subject": "", "attribute": "childhood_home",
                     "value": "Westminster"}], "people": []},
        {"prose": "Westminster, in the narrow years."},
        _mem_classify(kind="declaration", recalls=True, declares_memory=True),
        {"claims": [{"about": "self", "subject": "", "attribute": "childhood_home",
                     "value": "Lancaster"}], "people": []},
        {"prose": "Lancaster sits oddly against what you remember."},
    ])
    run_turn(world, arc, provider, "I think back to my childhood home in Westminster.",
             turn=2, scope=[PLAYER, "place:study"], mode="pure")
    r2 = run_turn(world, arc, provider, "I think back to my childhood home in Lancaster.",
                  turn=3, scope=[PLAYER, "place:study"], mode="pure")
    reads = _PWR(world)
    assert reads.assertion_in_frame(PLAYER_FRAME, PLAYER, "childhood_home", "Westminster")
    assert not reads.assertion_in_frame(PLAYER_FRAME, PLAYER, "childhood_home", "Lancaster")
    assert any(why == "memory_collision_quarantined"
               for (_e, _a, why) in (r2.trace.resolver or []))
    assert "THE MEMORY SITS ODDLY" in _narrate_prompt(provider)


def test_compact_memory_stub_default_does_not_collide():
    # Cx 439 #2: narrative-memory compaction (task `mem`) must never receive the
    # Remembrancer's silent default — an unstubbed compaction raises (queue
    # exhaustion), exactly as before #97.
    import pytest as _pytest

    from construct import cohorts as _co
    from construct.provider import ProviderTransportError, StubProvider as _SP
    with _pytest.raises(ProviderTransportError):
        _co.compact_memory(_SP([]), "", "older beat")


def test_settle_reconstructs_name_evidence_when_extractor_omits_names(world):
    # Cx 443 note folded in: the LIVE extractor shape — kind rows, slug ids, NO name
    # rows — must still stub the proper-named venue through prose reconstruction,
    # while lowercase-in-prose places stay denied. Pins the settle wiring itself.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.append({"items": []})
    world._extractions.append({"items": [                       # the probe's real shape
        {"entity": "place:the_hart_and_bell", "attribute": "kind", "value": "inn"},
        {"entity": "place:coach_yard", "attribute": "kind", "value": "coach_yard"},
    ]})
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "Before the Hall, you had a room at The Hart and Bell, above the "
                  "coach yard."},
    ])
    r = run_turn(world, arc, provider, "I think back to where I stayed.", turn=2,
                 scope=[PLAYER, "place:study"])
    assert r.prose
    p = world.porcelain
    assert p.state("place:the_hart_and_bell", "name")["fact"]["value"] \
        == "The Hart and Bell"                                  # reconstructed, cased
    assert not (p.state("place:coach_yard", "kind").get("fact") or {})  # denied


# ---------------------------------------------------------------------------
# Room-coherence fixes (founder live test pass, 2026-07-04: the drawing-room twin)
# ---------------------------------------------------------------------------

def test_move_synonym_for_current_room_binds_no_twin(world):
    # THE DRAWING-ROOM INCIDENT: the player, standing in the established parlor, says
    # "I step back into the drawing room" — a natural synonym. The old roster EXCLUDED
    # the current scene, so the bind could never see it and minted place:drawing_room,
    # splitting the cast across twin rooms. Now: binds to the room they're in,
    # already-here no-op, and the synonym is LEARNED as an alias.
    arc = make_arc()
    seed_arc(world, arc)
    from construct.arc.executor import turn_time as _tt
    world.porcelain.ingest_structured([
        {"entity": "place:parlor", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:parlor", "attribute": "name", "value": "the parlor"},
        {"entity": PLAYER, "attribute": "in", "value": "place:parlor",
         "value_type": "entity", "valid_from": _tt(1)},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the drawing room", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"verdict": "existing", "match": "place:parlor"},      # the dst bind sees HOME
        {"prose": "You are already in the parlor; the fire has not moved."},
    ])
    result = run_turn(world, arc, provider, "I step back into the drawing room.", turn=2,
                      scope=[PLAYER, "place:parlor"])
    assert result.trace.movement_status == "clear"
    assert result.trace.same_place is True                          # a no-op, not travel
    assert world.porcelain.locate(PLAYER)[0] == "place:parlor"      # never left
    assert not PorcelainWorldReads(world).has_entity("place:drawing_room")  # NO twin
    # the world learned the player's word — next time refer() binds it at tier 1
    _alias = world.porcelain.state("place:parlor", "alias")
    assert (_alias.get("fact") or {}).get("value") == "drawing room"


def test_move_ambiguous_destination_asks_never_mints(world):
    # ASK, NEVER HALLUCINATE (founder 2026-07-04): an ambiguous destination renders a
    # clarify beat — the world asks which the player means; no mint, no relocation,
    # no invented arrival.
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:north_cellar", "attribute": "kind", "value": "cellar",
         "timeless": True},
        {"entity": "place:north_cellar", "attribute": "name", "value": "the north cellar"},
        {"entity": "place:south_cellar", "attribute": "kind", "value": "cellar",
         "timeless": True},
        {"entity": "place:south_cellar", "attribute": "name", "value": "the south cellar"},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the basement", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"verdict": "ambiguous", "match": ""},
        {"prose": "“Which cellar do you mean, sir — north or south?”"},
    ])
    result = run_turn(world, arc, provider, "I head down to the basement.", turn=2,
                      scope=[PLAYER, "place:study", "place:north_cellar",
                             "place:south_cellar"])
    assert result.trace.movement_status == "ambiguous"
    assert world.porcelain.locate(PLAYER)[0] == "place:study"       # unmoved
    assert not PorcelainWorldReads(world).has_entity("place:basement")
    _np = _narrate_prompt(provider)
    assert "THE DESTINATION IS UNCLEAR" in _np and "Never guess" in _np


def test_narrator_briefed_places_keep_their_names(world):
    # The drift's SOURCE was the narrator renaming the parlor "the drawing room" —
    # the render contract now pins canonical place names on every turn.
    arc = make_arc()
    seed_arc(world, arc)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "The study sits quiet around you."},
    ])
    run_turn(world, arc, provider, "I take in the room.", turn=2,
             scope=[PLAYER, "place:study"])
    _np = _narrate_prompt(provider)
    assert "PLACES KEEP THEIR NAMES" in _np
    assert "never 'the drawing room'" in _np


# ---------------------------------------------------------------------------
# #101 DISTANCE FIDELITY (Cx 445 constraints; founder probe 8: the village teleport)
# ---------------------------------------------------------------------------

def _hall_world(world):
    """Origin with real topology: the parlor sits IN Brackenmere Hall (chain depth 2)."""
    from construct.arc.executor import turn_time
    world.porcelain.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "manor", "timeless": True},
        {"entity": "place:hall", "attribute": "name", "value": "Brackenmere Hall"},
        {"entity": "place:parlor", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:parlor", "attribute": "name", "value": "the parlor"},
        {"entity": "place:parlor", "attribute": "in", "value": "place:hall",
         "value_type": "entity"},
        # valid_from supersedes the fixture's study placement (single-parent semantics)
        {"entity": PLAYER, "attribute": "in", "value": "place:parlor",
         "value_type": "entity", "valid_from": turn_time(1)},
    ])


def test_unknown_distance_move_prices_by_model_with_hygienic_ids(world):
    # The village teleport, closed by the INVERSION (Cx 454): the map can't prove
    # parlor→consulting-room is local, so the move is DISTANCE UNKNOWN — the model
    # prices it, the render is scale-neutral, ids stay hygienic, and NO farness is
    # ever stored (no journey event, no "long" anywhere durable).
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    _hall_world(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the consulting room in the village",
         "requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
         "commitment": ""},
        {"verdict": "new", "match": ""},                     # the dst bind: genuinely new
        {"prose": "The storm walks you down the long dark lane to the village."},
        {"advance_minutes": 75, "jump_to_phase": "", "jump_days": 0,
         "reason": "a night walk to the village"},           # the journey estimate
    ])
    result = run_turn(world, arc, provider, "I go to the consulting room in the village.",
                      turn=2, scope=[PLAYER, "place:parlor"])
    p = world.porcelain
    # hygienic ids: child nested in a thin container shell
    assert p.locate(PLAYER)[0] == "place:consulting_room"
    assert p.state("place:consulting_room", "in")["fact"]["value"] == "place:village"
    assert p.state("place:village", "kind")["fact"]["value"] == "village"
    assert not _PWR(world).has_entity("place:consulting_room_in_the_village")
    # distance unknown: model-priced, scale-neutral render, NOTHING durable stored
    assert result.trace.distance_unknown == "place:parlor->place:consulting_room"
    assert not _PWR(world).events(kind="journey")            # derived farness never stored
    assert "MOVEMENT AT ITS TRUE SCALE" in _narrate_prompt(provider)
    _elp = next((pr for (pr, _s, _t) in provider.calls
                 if "CANNOT PROVE" in pr), None)
    assert _elp is not None
    assert result.trace.time_advanced == 75                  # the real cost, not 6 min


def test_sibling_rooms_are_provably_near_bucket_kept(world):
    # parlor → study, siblings under the hall: NEARNESS proven deterministically —
    # the 6-minute bucket stays, no model pricing, no scale-neutral directive.
    arc = make_arc()
    seed_arc(world, arc)
    _hall_world(world)
    world.porcelain.ingest_structured([
        {"entity": "place:study", "attribute": "in", "value": "place:hall",
         "value_type": "entity"}])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the study", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "You cross the passage into the study."},
    ])
    result = run_turn(world, arc, provider, "I go to the study.", turn=2,
                      scope=[PLAYER, "place:parlor", "place:study"])
    assert world.porcelain.locate(PLAYER)[0] == "place:study"
    assert result.trace.distance_unknown == ""
    assert "MOVEMENT AT ITS TRUE SCALE" not in _narrate_prompt(provider)
    assert result.trace.time_advanced == 6                   # the local bucket held


def test_ambiguous_locative_container_asks_never_mints(world):
    # "in the village" with TWO known villages: the ask path, no mint, no guess.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:north_village", "attribute": "kind", "value": "village",
         "timeless": True},
        {"entity": "place:north_village", "attribute": "name", "value": "North Village"},
        {"entity": "place:south_village", "attribute": "kind", "value": "village",
         "timeless": True},
        {"entity": "place:south_village", "attribute": "name", "value": "South Village"},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the smithy in the village", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"verdict": "new", "match": ""},
        {"prose": "“Which village, sir — north or south?”"},
    ])
    result = run_turn(world, arc, provider, "I ride to the smithy in the village.",
                      turn=2, scope=[PLAYER, "place:study", "place:north_village",
                                     "place:south_village"])
    assert result.trace.movement_status == "ambiguous"
    assert world.porcelain.locate(PLAYER)[0] == "place:study"
    assert not _PWR(world).has_entity("place:smithy")
    assert "THE DESTINATION IS UNCLEAR" in _narrate_prompt(provider)


def test_same_place_synonym_charges_no_move_time(world):
    # Cx 445 wrinkle: the already-here bind must not pay the 6-minute move bucket —
    # the input's own move verbs would otherwise still hit it.
    arc = make_arc()
    seed_arc(world, arc)
    from construct.arc.executor import turn_time as _tt
    world.porcelain.ingest_structured([
        {"entity": "place:parlor", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:parlor", "attribute": "name", "value": "the parlor"},
        {"entity": PLAYER, "attribute": "in", "value": "place:parlor",
         "value_type": "entity", "valid_from": _tt(1)},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the drawing room", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"verdict": "existing", "match": "place:parlor"},
        {"prose": "You are already in the parlor."},
    ])
    result = run_turn(world, arc, provider, "I walk back into the drawing room.", turn=2,
                      scope=[PLAYER, "place:parlor"])
    assert result.trace.same_place is True
    assert result.trace.time_advanced == 1                   # a beat, not a move


def test_move_exact_current_room_name_is_a_time_noop(world):
    # Cx 447 blocker: "I go to the study" while STANDING in the study resolved through
    # the primary refer path and charged the 6-minute move bucket. All already-here
    # paths are now a no-op: same_place, 1-minute beat, no relocation churn.
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:study", "attribute": "name", "value": "the study"}])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the study", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "You are already in the study."},
    ])
    result = run_turn(world, arc, provider, "I go to the study.", turn=2,
                      scope=[PLAYER, "place:study"])
    assert result.trace.movement_status == "clear"
    assert result.trace.same_place is True
    assert result.trace.time_advanced == 1                    # a beat, never a move
    assert world.porcelain.locate(PLAYER)[0] == "place:study"


def test_take_synonym_binds_scoped_scene_object(world):
    # Cx 447 note pinned: the SCOPED refer at the take seam lets "the blade" bind the
    # scene's established knife at tier 2 — no obj:blade sibling ever mints (the
    # founder's object-synonym mandate).
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "obj:knife", "attribute": "kind", "value": "knife", "timeless": True},
        {"entity": "obj:knife", "attribute": "name", "value": "a boning knife"},
        {"entity": "obj:knife", "attribute": "in", "value": "place:study",
         "value_type": "entity"},
    ])
    world._extractions.append({"items": []})                   # player-input extract
    world._extractions.append({"entity_id": "obj:knife",       # refer tier-2 judgment
                               "confidence": 0.9, "signals": ["synonym"]})
    world._extractions.append({"items": []})                   # post-render extract
    provider = StubProvider([
        {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": "", "commits": False, "commitment": "",
         "takes": "the blade"},
        {"prose": "You take up the boning knife."},
    ])
    result = run_turn(world, arc, provider, "I take the blade.", turn=2,
                      scope=[PLAYER, "place:study", "obj:knife"])
    assert result.trace.took == "obj:knife"
    assert world.porcelain.locate("obj:knife")[0] == PLAYER    # held, the real knife
    assert not _PWR(world).has_entity("obj:blade")             # no sibling minted


def test_wrapper_world_cross_site_move_is_distance_unknown(world):
    # THE INVERSION'S WIN (Cx 454, founder's shape challenge): under a shared WORLD
    # wrapper (room→hall→world vs room→village→world) the old disjoint-chain proxy
    # went blind. Nearness can't be proven (different immediate parents, no route),
    # so the move is distance-unknown and the MODEL prices it — wrapped worlds keep
    # honest travel costs with no declared-scale metadata.
    arc = make_arc()
    seed_arc(world, arc)
    from construct.arc.executor import turn_time as _tt
    world.porcelain.ingest_structured([
        {"entity": "place:world", "attribute": "kind", "value": "region", "timeless": True},
        {"entity": "place:hall", "attribute": "kind", "value": "manor", "timeless": True},
        {"entity": "place:hall", "attribute": "in", "value": "place:world",
         "value_type": "entity"},
        {"entity": "place:parlor", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:parlor", "attribute": "name", "value": "the parlor"},
        {"entity": "place:parlor", "attribute": "in", "value": "place:hall",
         "value_type": "entity"},
        {"entity": "place:village", "attribute": "kind", "value": "village", "timeless": True},
        {"entity": "place:village", "attribute": "in", "value": "place:world",
         "value_type": "entity"},
        {"entity": "place:forge", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:forge", "attribute": "name", "value": "the forge"},
        {"entity": "place:forge", "attribute": "in", "value": "place:village",
         "value_type": "entity"},
        {"entity": PLAYER, "attribute": "in", "value": "place:parlor",
         "value_type": "entity", "valid_from": _tt(1)},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the forge", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "You walk down to the forge in the village."},
        {"advance_minutes": 40, "jump_to_phase": "", "jump_days": 0,
         "reason": "the walk down to the village"},
    ])
    result = run_turn(world, arc, provider, "I go to the forge.", turn=2,
                      scope=[PLAYER, "place:parlor", "place:forge"])
    assert world.porcelain.locate(PLAYER)[0] == "place:forge"
    assert result.trace.distance_unknown == "place:parlor->place:forge"
    assert result.trace.time_advanced == 40   # the model priced it — the wrapper is moot


def test_ambiguous_container_by_name_kind_evidence_asks(world):
    # Cx 449 blocker: the container match must read WORLD FACTS (name/kind), never
    # the id wording — place:north / place:south with kind=village and names
    # "North Village"/"South Village" ARE two villages; "in the village" must ASK,
    # and neither child nor container may mint.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:north", "attribute": "kind", "value": "village", "timeless": True},
        {"entity": "place:north", "attribute": "name", "value": "North Village"},
        {"entity": "place:south", "attribute": "kind", "value": "village", "timeless": True},
        {"entity": "place:south", "attribute": "name", "value": "South Village"},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the smithy in the village", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"verdict": "new", "match": ""},
        {"prose": "“Which village, sir — north or south?”"},
    ])
    result = run_turn(world, arc, provider, "I ride to the smithy in the village.",
                      turn=2, scope=[PLAYER, "place:study", "place:north", "place:south"])
    assert result.trace.movement_status == "ambiguous"
    assert world.porcelain.locate(PLAYER)[0] == "place:study"
    assert not _PWR(world).has_entity("place:smithy")
    assert not _PWR(world).has_entity("place:village")
    assert "THE DESTINATION IS UNCLEAR" in _narrate_prompt(provider)


def test_unique_container_binds_by_name_kind_evidence(world):
    # The unique half of the same rule: ONE known village (id place:north, name
    # "North Village") — "the smithy in the village" nests in the REAL village,
    # never a fresh generic place:village twin.
    from construct.adapter import PorcelainWorldReads as _PWR
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:north", "attribute": "kind", "value": "village", "timeless": True},
        {"entity": "place:north", "attribute": "name", "value": "North Village"},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the smithy in the village", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        # no dst-bind stub: the unique container match takes the COMPOUND path
        # (straight to the nesting grant), never the semantic-bind cohort
        {"prose": "You ride down into North Village and find the smithy."},
    ])
    run_turn(world, arc, provider, "I ride to the smithy in the village.", turn=2,
             scope=[PLAYER, "place:study", "place:north"])
    p = world.porcelain
    assert p.locate(PLAYER)[0] == "place:smithy"
    assert p.state("place:smithy", "in")["fact"]["value"] == "place:north"  # the REAL one
    assert not _PWR(world).has_entity("place:village")                      # no twin


def test_direct_clear_route_proves_nearness(world):
    # Cx 458 blocker regression: two places with DIFFERENT parents but a direct
    # clear `connects_to` way between them (a lane, a corridor, a lift) are provably
    # near — no distance_unknown, no scale-neutral directive, deterministic bucket.
    from construct.arc.executor import turn_time as _tt
    arc = make_arc()
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "manor", "timeless": True},
        {"entity": "place:parlor", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:parlor", "attribute": "name", "value": "the parlor"},
        {"entity": "place:parlor", "attribute": "in", "value": "place:hall",
         "value_type": "entity"},
        {"entity": "place:gatehouse", "attribute": "kind", "value": "gatehouse",
         "timeless": True},
        {"entity": "place:gatehouse", "attribute": "name", "value": "the gatehouse"},
        # different roots — but a DIRECT connecting way exists
        {"entity": "place:parlor", "attribute": "connects_to", "value": "place:gatehouse",
         "value_type": "entity"},
        {"entity": PLAYER, "attribute": "in", "value": "place:parlor",
         "value_type": "entity", "valid_from": _tt(1)},
    ])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the gatehouse", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "You cross to the gatehouse."},
    ])
    result = run_turn(world, arc, provider, "I go to the gatehouse.", turn=2,
                      scope=[PLAYER, "place:parlor", "place:gatehouse"])
    assert world.porcelain.locate(PLAYER)[0] == "place:gatehouse"
    assert result.trace.distance_unknown == ""               # the route PROVED nearness
    assert "MOVEMENT AT ITS TRUE SCALE" not in _narrate_prompt(provider)
    assert result.trace.time_advanced == 6                   # deterministic bucket held


# ---------------------------------------------------------------------------
# #102 JOURNEY DELIBERATION (Cx 457; founder-shaped: the mind weighs it first)
# ---------------------------------------------------------------------------

def _deadline_arc(threshold: float = 100.0):
    from construct.arc.conditions import Quantity
    from construct.clock import ELAPSED_ATTR, ELAPSED_ENTITY
    return replace(make_arc(), failure_when=Quantity(
        ELAPSED_ENTITY, ELAPSED_ATTR, ">=", threshold))


def test_journey_deliberation_holds_move_once_then_proceeds_on_cache(world):
    # Founder's shape end-to-end: deadline at 100 min, clock near zero — a ride the
    # estimator prices at 90 min against ~100 left... make it CROSS: estimate 120.
    # Turn A: the move HOLDS, the mind weighs it (second-person, open question),
    # the accept marker carries the cached estimate. Turn B (the player insists):
    # the move COMMITS with no second warning, priced by the CACHED estimate.
    arc = _deadline_arc(threshold=100.0)
    seed_arc(world, arc)
    _hall_world(world)
    world._extractions.extend([{"items": []}, {"items": []},
                               {"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the consulting room in the village",
         "requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
         "commitment": ""},
        {"verdict": "new", "match": ""},                      # dst bind: genuinely new
        {"advance_minutes": 120, "jump_to_phase": "", "jump_days": 0,
         "reason": "a long night ride"},                      # the PRE-COMMIT estimate
        {"prose": "You pause at the door, weighing the road against the hour."},
        # ---- turn B: the player insists ----
        {"kind": "action", "moves_to": "the consulting room in the village",
         "requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
         "commitment": ""},
        {"verdict": "new", "match": ""},
        {"prose": "You take the road anyway; the night takes its due."},
    ])
    r1 = run_turn(world, arc, provider, "I ride to the consulting room in the village.",
                  turn=2, scope=[PLAYER, "place:parlor"])
    assert r1.trace.movement_status == "deliberating"
    assert world.porcelain.locate(PLAYER)[0] == "place:parlor"      # NOT moved
    assert not PorcelainWorldReads(world).has_entity("place:consulting_room")
    _np = _narrate_prompt(provider)
    assert "YOUR OWN MIND WEIGHS IT" in _np
    assert "has NOT moved" in _np and "open question" in _np
    r2 = run_turn(world, arc, provider, "I ride to the consulting room in the village.",
                  turn=3, scope=[PLAYER, "place:parlor"])
    assert r2.trace.movement_status in ("clear", "obscured")        # committed now
    assert world.porcelain.locate(PLAYER)[0] == "place:consulting_room"
    assert r2.trace.deliberating == ""                              # one warning, once
    assert r2.trace.journey_est == 120                              # the CACHED price
    assert r2.trace.time_advanced == 120                            # reused, not re-asked


def test_journey_within_budget_commits_without_deliberation(world):
    # est < remaining: no warning, the move commits, and the pre-commit estimate is
    # REUSED as the turn's time (never priced twice).
    arc = _deadline_arc(threshold=500.0)
    seed_arc(world, arc)
    _hall_world(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the consulting room in the village",
         "requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
         "commitment": ""},
        {"verdict": "new", "match": ""},
        {"advance_minutes": 75, "jump_to_phase": "", "jump_days": 0,
         "reason": "a night walk"},                           # pre-commit estimate
        {"prose": "You go down to the village through the rain."},
    ])
    result = run_turn(world, arc, provider,
                      "I go to the consulting room in the village.", turn=2,
                      scope=[PLAYER, "place:parlor"])
    assert result.trace.movement_status in ("clear", "obscured")
    assert result.trace.deliberating == ""
    assert world.porcelain.locate(PLAYER)[0] == "place:consulting_room"
    assert result.trace.time_advanced == 75                   # the one estimate, reused


def test_no_deadline_means_no_deliberation(world):
    # distance uncertainty ALONE never warns (Cx 457): without an established
    # deadline the unknown-distance move just commits and model-prices.
    arc = make_arc()                                          # no failure_when
    seed_arc(world, arc)
    _hall_world(world)
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the consulting room in the village",
         "requires": [], "needs_test": False, "uncertain_of": "", "commits": False,
         "commitment": ""},
        {"verdict": "new", "match": ""},
        {"prose": "You walk down to the village."},
        {"advance_minutes": 60, "jump_to_phase": "", "jump_days": 0,
         "reason": "the walk"},                               # settle-time estimate
    ])
    result = run_turn(world, arc, provider,
                      "I go to the consulting room in the village.", turn=2,
                      scope=[PLAYER, "place:parlor"])
    assert result.trace.deliberating == ""
    assert result.trace.movement_status in ("clear", "obscured")
    assert "YOUR OWN MIND WEIGHS IT" not in _narrate_prompt(provider)


def test_near_move_under_deadline_never_deliberates(world):
    # a provably-near step (siblings under the hall) never warns even with the
    # deadline tight — the deliberation is for unpriceable travel, not doors.
    arc = _deadline_arc(threshold=10.0)                       # nearly out of time
    seed_arc(world, arc)
    _hall_world(world)
    world.porcelain.ingest_structured([
        {"entity": "place:study", "attribute": "in", "value": "place:hall",
         "value_type": "entity"}])
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the study", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "You cross the passage into the study."},
    ])
    result = run_turn(world, arc, provider, "I go to the study.", turn=2,
                      scope=[PLAYER, "place:parlor", "place:study"])
    assert result.trace.deliberating == ""
    assert world.porcelain.locate(PLAYER)[0] == "place:study"


def _door_between(world, a: str, b: str, state: str):
    # PB's portal shape (test_route.py): host-declared traversal policy + links
    world.porcelain.ingest_structured([
        {"entity": "traversal:door", "attribute": "blocks_when_state", "value": "shut",
         "timeless": True},
        {"entity": "obj:door1", "attribute": "kind", "value": "door", "timeless": True},
        {"entity": "obj:door1", "attribute": "state", "value": state},
        {"entity": a, "attribute": "connects_to", "value": "obj:door1",
         "value_type": "entity", "timeless": True},
        {"entity": "obj:door1", "attribute": "connects_to", "value": b,
         "value_type": "entity", "timeless": True},
    ])


def test_open_door_route_is_near_no_deliberation(world):
    # Cx 465 #1: PB routes a door as place -> obj:door -> place (len 3). An OPEN
    # door between differently-rooted places is a STEP — near, no deliberation even
    # at deadline's edge, no distance_unknown, deterministic bucket.
    from construct.arc.executor import turn_time as _tt
    arc = _deadline_arc(threshold=10.0)                       # nearly out of time
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:parlor", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:parlor", "attribute": "name", "value": "the parlor"},
        {"entity": "place:annex", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:annex", "attribute": "name", "value": "the annex"},
        {"entity": PLAYER, "attribute": "in", "value": "place:parlor",
         "value_type": "entity", "valid_from": _tt(1)},
    ])
    _door_between(world, "place:parlor", "place:annex", state="open")
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the annex", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "You step through the open door into the annex."},
    ])
    result = run_turn(world, arc, provider, "I go through to the annex.", turn=2,
                      scope=[PLAYER, "place:parlor", "place:annex"])
    assert world.porcelain.locate(PLAYER)[0] == "place:annex"
    assert result.trace.deliberating == ""
    assert result.trace.distance_unknown == ""                # the portal route is NEAR
    assert result.trace.time_advanced == 6                    # the local bucket held


def test_blocked_route_never_renders_as_deliberation(world):
    # Cx 465 #2: a SHUT door is a blocked route, not a deadline choice — passability
    # verdicts first; only a move that WOULD commit may deliberate.
    from construct.arc.executor import turn_time as _tt
    arc = _deadline_arc(threshold=10.0)
    seed_arc(world, arc)
    world.porcelain.ingest_structured([
        {"entity": "place:parlor", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:parlor", "attribute": "name", "value": "the parlor"},
        {"entity": "place:annex", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "place:annex", "attribute": "name", "value": "the annex"},
        {"entity": PLAYER, "attribute": "in", "value": "place:parlor",
         "value_type": "entity", "valid_from": _tt(1)},
    ])
    _door_between(world, "place:parlor", "place:annex", state="shut")
    world._extractions.extend([{"items": []}, {"items": []}])
    provider = StubProvider([
        {"kind": "action", "moves_to": "the annex", "requires": [],
         "needs_test": False, "uncertain_of": "", "commits": False, "commitment": ""},
        {"prose": "The door will not give."},
    ])
    result = run_turn(world, arc, provider, "I go through to the annex.", turn=2,
                      scope=[PLAYER, "place:parlor", "place:annex"])
    assert result.trace.movement_status == "blocked"
    assert result.trace.movement_obstruction is not None
    assert result.trace.deliberating == ""                    # never a deadline choice
    assert world.porcelain.locate(PLAYER)[0] == "place:parlor"


def test_journey_accept_key_is_a_fixed_digest():
    # Cx 465 #3: the marker key never substrings away its components — fixed-size
    # digest over origin|destination|hazard|coordinate; a moved deadline re-warns.
    from construct.turnloop import _journey_accept_key as k
    long_origin = "place:" + "very_long_origin_" * 10
    long_dest = "an_extraordinarily_long_novel_destination_slug_" * 4
    a = k(long_origin, long_dest, 100.0)
    b = k(long_origin, long_dest, 250.0)                      # the deadline moved
    assert a != b                                             # fresh warning key
    assert a == k(long_origin, long_dest, 100.0)              # deterministic
    assert len(a) == len(b) == len("jacc_") + 20              # fixed size, no truncation
    assert a.startswith("jacc_")


# ---------------------------------------------------------------------------
# WORLD LAWS (#105, WORLD-LAWS.md, Cx 470) — the reserved briefing lane + the
# shared adjudication block at play time.
# ---------------------------------------------------------------------------

_LAWS = [
    {"name": "The Ledger of Hours", "register": "systemic",
     "rule": "every favor owed is recorded and must be repaid in kind",
     "cost_limit": "a debt unpaid compounds", "embodiment": "the Clerks",
     "texture": "ledger-slips", "nearest_borrowed_shape": "",
     "changed_consequence": "rank is a running balance", "disclosure": "understood"},
    {"name": "The Salt Concord", "register": "social",
     "rule": "no violence may pass between those who have shared salt",
     "cost_limit": "an oathbreaker is barred from every table",
     "embodiment": "the table-keepers", "texture": "the salt bowl at every door",
     "nearest_borrowed_shape": "guest-right",
     "changed_consequence": "hospitality is a weaponizable jurisdiction",
     "disclosure": "understood"},
    {"name": "The Undertow", "register": "environmental",
     "rule": "the fog carries sound backward — words arrive before they are spoken",
     "cost_limit": "listeners sicken with borrowed time",
     "embodiment": "the wardens of the shore", "texture": "wax-plugged ears",
     "nearest_borrowed_shape": "prophecy",
     "changed_consequence": "foreknowledge is a public hazard, not a gift",
     "disclosure": "discovered"},
]


class TestWorldLaws:
    def test_law_lane_survives_overcrowded_pins(self, world):
        # Cx 470 ruling 4 + test bar: 3 laws plus MORE than _PIN_CAP active pins
        # still brief every law — the constitution rides a reserved lane AHEAD
        # of the capped PINS block, never competing under the cap.
        from construct.arc.grammar import Pin
        from construct.turnloop import _PIN_CAP
        crowd = tuple(
            Pin(f"pin:crowd{i}", "region", "place:study", f"crowding directive {i}",
                subject_attribute=f"detail{i}", anchor="place:study", severity=0.9)
            for i in range(_PIN_CAP + 2))
        arc = replace(make_arc(), pins=crowd)
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "The study holds its breath."},
        ])
        result = run_turn(world, arc, provider, "I look around.", turn=1,
                          laws=_LAWS)
        brief = _narrate_prompt(provider)
        assert len(result.trace.pins) == _PIN_CAP + 2   # all active…
        assert "PINNED AWARENESS" in brief              # …capped block present
        for law in _LAWS:
            assert law["name"] in brief                 # every law briefed
        # the reserved lane renders BEFORE the ordinary pins
        assert brief.index("WORLD LAWS") < brief.index("PINNED AWARENESS")
        assert result.trace.laws == [law["name"] for law in _LAWS]

    def test_discovered_law_briefs_as_hidden(self, world):
        # Founder disclosure ruling: an 'understood' law is open lived context;
        # a 'discovered' law binds silently — woven, never stated.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "Fog against the glass."},
        ])
        run_turn(world, arc, provider, "I listen.", turn=1, laws=_LAWS)
        brief = _narrate_prompt(provider)
        assert "STILL UNDISCOVERED" in brief
        # the hidden law sits under the weave directive, after the open laws
        assert brief.index("The Undertow") > brief.index("STILL UNDISCOVERED")
        assert brief.index("The Ledger of Hours") < brief.index("STILL UNDISCOVERED")

    def test_classify_receives_the_same_laws_block(self, world):
        # Cx 470 test bar: consumers get the SAME rendered law objects — the
        # classify (assured/refused) feed carries laws_block(laws) verbatim,
        # the identical render the build-side authors received.
        from construct.laws import laws_block
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "You weigh the debt."},
        ])
        run_turn(world, arc, provider, "I call in the favor.", turn=1, laws=_LAWS)
        classify_prompt = provider.calls[0][0]
        assert laws_block(_LAWS) in classify_prompt
        assert "JUDGE AGAINST THE LAWS" in classify_prompt

    def test_no_laws_no_lane(self, world):
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "Quiet."},
        ])
        result = run_turn(world, arc, provider, "I wait.", turn=1)
        assert "WORLD LAWS" not in _narrate_prompt(provider)
        assert "JUDGE AGAINST THE LAWS" not in provider.calls[0][0]
        assert result.trace.laws == []

    def test_reality_contract_rides_the_no_law_case(self, world):
        # Cx 475 note: the reality register's one-line contract reaches the
        # briefing lane AND the adjudication feeds even when no laws exist —
        # "in a real-world register…" always has an explicit referent.
        arc = make_arc()
        seed_arc(world, arc)
        world._extractions.append({"items": []})
        world._extractions.append({"items": []})
        provider = StubProvider([
            {"kind": "action", "moves_to": "", "requires": [], "needs_test": False,
             "uncertain_of": ""},
            {"prose": "The world stays stubbornly real."},
        ])
        result = run_turn(world, arc, provider, "I try to fly.", turn=1,
                          reality="real")
        assert "THE REALITY REGISTER: REAL" in _narrate_prompt(provider)
        assert "THE REALITY REGISTER: REAL" in provider.calls[0][0]  # classify
        assert result.trace.laws == []
