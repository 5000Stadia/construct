"""READS AT THE PLAY HORIZON (docs/design/READS-AT-PLAY-HORIZON.md r7).

A generated world's canon holds the whole hidden source story; play happens in a band just
after its first chunk. Play code reads through a `HorizonView`, so no read — however deep in
a helper — sees the source story's future, and id-collision checks alone read the head."""
import inspect
import json
import shutil

import pytest
from patternbuffer import World
from patternbuffer.porcelain import Porcelain
from patternbuffer.testing import StubModel, rule_classifier_fallback

from construct import adapter, game
from construct.adapter import (
    PORCELAIN_EVENT_READS, PORCELAIN_PASSTHROUGH, PORCELAIN_VALID_TIME_READS, WORLD_EXPOSED,
    HorizonView, PorcelainWorldReads, _HorizonPorcelain, is_future_only, play_horizon,
    raw_world,
)
from construct.clock import ELAPSED_ATTR, ELAPSED_ENTITY, read_clock
from construct.reshape import ReshapePlan, canonicalize_plan
from construct.semantics import attribute_default
from construct.turnloop import _grant_moved_place, _growth_exists, _mint_held_object

PROT = "person:prot"
STEP = 1_000_000.0
OPENING = STEP + 1000.0          # opening_as_of: just after chunk 1
NEXT_SOURCE = 2 * STEP           # the next source coordinate (the band's ceiling)
FUTURE = 10 * STEP               # the source story's ending


def _fallback(prompt, schema, _rule=rule_classifier_fallback()):
    return _rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}


def _rows():
    """Run 10's shape. The shed and the pass EXIST timelessly (as in run 10's real world);
    only their relationship facts lie in the future. `person:later`, `obj:later_thing` and
    `place:far_hut` are genuinely future-only (kind/name only at FUTURE)."""
    return [
        {"entity": "place:cell", "attribute": "kind", "value": "cell", "timeless": True},
        {"entity": "place:street", "attribute": "kind", "value": "street", "timeless": True},
        {"entity": "place:shed", "attribute": "kind", "value": "shed", "timeless": True},
        {"entity": "place:shed", "attribute": "name", "value": "ice cutter shed",
         "timeless": True},
        {"entity": PROT, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "obj:pass", "attribute": "kind", "value": "pass", "valid_from": 0.0},
        {"entity": PROT, "attribute": "in", "value": "place:cell", "value_type": "entity",
         "valid_from": STEP},
        {"entity": PROT, "attribute": "in", "value": "place:street", "value_type": "entity",
         "valid_from": OPENING + 5},
        # --- the hidden future (the source ending) ---
        {"entity": PROT, "attribute": "in", "value": "place:shed", "value_type": "entity",
         "valid_from": FUTURE},
        {"entity": "obj:pass", "attribute": "in", "value": PROT, "value_type": "entity",
         "valid_from": FUTURE},
        {"entity": "person:later", "attribute": "kind", "value": "person",
         "valid_from": FUTURE},
        {"entity": "person:later", "attribute": "name", "value": "Later Person",
         "valid_from": FUTURE},
        {"entity": "obj:later_thing", "attribute": "kind", "value": "object",
         "valid_from": FUTURE},
        {"entity": "place:far_hut", "attribute": "kind", "value": "hut", "valid_from": FUTURE},
        {"entity": "place:far_hut", "attribute": "name", "value": "far hut",
         "valid_from": FUTURE},
        # the clock: 60 minutes have passed by the horizon; the ending adds 9000 more
        {"entity": ELAPSED_ENTITY, "attribute": "kind", "value": "clock", "timeless": True},
        {"entity": ELAPSED_ENTITY, "attribute": ELAPSED_ATTR, "value": 0,
         "value_type": "literal", "valid_from": STEP},
        {"entity": ELAPSED_ENTITY, "attribute": ELAPSED_ATTR, "value": 60,
         "value_type": "delta", "valid_from": OPENING + 1},
        {"entity": ELAPSED_ENTITY, "attribute": ELAPSED_ATTR, "value": 9100,
         "value_type": "delta", "valid_from": FUTURE},
        # events either side of the horizon
        {"entity": "event:early_bell", "attribute": "kind", "value": "bell",
         "valid_from": OPENING + 2},
        {"entity": "event:late_bell", "attribute": "kind", "value": "bell",
         "valid_from": FUTURE},
    ]


@pytest.fixture
def hworld(tmp_path):
    w = World(tmp_path / "h.world", world_id="w:h", model=StubModel(fallback=_fallback),
              stance="fiction", attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured(_rows())
    yield w
    w.close()


H = OPENING + 10                  # a play horizon ten turns in


# --------------------------------------------------------------- the view itself (8, 13, 14)

def test_legacy_view_is_the_raw_world(hworld):
    assert HorizonView(hworld, None) is hworld
    assert HorizonView(hworld, lambda: None) is hworld
    assert raw_world(hworld) is hworld


def test_valid_time_reads_inject_and_clamp(hworld):
    v = HorizonView(hworld, H)
    assert hworld.porcelain.locate(PROT)[0] == "place:shed"            # the head: the ending
    assert v.porcelain.locate(PROT)[0] == "place:street"               # absent as_of → h
    assert v.porcelain.locate(PROT, as_of=None)[0] == "place:street"   # explicit None → h
    assert v.porcelain.locate(PROT, as_of=FUTURE + 1)[0] == "place:street"   # clamped
    assert v.porcelain.locate(PROT, as_of=STEP + 1)[0] == "place:cell"       # earlier passes
    assert PorcelainWorldReads(v).location_chain(PROT)[0] == "place:street"


def test_events_until_capped(hworld):
    v = HorizonView(hworld, H)
    ids = {e["id"] for e in v.porcelain.events(kind="bell")}
    assert ids == {"event:early_bell"}
    assert {e["id"] for e in hworld.porcelain.events(kind="bell")} == {
        "event:early_bell", "event:late_bell"}


def test_refer_gets_the_horizon(hworld, monkeypatch):
    seen = {}

    def spy(description, scope=None, frame="canon", constraints=None, as_of=None, **kw):
        seen["as_of"] = as_of
        return None
    monkeypatch.setattr(hworld, "refer", spy)
    HorizonView(hworld, H).refer("the street", frame="canon")
    assert seen["as_of"] == H
    HorizonView(hworld, H).refer("the street", as_of=FUTURE)
    assert seen["as_of"] == H                                        # clamped


def test_world_surface_is_deny_by_default(hworld):
    v = HorizonView(hworld, H)
    for name in ("buffer", "state", "locate", "snapshot", "materialize", "resolve",
                 "charter", "semantics", "ingestor", "world_id"):
        with pytest.raises(AttributeError, match="horizon view"):
            getattr(v, name)
    assert v.head is hworld


def test_porcelain_proxy_is_deny_by_default():
    class _Stub:
        def brand_new_read(self, as_of=None):
            return as_of
    with pytest.raises(AttributeError, match="horizon view"):
        _HorizonPorcelain(_Stub(), lambda: 1.0).brand_new_read


#: The pinned engine's public World members (instance attributes included). An engine bump
#: that adds one fails here, so it gets classified (it is denied at runtime meanwhile).
PINNED_WORLD_PUBLIC = frozenset({
    "aggregate", "buffer", "canonical_attribute", "charter", "classifier", "close",
    "commit_set", "composition", "confidence", "contents", "correlate",
    "correlation_conflicts", "correlations", "extract", "features", "fidelity_audit",
    "identity_conflicts", "in_transit", "indexes", "ingest", "ingest_structured", "ingestor",
    "locate", "materialize", "neighborhood", "path", "policy", "porcelain", "projector",
    "refer", "registry", "resolve", "resolver", "route", "salience", "salience_index",
    "semantics", "snapshot", "state", "state_union", "truth", "who_knows", "world_id",
})


def test_classification_pins_the_engine_surfaces(hworld):
    public = {n for n, m in inspect.getmembers(Porcelain, inspect.isfunction)
              if not n.startswith("_")}
    classes = (PORCELAIN_VALID_TIME_READS, PORCELAIN_EVENT_READS, PORCELAIN_PASSTHROUGH)
    for n in public:                                      # exactly one class each
        assert sum(n in c for c in classes) == 1, n
    assert public == set().union(*classes)
    for n in public:                                      # the valid-time class = has as_of
        has = "as_of" in inspect.signature(getattr(Porcelain, n)).parameters
        assert has == (n in PORCELAIN_VALID_TIME_READS), n
    assert {n for n in dir(hworld) if not n.startswith("_")} == PINNED_WORLD_PUBLIC
    assert "as_of" in inspect.signature(hworld.refer.__call__).parameters   # dynamic Refer
    assert WORLD_EXPOSED == {"porcelain", "refer", "close", "head"}


def test_play_horizon_rule():
    assert play_horizon(None, None, 5) is None
    assert play_horizon(OPENING, NEXT_SOURCE, 3) == OPENING + 3
    assert play_horizon(OPENING, NEXT_SOURCE, 10**9) == NEXT_SOURCE - 1.0


# ------------------------------------------------------ the identity rule (1, 2, 3, 11, 12)

def test_grant_takes_at_the_horizon(hworld):
    """T1: run 10 — every improv mint reported grant_failed because the verify read the
    head (the source ending)."""
    at = OPENING + 6
    got, seg = _grant_moved_place(hworld, PROT, "the lamplit square", at=at, as_of=at)
    assert got == "place:lamplit_square"
    assert PorcelainWorldReads(hworld, horizon=at).location_chain(PROT)[0] == got
    # negative control: the head read (the old verify) reports the mint as not taken
    got2, seg2 = _grant_moved_place(hworld, PROT, "the quiet yard", at=at + 1, as_of=None)
    assert got2 is None and seg2["status"] == "grant_failed"


def test_grant_never_writes_onto_a_future_only_place(hworld):
    """T2: 'the far hut' exists only in the hidden future — the move mints a fresh suffix."""
    at = OPENING + 6
    before = len(hworld.porcelain.facts("canon", entity="place:far_hut"))
    got, _ = _grant_moved_place(HorizonView(hworld, at), PROT, "the far hut", at=at, as_of=at)
    assert got == "place:far_hut_1"
    assert len(hworld.porcelain.facts("canon", entity="place:far_hut")) == before


def test_mint_collides_at_head_and_verifies_at_horizon(hworld):
    """T3/H1: a take of 'later thing' must not take the future-only obj:later_thing."""
    at = OPENING + 7
    got = _mint_held_object(HorizonView(hworld, at), PROT, "later thing", at=at)
    assert got == "obj:later_thing_1"


def test_growth_allocation_reads_the_head(hworld):
    """T5: growth's id allocation is collision avoidance — a future-only id counts as taken."""
    v = HorizonView(hworld, H)
    assert not PorcelainWorldReads(v).has_entity("place:far_hut")
    assert _growth_exists(v)("place:far_hut") is True
    assert is_future_only(v, "place:far_hut") and not is_future_only(hworld, "place:far_hut")


def test_reshape_never_lands_on_a_future_only_entity(hworld):
    """T6 (cr r3): a reshape plan naming a future-only id maps it to one fresh suffix across
    its rows and frames; a loose name that refer's tier-1 lookup binds to the future entity
    is refused by the presence guard."""
    def plan():
        return ReshapePlan(
            slug="x",
            state_rows=[{"entity": "person:later", "attribute": "mood", "value": "calm"},
                        {"entity": "obj:note", "attribute": "about", "value": "Later Person"}],
            frame_rows=[{"frame": "knows:person:later", "entity": PROT,
                         "attribute": "seen", "value": "yes"}])
    p = canonicalize_plan(HorizonView(hworld, H), plan())
    assert p.state_rows[0]["entity"] == "person:later_1"
    assert p.frame_rows[0]["frame"] == "knows:person:later_1"
    assert p.state_rows[1]["value"] != "person:later"
    raw = canonicalize_plan(hworld, plan())                      # negative control
    assert raw.state_rows[0]["entity"] == "person:later"


# ------------------------------------------------------------- the clock (10, C1-C5)

def test_clock_reads_the_horizon(hworld):
    v = HorizonView(hworld, H)
    assert read_clock(v).minutes == 60
    assert read_clock(hworld).minutes == 9160                  # negative control: the future


def test_doorway_time_jump_derives_from_the_horizon(hworld):
    v_rows = game._plan_episode_doorway(HorizonView(hworld, H), PROT).time_rows
    raw_rows = game._plan_episode_doorway(hworld, PROT).time_rows

    def jump(rows):
        return [r["value"] for r in rows if r.get("value_type") == "delta"]
    assert jump(v_rows) != jump(raw_rows)


# --------------------------------------------------------- the chapter-2 build (4, 5, 6, 7)

def test_doorway_fallback_opens_where_the_player_is(hworld):
    """G5: with no terminal-location receipt the doorway falls back to a live locate."""
    assert game._plan_episode_doorway(HorizonView(hworld, H), PROT).place == "place:street"
    assert game._plan_episode_doorway(hworld, PROT).place == "place:shed"   # the leak


def test_hook_cast_stages_at_the_horizon_and_skips_future_ids(hworld):
    """G6-G8."""
    v = HorizonView(hworld, H)
    proposal = {"hook_cast": [{"id": "person:newcomer", "name": "Newcomer"},
                              {"id": "person:later", "name": "Later Person"}]}
    rows, ids = game._plan_hook_cast(v, PorcelainWorldReads(v), proposal, None, PROT,
                                     at=H)
    ins = [r for r in rows if r["attribute"] == "in"]
    assert ins and all(r["value"] == "place:street" for r in ins)
    assert not any(r["entity"] == "person:later" for r in rows)
    raw_rows, _ = game._plan_hook_cast(hworld, PorcelainWorldReads(hworld), proposal, None,
                                       PROT, at=H)
    assert any(r["value"] == "place:shed" for r in raw_rows if r["attribute"] == "in")


def test_author_inputs_come_from_the_horizon(hworld):
    """G2/G4/R1/S2: known ids, known people and the world digest exclude a future-only
    person, and the digest carries no future location of the protagonist."""
    v = HorizonView(hworld, H)
    assert "person:later" not in game._canon_entity_ids(v)
    assert "person:later" not in game._known_people(v)
    assert "person:later" in game._canon_entity_ids(hworld)          # negative control
    snap = hworld.porcelain.snapshot([PROT], as_of=H)
    assert all(f.get("value") != "place:shed" for f in snap.get("facts", []))
    v_digest = game._world_digest(v)
    assert "person:later" not in v_digest and "Later Person" not in v_digest


# ------------------------------------------------- continue_episode end to end (4a, 4b)

def _make_horizon_slot(tmp_path, monkeypatch, name="hz"):
    from tests.test_world_polish import _PROPOSAL
    from construct.arc import io as arc_io
    from construct.arc.executor import SESSION
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    spath = tmp_path / "worlds" / f"{name}.world"
    w = World(spath, world_id=f"w:{name}", stance="fiction",
              attribute_default=attribute_default, model=StubModel(fallback=_fallback))
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured(_rows())
    arc = game._build_arc({**_PROPOSAL, "protagonist": PROT, "title": "First"},
                          arc_id="arc:main")
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    w.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "kind", "value": "turn",
         "valid_from": OPENING},
        {"entity": "session:narrative_memory", "attribute": "text",
         "value": "You slipped out of the cell into the street.",
         "value_type": "literal", "valid_from": OPENING},
    ], frame=SESSION)
    w.close()
    spath.with_suffix(".meta.json").write_text(json.dumps(
        {"title": "First", "protagonist": PROT, "arc_scope": [PROT], "mode": "pure",
         "scenario_mode": "win_loss", "genre": "noir", "death_policy": "shielded",
         "opening_as_of": OPENING, "next_source_as_of": NEXT_SOURCE,
         "entry_epoch": OPENING}))
    shutil.copyfile(spath, game.slot_path(name, "u1"))
    return name


def _spy_reads(monkeypatch):
    """Record the results of every raw porcelain read continue_episode makes."""
    seen: list = []
    for meth in ("locate", "snapshot", "state", "facts", "entities"):
        orig = getattr(Porcelain, meth)

        def spy(self, *a, _orig=orig, _m=meth, **kw):
            out = _orig(self, *a, **kw)
            seen.append((_m, a, kw, out))
            return out
        monkeypatch.setattr(Porcelain, meth, spy)
    return seen


def _leaks_future_facts(seen) -> bool:
    def walk(x):
        if isinstance(x, dict):
            if (x.get("entity") == PROT and x.get("attribute") == "in"
                    and x.get("value") == "place:shed"):
                return True
            if (x.get("entity") == "obj:pass" and x.get("attribute") == "in"
                    and x.get("value") == PROT):
                return True
            return any(walk(v) for v in x.values())
        if isinstance(x, (list, tuple)):
            return any(walk(v) for v in x)
        return False
    for meth, a, kw, out in seen:
        if meth == "locate" and a and a[0] == PROT and "place:shed" in (out or []):
            return True
        if walk(out):
            return True
    return False


def _gen_prompts(prov):
    from construct.provider import task_of
    return [p for (p, _s, _t) in prov.calls if task_of(p) == "gen"]


def test_continuation_reads_no_future_fact(tmp_path, monkeypatch):
    """4a: the realistic fixture — the shed and pass are legitimate known entities, but the
    protagonist's future location and possession never reach the chapter-2 build."""
    from tests.test_world_polish import _ContProvider, _PROPOSAL
    name = _make_horizon_slot(tmp_path, monkeypatch)
    seen = _spy_reads(monkeypatch)
    prov = _ContProvider([{**_PROPOSAL, "protagonist": PROT}])
    game.continue_episode(name, prov, player_id="u1")
    assert not _leaks_future_facts(seen)
    gens = _gen_prompts(prov)
    assert gens and all("person:later" not in g for g in gens)      # 4b: future-only id


def test_continuation_negative_control_leaks_on_the_raw_world(tmp_path, monkeypatch):
    """The same build with the view bypassed reads the hidden ending."""
    from tests.test_world_polish import _ContProvider, _PROPOSAL
    name = _make_horizon_slot(tmp_path, monkeypatch)
    monkeypatch.setattr(adapter, "HorizonView", lambda w, h=None: w)
    seen = _spy_reads(monkeypatch)
    prov = _ContProvider([{**_PROPOSAL, "protagonist": PROT}])
    game.continue_episode(name, prov, player_id="u1")
    assert _leaks_future_facts(seen)
    assert any("person:later" in g for g in _gen_prompts(prov))


# ------------------------------------------------------------- Session (9, 9b, 14)

def _session_scenario(tmp_path, monkeypatch, horizon: bool):
    from tests.test_session import _author_scenario
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    path = tmp_path / "worlds" / "demo.world"
    _author_scenario(path, "w:demo")
    if horizon:
        meta = json.loads(path.with_suffix(".meta.json").read_text())
        meta.update({"opening_as_of": 1000.0, "next_source_as_of": NEXT_SOURCE,
                     "entry_epoch": 1000.0})
        path.with_suffix(".meta.json").write_text(json.dumps(meta))
    return "demo"


def test_legacy_session_holds_the_raw_world(tmp_path, monkeypatch):
    from construct.session import Session
    from tests.test_session import _provider
    s = Session.open(_session_scenario(tmp_path, monkeypatch, False), player_id="leg",
                     fresh=True, provider=_provider())
    try:
        assert isinstance(s._world, World) and not isinstance(s._world, HorizonView)
        reply = s.turn("I look around the study.")
        assert reply.ok
    finally:
        s.close()


def test_session_horizon_advances_turn_by_turn(tmp_path, monkeypatch):
    """9 / 9b (cr r5): every injected as_of equals Session._horizon() at that read, computed
    independently from the raw world; the second turn's is one above the first's; the
    horizon computation never recurses through the proxy."""
    from construct.game import next_turn_number
    from construct.session import Session
    from tests.test_session import _provider
    s = Session.open(_session_scenario(tmp_path, monkeypatch, True), player_id="hz",
                     fresh=True, provider=_provider())
    try:
        assert isinstance(s._world, HorizonView)
        raw = s._world.head
        frozen = HorizonView(raw, s._horizon())          # negative control: a cached float
        log: list[tuple[float, float]] = []
        real_bind = adapter._bind_as_of

        def spy(fn, horizon, args, kwargs):
            expected = play_horizon(1000.0, NEXT_SOURCE, next_turn_number(raw))
            log.append((horizon, expected))
            return real_bind(fn, horizon, args, kwargs)
        monkeypatch.setattr(adapter, "_bind_as_of", spy)

        assert s.turn("I look around the study.").ok
        first = {h for h, _e in log}
        n1 = len(log)
        assert s.turn("I look around the study again.").ok
        second = {h for h, _e in log[n1:]}
        assert log and all(h == e for h, e in log)
        assert max(second) == max(first) + 1
        assert frozen.horizon() == min(first)            # the frozen view did not advance
    finally:
        s.close()


# ------------------------------------- fail closed when presence is unreadable (cr code review)

def _presence_raises(monkeypatch, entity):
    real = PorcelainWorldReads.has_entity

    def has_entity(self, e):
        if e == entity:
            raise RuntimeError("store unreadable")
        return real(self, e)
    monkeypatch.setattr(PorcelainWorldReads, "has_entity", has_entity)


def _canon_count(w):
    return len(w.porcelain.facts("canon"))


def test_reshape_declines_when_presence_is_unreadable(hworld, monkeypatch):
    """refer resolves 'Later Person' to the future-only id; the presence check raises; the
    reshape must neither return that id nor write anything. Since pattern-buffer e3101a4,
    refer at the horizon no longer resolves a future name, so the resolve is simulated:
    the guard is the backstop for any path that still binds one."""
    from types import SimpleNamespace
    from construct import cohorts, reshape
    real_refer = hworld.refer

    def refer(text, *a, **k):
        if text == "Later Person":
            return SimpleNamespace(status="resolved", entity_id="person:later")
        return real_refer(text, *a, **k)
    monkeypatch.setattr(hworld, "refer", refer)
    v = HorizonView(hworld, H)
    plan = ReshapePlan(slug="x", state_rows=[
        {"entity": "obj:note", "attribute": "about", "value": "Later Person"}])
    _presence_raises(monkeypatch, "person:later")
    with pytest.raises(adapter.IdentityUnavailable):
        canonicalize_plan(v, plan)
    monkeypatch.setattr(cohorts, "propose_reshape", lambda *a, **k: {"is_reshape": True})
    monkeypatch.setattr(reshape, "plan_from_proposal", lambda *a, **k: ReshapePlan(
        slug="x", state_rows=[{"entity": "obj:note", "attribute": "about",
                               "value": "Later Person"}]))
    before = _canon_count(hworld)
    assert reshape.apply_reshape(v, None, action="a", scene="s", canon="c",
                                 tier="complete_success", turn=3, enabled=True) is None
    assert _canon_count(hworld) == before


def test_grant_declines_when_presence_is_unreadable(hworld, monkeypatch):
    at = OPENING + 6
    _presence_raises(monkeypatch, "place:far_hut")
    before = _canon_count(hworld)
    got, seg = _grant_moved_place(HorizonView(hworld, at), PROT, "the far hut", at=at,
                                  as_of=at)
    assert (got, seg) == (None, None)
    assert _canon_count(hworld) == before


def test_hook_staging_declines_when_presence_is_unreadable(hworld, monkeypatch):
    v = HorizonView(hworld, H)
    _presence_raises(monkeypatch, "person:later")
    rows, ids = game._plan_hook_cast(
        v, PorcelainWorldReads(v), {"hook_cast": [{"id": "person:later", "name": "L"}]},
        None, PROT, at=H)
    assert rows == [] and ids == []
