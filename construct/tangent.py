"""WORLD-GROWTH G-A — tangent adoption, piece A: the pending-adoption
state machine (docs/design/WORLD-GROWTH.md §6 G-A item 1).

The player declares a NEW story of their own ("forget the case — I'm
making a life on this boat"). Adoption is a TWO-BEAT contract so a single
line of enthusiasm adopts nothing:

BEAT 1 — the declaration persists a PENDING-ADOPTION receipt as ONE
bounded record literal (a single row: one fold, one candidate generation
— partial supersession is unrepresentable; cr piece-A blocker 1). A newer
declaration SUPERSEDES the record whole, an explicit cancel clears it
whole, and a quiet span EXPIRES it host-side at read. Reopen preserves
exactly the one persisted candidate. The old main REMAINS main
throughout.

BEAT 2 — confirmation requires citing a LATER committed action as
tangent-consistent evidence (movement alone is never sufficient); the
judgment call is its own cohort, but every gate around it is host
structure over the VALIDATED opaque Pending value.

Pure and explicit throughout (the growth_eligibility discipline): no
hidden reads; the wiring supplies every input. Malformed HOST inputs
raise ValueError (the growth-assembly posture); malformed PERSISTED
state reads as no-candidate — a tangent gate fails toward the ordinary
story, never toward adoption.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass

from construct.growth import strict_flag

logger = logging.getLogger(__name__)

#: The single-slot pending receipt entity (session frame). ONE attribute
#: carries the WHOLE candidate: `record`, a JSON literal.
PENDING = "session:tangent_pending"

#: A pending declaration LAPSES after this many turns without
#: confirmation — the player drifted back, and a stale aim from twenty
#: turns ago must not adopt on an unrelated action's echo.
EXPIRY_TURNS = 12

#: Aim/action display bound — one stated aim, not a manifesto.
_MAX_AIM = 300


@dataclass(frozen=True)
class Pending:
    """A VALIDATED pending candidate — the only shape may_confirm accepts,
    and CONSTRUCTION IS THE VALIDATION (cr r2 blocker 1: a forged
    Pending("", True, "") must be impossible, not merely unlikely): every
    field enforces the exact, bounded contract read_pending requires."""

    aim: str
    declared_turn: int
    source_action: str

    def __post_init__(self):
        if type(self.aim) is not str or not self.aim.strip() \
                or len(self.aim) > _MAX_AIM:
            raise ValueError(f"Pending: aim must be a nonempty bounded "
                             f"string, got {self.aim!r}")
        if type(self.declared_turn) is not int \
                or isinstance(self.declared_turn, bool) \
                or self.declared_turn < 0:
            raise ValueError(f"Pending: declared_turn must be an exact "
                             f"non-negative int, got {self.declared_turn!r}")
        if type(self.source_action) is not str \
                or not self.source_action.strip() \
                or len(self.source_action) > _MAX_AIM:
            raise ValueError(f"Pending: source_action must be a nonempty "
                             f"bounded string, got {self.source_action!r}")


def _require_turn(turn, what: str) -> int:
    if type(turn) is not int or isinstance(turn, bool) or turn < 0:
        raise ValueError(f"tangent: {what} must be an exact non-negative "
                         f"int, got {turn!r}")
    return turn


def _require_at(at) -> float:
    """The growth-assembly temporal boundary, exactly (cr r2 blocker 3):
    overflow normalizes to ValueError, and a coordinate the float cannot
    represent EXACTLY (2**53+1) is rejected, never silently rounded."""
    if type(at) not in (int, float) or isinstance(at, bool):
        raise ValueError(f"tangent: at must be a finite non-negative time, "
                         f"got {at!r}")
    try:
        f = float(at)
    except OverflowError:
        raise ValueError(f"tangent: at {at!r} exceeds the engine's float "
                         "coordinate") from None
    if not math.isfinite(f) or f < 0 or f != at:
        raise ValueError(f"tangent: at must be a finite non-negative time "
                         f"exactly representable in the engine's float "
                         f"coordinate, got {at!r}")
    return f


def _normalize_aim(aim) -> str:
    """Normalize + bound — applied at BOTH the trigger read and again at
    persistence (cr blocker 3: the persistence boundary revalidates)."""
    if type(aim) is not str:
        return ""
    aim = " ".join(aim.split())
    if not aim or len(aim) > _MAX_AIM:
        return ""
    return aim


def declaration(verdict, *, kind: str) -> str:
    """The BEAT-1 trigger read (fail-closed, the strict_flag discipline):
    returns the normalized aim ONLY when the classifier affirmed a real
    declaration on a committed in-world turn AND supplied a usable aim.
    Everything else — a non-dict verdict, absent fields, truthy-not-True
    flags, blank/overlong/mistyped aims, non-action kinds — reads ""."""
    if not isinstance(verdict, dict) or kind != "action":
        return ""
    if not strict_flag(verdict.get("declares_tangent_aim")):
        return ""
    return _normalize_aim(verdict.get("tangent_aim"))


def pending_rows(aim: str, *, turn: int, action: str, at: float) -> list[dict]:
    """BEAT 1's receipt — ONE bounded record literal, so a declaration,
    supersession, or cancel is always a single coherent write (no hybrid
    of a new aim over an old turn can exist). Host inputs validated
    loudly; the aim is normalized and bounded AGAIN here."""
    norm = _normalize_aim(aim)
    if not norm:
        raise ValueError(f"tangent pending: aim must be a nonempty bounded "
                         f"string, got {aim!r}")
    if type(action) is not str or not action.strip():
        raise ValueError(f"tangent pending: action must be a nonempty "
                         f"string, got {action!r}")
    record = json.dumps({"aim": norm,
                         "declared_turn": _require_turn(turn, "turn"),
                         "source_action": " ".join(action.split())[:_MAX_AIM]})
    return [{"entity": PENDING, "attribute": "record", "value": record,
             "value_type": "literal", "valid_from": _require_at(at)}]


def cancel_rows(*, at: float) -> list[dict]:
    """An explicit cancel clears the slot by superseding the RECORD with
    the literal empty value — one write, whole-candidate, history
    readable (never a retract)."""
    return [{"entity": PENDING, "attribute": "record", "value": "",
             "value_type": "literal", "valid_from": _require_at(at)}]


def read_pending(reads, *, turn: int) -> Pending | None:
    """The current pending candidate, or None. The COMPLETE record shape
    is required (aim + declared_turn + source_action, exact types,
    nonempty, bounded) and EXPIRY is evaluated here, host-side: only
    0 <= turn - declared_turn <= EXPIRY_TURNS is live — a future-declared
    or lapsed record is structurally invisible. Malformed or unreadable
    PERSISTED state returns None; a malformed `turn` PARAM is a host bug
    and raises."""
    _require_turn(turn, "turn")
    try:
        raw = reads.state(PENDING, "record", frame="session:main")
        if not isinstance(raw, str) or not raw.strip():
            return None
        rec = json.loads(raw)
        if not isinstance(rec, dict):
            return None
        aim = rec.get("aim")
        declared = rec.get("declared_turn")
        action = rec.get("source_action")
        if type(aim) is not str or not aim.strip() or len(aim) > _MAX_AIM:
            return None
        if type(declared) is not int or isinstance(declared, bool) \
                or declared < 0:
            return None
        if type(action) is not str or not action.strip() \
                or len(action) > _MAX_AIM:
            return None
        if not (0 <= turn - declared <= EXPIRY_TURNS):
            return None  # lapsed — or declared in the player's future
        return Pending(aim=aim.strip(), declared_turn=declared,
                       source_action=action.strip())
    except Exception:  # noqa: BLE001 — unreadable pending = no pending
        logger.warning("tangent pending read failed", exc_info=True)
        return None


def may_confirm(pending, *, turn: int, committed: bool) -> bool:
    """The HOST structure around BEAT 2 (the judgment itself is a cohort;
    this gate is what makes a single line of enthusiasm structurally
    unable to adopt): a VALIDATED Pending value — nothing else is
    accepted, a bare dict cannot impersonate a receipt — a strictly
    LATER turn, a committed in-world action this turn — and the EXPIRY
    invariant rechecked at THIS boundary (cr r2 blocker 2: a legitimately
    read Pending cached past its window must not confirm at turn 100)."""
    _require_turn(turn, "turn")
    if not isinstance(pending, Pending) or committed is not True:
        return False
    return 1 <= turn - pending.declared_turn <= EXPIRY_TURNS
