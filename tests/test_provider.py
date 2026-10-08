import asyncio
import json
import os
from pathlib import Path

import pytest

from construct.provider import (
    CODEX_PAYLOAD_CAP_BYTES,
    CodexProvider,
    ProviderAuthError,
    ProviderTransientError,
    ProviderTransportError,
    SchemaViolation,
    StubProvider,
    engine_callable,
    force_strict_object_schema,
)

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


def test_stub_returns_and_logs():
    stub = StubProvider([{"answer": "yes"}])
    result = asyncio.run(stub.complete("q?", SCHEMA, tier="cheap"))
    assert result == {"answer": "yes"}
    assert stub.calls == [("q?", SCHEMA, "cheap")]


def test_stub_validates_schema():
    stub = StubProvider([{"wrong_key": 1}])
    with pytest.raises(SchemaViolation):
        asyncio.run(stub.complete("q?", SCHEMA))


def test_stub_exhausted_is_loud():
    stub = StubProvider()
    with pytest.raises(ProviderTransportError):
        asyncio.run(stub.complete("q?", SCHEMA))


def test_engine_callable_sync_bridge():
    stub = StubProvider([{"answer": "bound"}])
    call = engine_callable(stub, tier="main")
    assert call("prompt", SCHEMA) == {"answer": "bound"}
    assert stub.calls[0][2] == "main"


def test_force_strict_schema():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "nested": {"type": "object", "properties": {"x": {"type": "integer"}}},
            "items": {"type": "array", "items": {"type": "object",
                                                 "properties": {"y": {"type": "string"}}}},
        },
    }
    strict = force_strict_object_schema(schema)
    assert strict["additionalProperties"] is False
    assert sorted(strict["required"]) == ["items", "name", "nested"]
    assert strict["properties"]["nested"]["additionalProperties"] is False
    assert strict["properties"]["items"]["items"]["additionalProperties"] is False
    # original untouched
    assert "additionalProperties" not in schema


def test_force_strict_supplies_missing_types():
    # The engine's extract schema has a deliberately untyped `value`
    # leaf; the backend requires a type on every node.
    schema = {
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "value": {"description": "literal or entity id"},
                },
            }},
        },
    }
    strict = force_strict_object_schema(schema)
    value_node = strict["properties"]["items"]["items"]["properties"]["value"]
    assert value_node["type"] == ["string", "number", "boolean", "null"]


def test_codex_missing_auth_fails_fast(tmp_path: Path):
    provider = CodexProvider(auth_path=tmp_path / "absent.json")
    with pytest.raises(ProviderAuthError, match="codex login"):
        asyncio.run(provider.complete("q?", SCHEMA))


def test_codex_malformed_auth_fails_fast(tmp_path: Path):
    bad = tmp_path / "auth.json"
    bad.write_text(json.dumps({"tokens": {}}))
    provider = CodexProvider(auth_path=bad)
    with pytest.raises(ProviderAuthError):
        asyncio.run(provider.complete("q?", SCHEMA))


def test_codex_payload_cap_is_loud(tmp_path: Path):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(
        {"tokens": {"access_token": "t", "account_id": "a"}}))
    provider = CodexProvider(auth_path=auth)
    huge = "x" * (CODEX_PAYLOAD_CAP_BYTES + 1)
    with pytest.raises(ProviderTransportError, match="transport cap"):
        asyncio.run(provider.complete(huge, SCHEMA))


def test_codex_describe_names_no_secret():
    provider = CodexProvider(auth_path=Path("/nonexistent"))
    assert "codex/" in provider.describe()


def test_keepalive_socket_options_for_dead_peer_detection():
    # The SOURCE fix for the hung-call wedge (letters 059/060): TCP keepalive so
    # a dead/wedged peer surfaces as a socket error (~60s) instead of hanging,
    # rather than a process-killer recovery. SO_KEEPALIVE always; TCP_KEEP* tuning
    # on Linux. Must wire into httpx's public transport API (non-fiddly).
    import socket as _s
    import httpx
    opts = CodexProvider._keepalive_socket_options()
    assert (_s.SOL_SOCKET, _s.SO_KEEPALIVE, 1) in opts
    if hasattr(_s, "TCP_KEEPIDLE"):                     # Linux deploy target
        assert any(o[1] == _s.TCP_KEEPIDLE for o in opts)
    httpx.AsyncHTTPTransport(socket_options=opts)       # public API, must not raise


@pytest.mark.skipif(
    not (Path.home() / ".codex" / "auth.json").exists()
    or os.getenv("HOLODECK_LIVE_SMOKE") != "1",
    reason="live smoke test requires codex auth and HOLODECK_LIVE_SMOKE=1",
)
def test_codex_live_smoke():
    provider = CodexProvider()
    result = asyncio.run(provider.complete(
        "Reply with the single word 'ready' in the answer field.",
        SCHEMA, tier="cheap"))
    assert isinstance(result.get("answer"), str)


def test_transient_transport_failure_retries_then_succeeds(tmp_path):
    # Founder live build sunk by ONE dropped stream ('peer closed connection /
    # incomplete chunked read'): connection-level failures are transient —
    # retried bounded before surfacing.
    import asyncio
    provider = CodexProvider(auth_path=tmp_path / "absent.json")
    calls = {"n": 0}

    async def flaky(prompt, schema, tier, deliberate=False):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderTransientError("peer closed connection (incomplete chunked read)")
        return '{"ok": true}'

    provider._call_once = flaky
    orig_sleep = asyncio.sleep

    async def run():
        asyncio.sleep = lambda s: orig_sleep(0)  # no real backoff in tests
        try:
            return await provider.complete("p", {"type": "object",
                                                 "properties": {"ok": {"type": "boolean"}},
                                                 "required": ["ok"]})
        finally:
            asyncio.sleep = orig_sleep

    assert asyncio.run(run()) == {"ok": True}
    assert calls["n"] == 3          # two transient failures, third lands


def test_non_transient_transport_failure_fails_fast(tmp_path):
    # API-level errors keep fail-fast semantics — no retry.
    import asyncio
    import pytest
    provider = CodexProvider(auth_path=tmp_path / "absent.json")
    calls = {"n": 0}

    async def broken(prompt, schema, tier, deliberate=False):
        calls["n"] += 1
        raise ProviderTransportError("Codex API error (400): bad request")

    provider._call_once = broken
    with pytest.raises(ProviderTransportError):
        asyncio.run(provider.complete("p", {"type": "object", "properties": {},
                                            "required": []}))
    assert calls["n"] == 1          # no retry on a non-transient failure


# ---- strict-schema preflight (cr follow-up: the D2 live-only ABSENCE_SCHEMA
# defect — an array without `items` passed the stub and 400'd on the real API)

def test_lint_schema_rejects_array_without_items():
    import pytest
    from construct.provider import lint_schema
    with pytest.raises(ValueError, match="array without 'items'"):
        lint_schema({"type": "object", "properties": {
            "subjects": {"type": "array", "maxItems": 2}}})
    # nested inside items of a valid array — still caught, with the path
    with pytest.raises(ValueError, match=r"\$\.properties\.rows\.items"):
        lint_schema({"type": "object", "properties": {
            "rows": {"type": "array", "items": {"type": "array"}}}})


def test_lint_schema_rejects_required_not_in_properties():
    import pytest
    from construct.provider import lint_schema
    with pytest.raises(ValueError, match="missing from properties"):
        lint_schema({"type": "object", "properties": {"a": {"type": "string"}},
                     "required": ["a", "ghost"]})


def test_lint_schema_runs_on_the_stub_path_too():
    import pytest
    from construct.provider import StubProvider, complete_sync
    with pytest.raises(ValueError, match="array without 'items'"):
        complete_sync(StubProvider([{"x": []}]),
                      "p", {"type": "object", "properties": {
                          "x": {"type": "array"}}})


# ---- A1 provider swap: the shipped default is the metered API-key provider;
# subscription OAuth is an explicit opt-in (CONSTRUCT_PROVIDER=codex,
# personal-use context under OpenAI's Terms of Use).

def test_default_provider_is_openai(monkeypatch):
    from construct.provider import OpenAIProvider, default_provider
    monkeypatch.delenv("CONSTRUCT_PROVIDER", raising=False)
    assert type(default_provider()) is OpenAIProvider
    monkeypatch.setenv("CONSTRUCT_PROVIDER", "openai")
    assert type(default_provider()) is OpenAIProvider


def test_default_provider_codex_is_explicit_opt_in(monkeypatch):
    from construct.provider import default_provider
    monkeypatch.setenv("CONSTRUCT_PROVIDER", "codex")
    assert type(default_provider()) is CodexProvider


def test_default_provider_unknown_is_loud(monkeypatch):
    from construct.provider import ProviderError, default_provider
    monkeypatch.setenv("CONSTRUCT_PROVIDER", "anthropic")
    with pytest.raises(ProviderError, match="CONSTRUCT_PROVIDER"):
        default_provider()


def test_openai_missing_key_fails_fast(monkeypatch):
    from construct.provider import OpenAIProvider
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider()
    with pytest.raises(ProviderAuthError, match="OPENAI_API_KEY"):
        asyncio.run(provider.complete("q?", SCHEMA))


def test_openai_wire_is_api_key_shaped(monkeypatch):
    from construct.provider import OpenAIProvider
    monkeypatch.delenv("CONSTRUCT_OPENAI_BASE_URL", raising=False)
    provider = OpenAIProvider(api_key="sk-test")
    headers = provider._headers(provider._read_auth())
    assert headers["Authorization"] == "Bearer sk-test"
    # no subscription-shim identity headers on the metered wire
    assert "chatgpt-account-id" not in headers and "originator" not in headers
    assert provider._endpoint_path == "/v1/responses"
    assert provider._base_url == "https://api.openai.com"
    assert provider.describe().startswith("openai/")
    assert "sk-test" not in provider.describe()   # no secret in describe()


def test_openai_request_body_is_the_complete_strict_wire(monkeypatch):
    # cr A1 review: the metered wire must carry server-side Structured Outputs
    # adherence — text.format.strict=true — while the Codex consumer wire keeps
    # the Kernos-proven shape WITHOUT it. Oracle over the complete request body.
    from construct.provider import OpenAIProvider
    monkeypatch.delenv("CONSTRUCT_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("HOLODECK_CODEX_REASONING_EFFORT", raising=False)
    body = OpenAIProvider(api_key="sk-test")._body("the prompt", SCHEMA, "main")
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["name"] == "output"
    assert fmt["strict"] is True
    assert fmt["schema"] == force_strict_object_schema(SCHEMA)
    assert body["model"] == "gpt-5.5"
    assert body["store"] is False and body["stream"] is True
    assert body["input"] == [{"role": "user", "content": "the prompt"}]
    assert body["include"] == ["reasoning.encrypted_content"]
    assert "reasoning" in body and body["reasoning"]["effort"]
    assert body["prompt_cache_key"]
    # the Codex wire is DISTINCT: no strict key (proven shape preserved verbatim)
    codex_fmt = CodexProvider(auth_path=Path("/nonexistent"))._body(
        "the prompt", SCHEMA, "main")["text"]["format"]
    assert "strict" not in codex_fmt


def test_openai_key_fresh_read_from_env(monkeypatch):
    from construct.provider import OpenAIProvider
    provider = OpenAIProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "  sk-later  ")  # set AFTER construction
    assert provider._read_auth() == {"access": "sk-later"}


# ---- audit 2026-10 finding 9: engine tier routing matches pattern-buffer's prompt
# wording (`_CHEAP_ENGINE_PREFIXES`). If PB rewords those prompts, extraction would
# silently move to the main tier - slower, dearer, no error. This runs a tiny REAL
# pattern-buffer ingest through `engine_tier_dispatch` with a capturing provider.

class _TierRecorder(StubProvider):
    """Answers extraction / classification schemas and records (prompt, tier)."""

    async def complete(self, prompt, schema, *, tier="main", deliberate=False):
        self.calls.append((prompt, schema, tier))
        props = schema.get("properties", {})
        if "items" in props:
            return {"items": [
                {"entity": "person:cass", "attribute": "mood", "value": "wary"},
                {"entity": "obj:lamp", "attribute": "in", "value": "place:cellar",
                 "value_type": "entity"},
            ]}
        if "durability" in props:
            return {"durability": "STATE", "class_confidence": 0.8}
        if "verdicts" in props:
            return {"verdicts": []}
        raise ProviderTransportError("unexpected engine call")


@pytest.mark.parametrize("classify", ["inline", "batch"])
def test_pattern_buffer_extraction_and_classification_reach_the_cheap_tier(
        tmp_path, classify):
    from construct.game import _world
    from construct.provider import engine_tier_dispatch

    rec = _TierRecorder()
    world = _world(tmp_path / "drift.world", "drift", model=engine_tier_dispatch(rec),
                   stance="fiction", title="drift")
    world.porcelain.ingest("Cass held the lamp in the cellar, wary.", classify=classify)

    extraction = [c for c in rec.calls if "items" in c[1].get("properties", {})]
    classifying = [c for c in rec.calls
                   if "durability" in c[1].get("properties", {})
                   or "verdicts" in c[1].get("properties", {})]
    assert extraction, "pattern-buffer made no extraction call - the probe is vacuous"
    assert classifying, "pattern-buffer made no classification call - the probe is vacuous"
    # no prompt reworded away from the routing prefix: every one reached cheap
    assert {c[2] for c in extraction} == {"cheap"}, \
        "pattern-buffer reworded its extraction prompt; update _CHEAP_ENGINE_PREFIXES"
    assert {c[2] for c in classifying} == {"cheap"}, \
        "pattern-buffer reworded its classification prompt; update _CHEAP_ENGINE_PREFIXES"


# ---- audit 2026-10 tier 2 #10: the two Responses-wire providers are SIBLINGS

def test_codex_and_openai_providers_are_siblings_not_parent_child():
    from construct.provider import OpenAIProvider, _ResponsesWireProvider
    assert issubclass(CodexProvider, _ResponsesWireProvider)
    assert issubclass(OpenAIProvider, _ResponsesWireProvider)
    assert not issubclass(OpenAIProvider, CodexProvider)
    assert not issubclass(CodexProvider, OpenAIProvider)
    # the Codex-only credential path does not exist on the metered wire
    assert not hasattr(OpenAIProvider(api_key="k"), "_auth_path")


def test_empty_openai_model_env_does_not_leak_the_codex_variable(monkeypatch):
    from construct.provider import OpenAIProvider
    monkeypatch.setenv("CONSTRUCT_OPENAI_MODEL", "")
    monkeypatch.setenv("HOLODECK_CODEX_MODEL", "codex-only")
    assert OpenAIProvider(api_key="k")._main_model == "gpt-5.5"


def test_deliberate_calls_get_the_hard_bound_and_interactive_keep_their_tier_bound():
    # finding 8: `HARD if deliberate else min(tier_bound, HARD)` - pinned through the
    # timeout message the bound is reported in.
    import httpx
    from construct import provider as prov

    seen = []

    class _Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise httpx.ReadTimeout("slow")

        async def __aexit__(self, *a):
            return False

    async def run(deliberate, timeouts):
        p = prov.OpenAIProvider(api_key="k", timeouts=timeouts)
        orig = prov.asyncio.timeout
        prov.asyncio.timeout = lambda b: (seen.append(b), orig(b))[1]
        try:
            with pytest.raises(prov.ProviderTimeout):
                await p._call_once("p", SCHEMA, "main", deliberate)
        finally:
            prov.asyncio.timeout = orig

    real_client = httpx.AsyncClient
    httpx.AsyncClient = _Boom
    try:
        asyncio.run(run(False, {"main": 77.0}))
        asyncio.run(run(True, {"main": 77.0}))
        asyncio.run(run(False, {"main": 5000.0}))
    finally:
        httpx.AsyncClient = real_client
    assert seen == [77.0, prov.HARD_BOUND_SECONDS, prov.HARD_BOUND_SECONDS]


# ---- audit 2026-10 finding 7: one table drives the StubProvider's silent defaults

@pytest.mark.parametrize("task,key,expected", [
    ("csg", "specified", {"specified": True, "missing": [], "clarification": ""}),
    ("rmb", "stirs", {"stirs": False, "memory": "", "feeling": ""}),
    ("mcl", "claims", {"claims": [], "people": []}),
    ("law", "laws", {"reality_register": "secondary", "laws": []}),
    ("lwc", "verdicts", {"verdicts": []}),
])
def test_stub_silent_default_answers_without_consuming_the_queue(task, key, expected):
    from construct.provider import task_tag
    queued = {"answer": "kept"}
    stub = StubProvider([queued])
    got = asyncio.run(stub.complete(task_tag(task) + "p", {"type": "object"}))
    assert got == expected
    assert stub._queue == [queued]                      # the queue was not consumed
    got["extra"] = 1                                    # fresh copy: no shared mutable default
    assert asyncio.run(stub.complete(task_tag(task) + "p", {"type": "object"})) == expected
    # an EXPLICITLY stubbed call (queue head carries the signature key) is consumed instead
    explicit = {key: expected[key]}
    stub = StubProvider([explicit])
    assert asyncio.run(stub.complete(task_tag(task) + "p", {"type": "object"})) == explicit
    assert stub._queue == []


def test_engine_callable_tier_none_dispatches_by_prompt_shape():
    from construct.provider import engine_tier_dispatch
    stub = StubProvider([{"answer": "a"}, {"answer": "b"}, {"answer": "c"}])
    call = engine_callable(stub, tier=None)
    call("Extract world-state assertions from this", SCHEMA)
    call("Classify the lifetime of this fact", SCHEMA)
    call("Resolve the invention", SCHEMA)
    assert [c[2] for c in stub.calls] == ["cheap", "cheap", "main"]
    stub2 = StubProvider([{"answer": "a"}])
    engine_tier_dispatch(stub2)("Extract world-state x", SCHEMA)
    assert stub2.calls[0][2] == "cheap"

    async def inside_loop():
        with pytest.raises(RuntimeError, match="running event loop"):
            engine_tier_dispatch(StubProvider())("Extract world-state x", SCHEMA)
    asyncio.run(inside_loop())
