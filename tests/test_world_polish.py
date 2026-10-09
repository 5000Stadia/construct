"""World/scenario/session-layer polish (audit B2-B8): scenario listing, the build-path
entry-epoch scope, arc-build retry guards, and `continue_episode` atomicity + per-chapter
identity + settled-history hygiene."""

import json
import shutil

import pytest
from patternbuffer import World
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct import game
from construct.adapter import PorcelainWorldReads
from construct.arc import executor
from construct.arc import io as arc_io
from construct.arc.executor import SESSION, TURN_EPOCH
from construct.provider import StubProvider, task_of
from construct.semantics import attribute_default

PLAYER = "person:player"


def _fallback(prompt, schema, _rule=rule_classifier_fallback()):
    return _rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}


# ---------------------------------------------------------------------------- B4

def test_list_scenarios_hides_episode_checkpoints(tmp_path, monkeypatch):
    """B4: `<name>.<pid>.ep.checkpoint.world` is a per-player rollback file, not a scenario
    (it used to be listed like one, reaching the CLI/Discord pickers)."""
    monkeypatch.setattr(game, "WORLDS_DIR", tmp_path)
    for fname in ("demo.world", "demo.play.world", "demo.u1.play.world",
                  "demo.ep.checkpoint.world", "demo.u1.ep.checkpoint.world"):
        (tmp_path / fname).write_bytes(b"")
    assert [s["name"] for s in game.list_scenarios()] == ["demo"]


# ------------------------------------------------------------------- B6 + B8 (build)

_GOOD_ARC = {
    "protagonist": "person:a", "delta_type": "drive_inverted",
    "tension": ["person:a", "drive:doubt", "drive:proof"],
    "goal_statement": "find the truth", "theme": "the truth beneath the office",
    "beats": [{"id": "beat:learn", "phase": "climax", "weight": "required",
               "kind": "player_learns", "entity": "fact:secret",
               "attribute": "culprit", "value": "person:b"}],
}


def _bare_world(tmp_path, *, preplay_vf=None):
    w = World(tmp_path / "bw.world", world_id="w:bw", model=StubModel(fallback=_fallback),
              stance="fiction", title="Bare World")
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": "person:a", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:b", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "fact:secret", "attribute": "kind", "value": "proposition",
         "timeless": True},
    ])
    if preplay_vf is not None:       # a pre-play row ABOVE TURN_EPOCH -> the entry epoch is raised
        w.porcelain.ingest_structured([
            {"entity": "person:a", "attribute": "mood", "value": "wary",
             "valid_from": preplay_vf}])
    return w


class _ArcProvider(StubProvider):
    def __init__(self, proposals):
        super().__init__([])
        self._proposals = list(proposals)
        self.arc_calls = 0

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        if prompt.startswith("Classify the lifetime"):
            return {"durability": "STATE", "confidence": 0.9}
        if task_of(prompt) == "arc":
            i = min(self.arc_calls, len(self._proposals) - 1)
            self.arc_calls += 1
            return json.loads(json.dumps(self._proposals[i]))
        return {"items": []}


def test_finalize_restores_entry_epoch_contextvar(tmp_path):
    """B6: `_finalize_scenario` raised the entry-epoch contextvar for its own staging and
    never put it back — the same leak Cx 383 fixed in continue_episode."""
    w = _bare_world(tmp_path, preplay_vf=5000.0)
    before = executor.current_epoch()
    meta = game._finalize_scenario(w, "bw", "Bare World", _ArcProvider([_GOOD_ARC]),
                                   tmp_path / "bw_scenario.world", endless=False,
                                   play_as="person a")
    try:
        assert meta["entry_epoch"] > TURN_EPOCH          # it WAS raised during the build...
        assert executor.current_epoch() == before        # ...and never leaks out of it
    finally:
        w.close()


@pytest.mark.parametrize("bad", [
    {**_GOOD_ARC, "beats": []},                                        # IndexError (beats[-1])
    {**_GOOD_ARC, "beats": [{**_GOOD_ARC["beats"][0], "phase": "nonsense"}]},   # ValueError
], ids=["empty-beats", "off-enum-phase"])
def test_finalize_retries_an_unbuildable_arc_proposal(tmp_path, bad):
    """B8: a proposal `_build_arc` cannot build is a failed ATTEMPT in the arc retry loop
    (as in author_replan), not an abort of the whole build."""
    w = _bare_world(tmp_path)
    prov = _ArcProvider([bad, _GOOD_ARC])
    spath = tmp_path / "bw_scenario.world"
    game._finalize_scenario(w, "bw", "Bare World", prov, spath, endless=False,
                            play_as="person a")
    try:
        assert prov.arc_calls == 2
        assert spath.with_suffix(".meta.json").exists()                # published
    finally:
        w.close()


def test_finalize_unbuildable_every_attempt_fails_cleanly(tmp_path):
    w = _bare_world(tmp_path)
    prov = _ArcProvider([{**_GOOD_ARC, "beats": []}])
    with pytest.raises(RuntimeError, match="arc failed"):
        game._finalize_scenario(w, "bw", "Bare World", prov, tmp_path / "x.world",
                                endless=False, play_as="person a")
    assert prov.arc_calls == 3
    w.close()


# ------------------------------------------------------------------ continue_episode

_PROPOSAL = {
    "protagonist": PLAYER, "delta_type": "desire_at_cost",
    "tension": [PLAYER, "drive:duty", "drive:fear"],
    "beats": [{"id": "beat:next", "phase": "climax", "weight": "required",
               "kind": "event_occurs", "entity": "confrontation",
               "attribute": "", "value": ""}],
    "hook": "A stranger waits on the stair.", "title": "The Weight of Brass",
}


class _ContProvider(StubProvider):
    """gen -> the queued proposals (last repeats); dpol -> a fixed policy; pth -> one thread."""

    def __init__(self, proposals, *, policy="mortal", fail_gen=False):
        super().__init__([])
        self._proposals = list(proposals)
        self._policy = policy
        self._fail_gen = fail_gen
        self.gen_calls = 0

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        if prompt.startswith("Classify the lifetime"):
            return _fallback(prompt, schema)
        t = task_of(prompt)
        if t == "gen":
            if self._fail_gen:
                raise RuntimeError("provider down")
            i = min(self.gen_calls, len(self._proposals) - 1)
            self.gen_calls += 1
            return json.loads(json.dumps(self._proposals[i]))
        if "Decide the DEATH POLICY" in prompt:   # task tag `dpol` is 4 letters: task_of()==""
            return {"policy": self._policy, "reason": "test"}
        if t == "pth":
            return {"threads": [{"thread": "promised Ada to clear her brother's name",
                                 "status": "open"}]}
        return {"items": []}


def _make_slot(tmp_path, monkeypatch, name="cc"):
    """A played slot whose main arc was built by the REAL `_build_arc` (so it carries the
    placeholder premise), with a narrative ledger so the personal-threads call runs."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    spath = tmp_path / "worlds" / f"{name}.world"
    w = World(spath, world_id=f"w:{name}", stance="fiction", attribute_default=attribute_default,
              model=StubModel(fallback=_fallback))
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:office", "attribute": "kind", "value": "room", "timeless": True},
        {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": PLAYER, "attribute": "in", "value": "place:office"},
    ])
    arc = game._build_arc({**_PROPOSAL, "title": "First"}, arc_id="arc:main")
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    w.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "kind", "value": "turn", "valid_from": 1000.0},
        {"entity": "session:narrative_memory", "attribute": "text",
         "value": "You promised Ada you would clear her brother's name.",
         "value_type": "literal", "valid_from": 1000.0},
    ], frame=SESSION)
    w.close()
    spath.with_suffix(".meta.json").write_text(json.dumps(
        {"title": "First", "protagonist": PLAYER, "arc_scope": [PLAYER], "mode": "pure",
         "scenario_mode": "win_loss", "genre": "cozy", "death_policy": "shielded"}))
    shutil.copyfile(spath, game.slot_path(name, "u1"))
    return name


def _open_slot(name):
    return World(game.slot_path(name, "u1"), world_id=f"w:{name}", stance="fiction",
                 model=StubModel(fallback=_fallback))


def _spy_close(monkeypatch):
    """Record every World.close() on worlds game._world opens."""
    closed: list[bool] = []
    real = game._world

    def spy(*a, **kw):
        w = real(*a, **kw)
        orig = w.close

        def _close():
            closed.append(True)
            orig()
        w.close = _close
        return w
    monkeypatch.setattr(game, "_world", spy)
    return closed


def test_continue_failure_leaves_slot_untouched_and_closes_world(tmp_path, monkeypatch):
    """B5: nothing is written before the last fallible call — a failed continuation leaves
    no settled:episode_N / personal_threads rows (a retry used to append duplicates) — and
    the world is closed and the epoch restored on the failure path too."""
    name = _make_slot(tmp_path, monkeypatch)
    closed = _spy_close(monkeypatch)
    before = executor.current_epoch()
    with pytest.raises(RuntimeError, match="provider down"):
        game.continue_episode(name, _ContProvider([_PROPOSAL], fail_gen=True),
                              player_id="u1")
    assert closed, "the slot world must be closed on the failure path"
    assert executor.current_epoch() == before
    w = _open_slot(name)
    try:
        rows = [(str(r.entity), str(r.attribute)) for r in w.buffer.visible(frame=SESSION)]
        assert not any(e.startswith("settled:episode_") for e, _a in rows)
        assert ("session:personal_threads", "record") not in rows
        assert not any(e.startswith("event:episode_start_") for e, _a in rows)
    finally:
        w.close()


def test_continue_unbuildable_proposal_retries_then_succeeds(tmp_path, monkeypatch):
    """B8: an unbuildable continuation proposal (no beats) is a failed attempt; the next
    attempt's good proposal installs."""
    name = _make_slot(tmp_path, monkeypatch)
    prov = _ContProvider([{**_PROPOSAL, "beats": []}, _PROPOSAL])
    meta = game.continue_episode(name, prov, player_id="u1")
    assert prov.gen_calls == 2
    assert meta["main_arc"].startswith("arc:ep_")
    # the retry prompt told the author what went wrong
    gens = [p for (p, _s, _t) in prov.calls if task_of(p) == "gen"]
    assert "COULD NOT BE BUILT" in gens[1] and "COULD NOT BE BUILT" not in gens[0]


def test_continue_unbuildable_every_attempt_writes_nothing(tmp_path, monkeypatch):
    name = _make_slot(tmp_path, monkeypatch)
    closed = _spy_close(monkeypatch)
    prov = _ContProvider([{**_PROPOSAL, "beats": []}])
    with pytest.raises(RuntimeError, match="could not be built"):
        game.continue_episode(name, prov, player_id="u1")
    assert prov.gen_calls == 3 and closed
    w = _open_slot(name)
    try:
        assert not any(str(r.entity).startswith("settled:episode_")
                       for r in w.buffer.visible(frame=SESSION))
    finally:
        w.close()


def test_continue_settled_history_excludes_placeholder_premise(tmp_path, monkeypatch):
    """B3: `_build_arc`'s placeholder premise StateIs(protagonist, kind, person) is not an
    answered question — the protagonist must never be recorded as closed history, nor
    named to the next chapter's author as one."""
    name = _make_slot(tmp_path, monkeypatch)
    prov = _ContProvider([_PROPOSAL])
    game.continue_episode(name, prov, player_id="u1")
    w = _open_slot(name)
    try:
        rec = next(json.loads(str(r.value)) for r in w.buffer.visible(frame=SESSION)
                   if str(r.entity).startswith("settled:episode_")
                   and str(r.attribute) == "record")
        assert not any(PLAYER in line for line in rec["settled"])
    finally:
        w.close()
    gen = next(p for (p, _s, _t) in prov.calls if task_of(p) == "gen")
    assert f"{PLAYER} · kind" not in gen


def test_continue_persists_chapter_title_and_death_policy_per_slot(tmp_path, monkeypatch):
    """B2: the new chapter's title and death policy are computed by continue_episode but the
    caller drops the returned meta and the Session reloads the SHARED scenario meta (chapter
    one's). They are persisted in the slot's session frame and the Session prefers them."""
    from construct import Session
    name = _make_slot(tmp_path, monkeypatch)
    meta = game.continue_episode(name, _ContProvider([_PROPOSAL], policy="mortal"),
                                 player_id="u1")
    assert meta["title"] == "The Weight of Brass" and meta["death_policy"] == "mortal"
    # the shared scenario meta is untouched (a /restart to chapter one must still see it)
    shared = json.loads((tmp_path / "worlds" / f"{name}.meta.json").read_text())
    assert shared["title"] == "First" and shared["death_policy"] == "shielded"
    s = Session.open(name, player_id="u1", provider=StubProvider([]))
    try:
        assert s.title == "The Weight of Brass"
        assert s._meta["death_policy"] == "mortal"
    finally:
        s.close()


def test_second_continuation_supersedes_chapter_identity(tmp_path, monkeypatch):
    """The per-slot chapter rows are latest-wins across consecutive continuations."""
    from construct import Session
    name = _make_slot(tmp_path, monkeypatch)
    game.continue_episode(name, _ContProvider([_PROPOSAL], policy="mortal"), player_id="u1")
    w = _open_slot(name)                       # chapter two is PLAYED: turns advance the clock
    w.porcelain.ingest_structured([
        {"entity": "event:turn_7", "attribute": "kind", "value": "turn",
         "valid_from": 1007.0}], frame=SESSION)
    w.close()
    game.continue_episode(name, _ContProvider([{**_PROPOSAL, "title": "A Third Ledger"}],
                                              policy="premise"), player_id="u1")
    s = Session.open(name, player_id="u1", provider=StubProvider([]))
    try:
        assert s.title == "A Third Ledger"
        assert s._meta["death_policy"] == "premise"
    finally:
        s.close()


def test_continue_releases_world_and_epoch_on_success(tmp_path, monkeypatch):
    name = _make_slot(tmp_path, monkeypatch)
    closed = _spy_close(monkeypatch)
    before = executor.current_epoch()
    game.continue_episode(name, _ContProvider([_PROPOSAL]), player_id="u1")
    assert closed and executor.current_epoch() == before


def test_three_continuations_chapter_rows_read_the_latest_chapter(tmp_path, monkeypatch):
    """AUDIT-2026-10: continue_episode wrote session:episode.entry_epoch / .arc_scope and
    session:scope.independent_extra WITHOUT a valid_from, so every continuation stamped them at
    0.0 and they TIED (conflicted); after a third chapter the engine served chapter two's values.
    Each must be stamped on the chapter's own turn axis, as chapter_title already is."""
    from construct.adapter import PorcelainWorldReads
    from construct.scenario_meta import PlaythroughState
    name = _make_slot(tmp_path, monkeypatch)
    metas = []
    for i, entity in enumerate(("place:office", "place:annex", "place:cellar")):
        w = _open_slot(name)               # the chapter is PLAYED before it is concluded:
        w.porcelain.ingest_structured([    # turns advance the clock, new places become known
            {"entity": entity, "attribute": "kind", "value": "room", "timeless": True},
            {"entity": f"event:turn_{7 + i * 10}", "attribute": "kind", "value": "turn",
             "valid_from": 1007.0 + i * 10}], frame=SESSION)
        w.close()
        prop = {**_PROPOSAL, "title": f"Ledger {i}",
                "beats": [{**_PROPOSAL["beats"][0], "entity": entity}]}
        metas.append(game.continue_episode(name, _ContProvider([prop]), player_id="u1"))
    assert len({m["entry_epoch"] for m in metas}) == 3
    w = _open_slot(name)
    try:
        reads = PorcelainWorldReads(w)
        for entity, attribute in (("session:episode", "entry_epoch"),
                                  ("session:episode", "arc_scope"),
                                  ("session:scope", "independent_extra")):
            st = w.porcelain.state(entity, attribute, frame=SESSION)
            assert st["status"] == "known", (entity, attribute, st["status"])
        assert float(reads.state("session:episode", "entry_epoch", frame=SESSION)) \
            == metas[2]["entry_epoch"]
        assert json.loads(reads.state("session:episode", "arc_scope", frame=SESSION)) == [PLAYER]
        assert PlaythroughState.from_world({}, w).entry_epoch == metas[2]["entry_epoch"]
    finally:
        w.close()


def test_ingest_stops_with_the_real_cause_when_every_chunk_fails(tmp_path, monkeypatch):
    """Every chunk failing (e.g. a model the account refuses) used to be skipped chunk by chunk
    and surface later as a misleading 'bare world' arc failure. It now stops at once, naming it."""
    import pytest
    from patternbuffer import porcelain as pb_porcelain
    from construct import game
    from construct.provider import ProviderTransportError, StubProvider

    monkeypatch.setattr(game, "WORLDS_DIR", tmp_path)
    monkeypatch.setattr(game, "scenario_path", lambda name: tmp_path / f"{name}.world")

    def refuse(self, *a, **k):
        raise ProviderTransportError("Codex API error (400): model not supported")
    for cls in vars(pb_porcelain).values():
        if isinstance(cls, type) and hasattr(cls, "extract"):
            monkeypatch.setattr(cls, "extract", refuse)
    prose = tmp_path / "book.md"
    prose.write_text("# A Book\n\n## One\n\nThe first chapter.\n\n## Two\n\nThe second chapter.\n")
    with pytest.raises(RuntimeError, match="every one of .* chunk.*model not supported"):
        game.create_scenario_from_ingest("failfast", prose, StubProvider([]))
