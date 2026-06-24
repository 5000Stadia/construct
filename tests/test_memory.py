"""Narrative-memory Ledger — forced-depth validation of the layers the short
tests never reach: the rolling verbatim window, the append-only archive, and the
`compact_memory` cohort that fires at the compaction boundary (>RECENT+BATCH turns)
and whose output must actually REACH the narrator's briefing. Plus fail-open.

These drive run_turn past the boundary with a stub, so the `⟦mem⟧` cohort — which
no other test exercises — actually executes.
"""

import json

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.adapter import PorcelainWorldReads
from construct.arc import io as arc_io
from construct.arc.conditions import InFrame, TurnsQuiet
from construct.arc.executor import SESSION, turn_time
from construct.arc.grammar import (
    Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight,
)
from construct.provider import StubProvider, task_of
from construct.turnloop import (
    _MEMORY, _RECENT_TURNS, _COMPACT_BATCH, _TRANSCRIPT, run_turn,
)

PLAYER = "person:hero"
PF = f"knows:{PLAYER}"


def _world(path) -> World:
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    w = World(path, world_id="w:mem", model=StubModel(fallback=fallback),
              stance="fiction", title="Mem World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:hall", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:hall"},
        # A named object in scene → exercises BY-NAME grounding (no raw ids briefed).
        {"entity": "obj:lamp", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:lamp", "attribute": "name", "value": "the brass lamp", "timeless": True},
        {"entity": "obj:lamp", "attribute": "in", "value": "place:hall"},
        {"entity": "fact:rune", "attribute": "kind", "value": "proposition", "timeless": True},
    ])
    # A main arc that never concludes over the test (unreachable win condition;
    # refusal clock parked far out) so we can run many turns freely.
    beat = Beat("beat:learn", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame(PF, "fact:rune", "meaning", "never"))
    refusal = Clock("clock:refusal", TurnsQuiet(999),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape("shape:main", "drive_inverted", (PLAYER, "a", "b"),
                            world_condition=InFrame(PF, "fact:rune", "meaning", "never"),
                            premise=InFrame("canon", PLAYER, "kind", "person"),
                            refusal_variant_id="shape:refused")
    arc = Arc("arc:main", PLAYER, shape, (beat,), (), refusal, 1, ("beat:learn",),
              {Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3, Phase.CLIMAX: 2,
               Phase.FALLING: 2})
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc)
                                  + arc_io.portfolio_items(["arc:main"]))
    # Seed the player's knowledge frame so the scene has content to brief (the
    # narrator reads knows:<protagonist>); include the named lamp for by-name test.
    w.porcelain.ingest_structured([
        {"entity": PLAYER, "attribute": "in", "value": "place:hall"},
        {"entity": "obj:lamp", "attribute": "in", "value": "place:hall"},
        {"entity": "obj:lamp", "attribute": "name", "value": "the brass lamp"},
    ], frame=PF)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame=SESSION)
    return w, arc


class _MemStub(StubProvider):
    """Routes every turn cohort by task tag; the `mem` cohort returns a numbered
    compacted memory so we can see exactly when/whether it fired."""

    def __init__(self, mem_raises=False):
        super().__init__([])
        self.mem_calls = 0
        self.mem_raises = mem_raises

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        t = task_of(prompt)
        if t == "mem":
            if self.mem_raises:
                raise RuntimeError("boom")
            self.mem_calls += 1
            return {"memory": f"COMPACTED-MEMORY-{self.mem_calls}"}
        if t == "cls":
            return {"kind": "action", "moves_to": "", "requires": []}
        if t == "ndg":
            return {"thread": "", "directive": ""}
        if t == "nar":
            return {"prose": f"A beat unfolds in the hall."}
        if t == "npt":  # TURN-LATENCY Lever 4: folded per-NPC call
            return {"acts": False, "action": "", "speaks": False,
                    "intent": "", "line_hint": ""}
        if t == "npa":
            return {"acts": False, "action": ""}
        if t == "npi":
            return {"speaks": False, "intent": "", "line_hint": ""}
        if prompt.startswith("Classify the lifetime"):
            return {"durability": "STATE", "confidence": 0.9}
        return {"items": []}


def _play(w, arc, provider, n_turns):
    for n in range(1, n_turns + 1):
        run_turn(w, arc, provider, f"I search the hall, attempt {n}.", turn=n,
                 scenario_mode="endless", generate=False)


def _last_narrate_prompt(provider):
    for prompt, _schema, _tier in reversed(provider.calls):
        if task_of(prompt) == "nar":
            return prompt
    return ""


def test_compaction_fires_trims_and_archives(tmp_path):
    w, arc = _world(tmp_path / "c.world")
    prov = _MemStub()
    # Boundary is RECENT+BATCH (8+4=12); first compaction at turn 13.
    _play(w, arc, prov, _RECENT_TURNS + _COMPACT_BATCH + 1)
    reads = PorcelainWorldReads(w)
    # The mem cohort actually fired (the part no other test reaches).
    assert prov.mem_calls >= 1
    # The compacted memory landed in the host narrative-memory store (never canon).
    mem = reads.state(_MEMORY, "text", frame=SESSION)
    assert mem == "COMPACTED-MEMORY-1"
    assert w.porcelain.state(_MEMORY, "text")["status"] != "known"  # NOT in canon
    # The verbatim window was trimmed (never grows past RECENT+BATCH).
    recent = json.loads(reads.state(_TRANSCRIPT, "recent", frame=SESSION))
    assert len(recent) <= _RECENT_TURNS + _COMPACT_BATCH
    # The append-only ARCHIVE kept the earliest beat, retrievably (recoverability).
    assert w.porcelain.state("arch:turn_1", "prose", frame=SESSION)["status"] == "known"
    w.close()


def test_memory_reaches_the_narrator(tmp_path):
    w, arc = _world(tmp_path / "b.world")
    prov = _MemStub()
    _play(w, arc, prov, _RECENT_TURNS + _COMPACT_BATCH + 2)
    brief = _last_narrate_prompt(prov)
    # After compaction, the narrator's brief carries BOTH the compacted memory and
    # the recent verbatim window — the whole point of the layer.
    assert "NARRATIVE MEMORY" in brief and "COMPACTED-MEMORY-1" in brief
    assert "THE STORY SO FAR" in brief
    # By-name grounding: the lamp appears by its name, never as a raw id.
    assert "the brass lamp" in brief and "obj:lamp" not in brief
    w.close()


def test_compaction_is_fail_open(tmp_path):
    w, arc = _world(tmp_path / "f.world")
    prov = _MemStub(mem_raises=True)
    # Even though the mem cohort raises every time, turns keep completing.
    _play(w, arc, prov, _RECENT_TURNS + _COMPACT_BATCH + 3)
    reads = PorcelainWorldReads(w)
    # No memory was written (compaction never succeeded), but play never broke and
    # the window is capped so it can't grow without bound.
    assert reads.state(_MEMORY, "text", frame=SESSION) is None
    recent = json.loads(reads.state(_TRANSCRIPT, "recent", frame=SESSION))
    assert len(recent) <= _RECENT_TURNS + _COMPACT_BATCH
    w.close()


def test_below_boundary_no_compaction(tmp_path):
    w, arc = _world(tmp_path / "n.world")
    prov = _MemStub()
    _play(w, arc, prov, _RECENT_TURNS)  # below the boundary
    assert prov.mem_calls == 0
    assert PorcelainWorldReads(w).state(_MEMORY, "text", frame=SESSION) is None
    w.close()
