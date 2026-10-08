"""Concealment: what the hidden arc turns on, and the vocabulary built from it.

Owns the protected `(entity, attribute)` keys (`arc_protected_keys`, with the
placeholder-premise exclusion), the shared concealment vocabulary and its screens
(`concealed_tokens`, `value_leaks`, `_CONCEAL_STOP`, `_CONCEAL_WORD`), and the set of
entity ids the arc references (`arc_entities`). Conditions are imported lazily inside
the functions (turnloop imports the executor, which re-exports this module). Re-exported
by `construct.arc.executor`.
"""

from __future__ import annotations

import re
from typing import Any

from construct.arc.grammar import Arc
from construct.arc.supersession import active_beats


def _is_placeholder_premise(atom: Any, protagonist: str) -> bool:
    """True for the host's placeholder premise atom `StateIs(protagonist, "kind",
    "person")` — the protagonist merely being a person, which conceals nothing."""
    from construct.arc.conditions import StateIs

    return (isinstance(atom, StateIs) and atom.entity == protagonist
            and atom.attribute == "kind" and atom.value == "person")


def _premise_keys(arc: Arc) -> set[tuple[str, str]]:
    """Protected `(entity, attribute)` keys of the arc's premise, minus the
    protagonist-is-a-person placeholder (see `arc_protected_keys`)."""
    from construct.arc.conditions import InFrame, StateIs, atoms_of

    return {(a.entity, a.attribute)
            for a in atoms_of(arc.shape.premise)
            if isinstance(a, (StateIs, InFrame))
            and not _is_placeholder_premise(a, arc.protagonist)}


def arc_protected_keys(arc: Arc, reads: Any = None) -> set[tuple[str, str]]:
    """The `(entity, attribute)` KEYS the hidden arc turns on — its beats'
    conditions + the destination + premise (GATED-INGEST-COHORT, momentous
    default-deny, option A). The ingest gate default-denies a NEW, UNLICENSED
    narrator assertion of one of these (it would hand away the answer / grant
    the win), routing it to quarantine for arc review; ordinary detail on the
    SAME entities (a different attribute) still promotes — so improv isn't
    strangled, only the load-bearing facts are protected."""
    from construct.arc.conditions import InFrame, StateIs, atoms_of

    keys: set[tuple[str, str]] = set()
    _beats = active_beats(reads, arc) if reads is not None else arc.beats
    exprs = [b.achievable_via for b in _beats]
    exprs += [b.unreachable_if for b in _beats if b.unreachable_if]
    exprs += [arc.shape.world_condition]
    # The premise folds in too, EXCEPT the host's placeholder `StateIs(protagonist,
    # "kind", "person")` (game._build_arc stamps it on every arc). It is trivially
    # true, hides no answer, and as a protected key it would turn the protagonist's
    # own name into concealed vocabulary (value_leaks('Edith Marlowe has been your
    # oldest friend') -> True). Any OTHER premise atom — even one on the
    # protagonist, e.g. a secret parentage — stays protected.
    keys.update(_premise_keys(arc))
    # PILLAR CLUE FACTS are load-bearing answers too (Cx 041): the genuine/false coverage
    # conditions reference the clue facts the player must EARN through play. Protect them so
    # no narrator path (incl. card-weaving's deliver_card) can promote/mirror an unearned
    # clue — only the authorized interview-delivery write (`learn_clue_items` straight to
    # knows:<protagonist>) lands them.
    for pillar in arc.pillars:
        if pillar.genuine_via is not None:
            exprs.append(pillar.genuine_via)
        if pillar.false_via is not None:
            exprs.append(pillar.false_via)
    for expr in exprs:
        for atom in atoms_of(expr):
            if isinstance(atom, (StateIs, InFrame)):
                keys.add((atom.entity, atom.attribute))
    return keys


#: Function words + structural attr names that are never "concealed vocabulary" (they'd
#: false-positive every freeform value). Shared by the render + build leak screens.
_CONCEAL_STOP = {"the", "a", "an", "of", "to", "is", "in", "on", "status", "kind",
                 "name", "alias", "title", "fact", "event", "obj", "person", "place"}


#: The one word tokenizer of the concealment vocabulary, used on BOTH sides (building the
#: tokens, screening the text) so they cannot disagree: any run of letters/digits, so
#: punctuation and `_`/`-`/`:` separators never hide a token. Same run as
#: `turnloop._secret_word_set` (`[a-z0-9]+`), made unicode-aware so an accented name
#: ('josé') is one word on both sides.
_CONCEAL_WORD = re.compile(r"[^\W_]+")


def concealed_tokens(keys: set[tuple[str, str]]) -> set[str]:
    """Distinctive tokens of the arc's HIDDEN facts — drawn from each protected entity id
    and attribute (NOT the value: a protected fact's value is often a public name, not itself
    secret). The shared concealment vocabulary the cold open screens freeform text against
    (Cx 022 #3 / 333 #3 / 337). `keys` = `arc_protected_keys(arc)`."""
    toks: set[str] = set()
    for (e, a) in keys:
        for src in (str(e).split(":", 1)[-1], str(a)):
            for t in _CONCEAL_WORD.findall(src.lower()):
                if len(t) > 3 and t not in _CONCEAL_STOP:
                    toks.add(t)
    return toks


def value_leaks(text: str, tokens: set[str]) -> bool:
    """True if freeform `text` brushes any concealed token. One screen used by BOTH the
    render path (`Session._value_leaks` / `live_threads`) and the build path
    (`game.seed_player_relationships`) so a leaked value can never be persisted or shown
    (Cx 337). Empty token set → fail-open False (a quiet/unprotected arc conceals nothing)."""
    if not tokens:
        return False
    # TOTAL tokenizer (the same word run `turnloop._secret_word_set` uses; it can't
    # be imported here — turnloop imports this module): punctuation ('the culprit,') must
    # never leave a concealed token un-matched. `_`/`-`/`:` are non-alphanumeric, so
    # id-style text ('person:edith_marlowe') still splits into its words.
    words = set(_CONCEAL_WORD.findall(str(text).lower()))
    return bool(tokens & words)


def arc_entities(arc: Arc, reads: Any = None) -> set[str]:
    """Entity ids the arc references (for arc_touch detection and the
    irony-delta scope)."""
    from construct.arc.conditions import atoms_of
    from construct.arc.lint import _entity_referents

    out: set[str] = set()
    _beats = active_beats(reads, arc) if reads is not None else arc.beats
    exprs = [b.achievable_via for b in _beats]
    exprs += [b.unreachable_if for b in _beats if b.unreachable_if]
    exprs += [arc.shape.world_condition, arc.shape.premise]
    # Pillar coverage conditions reference the clue FACT entities (STORY-SHAPES §8 / Cx 032
    # blocker 1): include them so the scenario scope surfaces the clues the player gathers.
    for pillar in arc.pillars:
        if pillar.genuine_via is not None:
            exprs.append(pillar.genuine_via)
        if pillar.false_via is not None:
            exprs.append(pillar.false_via)
    for expr in exprs:
        for atom in atoms_of(expr):
            out.update(_entity_referents(atom))
    out.add(arc.protagonist)
    return out
