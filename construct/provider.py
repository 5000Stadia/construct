"""The provider interface (docs/design/PROVIDER-INTERFACE.md).

Every model call in Holodeck routes through `Provider.complete(prompt,
schema, *, tier)`. Schema enforcement lives HERE — no caller ever
re-validates. The provider never decides policy: it raises typed errors
with diagnostics preserved; cohorts fail open, the render fails loud,
session zero fails fast.

Nothing downstream of this module may name a vendor, model id, endpoint,
or credential. Downstream code knows "main" and "cheap", nothing else.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

Tier = Literal["main", "cheap"]

#: House standard (Kernos letter 021): no unbounded external calls.
#: cheap covers chunked extraction (large structured outputs on the
#: mini model); main covers narration/invention.
DEFAULT_TIMEOUTS: dict[str, float] = {"main": 300.0, "cheap": 180.0}
HARD_BOUND_SECONDS = 600.0

#: The transport threshold that tips the Codex consumer backend into
#: mid-stream timeouts (Kernos production finding). Enforced loudly.
CODEX_PAYLOAD_CAP_BYTES = 40 * 1024


class ProviderError(Exception):
    """Base. Never silently absorbed; diagnostics preserved."""


class ProviderAuthError(ProviderError):
    """Credential problem; message names the fix (e.g. `codex login`)."""


class ProviderTimeout(ProviderError):
    """The per-call bound tripped."""


class ProviderTransportError(ProviderError):
    """HTTP / wire / payload failure; raw tail preserved in the message."""


class SchemaViolation(ProviderError):
    """Output failed schema validation after the bounded re-ask."""


def validate_against_schema(payload: dict, schema: dict) -> None:
    """Raise SchemaViolation unless payload validates. jsonschema does
    the work; the wrapper exists so callers see our typed error."""
    import jsonschema

    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as exc:
        raise SchemaViolation(f"output violates schema: {exc.message}") from exc


class Provider(ABC):
    """One model call: structured JSON out, schema-enforced.

    `deliberate=True` asks for deeper reasoning (slow, for planning-class
    work like arc authoring); the default is fast — narration-class work
    needs a good model, not deep deliberation (letter 022, finding C)."""

    @abstractmethod
    async def complete(self, prompt: str, schema: dict, *, tier: Tier = "main",
                       deliberate: bool = False) -> dict: ...

    @abstractmethod
    def describe(self) -> str:
        """For receipts: which mind produced which call."""


ModelCallable = Callable[[str, dict], dict]


def complete_sync(provider: Provider, prompt: str, schema: dict, *, tier: Tier = "main",
                  deliberate: bool = False) -> dict:
    """Sync bridge for the (synchronous) host stack. The v0 turn loop is
    fully synchronous because the engine invokes its model shim
    synchronously mid-call; async fan-out is a later optimization."""
    return asyncio.run(provider.complete(prompt, schema, tier=tier, deliberate=deliberate))


def engine_callable(provider: Provider, tier: Tier = "main") -> ModelCallable:
    """Bind a tier; return the sync `(prompt, schema) -> json` callable
    the engine's `World(model=...)` expects (letter 004, Q5 ruling)."""

    def call(prompt: str, schema: dict) -> dict:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(provider.complete(prompt, schema, tier=tier))
        raise RuntimeError(
            "engine_callable invoked inside a running event loop; "
            "hand the engine an executor-dispatched wrapper instead"
        )

    return call


#: Engine prompt prefixes that are parse/extract work — cheap tier per
#: the founder's assignment (letter 012: "ingestion extraction" and the
#: classifier are cheap; only narration and character interpretation
#: are good-tier).
_CHEAP_ENGINE_PREFIXES = ("Extract world-state", "Classify the lifetime")


def engine_tier_dispatch(provider: Provider) -> ModelCallable:
    """The engine gets ONE callable; tier is chosen per call by prompt
    shape: extraction/classification → cheap, everything else (resolver
    invention, refer tier-2) → main. Pure dispatch, no vendor knowledge."""

    def call(prompt: str, schema: dict) -> dict:
        tier: Tier = "cheap" if prompt.startswith(_CHEAP_ENGINE_PREFIXES) else "main"
        return asyncio.run(provider.complete(prompt, schema, tier=tier))

    return call


class StubProvider(Provider):
    """Canned, deterministic responses for tests — the engine accepts it
    the same way, which is how arc-layer and session-zero logic get
    tested before and without any live model."""

    def __init__(self, responses: list[dict] | None = None) -> None:
        self._queue: list[dict] = list(responses or [])
        self.calls: list[tuple[str, dict, str]] = []

    def enqueue(self, response: dict) -> None:
        self._queue.append(response)

    async def complete(self, prompt: str, schema: dict, *, tier: Tier = "main",
                       deliberate: bool = False) -> dict:
        self.calls.append((prompt, schema, tier))
        if not self._queue:
            raise ProviderTransportError("StubProvider queue exhausted")
        response = self._queue.pop(0)
        validate_against_schema(response, schema)
        return response

    def describe(self) -> str:
        return "stub"


def _nullable(node: Any) -> Any:
    """Make a schema node accept null (the strict-mode optionality idiom)."""
    if not isinstance(node, dict):
        return node
    out = dict(node)
    t = out.get("type")
    if isinstance(t, str) and t != "null":
        out["type"] = [t, "null"]
    elif isinstance(t, list) and "null" not in t:
        out["type"] = t + ["null"]
    return out


def strip_nulls(payload: Any) -> Any:
    """Drop null-valued object keys from a model response — the inverse
    of the all-required-with-nullable schema transform."""
    if isinstance(payload, dict):
        return {k: strip_nulls(v) for k, v in payload.items() if v is not None}
    if isinstance(payload, list):
        return [strip_nulls(v) for v in payload]
    return payload


def force_strict_object_schema(schema: Any) -> Any:
    """Recursive transform for the Codex backend's strict-schema rules:
    every `type: object` level declares `additionalProperties: false`
    and lists all properties as required. (Pattern from the Kernos
    reference provider; copied, never imported.)"""
    if isinstance(schema, list):
        return [force_strict_object_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        props = out.get("properties", {})
        originally_required = set(out.get("required", []))
        new_props = {}
        for key, sub in props.items():
            sub = force_strict_object_schema(sub)
            if key not in originally_required and originally_required:
                sub = _nullable(sub)
            new_props[key] = sub
        out["properties"] = new_props
        # Backend rule: required must list EVERY property; optionality
        # is expressed as nullability instead, and the response side
        # strips nulls so callers keep the original optional semantics.
        out["required"] = sorted(props.keys())
    if "items" in out:
        out["items"] = force_strict_object_schema(out["items"])
    for combinator in ("anyOf", "oneOf", "allOf"):
        if combinator in out:
            out[combinator] = [force_strict_object_schema(b) for b in out[combinator]]
    if "type" not in out and not any(
            k in out for k in ("anyOf", "oneOf", "allOf", "enum", "$ref")):
        # The backend requires a type on every node; deliberately
        # untyped leaves (e.g. an assertion value: literal-or-entity-id)
        # get the permissive scalar union.
        if "properties" in out:
            out["type"] = "object"
        elif "items" in out:
            out["type"] = "array"
        else:
            out["type"] = ["string", "number", "boolean", "null"]
    return out


class CodexProvider(Provider):
    """The shipped zero-credit default: ChatGPT-subscription OAuth via
    the Codex-shape HTTP shim (Kernos-proven pattern, letter 020).

    Wire invariants carried from Kernos production: OAuth bearer (never
    an API key) + chatgpt-account-id + originator/UA headers; SSE-only
    endpoint; `store: false`; `include: reasoning.encrypted_content`;
    strict-coerced output schema; ~40KB payload cap enforced loudly.
    Auth is fresh-read from `~/.codex/auth.json` per call; 401 fails
    fast with the fix named — never retried."""

    def __init__(
        self,
        auth_path: Path | None = None,
        main_model: str | None = None,
        cheap_model: str | None = None,
        base_url: str | None = None,
        timeouts: dict[str, float] | None = None,
    ) -> None:
        self._auth_path = auth_path or Path.home() / ".codex" / "auth.json"
        self._main_model = main_model or os.getenv("HOLODECK_CODEX_MODEL", "gpt-5.5")
        self._cheap_model = cheap_model or os.getenv("HOLODECK_CODEX_CHEAP_MODEL", "gpt-5.4-mini")
        self._base_url = (base_url or os.getenv(
            "HOLODECK_CODEX_BASE_URL", "https://chatgpt.com/backend-api")).rstrip("/")
        self._timeouts = dict(DEFAULT_TIMEOUTS, **(timeouts or {}))
        import uuid
        self._session_id = f"construct-{uuid.uuid4()}"

    # -- plumbing ---------------------------------------------------------

    def _read_auth(self) -> dict:
        """Fresh per call — never cached across runs (letter 020)."""
        if not self._auth_path.exists():
            raise ProviderAuthError(
                f"no Codex credential at {self._auth_path} — run `codex login`")
        try:
            tokens = json.loads(self._auth_path.read_text())["tokens"]
            return {"access": tokens["access_token"], "account_id": tokens["account_id"]}
        except (KeyError, json.JSONDecodeError) as exc:
            raise ProviderAuthError(
                f"unreadable Codex credential ({exc}) — run `codex login`") from exc

    def _headers(self, auth: dict) -> dict[str, str]:
        system = platform.system().lower() or "unknown"
        details = "; ".join(p for p in (platform.release(), platform.machine()) if p)
        return {
            "session_id": self._session_id,
            "x-client-request-id": self._session_id,
            "Authorization": f"Bearer {auth['access']}",
            "chatgpt-account-id": auth["account_id"],
            "originator": "pi",
            "User-Agent": f"pi ({system} {details})".strip(),
            "Content-Type": "application/json",
            "OpenAI-Beta": "responses=experimental",
            "accept": "text/event-stream",
        }

    def _model_for(self, tier: Tier) -> str:
        return self._main_model if tier == "main" else self._cheap_model

    def _body(self, prompt: str, schema: dict, tier: Tier,
              deliberate: bool = False) -> dict:
        model = self._model_for(tier)
        body: dict[str, Any] = {
            "model": model,
            "instructions": (
                "Answer with a single JSON object conforming exactly to "
                "the required schema. No prose outside the JSON."
            ),
            "input": [{"role": "user", "content": prompt}],
            "store": False,
            "stream": True,
            "include": ["reasoning.encrypted_content"],
            "text": {"format": {
                "type": "json_schema",
                "name": "output",
                "schema": force_strict_object_schema(schema),
            }},
        }
        if model.startswith("gpt-5"):
            # Reasoning effort is THE latency cliff (measured: 22s low vs
            # 180s+ medium per extraction; a medium-effort narrate put a
            # turn over 5 minutes — letter 022 finding C). Default LOW on
            # both tiers: good model, low effort. Only `deliberate` calls
            # (planning-class: arc authoring) pay for medium. Env
            # override applies everywhere.
            default_effort = "medium" if deliberate else "low"
            body["reasoning"] = {
                "effort": os.getenv("HOLODECK_CODEX_REASONING_EFFORT", default_effort),
                "summary": "auto",
            }
        # Session-correlation for backend prompt-cache hits (load-bearing
        # on large payloads per the Kernos production findings).
        body["prompt_cache_key"] = self._session_id
        return body

    @staticmethod
    async def _collect_sse_text(resp: Any) -> str:
        """Collect the final output text from the SSE stream. Partial
        output is preserved in errors — it is the only clue (DP-4)."""
        final: dict = {}
        text_chunks: list[str] = []
        buffer = ""
        async for chunk in resp.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                idx = buffer.index("\n\n")
                block, buffer = buffer[:idx], buffer[idx + 2:]
                data_lines = [l[5:].strip() for l in block.split("\n") if l.startswith("data:")]
                data_str = "\n".join(data_lines).strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type", "")
                if etype in ("response.completed", "response.done"):
                    final = event.get("response", event)
                elif etype == "response.output_text.delta":
                    text_chunks.append(event.get("delta", ""))
        for item in final.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        return content["text"]
        if text_chunks:
            return "".join(text_chunks)
        raise ProviderTransportError(
            f"Codex stream ended without output text; final event tail: "
            f"{json.dumps(final)[:300]}")

    # -- the interface ----------------------------------------------------

    async def complete(self, prompt: str, schema: dict, *, tier: Tier = "main",
                       deliberate: bool = False) -> dict:
        attempt_prompt = prompt
        for attempt in range(2):  # one bounded re-ask on schema mismatch
            raw = await self._call_once(attempt_prompt, schema, tier, deliberate)
            try:
                payload = strip_nulls(json.loads(raw))
            except json.JSONDecodeError as exc:
                payload, exc_msg = None, str(exc)
            else:
                try:
                    validate_against_schema(payload, schema)
                    return payload
                except SchemaViolation as exc:
                    exc_msg = str(exc)
            if attempt == 0:
                logger.warning("codex schema mismatch, re-asking: %s", exc_msg[:200])
                attempt_prompt = (
                    f"{prompt}\n\nYour previous answer was rejected: {exc_msg[:300]}. "
                    f"Answer again with JSON valid against the schema.")
                continue
            raise SchemaViolation(f"after re-ask: {exc_msg[:300]}")
        raise AssertionError("unreachable")

    async def _call_once(self, prompt: str, schema: dict, tier: Tier,
                         deliberate: bool = False) -> str:
        body = self._body(prompt, schema, tier, deliberate)
        payload_bytes = len(json.dumps(body))
        if payload_bytes > CODEX_PAYLOAD_CAP_BYTES:
            raise ProviderTransportError(
                f"payload {payload_bytes // 1024}KB exceeds the {CODEX_PAYLOAD_CAP_BYTES // 1024}KB "
                f"Codex transport cap — the briefing composer owns budget-shaping; "
                f"shrink the prompt, do not raise the cap")
        auth = self._read_auth()
        bound = min(self._timeouts.get(tier, DEFAULT_TIMEOUTS[tier]), HARD_BOUND_SECONDS)
        url = f"{self._base_url}/codex/responses"
        import httpx
        try:
            async with asyncio.timeout(bound):
                # Fresh client per call: each sync-bridge invocation runs
                # its own event loop, and an AsyncClient must not outlive
                # the loop it was created on.
                async with httpx.AsyncClient(timeout=120.0) as http:
                    async with http.stream(
                        "POST", url, headers=self._headers(auth), json=body
                    ) as resp:
                        if resp.status_code == 401:
                            await resp.aread()
                            raise ProviderAuthError(
                                f"Codex auth failed (401) — run `codex login`. "
                                f"Tail: {resp.text[:200]}")
                        if resp.status_code >= 400:
                            await resp.aread()
                            raise ProviderTransportError(
                                f"Codex API error ({resp.status_code}): {resp.text[:300]}")
                        return await self._collect_sse_text(resp)
        except TimeoutError as exc:
            raise ProviderTimeout(
                f"Codex call exceeded {bound:.0f}s bound (tier={tier})") from exc

    def describe(self) -> str:
        return f"codex/{self._main_model}+{self._cheap_model}"
