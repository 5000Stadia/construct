"""The protagonist split's Construct-side cause (eval/14, build 1): the build's vouched merge
folds a fragment into the protagonist, and the engine served the closure under its
FIRST-SEEN member. When the fragment was seen first, the committed arc row read back as the
fragment while the beats watched `knows:<protagonist>`. The vouch now names the protagonist
as the representative (pattern-buffer IDENTITY-REPRESENTATIVE-V1)."""

from __future__ import annotations

from types import SimpleNamespace

from construct import game

ARC = SimpleNamespace(arc_id="arc:main", protagonist="person:elias")


def _world_with_fragment_seen_first(tmp_path):
    w = game._world(tmp_path / "v.world", "v", model=None)
    w.porcelain.ingest_structured([          # the fragment enters the log first
        {"entity": "person:elias_venn", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:elias_venn", "attribute": "name", "value": "Elias Venn"},
    ])
    w.porcelain.ingest_structured([
        {"entity": "person:elias", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:elias", "attribute": "name", "value": "Elias"},
    ])
    return w


def _commit_arc_row(w):
    w.porcelain.ingest_structured([{"entity": "arc:main", "attribute": "protagonist",
                                    "value": "person:elias"}], frame="plot:main",
                                  classify="rules")


def test_vouch_keeps_the_protagonist_as_the_survivor(tmp_path):
    w = _world_with_fragment_seen_first(tmp_path)
    try:
        assert game._vouch_merge(w, "person:elias", "person:elias_venn") == "person:elias"
        _commit_arc_row(w)
        assert game._protagonist_coherence(w, ARC) == "person:elias"   # the seal passes
    finally:
        w.close()


def test_without_a_named_survivor_the_fragment_wins(tmp_path):
    # Negative control: the engine's default election reproduces the split.
    w = _world_with_fragment_seen_first(tmp_path)
    try:
        w.porcelain.merge("person:elias", "person:elias_venn", evidence="control")
        _commit_arc_row(w)
        assert game._protagonist_coherence(w, ARC) == "person:elias_venn"
    finally:
        w.close()
