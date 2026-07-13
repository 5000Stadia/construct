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


def atomic_capable(p) -> bool:
    """Does this engine expose the atomic envelope? Detection is
    signature-based and conservative: absent, ambiguous, or unreadable →
    NOT capable (fail closed). The final call shape is pbr's to GREEN; we
    detect only the reviewed protocol boundary (`atomic` on the
    structured-ingest path or the `commit_set` verb)."""
    try:
        if hasattr(p, "commit_set"):
            return True
        sig = inspect.signature(p.ingest_structured)
        return "atomic" in sig.parameters
    except Exception:  # noqa: BLE001 — unreadable surface is not capable
        return False


def activate_chunk(p, items: list[dict]) -> ActivationResult:
    """Commit one growth chunk atomically, or refuse before writing.

    On a non-atomic engine (PB 0.2.0): `activation_unavailable`, nothing
    written — a torn prefix is never an accepted runtime behavior. On an
    atomic engine: one envelope call; any engine-side abort surfaces as a
    failed result with the engine's receipts (still nothing visible, by
    the envelope's own contract)."""
    if not items:
        return ActivationResult(ok=False, reason="empty_chunk")
    if not atomic_capable(p):
        logger.warning("growth activation unavailable: engine has no atomic "
                       "envelope (%d items withheld — nothing written)",
                       len(items))
        return ActivationResult(ok=False, reason="activation_unavailable")
    try:
        receipt = p.ingest_structured(items, atomic=True)
    except Exception as exc:  # noqa: BLE001 — an aborted set is a clean refusal
        logger.warning("growth activation aborted by the engine: %s", exc)
        return ActivationResult(ok=False, reason=f"engine_abort:{exc}")
    rows = tuple(getattr(receipt, "rows", None) or
                 (receipt.get("rows", ()) if isinstance(receipt, dict) else ()))
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
