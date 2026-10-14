"""TurnIntent: the classify verdict as one typed object (audit 2026-10, tier 2 #1).

``cohorts.classify`` answers ``CLASSIFY_SCHEMA`` (cohorts.py) with a raw dict. The semantics of
that call (each field's default, which fields only count on which kinds, the fail-open and
fail-closed directions) are its real contract, so they live here, next to nothing else, instead of
scattered through ``run_turn``. ``run_turn`` reads one ``TurnIntent``: ``from_verdict`` on success,
``FAIL_OPEN`` when the provider fails.

The directions, which matter:
- ``addresses_present`` and ``asserts_or_reveals`` fail OPEN to True. Absent means "keep the
  protection": the sole-NPC hold, and extraction where a fact could be asserted.
- ``moves_open``, ``seeks_encounter`` and the tangent aim fail CLOSED. Only a literal True (or a
  usable aim on an action) raises them, because they gate canon mutation.
- The NPC fields carry the classifier's OPAQUE candidate ids (``npc_0`` …). Only ``run_turn``
  holds the map back to entity ids. Dismissal wins a conflict with ``moved_with`` or ``joins``.
"""

from __future__ import annotations

from dataclasses import dataclass
_ACTION = ("action",)
_ACTS = ("action", "declaration")


@dataclass(frozen=True)
class TurnIntent:
    """What the player's input means for this turn, as the classifier judged it."""

    kind: str = "action"                 # action | question | declaration | exit
    moves_to: str = ""                   # blank when whitespace-only (cr G2 r4)
    requires: tuple[str, ...] = ()
    needs_test: bool = False             # action only
    uncertain_of: str = ""
    mortal_risk: bool = False            # #95, action only
    reshape_attempt: bool = False        # action only
    commits: bool = False                # EFFECTIVE: conclusory AND condition none|hedge (R38)
    commitment: str = ""                 # the committed words; the input itself when blank
    #: HEDGE-VS-CONDITION (R38, IR-18): the model's RAW conclusory flag — read ONLY by the
    #: pure-mode declaration exemption — and the move's condition. A precondition/conditional
    #: conclusion is a PENDING DECISION, never an effective commitment.
    conclusory: bool = False
    commit_condition: str = "none"       # none | hedge | precondition | conditional
    commit_precondition: str = ""
    #: WALK-AWAY-DECLARED (R40, IR-16): strict flags, fail CLOSED (only a literal True).
    declares_giving_up: bool = False
    confirms_walkaway: bool = False
    takes: str = ""
    takes_more: tuple[str, ...] = ()     # further objects taken in the same move (run 5 t22)
    drops: str = ""
    examines_target: str = ""
    asks_targets: tuple[str, ...] = ()
    addresses_present: bool = True       # fails OPEN (task #5)
    moves_open: bool = False             # fails CLOSED, action only (WORLD-GROWTH G1)
    seeks_encounter: bool = False        # fails CLOSED, action only
    npcs_dismissed: tuple[str, ...] = ()  # opaque ids, action only
    moved_with: tuple[str, ...] = ()     # opaque ids, action only, never a dismissed one
    joins: tuple[str, ...] = ()          # opaque ids, action only, never a dismissed one (#82)
    asserts_or_reveals: bool = True      # fails OPEN (TURN-LATENCY A-lite)
    #: UTTERANCE-NOT-FACT (R42 r3): act | speech | mixed | unknown. Missing/invalid → unknown,
    #: which FAILS CLOSED: no factual extraction of the player's line at all.
    claims_are: str = "unknown"
    uses_knowledge: bool = False         # action only (Cx 247)
    asks_self: bool = False
    recalls: bool = False                # #97
    declares_memory: bool = False        # #97, action or declaration
    tangent_aim: str = ""                # BEAT-1 declaration, fails CLOSED
    #: MOVE-TO-UNPLACED-OBJECT: is the move's destination inside the current place? Tri-state:
    #: only a literal JSON boolean counts; absent or malformed is None (today's fixture rule).
    within_scene: bool | None = None

    @classmethod
    def from_verdict(cls, verdict: dict, player_input: str) -> "TurnIntent":
        """Normalize a successful classify verdict. ``verdict["kind"]`` is required (the schema
        requires it); every other field may be absent and takes its documented default."""
        from construct.growth import strict_flag
        from construct.tangent import declaration

        kind = verdict["kind"]
        action, acts = kind in _ACTION, kind in _ACTS
        dismissed = [t for t in (verdict.get("npcs_dismissed") or [])] if action else []
        return cls(
            kind=kind,
            moves_to=str(verdict.get("moves_to", "") or "").strip(),
            requires=tuple(r for r in verdict.get("requires", []) if r),
            needs_test=bool(verdict.get("needs_test")) and action,
            uncertain_of=(verdict.get("uncertain_of") or "").strip(),
            mortal_risk=bool(verdict.get("mortal_risk")) and action,
            reshape_attempt=bool(verdict.get("reshape_attempt")) and action,
            commits=_effective_commits(verdict, acts),
            conclusory=bool(verdict.get("commits")) and acts,
            commit_condition=_condition(verdict),
            declares_giving_up=verdict.get("declares_giving_up") is True,
            confirms_walkaway=verdict.get("confirms_walkaway") is True,
            commit_precondition=(verdict.get("commit_precondition").strip()
                                 if isinstance(verdict.get("commit_precondition"), str)
                                 else ""),
            commitment=(verdict.get("commitment") or "").strip() or player_input,
            takes=(verdict.get("takes") or "").strip(),
            takes_more=tuple(t.strip() for t in (verdict.get("takes_more") or [])
                             if isinstance(t, str) and t.strip()),
            drops=(verdict.get("drops") or "").strip(),
            examines_target=(verdict.get("examines_target") or "").strip(),
            asks_targets=tuple(t for t in (verdict.get("asks_targets") or []) if t),
            addresses_present=bool(verdict.get("addresses_present", True)),
            moves_open=strict_flag(verdict.get("moves_open")) and action,
            seeks_encounter=strict_flag(verdict.get("seeks_encounter")) and action,
            npcs_dismissed=tuple(dismissed),
            moved_with=tuple(t for t in (verdict.get("moved_with") or []) if t not in dismissed)
            if action else (),
            joins=tuple(t for t in (verdict.get("joins") or []) if t not in dismissed)
            if action else (),
            asserts_or_reveals=bool(verdict.get("asserts_or_reveals", True)),
            claims_are=(verdict.get("claims_are")
                        if verdict.get("claims_are") in ("act", "speech", "mixed")
                        else "unknown"),
            uses_knowledge=bool(verdict.get("uses_protagonist_knowledge")) and action,
            asks_self=bool(verdict.get("asks_self")),
            recalls=bool(verdict.get("recalls")),
            declares_memory=bool(verdict.get("declares_memory")) and acts,
            tangent_aim=declaration(verdict, kind=kind),
            within_scene=(verdict.get("within_scene")
                          if isinstance(verdict.get("within_scene"), bool) else None),
        )


#: Conditions that defer a conclusion (R38): the move is a pending decision, not a commitment.
DEFERRING_CONDITIONS = frozenset({"precondition", "conditional"})


def _condition(verdict: dict) -> str:
    """The move's commit condition; missing/unknown → "none" (legacy behaviour holds)."""
    c = verdict.get("commit_condition")
    return c if c in ("none", "hedge", "precondition", "conditional") else "none"


def _effective_commits(verdict: dict, acts: bool) -> bool:
    """IR-18: only a plain or hedged conclusion commits; a deferred one never does."""
    return (bool(verdict.get("commits")) and acts
            and _condition(verdict) not in DEFERRING_CONDITIONS)


#: The provider failed: a plain action with every protection on and every mutation gate shut.
FAIL_OPEN = TurnIntent()
