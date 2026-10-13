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

Every row carries `run` (the writing process) and `scope`: the build or session it belongs
to. One process can hold many sessions (the Discord bot keeps one per player, each
numbering its own turns from 1), so reports group by scope. The outermost build entry
point opens a build scope (`build_entry`); each Session keeps one session scope for its
turns and settles. Construct's
worker pools carry the scope into their threads (`submit_in_context`).

`scripts/timing_report.py` turns the log into the tables. Recording is best-effort and
never raises into the caller: a timing line must never sink a build or a turn."""

from __future__ import annotations

import contextvars
import functools
import json
import logging
import os
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

ENV = "CONSTRUCT_TIMING_LOG"

_lock = threading.Lock()
#: One id per process, on every row: the file writer. Reports group by `scope`, not this.
RUN = f"{os.getpid()}-{int(time.time())}"
#: The build or session this work belongs to (cr RED on c8904ad: one process can hold many
#: sessions, e.g. the Discord bot's one per player, each numbering its own turns from 1).
#: A context variable, so each thread and task carries its own; construct's worker pools
#: copy the submitting context into each worker (`submit_in_context`).
_scope: contextvars.ContextVar[str] = contextvars.ContextVar("timing_scope", default="")
#: The build stage or turn now running, within the scope.
_phase: contextvars.ContextVar[str] = contextvars.ContextVar("timing_phase", default="")


def enabled() -> bool:
    return bool(os.environ.get(ENV))


def set_phase(label: str) -> None:
    _phase.set(label)


def phase() -> str:
    return _phase.get()


def scope() -> str:
    return _scope.get()


def set_scope(kind: str, name: str = "") -> str:
    """Begin a new build or session scope in the current context and return its id."""
    sid = f"{kind}:{name}:{uuid.uuid4().hex[:8]}" if name else f"{kind}:{uuid.uuid4().hex[:8]}"
    _scope.set(sid)
    _phase.set("")
    return sid


def use_scope(sid: str) -> None:
    """Re-enter a known scope (a session's id, kept on the session object)."""
    _scope.set(sid)


def submit_in_context(pool, fn, *args, **kwargs):
    """`pool.submit` that runs `fn` in a copy of the caller's context, so a worker's calls
    keep the caller's scope and phase. One copy per task: a Context can't be entered by
    two threads at once."""
    return pool.submit(contextvars.copy_context().run, fn, *args, **kwargs)


def record(ev: str, **fields: Any) -> None:
    """Append one event line, stamped with wall time, phase and thread."""
    path = os.environ.get(ENV)
    if not path:
        return
    row = {"ev": ev, "t": round(time.time(), 3), "run": RUN, "scope": _scope.get(),
           "phase": _phase.get(),
           "thread": threading.current_thread().name, **fields}
    try:
        line = json.dumps(row, default=str)
        with _lock, open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — a timing line never sinks the caller
        logger.debug("timing record failed", exc_info=True)


def build_entry(fn):
    """Decorate a build entry point (ingest, interview, generated, continuation). The
    outermost one opens a build scope and restores the caller's scope and phase on
    return; a nested one (the generated build calls the ingest build) keeps the outer
    scope, so one user-visible build is one scope (cr RED on 7d095dd)."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _scope.get().startswith("build:"):
            return fn(*args, **kwargs)
        name = str(args[0]) if args else str(kwargs.get("name", ""))
        sid = f"build:{name}:{uuid.uuid4().hex[:8]}" if name else f"build:{uuid.uuid4().hex[:8]}"
        s_tok, p_tok = _scope.set(sid), _phase.set("")
        try:
            return fn(*args, **kwargs)
        finally:
            _scope.reset(s_tok)
            _phase.reset(p_tok)
    return wrapper


def stage(label: str) -> None:
    """A build progress line. A sub-step line ("…chunk 3/11 extracted", "…viable") is a
    mark inside the current stage. Any other line begins a stage: the "Stage N · ..."
    labels of a fresh build and the narrative labels of a continuation ("Dreaming up the
    next chapter") alike. Its head becomes the phase later calls are filed under."""
    label = label.strip()
    if label.startswith("…"):
        record("mark", label=label)
        return
    if not _scope.get().startswith("build:"):
        set_scope("build")  # progress outside any build entry point
    set_phase(label.split(" · ", 1)[0][:48])
    record("stage", label=label)


def call_label(prompt: str, task: str) -> str:
    """The step a call belongs to: the host's 3-letter task code, or, for an untagged
    engine call, the first words of its prompt ('Extract world-state', 'Classify the')."""
    if task:
        return task
    head = " ".join(prompt[:60].split()[:3])
    return f"engine:{head}" if head else "engine:?"
