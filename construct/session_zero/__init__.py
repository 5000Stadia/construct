"""Session zero as pure logic (docs/design/SESSION-ZERO.md).

The stage state machine only — checkpointed, resumable, path-aware. The
interviewer prompts and engine writes arrive post-freeze.
"""

from construct.session_zero.machine import Path, SessionZeroMachine, Stage, StageError

__all__ = ["Path", "SessionZeroMachine", "Stage", "StageError"]
