import asyncio
import json
import os
from pathlib import Path

import pytest

from construct.provider import (
    CODEX_PAYLOAD_CAP_BYTES,
    CodexProvider,
    ProviderAuthError,
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
