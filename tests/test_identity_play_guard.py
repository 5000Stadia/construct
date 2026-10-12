"""R34 P1 (gate gc53c58, monitor n126701): identity is decided only while a world is built,
never during play. A live turn must not rewrite who is who, so the engine's identity verbs
(merge, confirm, reject, retype, reconcile, adjudicate_deferred) are called only from the
build module, `construct/game.py`. This scan keeps every other module free of them."""

from __future__ import annotations

import ast
from pathlib import Path

IDENTITY_VERBS = {"merge", "confirm", "reject", "retype", "reconcile", "adjudicate_deferred"}
BUILD_MODULE = Path("construct/game.py")


ROOT = Path(__file__).resolve().parent.parent


def _identity_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return [f"{path.relative_to(ROOT)}:{node.lineno} .{node.func.attr}()"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in IDENTITY_VERBS]


def test_no_identity_verb_outside_the_build_module():
    hits = [hit for path in sorted((ROOT / "construct").rglob("*.py"))
            if path.relative_to(ROOT) != BUILD_MODULE
            for hit in _identity_calls(path)]
    assert not hits, f"identity verbs called outside the build: {hits}"


def test_the_scan_sees_the_build_module_s_own_merge():
    # The negative control: the scan does find the vouch's merge in the build module.
    assert any(h.endswith(".merge()") for h in _identity_calls(ROOT / BUILD_MODULE))
