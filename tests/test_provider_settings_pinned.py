"""Audit 2026-10 tier 2 #10: the provider refactor must not move a single setting.

`snapshot()` captures the EFFECTIVE settings of `CodexProvider` and `OpenAIProvider`
(models, effort ladder, base URL, endpoint, the headers built, the request body per
tier / deliberate / task, the schema-strict flag, the payload cap, describe()) under a
spread of environment configurations. `tests/golden/provider_settings.json` was
generated from the PRE-refactor code (`python tests/test_provider_settings_pinned.py
--write`), and this test asserts the refactored classes still produce it exactly.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden" / "provider_settings.json"

_ENV_KEYS = (
    "HOLODECK_CODEX_MODEL", "HOLODECK_CODEX_CHEAP_MODEL", "HOLODECK_CODEX_MAIN_EFFORT",
    "HOLODECK_CODEX_CHEAP_EFFORT", "HOLODECK_CODEX_BASE_URL",
    "HOLODECK_CODEX_REASONING_EFFORT", "CONSTRUCT_OPENAI_MODEL",
    "CONSTRUCT_OPENAI_CHEAP_MODEL", "CONSTRUCT_OPENAI_BASE_URL", "OPENAI_API_KEY",
)

#: env scenarios: every variable either provider reads, alone and all together.
_SCENARIOS: dict[str, dict[str, str]] = {
    "defaults": {},
    "codex_env_only": {
        "HOLODECK_CODEX_MODEL": "cx-main", "HOLODECK_CODEX_CHEAP_MODEL": "cx-cheap",
        "HOLODECK_CODEX_MAIN_EFFORT": "medium", "HOLODECK_CODEX_CHEAP_EFFORT": "minimal",
        "HOLODECK_CODEX_BASE_URL": "https://codex.example/api/"},
    "global_reasoning_override": {"HOLODECK_CODEX_REASONING_EFFORT": "minimal"},
    "openai_env_only": {
        "CONSTRUCT_OPENAI_MODEL": "oa-main", "CONSTRUCT_OPENAI_CHEAP_MODEL": "oa-mini",
        "CONSTRUCT_OPENAI_BASE_URL": "https://oa.example/", "OPENAI_API_KEY": " sk-env "},
    "everything": {
        "HOLODECK_CODEX_MODEL": "cx-main", "HOLODECK_CODEX_CHEAP_MODEL": "cx-cheap",
        "HOLODECK_CODEX_MAIN_EFFORT": "high", "HOLODECK_CODEX_CHEAP_EFFORT": "medium",
        "HOLODECK_CODEX_BASE_URL": "https://codex.example/api",
        "HOLODECK_CODEX_REASONING_EFFORT": "low",
        "CONSTRUCT_OPENAI_MODEL": "oa-main", "CONSTRUCT_OPENAI_CHEAP_MODEL": "oa-mini",
        "CONSTRUCT_OPENAI_BASE_URL": "https://oa.example", "OPENAI_API_KEY": "sk-all"},
    "non_gpt5_models": {
        "HOLODECK_CODEX_MODEL": "other-model", "CONSTRUCT_OPENAI_MODEL": "other-model"},
}

_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"},
                                             "opt": {"type": "integer"}},
           "required": ["answer"]}


def _provider_view(p) -> dict:
    """Everything observable about one provider instance's effective settings."""
    from construct.provider import ProviderError

    p._session_id = "sess-fixed"
    out: dict = {
        "describe": p.describe(),
        "main_model": p._main_model, "cheap_model": p._cheap_model,
        "main_effort": p._main_effort, "cheap_effort": p._cheap_effort,
        "base_url": p._base_url, "timeouts": p._timeouts,
        "endpoint_path": p._endpoint_path, "label": p._label,
        "auth_fix": p._auth_fix, "schema_strict": p._schema_strict,
    }
    try:
        auth = p._read_auth()
        out["auth"] = auth
        headers = p._headers(auth)
        out["headers"] = {k: v for k, v in headers.items() if k != "User-Agent"}
        out["user_agent_prefix"] = headers.get("User-Agent", "")[:3]
    except ProviderError as exc:
        out["auth_error"] = f"{type(exc).__name__}: {exc}"
    bodies = {}
    for tier in ("main", "cheap"):
        for deliberate in (False, True):
            for prompt in ("plain prompt", "⟦nar⟧\nnarrate", "⟦opn⟧\nopen"):
                key = f"{tier}|{'delib' if deliberate else 'fast'}|{prompt[:6]!r}"
                bodies[key] = p._body(prompt, _SCHEMA, tier, deliberate)
    out["bodies"] = bodies
    return out


def snapshot() -> dict:
    import construct.provider as prov

    nowhere = Path("/nonexistent/auth.json")
    snap: dict = {"payload_cap": prov.CODEX_PAYLOAD_CAP_BYTES,
                  "default_timeouts": prov.DEFAULT_TIMEOUTS,
                  "hard_bound": prov.HARD_BOUND_SECONDS}
    saved = {k: os.environ.get(k) for k in _ENV_KEYS + ("CONSTRUCT_PROVIDER",)}
    try:
        for name, env in _SCENARIOS.items():
            for k in _ENV_KEYS:
                os.environ.pop(k, None)
            os.environ.update(env)
            snap[f"{name}/codex"] = _provider_view(prov.CodexProvider(auth_path=nowhere))
            snap[f"{name}/openai"] = _provider_view(prov.OpenAIProvider())
        for k in _ENV_KEYS:
            os.environ.pop(k, None)
        # explicit kwargs beat env and defaults
        snap["kwargs/codex"] = _provider_view(prov.CodexProvider(
            auth_path=nowhere, main_model="m", cheap_model="c",
            base_url="https://k.example///", timeouts={"main": 5.0},
            main_effort="high", cheap_effort="medium"))
        snap["kwargs/openai"] = _provider_view(prov.OpenAIProvider(
            api_key="sk-kw", main_model="m", cheap_model="c",
            base_url="https://k.example///", timeouts={"cheap": 7.0},
            main_effort="high", cheap_effort="medium"))
        # the transport cap is enforced on BOTH wires (loudly, naming the wire label)
        caps = {}
        os.environ["OPENAI_API_KEY"] = "sk-cap"
        big = "x" * (prov.CODEX_PAYLOAD_CAP_BYTES + 1)
        for label, p in (("codex", prov.CodexProvider(auth_path=nowhere)),
                         ("openai", prov.OpenAIProvider())):
            try:
                asyncio.run(p.complete(big, _SCHEMA))
                caps[label] = "no error"
            except Exception as exc:  # noqa: BLE001
                caps[label] = f"{type(exc).__name__}: {str(exc)[:80]}"
        snap["cap_enforcement"] = caps
        # default_provider() selection seam
        sel = {}
        for choice in (None, "openai", "codex"):
            if choice is None:
                os.environ.pop("CONSTRUCT_PROVIDER", None)
            else:
                os.environ["CONSTRUCT_PROVIDER"] = choice
            sel[str(choice)] = type(prov.default_provider()).__name__
        snap["default_provider"] = sel
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return json.loads(json.dumps(snap, sort_keys=True, default=str))


def test_provider_effective_settings_unchanged_by_the_refactor():
    golden = json.loads(GOLDEN.read_text())
    now = snapshot()
    assert set(now) == set(golden)
    for key in golden:
        assert now[key] == golden[key], f"effective settings drifted at {key}"


def test_pinned_snapshot_actually_covers_both_providers_and_every_env():
    golden = json.loads(GOLDEN.read_text())
    assert len(golden) >= 15
    # the pins are not vacuous: the wires differ where they must, agree where they do
    assert golden["defaults/openai"]["base_url"] == "https://api.openai.com"
    assert golden["defaults/codex"]["base_url"] == "https://chatgpt.com/backend-api"
    assert golden["defaults/openai"]["schema_strict"] is True
    assert golden["defaults/codex"]["schema_strict"] is False


if __name__ == "__main__":
    if "--write" in sys.argv:
        import construct
        assert "agent-aa229fcb9b7a10066" in construct.__file__, construct.__file__
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(snapshot(), indent=1, sort_keys=True) + "\n")
        print("wrote", GOLDEN)
