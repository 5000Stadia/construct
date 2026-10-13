"""The timing log (founder 2026-10-13): every model call, build stage and turn, as JSON
lines, when CONSTRUCT_TIMING_LOG is set; nothing at all when it isn't."""

import asyncio
import json

import pytest

from construct import game, timing
from construct.provider import CodexProvider, ProviderTransientError, task_tag
from scripts.timing_report import load, report

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / "timing.jsonl"
    monkeypatch.setenv(timing.ENV, str(path))
    timing.set_phase("")
    return path


def _provider(tmp_path, answers):
    p = CodexProvider(auth_path=tmp_path / "absent.json")

    async def once(prompt, schema, tier, deliberate=False):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    p._call_once = once
    return p


def _no_backoff(monkeypatch):
    orig = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda s: orig(0))


def test_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv(timing.ENV, raising=False)
    p = _provider(tmp_path, ['{"ok": true}'])
    assert asyncio.run(p.complete("x", SCHEMA)) == {"ok": True}
    timing.record("mark", label="nothing")
    assert list(tmp_path.iterdir()) == []


def test_a_call_is_logged_with_its_step_retries_and_reasks(tmp_path, log, monkeypatch):
    _no_backoff(monkeypatch)
    p = _provider(tmp_path, [ProviderTransientError("peer closed"), '{"nope": 1}',
                             '{"ok": true}'])
    timing.set_phase("turn 3")
    asyncio.run(p.complete(task_tag("nar") + "narrate this", SCHEMA, tier="main"))
    (row,) = _rows(log)
    assert row["ev"] == "call" and row["step"] == "nar" and row["phase"] == "turn 3"
    assert row["tier"] == "main" and row["model"] == p._model_for("main")
    assert row["retries"] == 1 and row["reasks"] == 1 and row["ok"] is True
    assert row["t1"] >= row["t0"] and row["s"] >= 0


def test_an_engine_call_is_named_by_its_prompt_head(tmp_path, log):
    p = _provider(tmp_path, ['{"ok": true}'])
    asyncio.run(p.complete("Extract world-state assertions from this prose", SCHEMA,
                           tier="cheap"))
    assert _rows(log)[0]["step"] == "engine:Extract world-state assertions"


def test_a_failed_call_is_logged_and_still_raises(tmp_path, log):
    from construct.provider import ProviderTransportError
    p = _provider(tmp_path, [ProviderTransportError("Codex API error (400)")])
    with pytest.raises(ProviderTransportError):
        asyncio.run(p.complete("x", SCHEMA))
    (row,) = _rows(log)
    assert row["ok"] is False and "400" in row["error"]


def test_build_progress_marks_stages_and_sets_the_phase(log):
    game._emit(None, "Stage 2 · Reconciling identity · coreference")
    game._emit(None, "   …chunk 3/11 extracted")
    rows = _rows(log)
    assert [r["ev"] for r in rows] == ["stage", "mark"]
    assert timing.phase() == "Stage 2" and rows[1]["phase"] == "Stage 2"


def test_the_report_reads_stages_steps_and_turns(log):
    rows = [
        {"ev": "stage", "t": 0.0, "label": "Stage 1 · Ingesting"},
        {"ev": "call", "t": 1, "t0": 1.0, "t1": 11.0, "s": 10.0, "step": "engine:Extract",
         "tier": "cheap", "model": "m", "phase": "Stage 1", "ok": True},
        {"ev": "call", "t": 2, "t0": 2.0, "t1": 12.0, "s": 10.0, "step": "engine:Extract",
         "tier": "cheap", "model": "m", "phase": "Stage 1", "ok": True},
        {"ev": "stage", "t": 20.0, "label": "Stage 2 · Reconciling"},
        {"ev": "turn_start", "t": 30.0, "turn": 1, "phase": "turn 1"},
        {"ev": "call", "t": 31, "t0": 31.0, "t1": 51.0, "s": 20.0, "step": "nar",
         "tier": "main", "model": "M", "phase": "turn 1", "ok": True},
        {"ev": "turn_end", "t": 52.0, "turn": 1, "ok": True},
        {"ev": "settle", "t": 53.0, "t0": 52.5, "s": 5.0},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    md = report(load(str(log)))
    assert "| Stage 1 · Ingesting | 20 | 2 | 20 | 1.0 |" in md
    assert "| engine:Extract | cheap / m | 2 | 20 |" in md
    assert "| 1 | 22 | 1 | 20 |" in md and md.rstrip().endswith("|")
    assert "| Stage 1 | 2 | 2 |" in md          # the two extractions overlapped


def _call(scope, t0, t1, step="engine:Extract"):
    return {"ev": "call", "run": "P", "scope": scope, "t": t0, "t0": t0, "t1": t1,
            "s": t1 - t0, "step": step, "tier": "cheap", "model": "m", "phase": "", "ok": True}


def _ev(ev, scope, t, **kw):
    return {"ev": ev, "run": "P", "scope": scope, "t": t, **kw}


def test_the_report_splits_builds_and_sessions_in_one_process(log):
    """cr RED on 8162287 and c8904ad: one append-only file, one process, many builds and
    sessions. Two sessions both have a turn 1, and they overlap; a build in one scope is
    not ended by a turn in another; an unfinished build ends at its own last row."""
    rows = [
        _ev("stage", "build:a", 0.0, label="Stage 1 · build a"),
        _call("build:a", 1.0, 5.0),
        _ev("stage", "build:b", 2.0, label="Stage 1 · build b"),
        _ev("turn_start", "session:x", 3.0, turn=1),          # x's turn 1 starts mid-build
        _call("build:a", 6.0, 9.0),
        _call("session:x", 4.0, 7.0, step="nar"),
        _ev("turn_start", "session:y", 5.0, turn=1),          # y's turn 1 overlaps x's
        _call("session:y", 5.5, 8.5, step="cls"),
        _ev("turn_end", "session:x", 10.0, turn=1, ok=True),
        _ev("turn_end", "session:y", 12.0, turn=1, ok=True),
        _ev("settle", "session:x", 10.5, t0=10.2, s=2.0),
        _call("build:b", 20.0, 50.0),
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    md = report(load(str(log)))
    # build a is not cut short by session x's turn: it runs to its own last call (t=9)
    assert "### Build 1 (build:a)" in md and "| Stage 1 · build a | 9 | 2 | 7 |" in md
    assert "### Build 2 (build:b)" in md and "| Stage 1 · build b | 48 | 1 | 30 |" in md
    # two independent turn 1s, each with only its own call; x's settle stays with x
    assert "| session:x / 1 | 7 | 1 | 3 | 0.4 | nar 3 | 2 |" in md
    assert "| session:y / 1 | 7 | 1 | 3 |" in md


def test_scope_follows_the_context_into_worker_threads(log):
    from concurrent.futures import ThreadPoolExecutor
    sid = timing.set_scope("session", "w/p")
    timing.set_phase("turn 4")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [timing.submit_in_context(pool, timing.record, "mark", label=str(i))
                for i in range(2)]
        [f.result() for f in futs]
    rows = _rows(log)
    assert {r["scope"] for r in rows} == {sid} and {r["phase"] for r in rows} == {"turn 4"}


def test_every_row_carries_the_run_and_scope(log):
    sid = timing.set_scope("build", "w")
    timing.record("mark", label="x")
    row = _rows(log)[0]
    assert row["run"] == timing.RUN and row["scope"] == sid
