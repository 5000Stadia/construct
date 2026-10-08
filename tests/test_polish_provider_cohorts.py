"""Regression tests for the provider/cohorts polish batch (audit BUG-1/2/3).

BUG-1  `_clean_prose` truncated ordinary English; the leak cases it was built for
       (a JSON wrapper / meta-reasoning tail spilled into the `prose` value) must
       still be stripped.
BUG-2  `_collect_sse_text` ignored error / failed / incomplete / refusal events.
BUG-3  the task tags "cast"/"adapt"/"dpol" did not match the 3-letter tag grammar,
       so `task_of()` returned '' for those cohorts.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re

import pytest

from construct import cohorts
from construct.cohorts import _clean_prose
from construct.provider import (
    CodexProvider,
    ProviderError,
    ProviderTransportError,
    StubProvider,
    task_of,
    task_tag,
)


# --------------------------------------------------------------------------
# BUG-2 — SSE stream events
# --------------------------------------------------------------------------

class _FakeResp:
    """Just enough of an httpx streaming response for `_collect_sse_text`."""

    def __init__(self, events: list, chunk: int = 0):
        self._raw = "".join(
            f"event: {e.get('type', '')}\ndata: {json.dumps(e)}\n\n" for e in events)
        self._chunk = chunk

    async def aiter_text(self):
        if not self._chunk:
            yield self._raw
            return
        for i in range(0, len(self._raw), self._chunk):
            yield self._raw[i:i + self._chunk]


def _collect(events: list, chunk: int = 0) -> str:
    return asyncio.run(CodexProvider._collect_sse_text(_FakeResp(events, chunk)))


def _delta(t: str) -> dict:
    return {"type": "response.output_text.delta", "delta": t}


def _completed(text: str) -> dict:
    return {"type": "response.completed", "response": {"status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text", "text": text}]}]}}


def test_sse_normal_streams_unchanged():
    assert _collect([_delta('{"a":'), _delta('1}')]) == '{"a":1}'
    assert _collect([_delta("x"), _completed('{"a":1}')]) == '{"a":1}'
    assert _collect([_completed('{"a":1}')], chunk=7) == '{"a":1}'


def test_sse_error_event_carries_code_and_message():
    ev = {"type": "error", "code": "rate_limit_exceeded",
          "message": "Rate limit reached for gpt-5.5", "param": None}
    with pytest.raises(ProviderTransportError) as ei:
        _collect([_delta("par"), ev])
    assert "rate_limit_exceeded" in str(ei.value)
    assert "Rate limit reached for gpt-5.5" in str(ei.value)


def test_sse_nested_error_event_shape():
    ev = {"type": "error", "error": {"code": "server_error", "message": "upstream blew up"}}
    with pytest.raises(ProviderTransportError, match="server_error.*upstream blew up"):
        _collect([ev])


def test_sse_response_failed_carries_server_reason():
    ev = {"type": "response.failed", "response": {
        "status": "failed", "error": {"code": "invalid_prompt", "message": "boom"}}}
    with pytest.raises(ProviderTransportError) as ei:
        _collect([ev])
    assert "boom" in str(ei.value) and "invalid_prompt" in str(ei.value)


def test_sse_incomplete_is_not_returned_as_complete():
    # Before the fix this returned the truncated JSON '{"prose": "abc'.
    ev = {"type": "response.incomplete", "response": {
        "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}}
    with pytest.raises(ProviderTransportError, match="max_output_tokens"):
        _collect([_delta('{"prose": "abc'), ev])


def test_sse_completed_with_incomplete_status_is_not_complete():
    ev = {"type": "response.completed", "response": {
        "status": "incomplete", "incomplete_details": {"reason": "content_filter"},
        "output": []}}
    with pytest.raises(ProviderTransportError, match="content_filter"):
        _collect([_delta('{"prose": "abc'), ev])


def test_sse_refusal_content_part_raises_with_refusal_text():
    ev = {"type": "response.completed", "response": {"status": "completed", "output": [
        {"type": "message", "content": [
            {"type": "refusal", "refusal": "I cannot help with that."}]}]}}
    with pytest.raises(ProviderTransportError, match="I cannot help with that") as ei:
        _collect([ev])
    # a refusal is named as such, not misreported as an empty stream
    assert "refused" in str(ei.value)
    assert "ended without output text" not in str(ei.value)


def test_sse_refusal_stream_events_raise():
    evs = [{"type": "response.refusal.delta", "delta": "I can"},
           {"type": "response.refusal.done", "refusal": "I cannot comply."}]
    with pytest.raises(ProviderTransportError, match="I cannot comply"):
        _collect(evs)


def test_incomplete_is_not_retried_or_reasked(tmp_path):
    """complete() must not pay twice for an error that cannot improve: no transient
    retry and no schema re-ask (the truncated-JSON re-ask was the old wrong
    diagnosis)."""
    provider = CodexProvider(auth_path=tmp_path / "absent.json")
    calls = {"n": 0}
    schema = {"type": "object", "properties": {"prose": {"type": "string"}},
              "required": ["prose"]}

    async def once(prompt, schema_, tier, deliberate=False):
        calls["n"] += 1
        return await CodexProvider._collect_sse_text(_FakeResp([
            _delta('{"prose": "abc'),
            {"type": "response.incomplete", "response": {
                "incomplete_details": {"reason": "max_output_tokens"}}}]))

    provider._call_once = once
    with pytest.raises(ProviderError):
        asyncio.run(provider.complete("p", schema))
    assert calls["n"] == 1


# --------------------------------------------------------------------------
# BUG-3 — task tags
# --------------------------------------------------------------------------

def test_task_tag_rejects_malformed_code():
    for bad in ("cast", "adapt", "dpol", "CA", "ca", "c1t", ""):
        with pytest.raises(ValueError):
            task_tag(bad)
    assert task_tag("cst") == "⟦cst⟧\n"


def test_every_cohort_task_code_is_visible_to_task_of():
    """Every `task="..."` literal in the host sources must survive the real tagger
    and be read back by task_of."""
    root = pathlib.Path(__file__).resolve().parent.parent / "construct"
    pat = re.compile(r"""task\s*=\s*["']([^"']+)["']""")
    codes: set[str] = set()
    for src in root.glob("*.py"):
        codes |= set(pat.findall(src.read_text()))
    assert len(codes) > 40                       # the sweep actually found the cohorts
    for code in sorted(codes):
        assert task_of(task_tag(code) + "body") == code, (
            f"task code {code!r} is invisible to task_of")
    assert {"cas", "adp", "dpl"} <= codes
    assert not {"cast", "adapt", "dpol"} & codes


def test_cohort_task_codes_are_unique_per_cohort():
    """Each cohort function owns one code; no two functions share one."""
    import inspect

    owner: dict[str, str] = {}
    pat = re.compile(r"""task\s*=\s*["']([a-z]{3})["']""")
    for name, fn in inspect.getmembers(cohorts, inspect.isfunction):
        if fn.__module__ != cohorts.__name__:
            continue
        for code in set(pat.findall(inspect.getsource(fn))):
            assert code not in owner, f"{code!r} used by {owner[code]} and {name}"
            owner[code] = name


def _captured_task(call) -> str:
    """Run a cohort against a capturing stub; return task_of of the prompt it sent."""
    stub = StubProvider([])           # empty queue: the call is recorded, then raises
    with pytest.raises(ProviderError):
        call(stub)
    assert stub.calls, "cohort never reached the provider"
    return task_of(stub.calls[0][0])


def test_author_cast_prompt_is_tagged():
    assert _captured_task(lambda p: cohorts.author_cast(
        p, "digest", "theme", "deduction", "Ada", ["person:bob"])) == "cas"


def test_adapt_decision_prompt_is_tagged():
    assert _captured_task(lambda p: cohorts.adapt_decision(
        p, "the cellar door", unfilled_pillars=[("pillar:a", "who did it")])) == "adp"


def test_classify_death_policy_prompt_is_tagged():
    assert _captured_task(lambda p: cohorts.classify_death_policy(
        p, "heist", "caper", "a vault job goes wrong")) == "dpl"


# --------------------------------------------------------------------------
# BUG-1 — _clean_prose
# --------------------------------------------------------------------------

@pytest.mark.parametrize("prose", [
    "The corridor — it ends with a sealed hatch, rust-red.",
    "You read the ledger. The final has a smudge.",
    "A brace {of pheasants} hangs by the door.",
    'He says, "Go." She nods at the {lantern}. The path — it ends with a gate.',
    'She whispers, "Stay close"',                 # closing dialogue quote survives
])
def test_clean_prose_keeps_ordinary_english(prose):
    assert _clean_prose(prose) == prose


# One test per leak the function was built for (git log -S, 70ae9a7 + live harness).
def test_clean_prose_still_strips_json_wrapper_leak_with_meta_tail():
    leaked = ('You study the desk; the ledger lies open and dry. should have its own '
              'log and seal."}    _久久爱=final elọpọ? Wait final schema expected JSON object')
    assert _clean_prose(leaked).endswith("log and seal.")


def test_clean_prose_still_strips_quote_brace_then_junk():
    assert _clean_prose('I see none on this strip."}-vesm JSON includes maybe invalid'
                        ).endswith("strip.")


def test_clean_prose_still_strips_smart_quote_brace_degenerate_tail():
    smart = ('“The only person I can place there that night is the doctor. I saw him enter '
             'alone. I heard no study bell after dinner.”} swineneＰＣＴＳＴＲ? 北京赛车开? '
             'Wait final has weird? Actually final JSON has extra? It ends with')
    out = _clean_prose(smart)
    assert out.endswith("after dinner.”")
    assert "swinene" not in out and "final JSON" not in out and "}" not in out


def test_clean_prose_still_strips_leaked_json_object_and_prose_key():
    assert _clean_prose('The door opens. {"prose": "again", "x": 1}') == "The door opens."
    assert _clean_prose('The door opens. "prose": "again') == "The door opens."


def test_clean_prose_still_strips_reserved_task_markers():
    assert _clean_prose("The door opens. ⟦nar⟧ leaked") == "The door opens."
    assert _clean_prose("The door opens. ⟧ leaked") == "The door opens."


def test_clean_prose_still_strips_meta_reasoning_without_braces():
    assert _clean_prose("The door opens. Wait final schema expected") == "The door opens."
