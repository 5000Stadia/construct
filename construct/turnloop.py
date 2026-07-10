"""The turn loop — TURN-LOOP.md's DAG over the frozen porcelain.

Serial mutation spine → assembly fan-out → narrator render → post
(render ingested as canon + concealment audit). One call = one turn;
state lives in the playthrough world file.

Read pattern: atoms read live canon directly (per-key folds are ~0.2ms
after pattern-buffer 037 made folds closure-scoped). Snapshots are taken
only where a materialized fact LIST is genuinely needed — the player-
frame briefing and the canon mirror. The earlier SnapshotReads batching
existed only for the pre-037 per-read cost (seconds per fold) and was
retired once that cost vanished (PB catch-up, re-measured 2026-06-16).

Failure policy (TURN-LOOP §5): spine steps loud-fail; fan-out cohorts
fail open with the drop logged; the narrator failing is the turn
failing.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from construct import cohorts
from construct import resolution
from construct.resolve import (
    resolve_rows, bind_or_mint, _PLAYER_INPUT_MINT_KINDS,
    _NARRATION_MINT_KINDS, _NARRATION_STUB_KINDS, _PLACE_LIKE_KINDS,
)
from construct.adapter import PorcelainWorldReads, frame_facts
from construct.gauge import (
    apply_gauge_terminals, gauge_coloring, gauge_lines, gauge_pass,
)
from construct.reshape import apply_reshape
from construct.arc.executor import (
    LIFECYCLE_TERMINALS,
    PLOT,
    SESSION,
    arc_concluded,
    arc_entities,
    arc_lifecycle,
    arc_outcome,
    arc_protected_keys,
    beat_pass,
    clock_pass,
    climax_ready,
    conclusion_from_coverage,
    counters_from_session,
    coverage_summary,
    current_phase,
    emit_fallout,
    navigate,
    set_lifecycle,
    stored_lifecycle,
    turn_time,
)
from construct.arc.executor import _human as _human_entity
from construct.arc.generator import (
    AMBIENT_QUIET_MIN,
    _last_development_min,
    _mark_development,
    _pacing_ok as _gen_pacing_ok,
    confirmed_batch,
    generate_ambient,
    generate_from_fallout,
    generate_opportunistic,
    main_at_peak,
    prior_promote_batch,
    salient_moments,
    window_events,
)
from construct.arc.grammar import Arc, Phase, Weight
from construct.pins import resolve_active_pins
from construct.provider import Provider, ProviderError

logger = logging.getLogger(__name__)


import time as _time  # noqa: E402
from contextlib import contextmanager  # noqa: E402


def _destination_facts(arc: Arc, reads: Any) -> str:
    """The arc's hidden answer as newline-joined 'entity — attribute: value' lines (the
    protected (entity,attribute) → canon value set), or '' if the arc conceals nothing.
    Shared by the foreshadowing card and the commitment judge."""
    facts: list[str] = []
    for (e, a) in sorted(arc_protected_keys(arc)):
        try:
            v = reads.state(e, a)
        except Exception:
            v = None
        if isinstance(v, str) and v:
            disp = _human_entity(v) if ":" in v else v
            facts.append(f"{_human_entity(e)} — {a}: {disp}")
    return "\n".join(facts)


def _destination_directive(arc: Arc, reads: Any) -> str:
    """The narrator-as-DM's CARD (STORY-SHAPES.md card model — founder override of the
    earlier structural-absence ruling): the arc's hidden answer, framed as the
    destination to FORESHADOW toward, not a vault to guard. A DM must know the answer to
    lay a convergent trail — *you cannot foreshadow what you don't know* (the Joker-bomb
    argument). The discipline is "weave clues toward it, never blurt it, reveal only when
    earned." This re-introduces the answer the structural-absence pass removed; it no
    longer leaks because (a) the player frame is clean now (the seed bug that pre-loaded
    the answer is fixed), (b) the strict promotion gate backstops (a protected fact can't
    auto-promote from prose), (c) the neutral-narrator + brute-force deflection guards
    hold. Empty when the arc conceals nothing (genre-conditional)."""
    facts = _destination_facts(arc, reads)
    if not facts:
        return ""
    facts_block = "\n".join(f"  - {f}" for f in facts.split("\n"))
    return ("\nTHE HIDDEN DESTINATION (you, the narrator, KNOW this; the player does NOT "
            "— it is where the story is heading):\n"
            + facts_block
            + "\nFORESHADOW toward it like a good DM: plant ambiguous, observable clues "
            "that POINT here and let them accrete so the player can assemble it. But "
            "NEVER state, confirm, or hand it over — keep every clue deniable, reveal "
            "nothing until it is earned, and deflect any demand to be told. You hold the "
            "answer ONLY to lay the trail, never to give it away.\n"
            "RESTRAINT (critical — lay the trail SPARINGLY): once a clue is laid and the player "
            "has SEEN it (check the recent story), it is DONE — do NOT re-plant, re-describe, or "
            "re-emphasize it; leave it for them to pull on. Never re-surface the SAME clue every "
            "turn, and never bend every scene and every character toward it — a prop the world "
            "keeps shoving forward, with NPCs twitching at it each time, reads as fixation and "
            "breaks the fiction. MOST turns plant nothing new; add a fresh thread only when the "
            "trail has genuinely gone cold, and prefer a DIFFERENT facet over repeating one the "
            "player already holds.")


_SECRET_STOP = {"the", "a", "an", "of", "to", "is", "in", "on", "and", "or", "by",
                "for", "with", "person", "place", "obj", "fact", "event", "true",
                "false", "none", "unknown", "yes", "no"}


def _secret_tokens(arc: Arc, reads: Any, public: set[str]) -> set[str]:
    """Distinctive vocabulary of the arc's HIDDEN answers — tokens drawn from each
    protected attribute and its canon value — MINUS tokens that are public names in
    play (a public NPC is not a secret just because they turn out to be the culprit;
    the player must be free to ask about them). Used to spot a question fishing
    directly for the solution (Cx 022 blocking #2) so the narrator deflects rather
    than improvises an answer that could brush the secret."""
    toks: set[str] = set()
    for (e, a) in arc_protected_keys(arc):
        try:
            v = reads.state(e, a)
        except Exception:
            v = None
        for src in (a, v if isinstance(v, str) else ""):
            for t in (str(src).replace(":", " ").replace("_", " ")
                      .replace("-", " ").lower().split()):
                if len(t) > 3 and t not in _SECRET_STOP:
                    toks.add(t)
    return toks - public


def _secret_word_set(text: str) -> set[str]:
    """TOTAL word tokenizer (Cx 274): split on ANY non-alphanumeric run, so punctuation
    ('the map!', 'map;', 'key?') can never leave a protected token un-matched. Used on BOTH
    sides of the secret-take guard so the two tokenizations are identical."""
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(t) > 1 and t not in _SECRET_STOP}


def _take_touches_secret(takes: str, arc: Arc, reads: Any) -> bool:
    """Belt-and-suspenders for the improv-object take grant: never MINT an object that names
    the arc's HIDDEN / load-bearing matter (the murder weapon, the map, the dossier, the key) —
    that stays the narrator's to handle honestly, never granted by token. Covers the protected
    ATTRIBUTE/VALUE vocabulary AND each protected ENTITY's id-slug + name/alias/title, at ANY
    meaningful length and PUNCTUATION-insensitive (Cx 272/274/276: the >3 filter let 'take the map'
    slip, a stray '!' let 'the map!' slip, and a '/' in a protected VALUE let 'red map' slip — one
    total tokenizer over the WHOLE protected vocabulary closes all three)."""
    # Build the ENTIRE protected vocabulary through the ONE total tokenizer (Cx 276): the
    # protected attribute, its VALUE, the entity id-slug, and any name/alias/title — so a value
    # like "red/map" tokenizes to {red, map} exactly as the `takes` side does (the old
    # `_secret_tokens` splitter kept it one token and "red map" slipped). `_secret_tokens` is
    # left untouched for its question-deflection caller (which subtracts public names).
    secret: set[str] = set()
    for (e, a) in arc_protected_keys(arc):
        secret |= _secret_word_set(a)
        secret |= _secret_word_set(e.split(":")[-1])
        for attr in (a, "name", "alias", "aliases", "title"):
            try:
                val = reads.state(e, attr)
            except Exception:
                val = None
            if isinstance(val, str):
                secret |= _secret_word_set(val)
    if not secret:
        return False
    return bool(secret & _secret_word_set(takes))


def _move_touches_secret(moves_to: str, arc: Arc, reads: Any) -> bool:
    """NARROW concealment guard for the MOVE-permanence mint (founder live cohesion test,
    2026-06-29). The object-take guard above tokenizes the WHOLE protected vocabulary — including
    free-text descriptive VALUES — which is right for objects but WRONG for movement: a clue value
    like "lodging house" put the common word "house" in the set and blocked walking to a "coffee
    house" / "public house". A move only ever MINTS a place that doesn't yet exist, so it can leak
    no secret; the only thing worth refusing is CONJURING a place named after the hidden ANSWER —
    the culprit, the murder weapon, the culprit's hidden location. Those are the protected keys'
    ENTITY-REFERENCE values (`person:rival`, `place:lair`); block on the referenced entity's
    distinctive slug/name tokens ONLY, never on descriptive prose. Reaching an EXISTING hidden
    place stays the entitlement gate's job (`_names_undiscovered_dest`)."""
    secret: set[str] = set()
    for (e, a) in arc_protected_keys(arc):
        try:
            val = reads.state(e, a)
        except Exception:
            val = None
        # only an ENTITY-REFERENCE value names an answer (person:/place:/obj:/…); skip prose.
        if isinstance(val, str) and re.match(r"^[a-z_]+:[a-z0-9_]+$", val):
            secret |= _secret_word_set(val.split(":", 1)[-1])  # the referenced entity's slug
            try:
                nm = reads.state(val, "name")
            except Exception:
                nm = None
            if isinstance(nm, str):
                secret |= _secret_word_set(nm)
    if not secret:
        return False
    return bool(secret & _secret_word_set(moves_to))


#: The 3-act overlay on the five dramatic phases (CONVERGENCE-TO-CONCLUSION.md;
#: founder "collapse into a three-part act"). Act is a host-side convergence frame,
#: never a player-facing banner.
_ACT_OF = {
    Phase.SETUP: "I", Phase.RISING: "I",
    Phase.CRISIS: "II", Phase.CLIMAX: "II",
    Phase.FALLING: "III",
}


def _convergence_directive(phase: Phase, ready: bool, peril: bool = False) -> tuple[str, str]:
    """The act label + a CONVERGENCE directive for the narrator (founder: "all roads
    should lead to the conclusion — gentle nudges, or relocate the conclusive scene to
    where the story has gone") PLUS a rising-STAKES/SUSPENSE build-up toward the conclusive
    scene (founder: "don't forget tension, raised stakes, suspense build-up before the
    conclusive scene — especially peril/thriller"). Convergence is WHERE it ends; the build-up
    is the RISING PRESSURE on the way. `peril` (a high-stakes/thriller story) amplifies the
    suspense clause. Dramatic pull + staging only — NEVER informational, never reveals the
    hidden answer. Returns ("" , "") in Act III, where the resolution/epilogue directives own it."""
    act = _ACT_OF.get(phase, "I")
    base = ("\nCONVERGENCE (this is live fiction with a destination — bend every road "
            "toward it, gently and diegetically; NEVER stall and NEVER railroad). ")
    # The suspense curve: stakes and pressure should MOUNT as the conclusive scene nears — never
    # coast flat into it. Amplified for peril/thriller (make the danger and the cost of failure
    # felt; tighten the clock; build dread). This is dramatic PRESSURE, never the answer.
    if peril:
        build_i = (" Begin to let the STAKES register — what stands to be lost is real and "
                   "the danger is not far off.")
        build_ii = (" BUILD THE SUSPENSE: raise the stakes and tighten the screws as the climax "
                    "nears — make the threat vivid and close, the clock louder, the cost of "
                    "failure unmistakable; let dread and urgency mount turn over turn. Do NOT "
                    "coast calmly into the conclusion — the player should FEEL the pressure crest.")
    else:
        build_i = (" Let the stakes begin to register — what matters here, and what it would "
                   "cost to lose it.")
        build_ii = (" Let the STAKES and significance MOUNT toward the conclusion — each beat "
                    "weightier than the last, the pressure rising; the player should feel the "
                    "story gathering to a head, not drifting to a stop.")
    if act == "I":
        return act, base + (
            "ACT I — establish the world and let it breathe, but keep a current under "
            "it: surface the hooks and let the central tension tug at the player. Plant, "
            "don't push." + build_i)
    if act == "II":
        relocate = (
            "If the player has wandered from where the pivotal beat was imagined, "
            "RELOCATE it: bring the confrontation/discovery TO them, re-woven to fit "
            "wherever they now are (the moment can land in any place — it turns on what "
            "is true, not on a room). Do not stall and do not march them back.")
        if ready:
            return act, base + (
                "ACT II, and the conclusion is AT HAND — steer every road into it now. "
                + relocate + " Tighten toward the climax; let it feel inevitable, not "
                "forced. Reveal nothing the player hasn't earned — converge the DRAMA, "
                "never the answer." + build_ii)
        return act, base + (
            "ACT II — converge: every thread should bend toward the pivotal beat now, "
            "pressure rising. " + relocate + " Converge the DRAMA, never the answer." + build_ii)
    return act, ""  # Act III: resolution/epilogue directives own the close


#: Honorifics/articles that don't identify a person on their own (so "the doctor" matches
#: by 'doctor', not by 'dr'); kept short — the goal is to drop noise, not over-filter.
_NAME_NOISE = frozenset({"the", "of", "a", "an", "and", "mr", "mrs", "ms", "dr",
                         "lord", "lady", "sir", "miss", "old", "young"})

# Pressure-gated clues should surface under ANY directed investigative engagement, not just
# overt hostility. The live whodunit run showed the agent questions politely ("ask Mara to
# describe what she saw") — that IS pressing a witness in an investigation, but the original
# narrow set (press/demand/threaten/force/insist) never tripped, so pressure clues never
# revealed (0 clues across 16 turns → quiet_failure). These two signal sets broaden it:
# overt pressure OR an investigative probe (a question, a confrontation, asking someone to
# account for / describe / explain). Founder: "directed questioning IS pressing them."
_PRESSURE_VERBS = frozenset({
    "press", "demand", "threaten", "force", "insist", "confront", "accuse", "interrogate",
    "grill", "challenge", "corner", "push", "pressure", "intimidate",
})
_PROBE_SIGNALS = frozenset({
    "ask", "question", "where", "what", "when", "why", "who", "whom", "how", "describe",
    "explain", "account", "alibi", "admit", "confess", "tell", "really", "actually",
    "lying", "lie", "hiding", "hide", "saw", "witness", "prove", "show", "reveal", "did",
    "were", "was", "know", "knew", "suspect", "doing", "claim", "story", "truth",
})


def _is_pressing(text_low: str, *, needs_test: bool) -> bool:
    """Does the player's input apply investigative pressure to a present cast member?

    True for overt pressure verbs, OR an investigative probe (interrogative / asking
    someone to account, describe, explain), OR when classify flagged the action as
    uncertain (needs_test) — directed questioning of a suspect IS pressing them in an
    investigation. v1 heuristic; a fuller intent read later."""
    if needs_test:
        return True
    if "?" in text_low:
        return True
    toks = set(text_low.replace("?", " ").replace(",", " ").replace(".", " ").split())
    return bool(toks & _PRESSURE_VERBS) or bool(toks & _PROBE_SIGNALS)


#: EXAMINE channel (EXAMINE-CHANNEL.md): verbs that mark the player INSPECTING a physical thing.
#: Inspecting a NAMED object is close inspection (scrutiny) — it earns the object's evidentiary
#: clue, not just a glance. A bare "look around" (no object) is NOT scrutiny (handled elsewhere).
_EXAMINE_VERBS = frozenset({
    "examine", "inspect", "search", "study", "check", "scrutinize", "scour", "comb",
    "investigate", "open", "compare", "measure", "probe", "read", "test", "feel", "smell",
    "turn", "lift", "pry",
})


#: Close-inspection adverbs: "look CLOSELY / CAREFULLY at X" is scrutiny even though "look" alone
#: is a glance (Cx 083 — the folded §8b spec named "look closely"). A bare "look around" is not.
_SCRUTINY_ADVERBS = ("closely", "carefully", "close at", "in detail", "minutely")


def _is_scrutiny(text_low: str) -> bool:
    """Is the player CLOSELY inspecting a physical thing this turn (the EXAMINE analogue of
    `_is_pressing`)? True when an examine/inspect/search-class verb is present, OR a close-
    inspection adverb ('look closely/carefully at …'). A bare 'look around'/'notice' is a glance,
    not scrutiny. Gates `scrutiny` object-clues; a glance earns only `examined`-level clues."""
    toks = set(text_low.replace(",", " ").replace(".", " ").replace("?", " ").split())
    if toks & _EXAMINE_VERBS:
        return True
    return any(adv in text_low for adv in _SCRUTINY_ADVERBS)


#: Role-address synonyms: the player-agent addresses a suspect by their ROLE, often with a
#: common synonym ('Doctor' for a 'family physician', 'Constable' for a 'policeman'). Map the
#: synonym a player would say → the role tokens the surface_role carries, so role-address
#: engages the right NPC. The live whodunit run failed a delivery when the agent said only
#: "Doctor" and the matcher (name/id 'orme' only) didn't engage Dr. Orme.
_ROLE_SYNONYMS = {
    "doctor": "physician", "doc": "physician", "physician": "physician",
    "nurse": "nurse", "constable": "policeman", "officer": "policeman",
    "inspector": "detective", "captain": "captain", "colonel": "officer",
    "reverend": "clergyman", "father": "priest", "vicar": "clergyman",
    "professor": "scholar", "maid": "housekeeper", "butler": "butler",
    "cook": "cook", "clerk": "clerk", "barkeep": "bartender",
}

#: The vocabulary of ROLE-NOUN heads that can stand in for a person's identity when the player
#: addresses them by occupation/station ("the valet", "Doctor"). Only these tokens of an NPC's
#: surface_role become addressable — NOT arbitrary descriptors (Cx 051): "Sir Julian's valet"
#: must NOT be addressable by the victim's name 'Julian'; "Market Dalling scandal" not by
#: 'Market'/'scandal'; "family physician" not by 'family'. A surface_role token counts as an
#: address head only if it is a known role noun here (or a canonical synonym target).
_ROLE_NOUNS = frozenset({
    "physician", "doctor", "surgeon", "nurse", "apothecary",
    "valet", "butler", "maid", "housekeeper", "governess", "cook", "footman",
    "gardener", "groom", "coachman", "steward", "servant", "porter",
    "clerk", "secretary", "solicitor", "lawyer", "banker", "merchant", "clergyman",
    "priest", "vicar", "sexton", "professor", "scholar", "tutor", "schoolmaster",
    "constable", "policeman", "detective", "inspector", "sergeant", "captain",
    "colonel", "major", "soldier", "sailor", "guard", "watchman",
    "innkeeper", "landlord", "bartender", "barkeep", "publican",
    "gentlewoman", "widow", "heir", "heiress", "nephew", "niece", "ward",
}) | frozenset(_ROLE_SYNONYMS.values())


def _words(s: str) -> list[str]:
    """Lowercased word tokens, punctuation stripped (so 'Dr. Ames,' → ['dr','ames'])."""
    for ch in ",.;:!?\"'()[]—-":
        s = s.replace(ch, " ")
    return s.lower().split()


def _names_entity(entity: str, text_low: str, name: str = "", role: str = "") -> bool:
    """Cheap heuristic: does the lowercased player input name this entity? Matches the id
    stem ('person:night_clerk' → 'clerk'/'night'), the significant tokens of the NPC's
    narrated `name` ('Hobbes, the butler' → 'hobbes'/'butler'; 'Dr. Ames' → 'ames'), AND
    its `role`/surface_role tokens ('family physician' → 'physician'; so addressing 'the
    physician' engages them). A small role-synonym map also catches the form a player
    actually says ('Doctor' → the 'physician' role).

    Matching is WHOLE-TOKEN, not substring (Cx 049): substring matching let 'doc' hit
    'documents'. And role tokens are ADDRESS-FILTERED, not blindly added (Cx 051): only an
    NPC's role-NOUN heads ('valet', 'physician') are addressable identity, never arbitrary
    descriptors — so "Sir Julian's valet" is not addressable by the victim's name 'Julian',
    nor "family physician" by 'family'. v1 — a fuller coreference resolver later."""
    text_toks = set(_words(text_low))
    cands: set[str] = set()
    # Name + id-stem tokens are fully addressable identity (they ARE the person's name).
    stem = entity.split(":", 1)[-1].replace("_", " ")
    for src_toks in (_words(stem), _words(name)):
        for tok in src_toks:
            if len(tok) > 2 and tok not in _NAME_NOISE:
                cands.add(tok)
    # Role tokens are addressable ONLY when they are recognized role-noun heads (Cx 051) —
    # not the descriptors a role string carries (a victim's name, a place, 'family').
    role_toks = set(_words(role))
    cands |= {t for t in role_toks if t in _ROLE_NOUNS}
    if cands & text_toks:
        return True
    # Role-synonym address ('Doctor' for a physician): the player SAID (as a whole token) a
    # role word whose canonical role noun this NPC carries.
    for spoken, canon in _ROLE_SYNONYMS.items():
        if spoken in text_toks and canon in role_toks:
            return True
    return False


#: Interjections that lead a sentence with address punctuation but are never a title
#: ("Well, that's odd" / "God, the smell"). Belt-and-braces — resolution against canon
#: titles is the real filter; this just keeps the resolver from even trying.
_VOCATIVE_NOISE = frozenset({
    "well", "yes", "no", "right", "fine", "god", "lord", "damn", "hello", "hi",
    "hey", "wait", "stop", "now", "so", "ah", "oh", "hm", "hmm", "look", "listen",
    "please", "sorry", "thanks", "thank", "alright", "okay", "ok", "come", "go",
    "run", "quick", "help", "enough", "quiet", "steady", "easy", "careful", "still",
})

#: Title/rank attributes a person may carry in canon — the vocabulary of address.
_TITLE_ATTRS = ("role", "title", "rank", "position", "office")

_VOCATIVE_INTERJECTION = re.compile(r"^\s*(?:hey|oi|ho|say|listen)\b[,!\s]*",
                                    re.IGNORECASE)
_VOCATIVE_LEAD = re.compile(r"^\s*([A-Za-z]+)\s*[,!—:]")
_VOCATIVE_SOLE = re.compile(r"^\s*([A-Za-z]+)\s*[!?.]*\s*$")
_VOCATIVE_TAIL = re.compile(r"[,;]\s*([A-Za-z]+)\s*[!?.]*\s*$")


def _vocative_token(player_input: str) -> str:
    """#93 (Cx 404 C-scope): the ADDRESS-SYNTAX-gated vocative token of the player's
    line — 'Chief!', 'Chief, where were you?', 'Hey, Chief, what were your orders?',
    'what do you make of it, Chief?' — or '' when the line has no address shape.
    Syntax-gated ON PURPOSE: 'my chief concern' must never read as an address. An
    optional interjection lead-in ('Hey,'/'hey'/'Oi') is stripped case-insensitively
    BEFORE the lead form is read (Cx 427: 'Hey, Chief, …' failing to resolve silently
    re-enabled the sole-present-NPC fallback — the exact C-scope failure mode)."""
    _lead_src = _VOCATIVE_INTERJECTION.sub("", player_input, count=1)
    for pat, src in ((_VOCATIVE_LEAD, _lead_src), (_VOCATIVE_SOLE, _lead_src),
                     (_VOCATIVE_TAIL, player_input)):
        m = pat.match(src) if pat is not _VOCATIVE_TAIL else pat.search(src)
        if m:
            tok = m.group(1).lower()
            if len(tok) > 2 and tok not in _VOCATIVE_NOISE and tok not in _NAME_NOISE:
                return tok
    return ""


def _title_holder(canon_table: dict, token: str, protagonist: str) -> tuple[str | None, int]:
    """Resolve a vocative token against CANON titles/roles: the person entities whose
    role/title/rank carries the token (whole-token; role-synonyms honored — 'Doctor'
    finds the physician). Returns (holder, count): a UNIQUE holder resolves; zero or
    several → (None, count) and the convention falls through untouched (Cx 404: a
    unique canon role/title like 'Chief')."""
    if not token:
        return None, 0
    canon_tok = _ROLE_SYNONYMS.get(token, token)
    holders: set[str] = set()
    for (ent, attr), val in canon_table.items():
        if not str(ent).startswith("person:") or ent == protagonist:
            continue
        if str(attr) not in _TITLE_ATTRS:
            continue
        vtoks = set(_words(str(val)))
        if token in vtoks or canon_tok in vtoks:
            holders.add(str(ent))
    if len(holders) == 1:
        return next(iter(holders)), 1
    return None, len(holders)


def _departed_from(p: Any, reads: Any, npc: str, scene: str, *,
                   as_of: float | None = None) -> bool:
    """PRESENCE PROJECTION (Cx 363/364, the ghost-cast incident): True when the NPC's latest
    `departed_scene` event FROM this scene is same-or-newer than their current `in` row — the
    honest negative scene truth ("no longer here") for a departure whose destination the fiction
    never named. A NEWER positive `in` row (the story re-placed them) lifts the suppression.
    Best-effort: any read miss → False (presence falls back to the location truth)."""
    try:
        evs = reads.events(kind="departed_scene", participant=npc)
        dep_at = max((e.at for e in evs
                      if scene in (e.patients or ()) and e.at is not None), default=None)
        if dep_at is None:
            return False
        st = p.state(npc, "in", as_of=as_of)
        fact = st.get("fact") if isinstance(st, dict) else None
        valid = (fact or {}).get("valid") or []
        placed_at = valid[0] if valid else None
        # missing `valid` metadata → FAIL OPEN (no suppression), per the docstring promise
        # (Cx 369 #2) — a placeless NPC is already never-present via _colocated anyway.
        return placed_at is not None and dep_at >= placed_at
    except Exception:
        return False


def _colocated(npc_chain: list, scene: str, player_chain: list) -> bool:
    """Is an NPC present in the player's scene, CONTAINMENT-AWARE (founder bug: NPCs
    the cold open narrates as present were going inert under a brittle exact `in ==
    scene` match)? Present if the NPC is in the scene or anywhere WITHIN it (scene on
    the NPC's location chain), or their immediate place sits on the PLAYER's own chain
    (same area at a coarser grain). A person with NO location is never present."""
    return bool(npc_chain) and (scene in npc_chain or npc_chain[0] in player_chain)


@contextmanager
def _phase(trace: "TurnTrace", name: str):
    """Record a section's wall-clock into `trace.timings` (the optimization surface).
    Accumulates if a name recurs; negligible overhead, always on."""
    t = _time.perf_counter()
    try:
        yield
    finally:
        trace.timings[name] = round(trace.timings.get(name, 0.0)
                                    + (_time.perf_counter() - t), 2)


def _parallel(thunks: list) -> list:
    """Run independent, BLOCKING model-call thunks concurrently and return their
    results in the SAME order. Each cohort call does its own `asyncio.run` with a
    fresh per-call httpx client, so worker threads are safe; the win is collapsing
    the per-NPC calls (independent network I/O) from serial into one batch. A thunk
    that raises yields its exception object (callers already fail-open per NPC).
    Only the slow MODEL calls go in here — engine reads/commits stay on the main
    thread."""
    if not thunks:
        return []
    if len(thunks) == 1:
        try:
            return [thunks[0]()]
        except Exception as exc:  # noqa: BLE001 — mirror the per-call fail-open
            return [exc]
    out: list = [None] * len(thunks)
    with ThreadPoolExecutor(max_workers=min(len(thunks), 6)) as ex:
        futs = {ex.submit(t): i for i, t in enumerate(thunks)}
        for fut, i in futs.items():
            try:
                out[i] = fut.result()
            except Exception as exc:  # noqa: BLE001
                out[i] = exc
    return out

_ABSENT = object()
_PIN_CAP = 6  # max pins surfaced per turn (Cx 062: cap + stable order)
#: How many recent beats (player action + narration) to carry as the narrator's
#: short-term memory. The narrator is called STATELESS each turn (fresh prompt, no
#: persistent conversation), so this rolling window IS its memory — keep it RICH
#: (founder), not clipped to one beat. Bounded so the briefing can't grow forever.
import os as _os  # noqa: E402
_RECENT_TURNS = max(1, int(_os.getenv("CONSTRUCT_RECENT_TURNS", "8")))
#: Beats aging past the verbatim window are folded into a durable NARRATIVE MEMORY
#: (Kernos-style compaction at boundaries) — host-side, never canon. Compaction
#: runs in batches of this many aged beats, so the memory cohort fires occasionally
#: (not every turn). Fail-open: a miss never breaks the turn.
_COMPACT_BATCH = max(1, int(_os.getenv("CONSTRUCT_COMPACT_BATCH", "4")))
#: A conclusory commitment is "earned" once the player has had a real chance to play —
#: this many turns in, OR the arc is climax-ready. (Guards turn-1 abruptness WITHOUT
#: requiring the engine to have put the answer in the player frame — the card model.)
_MIN_COMMIT_TURN = max(1, int(_os.getenv("CONSTRUCT_MIN_COMMIT_TURN", "3")))
#: (Retired 2026-06-25, founder ruling / Cx 173: turns never force a conclusion. The post-climax
#: turn-count window `K_POSTCLIMAX` and the `session:reckoning_ready` turn-stamp are gone — a
#: commitment-owned arc stays ready indefinitely; only a landed commitment or an AUTHORED
#: diegetic-time/loss `failure_when` closes it. `_reckoning_ready` survives as a narrator nudge only.)
_TRANSCRIPT = "session:transcript"
_MEMORY = "session:narrative_memory"
#: The narrator's prose is staged here, NOT canon, so the ingest gate can
#: catch a contradiction of established canon before it overwrites it
#: (GATED-INGEST-COHORT; Cx round-robin). Non-contradicting rows promote to
#: canon; a row that changes an established value stays quarantined here for
#: arc review. Narrator-origin is stamped via `source` (PB 067).
_PROPOSED = "proposed:main"
_NARRATOR_SOURCE = "narrator"
#: Non-diegetic narrator "entities" the extraction must never canonize or use as a
#: container (the phantom `person:narrator` coreference bug — see the promotion gate).
_NARRATOR_PHANTOM = {"narrator", "person:narrator", _NARRATOR_SOURCE,
                     f"person:{_NARRATOR_SOURCE}"}


# NB the narration-VOICE phantom predicate (`person:narrator`/`unknown_speaker`) now lives in
# `construct/resolve.py` (`is_voice`) — the resolver drops these at the extract boundary, so the
# promote-gate copy was stripped (verified-then-strip, Cx 313). `_NARRATOR_PHANTOM` (above) stays:
# the deterministic take/drop guards still use it as a hard set.

#: Second-/first-person PRONOUN phantoms ("you"/"I"/"me") — the PROTAGONIST, never a separate entity.
#: Used now ONLY by the deterministic take/drop guards (a take/drop must not bind/relocate onto a
#: pronoun phantom). Extraction-time pronoun→protagonist binding is the resolver's job
#: (`resolve.is_deixis()` → `deixis_bound`); the promote-gate copy was stripped (Cx 313). EXEMPTED
#: when the world's protagonist id literally is one of these (then it IS the real entity).
_PRONOUN_PHANTOM = {"you", "person:you", "i", "person:i", "me", "person:me",
                    "myself", "person:myself", "self", "person:self"}


# NB the malformed-id predicate (`person:/you`, `place:/coffee_house`) now lives in
# `construct/resolve.py` (`is_malformed`) — the resolver drops these at the extract boundary, so the
# promote-gate copy was stripped (verified-then-strip, Cx 313).


@dataclass
class TurnTrace:
    """The --debug emission: a formatting of session/audit rows, never a
    second bookkeeping (CLI.md)."""

    turn: int
    classified: str = ""
    briefing_frames: list[str] = field(default_factory=list)
    cohort_calls: list[str] = field(default_factory=list)
    clocks_fired: list[str] = field(default_factory=list)
    beats_achieved: list[str] = field(default_factory=list)
    beats_closed: list[str] = field(default_factory=list)
    pacing: str = "hold"
    act: str = "I"  # the 3-act convergence frame this turn (I|II|III) — CONVERGENCE-TO-CONCLUSION
    nudge: str | None = None
    irony_delta_size: int = -1
    concealment_audit: str = "not-run"
    player_boundary: str = "clean"
    adjudication: str = "allowed"
    concluded: bool = False
    dropped_cohorts: list[str] = field(default_factory=list)
    furnished: list[str] = field(default_factory=list)
    point_reads: int = 0  # fallback per-key reads (the expensive kind)
    movement_status: str = ""  # route() passability: clear|blocked|obscured
    took: str = ""             # object the player took into possession this turn (obj.in=player)
    dropped: str = ""          # object the player set down this turn (obj.in=current place)
    move_debug: str = ""       # diagnostic: raw moves_to + refer outcome (why a move did/didn't commit)
    movement_obstruction: dict | None = None  # the blocking facts, for narration
    npcs_departed: list = field(default_factory=list)   # player-dismissed NPCs (departed_scene events)
    npcs_moved_with: list = field(default_factory=list)  # companions committed alongside the player move
    npcs_joined: list = field(default_factory=list)      # standing companionship committed this turn (#82)
    world_tick: list = field(default_factory=list)       # off-screen deltas committed in settle (#84; debug only)
    consequences: list = field(default_factory=list)     # ending-consequence events committed at the terminal (#96 S2)
    reveals: list = field(default_factory=list)  # (a,b) pairs correlated this turn (AKA reveal beats)
    outcome: str | None = None  # arc_outcome this turn: won|lost|None
    terminal_kind: str = ""     # #95: ""|"died" — transports must not infer "ended means continueable"
    peril: str = ""             # #95 debug: "staged"|"standing"|"cleared"|"" this turn
    vocative: str = ""          # #93 debug: "token->person:id (present|ABSENT)" when a title address resolved
    memory: str = ""            # #97 debug: the Remembrancer's stirred memory this turn (empty = silent)
    distance_unknown: str = ""  # #101 inversion: "place:a->place:b" when the map can't prove a local move
    deliberating: str = ""      # #102: the journey held for the player's own weighing (founder-shaped)
    journey_est: int = -1       # #102: a pre-commit elapsed estimate to reuse (never re-priced)
    same_place: bool = False    # a synonym for the current room bound already-here — no move, no time charge
    commitment: str = ""        # the player's conclusory commitment this turn (if any)
    commitment_grade: str = ""  # vindicated|partial|wrong|pyrrhic — graded outcome (epilogue flavor)
    commitment_bounced: bool = False  # commit attempted but required coverage incomplete → non-terminal bounce (COMMITMENT-AS-EFFECT)
    commitment_clarified: str = ""    # #88A: the move lacked a stage; the clarification beat rendered instead of a judgment
    main_fallout: list = field(default_factory=list)  # concrete canon consequences of a hollow/unjust main landing (caused_by the conclusion) — next-episode fuel
    events_fired: list = field(default_factory=list)  # authored event_occurs kinds that fired this turn (EVENT-OCCURS-FIRING) — the act-beats that achieved
    conclusion_shape: str = ""  # OUTCOME_SHAPE from pillar coverage (the EFFECT — STORY-SHAPES §0a)
    conclusion_basis: str = ""  # one-line why, for the epilogue + debug surface
    learned_clues: list = field(default_factory=list)  # clue ids surfaced into the player frame this turn
    discovered: list = field(default_factory=list)  # off-scene cast ids whose whereabouts the player learned this turn
    adapted: list = field(default_factory=list)  # (lane, pillar_id) the make-it-real doorway applied this turn (NARRATION-DISCIPLINE)
    weave_decision: str = ""    # story-governance: let_run|pepper_hook|deliver_card (CARD-WEAVING)
    weave_card: str = ""        # the card woven this turn (if any)
    floor_remaining: list = field(default_factory=list)  # floor-debt card ids still un-proposed
    terminal: bool = False  # this turn ended the scenario (win_loss mode + outcome)
    lifecycle: str = "active"  # main arc lifecycle this turn (won|lost|cancelled|incompletable|active)
    arc_fallout: list = field(default_factory=list)  # side arc ids that reached a terminal this turn
    generated: list = field(default_factory=list)  # arc ids minted by the DM generator this turn (P2)
    time_now: str = ""       # diegetic clock shown this turn (e.g. "Day 2, dusk")
    time_advanced: int = 0   # in-world minutes this turn consumed (DIEGETIC-TIME)
    pins: list = field(default_factory=list)  # (pin_id, scope_kind, salience) surfaced this turn
    gauge_levels: dict = field(default_factory=dict)  # gauge_id -> folded level after this turn's drain (GAUGE)
    resolver: list = field(default_factory=list)  # ENTITY-AUTHORITY resolver receipts (id, attr, reason) — debug
    contradictions: list = field(default_factory=list)  # narrator rows quarantined (changed established canon)
    quarantined: list = field(default_factory=list)  # narrator rows quarantined (unlicensed assertion of an arc key)
    laws: list = field(default_factory=list)  # WORLD LAWS (#105): law names briefed this turn (reserved lane)
    reshape: str = ""  # WORLD-CHANGING AGENCY: the narrator directive for a canon reshape committed this turn (flag-gated)
    replanned: str = ""  # the new main arc id if a reshape re-aimed the arc mid-story (flag-gated)
    reshape_entities: list = field(default_factory=list)  # visible committed reshape entity ids (carried into next-turn scope)
    timings: dict = field(default_factory=dict)  # per-section wall-clock (s) this turn — optimization surface
    briefing: str = ""  # the FULL assembled narrator briefing (the directives that drove the prose) — mechanics log

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class TurnResult:
    prose: str
    trace: TurnTrace
    exit_requested: bool = False  # player asked (OOC) to leave/start over → transport confirms
    # TURN-LATENCY dumbfire (founder 2026-06-28): the post-narrate bookkeeping tail — extract the
    # narrator's facts to canon, mirror, append the transcript, compact memory, advance diegetic
    # time. None of it changes the prose just returned; it only feeds FUTURE turns. The caller runs
    # it in the BACKGROUND so the player sees the text sooner, and JOINS it before the next turn
    # (so a back-to-back message can't start a turn before the prior settle finished — the single
    # PB SQLite connection demands that ordering). None for early returns (ooc/exit/question/denial).
    settle: Any = None  # a zero-arg callable, or None


def _player_frame(arc: Arc) -> str:
    return f"knows:{arc.protagonist}"


class _FailOpenIngest:
    """THE CLIMAX SHIELD (task #89, eval: hedgetest's conclusory turn DIED to a PB
    declaration raise — 'cannot declare semantics for attribute … after folded data exists').
    Wraps the porcelain for the TURN's duration: any `ingest_structured` raise is logged
    LOUDLY, noted on the trace, and returns an empty receipt — the prose is the player-facing
    deliverable and a bookkeeping error must never sink the turn (same policy the post-render
    extraction already had). Reads and every other verb delegate untouched."""

    def __init__(self, porcelain: Any, trace: "TurnTrace"):
        self._p = porcelain
        self._trace = trace

    def __getattr__(self, name: str) -> Any:
        return getattr(self._p, name)

    def ingest_structured(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._p.ingest_structured(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — fail-open by design
            logger.error("in-turn ingest failed (rows dropped, turn continues): %s", exc)
            try:
                self._trace.dropped_cohorts.append(f"ingest ({exc})")
            except Exception:
                pass
            return {"rows": []}


def _receipt_rows(receipt: Any) -> list[dict]:
    return receipt.to_dict()["rows"] if hasattr(receipt, "to_dict") else receipt["rows"]


def _partition_frames(items: list) -> tuple[list[dict], list[str]]:
    """FRAME PARTITION for extraction output (Cx 546/552) — the FIRST step after
    `extract()`, before name reconstruction and the resolver, on BOTH channels
    (narrator settle + player input). Extraction items MAY carry their own `frame`
    key (PB's schema makes it optional), and PB's `ingest_structured(frame=...)`
    default applies only to unframed items (per-item frames win — the sanctioned
    telling-scene mixed batch, PB 543). The host therefore decides HERE what each
    channel admits:
    - frame absent or exactly "canon" → accepted; the redundant key is stripped
      (the staging/commit destination is the host's, never the model's).
    - ANY other value — knows:<npc> knowledge copies, malformed empties —
      → FAIL-CLOSED dropped (returned as labels for channel-specific telemetry).
      A knowledge copy through an ungated channel corrupts NPC/player knowledge
      (Cx 546's breach); it waits for the knowledge-promotion gate (RFC-002).
    Runs BEFORE `reconstruct_names()`/`resolve_rows()` so a dropped row can leave
    NO derivative — no synthetic name row, no first-mention stub (Cx 552).
    Returns (accepted_copies, dropped_labels)."""
    accepted: list[dict] = []
    dropped: list[str] = []
    for row in items:
        if not isinstance(row, dict):
            accepted.append(row)
            continue
        fr = row.get("frame")
        if fr is None or fr == "canon":
            accepted.append({k: v for k, v in row.items() if k != "frame"})
        else:
            dropped.append(f"{row.get('entity')}/{row.get('attribute')}→{fr!r}")
    return accepted, dropped


def _snap_or_empty(p: Any, scope: list[str], frame: str = "canon",
                   *, as_of: float | None = None) -> dict:
    if not scope:
        return {"facts": []}
    ids = sorted(set(scope))
    snap = p.snapshot(ids, frame=frame, as_of=as_of)
    if "error" not in snap:
        return snap
    # The strict snapshot rejected the WHOLE batch because some id isn't a KNOWN entity (e.g.
    # an arc-scope `fact:*` beat target never asserted in canon, like fact:verdict). Don't lose
    # the whole table — that drops every NPC's narrated `name` and breaks interview delivery for
    # a player who addresses a suspect BY NAME (the live staged-whodunit bug). Recover the known
    # subset by probing per id (only on this failure path, so the happy path is unchanged).
    logger.warning("snapshot error for %s on %s: %s — recovering known subset per-id",
                   frame, ids, snap["error"])
    facts: list = []
    for e in ids:
        try:
            one = p.snapshot([e], frame=frame, as_of=as_of)
        except Exception:
            continue
        if "error" not in one:
            facts.extend(one.get("facts", []))
    return {"facts": facts}


def _route_obstruction(p: Any, origin: str | None, target: str | None,
                       *, as_of: float | None = None) -> dict | None:
    """First non-clear segment on origin->target via PB route() (RFC-003), or
    None. Fail-open: any route error => None => move proceeds unchecked. A
    `blocked` segment carries `evidence` (the portal's blocking fact); an
    `obscured` one a computed `unknown_basis`. `as_of` (Cx 255): read passability
    at the play horizon, so a future blocked/open portal can't alter movement now."""
    if not origin or not target or origin == target:
        return None
    try:
        r = p.route(origin, target, as_of=as_of)
    except Exception as exc:
        logger.warning("route() unavailable, movement unchecked: %s", exc)
        return None
    for seg in r.get("segments", []):
        if seg.get("status") in ("blocked", "obscured"):
            return seg
    return None


def _route_connects(p: Any, origin: str | None, target: str | None,
                    *, as_of: float | None = None) -> bool:
    """The nearness inversion's ROUTE arm (Cx 458): does a DIRECT, passable way
    connect origin and target? `_route_obstruction()` reports only problems and
    returns None for a clear route, so it can never prove nearness — this is the
    dedicated existence read. Direct = the termini are immediately connected
    (route length 2: a door, corridor, lane, lift); a multi-hop path proves a
    network, not nearness, and stays with the model's pricing. Fail-closed: any
    route error proves nothing."""
    if not origin or not target or origin == target:
        return False
    try:
        r = p.route(origin, target, as_of=as_of)
    except Exception:  # noqa: BLE001 — missing capture proves nothing
        return False
    _route = r.get("route") or []
    # DIRECT includes PB's portal shape (Cx 465 #1): place -> obj:door -> place is a
    # door, not a trek — near iff NO intermediate node is itself a place (an
    # intermediate place = genuine multi-hop travel, which stays with the model).
    return (r.get("status") in ("clear", "obscured") and len(_route) >= 2
            and not any(str(n).startswith("place:") for n in _route[1:-1]))


def _journey_accept_key(origin: str | None, dest_key: str, threshold: float) -> str:
    """#102 marker key (Cx 465 #3): a FIXED-SIZE digest over all four components
    (origin | destination | hazard identity | deadline coordinate) — truncation can
    never substring away the coordinate, so a moved deadline always re-warns."""
    import hashlib
    raw = f"{origin or ''}|{dest_key}|time_deadline|{int(threshold)}"
    return "jacc_" + hashlib.sha1(raw.encode()).hexdigest()[:20]


def _deadline_remaining(arc: Any, world: Any) -> tuple[float, float] | None:
    """#102 (Cx 457): the live diegetic time-deadline's remaining budget —
    (remaining_minutes, threshold) from the arc's `failure_when` Quantity over the
    elapsed clock, or None when the story authored no deadline. Deterministic reads
    only; the hazard must be ESTABLISHED, never inferred."""
    fw = getattr(arc, "failure_when", None)
    if fw is None:
        return None
    from construct.arc.conditions import Quantity, atoms_of
    from construct.clock import ELAPSED_ATTR, ELAPSED_ENTITY, read_clock
    for a in atoms_of(fw):
        if (isinstance(a, Quantity) and a.entity == ELAPSED_ENTITY
                and a.attribute == ELAPSED_ATTR and getattr(a, "cmp", "") in (">=", ">")):
            try:
                thr = float(a.value)
                cur = float(read_clock(world).minutes)
            except Exception:  # noqa: BLE001 — an unreadable clock is no hazard
                continue
            return max(0.0, thr - cur), thr
    return None


def _mirror_rows(p: Any, rows: list[dict], frame: str,
                 canon_table: dict[tuple[str, str], object], trace: TurnTrace,
                 *, as_of: float | None = None) -> None:
    """Mirror freshly-ingested canon facts into a knows: frame. Values
    come from the canon snapshot; point-read fallback for out-of-scope
    entities only. `as_of` (Cx 255): the fallback point-read honors the play
    horizon, so a future source winner can't be mirrored over the current value."""
    items = []
    for row in rows:
        if row.get("frame") not in (None, "canon"):
            continue
        key = (row["entity"], row["attribute"])
        value = canon_table.get(key, _ABSENT)
        if value is _ABSENT:
            st = p.state(row["entity"], row["attribute"], as_of=as_of)
            trace.point_reads += 1
            if st["status"] != "known":
                continue
            value = st["fact"]["value"]
        items.append({"entity": row["entity"], "attribute": row["attribute"],
                      "value": value})
    if items:
        # batch durability classification (one model call, not per-row) — the
        # per-turn latency fix (PB INGEST-HARDENING / letter 075).
        p.ingest_structured(items, frame=frame, classify="batch")


def furnish_scene(p: Any, scene: str | None, player_frame: str,
                  canon_table: dict, trace: TurnTrace,
                  *, as_of: float | None = None) -> None:
    """Fiction-mode scene furnishing (letter 020 finding B): seed the
    description thunk through the gate, force via `resolve()` (resolver
    authority, generated provenance, constraint inheritance), mirror to
    the player frame. Memoized — stable on return; lazy — current scene
    only. `as_of` (B' S3): check existing description as-of the play horizon, so an
    aftermath description for this scene never suppresses opening furnishing."""
    if scene is None or canon_table.get((scene, "description")) is not None:
        return
    st = p.state(scene, "description", as_of=as_of)
    trace.point_reads += 1
    if st["status"] != "unknown":
        return
    p.ingest_structured([{
        "entity": scene, "attribute": "description",
        "value": {"policy": "invent_under_canon"},
        "value_type": "unresolved",
    }])
    out = p.resolve(scene, "description")
    if out.get("status") != "resolved":
        logger.warning("scene furnish did not resolve: %s -> %s", scene, out.get("status"))
        return
    items = [{"entity": f["entity"], "attribute": f["attribute"], "value": f["value"]}
             for f in out.get("facts", []) if f.get("value") is not None]
    if items:
        p.ingest_structured(items, frame=player_frame, classify="batch")
        for item in items:
            canon_table[(item["entity"], item["attribute"])] = item["value"]
    trace.furnished.append(f"{scene}·description")
    logger.info("scene furnished: %s", scene)


def _table(snap: dict) -> dict[tuple[str, str], object]:
    return {(f["entity"], f["attribute"]): f["value"] for f in snap.get("facts", [])}


def _mint_held_object(world: Any, protagonist: str, description: str,
                      hint: str = "", *, at: float | None = None) -> str | None:
    """Mint a FRESH, host-owned `obj:<slug>` held by the protagonist (IMPROV-AND-AUTHORITY).
    HOST-OWNED, FRESH id (Cx 230): a cohort's `item_id` is at most a slug HINT, never
    authority — a returned EXISTING id would pollute that object's location and falsely
    allow. We always mint a fresh id, never reusing/mutating an existing entity. Returns the
    new id, or None if the write didn't land. Shared by the equipment grant (produce gear)
    and the take grant (pick an ordinary object out of the scene)."""
    words = (description or "").lower().split()
    while words and words[0] in {"my", "the", "a", "an", "your", "his", "her",
                                 "their", "its", "some"}:
        words.pop(0)
    slug = "".join(c if (c.isalnum() or c == "_") else "_"
                   for c in "_".join(words)).strip("_") or "thing"
    reads = PorcelainWorldReads(world)
    hint = (hint or "").strip()
    item_id = hint if (hint.startswith("obj:") and not reads.has_entity(hint)) else f"obj:{slug}"
    n = 1
    while reads.has_entity(item_id):   # never collide with an established entity
        item_id, n = f"obj:{slug}_{n}", n + 1
    name = " ".join(words)[:60].strip()
    rows = [
        {"entity": item_id, "attribute": "kind", "value": "object"},
        {"entity": item_id, "attribute": "in", "value": protagonist, "value_type": "entity"},
    ]
    if name:  # a readable name so the narrator can refer to it as the player named it
        rows.append({"entity": item_id, "attribute": "name", "value": name})
    if at is not None:
        for r in rows:
            r.setdefault("valid_from", at)
    world.porcelain.ingest_structured(rows)
    # VERIFY the grant actually made it at-hand; never claim a failed/conflicted write.
    if protagonist not in (PorcelainWorldReads(world).location_chain(item_id) or []):
        logger.warning("mint of %r did not take (%s)", description, item_id)
        return None
    return item_id


def _grant_equipment(world: Any, p: Any, protagonist: str, description: str,
                     scene: str | None, provider: Any, laws: str = "") -> bool:
    """IMPROV-AND-AUTHORITY: an unresolved required item that is ORDINARY role/personal
    equipment (a physician's bag, a detective's notebook) is GRANTED — minted as the
    protagonist's possession and committed (the world adapts), so the action stands
    instead of being denied for a missing canon object. A specific/load-bearing object
    is NOT granted. Fail-safe: no provider, a 'no' verdict, or any error → False (deny)."""
    if provider is None:
        return False
    try:
        from construct import cohorts
        v = cohorts.equipment_check(provider, actor=protagonist, item=description,
                                    scene=scene or "", manner="carry", laws=laws)
        if not isinstance(v, dict) or not v.get("ordinary_equipment"):
            return False
        item_id = _mint_held_object(world, protagonist, description, v.get("item_id") or "")
        if item_id is None:
            return False
        logger.info("adjudicate: granted ordinary equipment %r → %s (held by %s)",
                    description, item_id, protagonist)
        return True
    except Exception:
        logger.exception("equipment grant failed; denying")
        return False


def _grant_taken_object(world: Any, protagonist: str, description: str,
                        scene: str | None, provider: Any, at: float,
                        laws: str = "") -> str | None:
    """IMPROV-OBJECT PERMANENCE (founder: "a mug from the bar doesn't not exist"): when the
    player TAKES an object that isn't an established canon entity, grant it world permanence
    by minting a fresh `obj:` held by the player — IF it's an ordinary thing plainly present
    in the scene. A specific/named/load-bearing object is NOT minted by fiat (the narrator
    handles that honestly). Returns the new id, or None (no grant). Fail-safe: any miss → None."""
    if provider is None:
        return None
    try:
        from construct import cohorts
        v = cohorts.equipment_check(provider, actor=protagonist, item=description,
                                    scene=scene or "", manner="take", laws=laws)
        if not isinstance(v, dict) or not v.get("ordinary_equipment"):
            return None
        item_id = _mint_held_object(world, protagonist, description,
                                    v.get("item_id") or "", at=at)
        if item_id is not None:
            logger.info("take: granted ordinary present object %r → %s (held by %s)",
                        description, item_id, protagonist)
        return item_id
    except Exception:
        logger.exception("take grant failed; not granting")
        return None


_MOVE_LEAD_STOP = {"the", "a", "an", "to", "into", "toward", "towards", "over", "down", "up",
                   "back", "my", "his", "her", "their", "its", "our", "go", "head", "walk",
                   "of", "at", "in", "on"}

#: A move whose destination reduces to ONE of these (after stripping lead words) is DEICTIC /
#: directional, not a named place — minting `place:inside`/`place:back` would be junk (Cx 288).
#: The narrator handles "go back / go inside / go outside" diegetically against the real geography.
_DEICTIC_DEST = {"", "back", "inside", "outside", "in", "out", "there", "here", "away",
                 "around", "forward", "onward", "through", "off", "on", "somewhere", "home",
                 "left", "right", "further", "deeper", "closer", "nearer", "ahead", "beyond"}

#: Prepositions that begin a LOCATIVE TAIL ("rain barrel BY the shed"): the destination HEAD is the
#: last noun BEFORE the tail (Cx 325 — head matters: "back lane by the sheds"→lane allows;
#: "rain barrel by the shed"→barrel blocks).
_DEST_PREP = {"by", "near", "of", "on", "at", "behind", "beside", "beyond", "under", "over",
              "in", "past", "across", "down", "up", "along", "outside", "inside", "against", "round"}
#: FIXTURE / object head-nouns: a move "to" one of these is IN-SCENE repositioning, NOT a navigable
#: place — never mint a `place:` for it (Cx 325: "step to the table" minted place:table and walked
#: the player away from the colocated cast). Lexical because fixtures are often prose, not structured.
_FIXTURE_HEADS = {
    "table", "desk", "chair", "stool", "bench", "window", "door", "doorway", "barrel", "lamp",
    "lantern", "stove", "counter", "shelf", "shelves", "grate", "fire", "fireplace", "hearth",
    "mantel", "map", "paper", "papers", "body", "corpse", "cart", "case", "packet", "bed", "cabinet",
    "drawer", "sink", "basin", "crate", "box", "sack", "ledger", "book", "notebook", "blotter",
    "regulator", "wall", "floor", "ceiling", "rail", "post", "pillar", "column", "fountain", "statue",
    "bar", "till", "register", "safe", "chest", "trunk", "rack", "easel", "podium", "lectern",
    # critic-campaign run 1 (#94): "the cellar grating and the service hatch" minted a
    # phantom PLACE and the whole endgame floated in it — these are in-scene fixtures.
    "grating", "hatch", "keyhole", "hinge", "gutter", "drain", "threshold"}


def _dest_head(moves_to: str) -> str:
    """The HEAD noun of a move destination phrase, for the fixture/place split (Cx 325). Strips lead
    words, then takes the last word of the core noun phrase BEFORE any locative tail ('rain barrel by
    the shed' → 'barrel'; 'back lane by the warehouse sheds' → 'lane'; 'the table' → 'table')."""
    words = [w.strip(".,;:!?'\"") for w in (moves_to or "").lower().split()]
    words = [w for w in words if w]
    while words and words[0] in _MOVE_LEAD_STOP:
        words.pop(0)
    core = []
    for w in words:
        if w in _DEST_PREP and core:
            break
        core.append(w)
    return core[-1] if core else ""


def _names_undiscovered_dest(moves_to: str, cbi: dict, is_undiscovered, name_of) -> bool:
    """Whether an UNRESOLVED move destination NAMES an undiscovered offscene suspect or their
    authored location (Cx review #1). The entitlement gate runs only on a RESOLVED target, so a
    guessed/unresolved VARIANT of such a name must ALSO be denied the move-permanence mint — else
    the player teleports near an undiscovered suspect by naming a variant. Token match on the
    suspect's id/name/role and on their location's id/name. `name_of(entity)->str` resolves the
    display name (the movement step runs BEFORE the canon snapshot, so read it live)."""
    low = (moves_to or "").lower()
    for n in cbi.values():
        if not is_undiscovered(n):
            continue
        if _names_entity(n.node_id, low, name=str(name_of(n.node_id) or ""),
                         role=getattr(n, "surface_role", "")):
            return True
        loc = getattr(n, "location", "")
        if loc and _names_entity(loc, low, name=str(name_of(loc) or "")):
            return True
    return False


def _match_known_place(moves_to: str, candidates, reads, name_of) -> str | None:
    """Resolve an unresolved move to an ALREADY-KNOWN place by token — a looser fallback than
    `refer`, so "my own office" RETURNS to the existing place instead of minting a twin (founder
    cohesion test: returning home minted a duplicate office). Only place-kinded candidates; returns
    the id on a UNIQUE match, else None (0 → genuine improv → mint; >1 → ambiguous → don't guess).
    NB the broad case (a known place NOT in this candidate set) still rides PB coreference (#56)."""
    low = (moves_to or "").lower()
    hits = []
    for e in candidates:
        # prefix-is-type (Cx 327): a `place:`-prefixed candidate IS a place; do NOT filter on the
        # `kind` string (authored places carry DESCRIPTIVE kinds like "yard"/"murder scene…", which
        # the old kind∈{place,room,site} filter wrongly dropped → a known-place reuse miss → duplicate).
        if not e or not str(e).startswith("place:"):
            continue
        if _names_entity(e, low, name=str(name_of(e) or "")):
            hits.append(e)
    return hits[0] if len(hits) == 1 else None


def _match_held_object(drops: str, held: set, reads: Any) -> str | None:
    """Resolve a DROP phrase to an object the player ACTUALLY HOLDS, by token — you can only set
    down what you hold. Prefer this over global `world.refer`, which can pick a FRAGMENTED same-named
    twin: the take-mint's collision-avoiding `obj:pencil_1` (the held one) vs an extraction's
    `obj:pencil` (founder live cohesion test, Cx 297 follow-on — refer resolved 'the pencil' to the
    un-held twin, so the drop never fired). Unique held match → its id; 0 or >1 → None (fall back to
    refer). Matches on the id-stem/name tokens via `_names_entity`."""
    low = (drops or "").lower()
    hits = []
    for e in held:
        if not str(e).startswith("obj:"):
            continue
        try:
            nm = reads.state(e, "name")
        except Exception:
            nm = None
        if _names_entity(e, low, name=str(nm or "")):
            hits.append(e)
    return hits[0] if len(hits) == 1 else None


#: Function words that never distinguish a place reference (the contained-mint matcher).
_EMBED_STOP = {"the", "a", "an", "of", "to", "at", "in", "on", "my", "own", "back",
               "into", "over", "with", "and"}


def _embedded_container(moves_to: str, roster: list) -> tuple[str, str] | None:
    """#91 (Cx 387): a COMPOUND destination ("the Liddell warehouse, to the foreman's
    office") embeds an ESTABLISHED place — minting the tail as a TOP-LEVEL place forks the
    map and strands whoever is in the real one (the probe's parallel office). Match the
    phrase's distinctive tokens against the entitled place roster; a unique best match plus
    a non-matching tail segment → (container_id, tail_phrase) so the mint NESTS the new
    place inside the established one (chain-containment presence then colocates honestly).
    Deterministic; None on no/ambiguous match or when the phrase IS the container."""
    phrase = (moves_to or "").lower()
    ptoks = {t for t in re.split(r"[^a-z0-9]+", phrase) if len(t) > 3 and t not in _EMBED_STOP}
    if not ptoks:
        return None
    best: tuple[int, str, set] | None = None
    tied = False
    for pid, _label in roster or []:
        stoks = {t for t in str(pid).split(":", 1)[-1].split("_")
                 if len(t) > 3 and t not in _EMBED_STOP}
        # Cx 449: name/kind evidence widens the HIT surface (place:north named "North
        # Village" is findable by "village"). Match strength must still be EARNED:
        # either the original slug ratio holds, or the hit covers at least half the
        # place's NAME tokens — a lone kind-word brush ("...a rain-wet yard") never
        # qualifies a container on its own.
        _lcore = str(_label).split(" (the room", 1)[0]
        ltoks = {t for t in re.split(r"[^a-z0-9]+", _lcore.lower())
                 if len(t) > 3 and t not in _EMBED_STOP}
        ntoks = {t for t in re.split(r"[^a-z0-9]+", _lcore.split(" — ", 1)[0].lower())
                 if len(t) > 3 and t not in _EMBED_STOP}
        hit = (stoks | ltoks) & ptoks
        score = len(hit)
        _strong = ((stoks and score * 2 >= len(stoks))
                   or (ntoks and len(hit & ntoks) * 2 >= len(ntoks)))
        if score < 1 or not _strong:
            continue  # too weak a brush to be a reference
        if best is not None and score == best[0]:
            tied = True
        elif best is None or score > best[0]:
            best, tied = (score, pid, hit), False
    if best is None or tied:
        return None
    _score, container, hit = best
    segments = [s.strip() for s in re.split(r",|;|\bat\b|\bin\b|\bwithin\b|\binside\b|\bto\b",
                                            phrase) if s.strip()]
    # a tail must carry a DISTINCTIVE token of its own — "back to the study" leaves only
    # the stop-word "back", which is the reuse path's business ("go back"), not a nest.
    tails = [s for s in segments
             if not (hit & {t for t in re.split(r"[^a-z0-9]+", s) if t})
             and any(len(t) > 3 and t not in _EMBED_STOP
                     for t in re.split(r"[^a-z0-9]+", s))]
    if not tails:
        return None  # the whole phrase names the container — nothing to nest
    return container, tails[-1]


def _persons_under(p: Any, scene: str | None, as_of: float | None,
                   max_nodes: int = 64) -> set:
    """The scene's person ids by CONTAINMENT WALK (#94 F12, Cx 408 option 1): the
    presence AUTHORITY (`_present`/`_colocated`) treats nested containment as present,
    so the candidate SOURCE must enumerate the same shape — a person in a child place
    of the player's scene is in the scene. Bounded breadth-first walk over `contents`
    (descends nested `place:` children only); persons collected; best-effort, fail-open
    SOURCE enumeration (a mid-walk error keeps what was found — `_present` is the
    authority on every candidate anyway). Shared by the classify-candidate and
    npc-phase sites so presence keeps ONE shape."""
    out: set = set()
    if not scene:
        return out
    try:
        seen = {str(scene)}
        frontier = [str(scene)]
        while frontier and len(seen) < max_nodes:
            nxt: list = []
            for node in frontier:
                for c in (p.contents(node, as_of=as_of) or []):
                    c = str(c)
                    if c in seen:
                        continue
                    seen.add(c)
                    if c.startswith("person:"):
                        out.add(c)
                    elif c.startswith("place:"):
                        nxt.append(c)
            frontier = nxt
    except Exception:  # noqa: BLE001 — enumeration is a source, never an authority
        return out
    return out


def _grant_moved_place(world: Any, protagonist: str, moves_to: str, *, at: float,
                       p: Any = None, origin: str | None = None,
                       as_of: float | None = None,
                       roster: list | None = None,
                       hold_check: Any = None) -> tuple[str | None, dict | None]:
    """MOVEMENT PERMANENCE (founder live: "I said I went to Harrow's office" but canon kept me at
    the post office). A move to a NAMED place that didn't resolve to an established canon place (an
    improvised/narrated location) MINTS a fresh `place:<slug>` and commits the protagonist INTO it,
    so a narrated trip is REAL — the next turn renders the new scene, not the stale prior one, and
    only the cast actually there is present. The caller skips this for an entitlement-blocked or
    secret-brushing destination (the investigation gating + concealment stay authoritative).
    #91 (Cx 387): a compound phrase embedding an established roster place mints CONTAINED in it,
    and the grant obeys the SAME passability discipline as resolved travel (route to the container
    / an existing reused place is checked; blocked → no commit). Returns (place_id, obstruction);
    (None, seg) = blocked; (None, None) = no grant. Reuses an existing `place:<slug>` on match."""
    container: str | None = None
    _mint_container: tuple[str, str] | None = None  # (tail phrase, kind) — a NOVEL container to mint
    _embed = _embedded_container(moves_to, roster or [])
    if _embed is not None:
        container, moves_to = _embed
    else:
        # #101 MINT-ID HYGIENE (Cx 445): a locative TAIL must never be baked into the
        # child's identity — "Dr. Ames's consulting room in the village" is a
        # consulting room CONTAINED in a village, not one long room name. A tail that
        # names a KNOWN place was already caught by _embedded_container above; here the
        # tail is NOVEL or generic: split it off, and either bind it (unique roster
        # token match), flag ambiguity (two known villages → the ask path), or mint a
        # thin container shell (kind/name only).
        _loc = re.match(r"^(.*?)\s+(?:in|at|inside|within)\s+(?:the\s+)?(.{3,60})$",
                        (moves_to or "").strip(), re.IGNORECASE)
        if _loc and _loc.group(1).strip():
            _child, _tail = _loc.group(1).strip(), _loc.group(2).strip().rstrip(".,;")
            _ttoks = {t for t in re.split(r"[^a-z0-9]+", _tail.lower()) if len(t) > 3}

            def _place_evidence(pid: str, lb: str) -> set:
                # Cx 449 blocker: the container must match on WORLD FACTS (name/kind
                # in the roster label), never only on how the id happens to be worded
                # — place:north with name "North Village" IS a village.
                _core = str(lb).split(" (the room", 1)[0]  # drop the current-room marker
                return ({t for t in str(pid).split(":", 1)[-1].split("_") if len(t) > 3}
                        | {t for t in re.split(r"[^a-z0-9]+", _core.lower())
                           if len(t) > 3})

            _thits = [pid for pid, _lb in (roster or [])
                      if _ttoks & _place_evidence(pid, _lb)]
            if len(_thits) > 1:
                # "in the village" with two known villages: ASK, never guess (founder)
                return None, {"status": "ambiguous", "evidence": f"container {_tail!r} "
                              f"matches {len(_thits)} known places"}
            if len(_thits) == 1:
                container, moves_to = _thits[0], _child
            else:
                _tkind = _tail.lower().split()[-1]
                _mint_container = (_tail, _tkind if _tkind in _PLACE_LIKE_KINDS
                                   else "place")
                moves_to = _child
    words = (moves_to or "").lower().split()
    while words and words[0].strip(".,;:!?'\"") in _MOVE_LEAD_STOP:
        words.pop(0)
    slug = "".join(c if (c.isalnum() or c == "_") else "_"
                   for c in "_".join(words)).strip("_")
    if slug in _DEICTIC_DEST:
        # deictic/directional ("go back", "go inside") — not a named place; let the narrator
        # handle it against the real geography rather than mint `place:back` / `place:inside`.
        return None, None
    reads = PorcelainWorldReads(world)
    place_id = f"place:{slug}"
    # PASSABILITY ON THE GRANT PATH (Cx 387 hard constraint): the mint must not teleport
    # through a blocked route. The checkable target is the CONTAINER (it exists in canon)
    # or an existing reused place; a genuinely fresh top-level mint has no route data and
    # degrades to clear, exactly like missing capture elsewhere.
    seg: dict | None = None
    _gate_target = container if container else (place_id if reads.has_entity(place_id) else None)
    if p is not None and origin and _gate_target:
        try:
            seg = _route_obstruction(p, origin, _gate_target, as_of=as_of)
        except Exception:  # noqa: BLE001 — missing capture degrades, never false-blocks
            seg = None
        if seg and seg.get("status") == "blocked":
            logger.info("move grant to %r blocked en route to %s", moves_to, _gate_target)
            return None, seg
    if hold_check is not None and hold_check():
        # #102 (Cx 465 #2): the route would commit — NOW the mind may weigh it,
        # before anything mints.
        return None, {"status": "deliberating"}
    # REUSE an existing `place:<slug>` regardless of its `kind` string (Cx 325): a `place:`-prefixed
    # id is already place-typed for movement, but authored places carry DESCRIPTIVE kinds ("yard",
    # "murder scene in a narrow rain-wet yard…"), so the old kind∈{place,room,site} check spuriously
    # bumped `place:bluegate_yard` → `place:bluegate_yard_1` (a duplicate of the authored yard). The
    # id namespace IS the type; reuse it. (Coreference-reuse is the right default — Cx agrees.)
    rows: list[dict] = []
    if _mint_container is not None and container is None:
        # #101: the novel container mints as a THIN SHELL (Cx 445: place/kind/name only)
        # so the child nests honestly — place:consulting_room IN place:village, never
        # place:consulting_room_in_the_village.
        _tail_phrase, _tail_kind = _mint_container
        _tslug = re.sub(r"[^a-z0-9]+", "_", _tail_phrase.lower()).strip("_")
        if _tslug and _tslug not in _DEICTIC_DEST:
            container = f"place:{_tslug}"
            if not reads.has_entity(container):
                rows += [{"entity": container, "attribute": "kind",
                          "value": _tail_kind, "timeless": True},
                         {"entity": container, "attribute": "name",
                          "value": _tail_phrase[:60]}]
    if not reads.has_entity(place_id):
        rows += [{"entity": place_id, "attribute": "kind", "value": "place", "timeless": True},
                 {"entity": place_id, "attribute": "name", "value": " ".join(words)[:60].strip()}]
        if container:
            rows.append({"entity": place_id, "attribute": "in", "value": container,
                         "value_type": "entity", "valid_from": at})
    rows.append({"entity": protagonist, "attribute": "in", "value": place_id,
                 "value_type": "entity", "valid_from": at})
    world.porcelain.ingest_structured(rows)
    chain = PorcelainWorldReads(world).location_chain(protagonist) or []
    if not chain or chain[0] != place_id:
        logger.warning("move grant to %r did not take (%s)", moves_to, place_id)
        return None, seg
    logger.info("move: granted improv destination %r → %s (player now in%s)", moves_to,
                place_id, f", nested in {container}" if container else "")
    return place_id, seg


#: S2 (#96, Cx 414 constraint 2): the DETERMINISTIC ending-consequence map — an ending
#: writes concrete canon consequence EVENTS (closed kinds, caused_by the outcome receipt);
#: presentation surfaces (the continuation bridge, weave, world-tick) select and phrase
#: them later. No model authors the fact itself. Keyed by shape outcome / grade / binary.
_ENDING_CONSEQUENCES = {
    "triumph": ("the matter's clean resolution is public — those responsible answered "
                "for it", "risen"),
    "vindicated": ("the answer held, and word of who found it travels", "risen"),
    "won": ("the matter ended as it should, and people know it", "risen"),
    "costly_victory": ("the matter ended, and what it cost is spoken of as much as the "
                       "result", "mixed"),
    "pyrrhic": ("the result stands, but so does its price — both travel together", "mixed"),
    "bittersweet": ("the matter is settled on a flawed footing, and some feel it", "mixed"),
    "partial": ("the matter is held settled, though not every question closed with it",
                "mixed"),
    "wrong": ("the matter closed on an answer that will not hold — and word of it "
              "travels", "fallen"),
    "failure": ("the matter ended badly, and everyone near it knows", "fallen"),
    "quiet_failure": ("the moment passed without an answer; the quiet itself is noticed",
                      "fallen"),
    "lost": ("the chance is gone, and the going of it is known", "fallen"),
    # #95: the player's death — what they set in motion continues without them
    "died": ("they are gone, and word of how they fell travels; what they set in "
             "motion moves on without them", "remembered"),
}

#: The world-tick elapsed floor (Cx 395 constraint 2): no tick for a member seen more
#: recently than this many diegetic minutes — quick backtracks must not churn the world.
_TICK_FLOOR_MIN = 30.0
#: Tick caps: members per tick / committed rows per member (WORLD-TICK.md).
_TICK_MAX_MEMBERS = 2


def _world_tick(world: Any, p: Any, arc: Any, trace: Any, provider: Any, turn: int, *,
                cast: Any, npcs: list, entry_scene: str | None, scene: str | None,
                live_reads: Any, minutes_now: float | None) -> None:
    """WORLD-MOVES-WITHOUT-YOU (#84, WORLD-TICK.md, Cx 395 YELLOW→build): on a committed
    scene CHANGE, one cheap call proposes small off-screen actions for up to two eligible
    cast members; screened deltas commit as ordinary canon the player DISCOVERS by
    returning. Runs in the settle tail (zero latency; effects matter next turn). Teeth:
    - eligibility from the PERSISTED last-seen markers (never transcript inference) with
      the elapsed floor; only cast the player has actually met;
    - the culprit and required-clue holders never `moved` (reachability by construction —
      drop, never repair); nothing moves INTO the player's scene; destinations only from
      the entitled place roster (undiscovered-offscene locations excluded);
    - `detail` screened by concealed tokens AND protected condition VALUES (Cx 395);
    - closed event-kind set; ≤1 action per member; fail-open everywhere."""
    try:
        if trace.movement_status not in ("clear", "obscured") or not scene \
                or scene == entry_scene:
            return
        if getattr(trace, "terminal", None) or getattr(trace, "concluded", False):
            return
        if minutes_now is None:
            return  # no diegetic clock → no honest elapsed floor → no tick
        _nodes = (cast if isinstance(cast, dict)
                  else {n.node_id: n for n in cast}) if cast else {}
        if not _nodes:
            return
        from construct.arc.executor import (
            arc_protected_keys, concealed_tokens, value_leaks,
        )
        _pkeys = arc_protected_keys(arc)
        _ctoks = concealed_tokens(_pkeys)
        # protected condition VALUES (Cx 395: token screen alone can miss a sensitive
        # value) — any protected atom's literal value is banned vocabulary for `detail`.
        _pvals: set[str] = set()
        try:
            from construct.arc.conditions import InFrame, StateIs, atoms_of
            _exprs = [b.achievable_via for b in arc.beats] + [arc.shape.world_condition,
                                                              arc.shape.premise]
            for _x in _exprs:
                for _atom in atoms_of(_x):
                    if isinstance(_atom, (StateIs, InFrame)):
                        _v = str(getattr(_atom, "value", "") or "").lower().strip()
                        if len(_v) > 3:
                            _pvals.add(_v)
        except Exception:  # noqa: BLE001
            pass
        # members who never `moved`: the culprit + holders of genuine required-pillar clues
        # (delivered-or-not — conservative; reachability holds by construction).
        _req = {pl.pillar_id for pl in getattr(arc, "pillars", ()) if pl.required}
        _anchored = {nid for nid, n in _nodes.items()
                     if getattr(n, "is_culprit", False)
                     or any(c.pillar_id in _req and c.coverage_effect == "genuine"
                            and not c.is_red_herring
                            for c in getattr(n, "holds_clues", ()) or ())}
        members: list[tuple[str, str, str]] = []
        for nid in sorted(_nodes):
            if not nid.startswith("person:") or nid == arc.protagonist or nid in (npcs or []):
                continue
            try:
                _seen = live_reads.state(nid, "last_seen_min", frame=SESSION)
                if _seen is None:
                    continue  # never met — off-screen motion of a stranger isn't felt
                if minutes_now - float(_seen) < _TICK_FLOOR_MIN:
                    continue
                _loc = p.locate(nid)
                _where = _loc[0] if _loc else ""
                if _where == scene:
                    continue  # actually here — presence owns them
                _sheet = json.dumps(p.snapshot(nid, frame=f"knows:{nid}",
                                               lens="character_sheet"))[:1200]
                members.append((nid, _where, _sheet))
            except Exception:  # noqa: BLE001
                continue
            if len(members) >= _TICK_MAX_MEMBERS:
                break
        if not members:
            return
        # the entitled destination roster: known places minus the player's scene minus
        # undiscovered-offscene cast locations (the entitlement gate holds off-screen too;
        # same predicate as the movement gate — offscene + unlearned whereabouts)
        _pframe = f"knows:{arc.protagonist}"

        def _undisc(n: Any) -> bool:
            try:
                return (getattr(n, "presence", "") == "offscene"
                        and bool(getattr(n, "location", ""))
                        and not live_reads.assertion_in_frame(
                            _pframe, n.node_id, "whereabouts", n.location))
            except Exception:  # noqa: BLE001 — unreadable = treat as undiscovered (conservative)
                return True

        _excl = {getattr(n, "location", "") for n in _nodes.values()
                 if _undisc(n) and getattr(n, "location", "")}
        _places: list[tuple[str, str]] = []
        try:
            # CANON-VISIBLE ONLY (Cx 398 blocker 1; BOUNDED-READS take-up, PB 092): the
            # roster comes from the porcelain `entities("canon", …)` verb — frame-bound
            # by construction, so plot:/session:/knows: place rows can never leak hidden
            # topology. A destination still qualifies only if its name/kind READS through the
            # horizon-bound canon surface (the same self-screen the semantic-bind roster
            # uses); everything else is not world-truth geography.
            for _pid in world.porcelain.entities("canon", prefix="place:"):
                _pid = str(_pid or "")
                if not _pid or _pid == scene or _pid in _excl:
                    continue
                if any(_pid == q for q, _ in _places):
                    continue
                _nm = _kd = None
                try:
                    _nm = live_reads.state(_pid, "name")
                    _kd = live_reads.state(_pid, "kind")
                except Exception:  # noqa: BLE001
                    pass
                if not _nm and not _kd:
                    continue  # not canon-readable at the horizon — not a destination
                _places.append((_pid, str(_nm) if _nm
                                else _pid.split(":", 1)[-1].replace("_", " ")))
        except Exception:  # noqa: BLE001
            pass
        verdict = cohorts.world_tick(
            provider, members, _places,
            elapsed_note=f"Roughly {int(minutes_now)} diegetic minutes are on the clock; "
                         f"each person below has been off-screen a while.")
        trace.cohort_calls.append("world_tick:cheap")
        _valid_places = {q for q, _ in _places}
        _member_ids = {m for m, _w, _s in members}
        _done: set[str] = set()
        rows: list[dict] = []
        for t in (verdict.get("ticks") or []):
            mid = str((t or {}).get("member") or "")
            kind = str((t or {}).get("kind") or "")
            detail = str((t or {}).get("detail") or "").strip()
            if mid not in _member_ids or mid in _done or not kind:
                continue
            if value_leaks(detail, _ctoks) or any(v in detail.lower() for v in _pvals):
                logger.info("world tick for %s dropped (detail leaks)", mid)
                continue
            _done.add(mid)
            if kind == "moved":
                dest = str(t.get("moves_to") or "")
                if mid in _anchored or dest not in _valid_places or dest == scene:
                    logger.info("world tick move for %s dropped (%s)", mid,
                                "anchored" if mid in _anchored else "bad destination")
                    continue
                rows.append({"entity": mid, "attribute": "in", "value": dest,
                             "value_type": "entity", "valid_from": turn_time(turn)})
            else:
                _with = str(t.get("with_member") or "")
                if kind == "met_with":
                    # PATIENT AUTHORITY (Cx 398 blocker 2): an LLM-supplied patient must be
                    # a real, eligible OFF-screen person — never the protagonist (off-screen
                    # action is never about the player), never someone presently with the
                    # player, never a non-existent or undiscovered-offscene person. A bad
                    # patient drops the WHOLE meeting (a meeting with no one isn't a fact).
                    def _patient_ok(pid: str) -> bool:
                        if not pid.startswith("person:") or pid == arc.protagonist \
                                or pid in (npcs or []):
                            return False
                        _pn = _nodes.get(pid)
                        if _pn is not None and _undisc(_pn):
                            return False
                        try:
                            if live_reads.state(pid, "kind") is None:
                                return False  # not canon-readable — not a real person here
                            _ploc = p.locate(pid)
                            return not (_ploc and _ploc[0] == scene)
                        except Exception:  # noqa: BLE001
                            return False
                    if not _patient_ok(_with):
                        logger.info("world tick met_with for %s dropped (patient %r "
                                    "ineligible)", mid, _with)
                        continue
                _ev = f"event:tick_{mid.split(':', 1)[-1]}_{turn}"
                rows += [
                    {"entity": _ev, "attribute": "kind", "value": kind,
                     "valid_from": turn_time(turn)},
                    {"entity": _ev, "attribute": "agent", "value": mid,
                     "value_type": "entity", "valid_from": turn_time(turn)},
                    {"entity": _ev, "attribute": "detail", "value": detail[:200],
                     "valid_from": turn_time(turn)},
                ]
                if kind == "met_with":
                    rows.append({"entity": _ev, "attribute": "patient", "value": _with,
                                 "value_type": "entity", "valid_from": turn_time(turn)})
            trace.world_tick.append(f"{mid}:{kind}")
        if rows:
            p.ingest_structured(rows, classify="batch")
            logger.info("world tick committed: %s", trace.world_tick)
    except Exception:  # noqa: BLE001 — the tick is opportunistic; never break settle
        logger.warning("world tick skipped", exc_info=True)
        trace.dropped_cohorts.append("world_tick")


def adjudicate(world: Any, p: Any, protagonist: str, scene: str | None,
               requires: list[str], provider: Any = None,
               *, as_of: float | None = None, laws: str = "") -> str | None:
    """The Adjudicate faculty (letter 028, finding E): locate() is the
    rules lawyer. Each claimed item must resolve AND be at hand (its
    containment chain reaching the player or the current scene). Returns
    None if the action stands, else the denial reason. An unresolved item
    that is ordinary role equipment is GRANTED (improvise + commit) rather
    than denied (IMPROV-AND-AUTHORITY); load-bearing/specific objects still
    deny. Deterministic after refer() (+ one cheap grant check on a miss)."""
    for description in requires:
        # SCOPED (founder synonym mandate / Cx 445 note): scope unlocks refer's
        # tier-2 zero-candidate escalation + alias accrual — "the blade" finds the
        # established knife you hold, one cheap call once, deterministic thereafter.
        res = world.refer(description, scope=[e for e in (protagonist, scene) if e],
                          frame="canon", as_of=as_of)  # at-hand only at the horizon (Cx 257)
        if getattr(res, "status", None) != "resolved" or not getattr(res, "entity_id", None):
            if _grant_equipment(world, p, protagonist, description, scene, provider,
                                laws=laws):
                continue  # ordinary role equipment — granted, action stands
            return (f"{description!r} is not a thing you are known to have — "
                    f"it has never been established in this world's canon")
        entity = res.entity_id
        chain = p.locate(entity, as_of=as_of)
        if protagonist not in chain and (scene is None or scene not in chain):
            where = chain[0] if chain else "nowhere known"
            return (f"{description!r} ({entity}) is not at hand — "
                    f"it is at {where}")
    return None


def _protagonist_tokens(protagonist: str) -> list[str]:
    """Name fragments that mark third-person rendering of the player
    ('person:marn' -> 'marn'). Deterministic guard input (letter 025)."""
    slug = protagonist.split(":", 1)[-1]
    return [t for t in slug.replace("-", "_").split("_") if len(t) > 2]


def names_protagonist(text: str, protagonist: str) -> bool:
    lowered = f" {text.lower()} "
    return any(f" {tok}" in lowered.replace("’", " ").replace("'", " ")
               .replace(",", " ").replace(".", " ").replace(";", " ")
               for tok in _protagonist_tokens(protagonist))


def _conclusion_recorded(reads: Any) -> bool:
    return bool(reads.events(kind="conclusion", frame=SESSION))


#: A shape's LITERAL external result — the Contest "scoreboard" axis (Cx 027), read ALONGSIDE
#: pillar coverage. CONSOLIDATED (letters 131/132): the result is an ordinary canon Occurred EVENT
#: (declared win/loss kinds), minted by EVENT-OCCURS like any beat — the bespoke `scoreboard:main`
#: entity + `_world_event` state read + `reads_world_event` flag are RETIRED. `result_events` =
#: {"win": (kinds,), "loss": (kinds,), "participants": (ids,)} declared per-arc (None/empty → no
#: literal-result axis, the common case). Collision-proofed by participant filtering (event `kind`
#: is global — EVENT-OCCURS-FIRING.md). Reads canon events, NEVER the internal won/lost receipt
#: (which would re-couple proof to score — Cx 027 blocker 2). Loss binds over win on a tie (the
#: real result the world delivered); otherwise most-recent by valid time.
def _literal_result(reads: Any, result_events: dict | None) -> str | None:
    if not result_events:
        return None
    parts = set(result_events.get("participants") or ())

    def _last_at(kinds) -> float | None:
        # Scope by participants ALL-of (matching PB's porcelain participant filter): the event must
        # involve EVERY declared scoping entity, across agents ∪ patients — EventRow exposes those,
        # NOT a `participants` attr (the v1 bug Cx 134 caught). Empty parts → unscoped. This is the
        # collision-proofing for the global event `kind` (Cx 132 #4).
        ats = []
        for k in (kinds or ()):
            for e in reads.events(kind=k):
                if e.at is None:
                    continue
                ev = set(getattr(e, "agents", ()) or ()) | set(getattr(e, "patients", ()) or ())
                if not parts or parts <= ev:
                    ats.append(e.at)
        return max(ats) if ats else None

    win_at, loss_at = _last_at(result_events.get("win")), _last_at(result_events.get("loss"))
    if win_at is None and loss_at is None:
        return None
    if loss_at is None:
        return "win"
    if win_at is None:
        return "loss"
    return "loss" if loss_at >= win_at else "win"


def _conclusion_effect(reads: Any, arc: Arc, cost_disposition: str,
                       result_events: dict | None) -> dict | None:
    """The coverage-derived conclusion EFFECT (`conclusion_from_coverage`) for a pillar arc, or
    None when the arc declares no required pillars. The SINGLE source of truth shared by the
    commitment grade (COMMITMENT-AS-EFFECT: the grade is the EFFECT, not an LLM judgment) and the
    epilogue. `cost_weight` is the false-coverage cost integral for NORMAL polarity, 0 for
    fail_forward (comedy: a false-fill is success, never a cost — Cx 027 blocker 3)."""
    if not arc.pillars:
        return None
    summary = coverage_summary(reads, arc)
    req = summary["required"] or []
    if not req:
        return None
    cost_weight = 0.0 if cost_disposition == "fail_forward" else (len(summary["false"]) / len(req))
    world_event = _literal_result(reads, result_events)
    return conclusion_from_coverage(summary, cost_disposition=cost_disposition,
                                    world_event=world_event, cost_weight=cost_weight)


def _fire_event_occurs(world: Any, p: Any, reads: Any, arcs: list, provider: Provider,
                       action: str, tier: str, turn: int, trace: "TurnTrace",
                       protagonist: str, only_kinds: set | None = None) -> list[str]:
    """EVENT-OCCURS-FIRING (EVENT-OCCURS-FIRING.md, Cx 115): fire any authored `event_occurs`
    act-beat whose act just HAPPENED in the player's RESOLVED action, so `beat_pass` achieves it
    this turn (the fix for the arc-stall: nothing else writes arbitrary-kind canon events). Gathers
    PENDING `Occurred`-kind candidates across the arcs (main + side), asks the CONSTRAINED detector
    which occurred, and mints the canon event(s) + an action-event anchor (`caused_by`). Fail-open;
    skipped (no cohort call) when there are no pending event_occurs kinds. Returns the fired kinds."""
    from construct.arc.conditions import Occurred
    cands: dict[str, str] = {}  # kind -> beat_id; PENDING beats only, deduped by kind
    for arc in arcs:
        for beat in getattr(arc, "beats", ()):
            cond = beat.achievable_via
            if not isinstance(cond, Occurred):
                continue  # v1: direct Occurred beats (the generator's event_occurs shape)
            try:
                status = reads.state(beat.beat_id, "status", frame=PLOT)
            except Exception:
                status = None
            if status not in (None, "pending"):
                continue  # already achieved/closed → no candidate, no duplicate event
            if only_kinds is not None and cond.kind not in only_kinds:
                continue  # restricted pass (failure-tier result-event minting — see caller)
            cands.setdefault(cond.kind, beat.beat_id)
    if not cands:
        return []
    candidates = [{"kind": k, "what": k.replace("_", " ")} for k in cands]
    try:
        out = cohorts.detect_events(provider, action, tier, candidates)
        trace.cohort_calls.append("detect_events:cheap")
    except Exception as exc:  # never sink the turn on the detector
        trace.dropped_cohorts.append(f"detect_events ({exc})")
        return []
    fired = [k for k in (out.get("occurred") or []) if k in cands]  # constrained to candidates
    if not fired:
        return []
    # Mint a real canon ACTION event to anchor caused_by (Cx 115 #2 — not a session marker), then
    # the authored event(s) it caused. events(kind=X) then sees them → Occurred(kind=X) is true.
    action_eid = f"event:action_{turn}"
    rows = [{"entity": action_eid, "attribute": "kind", "value": "player_action",
             "valid_from": turn_time(turn)},
            {"entity": action_eid, "attribute": "agent", "value": protagonist,
             "value_type": "entity", "valid_from": turn_time(turn)}]
    for k in fired:
        eid = f"event:{k}_{turn}"
        # caused_by must be an EVENT-ENTITY causality ROW (Cx 117) — item-level `caused_by` is PB
        # row metadata that `events().caused_by` does not surface. Write the explicit row.
        rows += [{"entity": eid, "attribute": "kind", "value": k, "valid_from": turn_time(turn)},
                 {"entity": eid, "attribute": "agent", "value": protagonist,
                  "value_type": "entity", "valid_from": turn_time(turn)},
                 {"entity": eid, "attribute": "caused_by", "value": action_eid,
                  "value_type": "entity", "valid_from": turn_time(turn)}]
    try:
        p.ingest_structured(rows)  # canon — a true world event; the membrane is unaffected
    except Exception as exc:  # fail-open
        trace.dropped_cohorts.append(f"event_fire ({exc})")
        return []
    trace.events_fired = fired
    logger.info("event_occurs fired: %s (caused_by %s)", fired, action_eid)
    return fired


def _episode_since(reads: Any) -> float | None:
    """The valid-time of the latest EPISODE boundary, or None for a first/only episode.
    Written by `game.continue_episode` when a concluded story continues into the next
    episode (CONCLUDE→CONTINUE). Scopes `terminal_outcome` so a PRIOR episode's win/loss
    receipt doesn't freeze the new one (PB is append-only — we can't delete the old
    receipt, so we read only receipts SINCE the boundary)."""
    starts = reads.events(kind="episode_start", frame=SESSION)
    ats = [e.at for e in starts if e.at is not None]
    return max(ats) if ats else None


def terminal_outcome(reads: Any) -> str | None:
    """The recorded win/loss terminal of a `win_loss` scenario, or None if it
    hasn't ended (WIN-LOSS §10). Reads the SESSION receipt via `events()` (the
    same pattern as `_conclusion_recorded` — SESSION event rows are read by kind,
    not folded by `state()`); the outcome is encoded in the kind. Lets a
    transport stop ticking an ended story instead of re-rendering aftermath.
    Scoped to the CURRENT episode (CONCLUDE→CONTINUE): only receipts since the latest
    episode boundary count, so a continued story isn't frozen by its prior ending."""
    since = _episode_since(reads)
    # #95 (Cx 422): death outranks win/loss AND both scenario modes — checked first,
    # scoped to the episode like the others (a premise-policy chapter never writes one).
    if reads.events(kind="player_death", frame=SESSION, since=since):
        return "died"
    if reads.events(kind="arc_won", frame=SESSION, since=since):
        return "won"
    if reads.events(kind="arc_lost", frame=SESSION, since=since):
        return "lost"
    return None


def _has_time_deadline(arc: Arc) -> bool:
    """True if the arc authored a DIEGETIC-TIME deadline — a `Quantity` over
    `time:elapsed.elapsed_minutes` in `failure_when` (King's dinner, the bomb). Only such arcs
    need diegetic time advanced BEFORE the terminal check (Cx 173 #3); every other turn keeps the
    post-render time estimate (with narration) byte-for-byte unchanged."""
    fw = getattr(arc, "failure_when", None)
    if fw is None:
        return False
    from construct.arc.conditions import Quantity, atoms_of
    from construct.clock import ELAPSED_ATTR, ELAPSED_ENTITY
    return any(isinstance(a, Quantity) and a.entity == ELAPSED_ENTITY
               and a.attribute == ELAPSED_ATTR for a in atoms_of(fw))


def _advance_diegetic_time(world: Any, clock: Any, player_input: str, trace: "TurnTrace",
                           provider: Provider, *, narration: str) -> None:
    """Estimate how much in-world time this turn consumed and APPEND it to the accrue counter
    (DIEGETIC-TIME.md). Deterministic for ordinary turns (skips the model call); the model
    `estimate_elapsed` only for explicit temporal language (a wait/jump/rest/montage) or a
    cross-site JOURNEY (#101, Cx 445: the six-minute village trip — the local-move bucket
    must never price real travel). Best-effort: time never sinks a turn. Called EARLY for
    time-deadline arcs (narration unavailable → "") so the deadline crosses same-turn;
    otherwise POST-RENDER with the narration for a richer estimate."""
    try:
        from construct.clock import commit_elapsed, delta_from_estimate, deterministic_elapsed
        with _phase(trace, "time_estimate"):
            # an already-here no-op (a synonym for the current room, Cx 445 wrinkle) is
            # NOT a move for time purposes — and the input's own move VERBS would still
            # hit the 6-minute bucket, so the no-op bucket is FORCED, not inferred.
            _moved = trace.movement_status in ("clear", "obscured")
            if trace.same_place:
                est = {"advance_minutes": 1}
            elif trace.distance_unknown:
                # a pre-commit estimate (deliberation gate, #102) is REUSED — the same
                # movement is never priced twice in one story beat.
                est = ({"advance_minutes": trace.journey_est}
                       if trace.journey_est >= 0 else None)
            else:
                est = deterministic_elapsed(player_input, moved=_moved)
            if est is None:
                est = cohorts.estimate_elapsed(
                    provider, now=clock.render(),
                    hours_per_day=clock.calendar.hours_per_day,
                    phases=clock.calendar.phase_names,
                    action=player_input, narration=narration,
                    distance_unknown=trace.distance_unknown)
                trace.cohort_calls.append("estimate_elapsed")
            else:
                trace.cohort_calls.append("time_estimate:deterministic")
        trace.time_advanced = delta_from_estimate(clock, est)
        commit_elapsed(world, trace.time_advanced)
    except Exception as exc:  # noqa: BLE001 — time never sinks a turn
        logger.warning("diegetic-time estimate failed: %s", exc)
        trace.dropped_cohorts.append(f"estimate_elapsed ({exc})")


def run_turn(world: Any, arc: Arc, provider: Provider, player_input: str,
             turn: int, scope: list[str] | None = None,
             mode: str = "pure", endless: bool = False,
             scenario_mode: str = "endless", style: str = "",
             play_style: str = "",
             judgment_type: str = "claim-vs-fact",
             cost_disposition: str = "peril_redemption",
             result_events: dict | None = None,
             suspense: str = "general",
             cast: dict | None = None,
             side_arcs: list[Arc] | None = None,
             terminal_owner: str = "world_event",
             generate: bool = True,
             horizon: float | None = None,
             death_policy: str = "shielded",
             laws: list | None = None,
             reality: str = "",
             on_scene: Callable[[], None] | None = None) -> TurnResult:
    """mode: 'pure' (canon-strict; the default for determined scenarios —
    declarations are refused, claimed items are adjudicated) or
    'coauthor' (the player may declare facts into the world).
    endless: when False (default) the arc concludes and the world settles
    into aftermath at its destination; when True the world has no terminal
    arc and carries on indefinitely (clocks/NPCs keep running).
    side_arcs: the rest of the portfolio (LIVING-WORLD-GENERATOR P1). `arc` is
    the MAIN arc — it alone bears the win/loss terminal and anchors the player
    frame, scope, pins and briefing voice. Side arcs tick (clocks/beats), are
    classified per-arc, and on a non-won terminal emit FALLOUT + a diegetic
    acknowledgment; they NEVER end the scenario.
    laws: the world's sealed law objects (#105 WORLD LAWS) — rendered once
    into the SAME compact block for every consumer this turn (classify's
    assured/refused judgment, equipment/take grants, the reshape judge) and
    into the reserved briefing lane ahead of the capped pins (Cx 470).
    reality: the world's reality register — its one-line contract rides
    BESIDE the laws block for every consumer, including the no-law case
    (Cx 475: 'in a real-world register…' needs an explicit referent)."""
    side_arcs = side_arcs or []
    from construct import laws as _laws_mod
    _world_laws = [law for law in (laws or []) if isinstance(law, dict)]
    _reality_line = _laws_mod.reality_line(reality)
    _laws_full = "\n".join(
        p for p in (_reality_line, _laws_mod.laws_block(_world_laws)) if p)
    # Fold any terminal gauge floors into failure_when (GAUGE §5): the gauge
    # declaration is the source of truth; the loss terminal is derived each load.
    arc = apply_gauge_terminals(arc)
    p = world.porcelain
    # AS-OF PLAY HORIZON (B' S3): bind EVERY read this turn to the play horizon so beats/clocks
    # and presence/adjudication never see future source rows. None (legacy/single-timeframe) =
    # the timeline head — byte-for-byte unchanged. `_h` is the local alias threaded into the
    # direct p.locate/snapshot/state calls below (the adapter handles its own via `horizon`).
    _h = horizon
    live_reads = PorcelainWorldReads(world, horizon=horizon)
    trace = TurnTrace(turn=turn)
    p = _FailOpenIngest(p, trace)  # the climax shield (#89): in-turn writes fail open
    player_frame = _player_frame(arc)

    # ---- SERIAL SPINE -----------------------------------------------------
    # 1. Classify (cheap; fail-open to action). Movement intent + the assured-vs-
    #    uncertain resolution judgment ride the same call (no extra latency).
    moves_to, requires = "", []
    needs_test, uncertain_of = False, ""
    mortal_risk = False     # #95: the move risks the protagonist's LIFE (classify judgment)
    uses_knowledge = False  # SCENE-CONTEXT-SHAPE: protagonist-competence gate (Cx 247)
    asks_self = False       # ADDRESSED INWARD: a self-question routes to the player's own memory
    recalls = False         # #97: the player deliberately reaches into memory this turn
    declares_memory = False  # #97 retcon: the recall ASSERTS new autobiography
    reshape_attempt = False
    commits, commitment = False, ""
    takes = ""
    drops = ""
    examines_target = ""  # the ONE specific detail the player closely investigates (make-it-real gate)
    asserts_or_reveals = True  # conservative default (TURN-LATENCY A-lite): keep extraction
    # A brief actor descriptor so `classify` can wave off a test for things this
    # character is plainly proficient at (ACTION-RESOLUTION §1). Cheap point reads.
    actor = ""
    try:
        proto = arc.protagonist
        bits = [live_reads.state(proto, a) for a in ("role", "kind", "background")]
        actor = "; ".join(b for b in bits if isinstance(b, str) and b) \
            or proto.split(":")[-1].replace("_", " ")
    except Exception:
        actor = arc.protagonist.split(":")[-1].replace("_", " ")
    # BEAT-DELIVERY half 2 (topic-aware ASK delivery, Cx 125): assemble the ENTRY-scene
    # present clue-bearing cast's pursuable disclosures as OPAQUE candidates so `classify`
    # can match the player's QUESTION to the right one (the ASK twin of examines_target).
    # Opaque ids (clue ids can embed the answer); descriptor = the non-spoiling hook_text
    # (fallback: holder role). The deterministic reveal gate + presence stay authoritative at
    # delivery below — this only PICKS the topic. Pre-move (entry scene): a same-turn move+ask
    # falls back to authored order (Cx 125 v1 semantics).
    ask_candidates: list = []
    _ask_by_oid: dict = {}
    try:
        _entry_chain = p.locate(arc.protagonist, as_of=_h)
        _entry_scene = _entry_chain[0] if _entry_chain else None
    except Exception:
        _entry_chain, _entry_scene = [], None
    # PLAYER-DRIVEN CAST MOVEMENT (Cx 363/365, the ghost-cast incident): the present people as
    # OPAQUE candidates, so classify can capture plainly-worded dismissals ("you two may go") and
    # companions ("Sir? Shall we…") — committed pre-render so narration renders the updated map.
    npc_candidates: list = []
    _npc_by_oid: dict = {}
    if _entry_scene:
        # PRESENT-BUT-UNSEEN (#94 campaign F12, Cx 408): scope is a briefing/concealment
        # boundary, not a truth boundary — a person CANONICALLY IN THE ROOM (including a
        # nested child place; the source matches the `_present` authority's containment
        # shape) is by definition discovered. Union via the shared containment walk; the
        # colocation/departure checks below stay authoritative.
        for _pid in sorted(set(scope or []) | _persons_under(p, _entry_scene, _h)):
            if not _pid.startswith("person:") or _pid == arc.protagonist:
                continue
            try:
                if not _colocated(p.locate(_pid, as_of=_h), _entry_scene, _entry_chain) \
                        or _departed_from(p, live_reads, _pid, _entry_scene, as_of=_h):
                    continue  # not here — or dismissed and never re-placed (Cx 369 #1)
            except Exception:
                continue
            _oid = f"npc_{len(_npc_by_oid)}"
            _nm = None
            try:
                _nm = live_reads.state(_pid, "name")
            except Exception:
                pass
            _desc = str(_nm) if _nm else _pid.split(":", 1)[-1].replace("_", " ").title()
            _node = (cast or {}).get(_pid) if hasattr(cast or {}, "get") else None
            if _node is not None and getattr(_node, "surface_role", ""):
                _desc += f" ({_node.surface_role})"
            npc_candidates.append((_oid, _desc))
            _npc_by_oid[_oid] = _pid
    if cast:
        if _entry_scene:
            _citer = cast.items() if hasattr(cast, "items") else [(n.node_id, n) for n in cast]
            for _nid, _node in _citer:
                if not _nid.startswith("person:") or _nid == arc.protagonist:
                    continue
                _hc = getattr(_node, "holds_clues", ()) or ()
                if not _hc:
                    continue
                try:
                    _ncolocated = _colocated(p.locate(_nid, as_of=_h), _entry_scene, _entry_chain) \
                        and not _departed_from(p, live_reads, _nid, _entry_scene, as_of=_h)
                except Exception:
                    _ncolocated = False
                if not _ncolocated:
                    continue
                for _clue in _hc:
                    _oid = f"ask_{len(_ask_by_oid)}"
                    _desc = (getattr(_clue, "hook_text", "") or "").strip() \
                        or (getattr(_node, "surface_role", "") or _nid.split(":")[-1])
                    ask_candidates.append((_oid, _desc))
                    _ask_by_oid[_oid] = _clue
    asks_targets: list = []
    moved_with_ids: list = []
    dismissed_ids: list = []
    joins_ids: list = []
    try:
        with _phase(trace, "classify"):
            verdict = cohorts.classify(provider, player_input, actor=actor,
                                       ask_candidates=ask_candidates,
                                       npc_candidates=npc_candidates,
                                       laws=_laws_full)
        kind = verdict["kind"]
        moves_to = verdict.get("moves_to", "") or ""
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
        # PLAYER-DRIVEN CAST MOVEMENT (Cx 363/365): opaque ids → present NPC ids; only action
        # turns move people; a candidate can't be both dismissed and brought along (dismissal
        # is the stronger, explicit wording — it wins the conflict).
        if kind == "action":
            dismissed_ids = [_npc_by_oid[t] for t in (verdict.get("npcs_dismissed") or [])
                             if t in _npc_by_oid]
            moved_with_ids = [_npc_by_oid[t] for t in (verdict.get("moved_with") or [])
                              if t in _npc_by_oid and _npc_by_oid[t] not in dismissed_ids]
            # COMPANIONSHIP (#82, Cx 372/373): an invitation to stay with the player becomes
            # STANDING canon state below — separate field, never overloading the per-move
            # moved_with adjunct; dismissal wins the conflict here too.
            joins_ids = [_npc_by_oid[t] for t in (verdict.get("joins") or [])
                         if t in _npc_by_oid and _npc_by_oid[t] not in dismissed_ids]
        # Default TRUE on absence (old stubs / schema-less classify) so extraction is never
        # silently skipped where a fact could be asserted (protected-key licensing depends on it).
        asserts_or_reveals = bool(verdict.get("asserts_or_reveals", True))
        uses_knowledge = bool(verdict.get("uses_protagonist_knowledge")) and kind == "action"
        # ADDRESSED INWARD (founder live 2026-07-03, "my own memories should answer here"):
        # a question about the player's OWN life is CHECKED at classify — the mechanical
        # route, not directive luck — and outranks the last-speaker convention downstream.
        asks_self = bool(verdict.get("asks_self"))
        # #97 THE REMEMBRANCER (Cx 434 constraint 1): the deliberate memory reach and the
        # autobiography DECLARATION are distinct signals — never overloaded onto asks_self.
        # `declaration` kind is ACCEPTED here (Cx 439 #1): the most literal retcon parse
        # ("I remember my childhood friend John Johnson…") IS a declaration — of the
        # player's own past, which is theirs to author; world-fact fiat stays denied below.
        recalls = bool(verdict.get("recalls"))
        declares_memory = (bool(verdict.get("declares_memory"))
                           and kind in ("action", "declaration"))
        trace.cohort_calls.append("classify:cheap")
    except ProviderError as exc:
        kind = "action"
        trace.dropped_cohorts.append(f"classify ({exc})")
    trace.classified = kind
    improv_query = ""  # set when an unanswerable question falls through to narration

    if kind == "exit":
        # Out-of-character "let's do a new story / quit" — DON'T advance the world.
        # Signal the transport, which owns the start menu and the confirm step.
        return TurnResult(prose="", trace=trace, exit_requested=True)
    if kind == "question":
        # The engine's refer (HD 003 fix) strips determiners and resolves
        # against a knows:-derived scope, so "where is my brass spoon?"
        # binds engine-side — the old host-side normalize-and-retry is
        # retired (PB catch-up).
        a = p.ask(player_input, frame=player_frame, as_of=_h)  # answer at the play horizon (Cx 255)
        prose = a.get("prose") if isinstance(a, dict) else getattr(a, "prose", None)
        facts = a.get("facts") if isinstance(a, dict) else getattr(a, "facts", [])
        if prose or facts:
            answer = prose or "; ".join(
                f"{f['entity']} {f['attribute']}: {f['value']}" for f in facts)
            trace.concealment_audit = "n/a (ask path, frame-scoped)"
            return TurnResult(prose=answer, trace=trace)
        # Canon can't answer (e.g. "where's the closest pub?" — unestablished but
        # something this character would plainly KNOW). DON'T stonewall with "you
        # can't say for certain" — that's the absence of improvisation the founder
        # flagged. Fall through to the narrator and improvise an answer GROUNDED in
        # who the player is (a long-standing resident knows the local geography),
        # under canon + concealment.
        kind = "action"
        improv_query = player_input
        uses_knowledge = True  # improvising an answer the character would plainly know → competence
        trace.classified = "question→improv"
    if kind == "ooc":
        # CONDUIT ONLY VIA /ooc (founder 2026-07-01): the automatic classify→Conduit route
        # broke immersion — an in-fiction line to a present character ("do you have any more
        # questions for these two?" said to Reed) got mis-tagged OOC and answered by the host
        # persona instead of the character. The host now speaks ONLY when the player explicitly
        # types /ooc (transport → ooc_respond). Anything typed WITHOUT /ooc stays in the fiction:
        # a stray 'ooc' verdict (legacy stub) falls through to the in-world action path.
        kind = "action"

    if kind == "declaration" and mode == "pure" and not commits and not declares_memory:
        # A declaration that tries to AUTHOR a new world-fact by fiat is denied in canon-strict
        # mode. But a CONCLUSORY COMMITMENT (commits=True) read as a declaration ("It was Julian —
        # he killed his uncle") is NOT fact-authoring — it's the player naming their conclusion,
        # the climax the commitment path judges/concludes/bounces (#2: a hedged accusation must
        # not be stonewalled as illegal authoring just because it parsed as a declaration).
        # And a DECLARED MEMORY (#97, Cx 439 #1) is the player authoring their OWN past — the
        # retcon channel's guarded doorway handles it (screens, beliefs, collisions), never
        # the generic denial; it proceeds as an ordinary in-world beat.
        trace.adjudication = "denied: declarations are co-author moves; this scenario is canon-strict"
        return TurnResult(
            prose="(canon-strict) This world's facts are already written — "
                  "you can act in it, but not author it. State what you DO.",
            trace=trace)
    if kind == "declaration" and declares_memory:
        # the declared memory flows on as an in-world beat: the commit channel runs at the
        # Remembrancer block, and the rest of the turn (render, extraction) treats the
        # recollection like any other action prose.
        kind = "action"

    # 1b. Adjudication (letter 028, finding E): locate() is the rules
    #     lawyer. A failed precondition means the action DOES NOT COMMIT;
    #     the failure renders honestly and is receipted, never silent.
    pre_chain = p.locate(arc.protagonist, as_of=_h)
    pre_scene = pre_chain[0] if pre_chain else None
    if requires and mode == "pure":
        denial = adjudicate(world, p, arc.protagonist, pre_scene, requires, provider,
                            as_of=_h, laws=_laws_full)
        if denial:
            trace.adjudication = f"denied: {denial}"
            prose = cohorts.narrate(
                provider,
                f"SCENE: you are at {pre_scene or 'an unresolved place'}.\n"
                f"THE PLAYER ATTEMPTED: {player_input}\n"
                f"ADJUDICATION (binding): the attempt FAILS — {denial}. "
                f"Render the failure honestly and diegetically; the world "
                f"does not bend.",
                arc.protagonist, peopled=False, competence=False)  # brief denial render (Cx 247)
            trace.cohort_calls.append("narrate:main")
            p.ingest_structured([
                {"entity": f"event:turn_{turn}", "attribute": "kind",
                 "value": "turn", "valid_from": turn_time(turn)},
                {"entity": f"event:turn_{turn}", "attribute": "adjudication",
                 "value": trace.adjudication, "valid_from": turn_time(turn)},
                # This denial ADVANCES the turn number (a real failed action), so archive the
                # delivered prose synchronously too — parity with the main path: every
                # turn-advancing exchange is reconstructable after a crash (Cx 266/268 #1).
                {"entity": f"arch:turn_{turn}", "attribute": "player_said",
                 "value": player_input[:600], "valid_from": turn_time(turn)},
                {"entity": f"arch:turn_{turn}", "attribute": "prose",
                 "value": prose[:2400], "valid_from": turn_time(turn)},
            ], frame=SESSION, classify="rules")  # receipt + archive — RULES, no LM (Cx 268)
            return TurnResult(prose=prose, trace=trace)

    # 2. Ingest the player's effect. FAIL-OPEN on a text-extraction schema violation
    #    (the cheap extractor occasionally malforms its JSON and the provider raises
    #    after a re-ask): the render extraction below is the authoritative capture and
    #    movement rides moves_to/refer, so a failed player-input extraction must NOT
    #    sink the turn — degrade to no player-stated facts this turn (logged).
    # TURN-LATENCY Lever A-lite (Cx 077/079): SKIP the expensive player-input extraction on
    # turns that can't assert/reveal a new fact — pure look/ask/talk, and simple move/take
    # already captured deterministically by moves_to/takes below. classify flags this via
    # `asserts_or_reveals` (default TRUE → conservative: old stubs / uncertainty keep extraction,
    # so protected-key licensing via pre_keys is never silently lost). ~6s saved on those turns.
    # The objects the protagonist HOLDS at the START of the turn — captured BEFORE the player-input
    # extraction below, which may itself write a held object into a container it names ("set the
    # pencil down on a table" → `obj:pencil in obj:table`). The deterministic DROP step (2c-ii) needs
    # this pre-extraction view: otherwise its "is it still held?" check reads the already-polluted
    # state and bails, leaving the object under an unlocated container (Cx 295 BLOCK).
    try:
        _pre_held = {h for h in p.contents(arc.protagonist, as_of=_h)
                     if str(h).startswith("obj:")}
    except Exception:
        _pre_held = set()
    receipt_rows = []
    # Resolved player-action candidates (entity/attribute/value dicts) for the
    # fact-source v3 hydration join: the generator needs values for the value-side
    # spine-touch check, but PB receipts carry only entity/attribute (no value).
    # Captured here so confirmed_batch() can hydrate confirmed keys from candidates.
    _player_delta_candidates: list[dict] = []
    if asserts_or_reveals:
        try:
            with _phase(trace, "player_ingest"):
                # ENTITY AUTHORITY (Cx 304): READ-ONLY extract → RESOLVE → structured ingest, so the
                # player's sentence can't free-mint a fragment/phantom into canon ("pick up a plain
                # pencil from the desk and pocket it" used to mint `obj:pencil in obj:desk` +
                # `obj:pencil in person:you`). The resolver binds mentions to present entities, binds
                # deixis to the protagonist, mints one typed entity for genuine novelty, drops the rest.
                def _pin_name(e: str) -> str:
                    try:
                        v = live_reads.state(e, "name")
                    except Exception:
                        v = None
                    return v if isinstance(v, str) else ""
                _pin_cands = (set(scope or []) | set(_pre_held) | set(pre_chain or [])
                              | ({pre_scene} if pre_scene else set()) | {arc.protagonist})
                # pov= (PB SHAPE-FIX 4c, #108): the player's "I" IS the protagonist —
                # deixis binds to them; person:you/person:i can never mint.
                _raw = p.extract(player_input, scene=pre_scene, extract="lean",
                                 pov=arc.protagonist)  # read-only
                # FRAME PARTITION (Cx 552: the player channel is the SAME structural
                # bypass — a knows:* extraction row landed directly in the NPC frame,
                # ungated, no telemetry). First step after extract; policy + rationale:
                # _partition_frames.
                _raw, _input_dropped = _partition_frames(list(_raw))
                if _input_dropped:
                    logger.info(
                        "player input: dropped %d non-canon-framed row(s) "
                        "(knowledge-promotion gate not yet built): %s",
                        len(_input_dropped), _input_dropped[:5])
                    trace.dropped_cohorts.append(
                        f"input_noncanon_frames ({len(_input_dropped)})")
                # PLAYER channel mint policy (founder 2026-06-30): no person/place by fiat — the
                # player's "I am Bradford Clemense" must not mint a present NPC; the world introduces
                # NPCs, the move channel makes places. Objects still mint (improv permanence).
                _resolved, _prec = resolve_rows(_raw, scene=_pin_cands, protagonist=arc.protagonist,
                                                name_of=_pin_name, allow_mint=True,
                                                mint_kinds=_PLAYER_INPUT_MINT_KINDS)
                trace.resolver = (trace.resolver or []) + _prec
                # Capture candidates BEFORE ingest for the value-side hydration join (§A, Cx 525):
                # receipt_rows below carries entity/attribute only; _player_delta_candidates
                # preserves values so confirmed_batch() can satisfy the value-side spine-touch check.
                _player_delta_candidates = [
                    {"entity": str(r.get("entity", "")),
                     "attribute": str(r.get("attribute", "")),
                     "value": r.get("value", "")}
                    for r in (_resolved if isinstance(_resolved, list) else list(_resolved))
                ]
                receipt_rows = _receipt_rows(p.ingest_structured(_resolved, classify="batch"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("player-input extraction failed; continuing: %s", exc)
            trace.dropped_cohorts.append(f"player_ingest ({exc})")
            receipt_rows = []
    else:
        trace.dropped_cohorts.append("player_ingest (skipped: no asserts/reveals)")

    # 2a-ii. PLAYER-DRIVEN DISMISSALS (Cx 363/365, ghost-cast incident): the player plainly sent
    # present people away ("you two may go"). The HONEST commit for a destination the fiction
    # hasn't named is NEGATIVE scene truth — a `departed_scene` EVENT (agent=npc, patient=scene),
    # never `in=unknown`, never a fake place, never a bare retract (an older base-location row
    # would leak as current — Cx 364). Presence projection below suppresses same-scene presence
    # until a newer positive `in` row appears. Committed PRE-render so narration renders the map.
    if dismissed_ids and _entry_scene:
        try:
            _drows = []
            for _did in dismissed_ids:
                _ev = f"event:departed_{_did.split(':', 1)[-1]}_{turn}"
                _drows += [
                    {"entity": _ev, "attribute": "kind", "value": "departed_scene",
                     "valid_from": turn_time(turn)},
                    {"entity": _ev, "attribute": "agent", "value": _did,
                     "value_type": "entity", "valid_from": turn_time(turn)},
                    {"entity": _ev, "attribute": "patient", "value": _entry_scene,
                     "value_type": "entity", "valid_from": turn_time(turn)},
                    # dismissal ends companionship too (#82, Cx 373): supersede the standing
                    # `accompanying` state with the literal empty value (no value_type).
                    {"entity": _did, "attribute": "accompanying", "value": "",
                     "valid_from": turn_time(turn)},
                ]
            p.ingest_structured(_drows, classify="batch")
            trace.npcs_departed = list(dismissed_ids)
            logger.info("player dismissed %s from %s (departed_scene events)",
                        dismissed_ids, _entry_scene)
        except Exception as exc:  # never sink the turn
            logger.warning("dismissal commit failed: %s", exc)

    # 2b. Movement (letter 026): the player's relocation commits
    #     deterministically — refer() resolves the destination as the
    #     player named it, the move goes through the gate as a stated
    #     item, and single-parent semantics supersede the old location.
    #     Unresolved destinations fall back to whatever extraction did,
    #     loudly logged.
    _move_clarify = ""  # ambiguous destination → the world ASKS (founder: never hallucinate)
    # ---- #102 JOURNEY DELIBERATION (Cx 457; founder-shaped 2026-07-04) -----------------
    # When a live deadline stands and a move the map can't prove local would eat the
    # remaining budget, the character's OWN MIND weighs it before a single step is
    # taken — "you consider X, but realize you may (consequence); X or Y?" — one
    # warning, once; re-stating the move proceeds on the CACHED estimate. Deterministic
    # over established facts (Cx: no sheet call needed); the same cheap estimator is
    # the crossing authority, never a fixed floor.
    _delib_deadline = _deadline_remaining(arc, world) if kind == "action" else None

    def _hold_for_deliberation(dest_id: str | None, label: str) -> bool:
        """True = HOLD the move (deliberation briefed). Also caches the pre-commit
        estimate on the trace for the accept/under-budget cases so the turn's time
        advance never re-prices the same movement."""
        if _delib_deadline is None:
            return False
        _dest_key = dest_id or re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
        if dest_id:
            if dest_id == pre_scene:
                return False
            _dchain = [dest_id] + (p.locate(dest_id, as_of=_h) or [])
            if ((len(pre_chain) > 1 and len(_dchain) > 1 and pre_chain[1] == _dchain[1])
                    or dest_id in pre_chain or (pre_scene and pre_scene in _dchain)
                    or _route_connects(p, pre_scene, dest_id, as_of=_h)):
                return False  # provably near — no deliberation on a step
        _key = _journey_accept_key(pre_scene, _dest_key, _delib_deadline[1])
        try:  # accepted before (origin+dest+hazard+coordinate, Cx 457)? proceed, reuse est
            from construct.adapter import frame_facts as _ff
            for _r in _ff(world, SESSION, entity="session:journey_accept",
                          attribute=_key):
                trace.journey_est = int(json.loads(str(_r.value)).get("est", -1))
                return False
        except Exception:  # noqa: BLE001
            pass
        try:  # the SAME cheap estimator, pre-commit — the crossing authority
            from construct.clock import read_clock as _rc
            _clk = _rc(world)
            _est = cohorts.estimate_elapsed(
                provider, now=_clk.render(),
                hours_per_day=_clk.calendar.hours_per_day,
                phases=_clk.calendar.phase_names,
                action=player_input, narration="",
                distance_unknown=f"{pre_scene}->{_dest_key}")
            _est_min = max(0, int(_est.get("advance_minutes") or 0))
            trace.cohort_calls.append("estimate_elapsed:precommit")
        except Exception:  # noqa: BLE001 — estimation failure never blocks movement
            return False
        if _est_min < _delib_deadline[0]:
            trace.journey_est = _est_min  # fits the budget — commit, reuse the price
            return False
        p.ingest_structured([{  # the one-warning marker carries the cached estimate
            "entity": "session:journey_accept", "attribute": _key,
            "value": json.dumps({"est": _est_min, "turn": turn}),
            "value_type": "literal", "valid_from": turn_time(turn),
        }], frame=SESSION, classify="batch")
        trace.movement_status = "deliberating"
        trace.deliberating = (f"{label} — roughly {_est_min} minutes of travel against "
                              f"about {int(_delib_deadline[0])} minutes left")
        logger.info("journey held for deliberation: %s", trace.deliberating)
        return True

    if moves_to:
        # SEEK-A-PERSON unwrap (founder live 2026-07-01, "I go back to where Reed is"): the
        # "where X is" wrapper defeats refer's token match, so the move resolved NOTHING and the
        # player never traveled — the narrator then conjured a ghost arrival instead. Strip the
        # wrapper to the inner referent; the person→place redirect below (Cx 003) then carries
        # the player to X's TRUE location.
        _seek = re.match(r"(?i)^\s*(?:back\s+to\s+)?(?:to\s+)?where(?:ver)?\s+(.+?)\s+(?:is|was)\s*$",
                         moves_to.strip())
        if _seek:
            moves_to = _seek.group(1).strip()
            logger.info("seek-a-person move unwrapped -> %r", moves_to)
        # Resolve the move destination at the play horizon (Cx 257 fresh-hunt): a HEAD refer
        # would resolve a place that only exists in the source AFTERMATH, and route()'s
        # `no_path` returns empty segments (seg is None) — so a future-only place would fall
        # through and commit as live movement. as_of=_h confines the candidate set.
        res = world.refer(moves_to, frame="canon", as_of=_h)
        status = getattr(res, "status", None)
        target = getattr(res, "entity_id", None)
        # ORIGINAL refer outcome, captured BEFORE the guards below null `status`/`target` (Cx 288):
        # the move-permanence grant must fire ONLY on a genuine ZERO-CANDIDATE miss — never when
        # refer actually RESOLVED a name (a horizon-absent / aftermath place was resolved-then-
        # dropped, an entitlement/person case stays "resolved") nor when refer was UNDERDETERMINED
        # with candidates (ambiguous — resolving by slug would violate PB's reference contract).
        _orig_status = status
        _orig_candidates = tuple(getattr(res, "candidates", None) or ())
        trace.move_debug = (f"moves_to={moves_to!r} status={_orig_status!r} "
                            f"target={target!r} cands={len(_orig_candidates)}")
        # Horizon-presence guard (Cx 257): `refer` resolves an entity by its registered NAME
        # even when that entity only EXISTS in the source AFTERMATH — tier-1 identity lookup
        # bypasses the as_of candidate filter. So confirm the target is present at the play
        # horizon (has_entity is horizon-bound) before treating it as a reachable destination;
        # a future-only place is not here yet. No-op for ordinary timeless geography.
        if status == "resolved" and target and not live_reads.has_entity(target):
            logger.info("move target %s absent at the play horizon; not resolving", target)
            status, target = None, None
        # Entitlement gate (INVESTIGATION-SHAPE.md §3c / Cx 061 #3): for OFFSCENE cast, canon
        # referability is NOT player entitlement. Movement to the person OR their authored
        # place is blocked until the player has LEARNED their whereabouts (a `whereabouts` row
        # in knows:<protagonist>, written by the discovery step). Otherwise a guessed name/
        # place skips the discovery chain and layer-1 topology collapses into layer-2.
        _cbi = (cast if isinstance(cast, dict)
                else {n.node_id: n for n in cast}) if cast else {}

        def _name_of(e: str) -> str:
            # Display name at the play horizon (the canon snapshot isn't built until step 3, after
            # movement) — live_reads is horizon-bound and returns the unwrapped value or None.
            try:
                v = live_reads.state(e, "name")
            except Exception:
                return ""
            return v if isinstance(v, str) else ""

        def _undiscovered_offscene(n) -> bool:
            return (getattr(n, "presence", "") == "offscene" and bool(getattr(n, "location", ""))
                    and not live_reads.assertion_in_frame(
                        player_frame, n.node_id, "whereabouts", n.location))
        if status == "resolved" and target and cast:
            _tnode = _cbi.get(target)
            _gate = (_tnode is not None and _undiscovered_offscene(_tnode)) or any(
                _undiscovered_offscene(n) for n in _cbi.values() if n.location == target)
            if _gate:
                trace.movement_status = "undiscovered"
                logger.info("movement to undiscovered offscene target %s blocked "
                            "(no learned whereabouts)", target)
                target = None
        # Movement guard (INVESTIGATION-SHAPE.md §3c / Cx 057): a route resolves to a
        # PLACE. If the player named a PERSON ("go to Parker"), travel to that person's
        # location — never set the protagonist `in` a person. If their whereabouts aren't
        # placed/known, don't teleport; the narrator handles it diegetically.
        if status == "resolved" and target and target.startswith("person:"):
            _pchain = p.locate(target, as_of=_h)
            _person_place = _pchain[0] if _pchain else None
            if _person_place:
                logger.info("route to person %s redirected to their place %s",
                            target, _person_place)
                target = _person_place
            else:
                logger.info("route to person %s has no known place; not moving", target)
                target = None
        if status == "resolved" and target and not target.startswith("place:"):
            # RESOLVED NON-PLACE target (Cx 327): `refer("the table")` can resolve to a same-scene
            # `obj:table` (already in canon / minted by player-input extraction). A person is NEVER
            # located IN an object — committing `person.in = obj:table` is the cast-disappearance /
            # person-in-object desync. Absorb it: in-scene repositioning (fixture head, or the target
            # sits in the current scene), no location row. A resolved non-place that ISN'T a scene
            # absorb case is simply not a destination — don't commit it; the narrator handles it.
            _tchain = p.locate(target, as_of=_h) or []
            _in_scene_obj = bool(pre_scene and pre_scene in _tchain) or bool(
                pre_chain and _tchain and _tchain[0] == pre_chain[0])
            if _dest_head(moves_to) in _FIXTURE_HEADS or _in_scene_obj:
                trace.movement_status = "in_scene"
                logger.info("resolved non-place target %r (fixture/scene-object) — in-scene, not travel",
                            target)
            else:
                logger.info("resolved non-place target %r is not a location; narration handles", target)
            target = None  # never relocate into a non-place
        if status == "resolved" and target and target == pre_scene:
            # EXACT current-room naming (Cx 447 blocker): "I go to the study" while
            # standing in the study is a no-op — no relocation row, no route check,
            # and NO move-bucket time charge (the 445 wrinkle, now on ALL paths).
            trace.movement_status = "clear"
            trace.same_place = True
            target = None
            logger.info("move %r resolved to the CURRENT scene — already here", moves_to)
        if status == "resolved" and target:
            # Passability (PB route(), RFC-003): a `blocked` way (a portal with a
            # blocking state/relation under the declared traversal policy) is not
            # walked — the narrator explains why. `obscured` (state unknown) is
            # allowed but flagged so the prose can hedge; missing capture degrades
            # to obscured/clear, never a false hard-block.
            origin = pre_chain[0] if pre_chain else None
            seg = _route_obstruction(p, origin, target, as_of=_h)
            if seg and seg.get("status") == "blocked":
                trace.movement_status = "blocked"
                trace.movement_obstruction = seg
                logger.info("movement blocked: %s -> %s (%s)", arc.protagonist,
                            target, seg.get("evidence"))
            elif _hold_for_deliberation(target, moves_to):
                pass  # #102 (Cx 465 #2): only a move that WOULD commit deliberates
            else:
                p.ingest_structured([{
                    "entity": arc.protagonist, "attribute": "in", "value": target,
                    "value_type": "entity", "valid_from": turn_time(turn),
                }], classify="batch")
                trace.movement_status = seg.get("status") if seg else "clear"
                if seg:
                    trace.movement_obstruction = seg
                logger.info("player moved: %s -> %s (%s)", arc.protagonist, target,
                            trace.movement_status)
        elif cast and _names_undiscovered_dest(moves_to, _cbi, _undiscovered_offscene, _name_of):
            # ENTITLEMENT GATE for an UNRESOLVED name (Cx review #1): the gate above runs only on a
            # RESOLVED target, so a guessed/unresolved VARIANT of an undiscovered offscene suspect or
            # their authored location would otherwise reach the mint and teleport the player near
            # them. Deny it here too — the narrator renders "you don't know where that is yet."
            trace.movement_status = "undiscovered"
            logger.info("unresolved move %r names an undiscovered offscene target; not minting",
                        moves_to)
        elif (_orig_status != "resolved" and not _orig_candidates
              and trace.movement_status not in ("undiscovered", "blocked")
              and not _move_touches_secret(moves_to, arc, live_reads)):
            # MOVEMENT PERMANENCE (founder: "I said I went to Harrow's office"): a GENUINE
            # zero-candidate miss — refer resolved nothing and offered no candidates — so the
            # destination is a NAMED, improvised/narrated location. Mint it and commit the move, so
            # the narrated arrival is REAL and the next turn renders the NEW scene (not the stale
            # prior one with the wrong cast present). Excluded by the guards above: a horizon-absent
            # / aftermath place (refer RESOLVED it, then Cx 257 dropped it), an ambiguous reference
            # (candidates present), an undiscovered offscene suspect (gate above + the resolved gate),
            # and a blocked route. The concealment guard here is the NARROW `_move_touches_secret`
            # (founder cohesion test, 2026-06-29) — it blocks conjuring a place named after the hidden
            # ANSWER ("the rival's lair") but NOT one sharing a common clue word ("coffee house",
            # where a "lodging house" clue had polluted the broad take-guard with "house"). A mint only
            # ever fires on a ZERO-candidate miss (the place does NOT exist in canon), so a fresh empty
            # place leaks no secret; reaching an EXISTING hidden place is the entitlement gate's job.
            # Best-effort; a miss → "rely on extraction".
            # IN-SCENE FIXTURE GUARD (Cx 325, blind-test): a move "to" a FIXTURE/object of the current
            # scene ("step to the table", "go to the rain barrel") is repositioning WITHIN the room, not
            # travel to a navigable place. Minting `place:table` walked the player out of the briefing
            # room and abandoned the colocated cast (npcs=- / "Maud is not here"). Absorb it: no mint, no
            # `protagonist.in` row — the player stays in-scene with the people. Head-noun based (the
            # fixture is prose, not a structured feature). Navigable place heads ("office", "yard",
            # "lane", "kitchen") fall through to the mint and still travel (founder "Harrow's office").
            if _dest_head(moves_to) in _FIXTURE_HEADS:
                trace.movement_status = "in_scene"  # no mint, no relocation — stay with the people
                logger.info("move %r is an in-scene fixture (head %r) — repositioning, not travel",
                            moves_to, _dest_head(moves_to))
            else:
                # a DEICTIC destination ("back", "outside") is geography, never a reference
                # to a named roster place — skip the bind, let the mint path refuse as before.
                _slug_probe = re.sub(r"[^a-z0-9]+", "_",
                                     str(moves_to).lower()).strip("_")
                _deictic = _slug_probe in _DEICTIC_DEST
                # THE KNOWN-WORLD PLACE ROSTER, built FIRST (Cx 356 / Cx 390): scope alone
                # misses authored geography (production bodycase scope holds ONE place, not
                # bluegate_yard) — enumerate `place:` entities from canon + the player's frame
                # (horizon-screened by the name/kind read through live_reads), excluding
                # UNDISCOVERED offscene cast locations (entitlement gate, Cx 354) and
                # redacting concealed values. Serves the compound-container check, the
                # semantic bind, AND the mint.
                _roster: list = []
                if not _deictic:
                    try:
                        from construct.arc.executor import concealed_tokens, value_leaks
                        _ctoks = concealed_tokens(arc_protected_keys(arc))
                        _excl = {n.location for n in (_cbi or {}).values()
                                 if _undiscovered_offscene(n) and n.location} if cast else set()
                        _cand_places = set(scope or []) | ({pre_scene} if pre_scene else set()) \
                            | set(pre_chain or [])
                        # BOUNDED-READS (PB 092): every enumeration names its frame —
                        # canon (world truth) + the player's own knowledge; the old
                        # unframed scan is not expressible on the porcelain, by design.
                        for _frm in ("canon", player_frame):
                            try:
                                for _pid2 in world.porcelain.entities(
                                        _frm, prefix="place:"):
                                    _cand_places.add(_pid2 or "")
                            except Exception:
                                pass  # enumeration is best-effort; scope∪chain still serve
                        _cand_places -= _excl | {""}
                        for _pid in sorted(_cand_places):
                            if not str(_pid).startswith("place:"):
                                continue
                            _bits = []
                            for _a in ("name", "kind"):
                                if (_pid, _a) in arc_protected_keys(arc):
                                    continue
                                _v = live_reads.state(_pid, _a)
                                if _v and not value_leaks(str(_v), _ctoks):
                                    _bits.append(str(_v))
                            if not _bits and _pid not in set(scope or []):
                                continue  # not horizon-present/readable — not a bind target
                            _label = " — ".join(_bits) or _pid.split(":", 1)[-1] \
                                .replace("_", " ")
                            # THE CURRENT SCENE IS A BIND TARGET (founder live, the
                            # drawing-room twin): a synonym for the room the player is
                            # STANDING IN ("the drawing room" in an established parlor)
                            # must bind to it, not mint a twin — its exclusion here was
                            # the hole. Marked so the judge knows it's where they are.
                            if _pid == pre_scene:
                                _label += " (the room the player is in RIGHT NOW)"
                            _roster.append((_pid, _label))
                    except Exception:  # roster is best-effort; reuse/bind/mint degrade
                        logger.warning("place roster build failed", exc_info=True)
                        _roster = []

                def _do_grant() -> None:
                    """The improv mint (shared by the compound-container path and the
                    zero-candidate fallback) — route/passability gated inside; the
                    deliberation hold runs AFTER the grant's own passability gate
                    (Cx 465 #2), via the callable it invokes just before minting."""
                    nonlocal _move_clarify
                    granted, _gseg = _grant_moved_place(
                        world, arc.protagonist, moves_to, at=turn_time(turn),
                        p=p, origin=pre_chain[0] if pre_chain else None,
                        as_of=_h, roster=_roster,
                        hold_check=lambda: _hold_for_deliberation(None, moves_to))
                    if _gseg and _gseg.get("status") == "ambiguous":
                        # #101 (Cx 445): an ambiguous locative tail ("in the village",
                        # two known villages) → the ask path, never a guessed mint.
                        trace.movement_status = "ambiguous"
                        _move_clarify = str(moves_to)
                        logger.info("move %r container ambiguous — clarify beat (%s)",
                                    moves_to, _gseg.get("evidence"))
                    elif _gseg and _gseg.get("status") == "blocked":
                        trace.movement_status = "blocked"
                        trace.movement_obstruction = _gseg
                    elif granted:
                        trace.movement_status = _gseg.get("status") if _gseg else "clear"
                        if _gseg:
                            trace.movement_obstruction = _gseg
                    else:
                        logger.warning("movement destination %r did not resolve (%s); "
                                       "relying on extraction", moves_to, status)

                if _embedded_container(moves_to, _roster) is not None:
                    # #91 (Cx 390 blocker): COMPOUND-CONTAINED DETECTION WINS over simple
                    # known-place reuse — "the Liddell warehouse, to the foreman's office"
                    # token-matches the warehouse, and the reuse path would flatten the
                    # player INTO the container, never minting the durable child scene
                    # (and stranding whoever is really there). A unique container + tail
                    # goes straight through the mint; its passability gate still runs.
                    _do_grant()
                elif (_known := _match_known_place(
                        moves_to,
                        set(scope or []) | ({pre_scene} if pre_scene else set())
                        | set(pre_chain or []),
                        live_reads, _name_of)) and _known != pre_scene \
                        and not _hold_for_deliberation(_known, moves_to):
                    # reuse an already-KNOWN place by token ("my own office" → the existing
                    # office) so a return home doesn't mint a duplicate (founder cohesion test).
                    p.ingest_structured([{
                        "entity": arc.protagonist, "attribute": "in", "value": _known,
                        "value_type": "entity", "valid_from": turn_time(turn),
                    }], classify="batch")
                    trace.movement_status = "clear"
                    logger.info("move resolved to KNOWN place %s (reused, not minted)", _known)
                elif _known == pre_scene:
                    trace.movement_status = "clear"  # naming the current place → already here
                    trace.same_place = True          # Cx 445: no time charge for a no-op
                else:
                    # SEMANTIC BIND BEFORE MINT (Cx 354 A, founder phantom-scene incident): the
                    # destination may be a DEFINITE DESCRIPTION of an established place by ROLE
                    # ("the scene of the crime" → the authored murder-scene yard) that token
                    # matching can't bind — minting here forked the world (place:scene_of_the_
                    # crime, an invented indoor room contradicting the outdoor yard). One cheap
                    # call over the ENTITLED roster decides existing/new/ambiguous.
                    # existing → travel there (same commit as the known-place reuse above);
                    # new → mint as before (improv-travel preserved); ambiguous → no commit, the
                    # narrator handles it diegetically. Fail-open to the mint on any error.
                    _bound = None
                    _amb = False
                    try:
                        if _deictic:
                            raise LookupError("deictic destination — bind skipped")
                        if _roster:
                            _dv = cohorts.resolve_destination(provider, moves_to, _roster)
                            trace.cohort_calls.append("resolve_destination:cheap")
                            if _dv.get("verdict") == "existing" and \
                                    _dv.get("match") in {pid for pid, _ in _roster}:
                                _bound = _dv["match"]
                            elif _dv.get("verdict") == "ambiguous":
                                _amb = True
                    except Exception as exc:  # never sink the turn — fall to the mint
                        (logger.info if _deictic else logger.warning)(
                            "destination bind skipped (%s)", exc)
                    if _bound:
                        # ALIAS ACCRUAL (founder: "the bar's basement" must find the tavern
                        # cellar): a successful semantic bind teaches the world the player's
                        # word — one cheap call per synonym ONCE, then refer() tier-1a binds
                        # it deterministically forever (PB's by_alias index reads this row).
                        try:
                            _alias = re.sub(
                                r"^\s*(?:the|a|an|my|your|his|her|its|their|our)\s+", "",
                                str(moves_to).strip(), flags=re.IGNORECASE).strip()
                            if _alias and _alias.lower() not in (
                                    str(live_reads.state(_bound, "name") or "").lower(),):
                                p.ingest_structured([{
                                    "entity": _bound, "attribute": "alias", "value": _alias,
                                    "valid_from": turn_time(turn),
                                }], classify="batch")
                                logger.info("alias learned: %s known_as %r", _bound, _alias)
                        except Exception:  # noqa: BLE001 — alias learning is enrichment
                            pass
                        if _bound == pre_scene:
                            # a synonym for the room they're STANDING IN — already here;
                            # no relocation row, no twin (the drawing-room incident).
                            trace.movement_status = "clear"
                            trace.same_place = True  # Cx 445: no time charge for a no-op
                            logger.info("move %r bound to the CURRENT scene %s — already here",
                                        moves_to, _bound)
                        else:
                            # SAME MOVEMENT GATES AS RESOLVED TRAVEL (Cx 358 blocker): a bound
                            # destination must not teleport through a blocked route — run the
                            # passability check exactly as the resolved branch does; blocked →
                            # no commit + obstruction on the trace; obscured → commit but hedge.
                            # Deliberation runs AFTER passability (Cx 465 #2): only a move
                            # that WOULD commit may render as a deadline choice.
                            _seg = _route_obstruction(p, pre_chain[0] if pre_chain else None,
                                                      _bound, as_of=_h)
                            if _seg and _seg.get("status") == "blocked":
                                trace.movement_status = "blocked"
                                trace.movement_obstruction = _seg
                                logger.info("bound move blocked: %s -> %s (%s)", arc.protagonist,
                                            _bound, _seg.get("evidence"))
                            elif _hold_for_deliberation(_bound, moves_to):
                                pass  # #102: held for the player's own weighing
                            else:
                                p.ingest_structured([{
                                    "entity": arc.protagonist, "attribute": "in", "value": _bound,
                                    "value_type": "entity", "valid_from": turn_time(turn),
                                }], classify="batch")
                                trace.movement_status = _seg.get("status") if _seg else "clear"
                                if _seg:
                                    trace.movement_obstruction = _seg
                                logger.info("move %r semantically BOUND to %s (%s)", moves_to,
                                            _bound, trace.movement_status)
                    elif _amb:
                        # ASK, NEVER HALLUCINATE (founder 2026-07-04): an ambiguous
                        # destination gets a CLARIFY beat — the world asks which the player
                        # means, in-fiction; no mint, no relocation, no invented arrival.
                        trace.movement_status = "ambiguous"
                        _move_clarify = str(moves_to)
                        logger.info("move %r ambiguous against roster — clarify beat, "
                                    "no mint, no relocation", moves_to)
                    else:
                        _do_grant()
        elif trace.movement_status != "in_scene" and not trace.same_place:
            # an absorbed in-scene fixture / already-here no-op is handled, not a miss
            logger.warning("movement destination %r did not resolve (%s); "
                           "relying on extraction", moves_to, status)

    # ---- #101 DISTANCE: THE NEARNESS INVERSION (Cx 454; founder's shape challenge) -----
    # The map is authoritative about NEARNESS, never farness. A committed move is
    # provably near when: destination shares the origin's immediate parent (siblings in
    # one site); either terminus sits on the other's containment chain (stepping in/out);
    # or a route segment directly connects them. Everything else is DISTANCE UNKNOWN —
    # not "long", not "a journey", just unpriceable by the map — and the time estimator
    # (which already knows what a city or a kingdom is) prices it from the fiction.
    # The old disjoint-chain farness proxy, the settlement vocabulary, and the durable
    # journey event all retire: derived farness is never stored (Cx 454 hard rule).
    if (trace.movement_status in ("clear", "obscured") and not trace.same_place
            and pre_chain):
        try:
            _post_chain = p.locate(arc.protagonist, as_of=_h) or []
            if _post_chain and _post_chain[0] != pre_chain[0]:
                _near = (
                    (len(pre_chain) > 1 and len(_post_chain) > 1
                     and pre_chain[1] == _post_chain[1])       # siblings in one site
                    or _post_chain[0] in pre_chain             # stepped INTO containment
                    or pre_chain[0] in _post_chain             # stepped OUT of it
                )
                if not _near:
                    # route evidence (Cx 458): a known DIRECT passable way connecting
                    # the termini — read via the dedicated existence check, because
                    # _route_obstruction() returns None for exactly the clear routes
                    # that prove nearness.
                    _near = _route_connects(p, pre_chain[0], _post_chain[0], as_of=_h)
                if not _near:
                    trace.distance_unknown = f"{pre_chain[0]}->{_post_chain[0]}"
                    logger.info("move distance UNKNOWN (map can't prove local): %s",
                                trace.distance_unknown)
        except Exception as exc:  # noqa: BLE001 — detection is enrichment, never a gate
            trace.dropped_cohorts.append(f"nearness_check ({exc})")

    # 2b-ii. COMPANION MOVEMENT (Cx 363/365: "Sir? Shall we…"): commit `in` rows for the
    # companions the player's move PLAINLY included — ONCE, after the movement chain, keyed on
    # the route gate having ACCEPTED the move (clear/obscured) on ANY commit path (resolved /
    # known-reuse / semantic-bound / mint). Never on blocked/undiscovered/ambiguous/in_scene/
    # failed-mint/same-place no-op. Same valid_from as the player's own move (Cx 363).
    # STANDING COMPANIONS (#82, the Reed ping-pong): every present NPC whose `accompanying`
    # state names the protagonist comes along on ANY accepted move — the standing canon state
    # decides, not this turn's wording. Dismissed-this-turn wins; already-listed skipped.
    if trace.movement_status in ("clear", "obscured"):
        for _pid in _npc_by_oid.values():
            if _pid in moved_with_ids or _pid in dismissed_ids:
                continue
            try:
                if live_reads.state(_pid, "accompanying") == arc.protagonist:
                    moved_with_ids.append(_pid)
            except Exception:  # noqa: BLE001 — a miss just means no standing companionship
                pass
    if moved_with_ids and trace.movement_status in ("clear", "obscured"):
        try:
            _post_chain = p.locate(arc.protagonist, as_of=_h)
            _new_scene = _post_chain[0] if _post_chain else None
            if _new_scene and _new_scene != _entry_scene:
                p.ingest_structured([
                    {"entity": _cid, "attribute": "in", "value": _new_scene,
                     "value_type": "entity", "valid_from": turn_time(turn)}
                    for _cid in moved_with_ids], classify="batch")
                trace.npcs_moved_with = list(moved_with_ids)
                logger.info("companions moved with player: %s -> %s",
                            moved_with_ids, _new_scene)
        except Exception as exc:  # never sink the turn
            logger.warning("companion movement commit failed: %s", exc)

    # 2b-iii. COMPANIONSHIP STATE (#82, Cx 372/373): an invitation ("stick with me") or an
    # accepted bring-along move makes companionship STANDING canon — an ordinary world-truth
    # row through the ingest doorway ({npc, accompanying, protagonist}), like possession.
    # From here on every accepted player move carries them (2b-ii above) with no per-turn
    # wording dependence; dismissal (2a-ii) supersedes it with the empty literal.
    _new_companions = [
        _cid for _cid in dict.fromkeys(joins_ids + list(trace.npcs_moved_with))
        if _cid not in dismissed_ids]
    if _new_companions:
        try:
            p.ingest_structured([
                {"entity": _cid, "attribute": "accompanying", "value": arc.protagonist,
                 "value_type": "entity", "valid_from": turn_time(turn)}
                for _cid in _new_companions], classify="batch")
            trace.npcs_joined = list(_new_companions)
            logger.info("companionship committed: %s accompanying %s",
                        _new_companions, arc.protagonist)
        except Exception as exc:  # never sink the turn
            logger.warning("companionship commit failed: %s", exc)

    # 2c. Possession (parallel to movement): when the player TAKES an object, record it
    #     as HELD (obj.in = the protagonist) deterministically — so the adjudicator and
    #     the narrator agree the player has it. (Founder's ledger bug: the player tucked
    #     the ledger under their arm but canon never tracked possession, so a later "set
    #     it back" was wrongly denied. Host-side + coreference-proof: "I take X" → X is
    #     with you, never the pronoun-phantom the extraction sometimes invents.)
    if takes:
        # SCOPED (founder synonym mandate): scene + held — "the blade" binds the
        # scene's knife at tier 2 instead of minting a sibling obj:blade.
        ores = world.refer(takes, scope=[e for e in (pre_scene, arc.protagonist) if e],
                           frame="canon", as_of=_h)  # take only a horizon-present object (Cx 257)
        otarget = getattr(ores, "entity_id", None)
        # Horizon-presence guard (Cx 257): don't grant possession of a future-only object that
        # `refer` matched purely by its registered name; it doesn't exist yet at the opening.
        if otarget and not live_reads.has_entity(otarget):
            logger.info("take target %s absent at the play horizon; not granting", otarget)
            otarget = None
        if (getattr(ores, "status", None) == "resolved" and otarget
                and otarget != arc.protagonist and otarget not in _NARRATOR_PHANTOM
                and otarget not in _PRONOUN_PHANTOM):
            p.ingest_structured([{
                "entity": otarget, "attribute": "in", "value": arc.protagonist,
                "value_type": "entity", "valid_from": turn_time(turn),
            }], classify="batch")
            trace.took = otarget
            logger.info("player took: %s -> held by %s", otarget, arc.protagonist)
        elif takes and not _take_touches_secret(takes, arc, live_reads):
            # ENTITY AUTHORITY (Cx 304): before MINTING, BIND by token to an object already present
            # in the scene/held set — so "take the pencil" grabs the scene's `obj:pencil` instead of
            # spawning a twin `obj:pencil_1` (the live bug: `refer` missed it by name; the bounded
            # token matcher catches it; one identity authority shared with the prose resolver).
            def _live_name(e: str) -> str:
                try:
                    v = live_reads.state(e, "name")
                except Exception:
                    v = None
                return v if isinstance(v, str) else ""
            _take_cands = (set(scope or []) | set(_pre_held)
                           | set(pre_chain or []) | ({pre_scene} if pre_scene else set()))
            _bound, _why = bind_or_mint(takes, kind="obj", candidates=_take_cands,
                                        protagonist=arc.protagonist, name_of=_live_name)
            if _bound and str(_bound).startswith("obj:") and _bound != arc.protagonist:
                p.ingest_structured([{
                    "entity": _bound, "attribute": "in", "value": arc.protagonist,
                    "value_type": "entity", "valid_from": turn_time(turn),
                }], classify="batch")
                trace.took = _bound
                logger.info("player took (bound present object): %s -> held by %s",
                            _bound, arc.protagonist)
            elif _why == "mint":
                # IMPROV-OBJECT PERMANENCE (founder: "a mug from the bar doesn't not exist"): the take
                # named an object NOT present in canon (ZERO candidates). If it's an ordinary thing
                # plainly present in the scene, grant world permanence — mint ONE fresh obj held by the
                # player. A specific/named/load-bearing object is not minted (the gate denies). Only a
                # genuine `mint` signal reaches here — an AMBIGUOUS take must NOT spawn a sibling (Cx
                # 306): it falls through to no canon write + a receipt, below.
                granted = _grant_taken_object(world, arc.protagonist, takes, pre_scene,
                                              provider, at=turn_time(turn),
                                              laws=_laws_full)
                if granted:
                    trace.took = granted
            else:
                # ambiguous / dropped — multiple present matches or a voice/malformed mention. No canon
                # write (never a third sibling); surface a receipt and let the narrator handle it.
                trace.resolver = (trace.resolver or []) + [(takes, "takes", _why)]
                logger.info("take %r unresolved (%s); no mint", takes, _why)

    # 2c-ii. DROP (the inverse of take, founder cohesion test): when the player SETS DOWN a HELD
    #     object, commit it into the current place — so a dropped thing actually STAYS where it was
    #     left and doesn't snap back to the pocket next turn (the prose said "you set it down" but
    #     canon kept it held). Only a thing currently in the protagonist's possession can be set
    #     down here; otherwise the narrator handles it. Deterministic, parallel to the take commit.
    if drops and pre_scene:
        dres = world.refer(drops, scope=[e for e in (arc.protagonist, pre_scene) if e],
                           frame="canon", as_of=_h)  # held first: you drop what you hold
        # Resolve to an object the player ACTUALLY HOLDS first (you can only set down what you hold);
        # fall back to global refer. This sidesteps a FRAGMENTED same-named twin where refer picks the
        # un-held `obj:pencil` while the held one is the take-mint's `obj:pencil_1` (Cx 297 follow-on,
        # found live: drops resolved but to the wrong twin, so the drop never fired).
        _held_match = _match_held_object(drops, _pre_held, live_reads)
        dtarget = _held_match or getattr(dres, "entity_id", None)
        _resolved = bool(_held_match) or getattr(dres, "status", None) == "resolved"
        # "Actually held" reads the PRE-extraction view (_pre_held) UNION the live chain: the
        # player-input extraction may already have moved the named object into a container it
        # mentioned ("set the pencil down on a table" → `obj:pencil in obj:table`, an unlocated
        # furniture entity), which would otherwise defeat this check. The deterministic drop is
        # AUTHORITATIVE over that licensed container phrase: commit `obj in pre_scene` (the safe
        # default — the object stays in the CURRENT place), at a within-turn sub-tick so it
        # supersedes the same-`valid_from` container row (Cx 295).
        _was_held = (dtarget in _pre_held
                     or arc.protagonist in (p.locate(dtarget, as_of=_h) or []))
        if (_resolved and dtarget
                and dtarget not in _NARRATOR_PHANTOM and dtarget not in _PRONOUN_PHANTOM
                and _was_held):
            # Commit at a within-turn SUB-TICK (+0.5; turns are spaced 1.0 apart) so the deterministic
            # drop strictly supersedes any same-`valid_from` container row the player-input extraction
            # wrote — PB's tie-break at equal coordinates does not otherwise favor this later structured
            # write (Cx 295). Semantically true: the set-down happens after the input is read.
            p.ingest_structured([{
                "entity": dtarget, "attribute": "in", "value": pre_scene,
                "value_type": "entity", "valid_from": turn_time(turn) + 0.5,
            }], classify="batch")
            trace.dropped = dtarget
            logger.info("player set down: %s -> %s (left in place)", dtarget, pre_scene)

    # 3. Scene + the canon materialization (ONE snapshot serves the tick).
    chain = p.locate(arc.protagonist, as_of=_h)
    scene = chain[0] if chain else None
    # Diegetic time (DIEGETIC-TIME.md): the current moment on the governing
    # calendar (the player's place → world default), read for the briefing now and
    # advanced after the render. Best-effort — the clock never sinks a turn.
    try:
        from construct.clock import read_clock
        _clock = read_clock(world, scene)
        trace.time_now = _clock.render()
    except Exception:
        logger.exception("clock read failed")
        _clock = None
    if scope is None:
        scope = sorted(e for e in arc_entities(arc) if live_reads.has_entity(e))
        trace.point_reads += len(arc_entities(arc))
    # The scene's structural FEATURES — its `part_of`-children (PLACE-FEATURE-
    # ABSTRACTION-V1, PB 070): a place's sub-features (a hatch in the dome, the
    # desk in the office) are pulled into scope so their facts (incl. `feel`)
    # surface, and listed for the narrator. Empty until `part_of` is authored.
    scene_features = []
    if scene:
        try:
            scene_features = list(p.features(scene, as_of=_h))
        except Exception:  # read unsupported / error — never break the turn
            scene_features = []
    snap_scope = list(scope) + ([scene] if scene else []) + scene_features
    canon_snap = _snap_or_empty(p, snap_scope, as_of=_h)
    canon_table = _table(canon_snap)

    _mirror_rows(p, receipt_rows, player_frame, canon_table, trace, as_of=_h)
    touched = {row["entity"] for row in receipt_rows}
    if touched & arc_entities(arc):
        p.ingest_structured([
            {"entity": f"event:arc_touch_{turn}", "attribute": "kind",
             "value": "arc_touch", "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # arc-touch marker — bookkeeping

    # 4. World tick (strict order; beats LAST). Atoms read LIVE canon
    #    directly: per-key folds are ~0.2ms post-engine-037 (were seconds
    #    pre-fix), so the SnapshotReads batching that existed only for the
    #    old cost is retired — and reading live is more correct (clocks
    #    and beats see this turn's own commits). Snapshots below are kept
    #    only where a materialized fact LIST is needed (briefing, mirror).
    # Gauge drain FIRST (GAUGE §3, Cx 150): commit each gauge's signed per-turn
    # delta before clocks/beats/outcome so a crossed floor is visible to terminal
    # and Quantity-driven-clock evaluation THIS turn (not the post-render time slot).
    trace.gauge_levels = gauge_pass(world, arc, player_input, as_of=_h)
    # For a TIME-DEADLINE arc only (Cx 173 #3): advance diegetic time HERE — before clocks/beats/
    # outcome — so a single big-jump action ("I wait three hours", "I go watch the movie") crosses
    # the authored deadline (`failure_when` = Quantity over time:elapsed) on the SAME turn it's taken
    # (obviously the bomb goes off). The render's `trace.time_now` was read pre-advance and is left
    # unchanged, so the narration's time-of-day is unaffected; only the terminal check sees it. Every
    # NON-deadline turn keeps the richer post-render estimate (with narration), byte-for-byte as before.
    _time_committed = False
    if _clock is not None and _has_time_deadline(arc):
        _advance_diegetic_time(world, _clock, player_input, trace, provider, narration="")
        _time_committed = True
    counters = counters_from_session(live_reads, arc)
    trace.clocks_fired = clock_pass(world, arc, live_reads, counters, turn)
    # Side arcs tick on the same shared pacing counters (whole-scene property,
    # P1 simplification): their clocks live in the same plot:main frame, keyed by
    # unique ids, so they fire independently without colliding with the main arc.
    for sa in side_arcs:
        if stored_lifecycle(live_reads, sa) in LIFECYCLE_TERMINALS:
            continue  # concluded arcs no longer tick
        trace.clocks_fired += clock_pass(world, sa, live_reads, counters, turn)

    with _phase(trace, "furnish"):
        furnish_scene(p, scene, player_frame, canon_table, trace, as_of=_h)
    # SCENE-IMAGERY (founder: start the image gen ASAP, in parallel): the scene's
    # description is committed now — fire the detection/render hook here so the
    # picture renders WHILE the NPC actions + narration below run, and is ready to
    # show just before this scene's prose. Best-effort; never affects the turn.
    if on_scene is not None:
        try:
            on_scene()
        except Exception:
            logger.debug("on_scene hook failed", exc_info=True)

    # NPCs PRESENT in the scene drive their own action + speech. Presence is
    # CONTAINMENT-AWARE, not an exact `in == scene` match (founder bug: NPCs the cold
    # open narrates as HERE were going inert and never acting). A person counts as
    # present if they share the player's immediate place, OR they are anywhere within
    # the player's scene, OR their room sits on the player's own location chain — so a
    # small authoring granularity gap (player at the colony level, the clerk in a room
    # within it) no longer silences them. A person with NO location is never present.
    def _present(e: str) -> bool:
        if not scene:
            return False
        if _departed_from(p, live_reads, e, scene, as_of=_h):
            return False  # dismissed/departed and not re-placed — negative scene truth (Cx 364)
        if canon_table.get((e, "in")) == scene:  # fast path: exact same place
            return True
        npc_chain = p.locate(e, as_of=_h)
        trace.point_reads += 1
        return _colocated(npc_chain, scene, chain)

    # PRESENT-BUT-UNSEEN (#94 campaign F12, Cx 408): union the scene's canonical persons
    # with scope via the shared containment walk (`_persons_under` matches `_present`'s
    # nested-containment shape) — someone physically in the room, or in a child place of
    # it, is discovered by definition; scope-gated enumeration made the colocated Tin Ear
    # invisible ("none besides you"). `_present` stays the authority.
    npcs = [e for e in sorted(set(scope or []) | _persons_under(p, scene, _h))
            if e.startswith("person:") and e != arc.protagonist and _present(e)]
    # ---- #97 THE REMEMBRANCER (REMEMBRANCER.md, Cx 434) --------------------
    # The protagonist's own memory as a silent participant, symmetric with npc_turn.
    # GATED (constraint 2): self-questions, deliberate recall, declarations, and
    # protagonist-knowledge turns — never ordinary look-around. A DECLARATION commits
    # FIRST (constraint 6: the mind reacts to the new autobiography), then memory_turn
    # rides the same cheap parallel batch as the NPC decisions.
    memory_result: dict | None = None
    _memory_tensions: list[str] = []
    _memory_gate = (asks_self or recalls or declares_memory or uses_knowledge) \
        and kind in ("action", "question")
    _mem_sheet = ""
    if declares_memory:
        from construct import remembrancer
        with _phase(trace, "declare_memory"):
            _memory_tensions, _mem_receipts = remembrancer.commit_declared_memory(
                world, provider, player_input, arc.protagonist, arc, turn)
        trace.resolver = (trace.resolver or []) + _mem_receipts
        trace.cohort_calls.append("extract_memory_claims:cheap")
    if _memory_gate:
        try:
            from construct import remembrancer
            _mem_sheet = remembrancer.build_sheet(world, arc.protagonist, arc,
                                                  horizon=_h)
        except Exception as exc:  # noqa: BLE001 — a sheet miss just skips the call
            trace.dropped_cohorts.append(f"memory_sheet ({exc})")
            _memory_gate = False

    # TURN-LATENCY Lever 4: the speak-intent half of each present NPC's folded
    # npc_turn call, stashed here and consumed at the briefing-assembly point.
    npc_turn_results: dict = {}
    if npcs:
        # Engine reads (sheets) stay on the main thread (fast, local); the slow
        # npc_turn MODEL calls run CONCURRENTLY (decisions against the same
        # entry scene). Commits stay SERIAL so canon order is preserved.
        # SEMANTICS (Cx 022, documented-not-reverted): parallelizing the DECISIONS
        # means each NPC decides against the SAME entry scene — they act
        # SIMULTANEOUSLY within the turn, not in a serial reaction chain (NPC B no
        # longer sees NPC A's commit before deciding). For a single beat this is the
        # intended reading (all present NPCs act in the same moment) and the latency
        # win is large; the COMMITS are still serialized so canon order is
        # deterministic. If serial reaction is ever needed, drop _parallel here.
        # Horizon-bind the character-sheet read (Cx 259 fresh-hunt): this sheet feeds
        # npc_turn, whose accepted action is ingested to canon before beat_pass + terminal —
        # so a future-stamped knows:<npc> row must NOT drive NPC behavior at the play horizon.
        sheets = {npc: json.dumps(p.snapshot(npc, frame=f"knows:{npc}",
                                             lens="character_sheet", as_of=_h))[:4000]
                  for npc in npcs}
        scene_json = json.dumps(canon_snap)[:4000]
        # THE CONVERSATION SO FAR (founder 2026-07-01, "dialogue and facts repeating"): the NPC
        # decision was BLIND to recent dialogue — Reed pressed for the grinder's name a minute
        # after Maud gave it. Hand each NPC the last exchanges so intents ADVANCE, not re-tread.
        _npc_recent = ""
        try:
            _rtr = live_reads.state(_TRANSCRIPT, "recent", frame=SESSION)
            _rjs = json.loads(_rtr) if _rtr else []
            _npc_recent = "\n\n".join(
                f"PLAYER: {e.get('player', '')}\nSCENE: {e.get('prose', '')}"
                for e in _rjs[-2:])[:3000]
        except Exception:
            _npc_recent = ""
        # TURN-LATENCY Lever 4: ONE folded npc_turn call per present NPC (was two —
        # npc_world_action here + npc_intent later). The world-action half commits
        # EARLY (below, unchanged); the speak-intent half is stashed in
        # `npc_turn_results` and consumed at the briefing-assembly point downstream.
        # COMPANION TEXTURE (#85): a standing companion decides their beat knowing they are
        # WITH the player — they react/interject unprompted instead of waiting to be addressed.
        def _is_companion(n: str) -> bool:
            try:
                return live_reads.state(n, "accompanying") == arc.protagonist
            except Exception:  # noqa: BLE001
                return False
        _thunks = [
            (lambda n=npc: cohorts.npc_turn(provider, n, sheets[n],
                                            scene_json, arc.protagonist,
                                            recent=_npc_recent,
                                            companion=_is_companion(n)))
            for npc in npcs]
        if _memory_gate:
            # #97 (Cx 434 constraint 6): memory_turn rides the SAME cheap batch — one
            # more concurrent call on gated turns, no extra serial phase.
            _thunks.append(lambda: cohorts.memory_turn(
                provider, arc.protagonist, _mem_sheet, scene_json, player_input,
                tensions="; ".join(_memory_tensions)))
        with _phase(trace, "npc_action"):
            decisions = _parallel(_thunks)
        if _memory_gate:
            _mem_dec = decisions.pop()
            if isinstance(_mem_dec, Exception):
                trace.dropped_cohorts.append(f"memory_turn ({_mem_dec})")
            else:
                memory_result = _mem_dec
                trace.cohort_calls.append("memory_turn:cheap")
        for npc, decision in zip(npcs, decisions):
            if isinstance(decision, Exception):
                trace.dropped_cohorts.append(f"npc_turn:{npc} ({decision})")
                continue
            trace.cohort_calls.append(f"npc_turn:{npc}:cheap")
            npc_turn_results[npc] = decision  # carry the speak-intent half forward
            if decision["acts"] and decision["action"]:
                # ENTITY AUTHORITY (Cx 304): resolve the NPC's narrated act before it touches canon —
                # bind to present entities, bind "you" to the protagonist, drop voice/phantom rows.
                _ncands = {e for (e, _a) in canon_table if isinstance(e, str) and ":" in e}
                if scene:
                    _ncands.add(scene)
                _ncands.add(npc)

                def _npc_name(e: str, _ct=canon_table) -> str:
                    v = _ct.get((e, "name"))
                    if not isinstance(v, str):
                        try:
                            v = live_reads.state(e, "name")
                        except Exception:
                            v = None
                    return v if isinstance(v, str) else ""
                _nraw = p.extract(decision["action"], scene=scene, extract="lean",
                                  pov=npc)  # read-only; the NPC's own "I" (PB 4c)
                _nres, _nrec = resolve_rows(_nraw, scene=_ncands, protagonist=arc.protagonist,
                                            name_of=_npc_name, allow_mint=True)
                trace.resolver = (trace.resolver or []) + _nrec
                p.ingest_structured(_nres, classify="batch")
                canon_snap = _snap_or_empty(p, snap_scope, as_of=_h)  # refresh: canon moved
                canon_table = _table(canon_snap)
    elif _memory_gate:
        # #97: an empty room still has a mind — the gated memory call runs alone.
        with _phase(trace, "memory_turn"):
            try:
                memory_result = cohorts.memory_turn(
                    provider, arc.protagonist, _mem_sheet,
                    json.dumps(canon_snap)[:2000], player_input,
                    tensions="; ".join(_memory_tensions))
                trace.cohort_calls.append("memory_turn:cheap")
            except Exception as exc:  # noqa: BLE001 — interiority never sinks a turn
                trace.dropped_cohorts.append(f"memory_turn ({exc})")

    # ---- #93 VOCATIVE TITLE RESOLUTION (Cx 404 C-scope) --------------------
    # 'Chief!' resolves to the CANON title-holder — address-syntax-gated (never
    # 'my chief concern'), unique-holder-only. Present holder → the address binds to
    # them; ABSENT holder → the last-speaker convention and the sole-present-NPC
    # delivery fallback are both suppressed (never re-route an absent person's floor),
    # and the narrator renders an honest not-here beat. Deterministic; zero model calls.
    _voc_holder, _voc_absent, _voc_name = "", False, ""
    if kind == "action":
        _vtok = _vocative_token(player_input)
        if _vtok:
            _vh, _vcount = _title_holder(canon_table, _vtok, arc.protagonist)
            if _vh:
                _voc_name = str(canon_table.get((_vh, "name")) or
                                _vh.split(":", 1)[-1].replace("_", " ").title())
                if _vh in npcs:
                    _voc_holder = _vh
                    trace.vocative = f"{_vtok}->{_vh} (present)"
                else:
                    _voc_absent = True
                    trace.vocative = f"{_vtok}->{_vh} (ABSENT)"

    # ---- INTERVIEW DELIVERY (STORY-SHAPES §8) ----------------------------
    # Questioning a present cast member surfaces its authorized clues into the player
    # frame — the moment that advances pillar coverage in real play. Earned + bounded:
    # only when the player ENGAGES that NPC this turn (names them, or they're the only one
    # present), at most one NEW clue per NPC, gated by reveal_condition (pressure inferred
    # from the action; trust/object_seen deferred to v2). Written BEFORE beat_pass so a
    # gated beat/pillar can fire the same turn. Fail-open per clue.
    learned: list = []
    if cast and kind == "action" and npcs:
        from construct.cast import learn_clue_items, revealable_clues
        low = player_input.lower()
        pressing = _is_pressing(low, needs_test=needs_test)
        # #93: an address to an ABSENT title-holder must not fall through to the sole
        # present NPC — 'Chief!' with the chief away never delivers Reed's clue.
        only_one = len(npcs) == 1 and not _voc_absent
        # Topic-aware selection (BEAT-DELIVERY half 2, Cx 125): the clue ids the classifier
        # judged the player's question to be PURSUING (mapped back from opaque ask_* ids). The
        # deterministic reveal gate below stays authoritative — `asks_targets` only PICKS among
        # already-eligible+fresh clues; empty/irrelevant → today's authored-order behavior.
        _target_clue_ids = {getattr(_ask_by_oid[o], "clue_id", None)
                            for o in asks_targets if o in _ask_by_oid}
        for npc in npcs:
            node = cast.get(npc)
            _name = str(canon_table.get((npc, "name")) or "")
            _role = getattr(node, "surface_role", "") if node else ""
            if node is None or not (only_one or npc == _voc_holder
                                    or _names_entity(npc, low, name=_name,
                                                     role=_role)):
                continue
            # Eligible = gate-passing (none always; pressure/examine when the lever is present)
            # AND not already in the player frame. The gate is the rigid, algorithmic filter.
            eligible = [c for c in revealable_clues(node, pressure=pressing)
                        if not live_reads.assertion_in_frame(player_frame, *c.surface_fact)]
            if not eligible:
                continue
            # Prefer an eligible clue the classifier flagged as the question's target; else
            # fall back to the first by genuine-first rank (legacy). One fresh clue per NPC.
            clue = next((c for c in eligible if c.clue_id in _target_clue_ids), eligible[0])
            try:
                p.ingest_structured(learn_clue_items(clue), frame=player_frame,
                                    classify="batch")
                learned.append((npc, clue))
            except Exception as exc:  # one clue must not sink the turn
                trace.dropped_cohorts.append(f"learn_clue:{clue.clue_id} ({exc})")

    # ---- EXAMINE DELIVERY (EXAMINE-CHANNEL.md) -----------------------------------------
    # Inspecting a present clue-bearing OBJECT/SITE surfaces its evidentiary fact into the
    # player frame — the EXAMINE-channel analogue of interview delivery. Earned (close
    # inspection = scrutiny; a glance = examined-level), present-gated (the object must be
    # in/within the scene), one fresh clue per object per turn. A PLAIN object (not a cast
    # node) matches nothing → no delivery, so the narrator renders it as atmosphere (never
    # fabricated evidence). Object holders carry NO knows:<obj> frame — their fact rides the
    # player frame only here (Cx 073). Fail-open per clue.
    if cast and kind == "action" and _is_scrutiny(player_input.lower()):
        from construct.cast import learn_clue_items as _lci
        from construct.cast import revealable_clues as _rc
        low_ex = player_input.lower()
        _cast_items = cast.items() if hasattr(cast, "items") else [(n.node_id, n) for n in cast]
        for oid, onode in _cast_items:
            if oid.startswith("person:"):
                continue  # people are the ASK channel, handled above
            _orole = getattr(onode, "surface_role", "")
            if not _names_entity(oid, low_ex, role=_orole) or not _present(oid):
                continue
            for clue in _rc(onode, examined=True, scrutiny=True):
                e, a, v = clue.surface_fact
                if live_reads.assertion_in_frame(player_frame, e, a, v):
                    continue  # already learned — don't re-surface
                try:
                    p.ingest_structured(_lci(clue), frame=player_frame, classify="batch")
                    learned.append((oid, clue))
                except Exception as exc:  # one clue must not sink the turn
                    trace.dropped_cohorts.append(f"examine_clue:{clue.clue_id} ({exc})")
                break  # one fresh clue per object per turn

    trace.learned_clues = [c.clue_id for (_npc, c) in learned]

    # ---- DISCOVERY → REACHABILITY (INVESTIGATION-SHAPE.md §3c) -----------------------
    # When a delivered clue NAMES an off-scene cast member (their id appears in the clue's
    # fact), the player has learned where to find them: write their whereabouts into the
    # player frame (layer 2, entitlement) so the route is now player-known, and brief that
    # they may be sought (layer 3, pacing). The suspect's `in` + their place were authored as
    # canon at build (layer 1). No `route_open` flag is ever stored. Fail-open per write.
    discovered: list = []
    if cast and learned:
        cast_by_id = cast if isinstance(cast, dict) else {n.node_id: n for n in cast}
        for (_npc, clue) in learned:
            e, _a, v = clue.surface_fact
            for ref in (e, v):
                tgt = cast_by_id.get(ref)
                if (tgt is None or getattr(tgt, "presence", "") != "offscene"
                        or not getattr(tgt, "location", "")):
                    continue
                if live_reads.assertion_in_frame(player_frame, ref, "whereabouts", tgt.location):
                    continue  # already discovered — don't re-surface
                try:
                    p.ingest_structured([{"entity": ref, "attribute": "whereabouts",
                                          "value": tgt.location, "value_type": "entity"}],
                                        frame=player_frame, classify="batch")
                    discovered.append((ref, tgt.location))
                except Exception as exc:  # discovery must not sink the turn
                    trace.dropped_cohorts.append(f"discover:{ref} ({exc})")
    trace.discovered = [ref for (ref, _loc) in discovered]

    # ---- MAKE-IT-REAL: a PURSUED off-script thread becomes THE path (NARRATION-DISCIPLINE.md) -
    # When the player pursued an investigative thread that delivered NO authored clue, and an
    # unfilled required cause remains, judge (cheap) whether the pursuit can HONESTLY serve that
    # cause. If so, REROUTE: write the cause's ALREADY-AUTHORED genuine clue through the same
    # learn-clue doorway — the narrator frames it as discovered via the player's OWN detail, so
    # the case solves by THEIR path, never railroaded back to the pre-written clue. Route-flex,
    # NEVER answer-flex: the hidden answer is never minted here (the host derives the fact from
    # the authored pillar; the cohort only ROUTES). Budgeted; fail-open. SKIPPED when the player
    # is engaging an authored holder (that is a reveal-condition gate, not an un-authored thread)
    # or nothing was authored to cover. The destructive lane is NOT here — a ruinous decisive act
    # is the resolution deck + world-reaction path, never a make-it-real rescue (Cx 086).
    adapt_directives: list[str] = []
    # PURSUIT SIGNAL (Cx 087): the player CLOSELY investigated ONE specific detail — not a
    # generic look-around. `examines_target` (from classify) carries it; empty = no make-it-real
    # (avoids adapting every atmospheric mention into structure).
    if (cast and kind == "action" and not learned and generate and arc.pillars
            and examines_target):
        try:
            from construct.arc.adapt import (ADAPT_BUDGET, adaptations_used,
                                             apply_adaptation)
            from construct.cast import all_clues as _all_clues_ad
            tgt_low = examines_target.lower()
            _cast_tuple = tuple(cast.values()) if isinstance(cast, dict) else tuple(cast)
            # If the pursued target IS an authored cast entity/holder, this is the ASK/EXAMINE
            # channel (and possibly a not-yet-met reveal condition) — NOT an un-authored thread.
            # Skip make-it-real so we never short-circuit an authored gate.
            names_authored = any(
                _names_entity(n.node_id, tgt_low,
                              name=str(canon_table.get((n.node_id, "name")) or ""),
                              role=getattr(n, "surface_role", ""))
                for n in _cast_tuple)
            summ = coverage_summary(live_reads, arc)
            if (not names_authored and summ["unfilled"]
                    and adaptations_used(live_reads) < ADAPT_BUDGET):
                # unfilled pillar id -> its authored GENUINE clue fact (the reroute target —
                # writing it satisfies the pillar's genuine_via, so the cause actually covers).
                by_pillar: dict = {}
                for c in _all_clues_ad(_cast_tuple):
                    if (c.pillar_id in summ["unfilled"] and c.coverage_effect == "genuine"
                            and not c.is_red_herring and c.pillar_id not in by_pillar):
                        by_pillar[c.pillar_id] = c.surface_fact
                labels = {pl.pillar_id: pl.label for pl in arc.pillars}
                offer = [(pid, labels.get(pid, pid)) for pid in summ["unfilled"]
                         if pid in by_pillar]
                if offer:
                    with _phase(trace, "adapt"):
                        # route on the PRECISE pursued detail (Cx 089 #2), not the full input
                        decision = cohorts.adapt_decision(
                            provider, examines_target, unfilled_pillars=offer, actor=actor)
                    trace.cohort_calls.append("adapt:cheap")
                    lane = (decision or {}).get("lane")
                    pid = (decision or {}).get("pillar_id") or ""
                    if lane == "genuine" and pid in by_pillar:
                        e, a, v = by_pillar[pid]
                        ar = apply_adaptation(
                            world, {"lane": "genuine", "pillar_id": pid, "fact": [e, a, v],
                                    "reason": (decision.get("reason") or "")},
                            protagonist=arc.protagonist, turn=turn, reads=live_reads)
                        if ar.get("applied"):
                            trace.adapted.append((ar["lane"], pid))
                            adapt_directives.append(
                                "\nMAKE IT REAL (the player's OWN line of inquiry pays off — "
                                "NARRATION-DISCIPLINE): their pursuit leads them, through their "
                                "own observation and reasoning RIGHT NOW, to a NEW realization — "
                                f"that {_human_entity(a)} of {_human_entity(e)} is "
                                f"{_human_entity(str(v))}. Render this as the detail they chose "
                                "yielding THIS realization FRESHLY, this turn ('the ring tells you "
                                "X', 'now you see that…') — NOT a witness reciting it, NEVER a "
                                "redirect to another object/person. CRUCIAL: do NOT lean on facts "
                                "the player has not actually established — never write 'as you "
                                "already knew' / 'the timeline you already fixed' for anything not "
                                "yet learned; the realization arises from THIS observation alone. "
                                f"({(decision.get('reason') or '').strip()})")
        except Exception as exc:  # make-it-real must never sink a turn
            trace.dropped_cohorts.append(f"adapt ({exc})")

    # CHARACTER-GROUNDING P4 — the grounding runway: the FIRST play turn is the player settling
    # into who and where they are (the Picard 'step into your ready room' beat). Hold the
    # call-to-action / inciting incident for this one turn — suppress case-pressure (weave + nudge)
    # and brief the narrator to keep it grounded — so the story lands a beat later, not on turn 1.
    _grounding_runway = turn <= 1

    # ---- STORY GOVERNANCE: weave a card, or serve the live path (CARD-WEAVING.md) -------
    # Supersedes the passive cast-threads nudge (Cx 039 #5). When there are un-played cards
    # (cast clues carrying a hook) or floor debt, ask weave_pick whether to let_run /
    # pepper_hook / deliver_card, then weave the chosen card at its seam. A card is
    # 'delivered' once its fact is in the player frame (interview delivery did it);
    # 'hook_proposed' persists in session:main so the proposal floor accrues across turns.
    # The HOOK is never the fact (the safety seam) — peppering it informs choice only.
    # Fail-open: governance must never sink a turn.
    weave_directive = None
    if cast:
        from construct.cast import all_clues as _all_clues
        from construct.cast import floor_clues as _floor_clues
        try:
            nodes = tuple(cast.values())
            clues = [c for c in _all_clues(nodes) if c.hook_text]
            delivered = {c.clue_id for c in clues
                         if live_reads.assertion_in_frame(player_frame, *c.surface_fact)}
            proposed = set(delivered)
            for c in clues:
                if live_reads.state(f"card:{c.clue_id}", "weave_state",
                                    frame=SESSION) == "hook_proposed":
                    proposed.add(c.clue_id)
            # THE LIDDELL RECITAL (eval/07, craft pass): an already-PROPOSED hook must leave
            # the candidate deck — weave_pick kept re-picking the same card and the narrator
            # recited its hook_text verbatim turn after turn. Genre proposes ONCE (the floor
            # is satisfied when the hook is on the table); the player disposes. SAY IT ONCE.
            unplayed = [c for c in clues if c.clue_id not in proposed]
            req_ids = [pl.pillar_id for pl in arc.pillars if pl.required]
            debt = [c for c in _floor_clues(nodes, req_ids) if c.clue_id not in proposed]
            trace.floor_remaining = [c.clue_id for c in debt]
            if (unplayed or debt) and not _grounding_runway:
                present = ", ".join(str(canon_table.get((n, "name")) or _human_entity(n))
                                    for n in npcs) or "(no one in particular)"
                scene_desc = (f"Place: {_human_entity(scene) if scene else 'here'}. Present: "
                              f"{present}. The player just: {player_input}")
                # Momentum CONTEXT for the storytelling judgment (not a mechanical gate —
                # "appeal to good storytelling at a distance"): tell weave_pick whether the
                # moment is urgent, flowing, freshly-woven (let it breathe), or a calm one to
                # leave alone. The judgment paces itself from this; no hard cooldown.
                _last_weave = live_reads.state("weave:pacing", "last_turn", frame=SESSION)
                _wove_recently = isinstance(_last_weave, int) and (turn - _last_weave) <= 2
                if trace.clocks_fired:
                    momentum = "URGENT — a clock/pressure is live this turn; a beat is welcome"
                elif learned:
                    momentum = "flowing — the player just turned something up; likely let it ride"
                elif _wove_recently:
                    momentum = ("a thread was woven a turn or two ago — let this scene BREATHE; "
                                "weave again only if it has genuinely gone slack")
                else:
                    momentum = ("a calm, unhurried moment — serve the player's path; weave only "
                                "if the scene has truly gone slack")
                wv = cohorts.weave_pick(
                    provider, scene_desc,
                    [f"{c.clue_id} :: {c.hook_text}" for c in unplayed],
                    [f"{c.clue_id} :: {c.hook_text}" for c in debt],
                    momentum, arc.protagonist)
                trace.cohort_calls.append("weave_pick:cheap")
                dec = wv.get("decision", "let_run")
                card_id = wv.get("card_id", "")
                by_id = {c.clue_id: c for c in unplayed}
                if card_id not in by_id:  # a stray model id can't drive state (Cx 041 nit)
                    card_id = ""
                # `deliver_card` is only safe when the fact is ALREADY earned (in the player
                # frame). Un-played cards aren't earned by definition, so demote to pepper_hook
                # (Cx 041); earned cards are carried by the LEARNED THIS TURN block, not here.
                if dec == "deliver_card":
                    dec = "pepper_hook"
                trace.weave_decision, trace.weave_card = dec, card_id
                chosen = by_id.get(card_id)
                if dec == "pepper_hook" and chosen:
                    # Build the woven directive from ONLY the AUTHORED, non-spoiling
                    # `hook_text` — NO free model prose at all (not the model's `directive`,
                    # not its `seam_hint`), so a deliver-shaped response can't smuggle the
                    # underlying fact into the narrator prompt (Cx 043/045). The narrator
                    # finds the seam itself from the scene it already has in the briefing.
                    weave_directive = (
                        f"\nWEAVE THIS IN (woven naturally into the current scene): "
                        f"{chosen.hook_text}\nSurface this as a HOOK — why the thread is worth "
                        f"pursuing — woven into what is happening now; do NOT state the "
                        f"underlying fact, and never interrupt a good moment to force it.")
                    p.ingest_structured(
                        [{"entity": f"card:{card_id}", "attribute": "weave_state",
                          "value": "hook_proposed"},
                         {"entity": "weave:pacing", "attribute": "last_turn", "value": turn}],
                        frame=SESSION, classify="batch")
        except Exception as exc:  # governance must never sink the turn
            trace.dropped_cohorts.append(f"weave_pick ({exc})")

    player_snap = _snap_or_empty(p, snap_scope, frame=player_frame, as_of=_h)
    # EVENT-OCCURS-FIRING (Cx 115): resolve the action outcome NOW (before beat_pass) so an authored
    # `event_occurs` act-beat can fire on a SUCCESSFUL act and beat_pass achieves it THIS turn. The
    # tier is drawn ONCE here (deterministic deck) and REUSED by the narrator briefing (no 2nd draw).
    _resolved_tier = ""
    if kind == "action":
        if needs_test:
            try:
                _resolved_tier = resolution.draw_tier(live_reads, p)
                trace.adjudication = f"test:{_resolved_tier}"
            except Exception as exc:  # never sink a turn on a resolution hiccup
                logger.warning("resolution draw failed: %s", exc)
                trace.dropped_cohorts.append(f"resolution ({exc})")
        else:
            _resolved_tier = "assured"
        # fire authored act-beats only on a SUCCESS tier (never a failure — Cx 115 #1). Skip
        # TERMINAL side arcs (Cx 117): a dead side arc's pending Occurred beats offer no candidates.
        if _resolved_tier in ("assured", "success_cost", "complete_success"):
            _live_arcs = [arc] + [sa for sa in side_arcs
                                  if stored_lifecycle(live_reads, sa) not in LIFECYCLE_TERMINALS]
            _fire_event_occurs(world, p, live_reads, _live_arcs, provider,
                               player_input, _resolved_tier, turn, trace, arc.protagonist)
        elif (_resolved_tier in ("failure_opportunity", "terrible_failure")
              and result_events and result_events.get("loss")
              and (commits or current_phase(live_reads, arc)
                   in (Phase.CRISIS, Phase.CLIMAX, Phase.FALLING))):
            # The LOSS half of a literal-result axis (Contest, letters 131/132 + Cx 132 #2): a
            # FAILURE at the active RESULT MOMENT IS the loss — mint the declared loss-kind
            # result-event. Gated to the result moment (a conclusory commit, OR the arc in its
            # late CRISIS/CLIMAX/FALLING phase — NOT climax_ready, which would deadlock since the
            # loss-beat can't both BE a climax beat and require climax already-achieved) so an
            # early failed action can't canonize the loss; RESTRICTED to the declared loss-kinds
            # (`only_kinds`) so ordinary beats keep the success-only rule. Main arc only (the
            # literal result is the protagonist's). The gate's exact shape is validated against a
            # real Contest arc in the #33 pass; dormant until an arc declares result_events.
            _fire_event_occurs(world, p, live_reads, [arc], provider,
                               player_input, _resolved_tier, turn, trace, arc.protagonist,
                               only_kinds=set(result_events.get("loss") or ()))
    # ---- #95 DEATH GATE (DEATH-TESTAMENT.md, Cx 422) -----------------------------------
    # Death is an EFFECT, never a draw or a whim: staged mortal peril (the player SAW the
    # stakes and persisted) + a real drawn test + the deck's terrible_failure + the
    # world's death_policy saying death IS the end here. First mortal-risk turn STAGES
    # (stakes unmistakable, the move lands short of death); leaving the peril or a
    # non-risk turn clears the marker — peril never stalks the player across scenes.
    died = False
    _death_staged = False
    _peril_scene = ""
    try:
        _peril_scene = str(live_reads.state("session:peril", "scene",
                                            frame=SESSION) or "").strip()
    except Exception:  # noqa: BLE001 — the marker read is enrichment, never a gate
        _peril_scene = ""
    _peril_standing = bool(_peril_scene) and _peril_scene == str(scene or "")
    if kind == "action":
        died = (death_policy == "mortal" and mortal_risk and _peril_standing
                and needs_test and _resolved_tier == "terrible_failure")
        try:
            if (death_policy == "mortal" and mortal_risk
                    and not _peril_standing and not died):
                # STAGING turn — MORTAL chapters only (Cx 426: a shielded/premise world
                # must never gain a lethal-peril marker or be told death is on the
                # table; the genre decides). The marker persists scene + cause; the
                # render directive below makes the stakes unmistakable, short of death.
                p.ingest_structured([
                    {"entity": "session:peril", "attribute": "scene",
                     "value": str(scene or ""), "valid_from": turn_time(turn)},
                    {"entity": "session:peril", "attribute": "cause",
                     "value": (uncertain_of or player_input)[:200],
                     "valid_from": turn_time(turn)},
                ], frame=SESSION, classify="batch")
                _death_staged = True
                trace.peril = "staged"
            elif _peril_scene and (not mortal_risk
                                   or death_policy != "mortal"
                                   or str(scene or "") != _peril_scene):
                # first non-risk turn / scene change / a chapter whose policy no longer
                # puts death on the table: the peril releases its grip
                p.ingest_structured([
                    {"entity": "session:peril", "attribute": "scene", "value": "",
                     "valid_from": turn_time(turn)},
                ], frame=SESSION, classify="batch")
                trace.peril = "cleared"
            elif _peril_standing and mortal_risk:
                trace.peril = "standing"
        except Exception as exc:  # noqa: BLE001 — marker writes never sink a turn
            trace.dropped_cohorts.append(f"peril_marker ({exc})")
    if died:
        trace.peril = "standing"
        logger.info("player death: staged peril + mortal risk + terrible_failure "
                    "(policy=mortal) at %s", scene)

    # WORLD-CHANGING AGENCY (flag-gated, default OFF — WORLD-CHANGING-AGENCY.md): an
    # earned, uncertain act may RESHAPE canon. Commit PRE-beat_pass (so the arc reacts
    # THIS turn) through the host doorway, then patch the local materialization the
    # post-render gate reads (canon_table is a stale snapshot — Cx 204/205 #1) and
    # license the exact sanctioned rows so the narrator may restate them past the
    # protected-key gate (Cx 204/205 #2). Inert when off: apply_reshape returns None →
    # no patch, no license, no briefing change. Private witness frames are NOT licensed.
    _reshape_license: set[tuple[str, str, str]] = set()
    # The reshape judge (a model call) runs ONLY when classify flagged a genuine miraculous
    # attempt — so an ordinary uncertain action (pick a lock, search) never pays for it. This
    # cheap pre-filter is what lets world-changing be ON by default without taxing every turn.
    if reshape_attempt and needs_test and _resolved_tier not in ("", "assured"):
        _snap = set(snap_scope)
        _scene_facts = "; ".join(
            f"{e.split(':', 1)[-1]}.{a}={v}"
            for (e, a), v in list(canon_table.items()) if e in _snap)[:1200]
        _rr = apply_reshape(world, provider, action=player_input,
                            scene=(scene or arc.protagonist),
                            canon=f"{uncertain_of}. {_scene_facts}".strip(),
                            tier=_resolved_tier, turn=turn, laws=_laws_full)
        if _rr is not None:
            trace.reshape = _rr.summary
            for _row in _rr.canon_rows:
                if _row["entity"] == _rr.event_id:
                    continue  # the reshape EVENT anchor, not a player-visible world fact
                canon_table[(_row["entity"], _row["attribute"])] = _row["value"]
                _reshape_license.add((_row["entity"], _row["attribute"], _row["value"]))
            # Carry the visible reshape entities so the Session can keep them in NEXT-turn
            # scope (Cx 221): a revived NPC the replacement arc doesn't reference must not
            # drop out of scene awareness after the re-plan.
            trace.reshape_entities = sorted({r["entity"] for r in _rr.canon_rows
                                             if r["entity"] != _rr.event_id})
            logger.info("world reshape committed: %s (%d visible rows licensed)",
                        _rr.event_id, len(_reshape_license))
            # The reshape may have made the destination stale → re-aim the MAIN arc
            # (first cut: re-evaluate on every LANDED reshape; the cohort judges staleness
            # and can keep the through-line). Same-turn swap so beat_pass + briefing + gate +
            # outcome all run from the new arc (Cx 210/212). Flag-gated via apply_reshape above.
            if _rr.landed:
                from construct.arc import io as arc_io
                from construct.game import author_replan
                _ro = author_replan(world, arc, provider, reshape_summary=_rr.summary, turn=turn)
                if _ro.reason == "replanned" and _ro.arc is not None:
                    arc_io.replan_main_arc(world, _ro.arc, turn=turn)
                    arc = _ro.arc                       # swap the LIVE arc — all downstream uses it
                    trace.replanned = arc.arc_id
                    # Refresh scope + snapshots from the NEW arc. CRUCIAL (Cx 215 #2): also
                    # include the VISIBLE committed reshape entities (landed state/restage/
                    # consequence rows, not the event anchor) — a coherent replacement arc may
                    # not reference a restaged entity (e.g. a revived NPC) via arc_entities, and
                    # a fresh PB read only carries rows whose entities are in the requested scope.
                    _reshaped_ents = [r["entity"] for r in _rr.canon_rows
                                      if r["entity"] != _rr.event_id and live_reads.has_entity(r["entity"])]
                    _new_scope = sorted(set(e for e in arc_entities(arc) if live_reads.has_entity(e))
                                        | set(_reshaped_ents))
                    snap_scope = _new_scope + ([scene] if scene else []) + scene_features
                    canon_snap = _snap_or_empty(p, snap_scope, as_of=_h)
                    canon_table = _table(canon_snap)
                    player_snap = _snap_or_empty(p, snap_scope, frame=player_frame, as_of=_h)
                    logger.info("arc re-planned mid-story -> %s", arc.arc_id)
                elif _ro.reason == "no_replacement":
                    # The old destination is gone and nothing coherent replaces it → EXPLICIT
                    # old-main-arc fallout (never a silent stale arc, never a broken install).
                    try:
                        _fo = emit_fallout(world, arc, "incompletable", turn)
                        trace.arc_fallout.append(arc.arc_id)
                        trace.reshape = (trace.reshape + " " + _fo.directive).strip()
                    except Exception:
                        logger.exception("reshape no_replacement fallout failed")
                # provider_error → keep the current arc + the committed reshape (fail-open)
    achieved, closed, revealed = beat_pass(world, arc, live_reads, turn)
    trace.beats_achieved, trace.beats_closed = achieved, closed
    trace.reveals = revealed
    # Side-arc beats tick too (their statuses drive side-arc lifecycle below).
    # Folded into the trace lists for the debug surface; main-arc `achieved`
    # alone drives pacing/pins (the player is the main protagonist).
    for sa in side_arcs:
        if stored_lifecycle(live_reads, sa) in LIFECYCLE_TERMINALS:
            continue
        sa_ach, sa_closed, sa_rev = beat_pass(world, sa, live_reads, turn)
        trace.beats_achieved += sa_ach
        trace.beats_closed += sa_closed
        trace.reveals += sa_rev

    # ---- PINNED AWARENESS (PINNED-AWARENESS spec; reviews 060/062/063) ---
    # One awareness coordinate for the WHOLE assembly (Kernos 060 #2 / Cx #2):
    # region ancestry (the turn's current chain), the scene's present entities,
    # and the temporal window all resolve as-of the same `now`. Candidates come
    # from the arc's pin set (the host index, never a log scan).
    awareness_as_of = turn_time(turn)
    pin_subjects: set[tuple] = set()
    active_pins: list = []
    if arc.pins:
        present_entities = {e for (e, a), v in canon_table.items()
                            if a == "in" and v == scene}
        present_entities.add(arc.protagonist)
        try:  # `spent` pins recede permanently (Kernos 060 #6); none normally
            spent = {a for ev in live_reads.events(kind="pin_spent", frame=SESSION)
                     for a in ev.agents}
        except Exception:
            spent = set()
        # Arc progress drives foreshadowing escalation: fraction of REQUIRED
        # beats achieved → an `escalates` pin's clue gets louder as the reveal
        # nears (v2 clue-trail).
        required = [b for b in arc.beats if b.weight is Weight.REQUIRED]
        done = sum(1 for b in required
                   if live_reads.assertion_in_frame("plot:main", b.beat_id, "status", "achieved"))
        progress = (done / len(required)) if required else 0.0
        active_pins = resolve_active_pins(
            arc.pins, ancestry=set(chain), present_entities=present_entities,
            as_of=awareness_as_of, spent=spent, progress=progress)
        pin_subjects = {ap.subject_key for ap in active_pins}
        trace.pins = [(ap.pin.pin_id, ap.pin.scope_kind, round(ap.salience, 3))
                      for ap in active_pins]

    # ---- ASSEMBLY FAN-OUT (reuses the tick's materializations) -----------
    # The protagonist's facts are recast as "you" and segregated — the
    # narrator must never see the player listed as a scene entity
    # (letter 025: the briefing itself was inviting third-person Marn).
    # A pinned subject is suppressed from the plain scene list and surfaced
    # ONLY in the PINS block, with its directive (dedupe, Kernos 060 #5).
    # Render grounding BY NAME, never raw ids — cleaner for the narrator and it
    # closes an id-leak (the narrator must speak the world's names, not 'person:x').
    # Names are resolved from the player frame (so still frame-scoped, no leak); an
    # entity with no established name falls back to a humanized id.
    _NAME_ATTRS = ("name", "alias", "title")
    names = {}
    for f in player_snap.get("facts", []):
        if f["attribute"] in _NAME_ATTRS and f["entity"] not in names:
            names[f["entity"]] = str(f["value"])

    def _disp(x: Any) -> str:
        s = str(x)
        if s in names:
            return names[s]
        if ":" in s and s.split(":", 1)[0] in ("person", "place", "obj", "fact", "event"):
            local = s.split(":", 1)[-1].replace("_", " ")
            return local.title() if s.startswith("person:") else local  # person slug = a proper name
        return s

    # LOCATION FILTER (founder live: "the tape followed us everywhere"): scene facts are the
    # player-frame snapshot over the WHOLE arc scope, so a learned-but-ELSEWHERE entity (a clue
    # object left at another place) would surface in EVERY scene's briefing → the narrator renders
    # it here even though it isn't. Restrict `scene_lines` to what is actually present in/near THIS
    # scene: the place itself, its features, the protagonist, things held, and colocated
    # people/objects (`_present`). The player still KNOWS the rest (player frame / irony threads) —
    # it just isn't narrated as physically HERE. Abstract/unplaced facts (fact:*) ride the threads.
    _here = {e for e in {f["entity"] for f in player_snap.get("facts", [])}
             if e == scene or e in scene_features or e == arc.protagonist or _present(e)}
    scene_lines, you_lines = [], []
    for f in player_snap.get("facts", []):
        if f["attribute"] in _NAME_ATTRS:
            continue  # names feed the resolver above, not shown as bare facts
        if f["entity"] == arc.protagonist:
            you_lines.append(f"you · {f['attribute']} · {_disp(f['value'])}")
        elif (f["entity"], f["attribute"]) in pin_subjects:
            continue
        elif f["entity"] not in _here:
            continue  # established ELSEWHERE — not physically in this scene (don't render it here)
        else:
            scene_lines.append(f"{_disp(f['entity'])} · {f['attribute']} · {_disp(f['value'])}")
    trace.briefing_frames = [player_frame]

    # Irony delta via the designed sixth read (frame_diff) — restored
    # after PB's indexed read path landed (letter 024; measured 0.68s on
    # the live world vs >250s pre-fix).
    player_table = _table(player_snap)
    diff = p.frame_diff("canon", player_frame, sorted(set(snap_scope)), as_of=_h)  # Cx 255
    # DISCOVERY GATING (#84, Cx 395/396 constraint 1): off-screen world-tick consequences
    # must not become narrator fuel before the player earns them. A `event:tick_*` row rides
    # the irony delta ONLY when its agent is physically HERE; an absent person's `in` row is
    # never thread text (presence truth — the narrator doesn't get omniscient whereabouts).
    _tick_agents = {str(f["entity"]): str(f["value"]) for f in diff
                    if str(f["entity"]).startswith("event:tick_")
                    and f["attribute"] == "agent"}

    def _diff_surfaces(f: dict) -> bool:
        e = str(f["entity"])
        if e.startswith("event:tick_"):
            return _tick_agents.get(e) in _here
        if e.startswith("person:") and f["attribute"] == "in" and e not in _here:
            return False
        return True

    threads = [f"{f['entity']} · {f['attribute']} · {f['value']}"
               for f in diff if _diff_surfaces(f)][:12]
    trace.irony_delta_size = len(diff)

    # Conclusion detection (endless mode). Bounded worlds settle into
    # aftermath once the arc reaches its destination — the navigator
    # stops pushing toward an end already reached. Endless worlds note
    # the milestone but keep their pressure/clocks running indefinitely.
    # TERMINAL OWNER (Cx 141): for COMMITMENT-owned shapes (deduction/contest/…), world_condition
    # being met is READINESS for the reckoning, NOT the conclusion — the player's conclusory
    # commitment owns the curtain (the audit-office falter: seizing evidence ended the story before
    # the accusation could land). Such an arc concludes only on (a) refusal, (b) a landed commitment
    # [below], or (c) the post-climax window expiring (the reckoning never came). WORLD-EVENT-owned
    # shapes (endurance/farce) keep the direct world_condition terminal — unchanged.
    from construct.arc.conditions import Truth as _Truth
    from construct.arc.conditions import evaluate as _evaluate
    _commitment_owned = terminal_owner == "commitment"
    # DIEGETIC-CLOCK CONCLUSION (founder ruling 2026-06-25; Cx 173): turns are FREE — NO turn-count
    # ever forces a conclusion. A commitment-owned arc with no authored deadline stays READY forever;
    # it concludes ONLY on the player's commitment [below] or a crossed AUTHORED `failure_when`
    # (a fiction deadline = Quantity over time:elapsed, or an authored loss event). `_reckoning_ready`
    # remains, but ONLY as the narrator nudge ("THE RECKONING IS AT HAND") — never a countdown.
    # Gated on win_loss too (story-agnostic scoping): the nudge steers toward a CONCLUSORY move,
    # which only exists when the story has a win/loss destination. An endless/sandbox story (idle
    # family dynamics, open-ended romance, slice-of-life) has no conclusion to steer toward, so it
    # never gets the nudge — it just plays on.
    _reckoning_ready = _commitment_owned and scenario_mode == "win_loss" and (
        climax_ready(live_reads, arc)
        or _evaluate(arc.shape.world_condition, live_reads) is _Truth.TRUE)
    _authored_failure = (arc.failure_when is not None
                         and _evaluate(arc.failure_when, live_reads) is _Truth.TRUE)
    concluded = arc_concluded(live_reads, arc)
    if _commitment_owned:
        # world_condition is READINESS, not a conclusion. The only forced close is an authored
        # failure (deadline/loss event); the commitment's own terminal is handled below.
        concluded = _authored_failure
    trace.concluded = concluded
    if concluded and not _conclusion_recorded(live_reads):
        p.ingest_structured([
            {"entity": f"event:conclusion_{turn}", "attribute": "kind",
             "value": "conclusion", "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # conclusion marker — bookkeeping

    # Win/loss termination (WIN-LOSS §10): STRICTLY in `win_loss` mode (founder
    # ruling) — endless/freeplay never terminate. On the first won/lost, write
    # the one-time SESSION receipt; this turn renders the flavored aftermath, and
    # the transport stops ticking thereafter (Session reads terminal_outcome).
    # Main-arc lifecycle (LIVING-WORLD-GENERATOR §3): won/lost via arc_outcome,
    # plus incompletable/cancelled. For the MAIN arc in win_loss, a non-won
    # terminal ends the story as a loss (the win is foreclosed) — mapped to the
    # one-time `arc_lost` receipt. The main arc never emits fallout (its ending
    # IS the story's ending — the epilogue handles it); only side arcs regenerate.
    # CONCLUSORY COMMITMENT (STORY-SHAPES.md win-model): the player's decisive climactic
    # move ENDS the story — when it's EARNED (climax-ready, never turn 1). Capture +
    # JUDGE it ONCE (host call, not per-turn) → a graded outcome (vindicated / partial /
    # wrong / pyrrhic). The grade is EPILOGUE FLAVOR, not a pass/fail gate: a WRONG
    # accusation still concludes the story (the wrong person goes down; the twist lands
    # at the curtain). `knows:player` stays the evidence store — the held answer never
    # had to enter it. In endless mode the commitment is recorded + reflected, not terminal.
    # EARNED gate: a commitment concludes once the player has genuinely PLAYED — either
    # the arc is climax-ready, OR enough turns have passed (the card model means the
    # engine never just hands the answer into the player frame, so we must NOT require
    # that; "earned" = they've had the chance to investigate, not "the engine told them").
    # A turn-1 accusation is too abrupt — it stays an ordinary action until then.
    earned = climax_ready(live_reads, arc) or turn >= _MIN_COMMIT_TURN
    commitment_grade = ""
    commitment_bounced = False
    commitment_clarified = ""
    if commits and earned and terminal_outcome(live_reads) is None:
        # THE CLARIFICATION GATE (#88A, founder + Cx 375): an UNDERSPECIFIED conclusory move
        # ("REED DID IT" alone in an alley) gets ONE in-fiction clarification beat instead of a
        # judgment — no commitment, no grade, no receipt. The session receipt makes the second
        # utterance judged-as-given. PUBLIC staging context only; fail-open (a gate miss →
        # judge as before). Runs at most ONCE PER EPISODE (Cx 380: the receipt is episode-scoped
        # by design — one clarification per story keeps the no-loop guarantee; narrow later if
        # long episodes want more).
        try:
            _asked = live_reads.state("session:clarification", "asked", frame=SESSION)
        except Exception:
            _asked = "miss"  # can't read the receipt → don't gate (fail-open)
        if not _asked:
            try:
                _here = str(canon_table.get((scene, "name")) or
                            (scene or "").split(":")[-1].replace("_", " "))
                _who = ", ".join(
                    str(canon_table.get((n, "name")) or n.split(":")[-1].replace("_", " "))
                    for n in npcs) if npcs else ""
                _gate = cohorts.commitment_stage_gate(
                    provider, player_input, commitment, _here, _who, judgment_type or "")
                trace.cohort_calls.append("stage_gate:cheap")
                if not _gate.get("specified", True):
                    commitment_clarified = (_gate.get("clarification") or "").strip() or (
                        "the move needs a concrete stage — to whom, where, how")
                    commits = False  # not judged this turn; the beat renders instead
                    p.ingest_structured([{
                        "entity": "session:clarification", "attribute": "asked",
                        "value": f"turn_{turn}", "valid_from": turn_time(turn)}],
                        frame=SESSION, classify="batch")
                    logger.info("commitment clarification beat (missing: %s)",
                                _gate.get("missing"))
            except Exception as exc:  # noqa: BLE001 — never block the commitment path
                logger.warning("stage gate skipped (%s)", exc)
    if commits and earned and terminal_outcome(live_reads) is None:
        # COMMITMENT-AS-EFFECT slice 1 (Cx 105): a voluntary conclusive commitment LANDS only when
        # the payoff is EARNED — for an arc with REQUIRED pillars, required coverage must be
        # `complete` (genuine OR false; false counts, so a hollow case can still land). An INCOMPLETE
        # attempt BOUNCES, non-terminal — BEFORE the judge and BEFORE any commitment rows: no judge
        # call, no claim/grade, no event:commitment, no terminal; the narrator nudges "not yet
        # proven" and play continues. Scoped to the VOLUNTARY-commitment path only — forced closes
        # (clocks/refusal/scoreboard/arc_concluded) are untouched. No required pillars (legacy/
        # optional-only) → keep the existing judge/terminate path (gate on `required`, not arc.pillars).
        _csum = coverage_summary(live_reads, arc)
        if _csum.get("required") and not _csum.get("complete"):
            commitment_bounced = True
            logger.info("commitment bounced (not yet proven): unfilled required pillars %s",
                        _csum.get("unfilled"))
    if commits and earned and not commitment_bounced and terminal_outcome(live_reads) is None:
        # COMMITMENT-AS-EFFECT slice 2 (Cx 105/107): for a PILLAR arc the grade IS the coverage
        # EFFECT — computed ALGORITHMICALLY from `conclusion_from_coverage` (cost_disposition-aware),
        # never an LLM judgment (the model did this rigid-criteria work and got it WRONG live). The
        # accusation follows the evidence the player actually gathered, so coverage already encodes
        # just-vs-hollow: `wrong_case` (a required cause covered by a FALSE clue — a red herring
        # believed → an unjust/mistaken conviction) → 'wrong'; the intended/sound effect →
        # 'vindicated'; otherwise 'partial'. fail_forward (comedy) is honored (a live blowup is
        # effect-sound, never wrong_case). LEGACY pillar-less arcs keep the LLM judge — extracting a
        # verdict from open language with no coverage to read is genuinely its job.
        if _csum.get("required"):
            _eff = _conclusion_effect(live_reads, arc, cost_disposition, result_events)
            if _eff and _eff.get("wrong_case"):
                commitment_grade = "wrong"
            elif _eff and _eff.get("effect_sound"):
                commitment_grade = "vindicated"
            else:
                commitment_grade = "partial"
        else:
            destination = _destination_facts(arc, live_reads)
            try:
                jv = cohorts.judge_commitment(provider, commitment, judgment_type, destination)
                commitment_grade = jv.get("grade", "") or "partial"
                trace.cohort_calls.append("judge_commitment:cheap")
            except Exception as exc:  # never sink the turn on the judge
                logger.warning("judge_commitment failed: %s", exc)
                commitment_grade = "partial"
                trace.dropped_cohorts.append(f"judge_commitment ({exc})")
        p.ingest_structured([
            {"entity": f"claim:{arc.protagonist}", "attribute": "committed",
             "value": commitment[:300]},
            {"entity": f"claim:{arc.protagonist}", "attribute": "grade",
             "value": commitment_grade},
        ], classify="batch")
        p.ingest_structured([
            {"entity": f"event:commitment_{turn}", "attribute": "kind",
             "value": "commitment", "valid_from": turn_time(turn)},
            {"entity": f"event:commitment_{turn}", "attribute": "grade",
             "value": commitment_grade, "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # commitment marker — bookkeeping
    trace.commitment = commitment if commits else ""
    trace.commitment_grade = commitment_grade
    trace.commitment_bounced = commitment_bounced
    trace.commitment_clarified = commitment_clarified

    main_life = arc_lifecycle(live_reads, arc)
    trace.lifecycle = main_life
    outcome = arc_outcome(live_reads, arc)
    if _commitment_owned:
        # For a commitment shape, `world_condition` is READINESS, not victory, so don't let
        # arc_outcome's won-first mask an authored deadline (Cx 173 #4): evaluate `failure_when`
        # DIRECTLY. Only an authored failure (a crossed fiction deadline / loss event) can close a
        # ready arc; turn-count refusal/post-climax expiry no longer terminate. The commitment
        # [below] owns the win.
        outcome = "lost" if _authored_failure else None
    if outcome is None and main_life in ("incompletable", "cancelled"):
        outcome = "lost"
    # The commitment IS the conclusion (convergence): it terminates regardless of the
    # world_condition. The grade maps to the binary terminal receipt (wrong → lost; all else →
    # won) while the EFFECT (conclusion_from_coverage) is what the player feels. For pillar arcs
    # the grade is now derived FROM that effect (slice 2), so receipt + epilogue can't contradict:
    # an unjust/hollow conviction → 'wrong' → lost → terminal → a wrong_case epilogue (the
    # conviction still concluded, on a hollow note); a sound case → 'vindicated' → won → triumph.
    if commitment_grade:
        # #88 S2 HARDENING (Cx 375-C, founder's won-after-wrong bug): when a player commitment
        # LANDED this turn, the GRADE decides — unconditionally. On non-commitment-owned arcs
        # arc_outcome() could already say "won" because the world_condition (the player's frame
        # KNOWING the answer, e.g. via interview delivery) was satisfied — but knowing the truth
        # is not accusing rightly. A wrong commitment is a loss no matter what the frame knows.
        outcome = "lost" if commitment_grade == "wrong" else "won"
    trace.outcome = outcome
    # #95 (Cx 422): death ends BOTH scenario modes (permanence — an endless world still
    # ends at the player's death) and owns terminal precedence over ordinary win/loss.
    terminal = died or (scenario_mode == "win_loss" and outcome is not None)
    trace.terminal = terminal
    if died:
        trace.terminal_kind = "died"
    # CONCLUSION AS EFFECT (STORY-SHAPES §0a): when the arc declares pillars, the conclusory
    # scene's CHARACTER is the narrated effect of pillar COVERAGE, not a win/lost verdict. The
    # won/lost receipt above stays as the "episode concluded, stop ticking" plumbing; this is what
    # the player feels. Uses the SAME `_conclusion_effect` the commitment grade derives from (slice
    # 2), so the receipt, the grade, and the epilogue can never disagree.
    conc = None
    if (terminal and not died) or (concluded and not endless):
        conc = _conclusion_effect(live_reads, arc, cost_disposition, result_events)
        if _commitment_owned and _authored_failure and not commitment_grade:
            # AUTHORED DEADLINE/FAILURE closed a ready arc with no commitment (Cx 173): the fiction's
            # clock ran out (or its loss event fired) before the player drew the curtain. Force a
            # quiet-failure close — NOT the positive coverage effect — so the rendered shape matches
            # the `lost` receipt. (Only fires when the story AUTHORED a deadline/failure; a
            # no-deadline arc never reaches here — it just stays ready.)
            conc = {"outcome": "quiet_failure", "sound": False, "effect_sound": False,
                    "wrong_case": False,
                    # Agnostic basis: an authored failure_when fired with no commitment — a missed
                    # deadline (King's dinner), a decisive loss event (the protectee killed), etc.
                    # The narrator's epilogue renders the SPECIFIC event from world-state; this is the
                    # neutral fallback so it fits any story's "IT", not just a time deadline.
                    "basis": "the story's decisive turn came and went unmet"}
        # GAUGE coloring (GAUGE §5): a WIN earned on the last of the reserve is a COSTLY
        # victory, not a clean triumph — the gauge supplies the number, the shape the meaning.
        if conc and outcome == "won" and conc.get("outcome") == "triumph" \
                and gauge_coloring(arc, world, as_of=_h) == "costly":
            conc = dict(conc, outcome="costly_victory",
                        basis=conc.get("basis", "") +
                        " — but it was won on the last of the reserve, at the edge of disaster")
        if conc:
            trace.conclusion_shape = conc["outcome"]
            trace.conclusion_basis = conc["basis"]
    if terminal and terminal_outcome(live_reads) is None:
        # THE SHAPE RECEIPT (#88 S2, founder ruling via Cx 375/376/377): the durable record of a
        # conclusion is its NARRATIVE SHAPE — graded effect + basis — not the binary. The binary
        # `kind=arc_won/arc_lost` row survives ONLY as ended-state plumbing for terminal_outcome's
        # gate; display and continuation authoring read the shape attrs ("you can win with a
        # great loss, or lose with an unexpected boon").
        if died:
            # #95: the DEATH receipt owns the terminal — no arc_won/arc_lost shape rows
            # (terminal_outcome keys on kind=player_death; the story is not a score).
            _rcpt = f"event:player_death_{turn}"
            p.ingest_structured([
                {"entity": _rcpt, "attribute": "kind", "value": "player_death",
                 "valid_from": turn_time(turn)},
                {"entity": _rcpt, "attribute": "cause",
                 "value": (uncertain_of or player_input)[:200],
                 "valid_from": turn_time(turn)},
                {"entity": _rcpt, "attribute": "agent", "value": arc.protagonist,
                 "value_type": "entity", "valid_from": turn_time(turn)},
            ], frame=SESSION, classify="batch")
            set_lifecycle(world, arc, "lost", turn)
        else:
            _rcpt = f"event:arc_outcome_{turn}"
            _shape_rows = [
                {"entity": _rcpt, "attribute": "kind",
                 "value": f"arc_{outcome}", "valid_from": turn_time(turn)},
            ]
            if commitment_grade:
                _shape_rows.append({"entity": _rcpt, "attribute": "grade",
                                    "value": commitment_grade, "valid_from": turn_time(turn)})
            if conc:
                _shape_rows += [
                    {"entity": _rcpt, "attribute": "outcome_shape",
                     "value": conc.get("outcome", ""), "valid_from": turn_time(turn)},
                    {"entity": _rcpt, "attribute": "basis",
                     "value": conc.get("basis", ""), "valid_from": turn_time(turn)},
                ]
            p.ingest_structured(_shape_rows, frame=SESSION, classify="batch")
            set_lifecycle(world, arc, main_life, turn)
        # COMMITMENT-AS-EFFECT slice 3 (Cx 105 #5): a HOLLOW/unjust main landing writes a CONCRETE
        # canon consequence — the fallout the next episode grows from — anchored via `caused_by` to
        # the conclusion event. NOT a derived label ('hollow'/'irony'), NOT side-arc emit_fallout.
        # Deduction worked example: the case convicted on a red herring → the REAL culprit was never
        # brought to justice → they walk free (a true world fact, the book-2 hook). The protagonist-
        # knowledge gap is STRUCTURAL: this is CANON (the world knows the culprit is at large);
        # knows:<protagonist> does NOT get it — the protagonist believes they convicted rightly,
        # unless/until it surfaces. Fail-open; never sinks the terminal turn.
        if conc and conc.get("wrong_case") and cast:
            _cast_items = cast.items() if isinstance(cast, dict) else [(n.node_id, n) for n in cast]
            _culprit = next((cid for cid, n in _cast_items if getattr(n, "is_culprit", False)), None)
            if _culprit:
                try:
                    p.ingest_structured([
                        {"entity": _culprit, "attribute": "brought_to_justice", "value": "false",
                         "caused_by": f"event:arc_outcome_{turn}", "valid_from": turn_time(turn)},
                    ])  # canon (default frame) — the real culprit walks free; generator/next-episode fuel
                    trace.main_fallout.append((_culprit, "brought_to_justice", "false"))
                    logger.info("hollow landing: %s at large (caused_by the botched case)", _culprit)
                except Exception as exc:  # fallout must never sink the terminal turn
                    trace.dropped_cohorts.append(f"main_fallout ({exc})")
        # S2 CONSEQUENCE FACTS (#96, Cx 414 constraint 2 — the founder's newspaper ruling):
        # every ending writes concrete canon consequence EVENTS from the DETERMINISTIC map,
        # caused_by the outcome receipt — the world's true record that the player's story
        # HAD an effect. Presentation (the continuation bridge's callback, weave, the
        # world-tick) selects and phrases them later; a session presentation-receipt at
        # surfacing keeps a strong callback deliberate, never spam. Fail-open.
        try:
            _ckey = ("died" if died else
                     ((conc.get("outcome") if conc else None) or commitment_grade
                      or outcome or "lost"))
            _detail, _repdir = _ENDING_CONSEQUENCES.get(
                _ckey, _ENDING_CONSEQUENCES["lost"])
            _wid, _rid = f"event:consequence_word_{turn}", f"event:consequence_rep_{turn}"
            p.ingest_structured([
                {"entity": _wid, "attribute": "kind", "value": "word_spreads",
                 "caused_by": _rcpt, "valid_from": turn_time(turn)},
                {"entity": _wid, "attribute": "detail", "value": _detail,
                 "valid_from": turn_time(turn)},
                {"entity": _wid, "attribute": "agent", "value": arc.protagonist,
                 "value_type": "entity", "valid_from": turn_time(turn)},
                # item-level caused_by lands on the assertion row, NOT the event entity
                # (Cx 420; the event_occurs precedent) — events().caused_by needs the
                # explicit event-entity causality row.
                {"entity": _wid, "attribute": "caused_by", "value": _rcpt,
                 "value_type": "entity", "valid_from": turn_time(turn)},
                {"entity": _rid, "attribute": "kind", "value": "reputation_changes",
                 "caused_by": _rcpt, "valid_from": turn_time(turn)},
                {"entity": _rid, "attribute": "agent", "value": arc.protagonist,
                 "value_type": "entity", "valid_from": turn_time(turn)},
                {"entity": _rid, "attribute": "direction", "value": _repdir,
                 "valid_from": turn_time(turn)},
                {"entity": _rid, "attribute": "caused_by", "value": _rcpt,
                 "value_type": "entity", "valid_from": turn_time(turn)},
            ])  # canon — true world consequences, never derived drama
            trace.consequences = [f"word_spreads:{_ckey}",
                                  f"reputation_changes:{_repdir}"]
            logger.info("ending consequences committed: %s", trace.consequences)
        except Exception as exc:  # consequences must never sink the terminal turn
            trace.dropped_cohorts.append(f"ending_consequences ({exc})")

    # Side-arc lifecycle: classify each, and on the FIRST transition to a
    # terminal (guarded by the persisted lifecycle row so re-entry never re-fires)
    # acknowledge it diegetically and — for a non-won terminal — emit FALLOUT
    # (a standing canon consequence, generator fuel). Side arcs NEVER terminate
    # the scenario (no arc_won/arc_lost receipt, `ended` stays False).
    fallout_directives: list[str] = []
    fallouts = []  # the Fallout records (non-won terminals) — fuel for the generator
    for sa in side_arcs:
        if stored_lifecycle(live_reads, sa) in LIFECYCLE_TERMINALS:
            continue
        life = arc_lifecycle(live_reads, sa)
        if life == "active":
            continue
        set_lifecycle(world, sa, life, turn)
        trace.arc_fallout.append(sa.arc_id)
        if life == "won":
            fallout_directives.append(
                f"A side thread resolved in the world's favor — "
                f"{_human_entity(sa.protagonist)}'s matter came good. Note it in "
                f"passing; it is not the player's victory.")
        else:
            fo = emit_fallout(world, sa, life, turn)
            fallout_directives.append(fo.directive)
            fallouts.append(fo)

    # ---- THE OPPORTUNISTIC DM GENERATOR (LIVING-WORLD-GENERATOR P2a+P2b+P2c) ----
    # Three triggers share one mint path; at most ONE mint per turn (if/elif
    # chain). Paced, gated, fail-open; mints into the hidden plot frame, surfaces
    # only as a diegetic hook. Priority: regenerative > opportunistic > ambient.
    gen_hooks: list[str] = []

    # The development LEDGER records that the WORLD developed (beats achieved,
    # clocks fired, fallout emitted) — not generator bookkeeping. It is written
    # UNCONDITIONALLY (outside `if generate:`), so peak-turn developments are
    # recorded even when the right-of-way gate silences the trigger chain.
    # Skipping it at peak would make a beat-rich climax read as a false half-day
    # of silence and fire ambient the moment the climax breaks (§B, Cx 498).
    from construct.clock import read_clock as _rc_gen
    _gen_mins: float | None = None
    try:
        _gen_mins = float(_rc_gen(world).minutes)
    except Exception:  # noqa: BLE001 — clockless worlds skip ambient timing
        pass

    # _mark_development at non-mint development sites: beats achieved, clocks
    # fired this turn (both recorded in trace before this block), fallout
    # emitted (also above). One call covers all three conditions.
    if _gen_mins is not None and (
            trace.beats_achieved or trace.clocks_fired or fallouts):
        try:
            _mark_development(world, _gen_mins, turn)
        except Exception:  # noqa: BLE001
            logger.debug("_mark_development (non-mint) failed", exc_info=True)

    if generate:
        ctx = {
            "style": style,
            "available_ids": sorted(set(scope or []) | set(npcs) | {arc.protagonist}),
            "present_characters": "\n".join(
                f"{n}: drive={canon_table.get((n, 'drive'))} "
                f"fear={canon_table.get((n, 'fear'))}" for n in npcs) or "(none in scene)",
            "main_protagonist": arc.protagonist,
        }

        minted = None
        try:
            # 1. Right-of-way: main arc at CRISIS or CLIMAX → skip silently (§B).
            #    No receipt, no session row — not a DM judgment. The development
            #    ledger was already written above (unconditional); the trigger
            #    chain contributes ZERO rows on a peak turn.
            if main_at_peak(live_reads, arc):
                pass  # dramatic right-of-way — trigger chain stays quiet

            # 2. Regenerative (P2a): a dead arc seeds the next (highest priority).
            elif fallouts:
                minted = generate_from_fallout(world, live_reads, provider,
                                               fallouts[0], side_arcs, ctx, turn)

            # 3. Opportunistic (P2b): player's committed delta touched something
            #    salient — the DM wakes only when it notices (§A).
            else:
                _opp_moments: list[str] = []
                # spined = present NPCs with a canon drive or fear (§A); initialised
                # here so the ambient branch can read it if the try below fails.
                _spined: set[str] = {
                    n for n in npcs
                    if canon_table.get((n, "drive")) or canon_table.get((n, "fear"))
                }
                try:
                    # Fact-source v3 (§A, Cx 525): the explicit committed batch.
                    # No time-window fact read — narrator-extracted facts are committed
                    # UNSTAMPED (they land at the engine cursor, which never moves during
                    # play), making a valid_from window wrong in both directions: BLIND in
                    # session-zero/harness worlds (cursor < TURN_EPOCH), PERMANENTLY SALIENT
                    # in ingested worlds (cursor > every turn_time). See HD 520 + Cx 525.
                    _turn_floor = turn_time(turn - 1)
                    # (a) Previous turn's narrator delta: read the settle-persisted
                    # receipt-confirmed batch for turn n-1. The handoff row is keyed
                    # per-turn (event:turn_{n-1}/narrator_promote in session:main) so a
                    # missing or failed settle yields [] — never a stale replay (Cx 525 §2).
                    # NOTE: live_reads.state() with frame=SESSION does not resolve
                    # `event:` prefixed entities (PB routes by entity kind; event: entities
                    # with canon rows are not folded in session state reads). Use frame_facts
                    # to read the literal row value directly from the session buffer.
                    _prior_batch_rows = frame_facts(
                        world, SESSION,
                        entity=f"event:turn_{turn - 1}",
                        attribute="narrator_promote")
                    _prior_batch_raw = next(
                        (str(r.value) for r in _prior_batch_rows if r.value is not None),
                        None)
                    _prior_fact_rows: list[dict] = prior_promote_batch(_prior_batch_raw)
                    # (b) Current turn's player-action delta: receipt-confirmed under the
                    # same rule. _player_delta_candidates carries the resolved items with
                    # values (captured before ingest so confirmed_batch() can hydrate the
                    # value-side spine-touch check — PB receipts carry entity/attribute only).
                    # Value limitation: when extraction was skipped (asserts_or_reveals=False)
                    # _player_delta_candidates is [] and receipt_rows is [] — no player delta.
                    _player_batch, _ = confirmed_batch(
                        _player_delta_candidates, receipt_rows)
                    # Merge: prior narrator batch first (the larger, richer source), then
                    # current player delta. Both are post-gate receipt-confirmed rows (§A).
                    _fact_rows: list[dict] = _prior_fact_rows + _player_batch
                    # Event window: PB's `since` is INCLUSIVE; window_events
                    # client-filters to strictly-after to exclude the previous
                    # turn's own events (§A, Cx 498 note). Event rows carry explicit
                    # turn_time stamps and are unaffected by the cursor issue above.
                    _all_win_events = live_reads.events(
                        since=int(_turn_floor), frame="canon")
                    _win_events = window_events(_all_win_events, _turn_floor)
                    _prior_events = live_reads.events(
                        until=int(_turn_floor), frame="canon")
                    _prior_kinds: set[str] = {e.kind for e in _prior_events}
                    _opp_moments = salient_moments(
                        _fact_rows, _win_events, _prior_kinds, _spined)
                except Exception:  # noqa: BLE001 — salience read failure → not salient
                    logger.debug("salient_moments read failed", exc_info=True)

                # A cohort call requires at least one spined NPC in the scene:
                # P2b/P2c always mint NPC-protagonist arcs, and without a spine-
                # carrying NPC present the cohort has no grounded protagonist to
                # propose (§D — "world moves *at* the player, never *as* them").
                if _opp_moments and _spined:
                    if _gen_pacing_ok(live_reads, side_arcs, turn):
                        minted = generate_opportunistic(
                            world, live_reads, provider, _opp_moments,
                            side_arcs, ctx, turn, arc.protagonist)

                # 4. Ambient (P2c): diegetic quiet threshold crossed — endless only (§C).
                elif scenario_mode == "endless" and _gen_mins is not None and _spined:
                    _last_dev = _last_development_min(world, live_reads, _gen_mins, turn)
                    if (_gen_mins - _last_dev >= AMBIENT_QUIET_MIN
                            and _gen_pacing_ok(live_reads, side_arcs, turn)):
                        minted = generate_ambient(
                            world, live_reads, provider,
                            side_arcs, ctx, turn, arc.protagonist)

        except Exception as exc:  # the generator NEVER breaks the turn
            logger.warning("DM generator failed: %s", exc)
            minted = None

        if minted is not None:
            new_arc, hook = minted
            side_arcs.append(new_arc)  # ticks from next turn; also in the portfolio
            trace.generated.append(new_arc.arc_id)
            if hook:
                gen_hooks.append(hook)
            # _mark_development at the mint site (§C).
            if _gen_mins is not None:
                try:
                    _mark_development(world, _gen_mins, turn)
                except Exception:  # noqa: BLE001
                    logger.debug("_mark_development (mint) failed", exc_info=True)

    counters = counters_from_session(live_reads, arc)
    rung = navigate(counters, len(diff), bool(achieved))
    if concluded and not endless:
        rung = None  # the arc has resolved; do not escalate toward a reached end
    trace.pacing = ("concluded" if (concluded and not endless)
                    else (rung.value if rung else "hold"))

    nudge_directive = None
    # Card weaving (CARD-WEAVING.md) SUBSUMES the legacy thread-nudge for cast worlds (Cx
    # 039 #2) — don't double-fire. The nudge remains for pillar/cast-less worlds.
    if rung and threads and not cast and not _grounding_runway:
        try:
            with _phase(trace, "nudge"):
                pick = cohorts.nudge_pick(provider, rung.value, threads,
                                          "\n".join(scene_lines), arc.protagonist)
                trace.cohort_calls.append("nudge_pick:cheap")
                # Deterministic player-boundary guard (letter 025): a
                # directive that names the protagonist is re-asked once,
                # then DROPPED (fail-open) — pressure, never puppetry.
                if names_protagonist(pick["directive"], arc.protagonist):
                    pick = cohorts.nudge_pick(provider, rung.value, threads,
                                              "\n".join(scene_lines), arc.protagonist)
                    trace.cohort_calls.append("nudge_pick:cheap(re-ask)")
            if names_protagonist(pick["directive"], arc.protagonist):
                trace.dropped_cohorts.append("nudge (named the protagonist twice)")
            else:
                nudge_directive = pick["directive"]
                trace.nudge = nudge_directive
        except ProviderError as exc:
            trace.dropped_cohorts.append(f"nudge_pick ({exc})")

    npc_intents: list[str] = []
    if npcs:
        # TURN-LATENCY Lever 4: the speak-intent was already decided in the folded
        # npc_turn call at the early npc phase (one call per NPC). Consume the stashed
        # results here for the briefing — no second model call.
        for npc in npcs:
            intent = npc_turn_results.get(npc)
            if intent is None:  # the folded call failed-open for this NPC
                continue
            if intent["speaks"]:
                npc_intents.append(f"{npc}: wants {intent['intent']}"
                                   + (f" (voice: {intent['line_hint']})"
                                      if intent.get("line_hint") else ""))

    # ---- BRIEFING (no plot:, structurally — player-frame reads only) ----
    # Continuity: the recent story (player actions + the narrator's own beats) as a
    # rolling window — the narrator's short-term memory, since each turn is a fresh
    # stateless call. Rich but bounded to the last `_RECENT_TURNS`.
    try:
        _raw_tr = live_reads.state(_TRANSCRIPT, "recent", frame=SESSION)
        _recent = json.loads(_raw_tr) if _raw_tr else []
    except Exception:
        _recent = []
    # The compacted long-arc memory (themes/dynamics/threads beneath the recent
    # beats) — Kernos-style, host-side, never canon. Empty until beats age out.
    narrative_memory = live_reads.state(_MEMORY, "text", frame=SESSION) or ""
    # Out-of-character creative suggestions the engine agreed to TRY (`/ooc`):
    # soft aspirations, never canon — weave one in only where it fits.
    try:
        wishes = json.loads(live_reads.state("session:wishes", "list", frame=SESSION) or "[]")
    except (ValueError, TypeError):
        wishes = []
    story_so_far = ""
    if _recent:
        beats = []
        for e in _recent[-_RECENT_TURNS:]:
            if e.get("player"):
                beats.append(f"› You: {e['player']}")
            if e.get("prose"):
                beats.append(e["prose"])
        story_so_far = "\n\n".join(beats)
    briefing_parts = []
    if play_style:
        # The game-type directive (GAME-TYPES.md): WHAT KIND of game this is — what
        # to hand-wave vs. dramatize, the tension posture. Maintained every turn so
        # the agent's awareness of the experience never lapses. A directive, not a
        # toggle matrix (founder).
        briefing_parts.append(f"{play_style}\n")
    if wishes:
        # The player floated these OUT OF CHARACTER (`/ooc`) and the engine agreed to
        # try. Weave ONE in only where it fits naturally and serves the story — never
        # if it would spoil or derail the trajectory or the game type's payoff. Let
        # them go otherwise; they are wishes, not instructions.
        briefing_parts.append(
            "PLAYER'S OUT-OF-CHARACTER WISHES (rule of cool — realize one where it "
            "fits naturally and deepens the story; NEVER if it would spoil or derail "
            "the trajectory or the game type's climax; otherwise let it pass):\n"
            + "\n".join(f"- {w}" for w in wishes[-4:]) + "\n")
    if style:
        # The world-level voice overlay (NARRATIVE-FLAVOR-INGEST): HOW to write,
        # distilled once at ingest. Shapes voice/tone only — never adds facts.
        briefing_parts.append(
            f"STYLE (render the grounded world in this voice — tone only, never "
            f"new facts): {style}\n")
    if narrative_memory:
        briefing_parts.append(
            f"NARRATIVE MEMORY (the arc so far — standing dynamics, recurring "
            f"themes, unresolved threads; lower-resolution than the recent beats "
            f"below, but the through-line to honour):\n{narrative_memory}\n")
    if story_so_far:
        briefing_parts.append(
            f"THE STORY SO FAR (recent beats, in detail — your short-term memory of "
            f"what just happened; continue naturally, do not repeat or re-establish "
            f"what's here):\n{story_so_far}\n")
    if trace.time_now:
        # The diegetic hour, on THIS place's calendar — let it shape the light, who's
        # about, what's open; never state it as a clock readout.
        briefing_parts.append(
            f"THE TIME (render its FEEL — light, sounds, who is about — never as a "
            f"clock): {trace.time_now}\n")
    briefing_parts += [
        # The narrator never sees internal frame ids — only the scene as it stands.
        "THE SCENE RIGHT NOW (what is true and present here):",
        "\n".join(scene_lines) or "(nothing established here yet — the grid shows through)",
    ]
    if scene_features:
        # Navigable sub-features of this place (PLACE-FEATURE; part_of-children),
        # distinct from the things merely in the room.
        briefing_parts.append("\nFEATURES OF THIS PLACE (its sub-features/"
                              "structures): " + ", ".join(scene_features))
    if _world_laws or _reality_line:
        # WORLD LAWS (#105, Cx 470 ruling 4): the constitution rides a RESERVED
        # lane AHEAD of the capped pins — a busy turn's clue/social/temporal
        # pins can never push a law out of the narrator's standing awareness.
        # Disclosure-split (founder): understood laws are open lived context;
        # discovered laws bind silently, their edges woven, never named. The
        # reality register's contract rides the same lane (no-law case incl.).
        _lane = "\n".join(p for p in (_reality_line,
                                      _laws_mod.law_lines(_world_laws)) if p)
        briefing_parts.append("\n" + _lane)
        trace.laws = [str(law.get("name") or "") for law in _world_laws]
    if active_pins:
        pin_lines = [f"[{ap.pin.scope_kind}] {ap.pin.directive}"
                     for ap in active_pins[:_PIN_CAP]]
        briefing_parts.append(
            "\nPINNED AWARENESS (foreground these — what is true and pressing "
            "here, ordered by urgency; weave in diegetically, do not list):\n"
            + "\n".join(pin_lines))
    # GAUGE surfacing (GAUGE §4): the live numeric constraint IS the tension. Urgency is
    # derived this turn from the folded level vs the floor (distance_to_floor/range, Cx 150)
    # — never stored. Ordered most-urgent first; the narrator dramatizes it, never prints a HUD.
    _glines = sorted(gauge_lines(arc, world, as_of=_h), key=lambda t: t[2])
    if _glines:
        def _phrase(u: float) -> str:
            return ("all but gone — act now" if u <= 0.1 else "critical" if u <= 0.25
                    else "running low" if u <= 0.5 else "holding")
        briefing_parts.append(
            "\nLIVE PRESSURE (foreground this mounting constraint diegetically — let it "
            "tighten the scene; do NOT print a number/HUD unless the fiction shows a gauge):\n"
            + "\n".join(f"- {g.label}: {int(round(lvl))} ({_phrase(u)})"
                        for g, lvl, u in _glines))
    if weave_directive:
        # Story governance (CARD-WEAVING.md): weave the chosen card at its seam. Replaces
        # the passive cast-threads nudge; on 'let_run' there is no directive (serve the path).
        briefing_parts.append(weave_directive)
    if learned:
        # Interview delivery (§8): the NPC reveals these pieces THIS turn, in character,
        # in response to the player's questioning — deliver them as dialogue/disclosure,
        # not as a fact dump, and never name them as "clues".
        reveal_lines = [f"{_human_entity(npc)} reveals: {a.replace('_', ' ')} "
                        f"of {_human_entity(e)} is {_human_entity(str(v))}"
                        for (npc, clue) in learned for (e, a, v) in [clue.surface_fact]]
        briefing_parts.append(
            "\nWHAT IS LEARNED THIS TURN (the questioned character discloses it now, in "
            "character — weave it into their reply, do not list or label it):\n"
            + "\n".join(reveal_lines))
    if adapt_directives:
        # make-it-real (NARRATION-DISCIPLINE.md): the player's pursued thread became the path
        # to an unfilled cause. Render the reveal as their OWN deduction from the detail they
        # chose — never a redirect back to the authored clue, never a witness lecture.
        briefing_parts.extend(adapt_directives)
    if asks_self:
        # ADDRESSED INWARD (founder 2026-07-03): the classify CHECKED that this question is
        # about the player's own life — the mechanical route that outranks last-speaker.
        briefing_parts.append(
            "\nADDRESSED INWARD (binding): the player's question is about their OWN life, "
            "memory, or circumstances — their own memory answers it, in second person, from "
            "what they know (plus ordinary plausible autobiography under the improv rules). "
            "If the memory holds NO answer, honest uncertainty IS the answer — 'you turn it "
            "over and find nothing certain' is grounded in the moment and valid; never "
            "fabricate, and never hand the question to someone else because the memory came "
            "up empty. No present character answers it for them; someone may ADD what they "
            "uniquely know (an arrangement made, a message sent) only AFTER the memory has "
            "spoken.")
    if memory_result and memory_result.get("stirs") and (memory_result.get("memory") or "").strip():
        # #97 THE REMEMBRANCER: the mind's contribution rides the briefing as felt
        # second-person interiority — PROPORTION-bound (a flicker, not a flashback).
        trace.memory = str(memory_result.get("memory") or "")[:300]
        _feel = (memory_result.get("feeling") or "").strip()
        briefing_parts.append(
            "\nYOUR OWN MIND THIS TURN (weave as FELT memory in second person — a "
            "flicker, not a flashback; never a recital, never dialogue, never an "
            "action): " + trace.memory
            + (f" — felt as {_feel}." if _feel else ""))
    if _memory_tensions:
        # #97 contradiction rule (Cx 434 constraint 5): a quarantined collision is
        # surfaced as in-fiction tension — the FIRST established truth stands.
        briefing_parts.append(
            "\nTHE MEMORY SITS ODDLY (render as felt tension, one beat, never a "
            "lecture; what is already established REMAINS the truth): "
            + "; ".join(_memory_tensions))
    if trace.distance_unknown:
        # #101 inversion (Cx 454): the map couldn't prove this was a local step — the
        # render is SCALE-NEUTRAL: true scale when the fiction establishes it, modest
        # when it doesn't; a flat map must never overdramatize "across the yard".
        briefing_parts.append(
            "\nMOVEMENT AT ITS TRUE SCALE (render the travel honestly): the player "
            "moved between places whose distance the map does not establish. Render "
            "the movement at the scale the FICTION has established — a walk down a "
            "lane is a beat; a ride to another town is departing, the way, and "
            "arriving, with weather and effort as the scene holds them. Where the "
            "distance is NOT established, keep the transit brief and modest — never "
            "invent roads, distances, or landmarks the world hasn't given you.")
    if trace.deliberating:
        # #102 (founder-shaped): the weighing is the character's OWN MIND — second-person
        # deliberation ending on the open question; never a menu, never decided for them.
        briefing_parts.append(
            f"\nYOUR OWN MIND WEIGHS IT (render as ONE beat of second-person "
            f"deliberation, then stop — the player has NOT moved): they mean to set "
            f"out for {trace.deliberating.split(' — ')[0]}, but the story's deadline "
            f"stands against the time the way would take "
            f"({trace.deliberating.split(' — ', 1)[-1]} — translate to FELT time, "
            f"never numbers). Voice it as their own thought — 'you consider it; but "
            f"if you go now, you may…' — and end on the open question: press on, or "
            f"see to what the deadline demands first? Their next word decides; if "
            f"they choose the road, it will not be questioned again.")
    if _move_clarify:
        # ASK, NEVER HALLUCINATE (founder 2026-07-04): the destination was ambiguous —
        # render ONE in-world clarify beat (a companion asking "which do you mean?",
        # the narrator putting the fork plainly); the player has NOT moved; do not
        # invent an arrival or pick for them.
        briefing_parts.append(
            f"\nTHE DESTINATION IS UNCLEAR (render as ONE brief in-world beat, then "
            f"stop — the player has NOT moved): they said they were going to "
            f"\"{_move_clarify}\", and more than one known place could be meant. Have "
            f"the world ask which they mean — a present character's natural question, "
            f"or the narrator laying out the fork plainly. Never guess, never invent "
            f"an arrival.")
    if _voc_holder:
        # #93 (Cx 404 C): the player addressed a unique canon title-holder who IS here —
        # the address binds to them, outranking the last-speaker convention.
        briefing_parts.append(
            f"\nSPOKEN TO BY TITLE (binding): the player's address names a title held "
            f"by {_voc_name} — the words go to THEM, not to whoever spoke last. They "
            f"have the floor and answer in their own voice.")
    elif _voc_absent:
        # #93 (Cx 404 C): the addressed title-holder is NOT here — never re-route
        # their floor to whoever is; render the honest not-here beat.
        briefing_parts.append(
            f"\nCALLED FOR SOMEONE NOT HERE (binding): the player's address names a "
            f"title held by {_voc_name} — who is NOT present. No one here answers FOR "
            f"them, takes the question in their stead, or volunteers their knowledge; "
            f"render the address landing on their absence honestly (the room notes it; "
            f"someone may say plainly they are not here, and where they might be found "
            f"if that is established). Never teleport them in.")
    if commitment_clarified:
        # #88A: the decisive move needs a concrete stage before it can be judged — render ONE
        # in-world clarification beat (a character asking, the empty room answering); do NOT
        # resolve or conclude anything this turn; the player's NEXT attempt is taken as given.
        briefing_parts.append(
            "\nTHE DECISIVE MOVE NEEDS ITS STAGE (render this as ONE in-world beat, then stop): "
            + commitment_clarified)
    if commitment_bounced:
        # COMMITMENT-AS-EFFECT slice 1: the player tried to force the finale before the causes are
        # covered. The world DECLINES to conclude on it — NOT a failure, a "not yet": the authority
        # won't act on what's unproven, the threads don't connect, the declaration rings premature.
        # Render that diegetically and leave the player IN the story to keep working. Never end here.
        briefing_parts.append(
            "\nTHE COMMITMENT DOES NOT LAND (render this, do NOT end the story): the player has "
            "moved to conclude — but they have NOT yet earned/proven it on what they've actually "
            "established. Show the world declining, in-genre and without a lecture: the authority "
            "won't act on so little, the case/claim doesn't hold up, the moment rings premature — "
            "and the player is left to keep going (there is more to uncover/earn). This is 'not "
            "yet,' NOT a defeat; do not narrate an ending or a verdict.")
    if discovered:
        # Discovery affordance (§3c layer 3): the player now knows where to find these
        # off-scene people. Offer the route diegetically (the witness mentions where they
        # are); the player can GO there next. Pacing/bookkeeping, not a stored route flag.
        seek_lines = [f"{_human_entity(ref)} can be found at {_human_entity(loc)}"
                      for (ref, loc) in discovered]
        briefing_parts.append(
            "\nA LEAD OPENS (the player just learned where to find someone not present — let "
            "it surface naturally, e.g. the witness says where they are; the player may now go "
            "to them). Surface it as a CONTINUATION of what this conversation has already "
            "established: if the person is already under discussion, the speaker simply ADDS "
            "where to find them — never a recognition beat ('Mr So-and-so? I know that name!') "
            "for a name the conversation, or the speaker themselves, already raised:\n"
            + "\n".join(seek_lines))
    if terminal and died:
        # #95 THE FALL + THE TESTAMENT (DEATH-TESTAMENT.md, Cx 422): the death receipt
        # owns the terminal render — a THIRD branch selected BEFORE the reckoning/
        # settling ternary is ever consulted. Honest, staged, never a gotcha or a score.
        _dcast = sorted({arc.protagonist}
                        | {e for e in arc_entities(arc) if e.startswith("person:")})
        _dscope = [e for e in (set(arc_entities(arc)) | set(scope or []))
                   if e.startswith(("person:", "place:", "obj:", "fact:"))
                   and live_reads.has_entity(e)]
        _dreveal = [f"{f['entity']} · {f['attribute']} · {f['value']}"
                    for f in _snap_or_empty(p, sorted(_dscope), as_of=_h).get("facts", [])
                    if f["entity"] != arc.protagonist][:20]
        briefing_parts.append(
            "\nTHE STORY ENDS HERE — THE PROTAGONIST FALLS. The staged mortal risk the "
            "player walked into has claimed them; render it truthfully, in TWO BEATS, "
            "separated by a line containing only '⸻':\n"
            "BEAT 1 — THE FALL: the death rendered honestly, in scene, at the pace of "
            "the moment — the world answers the player's last move as it truly falls. "
            "NO rescue invented, NO cutaway, NO scolding, NO miraculous reprieve.\n"
            "BEAT 2 — THE TESTAMENT: the world after them, and their effect on it. "
            "What they changed that STAYS changed; what they left undone; the promises "
            "and bonds left forever open — named as testament, not bookkeeping ('she "
            "waited at the rail end after close; he never came'). A fitting fate for "
            f"each of these, as the player's passing touches them: {_dcast}. "
            "Concealment lifts now (the story is over): name what was hidden, what "
            "they never learned. Close every thread; open nothing; this world's story "
            "ends with them.")
        if _dreveal:
            briefing_parts.append(
                "\nTHE TRUTH (revealed at the curtain — weave in what lands):\n"
                + "\n".join(_dreveal))
    elif terminal:
        # Phase 4 flavor: when the arc declares pillars, the ending's character is the
        # EFFECT of pillar coverage (STORY-SHAPES §0a) — the narrated consequence of the
        # causes, never "you won/lost". Falls back to the commitment grade for legacy
        # (pillar-less) arcs so existing worlds are unchanged.
        _shape_flavor = {
            "triumph": "triumphant and earned — the causes came together soundly",
            "costly_victory": "a hard-won, costly close — reached, but the toll shows",
            "bittersweet": "bittersweet and ironic — it lands, but on a flawed footing; "
                           "the truth the player missed festers",
            "partial": "partial and unfinished — some of it resolved, much left open",
            "failure": "a failure that lands as consequence — the causes never came together",
            "quiet_failure": "a quiet, muted close — the moment passed, the causes unmet",
        }
        if conc:
            _grade = conc["outcome"]
            flavor = _shape_flavor[conc["outcome"]] + f" ({conc['basis']})"
        else:
            # Legacy grade-aware flavor (pillar-less arcs): vindication / near-miss /
            # ironic-wrong / hollow-pyrrhic.
            _grade = commitment_grade or ("won" if outcome == "won" else "lost")
            flavor = {
                "vindicated": "triumphant and earned — they got it right",
                "partial": "bittersweet — right in the main, but incomplete",
                "wrong": "ironic and quietly devastating — they were confident and WRONG",
                "pyrrhic": "a hollow victory — right, but at a cost that outweighs it",
                "won": "triumphant but earned — the goal is reached",
                "lost": "somber — the goal is lost, the chance gone",
            }.get(_grade, "somber — the goal is lost")
        # The movie epilogue: name the cast for fates, lift concealment, and HAVE FUN
        # revealing the interesting bits the player never uncovered (the dessert course).
        cast = sorted({arc.protagonist}
                      | {e for e in arc_entities(arc) if e.startswith("person:")})
        reveal_scope = [e for e in (set(arc_entities(arc)) | set(scope or []))
                        if e.startswith(("person:", "place:", "obj:", "fact:"))
                        and live_reads.has_entity(e)]
        reveal = [f"{f['entity']} · {f['attribute']} · {f['value']}"
                  for f in _snap_or_empty(p, sorted(reveal_scope), as_of=_h).get("facts", [])
                  if f["entity"] != arc.protagonist][:20]
        _ending_tag = conc["outcome"] if conc else f"{outcome}; grade: {_grade}"
        # S1 (#96, Cx 414 constraint 1): the ending voice BRANCHES on whether a player
        # commitment landed. A commitment-owned close gets the RECKONING scene; a silent /
        # world-event / authored-failure close gets a SETTLING beat — the world registering
        # the matter closing, with NO verdict, accusation, grade, or scene of judgment
        # (the invisible flip was the bug; a courtroom the player never convened is another).
        _commitment_landed = bool(commitment_grade)
        _beat1 = (
            "BEAT 1 — THE RECKONING SCENE: the player's decisive move LANDS where and as "
            "they staged it, and the world ANSWERS it, in scene — faces, voices, the "
            "moment turning. A wrong or failed move gets a SCENE too (the accusation "
            "landing on the wrong man, the room knowing it), never an explanation.\n"
            if _commitment_landed else
            "BEAT 1 — THE SETTLING: no decisive move was spoken, and none is invented — "
            "the world simply REGISTERS the matter closing, in scene: the thing found, "
            "the danger passed, the machinery of consequence starting to turn on its own "
            "(word carried, a door barred, men arriving). NO verdict, NO accusation, NO "
            "judgment scene — something completes and is SEEN to complete.\n")
        briefing_parts.append(
            f"\nTHE STORY ENDS HERE ({_ending_tag}). This conclusion is the EFFECT of what "
            f"the player did and left undone — narrate it as consequence, never as a "
            f"score. Render the close in TWO BEATS, separated by a line containing only "
            f"'⸻' (the close must breathe — never one compressed breath):\n"
            + _beat1 +
            f"BEAT 2 — THE AFTERMATH ({flavor}): the settled wake. For the protagonist "
            f"(you) AND each of these characters, a fitting FATE — where they end up, what "
            f"the outcome cost or won them: {cast}. A loss may carry an unexpected BOON "
            f"(a door opened, a truth freed, hope for a next time); a victory may carry a "
            f"lasting WOUND — when the shape says both, say both. Concealment lifts now "
            f"(the story is over): name what was hidden, savor what the player never "
            f"uncovered — the secret walked past, the red herrings' truth. Close every "
            f"thread; apply NO new pressure, open NO new hooks.")
        # The twist fires when the player committed to a MISTAKEN case (a false-filled
        # required cause → conc["wrong_case"]), or, for legacy arcs, a 'wrong' grade. NB it
        # uses wrong_case, NOT `not sound`: a triumphant Farce is all-false (sound=False) but
        # NOT a wrong case, so it must not trip the twist (Cx 027 blocker 3). The wrong cause
        # lands, then the real truth surfaces at the curtain.
        _wrong_case = (conc["wrong_case"] if conc else commitment_grade == "wrong")
        if commitment and _wrong_case:
            briefing_parts.append(
                f"\nTHE TWIST (the player's case was not sound — land it like Sherlock going "
                f"over his notes): they concluded “{commitment}”, but the truth is "
                f"otherwise. Reveal the REAL answer and why their read was mistaken — the "
                f"clue they misread, what was really going on. This is the payoff, not a "
                f"scolding.")
        if reveal:
            briefing_parts.append(
                "\nTHE TRUTH (revealed at the curtain — the full picture, including what "
                "the player never learned; weave in what lands):\n" + "\n".join(reveal))
    elif concluded and not endless:
        _aftermath = "the world responds to the player in the settled wake of the " \
                     "story's end, applying no new dramatic pressure."
        if conc:  # the resolution's character is the EFFECT of pillar coverage
            _aftermath = (f"the close is {conc['outcome']} — {conc['basis']}. Render it as "
                          f"the consequence of the causes the player did and didn't "
                          f"establish, in the settled wake; apply no new pressure.")
        briefing_parts.append("\nTHE ARC HAS RESOLVED — render this turn as "
                              "aftermath/denouement: " + _aftermath)
    else:
        # CONVERGENCE (CONVERGENCE-TO-CONCLUSION.md; founder "all roads lead to the
        # conclusion"): act-aware pull toward the climax + relocate-the-beat-to-the-
        # player. Only while the arc is live (not terminal, not concluded — those own
        # the close). Dramatic pull only; never reveals the answer.
        # peril/thriller stories amplify the suspense build-up; everything else gets the gentler
        # general mounting-stakes (founder; Cx 113: a genre-HAZARD signal — survival/horror/combat
        # → 'peril' — NOT cost_disposition, which over-fired for mastery/contest/discovery).
        _act, _conv = _convergence_directive(current_phase(live_reads, arc),
                                             climax_ready(live_reads, arc),
                                             peril=(suspense == "peril"))
        trace.act = _act
        if _conv:
            briefing_parts.append(_conv)
        if _reckoning_ready:
            # THE DECISIVE MOMENT IS AT HAND (Cx 141; tone made story-agnostic): this commitment-
            # owned arc is ripe — what it was building toward is reachable now — but the CURTAIN is
            # the player's conclusory move, WHATEVER this story's "IT" is: a deduction's accusation,
            # a romance's confession, a bond's reconciliation, a choice owned or renounced. Phrase it
            # in THIS story's register, not a thriller's. Steer toward it without forcing or revealing.
            briefing_parts.append(
                "\nTHE DECISIVE MOMENT IS WITHIN REACH — what this story has been building toward is "
                "now available to the player; what remains is THEIR conclusory move (in this story's "
                "own register: a declaration, a confession, a choice, naming a truth, the decisive "
                "act). Bring the moment to a head and make it FEEL available and weighty — but do NOT "
                "make it for them, and do not reveal anything hidden. The curtain is theirs to draw. "
                "SAY IT ONCE: if your recent turns already voiced this pressure ('the case now comes "
                "down to…', 'the hour demands…'), do NOT restate it — hold it quietly instead (a "
                "detail, a look, a silence carries the same weight without the sermon).")
    if fallout_directives:
        # A side arc died/resolved this turn (LIVING-WORLD-GENERATOR §3): the
        # world acknowledges it as a real beat in the wake — never a silent stall,
        # never a game-over for the player. The standing consequence is already in
        # canon; this just renders the world noticing.
        briefing_parts.append(
            "\nA STORY THREAD HAS CLOSED (render diegetically, as the world "
            "reacting in passing — a real beat, NOT the end of YOUR story; "
            "acknowledge it and move on):\n"
            + "\n".join(f"- {d}" for d in fallout_directives))
    if gen_hooks:
        # A new development the living world threw up this turn (P2): surface it
        # as it ARRIVES in the scene — diegetic, never a system announcement.
        briefing_parts.append(
            "\nA NEW DEVELOPMENT ARRIVES (render diegetically, in the moment — a "
            "fresh hook entering the scene, not a menu):\n"
            + "\n".join(f"- {h}" for h in gen_hooks))
    # AUTHORITATIVE PLAYER IDENTITY (founder 2026-06-30: "player name wins, fully"). The player's
    # interview-set name/pronouns are the SINGLE source of truth — they must WIN over any authored-
    # default personal name/gender baked into premise/background prose or the entity id. State it
    # explicitly and instruct supersession, so the cast addresses the player by THEIR chosen identity,
    # not the authored "Clara Vale". (The whole interview propagates: name + pronouns + the you_lines
    # facts below carry background/role.)
    # Read identity through the FOLDED POINT READ (Cx 320): `name` is set-valued, so a stale
    # narrator-polluted `name="Miss Vale"` row coexists with the player's `name="Bradford Clemense"`;
    # the snapshot dict (`canon_table`) collapses to the LAST member, but `state()` serves the
    # authoritative winner. Carry pronouns + background + role from canon too (the Foyer writes them
    # there; the player-frame YOU block misses them).
    def _id_attr(a: str) -> str:
        try:
            v = live_reads.state(arc.protagonist, a)
        except Exception:
            v = None
        return str(v) if isinstance(v, str) else ""
    _pname = _id_attr("name") or _disp(arc.protagonist)
    _ppron = _id_attr("pronouns") or _id_attr("gender")
    _pbg = _id_attr("background")
    _prole = _id_attr("role")
    if _pname:
        _id_head = (f"\nTHE PLAYER CHARACTER IS {_pname}"
                    + (f" ({_ppron})" if _ppron else "")
                    + ". That is WHO they are — not how to address them every line (founder: the "
                      "full name in every reply reads canned). Refer to them the way people "
                      "actually would in this world and moment: plain 'you', a title ('sir', "
                      "'inspector'), a surname, or nothing at all — the full name only where a "
                      "person would naturally use it (a formal introduction, a pointed moment)"
                    + (f"; {_ppron} pronouns throughout" if _ppron else "")
                    + ". If any premise/background/context text uses a DIFFERENT personal name or "
                      "gender for the protagonist, that is a stale authored default for the SAME "
                      f"person — never use the other name."
                    + (f"\n- their role: {_prole}" if _prole else "")
                    + (f"\n- what brought them here: {_pbg}" if _pbg else ""))
        briefing_parts.append(_id_head)
    if you_lines:
        briefing_parts.append("\nYOU (the player character; never a third party):\n"
                              + "\n".join(you_lines))
    if terminal or (concluded and not endless):
        # CLOSE TURN (Cx 139 #2): the epilogue/aftermath directive above OWNS the render. The
        # player's act is the FINAL beat folding INTO the close — NOT "render exactly this, no
        # more", which fought and beat the epilogue (the narrator rendered the action, never the
        # curtain). Fold it in so the denouement is what lands.
        briefing_parts.append(
            f"\nTHE PLAYER'S LAST ACT (the move that brings the curtain down — render it as the "
            f"final beat that FOLDS INTO the epilogue/aftermath above, not as the whole turn; the "
            f"close owns the scene): {player_input}")
    else:
        briefing_parts.append(f"\nTHE PLAYER JUST DID (render exactly this, no more): "
                              f"{player_input}")
    if trace.movement_obstruction:
        seg = trace.movement_obstruction
        if trace.movement_status == "blocked":
            ev = seg.get("evidence") or []
            facts = "; ".join(
                f"{e.get('entity')} · {e.get('attribute')} · {e.get('value')}" for e in ev
            ) or "the way is obstructed"
            briefing_parts.append(
                f"\nMOVEMENT BLOCKED (render diegetically): the player tried to go there "
                f"but the way is barred — {facts}. Show the attempt and why it fails; "
                f"the player does NOT arrive.")
        else:  # obscured
            briefing_parts.append(
                "\nMOVEMENT UNCERTAIN (render diegetically): the state of the way can't be "
                "confirmed — render the passage as ambiguous; do NOT assert it is clearly open.")
    if trace.reveals:
        pairs = "; ".join(f"{a} is {b}" for a, b in trace.reveals)
        briefing_parts.append(
            f"\nREVEAL (render as the player's dawning recognition this turn): {pairs}. "
            f"Two figures the player took for separate are one. Dramatize the realization; "
            f"don't state it as a flat fact.")
    # WHAT THE PLAYER CARRIES (object permanence — founder: "a mug from the bar doesn't not
    # exist"): the objects in the protagonist's possession (taken or granted), so the narrator
    # grounds on what's in hand and never re-narrates a held thing back where it came from.
    # Read from canon contents; best-effort, never sinks a turn.
    try:
        _held = [h for h in p.contents(arc.protagonist, as_of=_h) if str(h).startswith("obj:")]
    except Exception:
        _held = []
    if _held:
        def _held_name(h: str) -> str:
            nm = canon_table.get((h, "name"))
            if not nm:
                try:
                    nm = live_reads.state(h, "name")
                except Exception:
                    nm = None
            return str(nm or _human_entity(h))
        briefing_parts.append(
            "\nWHAT YOU ARE CARRYING (in hand or on your person right now — honor this; never "
            "narrate one of these back where it was taken from). This list is EXCLUSIVE: it is "
            "everything on your person — anything NOT named here (incl. a thing you earlier set "
            "down/handed off/left behind) is NOT carried; do not narrate it as pocketed or in hand: "
            + ", ".join(_held_name(h) for h in _held))
    if trace.dropped:
        # DROP ACKNOWLEDGMENT (Cx 299 non-blocking): a thing set down THIS turn left the player's
        # hands and stays where it was left — so the narrator doesn't re-pocket it from transcript
        # memory next turn (the founder's "object follows me" family). Names the object + the place.
        _dropped_canon = canon_table.get((trace.dropped, "name"))
        if not _dropped_canon:
            try:
                _dropped_canon = live_reads.state(trace.dropped, "name")
            except Exception:
                _dropped_canon = None
        _dropped_nm = str(_dropped_canon or _human_entity(trace.dropped))
        _here_nm = str(canon_table.get((pre_scene, "name")) or _human_entity(pre_scene)) if pre_scene else "here"
        briefing_parts.append(
            f"\nJUST SET DOWN (no longer carried — it STAYS here, at {_here_nm}; do not narrate it "
            f"back in hand or pocket): {_dropped_nm}")
    if npcs:
        # WHO IS PRESENT (continuity guard — Cx 091 #1): name EVERY present character, not just
        # the ones who speak this turn. A silent present NPC (standing quietly, watching) was
        # surfacing only as raw fact triples and the narrator could erase them ("the doctor is
        # the only one here") — a coherence break against the cold open. Speakers carry their
        # wants; the rest are simply named as present so they can't vanish.
        # COMPANION TEXTURE (#82/#85): the standing `accompanying` state marks who is WITH the
        # player by their own agreement — a companion, not a bystander. Surfaced so the render
        # gives them living texture: they react, notice, and may interject unprompted.
        _companions = set(trace.npcs_joined)
        for n in npcs:
            if n in _companions:
                continue
            try:
                if live_reads.state(n, "accompanying") == arc.protagonist:
                    _companions.add(n)
            except Exception:  # noqa: BLE001
                pass
        present_lines = []
        for n in npcs:
            nm = str(canon_table.get((n, "name")) or _human_entity(n))
            # CAST IDENTITY (#87): the authored pronouns ride the presence line so the
            # narration can never drift a character's gender between scenes.
            _pn = canon_table.get((n, "pronouns"))
            if not _pn:
                try:
                    _pn = live_reads.state(n, "pronouns")
                except Exception:  # noqa: BLE001
                    _pn = None
            if _pn:
                nm += f" ({_pn})"
            _tag = " [COMPANION — with the player by agreement]" if n in _companions else ""
            intent = npc_turn_results.get(n)
            if intent and intent.get("speaks") and intent.get("intent"):
                line = f"{nm}{_tag}: wants {intent['intent']}"
                if intent.get("line_hint"):
                    line += f" (voice: {intent['line_hint']})"
                present_lines.append(line)
            else:
                present_lines.append(f"{nm}{_tag}: present, silent for now (do NOT remove them "
                                     f"from the scene — they remain here unless they visibly "
                                     f"leave)")
        _companion_note = (
            " A COMPANION travels with the player and lives in the scene: they react to what "
            "happens, notice things in their own competence, and may interject or murmur an "
            "aside UNPROMPTED — a quick beat, not a speech; they never narrate the player and "
            "never dominate the turn." if _companions else "")
        briefing_parts.append(
            "\nPRESENT CHARACTERS (ONLY these characters are here right now — keep every one in "
            "the scene; play the ones with wants, keep the rest present even if quiet; anyone else "
            "from earlier scenes is elsewhere — do not stage them here):"
            + _companion_note + "\n"
            + "\n".join(present_lines))
    else:
        # PRESENCE TRUTH WHEN ALONE (founder 2026-07-01 "why are nell and grieves here???" / Cx 354
        # B2): with an EMPTY colocated set the briefing used to say NOTHING about presence, so the
        # narrator rode the transcript window and resurrected departed cast. State the engine truth.
        briefing_parts.append(
            "\nPRESENT CHARACTERS: none besides you. Do not stage earlier characters here, and do "
            "not have an absent person arrive, speak, or be recalled doing things in this place — "
            "the world's map says who is where; if the player seeks someone absent, the way to "
            "them is going there or sending word, never their sudden appearance.")
    if nudge_directive:
        briefing_parts.append(f"\nPACING DIRECTIVE (weave in diegetically): {nudge_directive}")
    if _grounding_runway and not (trace.clocks_fired or trace.beats_achieved
                                  or trace.terminal or trace.concluded):
        # ...unless a hand-authored turn-1 clock/beat/terminal genuinely fired — then the story
        # HAS arrived and the "settle a beat first" framing would contradict it (Cx 280 nit).
        briefing_parts.append(
            "\nGROUNDING RUNWAY (CHARACTER-GROUNDING, founder): this is the player's first beat — "
            "they are still settling into WHO and WHERE they are (their own space, their role, the "
            "ordinary texture of their world). Keep it GROUNDED and low-pressure; answer what they "
            "do. Do NOT introduce the inciting incident, the case, or any call-to-action this turn "
            "unless the PLAYER reaches for it — let them inhabit their world a moment first. The "
            "story arrives next beat.")
    deflect_secret = False
    if improv_query:
        public_name_toks = {t for nm in names.values()
                            for t in nm.lower().replace("-", " ").split()}
        secret_toks = _secret_tokens(arc, live_reads, public_name_toks)
        qtoks = set(improv_query.lower().replace("?", " ").replace(",", " ")
                    .replace(".", " ").split())
        deflect_secret = bool(secret_toks & qtoks)
    if improv_query and deflect_secret:
        # The fallen-through question probes the mystery's HIDDEN answer directly
        # (Cx 022 blocking #2). Do NOT improvise here — improvisation could brush the
        # secret. Deflect deterministically; the concealment block below names what's
        # protected, this just keeps the narrator from trying to answer it at all.
        trace.adjudication = "deflect: question probes a concealed arc fact"
        briefing_parts.append(
            f"\nWITHHELD QUESTION (do NOT improvise an answer): the player asked "
            f"“{improv_query}”, which reaches for something they have NOT uncovered. Do "
            f"not answer, confirm, deny, or hint at it — and do NOT invent a substitute "
            f"answer either. Deflect diegetically (the record is silent on that / it "
            f"isn't yours to know yet / that thread hasn't been pulled) and turn the "
            f"moment back to what is present and knowable. A deflection is NOT a flat "
            f"refusal: whoever fields it reacts as a person would (see A PEOPLED WORLD) — "
            f"an accusation lands with feeling before any procedure is cited. This is "
            f"earned only through play.")
    elif improv_query:
        briefing_parts.append(
            f"\nUNDER-DETERMINED QUESTION — IMPROVISE, but the WORLD'S INTEGRITY COMES "
            f"FIRST: the player asked “{improv_query}” and the record doesn't spell it out. "
            f"Answer as what THIS character would plainly know — a long-term resident knows "
            f"the local geography, where people eat, the neighbors, the routines.\n"
            f"  • If the thing plausibly EXISTS here but simply isn't written down yet, "
            f"AFFIRM it and invent consistent specifics (a name, a direction, a few streets "
            f"over) that fit this world.\n"
            f"  • BUT if the player names something that does NOT fit this world — an "
            f"anachronism or an out-of-setting thing (a 'pizza joint' in a rationed off-world "
            f"colony; a smartphone in a medieval vale) — do NOT fabricate it to match them. "
            f"Gently CORRECT in-world: there is no such thing here; name what this world has "
            f"in its place ('no pizza joint in Anchor — people eat at the ration canteen') "
            f"and let the player adapt to the world. Improvise the WORLD AS IT REALLY IS; "
            f"never bend its nature to the player's assumption.\n"
            f"Never a flat 'you can't say' for ordinary, knowable things; only a genuinely "
            f"SECRET answer is withheld (deflect diegetically). What you establish becomes "
            f"real (it will be remembered).")
    # Uncertain action → REUSE the tier drawn earlier (EVENT-OCCURS-FIRING reorder, Cx 115 — one
    # draw per turn, bound BEFORE beat firing) and tell the narrator WHAT happens (succeed/fail +
    # the twist); it improvises HOW. Assured actions never draw — they just succeed.
    if needs_test and _resolved_tier and _resolved_tier != "assured":
        briefing_parts.append("\n" + resolution.directive(_resolved_tier, uncertain_of))
    # ---- #95 mortal-risk render directives (DEATH-TESTAMENT.md, Cx 422) ---------------
    # Staged-never-a-gotcha: the first life-risking turn makes the stakes UNMISTAKABLE
    # and lands short of death; policy shields/premise-folds override a fatal draw.
    if _death_staged and not died:
        briefing_parts.append(
            "\nMORTAL STAKES (render, binding): this move risks the player character's "
            "LIFE, and they must SEE that plainly — make the lethal stakes unmistakable "
            "in the scene (the drop, the blade, the fire — concretely). This turn the "
            "move lands SHORT of death: a near-miss, a wound, pinned, thrown back — the "
            "world's honest warning shot. If they press on into this peril, it can kill.")
    elif (mortal_risk and _resolved_tier == "terrible_failure" and not died
          and death_policy in ("premise", "shielded")):
        # Cx 426: shielded/premise never stage a peril marker, so their fatal-draw
        # directives fire on the risk itself — the policy IS the contract, no
        # persistence needed (a mortal chapter's fatal draw is handled above/at death).
        if death_policy == "premise":
            briefing_parts.append(
                "\nDEATH, TRANSFORMED (render, binding): the move kills the player "
                "character — render the death honestly, and then the story's own "
                "premise transforms it (the loop resets, the ghost persists, the "
                "mechanism catches them) exactly as this story's premise established. "
                "The death is real and felt; the premise, not a rescue, is what answers "
                "it. The story continues.")
        else:  # shielded — the genre's contract caps the price below death
            briefing_parts.append(
                "\nTHE PRICE STOPS SHORT OF DEATH (render, binding): the failure lands "
                "hard — a wound, capture, ruin, a door slammed — in this genre's own "
                "conventions, but it does NOT kill the player character. Make the cost "
                "real and lasting; never a lethal beat.")
    if trace.reshape:
        # The act reshaped the world (committed pre-render). Tell the narrator the new
        # truth so prose matches canon; the sanctioned rows are licensed past the gate.
        briefing_parts.append(
            "\nWHAT THE ACT CHANGED (binding — the player's action reshaped the world; "
            "render this as real and match it exactly): " + trace.reshape)
    if trace.events_fired:
        # an authored act-beat fired this turn — it is now BINDING canon (Cx 115 #1); render it as
        # having happened, never contradict it.
        briefing_parts.append(
            "\nWHAT JUST HAPPENED (binding — the player's action brought this about; render it as "
            "real, do not walk it back): "
            + "; ".join(k.replace("_", " ") for k in trace.events_fired))
    # CONCEALMENT = STRUCTURAL ABSENCE (Kernos 076 Q2 / Cx 023 blocking #1): the narrator
    # is NOT handed the arc's hidden answer. It is briefed ONLY from the player frame, so
    # it cannot leak what it never sees. (Replaces the old _concealment_directive, which
    # fed the narrator the answer + "don't reveal" — the vault-with-a-sticky-note the mesh
    # ruled against, MORE leakable, not less. The strict promotion gate below stays as a
    # cheap backstop; the secret-question deflection guard above still fires.)
    # In HOLD-MODE (the story isn't concluding this turn) add the NEUTRAL-NARRATOR
    # discipline (Kernos Q4 / Cx blocking #2) — load-bearing for "the player may be
    # wrong": present evidence flatly, never weight a theory toward a verdict.
    hold_mode = not terminal and not (concluded and not endless)
    if hold_mode:
        briefing_parts.append(
            "\nNEUTRAL ON THE ANSWER (binding): stay neutral about the mystery's "
            "SOLUTION — present clues and misleading-but-true detail alike WITHOUT "
            "weighting them, and never confirm, deny, hint, wink at, or tonally tilt "
            "toward the player's theory or any conclusion; a leading question (“so it was "
            "X, right?”) gets only the observable facts, honest uncertainty, or an "
            "in-world deflection. This neutrality is EPISTEMIC — about the evidence and "
            "the verdict — and is NOT a flattening of human feeling: the characters still "
            "react with full emotion (see A PEOPLED WORLD), they simply do not give the "
            "answer away. The player draws their own conclusions — let them, even when "
            "they are heading somewhere wrong. The truth is told only at the end, never "
            "coaxed out mid-play.")
        # The DM's CARD: the hidden destination to FORESHADOW toward (card model). Gives
        # the narrator the answer so it can lay a convergent trail; "weave, don't blurt".
        dest = _destination_directive(arc, live_reads)
        if dest:
            briefing_parts.append(dest)
    briefing = "\n".join(briefing_parts)
    trace.briefing = briefing  # captured for the mechanics log (the directives → the prose)

    # ---- RENDER (loud-fail) ----------------------------------------------
    # SCENE-CONTEXT-SHAPE Stage 2: the peopled / competence directives ride the window
    # ONLY when this turn triggers them — present cast (containment-aware npcs), and a
    # capability-dependent protagonist-knowledge move (classify's uses_protagonist_knowledge,
    # or the question→improv ordinary-knowledge fallthrough). Cx 247 / K 080.
    _peopled, _competence = bool(npcs), (uses_knowledge or asks_self)
    # RULE OF COOL (founder 2026-06-27): inject the improv-serves-the-thread directive when there
    # is a rich live thread to gravitate toward — present cast, unwalked threads, or an authored
    # cast/pillar surface. Keeps the narrator's improv enriching the core, not inventing hollow
    # tangents (the castdemo rabbit-hole). Off on a genuinely empty scene (no always-on mass).
    _serve_thread = bool(npcs or threads or cast)
    with _phase(trace, "narrate"):
        prose = cohorts.narrate(provider, briefing, arc.protagonist,
                                peopled=_peopled, competence=_competence,
                                serve_thread=_serve_thread)
    trace.cohort_calls.append("narrate:main")
    # Deterministic player-boundary guard on the render: prose naming
    # the protagonist in third person gets ONE re-ask with the violation
    # named; a second violation ships but is flagged in the trace and
    # session receipts (visible to the live tester, never silent).
    if names_protagonist(prose, arc.protagonist):
        prose = cohorts.narrate(
            provider,
            briefing + f"\n\nVIOLATION TO FIX: your previous render named "
            f"{arc.protagonist} as a third-person character. They are 'you'. "
            f"Re-render without naming them.",
            arc.protagonist, peopled=_peopled, competence=_competence,
            serve_thread=_serve_thread)  # same flags (Cx 247)
        trace.cohort_calls.append("narrate:main(re-ask)")
    if names_protagonist(prose, arc.protagonist):
        trace.player_boundary = "FLAGGED: protagonist named in third person"

    def _settle():
        """Deferred post-narrate bookkeeping (TURN-LATENCY dumbfire): extract narrator
        facts to canon, mirror, append the transcript, compact memory, advance time. Feeds
        FUTURE turns only — never the prose already returned. The caller runs it in the
        background and JOINS it before the next turn (single PB connection demands ordering)."""
        nonlocal _recent  # the compaction branch rebinds the rolling window (trims it)
        # ---- POST: INGEST GATE (GATED-INGEST-COHORT) --------------------------
        # The licensed narrator improvises freely WITHIN its grounding, but its
        # prose is not trusted straight to canon. Stage it in a quarantine frame,
        # then promote everything EXCEPT a row that overwrites an established canon
        # value (a contradiction) — those stay quarantined for arc review. New
        # facts and same-value restatements promote (so good improv — the drawer's
        # papers, the paperclip — is never blocked). Narrator-origin is stamped.
        pre_keys = {(row["entity"], row["attribute"]) for row in receipt_rows}
        pre_entities = {row["entity"] for row in receipt_rows}
        briefing_keys = set(player_table)
        license_tokens = set(
            f"{briefing}\n{player_input}".lower()
            .replace("’", "").replace("'", "")
            .replace(",", " ").replace(".", " ").replace(";", " ").replace(":", " ")
            .split())

        def _licensed(entity: str, attribute: str) -> bool:
            # Licensed = the narrator was GIVEN it: a briefing/player key, an entity
            # already in play, the scene, or an entity whose every name-token came
            # from the briefing+input (possessives normalized).
            if (entity, attribute) in briefing_keys or (entity, attribute) in pre_keys:
                return True
            if entity in pre_entities or entity == scene:
                return True
            name_tokens = entity.split(":", 1)[-1].replace("-", "_").split("_")
            return all(tok in license_tokens for tok in name_tokens if tok)

        canon_before = dict(canon_table)  # established values BEFORE this render
        # `defer`: don't durability-classify the QUARANTINE staging — these rows are
        # only here to diff against canon for contradictions; the survivors get a single
        # batch classification on PROMOTION below. Kills the per-turn double-classify.
        # FAIL-OPEN: the PROSE is the player-facing deliverable and is already rendered;
        # the post-render extraction is bookkeeping (staging for the canon-commit gate). A
        # schema violation here (the cheap extractor malforming its JSON, raising after a
        # re-ask) must NOT sink an already-delivered turn — the harness caught this sinking
        # turns. Ship the prose; skip this turn's canon-commit (logged). (Turn-loop policy:
        # "the narrator failing is the turn failing" — this is POST-narrator.)
        # ENTITY AUTHORITY (ENTITY-AUTHORITY.md / Cx 304): READ-ONLY extract → RESOLVE → structured
        # stage. The narrator's prose is a PROPOSAL, never a free canon source (map-governs). The
        # resolver binds each mention to a known scene entity, mints one correctly-typed entity only
        # when genuinely novel, and DROPS voice/malformed/deixis-phantoms + person-in-object rows
        # BEFORE they reach the staging frame — so the misshapen graph is never created (vs the old
        # `p.ingest(prose)` that free-minted fragments/phantoms the promote-gate band-aids then chased).
        _resolve_cands = {e for (e, _a) in canon_table if isinstance(e, str) and ":" in e}
        if scene:
            _resolve_cands.add(scene)
        # #98 (Cx 415 #4): bind-before-mint must see past the current scene — a named inn
        # established two scenes ago must BIND its second mention, never mint a twin. Widen
        # the roster with every NAMED canon place/person (horizon-safe); ambiguity still
        # drops, so a bigger roster can only prevent duplicates, never force a bad bind.
        # CANON-FRAMED on purpose (Cx 433 blocker): unframed visible() would admit
        # plot:/session:/knows: name rows — private memory or plot topology must never
        # enter the canon bind path and get promoted into world truth.
        try:
            for _pfx in ("place:", "person:"):
                from construct.adapter import frame_facts as _ff2
                for _nr in _ff2(world, "canon", attribute="name", prefix=_pfx,
                                as_of=_h):
                    _resolve_cands.add(str(_nr.entity))
        except Exception:  # noqa: BLE001 — roster widening is enrichment, never a gate
            pass

        def _resolve_name_of(e: str) -> str:
            v = canon_table.get((e, "name"))
            if not isinstance(v, str):
                try:
                    v = live_reads.state(e, "name")
                except Exception:
                    v = None
            return v if isinstance(v, str) else ""
        try:
            with _phase(trace, "post_extract"):
                _raw = p.extract(prose, scene=scene, extract="lean",
                                 pov=arc.protagonist)  # READ-ONLY; "you" = the protagonist (PB 4c)
                # FRAME PARTITION — the FIRST step after extract (Cx 552: it must
                # precede reconstruct_names too, else a dropped knows:* row's subject
                # still spawns an unframed synthetic NAME row that stubs/promotes as
                # the dropped row's derivative). Policy + rationale: _partition_frames.
                _canon_items, _dropped_framed = _partition_frames(list(_raw))
                if _dropped_framed:
                    logger.info(
                        "narrator settle: dropped %d non-canon-framed row(s) "
                        "(knowledge-promotion gate not yet built): %s",
                        len(_dropped_framed), _dropped_framed[:5])
                    trace.dropped_cohorts.append(
                        f"settle_noncanon_frames ({len(_dropped_framed)})")
                # #98 live-probe finding: the lean extractor omits name rows — reconstruct
                # the cased surface form from the prose (the stub gate's only evidence);
                # synthetic names commit only WITH a stub, never onto bound entities.
                # Runs over the ACCEPTED copy only (Cx 552).
                from construct.resolve import reconstruct_names
                _canon_items = list(_canon_items) + reconstruct_names(
                    list(_canon_items), prose)
                # #98 (Cx 415 #2): the NARRATION channel — person leaves the free mint set;
                # place/person enter ONLY through the proper-name stub gate (minimal rows,
                # non-present).
                _resolved, _receipts = resolve_rows(
                    _canon_items, scene=_resolve_cands, protagonist=arc.protagonist,
                    name_of=_resolve_name_of, allow_mint=True,
                    mint_kinds=_NARRATION_MINT_KINDS,
                    stub_kinds=_NARRATION_STUB_KINDS)
                trace.resolver = (trace.resolver or []) + _receipts
                staged = _receipt_rows(p.ingest_structured(
                    _resolved, frame=_PROPOSED, classify="defer"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("render extraction failed; shipping prose, skipping commit: %s", exc)
            trace.dropped_cohorts.append(f"post_extract ({exc})")
            staged = []
        # the entities the narrator's prose touched (drop meta/assertion ids); read
        # their proposed-frame values (snapshot facts are fact-only — no meta noise)
        staged_entities = sorted({
            r["entity"] for r in staged
            if ":" in r["entity"] and not r["entity"].startswith(("a:", "attr:"))})
        proposed_vals = _table(_snap_or_empty(p, staged_entities, frame=_PROPOSED))

        # EPILOGUE-NO-CANON (Cx 189): on a TERMINAL / conclusion-curtain turn the narrator renders
        # FATE/SUMMARY prose ("walks back into the rain with his name cleared", "keeps his pride but not
        # his clean hands") — it must mint NOTHING into canon. Promoting it canonized descriptive ALIASES
        # onto the cast, which the next episode then surfaced as character NAMES ("With His Name Cleared").
        # The prose is still archived in session:main (the transcript below); any real consequence is
        # written BEFORE narration via the explicit conclusion/consequence paths, never mined back out of
        # curtain prose. So drop all promotion candidates on the epilogue turn.
        if trace.terminal or (trace.concluded and not endless):
            proposed_vals = {}

        protected_keys = arc_protected_keys(arc)  # the arc's load-bearing (hidden) facts
        # The objects the protagonist HOLDS at the play horizon (after this turn's deterministic
        # take/drop). Possession is HOST-owned: the narrator's prose extraction must never relocate
        # the player's inventory into furniture or a "pocket" pseudo-container (founder live cohesion
        # test, 2026-06-29: a held pencil was extracted `in obj:desk`/`obj:table`, a held token
        # `in obj:pocket` — stranding them off the player so the carry briefing lost them).
        try:
            _held_now = {h for h in p.contents(arc.protagonist, as_of=_h)
                         if str(h).startswith("obj:")}
        except Exception:
            _held_now = set()
        promote: list[dict] = []
        contradictions: list[tuple] = []
        quarantined: list[tuple] = []
        for (entity, attribute), newv in proposed_vals.items():
            # ENTITY AUTHORITY (verified-then-strip, Cx 313): the malformed / narrator-voice / pronoun-
            # deixis / person-in-object band-aids that USED to live here are GONE — the resolver
            # (`resolve_rows`, run at the read-only `extract` boundary before staging) drops/binds those
            # classes upstream, so they never reach `proposed_vals`. Live-proven on bodycase:
            # `trace.quarantined` was empty all 7 turns. The guards BELOW stay — they are NOT resolver-
            # subsumed: the held-object guard knows live inventory + same-turn drop licensing (which the
            # identity resolver does not), and the arc-key/contradiction gates are concealment/canon-diff
            # policy, a different layer.
            # POSSESSION IS HOST-OWNED: the narrator may not relocate a PLAYER-HELD object. A held
            # object's `in` changes ONLY via the deterministic take/drop steps; a narrator row that
            # moves it elsewhere (`obj:pencil in obj:desk`, `obj:token in obj:pocket`) is drift that
            # strands it off the player. Quarantine it unless the player licensed the move THIS turn
            # (a drop the deterministic step already committed → key in pre_keys). Keeps inventory on
            # the player across locations (founder live cohesion test, 2026-06-29).
            if (attribute == "in" and str(entity) in _held_now
                    and str(newv) != arc.protagonist and (entity, attribute) not in pre_keys
                    and entity != (trace.dropped or None)):
                quarantined.append((entity, attribute))
                continue
            key = (entity, attribute)
            established = canon_before.get(key, _ABSENT)
            # STRICT license for a PROTECTED arc fact (Cx 022 blocking #1): the mystery's
            # answer may enter canon AND the player frame ONLY if the player legitimately
            # surfaced it THIS turn — it is in their own action receipt (pre_keys) or
            # already in their knowledge frame (briefing_keys = the player-frame snapshot,
            # i.e. earned by prior play). Token matching (_licensed) is too loose here: a
            # narrator that merely RESTATES a hidden canon fact (SAME value) would otherwise
            # slip past the contradiction check and promote+mirror it into knows:<player>,
            # handing over the solution. So a protected key the player didn't earn this turn
            # is QUARANTINED — new OR same-value. A legitimately discovered arc fact is in
            # the player frame → licensed_strict → promotes normally (discovery still works).
            licensed_strict = (key in pre_keys or key in briefing_keys
                               or (entity, attribute, newv) in _reshape_license)
            # Promoted rows carry their narrator PROVENANCE (Cx 022 non-blocking): the
            # promote path is structured-ingest, which drops the `source` the staging
            # ingest stamped — re-stamp via `source_doc` so a promoted improv fact is
            # auditable as narrator-origin (vs player/author/canon-seed).
            if key in protected_keys:
                if licensed_strict:
                    promote.append({"entity": entity, "attribute": attribute,
                                    "value": newv, "source_doc": _NARRATOR_SOURCE})
                else:
                    quarantined.append(key)
                continue
            if established is not _ABSENT and established != newv and not licensed_strict:
                contradictions.append(key)  # narrator overwrote established truth
            else:
                promote.append({"entity": entity, "attribute": attribute,
                                "value": newv, "source_doc": _NARRATOR_SOURCE})
        # Fact-source v3 (§A, Cx 525): capture the RECEIPT of the promote ingest to
        # build the receipt-confirmed narrator batch for the next-turn generator read.
        # PB receipts carry entity/attribute but NOT value; the confirmed_batch() join
        # retains candidate values for confirmed (entity, attribute) keys so the
        # value-side spine-touch check in salient_moments() is satisfied.
        _promote_receipt_rows: list[dict] = []
        if promote:
            with _phase(trace, "promote"):
                _promote_receipt = p.ingest_structured(promote, frame="canon", classify="batch")
                _promote_receipt_rows = _receipt_rows(_promote_receipt)
                canon_table.update(_table(_snap_or_empty(p, snap_scope, as_of=_h)))
                _mirror_rows(p, promote, player_frame, canon_table, trace, as_of=_h)
        # Build the receipt-confirmed batch: promote candidates whose (entity, attribute)
        # appear in the receipt (failed ingests produce an empty receipt via _FailOpenIngest
        # — those candidates are uncommitted and must never enter the batch). Empty on
        # _FailOpenIngest or quiet turns. Capped at 60 rows (stable order: as committed).
        _confirmed, _dropped = confirmed_batch(promote, _promote_receipt_rows)
        if _dropped:
            logger.info(
                "narrator_promote batch capped: kept=%d dropped=%d (turn %d)",
                len(_confirmed), _dropped, turn)
        # Write the per-turn handoff row EVERY settle, OUTSIDE `if promote:` — an empty
        # list [] on quiet turns ensures the generator reads exactly turn n-1's row and
        # returns [] when it is absent or malformed (stale replay is structurally impossible).
        # Stored as a JSON literal in session:main; classify="rules" guarantees no model
        # call (deterministic write). The entity id carries an "event:" prefix, which PB's
        # guardrail classifies as EVENT — that is fine because the reader is a raw bounded
        # frame_facts read (not a folded state read), so EVENT vs STATE durability does not
        # affect retrieval. valid_from=turn_time(turn) keys it per-turn — Cx 525 amendment 2.
        try:
            p.ingest_structured([
                {"entity": f"event:turn_{turn}", "attribute": "narrator_promote",
                 "value": json.dumps([
                     {"entity": c["entity"], "attribute": c["attribute"], "value": c["value"]}
                     for c in _confirmed
                 ]),
                 "value_type": "literal", "valid_from": turn_time(turn)},
            ], frame=SESSION, classify="rules")
        except Exception:  # noqa: BLE001 — handoff row loss → false negative next turn, never stale
            logger.debug("narrator_promote handoff row write failed (turn %d)", turn, exc_info=True)
        trace.contradictions = sorted(contradictions)
        trace.quarantined = sorted(quarantined)

        leaked = [(it["entity"], it["attribute"]) for it in promote
                  if not _licensed(it["entity"], it["attribute"])]
        audit = []
        if leaked:
            audit.append(f"unlicensed:{leaked[:5]}")
        if contradictions:
            audit.append(f"contradiction:{sorted(contradictions)[:5]}")
        if quarantined:
            audit.append(f"momentous:{sorted(quarantined)[:5]}")
        trace.concealment_audit = "clean" if not audit else "FLAGGED: " + " ".join(audit)

        # The DEFERRED audit field — depends on the gate above (contradictions/quarantine),
        # so it lands with the finalizer, not the synchronous receipt. Lost-on-crash =
        # a debug field, never turn integrity (the synchronous receipt below owns that).
        p.ingest_structured([
            {"entity": f"event:turn_{turn}", "attribute": "concealment_audit",
             "value": trace.concealment_audit, "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # bookkeeping (audit) — no durability (K 077)

        # Append this beat to the rolling transcript (the narrator's short-term memory).
        # Beats past the verbatim window age out; once a BATCH has accumulated, fold
        # them into the durable NARRATIVE MEMORY via the memory cohort (Kernos-style
        # compaction at a boundary, reconciled in one call). Fail-open: a compaction
        # miss leaves the aged beats in place to retry next turn — never breaks the
        # turn. Stored literal so the classifier never mistypes the JSON blob.
        _recent.append({"turn": turn, "player": player_input[:400], "prose": prose[:1600]})
        if len(_recent) > _RECENT_TURNS + _COMPACT_BATCH:
            aged = _recent[: len(_recent) - _RECENT_TURNS]
            aged_text = "\n\n".join(
                (f"› You: {b['player']}\n" if b.get("player") else "") + (b.get("prose") or "")
                for b in aged)
            try:
                with _phase(trace, "compact_memory"):
                    updated = cohorts.compact_memory(provider, narrative_memory, aged_text)
                p.ingest_structured([
                    {"entity": _MEMORY, "attribute": "text", "value": updated["memory"][:6000],
                     "value_type": "literal", "valid_from": turn_time(turn)},
                ], frame=SESSION, classify="batch")  # narrative memory literal — no durability
                _recent = _recent[-_RECENT_TURNS:]  # aged beats now live in memory
                trace.cohort_calls.append("compact_memory:main")
            except Exception as exc:  # noqa: BLE001 — never break the turn on memory
                logger.warning("narrative-memory compaction failed: %s", exc)
                trace.dropped_cohorts.append(f"compact_memory ({exc})")
                _recent = _recent[-(_RECENT_TURNS + _COMPACT_BATCH):]  # cap unbounded growth
        p.ingest_structured([
            {"entity": _TRANSCRIPT, "attribute": "recent",
             "value": json.dumps(_recent), "value_type": "literal",
             "valid_from": turn_time(turn)},
        ], frame=SESSION, classify="batch")  # transcript literal — no durability

        # Advance diegetic time POST-RENDER for the normal case (richer estimate — it can use the
        # narration), UNLESS a time-deadline arc already advanced it early (Cx 173 #3) so the deadline
        # could cross same-turn. Best-effort; never blocks or breaks a turn.
        if _clock is not None and not _time_committed:
            _advance_diegetic_time(world, _clock, player_input, trace, provider, narration=prose)

        # ---- WORLD-MOVES-WITHOUT-YOU (#84, Cx 395/396) --------------------------------
        # LAST-SEEN MARKERS first (constraint 2): a durable session-frame minute-stamp for
        # each NPC actually PRESENT to the player this turn — the tick's elapsed floor reads
        # THIS, never transcript inference. Then the tick itself (after the time advance, so
        # the floor consumes the updated clock; before the mechanics log). Both fail-open.
        _mins_now: float | None = None
        try:
            from construct.clock import read_clock as _read_clock
            _mins_now = float(_read_clock(world).minutes)
        except Exception:  # noqa: BLE001 — clockless worlds simply never tick
            _mins_now = None
        if _mins_now is not None and npcs:
            try:
                p.ingest_structured([
                    {"entity": _n, "attribute": "last_seen_min", "value": _mins_now,
                     "valid_from": turn_time(turn)} for _n in npcs
                ], frame=SESSION, classify="batch")
            except Exception:  # noqa: BLE001
                logger.debug("last-seen markers skipped", exc_info=True)
        if not _grounding_runway:
            _world_tick(world, p, arc, trace, provider, turn, cast=cast, npcs=npcs,
                        entry_scene=_entry_scene, scene=scene, live_reads=live_reads,
                        minutes_now=_mins_now)

        _write_mechanics_log(arc, turn, player_input, prose, trace)

    # TURN-INTEGRITY RECEIPT + ARCHIVE — written SYNCHRONOUSLY, before the reply ships, so a
    # crash in the deferred-settle window can never leave a delivered turn the world log can't
    # reconstruct (Cx 069/266 durability requirement). This IS the spec's "durable pending-
    # finalization record (prose + turn context) before sendback": cheap literal/batch writes,
    # NO model call. It owns turn integrity — `event:turn_N.kind` is what next_turn_number reads
    # (no number collision / no phantom turn) and `arch:turn_N` preserves what was said/shown.
    # Everything LM-bearing (extract→promote, compaction, time advance) stays in `_settle`,
    # where a crash loses only future-feeding bookkeeping for one turn — never the turn itself.
    p.ingest_structured([
        {"entity": f"event:turn_{turn}", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(turn)},
        {"entity": f"event:turn_{turn}", "attribute": "pacing", "value": trace.pacing,
         "valid_from": turn_time(turn)},
        {"entity": f"event:turn_{turn}", "attribute": "player_boundary",
         "value": trace.player_boundary, "valid_from": turn_time(turn)},
        # The append-only ARCHIVE (Kernos Ledger discipline): the delivered beat preserved
        # lossless on a plain `arch:turn_N` entity (retrievable by `state()`), so the
        # compacted memory stays RECOVERABLE against it. Host frame — narrative, never canon.
        {"entity": f"arch:turn_{turn}", "attribute": "player_said",
         "value": player_input[:600], "valid_from": turn_time(turn)},
        {"entity": f"arch:turn_{turn}", "attribute": "prose",
         "value": prose[:2400], "valid_from": turn_time(turn)},
    ], frame=SESSION, classify="rules")  # bookkeeping ledger — RULES (no LM call) keeps this
    # synchronous pre-send write off the model path (Cx 268): `batch` would send the arch:* rows
    # to the durability model, putting a model call back before the reply ships. Kernos 077:
    # operational ledger rows skip durability classification entirely.

    return TurnResult(prose=prose, trace=trace, settle=_settle)


def _write_mechanics_log(arc: Arc, turn: int, player_input: str, prose: str,
                         trace: "TurnTrace") -> None:
    """Per-turn MECHANICS LOG (founder: read the machinery, not just the fiction — anticipate how
    each shape SHOULD behave). Env-gated by CONSTRUCT_MECHANICS_LOG (a path, or "1" → logs/
    mechanics-<arc>.md). Dumps, per turn: the classify→tick→arc→governance signals, which cohorts
    fired, and — the key — the FULL assembled BRIEFING (the directives that produced the prose) +
    the prose itself, so the mechanics→prose link is legible. OFF by default; never sinks a turn."""
    import os
    dest = os.environ.get("CONSTRUCT_MECHANICS_LOG")
    if not dest:
        return
    try:
        from pathlib import Path
        slug = arc.arc_id.replace(":", "_")
        path = (Path("logs") / f"mechanics-{slug}.md") if dest in ("1", "true", "yes") else Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        d = trace.to_dict() if hasattr(trace, "to_dict") else {}
        def _g(k, default=""):
            return d.get(k, getattr(trace, k, default))
        lines = [
            f"\n\n{'='*78}\n## Turn {turn} — {player_input!r}",
            f"- classify: kind={_g('classified')}  pacing={_g('pacing')}  "
            f"resolution_tier={_g('adjudication')}",
            f"- delivery: learned={_g('learned_clues') or '-'}  discovered={_g('discovered') or '-'}",
            f"- world tick: clocks_fired={_g('clocks_fired') or '-'}  beats_achieved="
            f"{_g('beats_achieved') or '-'}  beats_closed={_g('beats_closed') or '-'}  "
            f"events_fired={_g('events_fired') or '-'}  reveals={_g('reveals') or '-'}",
            f"- arc: act={_g('act')}  lifecycle={_g('lifecycle')}  concluded={_g('concluded')}  "
            f"conclusion={_g('conclusion_shape') or '-'}  terminal={_g('terminal')}  "
            f"outcome={_g('outcome') or '-'}  bounced={_g('commitment_bounced')}",
            f"- governance: weave={_g('weave_decision') or '-'}/{_g('weave_card') or '-'}  "
            f"adapted={_g('adapted') or '-'}  fallout={_g('arc_fallout') or '-'}  "
            f"generated={_g('generated') or '-'}",
            f"- cohorts fired: {_g('cohort_calls') or '-'}",
            f"- dropped: {_g('dropped_cohorts') or '-'}",
            f"- time: {_g('time_now')} (+{_g('time_advanced')}m)  "
            f"pins={_g('pins') or '-'}  quarantined={_g('quarantined') or '-'}",
            f"- timings(s): {_g('timings') or '-'}",
            "\n### BRIEFING (the directives that drove the prose)\n" + (trace.briefing or "(none)"),
            "\n### PROSE\n" + (prose or "(empty)"),
        ]
        with path.open("a") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:  # a debug log must NEVER affect a turn
        logger.exception("mechanics log write failed")


run_turn_sync = run_turn  # the v0 loop is synchronous end to end
