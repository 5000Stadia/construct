"""Library import pipeline — the drop-a-document-into-the-library layer.
Tests the plumbing (naming, dedup, type-gating, folder scan, move, fail-open)
without a live model by stubbing the build."""

import pytest

from construct import library


@pytest.fixture
def chdir_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    return tmp_path


def test_unique_name_dedups_against_library(chdir_tmp):
    (chdir_tmp / "worlds" / "the_tale.world").write_text("x")  # an existing scenario
    assert library._unique_name("The Tale") == "the_tale_2"
    assert library._unique_name("Brand New") == "brand_new"


def test_ingest_document_rejects_bad_input(chdir_tmp):
    with pytest.raises(FileNotFoundError):
        library.ingest_document(chdir_tmp / "missing.md", provider=None)
    bad = chdir_tmp / "notes.pdf"
    bad.write_text("x")
    with pytest.raises(ValueError):
        library.ingest_document(bad, provider=None)


def test_scan_folder_ingests_moves_and_is_fail_open(chdir_tmp, monkeypatch):
    imp = chdir_tmp / "import"
    imp.mkdir()
    (imp / "good.md").write_text("# A Good Story\n\nonce upon a time")
    (imp / "boom.txt").write_text("# Boom")
    (imp / "ignore.json").write_text("{}")          # wrong type → skipped

    calls = []

    def _fake_build(name, prose_path, provider, endless=False, on_stage=None):
        calls.append(name)
        if "boom" in prose_path.name:
            raise RuntimeError("simulated build failure")
        if on_stage:
            on_stage("Stage 1 · (stub)")
        return {"title": f"Built {name}", "protagonist": "person:x"}

    monkeypatch.setattr(library, "create_scenario_from_ingest", _fake_build)

    stages = []
    results = library.scan_import_folder(provider=None, import_dir=imp, on_stage=stages.append)

    names = {fn: meta for fn, meta in results}
    assert "ignore.json" not in names                       # wrong type skipped
    assert names["good.md"]["title"] == "Built good"          # name = filename stem
    assert "error" in names["boom.txt"]                     # fail-open, batch lives
    # good.md moved to processed/, boom.txt left in place (build failed)
    assert (imp / "processed" / "good.md").is_file()
    assert not (imp / "good.md").exists()
    assert (imp / "boom.txt").is_file()
    assert any("Stage 1" in s for s in stages)
