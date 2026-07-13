"""WORLD-GROWTH G1 — the activation adaptor and the growth-chunk assembly.

The host half of the ACTIVATION CONTRACT (docs/design/WORLD-GROWTH.md §3):
growth chunks become visible canon ALL OR NONE through PB's atomic
envelope (ATOMIC-ACTIVATION-V1: `ingest_structured(items, atomic=True)`
sugar over `commit_set`). Until that primitive ships, this adaptor FAILS
CLOSED — it detects capability absence BEFORE writing anything and
returns `activation_unavailable`: zero rows, zero displacement, zero
clock/route change, the caller renders the non-diegetic technical seam.

cr's build boundary (activation-delta review, 2026-07-13), honored here
structurally: NO reachable Growth path may call the non-atomic ingest —
this module is the only door, and this door refuses non-atomic engines.
Item ORDER is contractual under the envelope's staged-prefix gating:
declarations/parents precede references/children (`ordered_chunk_items`
owns that ordering deterministically).
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActivationResult:
    """The adaptor's outcome — receipts are RETURN VALUES, never rows."""

    ok: bool
    reason: str = ""            # "" on success; machine-readable otherwise
    receipts: tuple = ()        # engine receipt rows on success (as returned)


def _capability(p) -> str:
    """Which atomic surface does this engine expose? "commit_set" |
    "atomic_ingest" | "" (none). Detection is conservative and BOUND TO
    THE SURFACE THAT WILL BE CALLED (cr: never infer safety from one
    surface and invoke another): commit_set must be callable;
    atomic_ingest requires an EXPLICIT NAMED `atomic` parameter — a broad
    **kwargs ingest that would silently swallow the flag is NOT capable.
    Absent, ambiguous, or unreadable → "" (fail closed)."""
    try:
        if callable(getattr(p, "commit_set", None)):
            return "commit_set"
        sig = inspect.signature(p.ingest_structured)
        param = sig.parameters.get("atomic")
        if param is not None and param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY):
            return "atomic_ingest"
        return ""
    except Exception:  # noqa: BLE001 — unreadable surface is not capable
        return ""


def atomic_capable(p) -> bool:
    return _capability(p) != ""


def _affirmative_success(receipt, n_items: int) -> tuple[bool, str, tuple]:
    """ATOMIC-ACTIVATION-V1 r2 permits TYPED FAILURE RETURNS — success
    must be affirmative, never inferred from the absence of an exception
    (cr: an {outcome: aborted} return must not read as ok). Rejects an
    explicit failure outcome, any skipped ops, empty rows for a nonempty
    chunk, and any ambiguous shape."""
    if isinstance(receipt, dict):
        outcome = str(receipt.get("outcome", "")).lower()
        skipped = receipt.get("skipped") or ()
        rows = tuple(receipt.get("rows") or ())
    else:
        outcome = str(getattr(receipt, "outcome", "") or "").lower()
        skipped = getattr(receipt, "skipped", None) or ()
        rows = tuple(getattr(receipt, "rows", None) or ())
    if outcome and outcome not in ("ok", "committed", "success"):
        return False, f"engine_outcome:{outcome}", rows
    if skipped:
        return False, "engine_skipped_ops", rows
    if n_items and not rows:
        return False, "ambiguous_receipt:no_rows", rows
    return True, "", rows


def activate_chunk(p, items: list[dict]) -> ActivationResult:
    """Commit one growth chunk atomically, or refuse before writing.

    On a non-atomic engine (PB 0.2.0): `activation_unavailable`, nothing
    written — a torn prefix is never an accepted runtime behavior. On an
    atomic engine: one envelope call; any engine-side abort surfaces as a
    failed result with the engine's receipts (still nothing visible, by
    the envelope's own contract)."""
    if not items:
        return ActivationResult(ok=False, reason="empty_chunk")
    cap = _capability(p)
    if not cap:
        logger.warning("growth activation unavailable: engine has no atomic "
                       "envelope (%d items withheld — nothing written)",
                       len(items))
        return ActivationResult(ok=False, reason="activation_unavailable")
    try:
        if cap == "commit_set":
            # dispatch the surface that was DETECTED (never the sugar path
            # through a possibly-broad legacy ingest)
            receipt = p.commit_set([{"op": "assert", "item": i} for i in items])
        else:
            receipt = p.ingest_structured(items, atomic=True)
    except Exception as exc:  # noqa: BLE001 — an aborted set is a clean refusal
        logger.warning("growth activation aborted by the engine: %s", exc)
        return ActivationResult(ok=False, reason=f"engine_abort:{exc}")
    ok, reason, rows = _affirmative_success(receipt, len(items))
    if not ok:
        logger.warning("growth activation not affirmed: %s", reason)
        return ActivationResult(ok=False, reason=reason, receipts=rows)
    return ActivationResult(ok=True, receipts=rows)


def ordered_chunk_items(*, place: list[dict] | None = None,
                        containment: list[dict] | None = None,
                        passage: list[dict] | None = None,
                        moves: list[dict] | None = None,
                        encounter: list[dict] | None = None,
                        texture: list[dict] | None = None) -> list[dict]:
    """The growth chunk in CONTRACTUAL order (staged-prefix gating makes
    order semantic, not cosmetic): declarations and parents strictly
    before references and children — place stubs, then containment (incl.
    a G3 ancestry insertion's region-before-place pair, which the caller
    supplies in that order), then the passage/connection, then actor
    moves (protagonist + ALL standing companions — one set, §3's
    companion postcondition), then encounter stubs, then texture."""
    out: list[dict] = []
    for part in (place, containment, passage, moves, encounter, texture):
        if part:
            out.extend(part)
    return out


def strict_flag(value) -> bool:
    """The strict signal parser (cr piece-2 finding 1): ONLY the literal
    boolean True is true — strings ("false", "true"), numbers, and every
    other shape read False. Model-supplied flags gate canon mutation and
    must never fail open through truthiness."""
    return value is True


#: The CLOSED pipeline-outcome contract (cr piece-2 finding 2): exactly one
#: value permits growth — "miss", produced only AFTER the ordinary pipeline
#: (refer + known-place + semantic-bind) ran to completion and found
#: nothing. None/""/unknown/error are uninitialized-or-failed sentinels and
#: FORBID growth; the answered states forbid it because the world already
#: spoke: resolved / ambiguous / blocked / undiscovered / same_place /
#: fixture.
PIPELINE_MISS = "miss"


def growth_eligibility(*, kind: str, committed: bool, moves_open: bool,
                       seeks_encounter: bool,
                       pipeline_outcome: str | None,
                       host_deny: str | None = None) -> str | None:
    """The CONJUNCTIVE, ORDERED gate (spec §5; cr: a classifier boolean must
    never by itself authorize canon mutation). Returns the growth MODE
    ("place" | "encounter") when every condition holds, else None:

    1. an in-world, COMMITTED action turn (never hypothetical/negated/
       deliberative/OOC/question — the caller passes `committed` from the
       classify kind + its own guards);
    2. the ordinary pipeline ran FIRST and PROVED the miss —
       `pipeline_outcome` must be exactly PIPELINE_MISS ("miss"), a value
       produced only after refer/known-place/semantic-bind completed and
       found nothing; None/""/unknown/error are uninitialized-or-failed
       sentinels and forbid growth, as does every answered state;
    3. the host's NO-GROWTH check found no structural deny (`host_deny`
       is the enumerated provable reason, or None — a model opinion is
       never one);
    4. and a trigger signal fired (encounter outranks place when both —
       the player's stated aim is the person, the road serves it).

    Pure and explicit (the salient_moments discipline): no reads, no
    hidden state — the turnloop wiring slice supplies every input.
    """
    if kind != "action" or committed is not True:
        return None
    if pipeline_outcome != PIPELINE_MISS:
        return None  # the ONLY permitting value; everything else forbids
    if host_deny:
        return None
    if seeks_encounter is True:
        return "encounter"
    if moves_open is True:
        return "place"
    return None
