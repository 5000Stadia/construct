"""WORLD-GROWTH G-A — tangent adoption, piece A: the pending-adoption
state machine (docs/design/WORLD-GROWTH.md §6 G-A items 1).

The player declares a NEW story of their own ("forget the case — I'm
making a life on this boat"). Adoption is a TWO-BEAT contract so a single
line of enthusiasm adopts nothing:

BEAT 1 — the declaration persists a PENDING-ADOPTION receipt (normalized
aim, turn, the source action) in the session frame. Exactly ONE candidate
exists at a time: a newer declaration SUPERSEDES it, an explicit cancel
clears it, and a quiet span EXPIRES it (evaluated host-side at read — a
lapsed receipt is structurally invisible). Reopen preserves exactly the
one persisted candidate. The old main REMAINS main throughout.

BEAT 2 — confirmation requires citing a LATER committed action as
tangent-consistent evidence (movement alone is never sufficient); the
judgment call is its own cohort, but every gate around it is host
structure: a pending receipt must exist, be unexpired, and the citing
turn must be strictly later. Confirmation ARMS adoption; the activation
itself (piece B) rides the ruled engine envelope.

Pure and explicit throughout (the growth_eligibility discipline): no
hidden reads; the wiring supplies every input.
"""

from __future__ import annotations

import logging

from construct.growth import strict_flag

logger = logging.getLogger(__name__)

#: The single-slot pending receipt entity (session frame). One candidate,
#: ever: newer declarations supersede by writing the same keys.
PENDING = "session:tangent_pending"

#: A pending declaration LAPSES after this many turns without
#: confirmation — the player drifted back, and a stale aim from twenty
#: turns ago must not adopt on an unrelated action's echo.
EXPIRY_TURNS = 12

#: Aim display bound — one stated aim, not a manifesto.
_MAX_AIM = 300


def declaration(verdict: dict, *, kind: str) -> str:
    """The BEAT-1 trigger read (fail-closed, the strict_flag discipline):
    returns the normalized aim ONLY when the classifier affirmed a real
    declaration on a committed in-world turn AND supplied a nonempty aim.
    Everything else — absent fields, truthy-not-True flags, blank or
    overlong aims, non-action kinds — reads "" (no declaration)."""
    if kind != "action":
        return ""
    if not strict_flag(verdict.get("declares_tangent_aim")):
        return ""
    aim = verdict.get("tangent_aim")
    if type(aim) is not str:
        return ""
    aim = " ".join(aim.split())
    if not aim or len(aim) > _MAX_AIM:
        return ""
    return aim


def pending_rows(aim: str, *, turn: int, action: str, at: float) -> list[dict]:
    """BEAT 1's receipt — the SAME keys every time, so a newer declaration
    supersedes the older by ordinary fold semantics (one candidate by
    construction). `action` is the player's committed wording, bounded."""
    if type(aim) is not str or not aim.strip():
        raise ValueError("tangent pending: aim must be a nonempty string")
    if type(turn) is not int or isinstance(turn, bool) or turn < 0:
        raise ValueError(f"tangent pending: turn must be a non-negative "
                         f"int, got {turn!r}")
    return [
        {"entity": PENDING, "attribute": "aim", "value": aim.strip(),
         "value_type": "literal", "valid_from": at},
        {"entity": PENDING, "attribute": "declared_turn", "value": str(turn),
         "value_type": "literal", "valid_from": at},
        {"entity": PENDING, "attribute": "source_action",
         "value": str(action)[:_MAX_AIM], "value_type": "literal",
         "valid_from": at},
    ]


def cancel_rows(*, at: float) -> list[dict]:
    """An explicit cancel clears the slot by superseding the aim with the
    literal empty value (the dismissal-companionship pattern) — never a
    retract, so the history stays readable."""
    return [{"entity": PENDING, "attribute": "aim", "value": "",
             "value_type": "literal", "valid_from": at}]


def read_pending(reads, *, turn: int) -> dict | None:
    """The current pending candidate, or None. EXPIRY is evaluated here,
    host-side: a receipt older than EXPIRY_TURNS is structurally invisible
    (never half-visible). Read failures return None — a tangent gate must
    fail toward the ordinary story, never toward adoption."""
    try:
        aim = reads.state(PENDING, "aim", frame="session:main")
        if not isinstance(aim, str) or not aim.strip():
            return None
        declared_raw = reads.state(PENDING, "declared_turn",
                                   frame="session:main")
        declared = int(str(declared_raw))
        if declared < 0 or turn - declared > EXPIRY_TURNS:
            return None  # lapsed — the player drifted back
        action = reads.state(PENDING, "source_action", frame="session:main")
        return {"aim": aim.strip(), "declared_turn": declared,
                "source_action": action if isinstance(action, str) else ""}
    except Exception:  # noqa: BLE001 — unreadable pending = no pending
        logger.warning("tangent pending read failed", exc_info=True)
        return None


def may_confirm(pending: dict | None, *, turn: int, committed: bool) -> bool:
    """The HOST structure around BEAT 2 (the judgment itself is a cohort;
    this gate is what makes a single line of enthusiasm structurally
    unable to adopt): a live pending receipt, a strictly LATER turn, and
    a committed in-world action this turn."""
    if pending is None or committed is not True:
        return False
    declared = pending.get("declared_turn")
    if type(declared) is not int or isinstance(declared, bool):
        return False
    return turn > declared
