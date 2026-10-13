"""NAMED BUT NOT HERE (OPENING-SETTLE-AND-ELSEWHERE Part A, cr GREEN at r3).

R20 run 7: the player, in their cell, asked to see a sack in the warrant room; nothing
told the narrator it was elsewhere, and it rendered the sack (and a hearth) in the cell.
A line is emitted from the player frame alone; canon context can only suppress one."""

import pytest

from construct import game
from construct.named_elsewhere import named_elsewhere

HERO = "person:hero"
K = f"knows:{HERO}"


def _ingest(w, rows, frame):
    w.porcelain.ingest_structured(
        [{"entity": e, "attribute": a, "value": v} for e, a, v in rows],
        frame=frame, classify="rules")


@pytest.fixture
def w(tmp_path):
    w = game._world(tmp_path / "n.world", "n", model=None)
    geography = [
        ("place:ironhold", "name", "Ironhold"),
        ("place:cell", "name", "the cell"),
        ("place:cell", "part_of", "place:ironhold"),
        ("place:warrant_room", "name", "the warrant room"),
        ("place:warrant_room", "part_of", "place:ironhold"),
        ("obj:table", "part_of", "place:cell"),
    ]
    _ingest(w, geography + [(HERO, "in", "place:cell")], "canon")
    _ingest(w, geography, K)
    return w


def _ask(w, line, **kw):
    args = dict(player_frame=K, player_input=line, protagonist=HERO, scene="place:cell",
                scene_features=["obj:table"], ancestors=["place:ironhold"])
    args.update(kw)
    return named_elsewhere(w, **args)


def test_sibling_room_gives_the_line(w):
    # cr r2 P1: cell and warrant room share Ironhold; a shared ancestor proves nothing
    rows = [("obj:sack", "alias", "sack"), ("obj:sack", "in", "place:warrant_room")]
    _ingest(w, rows, "canon")
    _ingest(w, rows, K)
    assert _ask(w, "Let me see the sack.") == [("obj:sack", "sack", "the warrant room")]


def test_on_a_table_here_is_here(w):
    # the directed descendant case: the path reaches a feature of this room
    _ingest(w, [("obj:cup", "alias", "cup"), ("obj:cup", "in", "obj:table")], K)
    assert _ask(w, "I pick up the cup.") == []


def test_carried_is_here(w):
    _ingest(w, [("obj:knife", "alias", "knife"), ("obj:knife", "in", HERO)], K)
    assert _ask(w, "I check the knife.") == []


def test_in_this_room_is_here(w):
    _ingest(w, [("obj:pail", "alias", "pail"), ("obj:pail", "in", "place:cell")], K)
    assert _ask(w, "I kick the pail.") == []


def test_canon_only_placement_gives_no_block(w):
    # the player frame knows the ledger by name, but only canon knows where it is
    _ingest(w, [("obj:ledger", "alias", "ledger"), ("obj:ledger", "in", "place:warrant_room")],
            "canon")
    _ingest(w, [("obj:ledger", "alias", "ledger")], K)
    assert _ask(w, "Where is the ledger?") == []


def test_unknown_to_the_player_frame_gives_no_line(w):
    _ingest(w, [("obj:lamp", "alias", "lamp"), ("obj:lamp", "in", "place:warrant_room")],
            "canon")
    assert _ask(w, "I want the lamp.") == []


def test_player_frame_here_wins_over_canon_elsewhere(w):
    # `_here` (canon presence) is not consulted: the player frame puts the mug here
    _ingest(w, [("obj:mug", "alias", "mug"), ("obj:mug", "in", "place:warrant_room")], "canon")
    _ingest(w, [("obj:mug", "alias", "mug"), ("obj:mug", "in", "place:cell")], K)
    assert _ask(w, "I drink from the mug.") == []


def test_coarse_ancestor_is_underdetermined(w):
    _ingest(w, [("obj:coin", "alias", "coin"), ("obj:coin", "in", "place:ironhold")], K)
    assert _ask(w, "Where is the coin?") == []


def test_people_keep_their_own_path(w):
    _ingest(w, [("person:dena", "alias", "Dena"), ("person:dena", "in", "place:warrant_room")], K)
    assert _ask(w, "Dena, come here.") == []


def test_whole_word_only(w):
    _ingest(w, [("obj:sack", "alias", "sack"), ("obj:sack", "in", "place:warrant_room")], K)
    assert _ask(w, "The room was ransacked.") == []


def test_cap_and_order(w):
    names = ["anvil", "barrel", "candle", "drum", "ewer"]
    rows = []
    for n in names:
        rows += [(f"obj:{n}", "alias", n), (f"obj:{n}", "in", "place:warrant_room")]
    _ingest(w, rows, K)
    got = _ask(w, "Bring the ewer, the drum, the candle, the barrel and the anvil.")
    assert [label for _e, label, _p in got] == ["ewer", "drum", "candle", "barrel"]


def test_cycle_and_hop_cap_terminate(w):
    _ingest(w, [("obj:box", "alias", "box"), ("obj:box", "in", "obj:crate"),
                ("obj:crate", "in", "obj:box")], K)
    deep = [("obj:pin", "alias", "pin"), ("obj:pin", "in", "obj:c1"), ("obj:c1", "in", "obj:c2"),
            ("obj:c2", "in", "obj:c3"), ("obj:c3", "in", "obj:c4"),
            ("obj:c4", "in", "place:warrant_room")]
    _ingest(w, deep, K)
    assert _ask(w, "The box and the pin.") == []


def test_a_prose_read_object_matches_by_its_own_words(w):
    # run 7: obj:torn_laundry_sack carried no name or alias row; the player said "the sack"
    _ingest(w, [("obj:torn_laundry_sack", "kind", "object"),
                ("obj:torn_laundry_sack", "in", "place:warrant_room")], K)
    assert _ask(w, "Let me see the sack.") == [
        ("obj:torn_laundry_sack", "sack", "the warrant room")]


def test_an_ambiguous_word_asserts_nothing(w):
    _ingest(w, [("obj:torn_sack", "in", "place:warrant_room"),
                ("obj:grain_sack", "in", "place:warrant_room")], K)
    assert _ask(w, "Let me see the sack.") == []
    assert _ask(w, "Let me see the grain sack.") == [
        ("obj:grain_sack", "grain sack", "the warrant room")]


def test_a_named_remote_place_gets_the_place_line(w):
    # cr on cdf79d0: a question about a remote room is not a move, and needs the line too
    assert _ask(w, "What happened in the warrant room?") == [
        ("place:warrant_room", "the warrant room", "Ironhold")]


def test_the_scene_and_its_ancestors_are_not_elsewhere(w):
    assert _ask(w, "I pace the cell.") == []
    assert _ask(w, "Nobody leaves Ironhold.") == []


def test_a_place_head_noun_is_not_a_label(w):
    assert _ask(w, "I look around the room.") == []


def test_a_generic_kind_is_not_a_label(w):
    _ingest(w, [("obj:x1", "kind", "object"), ("obj:x1", "in", "place:warrant_room")], K)
    assert _ask(w, "Is there an object here?") == []
