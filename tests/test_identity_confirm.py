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
        assert game._closure_reader(w)(HERO) == {HERO, FRAG}
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
        closure = game._closure_reader(w)
        assert HERO not in closure(FRAG)
        assert game._held_apart(w, closure(FRAG), closure(HERO))
    finally:
        w.close()


def test_a_row_only_about_the_other_closure_is_not_evidence(tmp_path):
    w = _member_frame_world(tmp_path, [(HERO, "in", "place:yard")])
    try:
        game._stage_confirm_identity(w, _arc(), set())
        assert game._closure_reader(w)(HERO) == {HERO, FRAG, "person:tom"}
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
        closure = game._closure_reader(w)
        assert holder not in closure(hero)                           # never joined
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
        closure = game._closure_reader(w)
        assert game._held_apart(w, closure("person:voss"), closure("person:voss_2"))
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
        assert "person:voss_2" in game._closure_reader(w)("person:voss")
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
