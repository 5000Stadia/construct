"""IDENTITY-CONFIRM r2 (R34 P2 + P3; gate gc53c58, monitor n126701; cr GREEN): at the vouch
slot the build confirms the open `frame_owner` pairs of the protagonist and the required-
clue holders, with the load-bearing id as the survivor, rejects a pair whose own frames tell
the two apart, never joins two load-bearing closures, and stops the build (one ViabilityError
on every creation path) when such a pair is still open. Checks 2-7 of the spec."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from construct import game

HERO, FRAG = "person:tomas_vale", "person:tomas"


def _person(eid: str, name: str, *aliases: str) -> list[dict]:
    rows = [{"entity": eid, "attribute": "kind", "value": "person", "timeless": True},
            {"entity": eid, "attribute": "name", "value": name}]
    return rows + [{"entity": eid, "attribute": "alias", "value": a} for a in aliases]


def _knows(w, owner: str, rows: list[tuple[str, str, str]]) -> None:
    w.porcelain.ingest_structured(
        [{"entity": s, "attribute": a, "value": v, "value_type": "entity"} for s, a, v in rows],
        frame=f"knows:{owner}", classify="rules")


def _arc(protagonist: str = HERO):
    return SimpleNamespace(arc_id="arc:main", protagonist=protagonist)


def _twin_world(tmp_path, frag_frame_rows=None):
    """The run 6 / eval/14 build 2 shape: a name variant of the hero that owns a `knows:`
    frame, entered into the log BEFORE the hero (so the engine's own election would serve
    the closure under the fragment). reconcile() leaves the pair as a frame_owner proposal."""
    w = game._world(tmp_path / "t.world", "t", model=None)
    w.porcelain.ingest_structured(_person(FRAG, "Tomas Vale"), classify="rules")
    w.porcelain.ingest_structured(_person(HERO, "Tomas Vale")
                                  + [{"entity": "place:yard", "attribute": "kind",
                                      "value": "place", "timeless": True}], classify="rules")
    _knows(w, FRAG, frag_frame_rows if frag_frame_rows is not None
           else [(HERO, "in", "place:yard")])           # a row only ABOUT the hero
    w.porcelain.reconcile()
    assert game._frame_owner_proposals(w) == [(FRAG, HERO)]
    return w


def _commit_arc_row(w, protagonist: str = HERO) -> None:
    w.porcelain.ingest_structured([{"entity": "arc:main", "attribute": "protagonist",
                                    "value": protagonist}], frame="plot:main",
                                  classify="rules")


# ---- check 2: the hero's frame-owner twin is confirmed, the hero the survivor ------------

def test_the_heros_frame_owner_twin_is_confirmed_with_the_hero_as_survivor(tmp_path):
    w = _twin_world(tmp_path)
    try:
        game._stage_confirm_identity(w, _arc(), set())          # viable: no raise
        assert game._closure(w, HERO) == {HERO, FRAG}
        assert game._frame_owner_proposals(w) == []
        _commit_arc_row(w)
        assert game._protagonist_coherence(w, _arc()) == HERO   # the seal passes
    finally:
        w.close()


def test_a_pair_touching_no_load_bearing_id_is_left_alone(tmp_path):
    w = _twin_world(tmp_path)
    try:
        game._stage_confirm_identity(w, _arc("person:someone_else"), set())
        assert game._frame_owner_proposals(w) == [(FRAG, HERO)]   # neither confirmed nor a stop
    finally:
        w.close()


# ---- check 3 (a): the frame-evidence scan reads every closure member's own frame ---------

def _member_frame_world(tmp_path, member_rows):
    """FRAG's closure also holds person:tom, merged in earlier; the evidence (or the
    about-only row) sits in tom's frame, not in the frame of either proposal id."""
    w = _twin_world(tmp_path)
    w.porcelain.ingest_structured(_person("person:tom", "Tom"), classify="rules")
    assert w.porcelain.merge(FRAG, "person:tom", evidence="test fixture",
                             representative=FRAG)["outcome"] == "merged"
    _knows(w, "person:tom", member_rows)
    return w


def test_a_closure_members_frame_relating_the_two_closures_rejects_the_pair(tmp_path):
    w = _member_frame_world(tmp_path, [("person:tom", "distrusts", HERO)])
    try:
        game._stage_confirm_identity(w, _arc(), set())          # settled: no stop
        assert HERO not in game._closure(w, FRAG)
        assert game._held_apart(w, FRAG, HERO)
    finally:
        w.close()


def test_a_row_only_about_the_other_closure_is_not_evidence(tmp_path):
    w = _member_frame_world(tmp_path, [(HERO, "in", "place:yard")])
    try:
        game._stage_confirm_identity(w, _arc(), set())
        assert game._closure(w, HERO) == {HERO, FRAG, "person:tom"}
    finally:
        w.close()


def test_a_row_relating_the_two_ids_in_a_frame_is_evidence(tmp_path):
    w = _twin_world(tmp_path)
    try:
        assert not game._frames_tell_apart(w, {FRAG}, {HERO})
        _knows(w, FRAG, [(FRAG, "rivals", HERO)])
        assert game._frames_tell_apart(w, {FRAG}, {HERO})
    finally:
        w.close()


# ---- check 4 (b): receipts decide, not intentions ----------------------------------------

@pytest.mark.parametrize("receipt", [
    {"outcome": "no_proposal", "canonical_id": None},
    {"outcome": "vetoed", "canonical_id": None},
    {"outcome": "conflict_already_merged", "canonical_id": None},
    {"outcome": "merged", "canonical_id": FRAG},               # the wrong survivor
])
def test_a_confirm_receipt_that_is_not_success_stops_the_build(tmp_path, monkeypatch, receipt):
    w = _twin_world(tmp_path)
    try:
        monkeypatch.setattr(w.porcelain, "confirm", lambda a, b, representative=None: receipt)
        with pytest.raises(game.IdentityUnresolvedError) as err:
            game._stage_confirm_identity(w, _arc(), set())
        assert {(a, b) for a, b, _ in err.value.pairs} == {(FRAG, HERO)}
        assert repr(receipt["outcome"]) in str(err.value)
    finally:
        w.close()


def test_a_confirm_that_raises_stops_the_build(tmp_path, monkeypatch):
    w = _twin_world(tmp_path)
    try:
        def _boom(a, b, representative=None):
            raise ValueError("representative not in either closure")
        monkeypatch.setattr(w.porcelain, "confirm", _boom)
        with pytest.raises(game.IdentityUnresolvedError, match="ValueError"):
            game._stage_confirm_identity(w, _arc(), set())
    finally:
        w.close()


@pytest.mark.parametrize("outcome", ["conflict_already_correlated", "conflict_already_merged"])
def test_a_reject_receipt_that_is_not_success_stops_the_build(tmp_path, monkeypatch, outcome):
    w = _twin_world(tmp_path, frag_frame_rows=[(FRAG, "rivals", HERO)])
    try:
        monkeypatch.setattr(w.porcelain, "reject",
                            lambda a, b: {"outcome": outcome, "canonical_id": None})
        with pytest.raises(game.IdentityUnresolvedError) as err:
            game._stage_confirm_identity(w, _arc(), set())
        assert {(a, b) for a, b, _ in err.value.pairs} == {(FRAG, HERO)}
    finally:
        w.close()


# ---- check 5 (c): a transitive cascade never joins two load-bearing closures --------------

def test_a_cascade_never_joins_two_load_bearing_closures(tmp_path):
    """Three frame_owner proposals: hero~frag and frag~holder share the fragment, so
    confirming either first would let the other join the hero and the clue holder. A third,
    between two bystanders, touches nothing load-bearing and is left as it is."""
    hero, frag, holder = "person:ann", "person:ann_bell", "person:cray"
    w = game._world(tmp_path / "c.world", "c", model=None)
    try:
        w.porcelain.ingest_structured(
            _person(hero, "Ann Bell") + _person(holder, "Cray Lund")
            + _person(frag, "Ann Bell", "Cray Lund")
            + _person("person:pell", "Pell Orr") + _person("person:pell_orr", "Pell Orr"),
            classify="rules")
        _knows(w, frag, [(hero, "kin_of", "person:pell")])          # frag owns a frame
        _knows(w, "person:pell_orr", [("person:pell_orr", "in", "place:yard")])
        w.porcelain.reconcile()
        before = {frozenset(p) for p in game._frame_owner_proposals(w)}
        assert {frozenset((hero, frag)), frozenset((frag, holder)),
                frozenset(("person:pell", "person:pell_orr"))} <= before

        with pytest.raises(game.IdentityUnresolvedError) as err:
            game._stage_confirm_identity(w, _arc(hero), {holder})
        assert holder not in game._closure(w, hero)                  # never joined
        assert any("load-bearing" in why for _, _, why in err.value.pairs)
        assert frozenset(("person:pell", "person:pell_orr")) in {
            frozenset(p) for p in game._frame_owner_proposals(w)}   # bystanders untouched
        assert not any({a, b} & {"person:pell", "person:pell_orr"}
                       for a, b, _ in err.value.pairs)
    finally:
        w.close()


# ---- check 6: a cast-collision id is deliberately distinct ---------------------------------

def test_a_cast_collision_pair_is_held_apart_and_never_stops_the_build(tmp_path):
    w = game._world(tmp_path / "v.world", "v", model=None)
    try:
        w.porcelain.ingest_structured(_person("person:voss", "Voss"), classify="rules")
        game._admit_disambiguated_cast(
            w, {"person:voss": "person:voss_2"},
            {"cast": [{"id": "person:voss_2", "surface_role": "smuggler"}]})
        w.porcelain.reconcile()
        assert game._held_apart(w, "person:voss", "person:voss_2")
        assert not [p for p in w.porcelain.proposals()
                    if {p["a"], p["b"]} == {"person:voss", "person:voss_2"}]
        assert game._identity_stops(w, {"person:voss"}) == []
    finally:
        w.close()


def test_without_the_reject_the_cast_collision_pair_fuses(tmp_path):
    # Negative control: the same two people named Voss, not held apart, are one entity
    # after reconcile, which is the #92 collision the reject exists to prevent.
    w = game._world(tmp_path / "v.world", "v", model=None)
    try:
        w.porcelain.ingest_structured(_person("person:voss", "Voss")
                                      + _person("person:voss_2", "Voss"), classify="rules")
        w.porcelain.reconcile()
        assert "person:voss_2" in game._closure(w, "person:voss")
    finally:
        w.close()


# ---- check 7 (d): one build-stop contract on every creation path ---------------------------

STOP = game.IdentityUnresolvedError([(FRAG, HERO, "open frame_owner proposal")])


@pytest.fixture
def chdir_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _raise_stop(*a, **k):
    raise STOP


def _assert_stopped(err, name, source_path):
    assert err.value.problems[0] == STOP.plain
    assert "identity unresolved at build" in err.value.problems[1]
    assert Path(err.value.source_path).resolve() == source_path and source_path.is_file()
    assert not game.scenario_path(name).exists()
    assert not game.scenario_path(name).with_suffix(".meta.json").exists()


def test_the_interview_path_stops_as_not_viable_and_keeps_the_brief(chdir_tmp, monkeypatch):
    from tests.test_interview import _InterviewStub
    monkeypatch.setattr(game, "_stage_confirm_identity", _raise_stop)  # the real finalize
    with pytest.raises(game.ViabilityError) as err:
        game.create_scenario_from_interview("harbor", "a drowned harbor town", _InterviewStub())
    _assert_stopped(err, "harbor", chdir_tmp / "generated" / "harbor.brief.md")
    assert err.value.source_path.read_text() == "a drowned harbor town"


def test_the_ingest_path_stops_as_not_viable(chdir_tmp, monkeypatch):
    from tests.test_interview import _InterviewStub
    prose = chdir_tmp / "book.md"
    prose.write_text("# The Book\n\nTomas Vale walked into the yard.\n")
    monkeypatch.setattr(game, "_finalize_scenario", _raise_stop)
    with pytest.raises(game.ViabilityError) as err:
        game.create_scenario_from_ingest("book", prose, _InterviewStub())
    _assert_stopped(err, "book", prose)


def test_the_generated_path_stops_as_not_viable_and_keeps_the_story(chdir_tmp, monkeypatch):
    from construct import cohorts
    from tests.test_interview import _InterviewStub
    monkeypatch.setattr(game, "_author_world_laws", lambda *a, **k: ([], ""))
    monkeypatch.setattr(cohorts, "author_story",
                        lambda *a, **k: {"title": "Gen", "prose": "Tomas Vale waited."})
    monkeypatch.setattr(game, "_finalize_scenario", _raise_stop)
    with pytest.raises(game.ViabilityError) as err:
        game.create_scenario_from_generated("gen", _InterviewStub(), seed="s")
    _assert_stopped(err, "gen", chdir_tmp / "generated" / "gen.md")


@pytest.mark.parametrize("branch", ["generate", "interview", "ingest"])
def test_cli_new_prints_the_viability_message_and_exits_1(chdir_tmp, monkeypatch, capsys,
                                                         branch):
    import argparse

    from construct import cli
    kept = chdir_tmp / "generated" / "x.md"

    def _stop(name, *a, **k):
        raise game.ViabilityError(name, kept, [STOP.plain, str(STOP)])
    for fn in ("create_scenario_from_generated", "create_scenario_from_interview",
               "create_scenario_from_ingest"):
        monkeypatch.setattr(game, fn, _stop)
    monkeypatch.setattr(cli, "_provider", lambda: object())
    args = argparse.Namespace(
        name="x", endless=False, win_direction="", play_as="",
        generate="seed" if branch == "generate" else None,
        interview="a brief" if branch == "interview" else None,
        ingest=str(chdir_tmp / "book.md") if branch == "ingest" else None)
    assert cli._cmd_new(args) == 1
    err = capsys.readouterr().err
    assert STOP.plain in err and str(kept) in err and "Traceback" not in err


# ---- cr RED on 8ec8e27: the vouch and the cast-collision reject never fail open ----------

HOLDER, ECHO = "person:brigg", "person:ansel_brigg"


def _holder_world(tmp_path, monkeypatch):
    """A required-clue holder and a fragment the vouch allowlist selects (forced here)."""
    w = game._world(tmp_path / "h.world", "h", model=None)
    w.porcelain.ingest_structured(_person(ECHO, "Ansel Brigg") + _person(HOLDER, "Brigg"),
                                  classify="rules")
    monkeypatch.setattr(game, "_fidelity_vouched_pairs", lambda groups, lb: [(HOLDER, ECHO)])
    return w


@pytest.mark.parametrize("receipt", [
    {"outcome": "vetoed", "canonical_id": None},
    {"outcome": "merged", "canonical_id": ECHO},                # the wrong survivor
])
def test_a_bad_vouch_receipt_for_a_required_holder_stops_the_build(tmp_path, monkeypatch,
                                                                   receipt):
    w = _holder_world(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(w.porcelain, "merge", lambda *a, **k: receipt)
        with pytest.raises(game.IdentityUnresolvedError) as err:
            game._stage_vouch_merges(w, _arc(), {HOLDER})
        assert [(a, b) for a, b, _ in err.value.pairs] == [(HOLDER, ECHO)]
    finally:
        w.close()


def test_a_vouch_merge_that_raises_stops_the_build(tmp_path, monkeypatch):
    w = _holder_world(tmp_path, monkeypatch)
    try:
        def _boom(*a, **k):
            raise ValueError("representative not in either closure")
        monkeypatch.setattr(w.porcelain, "merge", _boom)
        with pytest.raises(game.IdentityUnresolvedError, match="ValueError"):
            game._stage_vouch_merges(w, _arc(), {HOLDER})
    finally:
        w.close()


def test_a_good_vouch_for_a_required_holder_keeps_the_holder(tmp_path, monkeypatch):
    # The control: the real engine merge, served as the holder, passes.
    w = _holder_world(tmp_path, monkeypatch)
    try:
        game._stage_vouch_merges(w, _arc(), {HOLDER})
        assert game._closure(w, HOLDER) == {HOLDER, ECHO}
    finally:
        w.close()


def test_a_wrong_survivor_for_a_required_holder_stops_a_real_build(chdir_tmp, monkeypatch):
    """End to end through the interview path's real finalize: the holder's vouched merge
    comes back served as the fragment, so the build stops, the half-built world is removed,
    and the caller gets one ViabilityError."""
    from patternbuffer.porcelain import Porcelain

    from tests.test_interview import _InterviewStub
    monkeypatch.setattr(game, "_stage_author_cast",
                        lambda world, provider, arc, *a, **k: (arc, (), None, {"person:rook"}))
    monkeypatch.setattr(game, "_fidelity_vouched_pairs",
                        lambda groups, lb: [("person:rook", "person:rook_echo")])
    monkeypatch.setattr(Porcelain, "merge", lambda self, a, b, evidence, representative=None:
                        {"outcome": "merged", "canonical_id": "person:rook_echo"})
    with pytest.raises(game.ViabilityError) as err:
        game.create_scenario_from_interview("harbor", "a drowned harbor town", _InterviewStub())
    assert err.value.problems[0] == game.IdentityUnresolvedError.plain
    assert "person:rook ~ person:rook_echo" in err.value.problems[1]
    assert not game.scenario_path("harbor").exists()
    assert not game.scenario_path("harbor").with_suffix(".meta.json").exists()
    assert (chdir_tmp / "generated" / "harbor.brief.md").is_file()


@pytest.mark.parametrize("stub", ["receipt", "raises"])
def test_a_failed_cast_collision_reject_stops_the_build(tmp_path, monkeypatch, stub):
    w = game._world(tmp_path / "v.world", "v", model=None)
    try:
        w.porcelain.ingest_structured(_person("person:voss", "Voss"), classify="rules")

        def _reject(a, b):
            if stub == "raises":
                raise RuntimeError("engine refused")
            return {"outcome": "conflict_already_correlated", "canonical_id": None}
        monkeypatch.setattr(w.porcelain, "reject", _reject)
        with pytest.raises(game.IdentityUnresolvedError) as err:
            game._admit_disambiguated_cast(
                w, {"person:voss": "person:voss_2"},
                {"cast": [{"id": "person:voss_2", "surface_role": "smuggler"}]})
        assert [(a, b) for a, b, _ in err.value.pairs] == [("person:voss", "person:voss_2")]
    finally:
        w.close()


def test_cast_authoring_lets_an_identity_stop_through(tmp_path, monkeypatch):
    """Cast authoring is fail-open for authoring misses, but an identity stop from the
    cast-collision admission must reach the creation path, not become 'pillar-less'."""
    import dataclasses

    from construct import cast, cohorts, story_shapes

    @dataclasses.dataclass(frozen=True)
    class _Arc:
        protagonist: str = HERO
        beats: tuple = ()
        pillars: tuple = ()

    monkeypatch.setattr(story_shapes, "shapes_for",
                        lambda gt: {"shape": "deduction", "secondary": []})
    monkeypatch.setattr(story_shapes, "author_signature_directive", lambda gt: "")
    monkeypatch.setattr(cohorts, "author_cast", lambda *a, **k: {"cast": []})
    monkeypatch.setattr(cast, "disambiguate_cast_identities",
                        lambda prop, ident, known: (prop, {"person:voss": "person:voss_2"}))
    monkeypatch.setattr(cast, "cast_from_proposal",
                        lambda prop: ([SimpleNamespace(node_id="person:voss_2")], []))
    for fn in ("check_solvability", "validate_signature_support", "validate_beat_delivery",
               "beat_delivery_targets"):
        monkeypatch.setattr(cast, fn, lambda *a, **k: [])
    monkeypatch.setattr(cast, "build_pillars", lambda *a, **k: ())
    monkeypatch.setattr(cast, "required_holder_ids", lambda *a, **k: set())
    monkeypatch.setattr(game, "_admit_disambiguated_cast", _raise_stop)
    w = game._world(tmp_path / "a.world", "a", model=None)
    try:
        with pytest.raises(game.IdentityUnresolvedError):
            game._stage_author_cast(w, object(), _Arc(), {}, "", [], [], ["deduction"], "")
    finally:
        w.close()


# ---- cr P1 on 8ec8e27: the scan holds no engine attribute list ---------------------------

def _append_bookkeeping(w, frame: str, entity: str, attribute: str, value: str) -> None:
    """Write an engine bookkeeping row into a frame the way the engine's own ingestor does
    (the fixture technique of pattern-buffer's tests/test_facts_bookkeeping.py). Fixture
    only: the code under test reads through the porcelain."""
    from patternbuffer.roles import _make_engine_roles
    w.buffer.append(entity=entity, attribute=attribute, value=value, value_type="entity",
                    status="stated", role=_make_engine_roles()["ingestor"], frame=frame)


@pytest.mark.parametrize("attribute", ["aka", "same_as", "source"])
def test_an_engine_bookkeeping_row_relating_the_closures_is_not_evidence(tmp_path, attribute):
    """Identity and provenance rows in a fragment's frame that name the other closure are
    the engine's bookkeeping, not the fragment's knowledge. facts(bookkeeping=False)
    leaves them out; the host names none of them."""
    w = _twin_world(tmp_path)
    try:
        _append_bookkeeping(w, f"knows:{FRAG}", FRAG, attribute, HERO)
        assert any(f["attribute"] == attribute for f in w.porcelain.facts(f"knows:{FRAG}"))
        assert not game._frames_tell_apart(w, {FRAG}, {HERO})
        game._stage_confirm_identity(w, _arc(), set())          # confirmed, not rejected
        assert game._closure(w, HERO) == {HERO, FRAG}
    finally:
        w.close()


def test_without_the_engine_filter_a_bookkeeping_row_would_read_as_evidence(tmp_path,
                                                                            monkeypatch):
    # Negative control: a scan that kept bookkeeping rows would reject a true twin.
    w = _twin_world(tmp_path)
    try:
        _append_bookkeeping(w, f"knows:{FRAG}", FRAG, "aka", HERO)
        real = w.porcelain.facts
        monkeypatch.setattr(w.porcelain, "facts",
                            lambda frame, **k: real(frame, **{**k, "bookkeeping": True}))
        assert game._frames_tell_apart(w, {FRAG}, {HERO})
    finally:
        w.close()


def test_the_build_module_imports_no_engine_constant():
    """The host reaches the engine through `World` and its porcelain only (CLAUDE.md)."""
    import ast
    from pathlib import Path as _P
    tree = ast.parse(_P(game.__file__).read_text())
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
             and (n.module or "").startswith("patternbuffer") for a in n.names}
    assert names == {"World"}, names
