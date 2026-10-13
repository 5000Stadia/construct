"""The timing log: where a build's and a turn's wall-clock goes (founder 2026-10-13: "a
detailed log on what duration each step takes and why so we can consider optimizing time
to execute in the future - much can benefit from optimal model choice, batch runs and
parallelism").

Off unless `CONSTRUCT_TIMING_LOG` names a file. Then every model call, every build stage
and every turn appends one JSON line there:

- `{"ev": "call", ...}`: one per provider call. Its task code, or the engine's prompt
  head for an untagged engine call; tier, model, deliberate; prompt size; re-asks;
  transient retries; ok or error; `t0`/`t1`/`s`; the phase it ran in; the thread it ran
  on. Calls that overlap in time on different threads ran in parallel.
- `{"ev": "stage", "label": ...}`: a build stage began. Its duration is the gap to the
  next stage or to the build's end.
- `{"ev": "turn_start" | "turn_end", "turn": n, ...}`: a turn's bounds. turn_end carries
  the turn's own section timings (`TurnTrace.timings`).
- `{"ev": "mark", "label": ...}`: any other point worth a timestamp.

Every row carries `run` (one id per process), because the file is append-only and may
hold many runs. Within a run, consecutive stage rows with no turn between them are one
build: a build ends at the next turn, or, if it never reached one, at its run's last row.

`scripts/timing_report.py` turns the log into the tables. Recording is best-effort and
never raises into the caller: a timing line must never sink a build or a turn."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

ENV = "CONSTRUCT_TIMING_LOG"

_lock = threading.Lock()
_phase = ""  # the build stage or turn now running (process-wide; settle threads inherit it)
#: One id per process, on every row: the log is append-only and may hold many runs.
RUN = f"{os.getpid()}-{int(time.time())}"


def enabled() -> bool:
    return bool(os.environ.get(ENV))


def set_phase(label: str) -> None:
    global _phase
    _phase = label


def phase() -> str:
    return _phase


def record(ev: str, **fields: Any) -> None:
    """Append one event line, stamped with wall time, phase and thread."""
    path = os.environ.get(ENV)
    if not path:
        return
    row = {"ev": ev, "t": round(time.time(), 3), "run": RUN, "phase": _phase,
           "thread": threading.current_thread().name, **fields}
    try:
        line = json.dumps(row, default=str)
        with _lock, open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — a timing line never sinks the caller
        logger.debug("timing record failed", exc_info=True)


def stage(label: str) -> None:
    """A build progress line. A "Stage N · ..." line begins a stage, and its "Stage N"
    becomes the phase later calls are filed under; any other line ("…chunk 3/11
    extracted", "…viable") is a mark inside the current stage."""
    label = label.strip()
    if label.startswith("Stage"):
        set_phase(label.split(" · ", 1)[0])
        record("stage", label=label)
    else:
        record("mark", label=label)


def call_label(prompt: str, task: str) -> str:
    """The step a call belongs to: the host's 3-letter task code, or, for an untagged
    engine call, the first words of its prompt ('Extract world-state', 'Classify the')."""
    if task:
        return task
    head = " ".join(prompt[:60].split()[:3])
    return f"engine:{head}" if head else "engine:?"
