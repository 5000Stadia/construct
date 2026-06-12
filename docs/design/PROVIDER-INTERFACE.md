# The Provider Interface — spec (design draft)

**Status:** Spec for review. No code. This is the FIRST thing built when
code starts (letter 003: "build the interface before any agent that
calls a model"). It is deliberately small — the value is the boundary,
not the machinery.

**One sentence:** every model call in Holodeck — the engine's injected
`model=` and every host cohort — routes through one
`(prompt, schema) -> json` interface with a tier hint; Codex
subscription auth is the shipped zero-credit default implementation, and
any user-supplied LLM API is just another implementation behind the same
boundary.

---

## 1. The interface (the ten lines that matter)

```python
Tier = Literal["main", "cheap"]

class Provider(Protocol):
    """One model call: structured JSON out, schema-enforced."""
    async def complete(self, prompt: str, schema: dict, *, tier: Tier = "main") -> dict: ...
    def describe(self) -> str: ...        # for receipts: "codex/gpt-5.x", "openai/<model>", …

def engine_callable(provider: Provider, tier: Tier = "main") -> ModelCallable:
    """Bind a tier; return the (prompt, schema) -> json callable the
    engine's World(model=...) expects (letter 004, Q5 ruling)."""
```

- `schema` is a JSON Schema; the returned dict **validates against it or
  the call raises** — schema enforcement is the provider's job, so no
  caller ever re-validates.
- `tier` is a *hint* mapping to a per-provider model pair (main/cheap).
  The engine has no tier parameter — `engine_callable` closes over one.
- Sync wrapper provided for callers that need it; the native surface is
  async (cohorts fan out).

## 2. MUST / NEVER (letters 003/008; ADOPTION-style, binding)

- **MUST** route every model call through this interface — engine
  `model=`, renderer/GM, NPC engines, beat-evaluator, input-classifier,
  interviewer, arc author. No exceptions, including "temporary" ones.
- **MUST** ship Codex subscription auth as the working default: detected
  and usable with zero configuration and zero credits.
- **NEVER** name a vendor, model id, endpoint, or credential anywhere
  past the interface boundary. Downstream code knows `main` and `cheap`,
  nothing else.
- **MUST** honor the user's selected provider EVERYWHERE once chosen at
  session zero — engine and cohorts alike; no silent fallback to Codex
  for "just this one call."
- **NEVER** store provider config or credentials in a `.world` file —
  they live in the host-side player profile only. A shipped world
  carries no secrets and no other player's boundaries (letter 008;
  grep-verifiable, SESSION-ZERO criterion (e)).

## 3. Failure semantics (typed; policy belongs to callers)

```python
class ProviderError(Exception): ...          # base; never silently absorbed
class ProviderAuthError(ProviderError): ...  # 401 family — actionable fix attached
class ProviderTimeout(ProviderError): ...    # the ~10-min house bound tripped
class ProviderTransportError(ProviderError): ...
class SchemaViolation(ProviderError): ...    # post-retry mismatch
```

The provider itself **never degrades silently and never decides
policy**: it raises typed errors with the raw diagnostic preserved.
Callers apply their own discipline — cohorts are fail-open (a broken
beat-evaluator never blocks the turn, DP-6); the turn-loop render is
loud-fail (an ungroundable turn surfaces an honest seam, DP-4); session
zero fails fast with the named fix. One mechanism, per-caller policy.

Every call is bounded (~10 minutes hard, per the house standard; default
much lower per tier — main 240s, cheap 60s, configurable). On schema
mismatch: one bounded re-ask with the violation named, then
`SchemaViolation`.

## 4. The Codex reference implementation (the shipped default)

The Kernos-proven shim — pattern copied from
`/home/k/Kernos/kernos/providers/codex_provider.py` (read-only
reference; **copy the pattern, never import**):

- **Auth:** fresh-read `~/.codex/auth.json` per run (never cached across
  runs); on 401 raise `ProviderAuthError("run `codex login`")` — fail
  fast, never retry an expired credential.
- **Transport:** direct HTTP (httpx, async), SSE response collection; no
  CLI spawn (kills the spawn floor and the max-turns failure class —
  letter 020 rationale).
- **Wire-shape invariants (load-bearing, from Kernos production):**
  `strict: null` present on every tool definition (the consumer backend
  treats a missing `strict` key differently from explicit null);
  schema coerced via the force-strict-object transform; payloads kept
  under the ~40KB threshold that tips the backend into mid-stream
  timeouts — the briefing composer owns budget-shaping, the shim enforces
  the cap loudly.
- **Tier map:** main → the shim's full model; cheap → its mini variant.
  One config row, provider-local.

## 5. Other implementations (session-zero PROVIDER stage)

Each is a thin adapter implementing `complete()`: OpenAI key, Anthropic
key, local/Ollama endpoint, anything else a user holds. Selection
happens once at session zero; the choice and its credential go to the
player profile; `describe()` lands in receipts so the audit trail names
which mind produced which call. **StubProvider** (canned, deterministic
JSON keyed by schema) ships for tests — the engine accepts it the same
way, which is how arc-layer and session-zero logic get tested before and
without any live model.

## 6. Placement and sequencing

`holodeck/provider.py` — host-side, never in the engine tree. Built
first, with the stub and the Codex shim, before any agent exists to call
it. The interface is the contract the rest of the build writes against;
its tests are transport-free (stub) plus one gated live smoke test
(skipped when `~/.codex/auth.json` is absent).
