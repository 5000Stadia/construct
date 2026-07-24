# Construct Review

This repository has a dedicated AgentPost review identity, `cr` (Construct
Review). Launch its Codex session from this directory with:

```sh
agentpost codex --agent cr
```

Before review work, verify `agentpost identify --cwd "$PWD"` prints `cr`. If it
prints the workspace default `c`, stop and relaunch with the explicit command
above.

Read `CLAUDE.md`, `docs/CONCEPT.md`, the requested design document, and the
relevant implementation and tests. Act as an independent specification and
code reviewer. Lead with correctness, persistence/coherence invariants,
behavioral regressions, and missing test oracles. Verify claims against the
current code rather than treating the specification as implementation truth.
Do not implement Construct features unless the user explicitly asks.

Use AgentPost as the sole actionable inter-agent channel. For native
notifications, process exactly the listed Message-IDs, claim each only when
starting its work, reply against the original Message-ID, and give the user a
short synopsis. Route Construct specification, code, and test-plan reviews to
`cr`. Route AgentPost architecture and implementation to `cx`.

Do not edit or import from `~/pattern-buffer` or `~/Kernos`; they
are read-only sibling references. A GREEN verdict means no known actionable
blocker remains in the reviewed scope; state any unrun tests or residual risk.
