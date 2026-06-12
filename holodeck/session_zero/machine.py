"""The session-zero stage machine (SESSION-ZERO §1, §3).

Pure logic: no I/O, no model calls, no engine. Checkpoints are plain
dicts so the post-freeze adapter can persist them to `session:main` and
reconstruct the machine from the persisted rows (resumability — an
interrupted interview loses nothing).
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class Stage(enum.Enum):
    GREET = "greet"
    PROVIDER = "provider"
    PATH = "path"
    WORLD = "world"
    SAFETY = "safety"
    ENTRY = "entry"
    DESTINATION = "destination"
    LINT = "lint"
    START = "start"


ORDER: tuple[Stage, ...] = (
    Stage.GREET, Stage.PROVIDER, Stage.PATH, Stage.WORLD, Stage.SAFETY,
    Stage.ENTRY, Stage.DESTINATION, Stage.LINT, Stage.START,
)


class Path(enum.Enum):
    INGEST = "A"
    LIVE = "B"


#: The which-sections-are-known switch (SESSION-ZERO §2): sections the
#: WORLD stage arrives with pre-filled, per path.
PREFILLED_SECTIONS: dict[Path, frozenset[str]] = {
    Path.INGEST: frozenset({"charter", "world_content", "characters"}),
    Path.LIVE: frozenset(),
}


class StageError(Exception):
    """Out-of-order or inconsistent stage transition."""


@dataclass
class Checkpoint:
    stage: Stage
    payload: dict = field(default_factory=dict)


class SessionZeroMachine:
    """Enforces stage order; replays persisted checkpoints for resume."""

    def __init__(self, checkpoints: list[dict] | None = None) -> None:
        self._done: list[Checkpoint] = []
        self._path: Path | None = None
        for row in checkpoints or []:
            self.complete(Stage(row["stage"]), dict(row.get("payload", {})))

    # -- state ----------------------------------------------------------

    @property
    def current_stage(self) -> Stage | None:
        """The next stage to run; None when the interview is complete."""
        if len(self._done) >= len(ORDER):
            return None
        return ORDER[len(self._done)]

    @property
    def is_complete(self) -> bool:
        return self.current_stage is None

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def prefilled_sections(self) -> frozenset[str]:
        if self._path is None:
            raise StageError("path not chosen yet")
        return PREFILLED_SECTIONS[self._path]

    def checkpoints(self) -> list[dict]:
        """Serializable form, ready for `session:main` persistence."""
        return [{"stage": c.stage.value, "payload": dict(c.payload)} for c in self._done]

    # -- transitions ------------------------------------------------------

    def complete(self, stage: Stage, payload: dict | None = None) -> None:
        expected = self.current_stage
        if expected is None:
            raise StageError("session zero already complete")
        if stage is not expected:
            raise StageError(f"expected stage {expected.value!r}, got {stage.value!r}")
        payload = dict(payload or {})
        if stage is Stage.PATH:
            try:
                self._path = Path(payload["path"])
            except (KeyError, ValueError) as exc:
                raise StageError("PATH completion requires payload {'path': 'A'|'B'}") from exc
        if stage is Stage.GREET and "launch" in payload:
            # An existing scenario was chosen (letters 012/013): the
            # wizard is skipped entirely. "resume" opens the scenario's
            # single playthrough slot at its head; "fresh" recopies the
            # pristine scenario over the slot. The copy itself is the
            # launcher's job; the machine records the choice.
            if payload["launch"] not in ("resume", "fresh") or "scenario" not in payload:
                raise StageError(
                    "GREET launch requires payload "
                    "{'launch': 'resume'|'fresh', 'scenario': <id>}")
            self._done = [Checkpoint(s, {"skipped_by_launch": True}) for s in ORDER[:-1]]
            self._done.append(Checkpoint(Stage.START, payload))
            logger.info("session zero: launch=%s, wizard skipped", payload["launch"])
            return
        self._done.append(Checkpoint(stage, payload))
        logger.info("session zero: stage %s complete", stage.value)
