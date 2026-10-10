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


# --------------------------------------------------------------------------
# R20 probe find — a server-side stream error is passing, so it is retried
# --------------------------------------------------------------------------

def test_server_error_stream_is_transient_but_request_errors_are_not():
    from construct.provider import ProviderTransientError
    probe_event = {"type": "error", "error": {"type": "server_error", "code": "server_error",
                   "message": "An error occurred while processing your request. You can retry "
                              "your request."}}
    with pytest.raises(ProviderTransientError):
        _collect([probe_event])
    for code in ("rate_limit_exceeded", "overloaded"):
        with pytest.raises(ProviderTransientError):
            _collect([{"type": "error", "code": code, "message": "x"}])
    with pytest.raises(ProviderTransportError) as ei:
        _collect([{"type": "response.failed", "response": {
            "status": "failed", "error": {"code": "invalid_prompt", "message": "boom"}}}])
    assert not isinstance(ei.value, ProviderTransientError)


def test_one_server_error_is_retried_to_success(tmp_path, monkeypatch):
    """The probe turn's classify lost the player's move to a single server_error that was
    not retried. Now the bounded transient retry re-sends it and the call succeeds."""
    provider = CodexProvider(auth_path=tmp_path / "absent.json")
    calls = {"n": 0}
    schema = {"type": "object", "properties": {"prose": {"type": "string"}}, "required": ["prose"]}

    async def once(prompt, schema_, tier, deliberate=False):
        calls["n"] += 1
        events = ([{"type": "error", "error": {"code": "server_error", "message": "retry me"}}]
                  if calls["n"] == 1 else [_completed('{"prose": "ok"}')])
        return await CodexProvider._collect_sse_text(_FakeResp(events))

    provider._call_once = once
    import construct.provider as P
    real_sleep = asyncio.sleep
    monkeypatch.setattr(P.asyncio, "sleep", lambda *a, **k: real_sleep(0))
    assert asyncio.run(provider.complete("p", schema)) == {"prose": "ok"}
    assert calls["n"] == 2


@pytest.mark.parametrize("status,transient", [(503, True), (502, True), (429, True),
                                              (500, True), (400, False), (404, False)])
def test_http_status_transience(tmp_path, monkeypatch, status, transient):
    """R20 run 2: a narration call lost its turn to one `503: no healthy upstream` because only
    stream errors were transient. A 429/5xx status is the same passing trouble; a 4xx request
    error still fails fast."""
    import httpx
    from construct.provider import ProviderTransientError
    provider = CodexProvider(auth_path=tmp_path / "absent.json")
    monkeypatch.setattr(provider, "_read_auth", lambda: {})
    monkeypatch.setattr(provider, "_headers", lambda auth: {})
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kw: httpx.MockTransport(
        lambda request: httpx.Response(status, text="no healthy upstream")))
    schema = {"type": "object", "properties": {"prose": {"type": "string"}}, "required": ["prose"]}
    with pytest.raises(ProviderTransportError) as ei:
        asyncio.run(provider._call_once("p", schema, "main"))
    assert isinstance(ei.value, ProviderTransientError) is transient


# ---- the narrator fits the transport cap (R20 probe run 5, turn 10) ----------------------

def _story_briefing(turns: int, prose: str = "The rope creaks. " * 40) -> str:
    from construct.briefing import STORY_SO_FAR_HEADER
    beats = "\n\n".join(f"› You: move {i}\n\n{prose}turn {i} prose" for i in range(1, turns + 1))
    return f"WORLD LAWS: river law.\n\n{STORY_SO_FAR_HEADER}{beats}\n\nTHE TIME: night\n"


def test_drop_oldest_story_turn_removes_one_turn_and_keeps_the_last():
    from construct.briefing import drop_oldest_story_turn
    b = _story_briefing(3)
    once = drop_oldest_story_turn(b)
    assert "move 1" not in once and "turn 1 prose" not in once
    assert "move 2" in once and "move 3" in once
    assert once.startswith("WORLD LAWS") and once.endswith("THE TIME: night\n")
    last = drop_oldest_story_turn(drop_oldest_story_turn(b))
    assert "move 3" in last and drop_oldest_story_turn(last) is None   # the last turn stays
    assert drop_oldest_story_turn("no story here") is None


class _CappedStub(StubProvider):
    """A stub with the wire providers' cap surface: size = prompt length."""
    def __init__(self, cap: int):
        super().__init__([{"prose": "You hold the rope."}])
        self.payload_cap_bytes = cap

    def payload_bytes(self, prompt, schema, tier="main", deliberate=False):
        return len(prompt)


def test_narrate_drops_old_beats_until_the_request_fits_the_cap():
    from construct.briefing import drop_oldest_story_turn
    b = _story_briefing(8)
    p = _CappedStub(cap=0)
    p.payload_cap_bytes = 10**9
    cohorts.narrate(p, b, "person:hero", shrink=drop_oldest_story_turn)
    uncapped = len(p.calls[0][0])
    cap = uncapped - 1500                       # about two turns too big
    p = _CappedStub(cap=cap)
    out = cohorts.narrate(p, b, "person:hero", shrink=drop_oldest_story_turn)
    sent = p.calls[0][0]
    assert out == "You hold the rope." and len(sent) <= cap
    assert "move 8" in sent and "move 1" not in sent        # newest kept, oldest dropped
    assert "WORLD LAWS" in sent and "THE TIME: night" in sent


def test_narrate_without_a_shrink_step_sends_the_briefing_untouched():
    p = _CappedStub(cap=10)
    cohorts.narrate(p, _story_briefing(4), "person:hero")
    assert "move 1" in p.calls[0][0]                         # no shrink: no shaping


def test_codex_payload_bytes_is_the_measure_its_cap_guard_uses():
    p = CodexProvider()
    schema = cohorts.NARRATE_SCHEMA
    prompt = "“quoted” — " * 50
    assert p.payload_bytes(prompt, schema) == len(json.dumps(p._body(prompt, schema, "main")))
    assert p.payload_cap_bytes == 40 * 1024
