"""The arc layer as pure logic (docs/design/ARC-LAYER.md).

No engine imports anywhere in this package: evaluation runs against the
narrow read-only `WorldReads` protocol (`holodeck.arc.conditions`), which
the porcelain adapter implements at integration time and test fixtures
implement as static folds.
"""

from holodeck.arc.truth import Truth
from holodeck.arc.conditions import (
    UNRESOLVED,
    EventRow,
    WorldReads,
    PacingCounters,
    evaluate,
)
from holodeck.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase
from holodeck.arc.lint import LintFinding, lint_arc, lint_post_repair

__all__ = [
    "Truth", "UNRESOLVED", "EventRow", "WorldReads", "PacingCounters",
    "evaluate", "Arc", "Beat", "Clock", "ConclusionShape", "Phase",
    "LintFinding", "lint_arc", "lint_post_repair",
]
