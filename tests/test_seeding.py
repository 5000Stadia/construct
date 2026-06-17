"""NPC-knows seeding (feature wave, letter 041): per-character knows:<id>
frames, frame-scoped secrecy (P4), and the criterion-(g) divergence —
all verified against a real engine World with a stubbed knowledge author
(no live model)."""

import json

import pytest

from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct.game import knows_inspect, reseed_character_frames, seed_character_frames
from construct.provider import StubProvider

DETECTIVE = "person:vance"
CLERK = "person:ilsa"
SECRET = ("fact:core_theft", "culprit", "person:ilsa")


class _KnowsStub(StubProvider):
    """Authors each character's frame: the clerk holds the secret (she
    did it); the detective does not (he hasn't solved it). Routes on the
    CHARACTER line of the seed_knows prompt."""

    def __init__(self):
        super().__init__([])

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        common = [{"entity": "place:office", "attribute": "kind", "value": "room"}]
        if f"CHARACTER: {CLERK}" in prompt:
            return {"facts": common + [
                {"entity": SECRET[0], "attribute": SECRET[1], "value": SECRET[2]},
                {"entity": "obj:memory_core", "attribute": "in", "value": "obj:false_drawer"},
            ]}
        if f"CHARACTER: {DETECTIVE}" in prompt:
            return {"facts": common + [
                {"entity": DETECTIVE, "attribute": "role", "value": "investigator"},
            ]}
        return {"facts": common}


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    rule = rule_classifier_fallback()
    w = World(tmp_path / "worlds" / "mystery.world", world_id="w:mystery",
              model=StubModel(fallback=lambda p, s: rule(p, s)),
              stance="fiction", title="Mystery")
    w.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": DETECTIVE, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": CLERK, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:memory_core", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:false_drawer", "attribute": "kind", "value": "drawer", "timeless": True},
        {"entity": SECRET[0], "attribute": "kind", "value": "proposition", "timeless": True},
        {"entity": SECRET[0], "attribute": SECRET[1], "value": SECRET[2]},
    ])
    w.close()
    (tmp_path / "worlds" / "mystery.meta.json").write_text(json.dumps({
        "title": "Mystery", "protagonist": DETECTIVE,
        "arc_scope": [SECRET[0], "obj:memory_core", DETECTIVE, CLERK],
    }))
    return "mystery"


def _open(name):
    return World(f"worlds/{name}.world", world_id=f"w:{name}",
                 model=StubModel(fallback=rule_classifier_fallback()))


def test_seeding_writes_frames_with_structural_secrecy(scenario):
    w = _open(scenario)
    try:
        seeded = seed_character_frames(w, _KnowsStub(), [DETECTIVE, CLERK], digest="{}")
        assert set(seeded) == {DETECTIVE, CLERK}
        # The clerk's frame holds the secret; the detective's does NOT —
        # non-leak by structural absence (P4), not by instruction.
        clerk_secret = w.porcelain.state(SECRET[0], SECRET[1], frame=f"knows:{CLERK}")
        det_secret = w.porcelain.state(SECRET[0], SECRET[1], frame=f"knows:{DETECTIVE}")
        assert clerk_secret["status"] == "known" and clerk_secret["fact"]["value"] == SECRET[2]
        assert det_secret["status"] == "unknown"
        # canon itself is untouched-by-frames: the secret is in canon too
        assert w.porcelain.state(SECRET[0], SECRET[1])["status"] == "known"
    finally:
        w.close()


def test_criterion_g_contrast(scenario):
    w = _open(scenario)
    try:
        seed_character_frames(w, _KnowsStub(), [DETECTIVE, CLERK], digest="{}")
    finally:
        w.close()
    # The headline: the same world, two provably-different knowledge states.
    r = knows_inspect(scenario, DETECTIVE, contrast=CLERK)
    assert (SECRET[0], SECRET[1]) in r["only_contrast"]          # only the clerk knows whodunit
    assert (SECRET[0], SECRET[1]) not in r["only_character"]
    assert ("obj:memory_core", "in") in r["only_contrast"]       # and where the core is hidden
    # single-character inspection works too
    solo = knows_inspect(scenario, CLERK)
    assert (SECRET[0], SECRET[1]) in solo["knows"]


def test_concurrent_seeding_matches_sequential(scenario, monkeypatch):
    # CONSTRUCT_SEED_CONCURRENCY > 1 fans the independent seed calls over a
    # thread pool (Kernos 044); the projected frames must be identical to the
    # sequential path — disjoint knows:<id> frames, appends still serialized.
    import construct.game as game
    monkeypatch.setattr(game, "SEED_CONCURRENCY", 3)
    w = _open(scenario)
    try:
        seeded = seed_character_frames(w, _KnowsStub(), [DETECTIVE, CLERK], digest="{}")
        assert set(seeded) == {DETECTIVE, CLERK}
        clerk_secret = w.porcelain.state(SECRET[0], SECRET[1], frame=f"knows:{CLERK}")
        det_secret = w.porcelain.state(SECRET[0], SECRET[1], frame=f"knows:{DETECTIVE}")
        assert clerk_secret["status"] == "known" and clerk_secret["fact"]["value"] == SECRET[2]
        assert det_secret["status"] == "unknown"
    finally:
        w.close()


def test_concurrent_seeding_is_fail_open_per_frame(scenario, monkeypatch):
    # One character's provider blip skips that frame, never the batch — the
    # fail-open contract must survive the concurrent path.
    from construct.provider import ProviderError
    import construct.game as game
    monkeypatch.setattr(game, "SEED_CONCURRENCY", 3)

    class _OneFails(_KnowsStub):
        async def complete(self, prompt, schema, *, tier="main", deliberate=False):
            if f"CHARACTER: {DETECTIVE}" in prompt:
                raise ProviderError("simulated blip")
            return await super().complete(prompt, schema, tier=tier, deliberate=deliberate)

    w = _open(scenario)
    try:
        seeded = seed_character_frames(w, _OneFails(), [DETECTIVE, CLERK], digest="{}")
        assert seeded == [CLERK]                                  # detective skipped, clerk kept
        assert w.porcelain.state(SECRET[0], SECRET[1], frame=f"knows:{CLERK}")["status"] == "known"
    finally:
        w.close()


def test_seeding_is_reversible(scenario):
    # Reseeding clears and re-authors knows: frames without touching canon
    # or plot: (founder reversibility condition).
    w = _open(scenario)
    try:
        seed_character_frames(w, _KnowsStub(), [CLERK], digest="{}")
    finally:
        w.close()
    reseeded = reseed_character_frames(scenario, _KnowsStub(), [CLERK])
    assert reseeded == [CLERK]
    # canon secret still present and unchanged after a reseed
    w = _open(scenario)
    try:
        assert w.porcelain.state(SECRET[0], SECRET[1])["status"] == "known"
        assert w.porcelain.state(SECRET[0], SECRET[1], frame=f"knows:{CLERK}")["status"] == "known"
    finally:
        w.close()
