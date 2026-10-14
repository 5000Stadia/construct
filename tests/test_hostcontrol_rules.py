"""Host-control writes are classified by the engine's fixed rules, never its model.

`plot:` / `session:` rows (arc status, phase, lifecycle, cursors, receipts, the transcript)
are host control data with last-write-wins semantics. Under the default inline classifier
the engine's model judged them, and a CONSTITUTIVE verdict makes a mutable row fold to its
EARLIEST value (the constitutive-fold trap, PB 066). `classify="rules"` runs the engine's
deterministic guardrails and leaves the rest STATE, with zero model calls
(docs/design/AUDIT-2026-10-ELEGANCE.md, "pattern-buffer's answer on the seam"; arc F13).

Three layers:
  * a static guard over every write call in `construct/` (no new host-control write can
    slip back to a model-backed mode),
  * the host-control writers driven on a real World: zero classify calls, and STATE even
    when the model would say otherwise,
  * one full turn: no host-control row is ever put in front of the classifier model.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from patternbuffer import World
from patternbuffer.model import TASK_CLASSIFY, TASK_CLASSIFY_BATCH
from patternbuffer.testing import StubModel

from construct.adapter import PorcelainWorldReads
from construct.arc import adapt, drift, executor, generator
from construct.provider import StubProvider
from tests.test_integration import PLAYER, make_arc, run_turn, seed_arc, world  # noqa: F401

PKG = Path(__file__).resolve().parent.parent / "construct"

_HOST_FRAME_NAMES = {"PLOT", "SESSION", "_SESSION_FRAME"}
_HOST_FRAME_PREFIXES = ("plot:", "session:")
#: helpers that stamp `frame="plot:main"` on every row they return, so a call that
#: carries them writes host-control rows even without a `frame=` argument
_PLOT_STAMPERS = {"arc_to_items", "index_items", "portfolio_items", "portfolio_add_items",
                  "beat_to_items"}
_MODEL_FREE = {"rules", "defer"}


def _host_control_calls():
    """Yield (relpath, function, call-node, classify-kwarg-or-None) for every
    `ingest_structured` / `commit_set` call that writes host-control frames."""
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text())
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("ingest_structured", "commit_set")):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            frame = kw.get("frame")
            host = False
            if isinstance(frame, ast.Name) and frame.id in _HOST_FRAME_NAMES:
                host = True
            elif (isinstance(frame, ast.Constant) and isinstance(frame.value, str)
                  and frame.value.startswith(_HOST_FRAME_PREFIXES)):
                host = True
            else:
                for arg in node.args:
                    for sub in ast.walk(arg):
                        if isinstance(sub, ast.Call):
                            f = sub.func
                            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                            if name in _PLOT_STAMPERS:
                                host = True
            if not host:
                continue
            fn = node
            while fn in parents and not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = parents[fn]
            fname = fn.name if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) else "<module>"
            yield path.relative_to(PKG).as_posix(), fname, node, kw.get("classify")


def test_every_host_control_write_is_model_free():
    """No `plot:*` / `session:*` write may ride a model-backed classifier. `commit_set`
    is model-free by the porcelain default (it refuses anything else), so an omitted
    `classify=` is fine there; `ingest_structured` must say `rules` (or `defer`)."""
    bad, seen = [], 0
    for rel, fname, call, classify in _host_control_calls():
        seen += 1
        if call.func.attr == "commit_set" and classify is None:
            continue
        ok = isinstance(classify, ast.Constant) and classify.value in _MODEL_FREE
        if not ok:
            bad.append(f"{rel}:{call.lineno} in {fname}() classify="
                       f"{ast.unparse(classify) if classify is not None else 'default(inline)'}")
    assert seen >= 40, f"the scan found only {seen} host-control writes; the guard is blind"
    assert not bad, "host-control writes on a model-backed classifier:\n" + "\n".join(bad)


# --- the writers on a real World ------------------------------------------------------------

def _classify_calls(w) -> list[tuple[str, dict]]:
    return [(p, s) for p, s in w._stub.calls if s.get("title") in (TASK_CLASSIFY,
                                                                   TASK_CLASSIFY_BATCH)]


def _listed(prompt: str) -> set[tuple[str, str]]:
    """The (entity, attribute) pairs a classify prompt puts in front of the model."""
    pairs = {(m.group(1), m.group(2))
             for m in re.finditer(r"^\s*\d+\.\s+(\S+) · (\S+) ·", prompt, re.M)}
    single = re.search(r"Subject: (\S+)\nAttribute: (\S+)\n", prompt)
    if single:
        pairs.add((single.group(1), single.group(2)))
    return pairs


def _drive_writers(w, arc) -> None:
    """Representative host-control writes: drift receipts, lifecycle, generator receipts,
    adapt ledger, the resolution deck."""
    from construct import resolution
    drift.mark_nudge(w, "thread:a", 120.0, 2)
    drift.mark_relocation(w, "beat:discover", "place:old", "place:new", 2)
    drift.mark_moment(w, "beat:discover", "event:moment_x", 3)
    drift.record_absence_declined(w, 3, "beat:discover", "no cast")
    drift.mark_repair(w, "arc:main", "beat:discover", "beat:new", "replace", 4)
    executor.set_lifecycle(w, arc, "won", 5)
    generator._mark_development(w, 300.0, 6)
    generator._record_decline(w, 6, "cap reached")
    generator._record_attempt(w, arc, "arc:main", 1, "fp123", 6)
    adapt._record(w, turn=7, lane="genuine", pillar_id="pillar:x", reason="r", new_used=1)
    resolution.draw_tier(PorcelainWorldReads(w), w.porcelain, seed_source=7)


def test_host_control_writers_make_zero_classify_model_calls(world):  # noqa: F811
    arc = make_arc()
    seed_arc(world, arc)
    before = len(_classify_calls(world))
    _drive_writers(world, arc)
    assert len(_classify_calls(world)) == before, (
        "a host-control write reached the durability classifier model")


def test_host_control_durability_is_model_independent(tmp_path):
    """Even a model that calls everything CONSTITUTIVE (the worst case: a mutable row would
    then fold to its earliest value) leaves host-control rows STATE, with zero model calls."""
    def fallback(prompt, schema):
        if schema.get("title") == TASK_CLASSIFY_BATCH:
            return {"verdicts": [
                {"index": int(i), "durability": "CONSTITUTIVE", "class_confidence": 0.9}
                for i in re.findall(r"^\s*(\d+)\.\s", prompt, re.M)]}
        if schema.get("title") == TASK_CLASSIFY:
            return {"durability": "CONSTITUTIVE", "class_confidence": 0.9}
        return {"items": []}

    stub = StubModel(fallback=fallback)
    w = World(tmp_path / "h.world", world_id="w:h", model=stub, stance="fiction", title="H")
    w._stub = stub
    try:
        w.ingestor.cursor.advance(1.0)
        w.ingest_structured([
            {"entity": "place:study", "attribute": "kind", "value": "room", "timeless": True},
            {"entity": PLAYER, "attribute": "kind", "value": "person", "timeless": True},
        ])
        arc = make_arc()
        before = len(_classify_calls(w))
        _drive_writers(w, arc)
        assert len(_classify_calls(w)) == before

        host = [r for r in w.buffer.all_rows() if r.frame.startswith(_HOST_FRAME_PREFIXES)]
        assert host, "the writers wrote nothing to the host frames"
        # rules: the guardrails (event:/caused_by -> EVENT; the engine's structural
        # attributes such as `kind` -> CONSTITUTIVE, identical under any model) or the STATE
        # default. A model verdict never lands.
        for r in host:
            got = w.classifier.get(r.id).durability
            want = ({"STATE", "EVENT", "CONSTITUTIVE"} if r.attribute == "kind"
                    else {"STATE", "EVENT"})
            assert got in want, (r.entity, r.attribute, got)
        # the mutable rows the constitutive-fold trap would freeze are STATE, and the LATEST wins
        assert w.porcelain.state(arc.arc_id, "lifecycle", frame="plot:main")["fact"]["value"] == "won"
        for r in host:
            if r.attribute in ("lifecycle", "last_nudge_min", "cursor", "done"):
                assert w.classifier.get(r.id).durability == "STATE", (r.entity, r.attribute)
    finally:
        w.close()


# --- a whole turn -------------------------------------------------------------------------

def test_a_turn_never_shows_the_classifier_a_host_control_row(world):  # noqa: F811
    """A full turn (classify -> narrate -> settle) writes `session:` bookkeeping (turn receipt,
    archive, transcript, memory, ...) and may touch `plot:`. Whatever else the classifier model
    is asked about (canon rows), it is never asked about a host-control row."""
    arc = make_arc()
    seed_arc(world, arc)
    base = len(_classify_calls(world))
    world._extractions.append({"items": [
        {"entity": "fact:secret", "attribute": "culprit", "value": "person:rival"}]})
    world._extractions.append({"items": []})
    provider = StubProvider([
        {"kind": "action", "claims_are": "act", "moves_to": "", "requires": [], "needs_test": False,
         "uncertain_of": ""},
        {"prose": "You find the culprit's name in the ledger."},
    ])
    result = run_turn(world, arc, provider, "I read the ledger.", turn=1)
    assert result.prose

    host = [r for r in world.buffer.all_rows() if r.frame.startswith(_HOST_FRAME_PREFIXES)]
    host_keys = {(r.entity, r.attribute) for r in host if not r.entity.startswith("event:")}
    assert {"session:transcript", "arch:turn_1"} & {e for e, _ in host_keys}, \
        "the turn wrote no host-control bookkeeping; the test is blind"
    shown = set()
    for prompt, _schema in _classify_calls(world)[base:]:
        shown |= _listed(prompt)
    leaked = shown & host_keys
    assert not leaked, f"host-control rows were put to the classifier model: {sorted(leaked)}"
