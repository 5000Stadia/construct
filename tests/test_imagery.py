"""SCENE-IMAGERY: per-location image prompts, hash-keyed reuse/refresh."""

from __future__ import annotations

import json

import pytest

from construct import cohorts, imagery
from construct.provider import StubProvider

STUDY = ("A narrow gaslit study at Number 17: a worn desk, ledgers in green tape, "
         "a low coal fire in the grate, damp pressing at the latched window.")
STUDY2 = STUDY + " Now the desk is overturned and the window glass is shattered."


@pytest.fixture
def worlds(tmp_path, monkeypatch):
    monkeypatch.setattr(imagery, "WORLDS_DIR", tmp_path)
    monkeypatch.setattr(imagery, "IMAGES_DIR", tmp_path / "images")  # never touch the repo tree
    monkeypatch.setenv("CONSTRUCT_SCENE_IMAGES", "1")  # opt back in (conftest disables by default)
    monkeypatch.delenv("CONSTRUCT_IMAGE_CMD", raising=False)
    # No real backend during tests — never hit the network (the built-in OpenAI
    # dispatcher fires whenever OPENAI_API_KEY is present).
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(imagery, "dispatcher", None)
    return tmp_path


def _prov(prompt="a gaslit Victorian study, bolted door, dying coal fire, fog at the glass"):
    return StubProvider([{"prompt": prompt}])


def test_fresh_then_cached_reuses_without_a_model_call(worlds):
    prov = _prov()
    rec = imagery.note_scene("latch", "place:study", "the study", STUDY, provider=prov)
    assert rec is not None and rec.status == "fresh"
    assert "oil color painting" in rec.prompt.lower()
    assert rec.asset_path.endswith(".png") and rec.description_hash in rec.asset_path
    assert len(prov.calls) == 1

    # same description on re-entry → cached, identical prompt, NO new model call
    again = imagery.note_scene("latch", "place:study", "the study", STUDY, provider=prov)
    assert again.status == "cached"
    assert again.prompt == rec.prompt
    assert again.asset_path == rec.asset_path
    assert len(prov.calls) == 1  # untouched — the reuse path never calls the model


def test_changed_description_makes_a_fresh_asset(worlds):
    prov = StubProvider([{"prompt": "a calm study"}, {"prompt": "a wrecked study"}])
    a = imagery.note_scene("latch", "place:study", "the study", STUDY, provider=prov)
    b = imagery.note_scene("latch", "place:study", "the study", STUDY2, provider=prov)
    assert b.status == "fresh"
    assert b.description_hash != a.description_hash
    assert b.asset_path != a.asset_path  # different hash → different file
    assert len(prov.calls) == 2


def test_house_style_always_appended(worlds):
    rec = imagery.note_scene("latch", "place:study", "the study", STUDY, provider=_prov())
    assert rec.prompt.strip().endswith(".")
    assert imagery.HOUSE_STYLE in rec.prompt
    # compose_prompt is deterministic and style-guaranteed even on raw content
    assert imagery.HOUSE_STYLE in imagery.compose_prompt("anything")


def test_genre_touch_dumped_into_style(worlds):
    rec = imagery.note_scene("latch", "place:study", "the study", STUDY,
                             provider=_prov(), genre="mystery whodunnit")
    assert "mystery whodunnit" in rec.prompt.lower()
    # no genre → no genre clause, but the house style still lands
    plain = imagery.compose_prompt("a room")
    assert "touch of" not in plain and imagery.HOUSE_STYLE in plain


def test_no_provider_falls_back_to_description(worlds):
    rec = imagery.note_scene("latch", "place:study", "the study", STUDY, provider=None)
    assert rec is not None and rec.status == "fresh"
    assert "green tape" in rec.prompt  # raw description carried through
    assert imagery.HOUSE_STYLE in rec.prompt


def test_disabled_returns_none(worlds, monkeypatch):
    monkeypatch.setenv("CONSTRUCT_SCENE_IMAGES", "0")
    assert imagery.note_scene("latch", "place:study", "s", STUDY, provider=_prov()) is None


def test_no_place_or_no_description_is_noop(worlds):
    assert imagery.note_scene("latch", None, "s", STUDY, provider=_prov()) is None
    assert imagery.note_scene("latch", "place:study", "s", "", provider=_prov()) is None
    assert imagery.note_scene("latch", "place:study", "s", "   ", provider=_prov()) is None


def test_manifest_persisted_and_reloadable(worlds):
    imagery.note_scene("latch", "place:study", "the study", STUDY, provider=_prov())
    path = imagery.manifest_path("latch")
    assert path.exists()
    data = json.loads(path.read_text())
    assert "place:study" in data
    assert data["place:study"]["description_hash"] == imagery._hash(STUDY)
    assert imagery.HOUSE_STYLE in data["place:study"]["prompt"]


def test_cohort_prompt_instructs_player_absence():
    """The image-prompt cohort must tell the model to strip people/the player."""
    prov = StubProvider([{"prompt": "an empty study"}])
    cohorts.image_prompt(prov, place_name="the study", description=STUDY)
    sent = prov.calls[0][0].lower()
    assert "no" in sent and ("person" in sent or "people" in sent or "unpeopled" in sent)
    assert "you" in sent  # explicitly bans the second-person 'you'


def test_dispatcher_is_called_on_fresh_only(worlds):
    seen = []

    def _disp(rec):  # a real backend writes the asset; caching is asset-gated
        seen.append(rec.status)
        from pathlib import Path
        Path(rec.asset_path).parent.mkdir(parents=True, exist_ok=True)
        Path(rec.asset_path).write_bytes(b"\x89PNG fake")

    imagery.dispatcher = _disp
    try:
        imagery.note_scene("latch", "place:study", "the study", STUDY, provider=_prov())
        imagery.note_scene("latch", "place:study", "the study", STUDY, provider=_prov())
    finally:
        imagery.dispatcher = None
    assert seen == ["fresh"]  # cached re-entry (asset present) does NOT re-dispatch


def test_backend_failure_is_not_cached_and_retries(worlds):
    """If a backend is configured but writes no asset (a failure / billing limit), the
    scene is NOT cached as done — a later visit re-renders so the image can still land."""
    calls = []
    imagery.dispatcher = lambda rec: calls.append(rec.place_id)  # writes no file
    try:
        a = imagery.note_scene("latch", "place:study", "the study", STUDY, provider=_prov())
        b = imagery.note_scene("latch", "place:study", "the study", STUDY, provider=_prov())
    finally:
        imagery.dispatcher = None
    assert a.status == "fresh" and b.status == "fresh"  # retried, not cached
    assert calls == ["place:study", "place:study"]
    assert not imagery.manifest_path("latch").exists()  # nothing cached
