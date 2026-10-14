"""Shared test fixtures / suite-wide defaults."""

import pytest


@pytest.fixture(autouse=True)
def _scene_imagery_off(monkeypatch):
    """SCENE-IMAGERY is default-ON in production, but the broad suite drives real turn
    flows with stub providers — leave it OFF by default so a turn never spawns an
    image-render thread, calls the stub for an image prompt, or writes a manifest into
    worlds/. Tests that exercise imagery (test_imagery.py) opt back IN explicitly."""
    monkeypatch.setenv("CONSTRUCT_SCENE_IMAGES", "0")


@pytest.fixture(autouse=True)
def _build_library_off(monkeypatch):
    """SEEDING-LIBRARY-WIRING rule 10 / test 9: the existing build tests script today's
    per-chunk extraction, so they run with the rollback switch set. The library tests
    (tests/test_seeding_library.py) opt in with CONSTRUCT_BUILD_LIBRARY=1."""
    monkeypatch.setenv("CONSTRUCT_BUILD_LIBRARY", "0")
