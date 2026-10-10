"""TurnIntent (construct/intent.py): the classify verdict's contract in one place.

The equivalence test keeps a verbatim copy of the unpacking that lived inline in ``run_turn``
before the extraction (turnloop.py, main @ 26b2e6a, lines 4096-4158) and checks the two agree on
randomized verdicts, so the move is proven behaviour-preserving, not assumed.
"""

import random

from construct.growth import strict_flag as _strict
from construct.intent import FAIL_OPEN, TurnIntent
from construct.tangent import declaration as _t_declaration

_NPC_BY_OID = {"npc_0": "person:ada", "npc_1": "person:bo", "npc_2": "person:cy"}


def _legacy_unpack(verdict, player_input):
    """The pre-extraction inline code, verbatim but for returning its locals."""
    dismissed_ids, moved_with_ids, joins_ids = [], [], []
    kind = verdict["kind"]
    moves_to = str(verdict.get("moves_to", "") or "").strip()
    requires = [r for r in verdict.get("requires", []) if r]
    needs_test = bool(verdict.get("needs_test")) and kind == "action"
    uncertain_of = (verdict.get("uncertain_of") or "").strip()
    mortal_risk = bool(verdict.get("mortal_risk")) and kind == "action"
    reshape_attempt = bool(verdict.get("reshape_attempt")) and kind == "action"
    commits = bool(verdict.get("commits")) and kind in ("action", "declaration")
    commitment = (verdict.get("commitment") or "").strip() or player_input
    takes = (verdict.get("takes") or "").strip()
    drops = (verdict.get("drops") or "").strip()
    examines_target = (verdict.get("examines_target") or "").strip()
    asks_targets = [t for t in (verdict.get("asks_targets") or []) if t]
    addresses_present = bool(verdict.get("addresses_present", True))
    moves_open = _strict(verdict.get("moves_open")) and kind == "action"
    seeks_encounter = (_strict(verdict.get("seeks_encounter")) and kind == "action")
    if kind == "action":
        dismissed_ids = [_NPC_BY_OID[t] for t in (verdict.get("npcs_dismissed") or [])
                         if t in _NPC_BY_OID]
        moved_with_ids = [_NPC_BY_OID[t] for t in (verdict.get("moved_with") or [])
                          if t in _NPC_BY_OID and _NPC_BY_OID[t] not in dismissed_ids]
        joins_ids = [_NPC_BY_OID[t] for t in (verdict.get("joins") or [])
                     if t in _NPC_BY_OID and _NPC_BY_OID[t] not in dismissed_ids]
    asserts_or_reveals = bool(verdict.get("asserts_or_reveals", True))
    uses_knowledge = bool(verdict.get("uses_protagonist_knowledge")) and kind == "action"
    asks_self = bool(verdict.get("asks_self"))
    recalls = bool(verdict.get("recalls"))
    declares_memory = (bool(verdict.get("declares_memory")) and kind in ("action", "declaration"))
    _t_aim = _t_declaration(verdict, kind=kind)
    return dict(kind=kind, moves_to=moves_to, requires=requires, needs_test=needs_test,
                uncertain_of=uncertain_of, mortal_risk=mortal_risk, reshape_attempt=reshape_attempt,
                commits=commits, commitment=commitment, takes=takes, drops=drops,
                examines_target=examines_target, asks_targets=asks_targets,
                addresses_present=addresses_present, moves_open=moves_open,
                seeks_encounter=seeks_encounter, dismissed_ids=dismissed_ids,
                moved_with_ids=moved_with_ids, joins_ids=joins_ids,
                asserts_or_reveals=asserts_or_reveals, uses_knowledge=uses_knowledge,
                asks_self=asks_self, recalls=recalls, declares_memory=declares_memory, _t_aim=_t_aim)


def _resolve(intent):
    """What run_turn does with the opaque ids (it alone holds the map)."""
    return ([_NPC_BY_OID[t] for t in intent.npcs_dismissed if t in _NPC_BY_OID],
            [_NPC_BY_OID[t] for t in intent.moved_with if t in _NPC_BY_OID],
            [_NPC_BY_OID[t] for t in intent.joins if t in _NPC_BY_OID])


def _as_legacy(intent):
    d, m, j = _resolve(intent)
    return dict(kind=intent.kind, moves_to=intent.moves_to, requires=list(intent.requires),
                needs_test=intent.needs_test, uncertain_of=intent.uncertain_of,
                mortal_risk=intent.mortal_risk, reshape_attempt=intent.reshape_attempt,
                commits=intent.commits, commitment=intent.commitment, takes=intent.takes,
                drops=intent.drops, examines_target=intent.examines_target,
                asks_targets=list(intent.asks_targets), addresses_present=intent.addresses_present,
                moves_open=intent.moves_open, seeks_encounter=intent.seeks_encounter,
                dismissed_ids=d, moved_with_ids=m, joins_ids=j,
                asserts_or_reveals=intent.asserts_or_reveals, uses_knowledge=intent.uses_knowledge,
                asks_self=intent.asks_self, recalls=intent.recalls,
                declares_memory=intent.declares_memory, _t_aim=intent.tangent_aim)


def _random_verdict(rng):
    pick = lambda *xs: rng.choice(xs)  # noqa: E731
    flag = lambda: pick(True, False, "true", 1, None, "absent")  # noqa: E731
    text = lambda: pick("", "   ", " the study ", None, "absent", "a key")  # noqa: E731
    ids = lambda: pick([], None, "absent", ["npc_0"], ["npc_1", "npc_9", ""],  # noqa: E731
                       ["npc_0", "npc_2", "npc_0"])
    v = {"kind": pick("action", "question", "declaration", "exit")}
    for k in ("needs_test", "mortal_risk", "reshape_attempt", "commits", "addresses_present",
              "moves_open", "seeks_encounter", "asserts_or_reveals", "uses_protagonist_knowledge",
              "asks_self", "recalls", "declares_memory", "declares_tangent_aim"):
        v[k] = flag()
    for k in ("moves_to", "uncertain_of", "commitment", "takes", "drops", "examines_target",
              "tangent_aim"):
        v[k] = text()
    for k in ("npcs_dismissed", "moved_with", "joins", "asks_targets"):
        v[k] = ids()
    v["requires"] = pick([], ["rope", ""], "absent")
    return {k: x for k, x in v.items() if x != "absent"}


def test_from_verdict_matches_the_legacy_inline_unpacking():
    rng = random.Random(1660)
    for _ in range(3000):
        v = _random_verdict(rng)
        assert _as_legacy(TurnIntent.from_verdict(v, "I open the drawer.")) == \
            _legacy_unpack(v, "I open the drawer."), v


def test_fail_open_protects_and_closes_every_mutation_gate():
    assert FAIL_OPEN.kind == "action"
    assert FAIL_OPEN.addresses_present and FAIL_OPEN.asserts_or_reveals
    assert not (FAIL_OPEN.moves_open or FAIL_OPEN.seeks_encounter or FAIL_OPEN.tangent_aim
                or FAIL_OPEN.commits or FAIL_OPEN.needs_test)
    assert FAIL_OPEN.commitment == ""


def test_dismissal_wins_and_only_actions_move_people():
    v = {"kind": "action", "npcs_dismissed": ["npc_0"], "moved_with": ["npc_0", "npc_1"],
         "joins": ["npc_0", "npc_2"]}
    i = TurnIntent.from_verdict(v, "x")
    assert i.moved_with == ("npc_1",) and i.joins == ("npc_2",)
    q = TurnIntent.from_verdict(dict(v, kind="question"), "x")
    assert q.npcs_dismissed == q.moved_with == q.joins == ()


def test_strict_flags_never_fail_open_through_truthiness():
    i = TurnIntent.from_verdict({"kind": "action", "moves_open": "true", "seeks_encounter": 1}, "x")
    assert not i.moves_open and not i.seeks_encounter


def test_takes_more_keeps_every_further_named_object():
    """R20 run 5 t22: the further objects of a multi-object take survive normalization;
    blanks and non-strings drop, an absent field is empty (old verdicts unchanged)."""
    v = {"kind": "action", "takes": " the ash-rake ",
         "takes_more": [" the poker", "", None, "the slate "]}
    intent = TurnIntent.from_verdict(v, "x")
    assert intent.takes == "the ash-rake"
    assert intent.takes_more == ("the poker", "the slate")
    assert TurnIntent.from_verdict({"kind": "action"}, "x").takes_more == ()
