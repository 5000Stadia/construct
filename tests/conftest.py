"""Shared test fixtures / suite-wide defaults."""

import pytest


@pytest.fixture(autouse=True)
def _scene_imagery_off(monkeypatch):
    """SCENE-IMAGERY is default-ON in production, but the broad suite drives real turn
    flows with stub providers — leave it OFF by default so a turn never spawns an
    image-render thread, calls the stub for an image prompt, or writes a manifest into
    worlds/. Tests that exercise imagery (test_imagery.py) opt back IN explicitly."""
    monkeypatch.setenv("CONSTRUCT_SCENE_IMAGES", "0")
