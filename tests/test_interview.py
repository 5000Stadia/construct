"""Interview path (Path B, feature wave): build a world LIVE from a brief
— verified end to end with a routing stub (no live model), through the
SAME finalize tail as ingest (arc + seeding + meta)."""

import json

import pytest

from construct.game import create_scenario_from_interview
from construct.provider import StubProvider, task_of

PROT = "person:mara"
SECRET = "fact:the_betrayal"


class _InterviewStub(StubProvider):
    """Answers every model call the interview path makes: the world
    spine, the engine's per-row classifier, the arc author, and the
    per-character knowledge seeder — routed by prompt shape."""

    def __init__(self):
        super().__init__([])

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if prompt.startswith("Classify the lifetime"):
            return {"durability": "CONSTITUTIVE", "confidence": 0.9}
        if prompt.startswith("Extract world-state"):
            return {"items": []}
        if task_of(prompt) == "itv":
            return {
                "title": "The Drowned Harbor", "description": "A sunken port town.",
                "genre_era": "drowned-world noir",
                "items": [
                    {"entity": "place:harbor", "attribute": "kind", "value": "place"},
                    {"entity": "place:lighthouse", "attribute": "kind", "value": "place"},
                    {"entity": "place:harbor", "attribute": "connects_to", "value": "place:lighthouse"},
                    {"entity": PROT, "attribute": "kind", "value": "person"},
                    {"entity": PROT, "attribute": "role", "value": "harbor master"},
                    {"entity": PROT, "attribute": "drive", "value": "protect the town"},
                    {"entity": PROT, "attribute": "fear", "value": "the water rising"},
                    {"entity": "person:rook", "attribute": "kind", "value": "person"},
                    {"entity": SECRET, "attribute": "kind", "value": "proposition"},
                    {"entity": SECRET, "attribute": "culprit", "value": "person:rook"},
                ],
            }
        if task_of(prompt) == "arc":
            return {
                "protagonist": PROT, "theme": "the cost of holding back the sea",
                "delta_type": "drive_inverted",
                "tension": [PROT, "drive:protect", "drive:truth"],
                "beats": [
                    {"id": "learn", "phase": "climax", "weight": "required",
                     "kind": "player_learns", "entity": SECRET,
                     "attribute": "culprit", "value": "person:rook"},
                    {"id": "confront", "phase": "crisis", "weight": "optional",
                     "kind": "event_occurs", "entity": "confrontation",
                     "attribute": "-", "value": "-"},
                ],
            }
        if task_of(prompt) == "skn":
            return {"facts": [{"entity": PROT, "attribute": "role", "value": "harbor master"}]}
        raise AssertionError(f"unrouted: {prompt[:60]!r}")


@pytest.fixture
def chdir_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_interview_builds_playable_scenario(chdir_tmp):
    stages: list[str] = []
    meta = create_scenario_from_interview(
        "harbor", "a drowned harbor town where the harbor master hides a betrayal",
        _InterviewStub(), on_stage=stages.append)
    # Per-stage status fires, naming each PB layer (progress + showcase).
    joined = " | ".join(stages)
    for n in ("Stage 1", "Stage 2", "Stage 3", "Stage 4", "Stage 5", "Stage 6"):
        assert n in joined, f"missing {n} in {joined}"
    assert "Reconciling identity" in joined and "passability" in joined
    assert meta["protagonist"] == PROT
    assert meta["title"] == "The Drowned Harbor"
    assert meta["theme"]
    # The world is real: charter + spine in canon, arc in plot:, frames seeded.
    from patternbuffer import World
    w = World("worlds/harbor.world", world_id="w:harbor")
    try:
        assert w.porcelain.state("place:harbor", "kind")["status"] == "known"
        assert w.porcelain.state(SECRET, "culprit")["status"] == "known"   # canon
        assert w.porcelain.state("arc:main", "protagonist", frame="plot:main")["status"] == "known"
        assert PROT in meta["seeded_frames"]
    finally:
        w.close()


def test_interview_is_playable_through_session(chdir_tmp):
    create_scenario_from_interview("harbor", "a drowned harbor town", _InterviewStub())
    # The built scenario plays through the same Session as an ingested one.
    from construct import Session

    class _PlayStub(_InterviewStub):
        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            if task_of(prompt) == "cls":
                self.calls.append(("classify", tier))
                return {"kind": "action", "moves_to": "", "requires": []}
            if task_of(prompt) == "ndg":
                return {"thread": "", "directive": ""}
            if task_of(prompt) == "nar":
                return {"prose": "The harbor breathes around you, grey and patient."}
            if prompt.startswith("Resolve an unestablished aspect"):
                return {"items": [{"value": "Grey water, salt-rotted pilings."}]}
            return await super().complete(prompt, schema, tier=tier, deliberate=deliberate)

    s = Session.open("harbor", player_id="p", provider=_PlayStub())
    r = s.turn("I look out over the harbor.")
    assert r.ok and "harbor" in r.prose.lower()
    s.close()
