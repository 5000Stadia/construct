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
    import re as _re
    if type(arc_id) is not str \
            or not _re.fullmatch(r"arc:[a-z0-9_]+", arc_id):
        raise ValueError(f"tangent build: arc_id must satisfy the id "
                         f"grammar arc:[a-z0-9_]+, got {arc_id!r}")
    if not isinstance(proposal, dict):
        return None, ["proposal: not a mapping"]
    proposal = dict(proposal)
    proposal["protagonist"] = protagonist   # forced, never trusted
    # UNIQUENESS + COLLISION (cr piece-B r2 blocker 3): duplicate beat ids
    # would serialize as one persisted beat with conflicting rows; an arc
    # id already in the world would collide two stories
    try:
        if reads.has_entity(arc_id):
            return None, ["preflight: arc_id_collision"]
    except Exception as exc:  # noqa: BLE001 — an unreadable world is unfit
        return None, [f"preflight: {exc}"]
    _beat_ids = [str(b.get("id", "")) for b in proposal.get("beats", [])
                 if isinstance(b, dict)]
    if len(set(_beat_ids)) != len(_beat_ids):
        return None, ["proposal: duplicate beat ids"]
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


@dataclass(frozen=True)
class PortfolioState:
    """The VERIFIED current portfolio (cr piece-B r2 blocker 1): both
    constitutive control rows located with their assertion ids — the
    adoption builder consumes only this, so an unverifiable manifest can
    never reach the envelope."""

    arc_ids: tuple
    main_arc: str
    retract_ids: tuple   # every visible arc_ids/main_arc assertion id

    def __post_init__(self):
        if not self.arc_ids or any(
                type(a) is not str or not a.startswith("arc:")
                for a in self.arc_ids):
            raise ValueError("PortfolioState: arc_ids must be arc ids")
        if type(self.main_arc) is not str \
                or not self.main_arc.startswith("arc:") \
                or self.main_arc not in self.arc_ids:
            raise ValueError("PortfolioState: main_arc must be a member "
                             "arc id")
        if len(self.retract_ids) < 2 \
                or len(set(self.retract_ids)) != len(self.retract_ids) \
                or any(type(r) is not str or not r.strip()
                       for r in self.retract_ids):
            raise ValueError("PortfolioState: retract_ids must be the >=2 "
                             "distinct assertion ids covering BOTH control "
                             "rows")


def read_portfolio_state(world) -> "PortfolioState | None":
    """Locate BOTH portfolio control rows (arc_ids + main_arc) with their
    assertion ids. Returns None when either is unlocatable — adoption
    fails toward the ordinary story, never toward a blind retract."""
    import json as _json
    try:
        from construct.adapter import frame_facts
        rows = [r for r in frame_facts(world, "plot:main",
                                       entity="arc:portfolio")
                if r.attribute in ("arc_ids", "main_arc")]
        ids_rows = [r for r in rows if r.attribute == "arc_ids"]
        main_rows = [r for r in rows if r.attribute == "main_arc"]
        if not ids_rows or not main_rows:
            return None
        arc_ids = _json.loads(str(ids_rows[-1].value))
        main_arc = str(main_rows[-1].value)
        return PortfolioState(
            arc_ids=tuple(str(a) for a in arc_ids), main_arc=main_arc,
            retract_ids=tuple(str(r.id) for r in rows))
    except Exception:  # noqa: BLE001 — unverifiable manifest = no adoption
        logger.warning("portfolio state read failed", exc_info=True)
        return None


def adoption_ops(*, arc, portfolio: PortfolioState, aim: str, turn: int,
                 at: float) -> list[dict]:
    """The ONE adoption unit (item 3b), as ordered typed ops for
    commit_set — built ONLY from the exact linted Arc and the VERIFIED
    portfolio (cr r2 blockers 1+2: no raw row lists, no caller-supplied
    manifest): retract every visible manifest control row FIRST (the
    Cx 167 constitutive-fold discipline), then assert the arc's own
    serialized rows + index, the old main's durable demotion (never a
    silent drop), the replacement manifest built HERE (the old main
    RETAINED as a side arc by construction), and the adoption receipt
    the phase boundary reads. Any op failing aborts the whole set
    engine-side; nothing here writes."""
    from construct.arc.grammar import Arc
    from construct.arc import io as arc_io
    if type(arc) is not Arc:
        raise ValueError("adoption ops: arc must be the exact linted Arc")
    if type(portfolio) is not PortfolioState:
        raise ValueError("adoption ops: portfolio must be the verified "
                         "PortfolioState")
    new_main_id = arc.arc_id
    old_main_id = portfolio.main_arc
    if new_main_id == old_main_id or new_main_id in portfolio.arc_ids:
        raise ValueError(f"adoption ops: {new_main_id} already in the "
                         "portfolio — adoption mints a NEW main")
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
        for rid in portfolio.retract_ids]
    new_arc_items = (arc_io.arc_to_items(arc, frame="plot:main")
                     + arc_io.index_items(arc, frame="plot:main"))
    ops += [{"op": "assert", "item": dict(i)} for i in new_arc_items]
    ops.append({"op": "assert", "item": {
        "entity": old_main_id, "attribute": "demoted",
        "value": ADOPTION_RECEIPT_KIND, "frame": "plot:main",
        "valid_from": at}})
    manifest_items = arc_io.portfolio_items(
        list(portfolio.arc_ids) + [new_main_id], main_arc_id=new_main_id,
        frame="plot:main", valid_from=at)
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
    n_asserts = n_retracts = 0
    for op in ops:
        if not isinstance(op, dict):
            return ActivationResult(ok=False, reason="malformed_op")
        if op.get("op") == "assert":
            item = op.get("item")
            if not isinstance(item, dict) \
                    or not str(item.get("entity", "")).strip() \
                    or not str(item.get("attribute", "")).strip():
                return ActivationResult(ok=False, reason="malformed_op")
            n_asserts += 1
        elif op.get("op") == "retract":
            if type(op.get("assertion_id")) is not str \
                    or not op["assertion_id"].strip() \
                    or type(op.get("reason")) is not str \
                    or not op["reason"].strip():
                return ActivationResult(ok=False, reason="malformed_op")
            n_retracts += 1
        else:
            return ActivationResult(ok=False, reason="malformed_op")
    if not n_asserts or not n_retracts:
        # adoption is MIXED by construction: the manifest supersession
        # (retracts) and the new truth (asserts) travel together or not
        # at all
        return ActivationResult(ok=False, reason="not_an_adoption_set")
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
