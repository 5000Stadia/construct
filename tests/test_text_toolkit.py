"""Property test for the text toolkit (`construct/text.py`, audit 2026-10 tier 2 #3).

Every tokenizer, slug helper, name-humanizing closure and inline id-humanizing idiom the
refactor pointed at `construct.text` is checked against its pre-refactor copy. The OLD
copies are kept VERBATIM from `polish-audit` (1f47281):

- whole functions as source text, executed in a copy of their own module's namespace, so
  they see the same constants and call each other by their original names (the only
  additions are the `from __future__ import annotations` and `import re` lines every one
  of those modules had at its top);
- inline snippets and closures as small functions with the old lines pasted in, beside a
  twin holding the new lines.

Each OLD/NEW pair runs on the same randomized inputs (ASCII and Unicode letters, case
changes, every ASCII punctuation mark, typographic quotes and dashes, Unicode whitespace,
combining marks, digits from other scripts, entity ids with odd colons, and fake reads that
return non-strings or raise) and must agree exactly: the same value (list order included),
or the same exception type.
"""

from __future__ import annotations

import random
import re
import string
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

import pytest

import construct.arc.concealment as concealment
import construct.arc.executor as executor
import construct.arc.generator as generator
import construct.cast as cast
import construct.clock as clock
import construct.game as game
import construct.growth as growth
import construct.imagery as imagery
import construct.journal as journal
import construct.laws as laws
import construct.play_styles as play_styles
import construct.remembrancer as remembrancer
import construct.reshape as reshape
import construct.resolve as resolve
import construct.transport_core as transport_core
import construct.turnloop as tl
from construct import text as T

#: Random inputs per OLD/NEW pair (heavier pairs set their own `n`).
N = 2000


def _old(module: Any, source: str) -> dict[str, Any]:
    """Run verbatim OLD source in a copy of `module`'s namespace; return that namespace."""
    ns = dict(vars(module))
    code = "from __future__ import annotations\nimport re\n" + source
    exec(compile(code, f"<old {module.__name__}>", "exec"), ns)
    return ns


# ---------------------------------------------------------------------------
# OLD copies: whole functions, verbatim from polish-audit 1f47281
# ---------------------------------------------------------------------------

OLD_TURNLOOP = _old(tl, r'''
def _secret_tokens(arc: Arc, reads: Any, public: set[str]) -> set[str]:
    """Distinctive vocabulary of the arc's HIDDEN answers — tokens drawn from each
    protected attribute and its canon value — MINUS tokens that are public names in
    play (a public NPC is not a secret just because they turn out to be the culprit;
    the player must be free to ask about them). Used to spot a question fishing
    directly for the solution (Cx 022 blocking #2) so the narrator deflects rather
    than improvises an answer that could brush the secret."""
    toks: set[str] = set()
    for (e, a) in arc_protected_keys(arc, reads):
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
    for (e, a) in arc_protected_keys(arc, reads):
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


def _concealed_move_vocab(arc: Arc, reads: Any) -> set[str]:
    """The MOVE-mint concealment vocabulary (see _move_touches_secret): the
    protected keys' ENTITY-REFERENCE answers only — each referenced entity's
    distinctive slug/name tokens, never descriptive prose. Shared by the
    move-permanence mint guard and the WORLD-GROWTH leaks predicate (the
    host applies the hidden words; the model never sees them)."""
    secret: set[str] = set()
    for (e, a) in arc_protected_keys(arc, reads):
        try:
            val = reads.state(e, a)
        except Exception:
            val = None
        # only an ENTITY-REFERENCE value names an answer (person:/place:/obj:/…); skip prose.
        if isinstance(val, str) and re.match(r"^[a-z_]+:[a-z0-9_]+$", val):
            secret |= _secret_word_set(val.split(":", 1)[-1])
            try:
                nm = reads.state(val, "name")
            except Exception:
                nm = None
            if isinstance(nm, str):
                secret |= _secret_word_set(nm)
    return secret


def _growth_concealed_vocab(arc: Arc, reads: Any) -> set[str]:
    """The FULL growth concealment vocabulary (cr wiring blocker 5): the
    gate contract requires the arc's protected/concealed vocabulary WHOLE
    — key/attribute tokens ("culprit"), every protected entity's slug and
    name/alias/title, protected VALUES, and each referenced answer
    entity's own names. Over-breadth here declines a retryable proposal —
    the correct cost; leaking the hidden answer into permanent canon is
    the unpayable one. EVERY authority read is fail-closed: an exception
    raises GrowthVocabUnavailable (technical decline upstream), never an
    empty contribution."""
    from construct.arc.executor import concealed_tokens
    secret: set[str] = set()
    try:
        keys = arc_protected_keys(arc, reads)
    except Exception as exc:  # the enumeration itself is an authority read
        raise GrowthVocabUnavailable(f"protected-key enumeration: {exc}") \
            from exc

    def _identity_words(entity: str) -> set[str]:
        """EVERY durable identity value the entity has registered UP TO
        THE PLAY HORIZON — the horizon-bound assertion log via
        reads.frame_rows, never a bare head scan (cr r6: a superseded
        alias still names the hidden answer, but a FUTURE-aftermath alias
        must not shrink present growth — as-of coherence is load-bearing
        in both directions)."""
        out: set[str] = set()
        try:
            for f in reads.frame_rows("canon", entity=entity):
                if f.attribute in ("name", "alias", "aliases", "title") \
                        and isinstance(f.value, str):
                    out |= _secret_word_set(f.value)
        except Exception as exc:
            raise GrowthVocabUnavailable(
                f"{entity} identity log: {exc}") from exc
        return out

    for (e, a) in keys:
        secret |= _secret_word_set(a)
        secret |= _secret_word_set(e.split(":")[-1])
        secret |= _identity_words(e)
        try:
            val = reads.state(e, a)
        except Exception as exc:
            raise GrowthVocabUnavailable(f"{e}.{a}: {exc}") from exc
        if isinstance(val, str):
            secret |= _secret_word_set(val)     # the protected VALUE itself
            if re.match(r"^[a-z_]+:[a-z0-9_]+$", val):
                # the referenced ANSWER's whole identity — slug + every
                # durable name/alias/title it has ever carried
                secret |= _secret_word_set(val.split(":", 1)[-1])
                secret |= _identity_words(val)
    secret |= concealed_tokens(keys)              # entity/attr distinctives
    return secret


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
    secret = _concealed_move_vocab(arc, reads)
    if not secret:
        return False
    return bool(secret & _secret_word_set(moves_to))


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


def _is_scrutiny(text_low: str) -> bool:
    """Is the player CLOSELY inspecting a physical thing this turn (the EXAMINE analogue of
    `_is_pressing`)? True when an examine/inspect/search-class verb is present, OR a close-
    inspection adverb ('look closely/carefully at …'). A bare 'look around'/'notice' is a glance,
    not scrutiny. Gates `scrutiny` object-clues; a glance earns only `examined`-level clues."""
    toks = set(text_low.replace(",", " ").replace(".", " ").replace("?", " ").split())
    if toks & _EXAMINE_VERBS:
        return True
    return any(adv in text_low for adv in _SCRUTINY_ADVERBS)


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
''')

OLD_CONCEALMENT = _old(concealment, r'''
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
''')

OLD_EXECUTOR = _old(executor, r'''
def _human(entity: str) -> str:
    """A readable name for an entity id, for the narrator directive (not stored). A `person:` slug
    is a proper NAME → Title-Case it (founder blind test: 'clara_vale' addressed as lowercase 'clara
    vale'); obj/place stay lowercase so prose reads naturally ('you lift the brass token')."""
    local = entity.split(":", 1)[-1].replace("_", " ")
    return local.title() if str(entity).startswith("person:") else local
''')

OLD_CAST = _old(cast, r'''
def _identity_tokens(text: str) -> set[str]:
    import re as _re
    return {t for t in _re.split(r"[^a-z0-9]+", str(text).lower())
            if len(t) > 3 and t not in _IDENTITY_STOP}
''')

OLD_CLOCK = _old(clock, r'''
def deterministic_elapsed(action: str, *, moved: bool = False) -> dict | None:
    """A cheap, DETERMINISTIC diegetic-time delta for ordinary turns (DIEGETIC-TIME.md /
    TURN-LATENCY Lever C, Cx 077): most turns advance time predictably by their ACTION kind, so
    the per-turn `estimate_elapsed` MODEL call is skipped. Returns an estimate dict (the same
    `{advance_minutes}` shape `delta_from_estimate` consumes) for ordinary actions, or **None**
    when the input carries explicit TEMPORAL language (a wait/jump/rest/montage) that needs the
    model to resolve a phase- or day-boundary. Best-effort + monotonic — time only goes forward."""
    low = action.lower()
    if any(m in low for m in _TEMPORAL_MARKERS):
        return None  # explicit time language → defer to the model estimate (phase/day jump)
    toks = set(low.replace(",", " ").replace(".", " ").replace("?", " ").split())
    if toks & _EXAMINE_VERBS:
        return {"advance_minutes": 12}      # close inspection / searching
    if moved or (toks & _MOVE_VERBS):
        return {"advance_minutes": 6}       # local movement within the scene/site
    if toks & _TAKE_VERBS:
        return {"advance_minutes": 2}       # take / use a simple object
    if toks & _GLANCE_VERBS:
        return {"advance_minutes": 1}       # a look / brief beat
    return {"advance_minutes": 3}           # ordinary action / questioning a person
''')

OLD_PLAY_STYLES = _old(play_styles, r'''
def _tokens(text: str) -> set[str]:
    import re
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) >= 3}


def match(label: str) -> str | None:
    """Resolve a FREE label ('heist', 'political intrigue', 'whodunnit') to the
    closest taxonomy key — exact key/slug first, else the best token overlap with a
    card's name (≥ half the label's words must land). None if nothing fits (→ free
    improvised). Lets a cohort/agent name a type plainly without knowing the 155
    keys."""
    k = _norm(label)
    if k in STYLE_CARDS:
        return k
    slug = "_".join(_tokens(label))
    if slug in STYLE_CARDS:
        return slug
    want = _tokens(label)
    if not want:
        return None
    best, best_score = None, 0.0
    for key, c in STYLE_CARDS.items():
        have = _tokens(c["name"])
        overlap = len(want & have)
        if not overlap:
            continue
        score = overlap / len(want)
        if score > best_score:
            best, best_score = key, score
    return best if best_score >= 0.5 else None
''')

OLD_RESOLVE = _old(resolve, r'''
def _is_place_like(kind_hint: str, eid: str) -> bool:
    """Whether a free-text `obj:` is really a mistyped PLACE — judged by its declared KIND value
    hitting `_PLACE_LIKE_KINDS` (Cx 308). Deliberately reads ONLY the kind, NOT the id-stem: a stem
    token would wrongly flag `obj:office_key`/`obj:street_lamp` (objects with a place word as a
    modifier). The extractor's `kind` is the reliable type signal — `obj:street kind street` is the
    mistyped place; `obj:office_key kind key` is a real object."""
    toks = set(re.split(r"[ _\-/:]+", (kind_hint or "").lower()))
    return bool(toks & _PLACE_LIKE_KINDS)


def reconstruct_names(rows: list[dict], prose: str) -> list[dict]:
    """#98 live-probe finding (letter 442): the lean extractor emits `kind` rows with
    lowercased slug ids but NO `name` rows — the cased surface form ("The Hart and
    Bell"), which is the stub gate's ONLY evidence, exists only in the prose the host
    already holds. For each `place:`/`person:` subject lacking a name row, find the
    id-stem's span in the prose (case-insensitive) and inject a SYNTHETIC name row
    carrying the span verbatim — `is_proper_named` then judges the real casing.
    Deterministic, fail-closed (no span → no name → no stub). Synthetic rows are
    marked so `resolve_rows` commits them ONLY on a stub mint — a bound entity's
    canon name is never re-asserted from prose casing."""
    if not prose:
        return []
    have_names = {r["entity"] for r in rows if r.get("attribute") == "name"}
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        eid = r.get("entity")
        if (not isinstance(eid, str) or eid in seen or eid in have_names
                or not eid.startswith(("place:", "person:"))):
            continue
        seen.add(eid)
        toks = [t for t in _local(eid).split("_") if t]
        if not toks:
            continue
        pat = r"\b" + r"[\s\-'’]+".join(re.escape(t) for t in toks) + r"\b"
        m = re.search(pat, prose, re.IGNORECASE)
        if m:
            out.append({"entity": eid, "attribute": "name", "value": m.group(0),
                        "_synthetic_name": True})
    return out


def _local(eid: Any) -> str:
    if not isinstance(eid, str):
        return ""
    return eid.split(":", 1)[1] if ":" in eid else eid


def is_voice(eid: Any) -> bool:
    """A non-diegetic narration-voice phantom (`person:narrator`, `person:unknown_speaker`). Matched
    whole-token so a legit `person:speakman` is untouched (was the host `_is_narrator_phantom` guard)."""
    if not isinstance(eid, str):
        return False
    toks = set(t for t in re.split(r"[ _\-/:]+", eid.lower()) if t)
    return bool(toks & _VOICE_TOKENS)
''')

OLD_LAWS = _old(laws, r'''
def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "law"
''')

OLD_REMEMBRANCER = _old(remembrancer, r'''
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s[:40] or "unnamed"
''')

OLD_IMAGERY = _old(imagery, r'''
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "scene"
''')

OLD_RESHAPE = _old(reshape, r'''
def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c == "_") else "_" for c in (text or "").lower()]
    return "".join(keep).strip("_") or "reshape"
''')

OLD_GROWTH = _old(growth, r'''
def _slugify(name: str) -> str:
    return _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
''')

OLD_GENERATOR = _old(generator, r'''
def _id_slug(s: str) -> str:
    """Entity-id-safe local part: PB's identity gate (rightly) rejects ids with
    embedded colons/odd characters as malformed — a reason like
    'lint:1-referents' or a source like 'event:arc_terminal_x' must be slugged
    before riding an id. The RAW string still travels as the row VALUE."""
    import re
    return re.sub(r"[^a-z0-9_]+", "_", (s or "").lower()).strip("_") or "x"
''')

OLD_GAME = _old(game, r'''
def _safe_player_id(player_id: str) -> str:
    """Filesystem-safe slot segment; never empty."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", player_id).strip("_")
    return safe or "player"


def _slug(s: str) -> str:
    """Conform an id segment to the frozen porcelain id grammar
    (^[a-z][a-z0-9_]*:[a-z0-9_:]+$) — model proposals love hyphens."""
    return re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_")


def _hidden_terms(world: Any, proposal: dict) -> set[str]:
    """The tokens a player-facing goal must NOT contain — the ANSWERS the arc
    keeps hidden, NOT the premise. A genre-true aim names the world's stakes
    ("lift the blight", "toss the ring into the fire", "see the lost child
    home") — those reference PREMISE entities (the problem, the setting), which
    the player already knows from the intro and which the goal SHOULD evoke. The
    spoiler is the SOLUTION: what the player must DISCOVER. So the forbidden set
    is only the `player_learns` beat VALUES (the culprit, the cure, the secret)
    plus a `player_learns` failure value — never the whole world vocabulary
    (that over-broad set is what forced every goal back to boilerplate).
    Short tokens (<3 chars) are dropped as noise. Fail-closed on the answers."""
    terms: set[str] = set()

    def _add_entity(raw: str) -> None:
        # ONLY a discovered ENTITY identity is a spoiler (the 'Dr. Archibald'
        # the player must name). A value that is an entity-id reference
        # (person:/obj:/fact:…) contributes its local-part tokens; a plain
        # literal value or a premise noun does NOT — naming the dragon, the
        # blight, the winter is the AIM the player asked for, never a leak.
        raw = str(raw)
        if ":" not in raw:
            return
        for tok in re.split(r"[^a-z0-9]+", raw.split(":", 1)[-1].lower()):
            if len(tok) >= 3:
                terms.add(tok)

    for b in proposal.get("beats", []):
        if b.get("kind") == "player_learns":
            _add_entity(b.get("value", ""))
    fw = proposal.get("failure_when") or {}
    if fw.get("kind") == "player_learns":
        _add_entity(fw.get("value", ""))
    return terms


def _goal_statement_safe(goal: str, forbidden: set[str]) -> bool:
    """True iff `goal` is non-empty and shares no whole word with the
    forbidden set — a structural token check, not a lint we hope holds."""
    if not goal or not goal.strip():
        return False
    words = {w for w in re.split(r"[^a-z0-9]+", goal.lower()) if w}
    return words.isdisjoint(forbidden)


def _fallback_protagonist(world: Any, located: list[str], play_as: str) -> str | None:
    """Deterministic last-resort binding (Cx 160 #2/#4) when the author stays
    stubborn: pick a LOCATED person — the durable map identity. `play_as` is only a
    TIE-BREAKER among located candidates (token overlap with id/name), never a
    license to fabricate a location for a bad role id. None if nothing is located."""
    if not located:
        return None
    want = {w for w in play_as.lower().replace(":", " ").split() if len(w) > 3}
    if want:
        def _score(pid: str) -> int:
            name = str(world.porcelain.state(pid, "name") or "")
            toks = set((pid + " " + name).lower().replace(":", " ").split())
            return len(want & toks)
        best = max(located, key=_score)
        if _score(best) > 0:
            return best
    return sorted(located)[0]  # stable: the first located person


def _tension_axis(arc) -> str:
    """A short 'X against Y' read of an arc's drive axis, or '' if unavailable."""
    try:
        _e, strong, weak = arc.shape.tension
        return (f"{strong.split(':')[-1].replace('_', ' ')} against "
                f"{weak.split(':')[-1].replace('_', ' ')}")
    except Exception:
        return ""
''')

OLD_TRANSPORT = _old(transport_core, r'''
def _pick(answer: str, choices: dict[str, tuple[str, ...]]) -> str | None:
    """Which ONE of `choices` did the answer pick? Matches the exact choice words as
    WHOLE WORDS (never substrings: "yes" is not "wipe", "new" is not "redo", and a
    word inside another word never counts). Returns None when no choice matches or
    when two different choices both do — the caller re-asks and keeps the prompt
    armed, so a destructive path never runs on an ambiguous answer."""
    words = set(re.findall(r"[a-z0-9]+", (answer or "").lower()))
    hit = {name for name, keys in choices.items() if words & set(keys)}
    return next(iter(hit)) if len(hit) == 1 else None


def _safe(s: str) -> str:
    """Filesystem-safe scenario-name segment; never empty."""
    import re
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s or "").strip("_") or "x"
''')

OLD_JOURNAL = _old(journal, r'''
def _humanize(entity_id: str) -> str:
    return entity_id.split(":", 1)[-1].replace("_", " ").title()
''')


# ---------------------------------------------------------------------------
# OLD/NEW inline snippets and closures (old lines verbatim; new lines as committed)
# ---------------------------------------------------------------------------

# turnloop._growth_attempt._disp
def old_growth_disp(live_reads, eid):
    try:
        v = live_reads.state(eid, "name")
    except Exception:
        v = None
    return v if isinstance(v, str) and v else \
        eid.split(":", 1)[-1].replace("_", " ")


def new_growth_disp(live_reads, eid):
    return T.name_or_humanized_id(live_reads, eid)


# turnloop._world_tick: the destination roster's (place, label) pair
def old_tick_place(_pid, _nm):
    return (_pid, str(_nm) if _nm
            else _pid.split(":", 1)[-1].replace("_", " "))


def new_tick_place(_pid, _nm):
    return (_pid, str(_nm) if _nm else T.humanize_id(_pid))


# turnloop._absence_beat: `_swhere` and the `_display` closure (the same rule)
def old_absence_where(live_reads, staged_scene):
    try:
        _sname = str(live_reads.state(staged_scene, "name") or "")
    except Exception:  # noqa: BLE001
        _sname = ""
    _swhere = _sname or staged_scene.split(":", 1)[-1].replace("_", " ")
    return _swhere


def old_absence_display(live_reads, pid):
    try:
        nm = str(live_reads.state(pid, "name") or "")
    except Exception:  # noqa: BLE001
        nm = ""
    return nm or pid.split(":", 1)[-1].replace("_", " ")


def new_absence_display(live_reads, pid):
    return T.name_text_or_humanized_id(live_reads, pid)


# turnloop._relocate_beat: the holder's description
def old_holder_desc(_hname, carrier_node):
    _hdesc = str(_hname or getattr(carrier_node, "surface_role", "")
                 or getattr(carrier_node, "shape_role", "")
                 or carrier_node.node_id.split(":", 1)[-1].replace("_", " "))
    return _hdesc


def new_holder_desc(_hname, carrier_node):
    _hdesc = str(_hname or getattr(carrier_node, "surface_role", "")
                 or getattr(carrier_node, "shape_role", "")
                 or T.humanize_id(carrier_node.node_id))
    return _hdesc


# turnloop._repair_beat: the condition entity's name, and a live holder's line fallback
def old_repair_entity(live_reads, _ent):
    try:
        _en = str(live_reads.state(_ent, "name")
                  or _ent.split(":", 1)[-1].replace("_", " "))
    except Exception:  # noqa: BLE001
        _en = _ent.split(":", 1)[-1].replace("_", " ")
    return _en


def new_repair_entity(live_reads, _ent):
    try:
        _en = str(live_reads.state(_ent, "name") or T.humanize_id(_ent))
    except Exception:  # noqa: BLE001
        _en = T.humanize_id(_ent)
    return _en


def old_repair_holder(live_reads, _h):
    try:
        _hn = str(live_reads.state(_h, "name")
                  or _h.split(":", 1)[-1].replace("_", " "))
        return _hn
    except Exception:  # noqa: BLE001 — one thread line, best-effort
        return _h.split(":", 1)[-1].replace("_", " ")


def new_repair_holder(live_reads, _h):
    try:
        _hn = str(live_reads.state(_h, "name") or T.humanize_id(_h))
        return _hn
    except Exception:  # noqa: BLE001 — one thread line, best-effort
        return T.humanize_id(_h)


# turnloop.run_turn: the classify actor descriptor
def old_actor(live_reads, arc):
    actor = ""
    try:
        proto = arc.protagonist
        bits = [live_reads.state(proto, a) for a in ("role", "kind", "background")]
        actor = "; ".join(b for b in bits if isinstance(b, str) and b) \
            or proto.split(":")[-1].replace("_", " ")
    except Exception:
        actor = arc.protagonist.split(":")[-1].replace("_", " ")
    return actor


def new_actor(live_reads, arc):
    actor = ""
    try:
        proto = arc.protagonist
        bits = [live_reads.state(proto, a) for a in ("role", "kind", "background")]
        actor = "; ".join(b for b in bits if isinstance(b, str) and b) \
            or T.humanize_id_last(proto)
    except Exception:
        actor = T.humanize_id_last(arc.protagonist)
    return actor


# turnloop.run_turn: an NPC classify candidate's descriptor
def old_npc_desc(_nm, _pid):
    _desc = str(_nm) if _nm else _pid.split(":", 1)[-1].replace("_", " ").title()
    return _desc


def new_npc_desc(_nm, _pid):
    _desc = str(_nm) if _nm else T.humanize_id_title(_pid)
    return _desc


# turnloop.run_turn: `_pin_name`, `_name_of`, `_live_name` (three identical closures)
def old_pin_name(live_reads, e):
    try:
        v = live_reads.state(e, "name")
    except Exception:
        v = None
    return v if isinstance(v, str) else ""


def old_name_of(live_reads, e):
    try:
        v = live_reads.state(e, "name")
    except Exception:
        return ""
    return v if isinstance(v, str) else ""


def old_live_name(live_reads, e):
    try:
        v = live_reads.state(e, "name")
    except Exception:
        v = None
    return v if isinstance(v, str) else ""


# briefing.build_briefing._id_attr (the same rule over any attribute of the protagonist)
def old_id_attr(live_reads, arc, a):
    try:
        v = live_reads.state(arc.protagonist, a)
    except Exception:
        v = None
    return str(v) if isinstance(v, str) else ""


def new_id_attr(live_reads, arc, a):
    return T.read_str(live_reads, arc.protagonist, a)


# turnloop.run_turn: the deliberation key and the deictic probe
def old_dest_key(dest_id, label):
    _dest_key = dest_id or re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    return _dest_key


def new_dest_key(dest_id, label):
    _dest_key = dest_id or T.slugify(str(label))
    return _dest_key


def old_slug_probe(moves_to):
    _slug_probe = re.sub(r"[^a-z0-9]+", "_",
                         str(moves_to).lower()).strip("_")
    return _slug_probe


def new_slug_probe(moves_to):
    _slug_probe = T.slugify(str(moves_to))
    return _slug_probe


# turnloop.run_turn: a roster place's label
def old_roster_label(_bits, _pid):
    _label = " — ".join(_bits) or _pid.split(":", 1)[-1] \
        .replace("_", " ")
    return _label


def new_roster_label(_bits, _pid):
    _label = " — ".join(_bits) or T.humanize_id(_pid)
    return _label


# turnloop.run_turn: `_npc_name` and `_resolve_name_of` (two identical closures)
def old_npc_name(live_reads, canon_table, e):
    def _npc_name(e: str, _ct=canon_table) -> str:
        v = _ct.get((e, "name"))
        if not isinstance(v, str):
            try:
                v = live_reads.state(e, "name")
            except Exception:
                v = None
        return v if isinstance(v, str) else ""
    return _npc_name(e)


def old_resolve_name_of(live_reads, canon_table, e):
    v = canon_table.get((e, "name"))
    if not isinstance(v, str):
        try:
            v = live_reads.state(e, "name")
        except Exception:
            v = None
    return v if isinstance(v, str) else ""


def new_table_or_read_name(live_reads, canon_table, e):
    return T.table_or_read_name(canon_table, live_reads, e)


# turnloop.run_turn: the vocative holder's name
def old_voc_name(canon_table, _vh):
    _voc_name = str(canon_table.get((_vh, "name")) or
                    _vh.split(":", 1)[-1].replace("_", " ").title())
    return _voc_name


def new_voc_name(canon_table, _vh):
    _voc_name = str(canon_table.get((_vh, "name")) or T.humanize_id_title(_vh))
    return _voc_name


# turnloop.run_turn._disp (scene lines) and session._establishing_anchors.disp
def old_scene_disp(names, x):
    s = str(x)
    if s in names:
        return names[s]
    if ":" in s and s.split(":", 1)[0] in ("person", "place", "obj", "fact", "event"):
        local = s.split(":", 1)[-1].replace("_", " ")
        return local.title() if s.startswith("person:") else local  # person slug = a proper name
    return s


def new_scene_disp(names, x):
    s = str(x)
    if s in names:
        return names[s]
    return T.human_name_typed_id(s)  # person slug = a proper name


def old_anchor_disp(names, x):
    s = str(x)
    if s in names:
        return names[s]
    if ":" in s and s.split(":", 1)[0] in ("person", "place", "obj", "fact", "event"):
        return s.split(":", 1)[-1].replace("_", " ")
    return s


def new_anchor_disp(names, x):
    s = str(x)
    if s in names:
        return names[s]
    return T.humanize_typed_id(s)


# turnloop.run_turn: the clarification gate's staging (scene name, who is present)
def old_stage_here_who(canon_table, scene, npcs):
    _here = str(canon_table.get((scene, "name")) or
                (scene or "").split(":")[-1].replace("_", " "))
    _who = ", ".join(
        str(canon_table.get((n, "name")) or n.split(":")[-1].replace("_", " "))
        for n in npcs) if npcs else ""
    return _here, _who


def new_stage_here_who(canon_table, scene, npcs):
    _here = str(canon_table.get((scene, "name")) or T.humanize_id_last(scene or ""))
    _who = ", ".join(
        str(canon_table.get((n, "name")) or T.humanize_id_last(n))
        for n in npcs) if npcs else ""
    return _here, _who


# turnloop.run_turn._settle: the license tokens and the name-token license
def old_license(briefing, player_input, entity):
    license_tokens = set(
        f"{briefing}\n{player_input}".lower()
        .replace("’", "").replace("'", "")
        .replace(",", " ").replace(".", " ").replace(";", " ").replace(":", " ")
        .split())
    name_tokens = entity.split(":", 1)[-1].replace("-", "_").split("_")
    return license_tokens, all(tok in license_tokens for tok in name_tokens if tok)


def new_license(briefing, player_input, entity):
    license_tokens = set(T.split_words(f"{briefing}\n{player_input}",
                                       seps=",.;:", drop="’'"))
    return license_tokens, all(tok in license_tokens
                               for tok in T.id_stem_parts(entity, hyphens=True))


# turnloop._mint_held_object: the words and the id slug
def old_mint_slug(description):
    words = (description or "").lower().split()
    while words and words[0] in {"my", "the", "a", "an", "your", "his", "her",
                                 "their", "its", "some"}:
        words.pop(0)
    slug = "".join(c if (c.isalnum() or c == "_") else "_"
                   for c in "_".join(words)).strip("_") or "thing"
    return words, slug


def new_mint_slug(description):
    words = T.split_words(description or "")
    while words and words[0] in {"my", "the", "a", "an", "your", "his", "her",
                                 "their", "its", "some"}:
        words.pop(0)
    slug = T.slugify_per_char("_".join(words)) or "thing"
    return words, slug


# turnloop._grant_moved_place: tail tokens, place evidence, tail kind, words + slug, shell slug
def old_grant_tokens(_tail, pid, lb):
    _ttoks = {t for t in re.split(r"[^a-z0-9]+", _tail.lower()) if len(t) > 3}

    def _place_evidence(pid: str, lb: str) -> set:
        # Cx 449 blocker: the container must match on WORLD FACTS (name/kind
        # in the roster label), never only on how the id happens to be worded
        # — place:north with name "North Village" IS a village.
        _core = str(lb).split(" (the room", 1)[0]  # drop the current-room marker
        return ({t for t in str(pid).split(":", 1)[-1].split("_") if len(t) > 3}
                | {t for t in re.split(r"[^a-z0-9]+", _core.lower())
                   if len(t) > 3})
    return _ttoks, _place_evidence(pid, lb)


def new_grant_tokens(_tail, pid, lb):
    _ttoks = set(T.alnum_words(_tail, min_len=4))

    def _place_evidence(pid: str, lb: str) -> set:
        _core = str(lb).split(" (the room", 1)[0]  # drop the current-room marker
        return (set(T.id_stem_parts(str(pid), min_len=4))
                | set(T.alnum_words(_core, min_len=4)))
    return _ttoks, _place_evidence(pid, lb)


def old_tail_kind(_tail):
    _tkind = _tail.lower().split()[-1]
    return _tkind


def new_tail_kind(_tail):
    _tkind = T.split_words(_tail)[-1]
    return _tkind


def old_grant_slug(moves_to):
    words = (moves_to or "").lower().split()
    while words and words[0].strip(".,;:!?'\"") in tl._MOVE_LEAD_STOP:
        words.pop(0)
    slug = "".join(c if (c.isalnum() or c == "_") else "_"
                   for c in "_".join(words)).strip("_")
    return words, slug


def new_grant_slug(moves_to):
    words = T.split_words(moves_to or "")
    while words and words[0].strip(T.EDGE_PUNCT) in tl._MOVE_LEAD_STOP:
        words.pop(0)
    slug = T.slugify_per_char("_".join(words))
    return words, slug


def old_shell_slug(_tail_phrase):
    _tslug = re.sub(r"[^a-z0-9]+", "_", _tail_phrase.lower()).strip("_")
    return _tslug


def new_shell_slug(_tail_phrase):
    _tslug = T.slugify(_tail_phrase)
    return _tslug


# briefing.build_briefing: `_held_name` and the dropped object's name (the same rule)
def old_held_name(canon_table, live_reads, h):
    nm = canon_table.get((h, "name"))
    if not nm:
        try:
            nm = live_reads.state(h, "name")
        except Exception:
            nm = None
    return str(nm or OLD_EXECUTOR["_human"](h))


def old_dropped_name(canon_table, live_reads, trace):
    _dropped_canon = canon_table.get((trace.dropped, "name"))
    if not _dropped_canon:
        try:
            _dropped_canon = live_reads.state(trace.dropped, "name")
        except Exception:
            _dropped_canon = None
    _dropped_nm = str(_dropped_canon or OLD_EXECUTOR["_human"](trace.dropped))
    return _dropped_nm


def new_held_name(canon_table, live_reads, h):
    return T.table_or_read_name_or_human(canon_table, live_reads, h)


def new_dropped_name(canon_table, live_reads, trace):
    return T.table_or_read_name_or_human(canon_table, live_reads, trace.dropped)


# briefing.build_briefing_rulings: public-name tokens and the question's tokens
def old_rulings_tokens(names, improv_query):
    public_name_toks = {t for nm in names.values()
                        for t in nm.lower().replace("-", " ").split()}
    qtoks = set(improv_query.lower().replace("?", " ").replace(",", " ")
                .replace(".", " ").split())
    return public_name_toks, qtoks


def new_rulings_tokens(names, improv_query):
    public_name_toks = {t for nm in names.values() for t in T.split_words(nm, seps="-")}
    qtoks = set(T.split_words(improv_query, seps=T.CLAUSE_PUNCT))
    return public_name_toks, qtoks


# session: status line place, Foyer protagonist name, scene-description name
def old_session_names(loc, proto, e):
    return (loc.split(":", 1)[-1].replace("_", " "),
            proto.split(":")[-1].replace("_", " "),
            e.split(":", 1)[-1].replace("_", " "))


def new_session_names(loc, proto, e):
    return (T.humanize_id(loc), T.humanize_id_last(proto), T.humanize_id(e))


# session._display_name: the humanized-id fallback
def old_display_name_tail(entity):
    s = str(entity)
    if ":" in s:
        local = s.split(":", 1)[-1].replace("_", " ")   # humanized id beats a descriptive clause
        return local.title() if s.startswith("person:") else local  # person slug = a proper name
    return None


def new_display_name_tail(entity):
    s = str(entity)
    if ":" in s:
        # a humanized id beats a descriptive clause; a person slug is a proper name
        return T.human_name(s)
    return None


# session.live_threads._leaks
def old_session_leaks(concealed, text, ev):
    blob = (f"{text} {ev.split(':', 1)[-1]}"
            .replace("_", " ").replace("-", " ").replace(":", " ").lower())
    words = set(blob.split())
    return bool(concealed & words)


def new_session_leaks(concealed, text, ev):
    words = set(T.split_words(f"{text} {T.id_local(ev)}", seps=T.ID_SEPARATORS,
                              lower="last"))
    return bool(concealed & words)


# foyer.world_anchors / character_setup, cast.staging_items, game (seed roster, doorway)
def old_humanize_sites(entity, place):
    return (entity.split(":", 1)[-1].replace("_", " "),
            (place.split(":", 1)[-1].replace("_", " ") if place else ""),
            place.split(":", 1)[-1].replace("_", " ").strip())


def new_humanize_sites(entity, place):
    return (T.humanize_id(entity),
            (T.humanize_id(place) if place else ""),
            T.humanize_id(place).strip())


# game: the play_as tokens of `_finalize_scenario_impl._toks`, an admitted person's name,
# and the leaked words (`forbidden` is always `_hidden_terms(...)`, whose words have 3+ chars)
def old_game_toks(s):
    return set(s.lower().replace(":", " ").replace("_", " ").split())


def new_game_toks(s):
    return set(T.split_words(s, seps=":_"))


def old_admit_name(_orig):
    return _orig.split(":", 1)[-1].replace("_", " ").title()


def new_admit_name(_orig):
    return T.humanize_id_title(_orig)


def old_leaked(goal, chosen, forbidden):
    leaked = {w for w in re.split(r"[^a-z0-9]+", f"{goal} {chosen}".lower())
              if w in forbidden}
    return leaked


def new_leaked(goal, chosen, forbidden):
    leaked = {w for w in T.alnum_words(f"{goal} {chosen}") if w in forbidden}
    return leaked


# transport_core: the transcript/feedback file segment
def old_transport_safe(external_id):
    import re
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", external_id).strip("_") or "player"
    return safe


def new_transport_safe(external_id):
    safe = T.file_safe(external_id) or "player"
    return safe


# ---------------------------------------------------------------------------
# Random inputs
# ---------------------------------------------------------------------------

_WORDS = (
    "the", "a", "an", "of", "to", "in", "at", "on", "by", "my", "own", "back", "into", "with",
    "and", "or", "is", "true", "none", "yes", "no", "press", "demand", "ask", "tell", "where",
    "what", "did", "examine", "inspect", "search", "look", "closely", "carefully", "glance",
    "go", "walk", "take", "grab", "open", "wait", "rest", "nap", "snap", "forest", "dawn",
    "culprit", "map", "key", "dossier", "weapon", "knife", "doctor", "doc", "physician",
    "constable", "officer", "captain", "chief", "clerk", "night", "valet", "butler", "julian",
    "family", "office", "village", "warehouse", "study", "tavern", "cellar", "room", "yard",
    "lane", "street", "barrel", "table", "shed", "foreman", "liddell", "north", "harbour",
    "person", "place", "obj", "fact", "event", "narrator", "speaker", "unknown", "kind",
    "status", "name", "alias", "title", "role", "you", "me", "chapter", "heist", "intrigue",
    "political", "whodunnit", "mystery", "romance", "horror", "survival", "cozy", "noir",
    "wipe", "keep", "fresh", "redo", "new", "cancel", "confirm",
    "josé", "café", "naïve", "Straße", "İstanbul", "ΣΟΦΙΑΣ", "σοφία", "Жена", "東京",
    "مرحبا", "x", "ab", "abc", "abcd", "abcde", "abcdef", "A1", "007", "²³", "١٢٣", "Ⅻ",
)
_PUNCT = tuple(string.punctuation) + ("’", "‘", "“", "”", "—", "–", "…", "·", "§", "¿", "¡")
_SPACE = (" ", " ", " ", " ", "\t", "\n", "\r", " ", " ", "　", "\x0b", "\x0c",
          "\x1c", "\x85", " ", "​")
#: Odd characters, plus the one context-sensitive lowering (the Greek final sigma) next to
#: the case-ignorable separators (':', '.', the apostrophes, a combining mark) that make
#: "lowercase, then split" differ from "split, then lowercase".
_ODD = ("é", "É", "ß", "ẞ", "İ", "ı", "K", "Σ", "σ", "ς", "ﬁ", "Æ", "ø", "ǅ", "́",
        "̇", "🙂", "‍", "½", "²", "٣", "_", ":", "-", "/", "__", "::", "--",
        "ΛΟΓΟΣ:ΤΙ", "ΟΔΟΣ.Α", "ΣΑΣ'Α", "ΤΙΣ’Α", "ΑΣ-Β", "ΑΣ_Β", "ΑΣ́Β", "Α.Σ:", "ΑΣ ",
        "ΑΣ,Β", "ΑΣ;Β", "ΑΣ?Β", "ΑΣ!Β", "ΑΣ\"Β", "ΑΣ(Β", "ΑΣ—Β", "ΑΣ/Β", "ΑΣ·Β")
_KINDS = ("person", "place", "obj", "fact", "event", "region", "arc", "PERSON", "Place", "")


def _word(rng: random.Random) -> str:
    w = rng.choice(_WORDS)
    return rng.choice((w, w, w, w.upper(), w.title(), w.capitalize()))


def _text(rng: random.Random, parts: int = 10) -> str:
    out = []
    for _ in range(rng.randint(0, parts)):
        r = rng.random()
        if r < 0.45:
            out.append(_word(rng))
        elif r < 0.65:
            out.append(rng.choice(_SPACE))
        elif r < 0.8:
            out.append(rng.choice(_PUNCT))
        elif r < 0.93:
            out.append(rng.choice(_ODD))
        else:
            out.append(_eid(rng))
    return "".join(out)


def _local(rng: random.Random) -> str:
    seps = ("_", "_", "_", "-", ":", "", " ", "__")
    parts = [_word(rng) if rng.random() < 0.85 else rng.choice(_ODD)
             for _ in range(rng.randint(0, 4))]
    out = ""
    for i, p in enumerate(parts):
        out += (rng.choice(seps) if i else "") + p
    if rng.random() < 0.1:
        out = rng.choice(("_", "-", ":")) + out
    if rng.random() < 0.1:
        out += rng.choice(("_", "-", ":"))
    return out


def _eid(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.08:
        return _local(rng)  # no kind prefix (maybe no colon at all)
    kind = rng.choice(_KINDS)
    eid = f"{kind}:{_local(rng)}"
    if r > 0.95:
        eid += f":{_local(rng)}"  # a second colon
    return eid


_RAISE = object()


class _Unreadable(Exception):
    pass


def _value(rng: random.Random, ids: list[str] | None = None) -> Any:
    r = rng.random()
    if r < 0.4:
        return _text(rng, 6)
    if r < 0.5 and ids:
        return rng.choice(ids)
    return rng.choice(("", None, None, 0, 7, 2.5, True, False, [], ["x"], {"k": "v"},
                       _RAISE, "Clara Vale", "the clerk", "josé", "Dr. Ames"))


class _Reads:
    """A fake `reads`: `state(e, a)` serves odd values or raises; `frame_rows` serves rows."""

    def __init__(self, values: dict, keys: set | None = None, rows: dict | None = None):
        self.values, self.keys, self.rows = values, keys or set(), rows or {}

    def state(self, entity, attribute):
        v = self.values.get((entity, attribute))
        if v is _RAISE:
            raise _Unreadable(f"{entity}.{attribute}")
        return v

    def frame_rows(self, frame, entity=None):
        rows = self.rows.get(entity, [])
        if rows is _RAISE:
            raise _Unreadable(f"{entity} rows")
        return rows


_ATTRS = ("name", "alias", "aliases", "title", "kind", "role", "background", "pronouns",
          "culprit", "weapon", "location", "status", "rank")


def _reads(rng: random.Random, ids: list[str]) -> _Reads:
    values = {}
    for e in ids:
        for a in _ATTRS:
            if rng.random() < 0.5:
                values[(e, a)] = _value(rng, ids)
    keys = {(rng.choice(ids), rng.choice(_ATTRS)) for _ in range(rng.randint(0, 4))}
    rows = {}
    for e in ids:
        if rng.random() < 0.05:
            rows[e] = _RAISE
        else:
            rows[e] = [SimpleNamespace(attribute=rng.choice(_ATTRS), value=_value(rng, ids))
                       for _ in range(rng.randint(0, 3))]
    return _Reads(values, keys, rows)


def _ids(rng: random.Random) -> list[str]:
    ids = [_eid(rng) for _ in range(rng.randint(1, 5))]
    # entity-reference shaped ids, so the `^[a-z_]+:[a-z0-9_]+$` answer branch runs
    ids += [f"{rng.choice(('person', 'place', 'obj'))}:{rng.choice(_WORDS[:60])}_"
            f"{rng.choice(_WORDS[:60])}" for _ in range(rng.randint(0, 2))]
    return ids


def _table(rng: random.Random, ids: list[str]) -> dict:
    return {(e, "name"): _value(rng, ids) for e in ids if rng.random() < 0.6}


def _keys_stub(arc, reads):
    return reads.keys


# ---------------------------------------------------------------------------
# The pairs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Case:
    name: str
    old: Callable[..., Any]
    new: Callable[..., Any]
    gen: Callable[[random.Random], tuple]
    n: int = N


def _t(rng):
    return (_text(rng),)


def _t_or_none(rng):
    return (None,) if rng.random() < 0.05 else (_text(rng),)


def _e(rng):
    return (_eid(rng),)


def _reads_and_id(rng):
    ids = _ids(rng)
    return (_reads(rng, ids), rng.choice(ids))


def _table_reads_id(rng):
    ids = _ids(rng)
    return (_reads(rng, ids), _table(rng, ids), rng.choice(ids))


def _arc_reads(rng):
    ids = _ids(rng)
    return (SimpleNamespace(protagonist=rng.choice(ids)), _reads(rng, ids))


def _with_secret_patch(fn):
    """Run an OLD growth-vocabulary call with the OLD `concealed_tokens` it imported."""
    def run(*args):
        real = executor.concealed_tokens
        executor.concealed_tokens = OLD_CONCEALMENT["concealed_tokens"]
        try:
            return fn(*args)
        finally:
            executor.concealed_tokens = real
    return run


def _roster(rng):
    roster = []
    for _ in range(rng.randint(0, 5)):
        pid = f"place:{rng.choice(_WORDS[50:120])}_{rng.choice(_WORDS[50:120])}"
        if rng.random() < 0.2:
            pid = _eid(rng)
        label = rng.choice((
            f"{_word(rng)} {_word(rng)} — {_word(rng)}",
            f"{_word(rng)} {_word(rng)} (the room the player is in RIGHT NOW)",
            _text(rng, 5), ""))
        roster.append((pid, label))
    return roster


def _phrase(rng):
    seps = (", ", "; ", " at ", " in ", " to ", " within ", " inside ", " ", " ", " the ")
    return "".join(rng.choice(seps) + _word(rng) for _ in range(rng.randint(0, 7)))


def _person_table(rng):
    ids = [f"person:{_local(rng)}" for _ in range(rng.randint(0, 4))] + _ids(rng)
    table = {}
    for e in ids:
        for a in ("role", "title", "rank", "name", "kind"):
            if rng.random() < 0.5:
                table[(e, a)] = rng.choice((_text(rng, 5), _word(rng), 3, None))
    return table


def _proposal(rng):
    def beat():
        return {"kind": rng.choice(("player_learns", "event_occurs", "")),
                "value": rng.choice((_eid(rng), _text(rng, 4), 5, None))}
    return {"beats": [beat() for _ in range(rng.randint(0, 3))],
            "failure_when": beat() if rng.random() < 0.5 else None}


def _world(rng, ids):
    values = {(e, "name"): _value(rng, ids) for e in ids}
    return SimpleNamespace(porcelain=_Reads(values))


def _tension(rng):
    r = rng.random()
    if r < 0.1:
        tension = (_eid(rng), _eid(rng))  # wrong arity: raises inside the try
    elif r < 0.15:
        tension = (_eid(rng), None, _eid(rng))  # a non-string: raises inside the try
    else:
        tension = (_eid(rng), _eid(rng), _eid(rng))
    return (SimpleNamespace(shape=SimpleNamespace(tension=tension)),)


def _choices(rng):
    return {k: tuple(rng.sample(_WORDS[:100], rng.randint(1, 3)))
            for k in rng.sample(("wipe", "keep", "new", "redo", "cancel"), rng.randint(1, 4))}


def _card_label(rng):
    if rng.random() < 0.3:
        return rng.choice([c["name"] for c in play_styles.STYLE_CARDS.values()])
    if rng.random() < 0.2:
        return rng.choice(list(play_styles.STYLE_CARDS))
    return _text(rng, 4)


def _rows_prose(rng):
    ids = _ids(rng) + [f"{rng.choice(('place', 'person'))}:{_local(rng)}" for _ in range(3)]
    rows = [{"entity": rng.choice(ids + [None, 5]),
             "attribute": rng.choice(("kind", "name", "in"))} for _ in range(rng.randint(0, 5))]
    prose = _text(rng, 12) + " " + " ".join(
        e.split(":", 1)[-1].replace("_", rng.choice((" ", "-", "’"))) for e in ids
        if rng.random() < 0.5)
    return (rows, prose if rng.random() < 0.95 else "")


TL, CON, EX, GM = OLD_TURNLOOP, OLD_CONCEALMENT, OLD_EXECUTOR, OLD_GAME

CASES = [
    # ---- turnloop: concealment vocabulary tokenizers --------------------------------
    Case("turnloop._secret_word_set", TL["_secret_word_set"], tl._secret_word_set, _t_or_none),
    Case("turnloop._secret_tokens", TL["_secret_tokens"], tl._secret_tokens,
         lambda r: _arc_reads(r) + ({_word(r).lower() for _ in range(r.randint(0, 3))},)),
    Case("turnloop._take_touches_secret", TL["_take_touches_secret"], tl._take_touches_secret,
         lambda r: (_text(r),) + _arc_reads(r)),
    Case("turnloop._concealed_move_vocab", TL["_concealed_move_vocab"],
         tl._concealed_move_vocab, _arc_reads),
    Case("turnloop._move_touches_secret", TL["_move_touches_secret"], tl._move_touches_secret,
         lambda r: (_text(r),) + _arc_reads(r)),
    Case("turnloop._growth_concealed_vocab", _with_secret_patch(TL["_growth_concealed_vocab"]),
         tl._growth_concealed_vocab, _arc_reads),
    # ---- turnloop: intent and address heuristics ------------------------------------
    Case("turnloop._is_pressing", lambda s, b: TL["_is_pressing"](s, needs_test=b),
         lambda s, b: tl._is_pressing(s, needs_test=b),
         lambda r: (_text(r) if r.random() < 0.5 else _text(r).lower(), r.random() < 0.1)),
    Case("turnloop._is_scrutiny", TL["_is_scrutiny"], tl._is_scrutiny,
         lambda r: (_text(r) if r.random() < 0.5 else _text(r).lower(),)),
    Case("turnloop._words", TL["_words"], tl._words, _t),
    Case("turnloop._names_entity", TL["_names_entity"], tl._names_entity,
         lambda r: (_eid(r), _text(r).lower(), _text(r, 4), _text(r, 4))),
    Case("turnloop._title_holder", TL["_title_holder"], tl._title_holder,
         lambda r: (_person_table(r), _word(r).lower() if r.random() < 0.9 else "", _eid(r))),
    Case("turnloop._dest_head", TL["_dest_head"], tl._dest_head,
         lambda r: (None,) if r.random() < 0.05 else (_phrase(r) + _text(r, 3),)),
    Case("turnloop._embedded_container", TL["_embedded_container"], tl._embedded_container,
         lambda r: (_phrase(r) if r.random() < 0.8 else _text(r), _roster(r))),
    Case("turnloop._protagonist_tokens", TL["_protagonist_tokens"], tl._protagonist_tokens, _e),
    Case("turnloop.names_protagonist", TL["names_protagonist"], tl.names_protagonist,
         lambda r: (_text(r) + " " + _local(r).replace("_", " "), _eid(r))),
    # ---- turnloop: inline snippets and closures --------------------------------------
    Case("turnloop._growth_attempt._disp", old_growth_disp, new_growth_disp, _reads_and_id),
    Case("turnloop._world_tick place label", old_tick_place, new_tick_place,
         lambda r: (_eid(r), _value(r))),
    Case("turnloop._absence_beat._swhere", old_absence_where, new_absence_display,
         _reads_and_id),
    Case("turnloop._absence_beat._display", old_absence_display, new_absence_display,
         _reads_and_id),
    Case("turnloop._relocate_beat holder desc", old_holder_desc, new_holder_desc,
         lambda r: (_value(r), SimpleNamespace(node_id=_eid(r), surface_role=_value(r),
                                               shape_role=_value(r)))),
    Case("turnloop._repair_beat entity name", old_repair_entity, new_repair_entity,
         _reads_and_id),
    Case("turnloop._repair_beat holder line", old_repair_holder, new_repair_holder,
         _reads_and_id),
    Case("turnloop.run_turn actor", old_actor, new_actor, lambda r: _arc_reads(r)[::-1]),
    Case("turnloop.run_turn npc candidate", old_npc_desc, new_npc_desc,
         lambda r: (_value(r), _eid(r))),
    Case("turnloop.run_turn._pin_name", old_pin_name,
         lambda reads, e: T.read_str(reads, e), _reads_and_id),
    Case("turnloop.run_turn._name_of", old_name_of,
         lambda reads, e: T.read_str(reads, e), _reads_and_id),
    Case("turnloop.run_turn._live_name", old_live_name,
         lambda reads, e: T.read_str(reads, e), _reads_and_id),
    Case("turnloop.run_turn dest key", old_dest_key, new_dest_key,
         lambda r: (r.choice((None, "", _eid(r))), _value(r))),
    Case("turnloop.run_turn deictic probe", old_slug_probe, new_slug_probe,
         lambda r: (_value(r),)),
    Case("turnloop.run_turn roster label", old_roster_label, new_roster_label,
         lambda r: ([_text(r, 3) for _ in range(r.randint(0, 2))], _eid(r))),
    Case("turnloop.run_turn._npc_name", old_npc_name, new_table_or_read_name,
         _table_reads_id),
    Case("turnloop.run_turn._settle._resolve_name_of", old_resolve_name_of,
         new_table_or_read_name, _table_reads_id),
    Case("turnloop.run_turn vocative name", old_voc_name, new_voc_name,
         lambda r: (lambda ids: (_table(r, ids), r.choice(ids)))(_ids(r))),
    Case("turnloop.run_turn._disp (scene)", old_scene_disp, new_scene_disp,
         lambda r: (lambda ids: ({e: _text(r, 3) for e in ids if r.random() < 0.3},
                                 r.choice(ids + [_text(r)])))(_ids(r))),
    Case("turnloop.run_turn stage here/who", old_stage_here_who, new_stage_here_who,
         lambda r: (lambda ids: (_table(r, ids), r.choice(ids + [None, ""]),
                                 r.sample(ids, r.randint(0, len(ids)))))(_ids(r))),
    Case("turnloop.run_turn._settle license", old_license, new_license,
         lambda r: (_text(r, 20), _text(r), _eid(r))),
    Case("turnloop._mint_held_object slug", old_mint_slug, new_mint_slug, _t_or_none),
    Case("turnloop._grant_moved_place tokens", old_grant_tokens, new_grant_tokens,
         lambda r: (_text(r, 5), _eid(r), _text(r, 6))),
    Case("turnloop._grant_moved_place tail kind", old_tail_kind, new_tail_kind,
         lambda r: (_text(r, 5),)),
    Case("turnloop._grant_moved_place slug", old_grant_slug, new_grant_slug,
         lambda r: (None,) if r.random() < 0.05 else (_phrase(r) + _text(r, 4),)),
    Case("turnloop._grant_moved_place shell slug", old_shell_slug, new_shell_slug, _t),
    # ---- briefing --------------------------------------------------------------------
    Case("briefing._id_attr", old_id_attr, new_id_attr,
         lambda r: _arc_reads(r)[::-1] + (r.choice(_ATTRS),)),
    Case("briefing._held_name", old_held_name, new_held_name,
         lambda r: (lambda ids: (_table(r, ids), _reads(r, ids), r.choice(ids)))(_ids(r))),
    Case("briefing dropped name", old_dropped_name, new_dropped_name,
         lambda r: (lambda ids: (_table(r, ids), _reads(r, ids),
                                 SimpleNamespace(dropped=r.choice(ids))))(_ids(r))),
    Case("briefing rulings tokens", old_rulings_tokens, new_rulings_tokens,
         lambda r: ({_eid(r): _text(r, 4) for _ in range(r.randint(0, 3))}, _text(r))),
    # ---- arc: concealment and the humanizer ------------------------------------------
    Case("concealment.concealed_tokens", CON["concealed_tokens"], concealment.concealed_tokens,
         lambda r: ({(_eid(r), r.choice(_ATTRS + (_text(r, 3),)))
                     for _ in range(r.randint(0, 4))},)),
    Case("concealment.value_leaks", CON["value_leaks"], concealment.value_leaks,
         lambda r: (r.choice((_text(r), _eid(r), 5, None)),
                    {_word(r).lower() for _ in range(r.randint(0, 4))})),
    Case("executor._human", EX["_human"], executor._human, _e),
    Case("text.human_name", EX["_human"], T.human_name, _e),
    # ---- other modules: tokenizers ---------------------------------------------------
    Case("cast._identity_tokens", OLD_CAST["_identity_tokens"], cast._identity_tokens,
         lambda r: (r.choice((_text(r), 5, None)),)),
    Case("clock.deterministic_elapsed", lambda a, m: OLD_CLOCK["deterministic_elapsed"](a, moved=m),
         lambda a, m: clock.deterministic_elapsed(a, moved=m),
         lambda r: (_text(r), r.random() < 0.2)),
    Case("play_styles._tokens", OLD_PLAY_STYLES["_tokens"], play_styles._tokens, _t_or_none),
    Case("play_styles._tokens join order", lambda s: "_".join(OLD_PLAY_STYLES["_tokens"](s)),
         lambda s: "_".join(play_styles._tokens(s)), _t_or_none),
    Case("play_styles.match", OLD_PLAY_STYLES["match"], play_styles.match,
         lambda r: (_card_label(r),), n=400),
    Case("resolve._is_place_like", OLD_RESOLVE["_is_place_like"], resolve._is_place_like,
         lambda r: (r.choice((_text(r, 4), None, "")), _eid(r))),
    Case("resolve.is_voice", OLD_RESOLVE["is_voice"], resolve.is_voice,
         lambda r: (r.choice((_eid(r), _text(r, 4), None, 5)),)),
    Case("resolve.reconstruct_names", OLD_RESOLVE["reconstruct_names"],
         resolve.reconstruct_names, _rows_prose),
    Case("session.live_threads._leaks", old_session_leaks, new_session_leaks,
         lambda r: ({_word(r).lower() for _ in range(r.randint(0, 4))}, _text(r), _eid(r))),
    Case("game._finalize_scenario_impl._toks", old_game_toks, new_game_toks, _t),
    Case("game._hidden_terms", GM["_hidden_terms"], game._hidden_terms,
         lambda r: (None, _proposal(r))),
    Case("game._goal_statement_safe", GM["_goal_statement_safe"], game._goal_statement_safe,
         lambda r: (r.choice((_text(r), "", "  ")), game._hidden_terms(None, _proposal(r)))),
    Case("game._player_goal leaked", old_leaked, new_leaked,
         lambda r: (_text(r), _text(r), game._hidden_terms(None, _proposal(r)))),
    Case("game._fallback_protagonist", GM["_fallback_protagonist"], game._fallback_protagonist,
         lambda r: (lambda ids: (_world(r, ids), r.sample(ids, r.randint(0, len(ids))),
                                 _text(r, 5)))(_ids(r))),
    Case("transport_core._pick", OLD_TRANSPORT["_pick"], transport_core._pick,
         lambda r: (r.choice((_text(r), None)), _choices(r))),
    # ---- slugs -----------------------------------------------------------------------
    Case("laws._slug", OLD_LAWS["_slug"], laws._slug, _t_or_none),
    Case("remembrancer._slug", OLD_REMEMBRANCER["_slug"], remembrancer._slug, _t_or_none),
    Case("imagery._slug", OLD_IMAGERY["_slug"], imagery._slug, _t_or_none),
    Case("reshape._slug", OLD_RESHAPE["_slug"], reshape._slug, _t_or_none),
    Case("growth._slugify", OLD_GROWTH["_slugify"], T.slugify, _t_or_none),
    Case("generator._id_slug", OLD_GENERATOR["_id_slug"], generator._id_slug, _t_or_none),
    Case("game._slug", GM["_slug"], game._slug, _t_or_none),
    Case("game._safe_player_id", GM["_safe_player_id"], game._safe_player_id, _t_or_none),
    Case("transport_core._safe", OLD_TRANSPORT["_safe"], transport_core._safe, _t_or_none),
    Case("transport_core transcript/feedback segment", old_transport_safe, new_transport_safe,
         _t_or_none),
    # ---- humanized ids ---------------------------------------------------------------
    Case("journal._humanize", OLD_JOURNAL["_humanize"], T.humanize_id_title, _e),
    Case("session status/setup/scene names", old_session_names, new_session_names,
         lambda r: (_eid(r), _eid(r), _eid(r))),
    Case("session._display_name humanized id", old_display_name_tail, new_display_name_tail,
         lambda r: (r.choice((_eid(r), _text(r, 3), 5)),)),
    Case("session._establishing_anchors.disp", old_anchor_disp, new_anchor_disp,
         lambda r: (lambda ids: ({e: _text(r, 3) for e in ids if r.random() < 0.3},
                                 r.choice(ids + [_text(r), 5])))(_ids(r))),
    Case("foyer/cast/game humanized ids", old_humanize_sites, new_humanize_sites,
         lambda r: (_eid(r), r.choice((_eid(r), "")))),
    Case("game admitted person name", old_admit_name, new_admit_name, _e),
    Case("game._tension_axis", GM["_tension_axis"], game._tension_axis, _tension),
]


def _run(fn: Callable[..., Any], args: tuple) -> tuple:
    try:
        return ("value", fn(*args))
    except Exception as exc:  # noqa: BLE001 — the exception TYPE is part of the behaviour
        return ("raises", type(exc))


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_old_copy_and_toolkit_agree(case: Case, monkeypatch) -> None:
    """The old copy and its toolkit replacement give the same result on every input."""
    monkeypatch.setattr(tl, "arc_protected_keys", _keys_stub)
    OLD_TURNLOOP["arc_protected_keys"] = _keys_stub
    rng = random.Random(f"text-toolkit:{case.name}")
    for i in range(case.n):
        args = case.gen(rng)
        old, new = _run(case.old, args), _run(case.new, args)
        assert old == new, f"{case.name} differs on input #{i}: {args!r}\nold={old!r}\nnew={new!r}"


def test_property_inputs_reach_the_interesting_branches() -> None:
    """Guard the generators: the random inputs really exercise raising reads, typed ids,
    multi-colon ids, non-ASCII letters and the empty-result fallbacks."""
    rng = random.Random("text-toolkit:coverage")
    texts = [_text(rng) for _ in range(3000)]
    assert any(any(ord(c) > 127 for c in t) for t in texts)
    assert any(t.strip() == "" for t in texts)
    assert sum(T.slugify(t) == "" for t in texts) > 50
    ids = [_eid(rng) for _ in range(3000)]
    assert sum(i.count(":") > 1 for i in ids) > 50
    assert sum(T.is_typed_id(i) for i in ids) > 1000
    assert sum(":" not in i for i in ids) > 20
    reads = _reads(rng, ids[:50])
    outcomes = {_run(reads.state, (e, a))[0] for e in ids[:50] for a in _ATTRS}
    assert outcomes == {"value", "raises"}
    assert any(not isinstance(v, str) and v for v in reads.values.values() if v is not _RAISE)


def test_old_names_stay_importable() -> None:
    """Names the suite or other modules import from their old homes still resolve there."""
    from construct.arc.concealment import _CONCEAL_WORD
    from construct.arc.executor import _CONCEAL_WORD as _ex_word, _human
    from construct.turnloop import (  # noqa: F401
        _dest_head, _embedded_container, _is_pressing, _is_scrutiny, _move_touches_secret,
        _names_entity, _secret_tokens, _secret_word_set, _take_touches_secret, _words,
        arc_protected_keys, names_protagonist,
    )
    from construct.game import _slug  # noqa: F401 — library.py imports it

    assert _human is T.human_name
    assert _CONCEAL_WORD is _ex_word is T.UNICODE_WORD


def test_examples_pin_the_documented_differences() -> None:
    """The near-duplicates stay distinct (worked examples from the toolkit docstrings)."""
    assert T.alnum_words("José's café, the map!") == ["jos", "s", "caf", "the", "map"]
    assert T.unicode_words("José's café, the map!") == ["josé", "s", "café", "the", "map"]
    assert T.split_words("José's café, the map!") == ["josé's", "café,", "the", "map!"]
    # the lowering order shows only through the Greek final sigma next to a case-ignorable mark
    assert T.respace("ΛΟΓΟΣ:ΤΙ", seps=":", lower="first") == "λογοσ τι"
    assert T.respace("ΛΟΓΟΣ:ΤΙ", seps=":", lower="last") == "λογος τι"
    assert T.split_words("Press ON", lower="never") == ["Press", "ON"]
    assert T.separator_words("a\tb kind, x_y-z/q:r") == ["a\tb", "kind,", "x", "y", "z", "q", "r"]
    assert T.slugify("A__b-_-c café") == "a_b_c_caf"
    assert T.slugify_keep_underscores("A__b-_-c café") == "a__b___c_caf"
    assert T.slugify_per_char("A__b-_-c café") == "a__b___c_café"
    assert T.slugify("Rain Barrel!", sep="-") == "rain-barrel"
    assert T.file_safe("Tg:12/Ab-c") == "Tg_12_Ab-c"
    assert T.humanize_id("a:b:c_d") == "b:c d"
    assert T.humanize_id_last("a:b:c_d") == "c d"
    assert T.human_name("person:clara_vale") == "Clara Vale"
    assert T.human_name("obj:brass_token") == "brass token"
    assert T.humanize_id_title("obj:brass_token") == "Brass Token"
    assert T.humanize_typed_id("person:clara_vale") == "clara vale"
    assert T.human_name_typed_id("person:clara_vale") == "Clara Vale"
    assert T.human_name_typed_id("arc:main") == "arc:main"
