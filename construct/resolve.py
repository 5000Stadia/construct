"""Entity Authority — the ONE coreference+typing-disciplined seam every canon entity-write consults
(docs/design/ENTITY-AUTHORITY.md). Founder ruling (2026-06-29): *fix the SHAPE, do not append rules
to handle a misshapen set of information.* PB is the object architecture; Construct is the engine —
so identity/type authority AT THE WRITE BOUNDARY is ours.

The misshapen graph is born at the three free-text extraction sites (player-input, NPC action, the
settle narrator-prose). Each free-mints a new entity per surface mention with no shared identity and
no type discipline → `obj:pencil`/`obj:pencil_1`/`obj:plain_pencil` (one pencil), `place:street` AND
`obj:street`, `person:unknown_speaker`/`person:/you` phantoms. This module makes the misshapen graph
*impossible to create*: every extracted row is RESOLVED (bound to a known entity / minted once with
the right kind / dropped) BEFORE it reaches canon. PURE DECISIONS — no world writes here; the caller
runs `porcelain.extract → resolve_rows → ingest_structured` (Cx 304).

Decisions are deterministic (Cx 304 pin 7: ambiguity calls no model and never mints). Each returns a
`reason` for live debugging.
"""
from __future__ import annotations

import re
from typing import Any, Callable

#: deixis → the protagonist (these DO have a referent; never mint a phantom). Cx 304 / Kernos 084 4c.
#: Cx 603 completes the first/second-person family with the plural pronouns (we/us/ourselves/
#: yourselves) and their person:-prefixed extractor forms.  "our"/"ours" project CONSERVATIVELY
#: to the protagonist as the one known included participant — never as exclusive ownership and
#: never guessing other group members.  The plural-reflexives (ourselves, yourselves) bind the
#: same way: the protagonist is the safe host-side anchor; inclusive-plural semantics require PB's
#: pov/scoped-plural fix (letter 570) and will be refined there, not here.
_DEIXIS = {"you", "i", "me", "myself", "self", "yourself",
           "we", "us", "ourselves", "yourselves",
           "my", "mine", "our", "ours", "your", "yours",
           "person:you", "person:i", "person:me", "person:myself", "person:self",
           "person:yourself", "person:we", "person:us",
           "person:ourselves", "person:yourselves",
           "person:my", "person:mine", "person:our", "person:ours",
           "person:your", "person:yours"}
#: narration-VOICE tokens → no entity at all (voice is a frame, not a thing). Kernos 084 4b.
_VOICE_TOKENS = {"narrator", "speaker"}
#: attributes whose VALUE is an entity (so the resolver must resolve the value position too, Cx 304 #3).
_ENTITY_VALUED_ATTRS = {"in", "at", "holds", "contains", "inside", "on", "within", "near"}
#: kinds a FREE-TEXT extraction (prose/player-input/NPC) may MINT on zero candidates. Deliberately
#: EXCLUDES `place` (Cx 306): a new place enters canon ONLY through the deterministic move channel
#: (its place-minting authority) — prose that free-mints `obj:street`/`place:street` is exactly the
#: typing-slip split. A `place:` mention with no candidate is dropped; it binds once the move makes it.
_FREE_TEXT_MINT_KINDS = frozenset({"obj", "person", "fact", "event", "doc"})
#: kinds the PLAYER-INPUT channel may mint — TIGHTER than free-text: no `person` and no `place`.
#: A player cannot conjure a NEW person or place into the world by fiat (IMPROV-AND-AUTHORITY model):
#: NPCs are introduced by the narrator/world (settle/NPC paths), places by the deterministic move
#: channel. The player CAN mint an ordinary OBJECT ("a mug from the bar"). Founder live bug
#: (2026-06-30): "I am Bradford Clemense" minted `person:bradford_clemense` as a present NPC — the
#: player's first-person self-reference must NEVER manifest a separate person.
_PLAYER_INPUT_MINT_KINDS = frozenset({"obj", "fact", "event", "doc"})
#: #98 FIRST-MENTION PERMANENCE (Cx 415, the 306 amendment): the NARRATION channel's mint kinds —
#: person leaves the free set (a descriptive "the landlord" must not mint) and place stays out;
#: BOTH re-enter only through the proper-name STUB gate below (founder's robot-vacuum ruling:
#: a named detail the world establishes becomes solid immediately; engagement paints the rest).
_NARRATION_MINT_KINDS = frozenset({"obj", "fact", "event", "doc"})
#: kinds the narration channel may STUB-mint on a zero-candidate PROPER NAME ("The Hart and Bell",
#: "John Johnson") — minimal rows only (`_STUB_ATTRS`), non-present, no scene effects (Cx 415 #3).
_NARRATION_STUB_KINDS = frozenset({"place", "person"})
#: the ONLY attributes a stub mint may carry (Cx 415 #3): typing, the name, and — for a place —
#: containment IFF the container BINDS to an existing place. No description, no features, no
#: presence; a person stub gets no `in` at all (staging stays with its own authorities).
_STUB_ATTRS = {"place": frozenset({"kind", "name", "in"}),
               "person": frozenset({"kind", "name", "role", "title"})}
#: connective/particle tokens that stay lowercase inside a proper name ("The Hart AND Bell",
#: "Duke OF Norfolk") — never evidence against proper-ness.
_NAME_CONNECTIVES = frozenset({"and", "of", "the", "a", "an", "de", "la", "le", "du",
                               "von", "van", "der", "den", "at", "on", "in", "&"})
#: PLACE-like kind/id nouns. An `obj:` whose KIND (or id-stem) is one of these is a MISTYPED place,
#: not an object — free-text must not mint it as an `obj:` (the move channel owns places), or the
#: `obj:street`/`place:street` split reforms (Cx 308). Interim host typing signal pending PB's
#: engine retype path (Kernos 083 bucket 2). Kept to unambiguous spatial nouns.
_PLACE_LIKE_KINDS = frozenset({
    "street", "road", "highway", "lane", "alley", "yard", "court", "square", "plaza",
    "room", "office", "hall", "chamber", "corridor", "passage", "stair", "landing", "lobby",
    "house", "building", "cottage", "cabin", "shop", "store", "tavern", "inn", "pub",
    "warehouse", "cellar", "attic", "kitchen", "parlor", "parlour", "study", "garden",
    "field", "path", "bridge", "gate", "dock", "wharf", "quay", "pier", "market", "churchyard",
    "cemetery", "graveyard", "station", "platform", "tunnel", "cave", "bay", "deck", "cabin",
    "place", "site", "location", "area", "district", "village", "town", "city", "quarter",
})


def _is_place_like(kind_hint: str, eid: str) -> bool:
    """Whether a free-text `obj:` is really a mistyped PLACE — judged by its declared KIND value
    hitting `_PLACE_LIKE_KINDS` (Cx 308). Deliberately reads ONLY the kind, NOT the id-stem: a stem
    token would wrongly flag `obj:office_key`/`obj:street_lamp` (objects with a place word as a
    modifier). The extractor's `kind` is the reliable type signal — `obj:street kind street` is the
    mistyped place; `obj:office_key kind key` is a real object."""
    toks = set(re.split(r"[ _\-/:]+", (kind_hint or "").lower()))
    return bool(toks & _PLACE_LIKE_KINDS)


def is_proper_named(name: Any) -> bool:
    """#98 (Cx 415 #1): is this extracted NAME a PROPER NAME — the resolver-side stub
    predicate, distinct from the session display helper (`_is_namelike` rightly rejects
    article-led strings for display fallback; a named VENUE is article-led by convention).

    Accepts: "The Hart and Bell", "John Johnson", "Dr. Ames", "Administrator Cray",
    "Brackenmere" — every significant token capitalized (connectives may stay lower).
    Rejects: "the street", "the yard", "the wrapped crown", "street", "a tall man" —
    any significant token lowercase is DESCRIPTION, not a name. Case is the evidence,
    so an extractor that lowercases everything simply never stubs (fail-closed)."""
    if not isinstance(name, str) or not name.strip():
        return False
    toks = [t for t in re.split(r"[\s\-]+", name.strip()) if t]
    if not toks:
        return False
    # a leading article is convention for venue names; it carries no case evidence
    if toks[0].lower() in ("the", "a", "an"):
        toks = toks[1:]
    sig = [t for t in toks if t.lower().strip(".,'") not in _NAME_CONNECTIVES]
    if not sig:
        return False
    return all(t[:1].isupper() for t in sig)


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


def is_malformed(eid: Any) -> bool:
    """An extraction-artifact id with an empty / leading-slash local-part (`person:/you`,
    `place:/coffee_house`, `obj:/door`). Never a real entity (was the host `_malformed_id` guard)."""
    if not isinstance(eid, str) or ":" not in eid:
        return False
    loc = eid.split(":", 1)[1]
    return loc.startswith("/") or not loc.strip("/_- ")


def is_voice(eid: Any) -> bool:
    """A non-diegetic narration-voice phantom (`person:narrator`, `person:unknown_speaker`). Matched
    whole-token so a legit `person:speakman` is untouched (was the host `_is_narrator_phantom` guard)."""
    if not isinstance(eid, str):
        return False
    toks = set(t for t in re.split(r"[ _\-/:]+", eid.lower()) if t)
    return bool(toks & _VOICE_TOKENS)


def is_deixis(token: Any) -> bool:
    """A first/second-person pronoun mention — binds to the protagonist, never its own entity."""
    if not isinstance(token, str):
        return False
    return token.lower().strip(".,!?'\"() ") in _DEIXIS


def _mention_text(eid: str, name: str = "") -> str:
    """The text used to coreference-match an extracted entity: its id-stem tokens + any name."""
    return (_local(eid).replace("_", " ") + " " + (name or "")).strip().lower()


def _entity_valued(row: dict) -> bool:
    return (row.get("value_type") == "entity"
            or (row.get("attribute") in _ENTITY_VALUED_ATTRS
                and isinstance(row.get("value"), str) and ":" in str(row.get("value"))))


def _kind_ok(entity: str, attribute: str, value: Any) -> bool:
    """Per-row kind expectation (Cx 304 #3): a PERSON's location (`in`) must be a place/person, never
    an OBJECT (`person:X in obj:street` is the desync). Other rows pass."""
    if attribute == "in" and str(entity).startswith("person:") and str(value).startswith("obj:"):
        return False
    return True


def _match_one(eid: str, name: str, candidates, name_of: Callable[[str], str]) -> tuple[str | None, str]:
    """Coreference the mention against a BOUNDED live candidate set by whole-token identity
    (Cx 304 #5). Returns (id, "bound") on a UNIQUE same-kind match, (None, "ambiguous") on multiple,
    (None, "none") on zero. NEVER mints here — ambiguity must not spawn a sibling (Cx 304 #1)."""
    from construct.turnloop import _names_entity  # lazy: turnloop imports this module
    mention = _mention_text(eid, name)
    prefix = eid.split(":", 1)[0] if isinstance(eid, str) and ":" in eid else ""
    hits = []
    for c in candidates:
        if not isinstance(c, str) or ":" not in c:
            continue
        # same-kind only — don't bind an obj mention to a person, etc. (a place/obj typing slip
        # binds because we DON'T constrain place<->obj here; that IS the retype-by-bind we want).
        # NB `prefix` is the bare namespace ("person"/"obj"/"place"), no colon (Cx 308: the old
        # `"person:"` comparison was dead, letting `obj:doctor` bind `person:doctor`).
        if prefix == "person" and not c.startswith("person:"):
            continue
        if prefix in ("place", "obj") and c.startswith("person:"):
            continue
        if _names_entity(c, mention, name=str(name_of(c) or "")):
            hits.append(c)
    hits = list(dict.fromkeys(hits))
    if len(hits) == 1:
        return hits[0], "bound"
    if len(hits) > 1:
        return None, "ambiguous"
    return None, "none"


def decide_entity(eid: str, name: str, *, candidates, protagonist: str,
                  name_of: Callable[[str], str], allow_mint: bool,
                  mint_kinds=None, kind_hint: str = "",
                  stub_kinds=None) -> tuple[str | None, str]:
    """Resolve ONE extracted entity id to its canonical form. Returns (resolved_id_or_None, reason).
    Order (Cx 304): malformed→drop, voice→drop, deixis→protagonist, coreference-bind (unique),
    ambiguous→drop (never a sibling), zero→typed mint IFF allow_mint AND the kind is sanctioned
    (`mint_kinds`, Cx 306 — free-text never mints a place) else drop. #98 (Cx 415): a channel may
    additionally sanction `stub_kinds` — a zero-candidate place/person whose extracted NAME is a
    PROPER NAME stub-mints ("stub_minted"; the caller trims it to `_STUB_ATTRS`); descriptive
    mentions still fall through to the ordinary denial."""
    if is_malformed(eid):
        return None, "dropped_malformed"
    if is_voice(eid):
        return None, "dropped_voice"
    if is_deixis(eid):
        return protagonist, "deixis_bound"
    bound, why = _match_one(eid, name, candidates, name_of)
    if why == "bound":
        return bound, "bound"
    if why == "ambiguous":
        return None, "ambiguous"          # Cx 304 #1: a definite/ambiguous mention never mints
    # zero candidates — mint only when the channel sanctions this kind (Cx 306: no free-text place)
    prefix = eid.split(":", 1)[0] if isinstance(eid, str) and ":" in eid else ""
    if stub_kinds and prefix in stub_kinds and is_proper_named(name):
        return eid, "stub_minted"         # #98: first-mention permanence — the named detail holds
    if allow_mint and (mint_kinds is None or prefix in mint_kinds):
        # a free-text `obj:` whose KIND is place-like is a MISTYPED place — deny (Cx 308): the move
        # channel owns places, so this can't mint an `obj:street` to later split against `place:street`.
        if prefix == "obj" and _is_place_like(kind_hint, eid):
            return None, "place_like_obj_denied"
        return eid, "minted"
    return None, "novel_denied"


def resolve_rows(rows: list[dict], *, scene, protagonist: str,
                 name_of: Callable[[str], str], allow_mint: bool = True,
                 mint_kinds=_FREE_TEXT_MINT_KINDS,
                 stub_kinds=None) -> tuple[list[dict], list[tuple]]:
    """Resolve a freeform extraction's rows (the player-input / NPC / settle-prose sites) into
    canon-ready structured rows. Rewrites BOTH the subject and any entity-valued value; DROPS the
    whole row if either side resolves to None or violates the kind expectation (Cx 304 #2/#3). A
    `kind` row on a BOUND (existing) entity is dropped — the extractor never RE-TYPES an established
    entity (Cx 306: this is what kills the `{place:street, kind, object}` cross-prefix retype). No
    writes. Returns (resolved_rows, receipts) where each receipt is (id, attribute, reason).

    #98 (Cx 415): `stub_kinds` opens the PROPER-NAME stub gate for this channel (the narration
    settle path passes {"place","person"}). A stub commits ONLY its `_STUB_ATTRS` rows (everything
    else trims); a stub's `in` needs a container that BINDS to an existing place; a stub in the
    VALUE position is denied outright (containment/presence toward a brand-new place would be a
    relocation effect — the move/staging authorities own those)."""
    names = {r["entity"]: r["value"] for r in rows
             if r.get("attribute") == "name" and isinstance(r.get("value"), str)}
    kinds = {r["entity"]: r["value"] for r in rows
             if r.get("attribute") == "kind" and isinstance(r.get("value"), str)}
    cache: dict[str, tuple[str | None, str]] = {}

    def decide(eid: str) -> tuple[str | None, str]:
        if eid not in cache:
            cache[eid] = decide_entity(eid, names.get(eid, ""), candidates=scene,
                                       protagonist=protagonist, name_of=name_of,
                                       allow_mint=allow_mint, mint_kinds=mint_kinds,
                                       kind_hint=kinds.get(eid, ""),
                                       stub_kinds=stub_kinds)
        return cache[eid]

    out: list[dict] = []
    receipts: list[tuple] = []
    for r in rows:
        e_id, e_reason = decide(r["entity"])
        if e_id is None:
            receipts.append((r["entity"], r.get("attribute"), e_reason))
            continue
        # never RE-TYPE an existing entity: a `kind` row whose subject BOUND to a known entity is
        # the extractor's typing opinion about something already canon — drop it (Cx 306).
        if r.get("attribute") == "kind" and e_reason == "bound":
            receipts.append((e_id, "kind", "bound_kind_skipped"))
            continue
        # #98: a stub is MINIMAL (Cx 415 #3) — anything beyond typing/name/(sanctioned
        # containment) trims; the picture gets painted only when engagement earns it.
        if e_reason == "stub_minted":
            _pref = e_id.split(":", 1)[0]
            if r.get("attribute") not in _STUB_ATTRS.get(_pref, frozenset()):
                receipts.append((e_id, r.get("attribute"), "stub_trimmed"))
                continue
        # a RECONSTRUCTED name (prose-casing evidence, `reconstruct_names`) exists to
        # feed the stub gate — it commits ONLY with the stub; a bound entity's canon
        # name is never re-asserted from prose casing.
        if r.get("_synthetic_name") and e_reason != "stub_minted":
            receipts.append((e_id, "name", "synthetic_name_skipped"))
            continue
        r2 = dict(r)
        r2.pop("_synthetic_name", None)
        r2["entity"] = e_id
        if _entity_valued(r):
            v_id, v_reason = decide(str(r.get("value")))
            if v_id is None:
                receipts.append((str(r.get("value")), r.get("attribute"), v_reason))
                continue
            if v_reason == "stub_minted":
                # #98: a stub never enters the VALUE position — pointing an existing
                # entity's `in`/`holds` at a brand-new place/person is a presence effect
                # the stub gate does not own (Cx 415 #3/#6).
                receipts.append((v_id, r.get("attribute"), "stub_value_denied"))
                continue
            r2["value"] = v_id
            if v_reason in ("bound", "minted", "deixis_bound"):
                receipts.append((v_id, r.get("attribute"), v_reason))
        if (e_reason == "stub_minted" and r.get("attribute") == "in"
                and not str(r2.get("value", "")).startswith("place:")):
            # a stub's containment must land on an EXISTING place (bound above) — a
            # person container or anything unbound drops (Cx 415 #3).
            receipts.append((e_id, "in", "stub_containment_unbound"))
            continue
        if not _kind_ok(r2["entity"], r2.get("attribute"), r2.get("value")):
            receipts.append((r2["entity"], r2.get("attribute"), "kind_mismatch"))
            continue
        out.append(r2)
        if e_reason in ("bound", "minted", "deixis_bound", "stub_minted"):
            receipts.append((r2["entity"], r2.get("attribute"), e_reason))
    return out, receipts


def bind_or_mint(mention: str, *, kind: str, candidates, protagonist: str,
                 name_of: Callable[[str], str]) -> tuple[str | None, str]:
    """The DETERMINISTIC-channel resolver (player take/drop/move): resolve a freeform mention to a
    known same-kind entity, or signal a typed mint. Returns (id, "bound") on a unique match,
    (protagonist, "deixis_bound") for 'me', (None, "mint") on zero (caller mints with the typed
    minter), (None, "ambiguous"/"dropped_*") otherwise. Shares one identity authority with
    resolve_rows so a take/move BINDS the scene's object instead of spawning a twin (Cx 304 #1)."""
    low = (mention or "").strip().lower()
    if is_deixis(low):
        return protagonist, "deixis_bound"
    from construct.turnloop import _names_entity
    want = f"{kind}:" if kind in ("place", "obj", "person") else ""
    hits = []
    for c in candidates:
        if not isinstance(c, str) or ":" not in c:
            continue
        # CHANNEL TYPING (Cx 304): a move binds only a place, a take only an obj — never a mistyped
        # twin (binding `obj:street` for a move is the location desync; mint `place:street` instead).
        if want and not c.startswith(want):
            continue
        if _names_entity(c, low, name=str(name_of(c) or "")):
            hits.append(c)
    hits = list(dict.fromkeys(hits))
    if len(hits) == 1:
        return hits[0], "bound"
    if len(hits) > 1:
        return None, "ambiguous"
    return None, "mint"
