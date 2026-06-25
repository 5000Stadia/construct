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
import re
import socket
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
#: Absolute ceiling. Interactive calls stay at their snappy tier bound (300/180); only DELIBERATE
#: build-time authoring (story/cast/arc/...) is allowed up to this. Raised 600→900 because
#: `author_cast` — the heaviest single generation (5-10 cast members × clues/pillars/staging/
#: signature, on the full ~6KB world digest) — was hitting the 600s tail on full builds and shipping
#: the world pillar-less (cast authoring skipped). A build is a one-time wait; interactive turns are
#: unaffected (tier-bounded). The structural latency win is parallelization (PB letter 083), not a
#: bigger single call — this just stops the pillar-less fail-open on the slow tail.
HARD_BOUND_SECONDS = 900.0

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
                  deliberate: bool = False, task: str = "") -> dict:
    """Sync bridge for the (synchronous) host stack. The v0 turn loop is
    fully synchronous because the engine invokes its model shim
    synchronously mid-call; async fan-out is a later optimization.

    `task` prepends the systematic section tag (see `task_tag`/`task_of`), so
    routing/tiering/profiling latch onto a stable marker rather than the prose."""
    if task:
        prompt = task_tag(task) + prompt
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

#: Reasoning-effort (thinking-level) ordering for gpt-5 models, low→high.
_EFFORT_RANK = {"minimal": 0, "low": 1, "medium": 2, "high": 3}

#: Systematic prompt sectioning (founder): every HOST cohort prompt OPENS with a
#: stable, content-independent TASK TAG — a 3-letter code in mathematical white
#: brackets `⟦abc⟧`. Routing/tiering/profiling latch onto the tag, never the prose
#: (a FICTION_CRAFT preamble or any wording change must not break dispatch). The
#: bracket chars `⟦⟧` (U+27E6/27E7) effectively never occur in fiction — unlike
#: ASCII `[]<>` which a sci-fi terminal-sim scene might emit — AND agents that
#: produce player-facing text are explicitly FORBIDDEN to emit them (see
#: `FORBID_TASK_MARKERS`), so content can never be mistaken for a tag. Engine
#: prompts (extraction/classification) are engine-owned and untagged; they keep
#: prefix-based dispatch (see `_CHEAP_ENGINE_PREFIXES`).
_TASK_OPEN, _TASK_CLOSE = "⟦", "⟧"  # ⟦ ⟧
_TASK_RE = re.compile(_TASK_OPEN + r"([a-z]{3})" + _TASK_CLOSE)

#: A one-line ban to weave into any cohort whose OUTPUT is shown to the player or
#: re-ingested, so the reserved markers never appear in content.
FORBID_TASK_MARKERS = (
    "Never write the characters ⟦ or ⟧ (reserved control markers).")


def task_tag(code: str) -> str:
    """The stable section header to prepend to a host cohort prompt (3-letter code)."""
    return f"{_TASK_OPEN}{code}{_TASK_CLOSE}\n"


def task_of(prompt: str) -> str:
    """The 3-letter task code a prompt is tagged with, or '' (engine/untagged)."""
    m = _TASK_RE.search(prompt[:120])
    return m.group(1) if m else ""


#: Host tasks whose render FLOORS at high effort regardless of tier default —
#: player-facing prose (founder ruling): the narrator (`nar`) holding a live scene
#: and the cold open (`opn`) the player first steps into.
_HIGH_EFFORT_TASKS = frozenset({"nar", "opn"})


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
        main_effort: str | None = None,
        cheap_effort: str | None = None,
    ) -> None:
        self._auth_path = auth_path or Path.home() / ".codex" / "auth.json"
        self._main_model = main_model or os.getenv("HOLODECK_CODEX_MODEL", "gpt-5.5")
        self._cheap_model = cheap_model or os.getenv("HOLODECK_CODEX_CHEAP_MODEL", "gpt-5.4-mini")
        # The MAIN tier's THINKING LEVEL (reasoning effort) — settable, because
        # main carries the quality-bearing work (narration, authoring, NPC voice,
        # generation). Effort is the latency cliff (letter 022 C: ~22s low vs 180s+
        # medium per call), so the default stays `low` (good model, low effort —
        # no behaviour change) and you dial it UP when you want more deliberation.
        # `deliberate` calls (arc authoring) still floor at medium. Levels:
        # minimal | low | medium | high. Cheap stays low (plumbing speed).
        self._main_effort = main_effort or os.getenv("HOLODECK_CODEX_MAIN_EFFORT", "low")
        self._cheap_effort = cheap_effort or os.getenv("HOLODECK_CODEX_CHEAP_EFFORT", "low")
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
            # turn over 5 minutes — letter 022 finding C). Per-tier thinking
            # level: cheap stays low (plumbing speed); main uses the SETTABLE
            # `main_effort` (default low — no behaviour change until dialled up).
            # `deliberate` floors main at medium (planning-class: arc authoring).
            # The legacy global env override still wins everywhere if set.
            if tier == "cheap":
                effort = self._cheap_effort
            else:
                effort = self._main_effort
                if deliberate and _EFFORT_RANK.get(effort, 1) < _EFFORT_RANK["medium"]:
                    effort = "medium"
            effort = os.getenv("HOLODECK_CODEX_REASONING_EFFORT", effort)
            # The narrator holding a LIVE SCENE is the crown jewel (player-facing
            # prose) — it floors at HIGH effort regardless of the tier default or a
            # lower global override (founder: narration quality over latency).
            if task_of(prompt) in _HIGH_EFFORT_TASKS and \
                    _EFFORT_RANK.get(effort, 1) < _EFFORT_RANK["high"]:
                effort = "high"
            body["reasoning"] = {"effort": effort, "summary": "auto"}
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

    @staticmethod
    def _keepalive_socket_options() -> list[tuple[int, int, int]]:
        """Kernel-level dead-peer detection — the SOURCE fix for the wedge that
        `asyncio.timeout`/`httpx` read-timeout couldn't catch (letters 059/060,
        founder's "resolve the source, don't recover" call). When a Codex
        connection goes silent in a bad socket/TLS state, async cancellation can
        strand in httpcore's shielded close (the `ep_poll`/0-CPU hang). TCP
        keepalive makes the *kernel* probe the peer; a dead one surfaces as a
        socket error in ~60s (30s idle + 3×10s probes) → a normal exception the
        existing fail-open/retry handles, instead of an indefinite hang.
        SO_KEEPALIVE is portable; the TCP_KEEP*/USER_TIMEOUT tuning is Linux-only
        (guarded). `TCP_USER_TIMEOUT` (ms) is the direct one for our case: it
        bounds how long *sent, unacknowledged* data may sit before the connection
        errors — i.e. request sent, response stalled — where idle-keepalive probes
        wouldn't even start. Keepalive covers the idle-dead case; USER_TIMEOUT the
        in-flight-stalled case. Both fail healthy long streams safely (data keeps
        getting ACKed)."""
        opts: list[tuple[int, int, int]] = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
        for name, value in (("TCP_KEEPIDLE", 30), ("TCP_KEEPINTVL", 10),
                            ("TCP_KEEPCNT", 3), ("TCP_USER_TIMEOUT", 60_000)):
            if hasattr(socket, name):
                opts.append((socket.IPPROTO_TCP, getattr(socket, name), value))
        return opts

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
        # `deliberate` (planning-class) calls are BUILD-TIME authoring only (story/cast/intro/
        # premise/flavor/arc/interview — never an interactive turn), and legitimately run long
        # (story_authoring ~150-300s). They were failing at the 300s main default during slow
        # provider spells even though there's headroom to HARD_BOUND. So give deliberate calls
        # the full HARD_BOUND (the user already waits for a build); interactive calls (narrate,
        # classify, npc_turn) keep their snappy tier default. Fixes the fresh-genre generation
        # ProviderTimeout (story_authoring exceeded 300s).
        _tier_bound = self._timeouts.get(tier, DEFAULT_TIMEOUTS[tier])
        bound = min(max(_tier_bound, HARD_BOUND_SECONDS) if deliberate else _tier_bound,
                    HARD_BOUND_SECONDS)
        url = f"{self._base_url}/codex/responses"
        import httpx
        try:
            async with asyncio.timeout(bound):
                # Fresh client per call: each sync-bridge invocation runs
                # its own event loop, and an AsyncClient must not outlive
                # the loop it was created on. The per-request read timeout
                # is generous (good-tier turns are long); the asyncio bound
                # above is the hard ceiling.
                transport = httpx.AsyncHTTPTransport(
                    socket_options=self._keepalive_socket_options())
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(bound, connect=30.0), transport=transport
                ) as http:
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
        except httpx.TimeoutException as exc:
            # Network read/connect timeout — surface as a typed ProviderTimeout
            # so callers' fail-open (except ProviderError) catches it: a
            # network blip skips one cohort/frame, never crashes the build.
            raise ProviderTimeout(f"Codex network timeout (tier={tier}): {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderTransportError(f"Codex transport error (tier={tier}): {exc}") from exc

    def describe(self) -> str:
        return f"codex/{self._main_model}+{self._cheap_model}"
