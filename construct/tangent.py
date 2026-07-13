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
    if type(pending) is not Pending or committed is not True:
        # EXACT type only (cr r3): a subclass overriding __post_init__
        # bypasses construction validation — no subtype may impersonate
        # the validated value
        return False
    return 1 <= turn - pending.declared_turn <= EXPIRY_TURNS


# ---------------------------------------------------------------------------
# Piece B — the tangent author gate + the ATOMIC adoption set (spec §6 G-A
# items 2, 3, 3b). The author's proposal is model display material; the
# HOST forces the protagonist, builds, and LINTS before anything touches
# the portfolio; the adoption itself is ONE typed mixed-operation set
# through the RULED engine envelope (PB <d0e5199b…>: commit_set(ops) with
# exactly {op:"assert", item} | {op:"retract", assertion_id, reason}) —
# host-side atomicity mechanisms are rejected outright, so on an engine
# without commit_set adoption fails CLOSED before writing anything.

#: The durable adoption receipt (the phase boundary reads it — item 4):
#: rides IN the atomic set, so the boundary flips with the adoption or
#: not at all.
ADOPTION_RECEIPT_KIND = "tangent_adopted"


def build_tangent_arc(proposal, *, protagonist: str, arc_id: str, reads
                      ) -> tuple:
    """The DEDICATED tangent build path (item 3; the LWG mint path
    structurally rejects player-protagonist arcs and is not reused): the
    model's proposal is display material — the HOST forces the
    protagonist to exactly the player, builds through the shared
    grammar, and runs the full arc lint. Returns (arc, []) or
    (None, problems); NOTHING is committed here — the caller may only
    hand a linted arc to the adoption set."""
    if type(protagonist) is not str or not protagonist.startswith("person:"):
        raise ValueError(f"tangent build: protagonist must be a person id, "
                         f"got {protagonist!r}")
    if type(arc_id) is not str or not arc_id.startswith("arc:"):
        raise ValueError(f"tangent build: arc_id must be an arc id, got "
                         f"{arc_id!r}")
    if not isinstance(proposal, dict):
        return None, ["proposal: not a mapping"]
    proposal = dict(proposal)
    proposal["protagonist"] = protagonist   # forced, never trusted
    try:
        from construct.game import _build_arc
        arc = _build_arc(proposal, arc_id=arc_id)
    except Exception as exc:  # noqa: BLE001 — a bad proposal is retryable
        return None, [f"build: {exc}"]
    if arc.protagonist != protagonist:
        return None, ["build: protagonist drift"]
    # the dedicated PREFLIGHT (item 3 "owns its schema and preflight"):
    # grounding the lint layer doesn't cover — the protagonist and the
    # tension entity must exist in the world the arc will govern
    try:
        if not reads.has_entity(protagonist):
            return None, ["preflight: ungrounded_protagonist"]
        tension_entity = arc.shape.tension[0] if arc.shape.tension else None
        if not tension_entity or not reads.has_entity(tension_entity):
            return None, ["preflight: ungrounded_tension"]
    except Exception as exc:  # noqa: BLE001 — an unreadable world is unfit
        return None, [f"preflight: {exc}"]
    try:
        from construct.arc.lint import lint_arc
        findings = lint_arc(arc, reads)
    except Exception as exc:  # noqa: BLE001 — an unlintable arc is unfit
        return None, [f"lint: {exc}"]
    # `2-paths` is advisory here exactly as at session zero and the LWG
    # preflight (generator.py) — everything else blocks
    problems = [f"lint:{f.check}" for f in findings if f.check != "2-paths"]
    if problems:
        return None, problems
    return arc, []


def adoption_ops(*, new_arc_items: list, manifest_items: list,
                 retract_ids: list, old_main_id: str, new_main_id: str,
                 aim: str, turn: int, at: float) -> list[dict]:
    """The ONE adoption unit (item 3b), as ordered typed ops for
    commit_set: retract the sealed portfolio manifest rows FIRST (the
    Cx 167 constitutive-fold discipline), then assert the new arc + its
    index, the old main's durable demotion (reason `tangent_adopted` —
    never a silent drop), the replacement manifest, and the adoption
    receipt the phase boundary reads. Any op failing aborts the whole
    set engine-side; nothing here writes."""
    if type(old_main_id) is not str or not old_main_id.startswith("arc:"):
        raise ValueError(f"adoption ops: old_main_id must be an arc id, "
                         f"got {old_main_id!r}")
    if type(new_main_id) is not str or not new_main_id.startswith("arc:") \
            or new_main_id == old_main_id:
        raise ValueError(f"adoption ops: new_main_id must be a DIFFERENT "
                         f"arc id, got {new_main_id!r}")
    if type(new_arc_items) is not list or not new_arc_items or any(
            not isinstance(i, dict) for i in new_arc_items):
        raise ValueError("adoption ops: new_arc_items must be a nonempty "
                         "list of row dicts")
    if type(manifest_items) is not list or not manifest_items or any(
            not isinstance(i, dict) for i in manifest_items):
        raise ValueError("adoption ops: manifest_items must be a nonempty "
                         "list of row dicts")
    if type(retract_ids) is not list or any(
            type(r) is not str or not r.strip() for r in retract_ids):
        raise ValueError("adoption ops: retract_ids must be assertion-id "
                         "strings")
    norm_aim = _normalize_aim(aim)
    if not norm_aim:
        raise ValueError(f"adoption ops: aim must be a nonempty bounded "
                         f"string, got {aim!r}")
    _require_turn(turn, "turn")
    at = _require_at(at)
    ev = f"event:tangent_adopted_{turn}"
    ops: list[dict] = [
        {"op": "retract", "assertion_id": rid,
         "reason": "tangent adoption: superseding the portfolio manifest"}
        for rid in retract_ids]
    ops += [{"op": "assert", "item": dict(i)} for i in new_arc_items]
    ops.append({"op": "assert", "item": {
        "entity": old_main_id, "attribute": "demoted",
        "value": ADOPTION_RECEIPT_KIND, "frame": "plot:main",
        "valid_from": at}})
    ops += [{"op": "assert", "item": dict(i)} for i in manifest_items]
    for attr, value in (("kind", ADOPTION_RECEIPT_KIND), ("aim", norm_aim),
                        ("old_main", old_main_id),
                        ("new_main", new_main_id)):
        ops.append({"op": "assert", "item": {
            "entity": ev, "attribute": attr, "value": value,
            "frame": "session:main", "valid_from": at}})
    return ops


def activate_adoption(p, ops: list) -> "object":
    """Commit the adoption set atomically, or refuse before writing.

    commit_set is the ONLY door (the set mixes retracts with asserts, so
    the assert-only atomic sugar can never carry it; host-side atomicity
    is rejected by PB outright). On an engine without commit_set:
    `adoption_unavailable`, nothing written. Success must be affirmative
    (the growth adaptor's own receipt discipline)."""
    from construct.growth import ActivationResult, _affirmative_success
    if type(ops) is not list or not ops:
        return ActivationResult(ok=False, reason="empty_set")
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in ("assert",
                                                            "retract"):
            return ActivationResult(ok=False, reason="malformed_op")
    n_asserts = sum(1 for op in ops if op["op"] == "assert")
    if not callable(getattr(p, "commit_set", None)):
        logger.warning("adoption unavailable: engine has no commit_set "
                       "(%d ops withheld — nothing written)", len(ops))
        return ActivationResult(ok=False, reason="adoption_unavailable")
    try:
        receipt = p.commit_set(list(ops))
    except Exception as exc:  # noqa: BLE001 — an aborted set is a refusal
        logger.warning("adoption aborted by the engine: %s", exc)
        return ActivationResult(ok=False, reason=f"engine_abort:{exc}")
    ok, reason, rows = _affirmative_success(receipt, n_asserts)
    if not ok:
        logger.warning("adoption not affirmed: %s", reason)
        return ActivationResult(ok=False, reason=reason, receipts=rows)
    return ActivationResult(ok=True, receipts=rows)
