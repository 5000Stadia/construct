"""ScenarioMeta / PlaythroughState (audit 2026-10 tier 2 #4, F1).

The golden round-trip is the safety net for the whole refactor: every committed
``worlds/*.meta.json`` must load and serialize back to the SAME JSON, byte for byte.
"""

import json
from pathlib import Path

import pytest

from construct import game
from construct.scenario_meta import (
    InputAuthority, PlaythroughState, ScenarioMeta, ScenarioMode,
)

REPO_WORLDS = Path(__file__).resolve().parent.parent / "worlds"
META_FILES = sorted(REPO_WORLDS.glob("*.meta.json"))


def test_there_are_golden_files():
    assert META_FILES, "no worlds/*.meta.json to pin the round-trip against"


@pytest.mark.parametrize("path", META_FILES, ids=lambda p: p.name)
def test_golden_round_trip_every_existing_meta(path):
    text = path.read_text()
    raw = json.loads(text)
    sm = ScenarioMeta.from_json(raw)
    assert sm.to_json() == raw
    assert list(sm.to_json()) == list(raw)                   # key ORDER too
    assert json.dumps(sm.to_json(), indent=2) == json.dumps(raw, indent=2)
    # and the file text itself, where it was written by json.dumps(indent=2)
    if text == json.dumps(raw, indent=2):
        assert json.dumps(sm.to_json(), indent=2) == text


def test_enums_equal_stored_strings_and_serialize_plain():
    sm = ScenarioMeta.from_json({"mode": "coauthor", "scenario_mode": "win_loss"})
    assert sm.mode is InputAuthority.COAUTHOR and sm.mode == "coauthor"
    assert sm.scenario_mode is ScenarioMode.WIN_LOSS and sm.scenario_mode == "win_loss"
    out = sm.to_json()
    assert type(out["mode"]) is str and type(out["scenario_mode"]) is str


def test_unknown_values_and_keys_are_preserved_verbatim():
    raw = {"zzz_legacy": {"a": 1}, "scenario_mode": "bounded", "title": "T",
           "_side_arcs": [], "mode": None, "opening_as_of": None}
    sm = ScenarioMeta.from_json(raw)
    assert sm.scenario_mode == "bounded" and not isinstance(sm.scenario_mode, ScenarioMode)
    assert sm.extra["zzz_legacy"] == {"a": 1}
    assert sm.to_json() == raw and list(sm.to_json()) == list(raw)
    assert sm.has("opening_as_of") and sm.get("opening_as_of", 5) is None   # null != absent
    assert not sm.has("genre") and sm.get("genre", "x") == "x"


def test_evolve_appends_new_keys_and_never_mutates():
    sm = ScenarioMeta.from_json({"title": "T", "seeded_frames": ["a"]})
    sm2 = sm.evolve(seeded_frames=["a", "b"], main_arc="arc:main", brand_new=1)
    assert sm.to_json() == {"title": "T", "seeded_frames": ["a"]}
    assert list(sm2.to_json()) == ["title", "seeded_frames", "main_arc", "brand_new"]
    assert sm2.main_arc == "arc:main" and sm2.get("brand_new") == 1


def test_load_missing_file_is_empty_and_save_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(game, "WORLDS_DIR", tmp_path)
    assert ScenarioMeta.load("nope").to_json() == {}
    sm = ScenarioMeta.load("nope").evolve(title="X", scenario_mode=ScenarioMode.ENDLESS)
    sm.save()
    on_disk = (tmp_path / "nope.meta.json").read_text()
    assert on_disk == json.dumps({"title": "X", "scenario_mode": "endless"}, indent=2)
    assert ScenarioMeta.load("nope") == sm


class TestPlaythroughState:
    def test_slot_rows_beat_meta(self):
        meta = {"title": "One", "death_policy": "shielded", "arc_scope": ["a", "b"],
                "entry_epoch": 100.0}
        st = PlaythroughState(meta, {
            "episode.arc_scope": json.dumps(["c"]), "episode.entry_epoch": 250,
            "episode.chapter_title": " Two ", "episode.death_policy": "mortal",
            "scope.independent_extra": json.dumps(["x"])})
        assert st.scope == ["c"] and st.slot_scope_loaded
        assert st.entry_epoch == 250.0
        assert st.meta["title"] == "Two" and st.meta["death_policy"] == "mortal"
        assert st.independent_extra == {"x"}
        assert meta["title"] == "One"                       # the input is not mutated

    def test_absent_rows_leave_meta_standing(self):
        st = PlaythroughState(ScenarioMeta.from_json(
            {"title": "One", "arc_scope": ["a"], "entry_epoch": 7}), {})
        assert st.scope == ["a"] and not st.slot_scope_loaded
        assert st.entry_epoch == 7.0 and st.meta["title"] == "One"
        assert st.independent_extra == set()

    def test_no_scope_anywhere_is_none_and_epoch_defaults(self):
        from construct.arc.executor import TURN_EPOCH
        st = PlaythroughState({}, {})
        assert st.scope is None and st.entry_epoch == float(TURN_EPOCH)

    def test_bad_slot_scope_falls_back_to_meta(self):
        st = PlaythroughState({"arc_scope": ["a"]}, {"episode.arc_scope": "{not json"})
        assert st.scope == ["a"] and not st.slot_scope_loaded
