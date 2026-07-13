"""WORLD-GROWTH G1 — the activation adaptor and the growth-chunk assembly.

The host half of the ACTIVATION CONTRACT (docs/design/WORLD-GROWTH.md §3):
growth chunks become visible canon ALL OR NONE through PB's atomic
envelope (ATOMIC-ACTIVATION-V1: `ingest_structured(items, atomic=True)`
sugar over `commit_set`). Until that primitive ships, this adaptor FAILS
CLOSED — it detects capability absence BEFORE writing anything and
returns `activation_unavailable`: zero rows, zero displacement, zero
clock/route change, the caller renders the non-diegetic technical seam.

cr's build boundary (activation-delta review, 2026-07-13), honored here
structurally: NO reachable Growth path may call the non-atomic ingest —
this module is the only door, and this door refuses non-atomic engines.
Item ORDER is contractual under the envelope's staged-prefix gating:
declarations/parents precede references/children (`ordered_chunk_items`
owns that ordering deterministically).
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActivationResult:
    """The adaptor's outcome — receipts are RETURN VALUES, never rows."""

    ok: bool
    reason: str = ""            # "" on success; machine-readable otherwise
    receipts: tuple = ()        # engine receipt rows on success (as returned)


def _capability(p) -> str:
    """Which atomic surface does this engine expose? "commit_set" |
    "atomic_ingest" | "" (none). Detection is conservative and BOUND TO
    THE SURFACE THAT WILL BE CALLED (cr: never infer safety from one
    surface and invoke another): commit_set must be callable;
    atomic_ingest requires an EXPLICIT NAMED `atomic` parameter — a broad
    **kwargs ingest that would silently swallow the flag is NOT capable.
    Absent, ambiguous, or unreadable → "" (fail closed)."""
    try:
        if callable(getattr(p, "commit_set", None)):
            return "commit_set"
        sig = inspect.signature(p.ingest_structured)
        param = sig.parameters.get("atomic")
        if param is not None and param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY):
            return "atomic_ingest"
        return ""
    except Exception:  # noqa: BLE001 — unreadable surface is not capable
        return ""


def atomic_capable(p) -> bool:
    return _capability(p) != ""


def _affirmative_success(receipt, n_items: int) -> tuple[bool, str, tuple]:
    """ATOMIC-ACTIVATION-V1 r2 permits TYPED FAILURE RETURNS — success
    must be affirmative, never inferred from the absence of an exception
    (cr: an {outcome: aborted} return must not read as ok). Rejects an
    explicit failure outcome, any skipped ops, empty rows for a nonempty
    chunk, and any ambiguous shape."""
    if isinstance(receipt, dict):
        outcome = str(receipt.get("outcome", "")).lower()
        skipped = receipt.get("skipped") or ()
        rows = tuple(receipt.get("rows") or ())
    else:
        outcome = str(getattr(receipt, "outcome", "") or "").lower()
        skipped = getattr(receipt, "skipped", None) or ()
        rows = tuple(getattr(receipt, "rows", None) or ())
    if outcome and outcome not in ("ok", "committed", "success"):
        return False, f"engine_outcome:{outcome}", rows
    if skipped:
        return False, "engine_skipped_ops", rows
    if n_items and not rows:
        return False, "ambiguous_receipt:no_rows", rows
    return True, "", rows


def activate_chunk(p, items: list[dict]) -> ActivationResult:
    """Commit one growth chunk atomically, or refuse before writing.

    On a non-atomic engine (PB 0.2.0): `activation_unavailable`, nothing
    written — a torn prefix is never an accepted runtime behavior. On an
    atomic engine: one envelope call; any engine-side abort surfaces as a
    failed result with the engine's receipts (still nothing visible, by
    the envelope's own contract)."""
    if not items:
        return ActivationResult(ok=False, reason="empty_chunk")
    cap = _capability(p)
    if not cap:
        logger.warning("growth activation unavailable: engine has no atomic "
                       "envelope (%d items withheld — nothing written)",
                       len(items))
        return ActivationResult(ok=False, reason="activation_unavailable")
    try:
        if cap == "commit_set":
            # dispatch the surface that was DETECTED (never the sugar path
            # through a possibly-broad legacy ingest)
            receipt = p.commit_set([{"op": "assert", "item": i} for i in items])
        else:
            receipt = p.ingest_structured(items, atomic=True)
    except Exception as exc:  # noqa: BLE001 — an aborted set is a clean refusal
        logger.warning("growth activation aborted by the engine: %s", exc)
        return ActivationResult(ok=False, reason=f"engine_abort:{exc}")
    ok, reason, rows = _affirmative_success(receipt, len(items))
    if not ok:
        logger.warning("growth activation not affirmed: %s", reason)
        return ActivationResult(ok=False, reason=reason, receipts=rows)
    return ActivationResult(ok=True, receipts=rows)


def ordered_chunk_items(*, place: list[dict] | None = None,
                        containment: list[dict] | None = None,
                        passage: list[dict] | None = None,
                        moves: list[dict] | None = None,
                        encounter: list[dict] | None = None,
                        texture: list[dict] | None = None) -> list[dict]:
    """The growth chunk in CONTRACTUAL order (staged-prefix gating makes
    order semantic, not cosmetic): declarations and parents strictly
    before references and children — place stubs, then containment (incl.
    a G3 ancestry insertion's region-before-place pair, which the caller
    supplies in that order), then the passage/connection, then actor
    moves (protagonist + ALL standing companions — one set, §3's
    companion postcondition), then encounter stubs, then texture."""
    out: list[dict] = []
    for part in (place, containment, passage, moves, encounter, texture):
        if part:
            out.extend(part)
    return out


def strict_flag(value) -> bool:
    """The strict signal parser (cr piece-2 finding 1): ONLY the literal
    boolean True is true — strings ("false", "true"), numbers, and every
    other shape read False. Model-supplied flags gate canon mutation and
    must never fail open through truthiness."""
    return value is True


#: The CLOSED pipeline-outcome contract (cr piece-2 finding 2): exactly one
#: value permits growth — "miss", produced only AFTER the ordinary pipeline
#: (refer + known-place + semantic-bind) ran to completion and found
#: nothing. None/""/unknown/error are uninitialized-or-failed sentinels and
#: FORBID growth; the answered states forbid it because the world already
#: spoke: resolved / ambiguous / blocked / undiscovered / same_place /
#: fixture.
PIPELINE_MISS = "miss"


def growth_eligibility(*, kind: str, committed: bool, moves_open: bool,
                       seeks_encounter: bool,
                       pipeline_outcome: str | None,
                       host_deny: str | None = None) -> str | None:
    """The CONJUNCTIVE, ORDERED gate (spec §5; cr: a classifier boolean must
    never by itself authorize canon mutation). Returns the growth MODE
    ("place" | "encounter") when every condition holds, else None:

    1. an in-world, COMMITTED action turn (never hypothetical/negated/
       deliberative/OOC/question — the caller passes `committed` from the
       classify kind + its own guards);
    2. the ordinary pipeline ran FIRST and PROVED the miss —
       `pipeline_outcome` must be exactly PIPELINE_MISS ("miss"), a value
       produced only after refer/known-place/semantic-bind completed and
       found nothing; None/""/unknown/error are uninitialized-or-failed
       sentinels and forbid growth, as does every answered state;
    3. the host's NO-GROWTH check found no structural deny (`host_deny`
       is the enumerated provable reason, or None — a model opinion is
       never one);
    4. and a trigger signal fired (encounter outranks place when both —
       the player's stated aim is the person, the road serves it).

    Pure and explicit (the salient_moments discipline): no reads, no
    hidden state — the turnloop wiring slice supplies every input.
    """
    if kind != "action" or committed is not True:
        return None
    if pipeline_outcome != PIPELINE_MISS:
        return None  # the ONLY permitting value; everything else forbids
    if host_deny:
        return None
    if seeks_encounter is True:
        return "encounter"
    if moves_open is True:
        return "place"
    return None


#: Model display fields must be PLAIN WORDS: an id token ANYWHERE in a
#: persisted field is an authority escape (the model naming/referencing
#: entities), as is markup. Search, never fullmatch (cr piece-3: the
#: embedded "waypost at place:secret_ford" must decline too).
_ID_TOKEN = __import__("re").compile(r"\b[a-z_]+:[a-z0-9_]+\b|[{}<>`]")

#: Field length bound — display lines, not documents.
_MAX_FIELD = 200


@dataclass(frozen=True)
class GrowthProposal:
    """The VALIDATED Assessor proposal — display fields only, host-checked;
    the row-assembly step (its own piece) turns this into ordered items
    with host-allocated ids."""

    assessment: str
    confidence: float
    place: dict | None = None       # {name, identity, parent_index}
    encounter: dict | None = None   # {name, role, drive, doing, companion?}
    texture: tuple = ()


def _field(obj: dict, path: str, key: str, leaks) -> tuple[str | None, str]:
    """One persisted model field: EXACT string type (no coercion-as-repair),
    nonempty, bounded, id-token-free anywhere, and concealment-screened by
    the HOST-SUPPLIED leak predicate. Returns (value, "") or (None, reason)
    with a field-qualified reason the wiring receipt can act on."""
    v = obj.get(key)
    if type(v) is not str:
        return None, f"malformed:{path}.{key}_type"
    v = v.strip()
    if not v:
        return None, f"malformed:{path}.{key}_empty"
    if len(v) > _MAX_FIELD:
        return None, f"malformed:{path}.{key}_length"
    if _ID_TOKEN.search(v):
        return None, f"unlicensed:{path}.{key}_id"
    if leaks(v):
        return None, f"unlicensed:{path}.{key}_concealed"
    return v, ""


def _clean(obj, path: str, fields: tuple, leaks) -> tuple[dict | None, str]:
    if type(obj) is not dict:
        return None, f"malformed:{path}_type"
    out = {}
    for f in fields:
        v, why = _field(obj, path, f, leaks)
        if v is None:
            return None, why
        out[f] = v
    return out, ""


def validated_proposal(raw: dict, *, mode: str, n_ancestry_options: int,
                       leaks, min_confidence: float = 0.35
                       ) -> tuple["GrowthProposal | None", str]:
    """The host gate over the Assessor's output (spec §3; cr piece-3
    hardening). Structural AUTHORITY checks — plausibility was the model's
    job: id tokens anywhere in any persisted field decline; every field is
    screened by the HOST-SUPPLIED concealment predicate (`leaks`, built
    from the arc's protected/concealed vocabulary — the model never sees
    the hidden words, the host applies them). `leaks` is REQUIRED with no
    permissive default: this boundary fails closed, and a genuinely
    vocabulary-free arc must say so explicitly (`lambda text: False`).
    The host-gate parameters themselves are validated — a malformed gate
    (NaN/None/bool threshold, bool/float option count, non-callable
    predicate) is a HOST bug and raises ValueError rather than quietly
    defeating the invariants. parent_index must be exactly
    an int strictly inside the host option count (no fallback option — the
    host names a wider-world option explicitly if legal); mode must be
    exactly place|encounter; texture is a real list of 1-3 exact strings
    (overage DECLINES, never truncates — a proposal failure is not a host
    repair opportunity); confidence must be a real finite number in [0,1]
    (bool excluded) and BELOW `min_confidence` declines
    `proposal:low_confidence` — LOW never emerges as an accepted proposal
    for a later caller to forget. Every decline is a stable
    field-qualified retryable reason."""
    import math
    if not callable(leaks):
        raise ValueError("growth gate: leaks must be a callable predicate "
                         "(pass `lambda text: False` for a vocabulary-free "
                         "arc — concealment screening is never optional)")
    if type(n_ancestry_options) is not int:
        raise ValueError("growth gate: n_ancestry_options must be an exact "
                         f"int, got {type(n_ancestry_options).__name__}")
    if type(min_confidence) not in (int, float) \
            or isinstance(min_confidence, bool) \
            or not math.isfinite(float(min_confidence)) \
            or not (0.0 <= float(min_confidence) <= 1.0):
        raise ValueError("growth gate: min_confidence must be a finite real "
                         f"in [0,1], got {min_confidence!r}")
    min_confidence = float(min_confidence)
    if mode not in ("place", "encounter"):
        return None, "malformed:mode"
    if type(raw) is not dict:
        return None, "malformed:proposal_type"
    assessment = raw.get("assessment")
    if type(assessment) is not str or not assessment.strip():
        return None, "malformed:assessment"
    assessment = assessment.strip()

    conf = raw.get("confidence")
    if type(conf) not in (int, float) or isinstance(conf, bool) \
            or not math.isfinite(float(conf)) or not (0.0 <= float(conf) <= 1.0):
        return None, "malformed:confidence"
    confidence = float(conf)
    if confidence < min_confidence:
        return None, "proposal:low_confidence"

    place = None
    place_raw = raw.get("place")
    if place_raw is not None:
        if n_ancestry_options < 1:
            return None, "unlicensed:place.no_ancestry_options"
        place, why = _clean(place_raw, "place", ("name", "identity"), leaks)
        if place is None:
            return None, why
        pi = place_raw.get("parent_index")
        if type(pi) is not int:
            return None, "malformed:place.parent_index_type"
        if not (0 <= pi < n_ancestry_options):
            return None, "unlicensed:place.parent_index_range"
        place["parent_index"] = pi

    encounter = None
    enc_raw = raw.get("encounter")
    if enc_raw is not None:
        encounter, why = _clean(enc_raw, "encounter",
                                ("name", "role", "drive", "doing"), leaks)
        if encounter is None:
            return None, why
        comp_raw = enc_raw.get("companion")
        if comp_raw is not None:
            comp, why = _clean(comp_raw, "encounter.companion",
                               ("name", "kind", "bond"), leaks)
            if comp is None:
                return None, why
            encounter["companion"] = comp

    if mode == "encounter" and encounter is None:
        return None, "malformed:encounter_required"
    if mode == "place" and place is None:
        return None, "malformed:place_required"

    tex_raw = raw.get("texture")
    if type(tex_raw) is not list:
        return None, "malformed:texture_type"
    if not (1 <= len(tex_raw) <= 3):
        return None, ("malformed:texture_too_many" if len(tex_raw) > 3
                      else "malformed:texture_empty")
    texture = []
    for i, t in enumerate(tex_raw):
        if type(t) is not str or not t.strip():
            return None, f"malformed:texture.{i}_type"
        t = t.strip()
        if len(t) > _MAX_FIELD:
            return None, f"malformed:texture.{i}_length"
        if _ID_TOKEN.search(t):
            return None, f"unlicensed:texture.{i}_id"
        if leaks(t):
            return None, f"unlicensed:texture.{i}_concealed"
        texture.append(t)
    return GrowthProposal(assessment=assessment, confidence=confidence,
                          place=place, encounter=encounter,
                          texture=tuple(texture)), ""


# ---------------------------------------------------------------------------
# Piece 4 — HOST ROW ASSEMBLY (spec §3 host gates): the model proposed
# DISPLAY FIELDS only; here the HOST allocates collision-free ids under the
# global identity authority and builds every row of the growth chunk as one
# HOST-BUILT BATCH in the contractual order (`ordered_chunk_items`). Nothing
# here writes — the caller hands the items to `activate_chunk` (all-or-none).

import math as _math
import re as _re


@dataclass(frozen=True)
class AssembledChunk:
    """One growth chunk, host-built and ready for atomic activation.
    `assessment` rides along for the receipt/audit trail (doctrine 3: the
    chunk cites its derivation) — it is NEVER a row and never rendered
    verbatim."""

    items: tuple                # ordered rows for activate_chunk
    assessment: str
    place_id: str = ""          # host-allocated (empty when no new place)
    person_id: str = ""
    companion_id: str = ""


def _slugify(name: str) -> str:
    return _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _alloc(prefix: str, name: str, exists, taken: set) -> str:
    """Collision-free id under the global identity authority: the canon
    roster (`exists`) AND this chunk's own allocations (`taken`) — a grown
    person and their same-named companion must not collide intra-chunk.
    Ordinal probe, the D3 re-mint pattern."""
    slug = _slugify(name)
    if not slug:
        return ""
    cand = f"{prefix}:{slug}"
    n = 1
    while cand in taken or exists(cand):
        n += 1
        cand = f"{prefix}:{slug}_{n}"
    taken.add(cand)
    return cand


def _entity_row(entity: str, attribute: str, value: str, at: float) -> dict:
    return {"entity": entity, "attribute": attribute, "value": value,
            "value_type": "entity", "valid_from": at}


def assemble_chunk(prop: GrowthProposal, *, mode: str, origin: str,
                   ancestry_options: list, protagonist: str,
                   companions: list, at: float, exists
                   ) -> tuple["AssembledChunk | None", str]:
    """Validated proposal → the ordered, host-built row batch.

    Host-supplied truth: `origin` (the place the player walks FROM — the
    passage's far end and the encounter anchor when no new place is grown),
    `ancestry_options` (the SAME existing-place list whose indexes the
    proposal was validated against — the parent is host truth, never model
    text), `companions` (ALL standing companions selected at the pre-move
    horizon: the §3 companion postcondition puts their moves in the SAME
    atomic set), `at` (the turn's valid_from), `exists` (the canon roster
    membership predicate backing id allocation).

    Malformed HOST inputs raise ValueError (a host bug must fail loudly,
    the piece-3 posture); a proposal defect that only assembly can see
    (an unsluggable display name) DECLINES retryably. Row facts:
    - the new place is declared (kind/name) with its `description` set to
      the proposed identity — `furnish_scene` sees a described place and
      STANDS DOWN (spec §3: one texture owner);
    - containment nests it in the host-picked parent; the passage commits
      `connects_to` BOTH WAYS (the road walked is walkable back);
    - the protagonist AND every standing companion move in the same set;
    - the encounter person is ANCHORED (`in` the grown place, else the
      origin — never prose-only), their companion bonded via
      `accompanying` (the standing presence machinery's own state);
    - texture lands as distinct `detail_<at>_N` rows on the anchor place:
      distinct within the chunk (same-attribute rows would supersede, and
      three facts must not collapse to one) AND across chunks (a later
      encounter on the same road must never supersede an earlier chunk's
      texture — growth is canon, forever); `at` is unique per chunk
      because one generative act per turn is the budget contract.
    """
    if not isinstance(prop, GrowthProposal):
        raise ValueError("growth assembly: prop must be a GrowthProposal")
    if mode not in ("place", "encounter"):
        raise ValueError(f"growth assembly: unknown mode {mode!r}")
    if not callable(exists):
        raise ValueError("growth assembly: exists must be the canon roster "
                         "membership predicate")
    if type(origin) is not str or not origin.startswith("place:"):
        raise ValueError(f"growth assembly: origin must be a place id, got "
                         f"{origin!r}")
    if type(protagonist) is not str or not protagonist.startswith("person:"):
        raise ValueError("growth assembly: protagonist must be a person id, "
                         f"got {protagonist!r}")
    if type(companions) is not list or any(
            type(c) is not str or not c.startswith("person:")
            for c in companions):
        raise ValueError("growth assembly: companions must be a list of "
                         "person ids")
    if type(at) not in (int, float) or isinstance(at, bool) \
            or not _math.isfinite(float(at)) or float(at) < 0:
        raise ValueError(f"growth assembly: at must be a finite non-negative "
                         f"time, got {at!r}")
    at = float(at)

    taken: set = set()
    place_rows: list[dict] = []
    containment: list[dict] = []
    passage: list[dict] = []
    place_id = ""
    if prop.place is not None:
        if type(ancestry_options) is not list or not ancestry_options or any(
                type(o) is not str or not o.startswith("place:")
                for o in ancestry_options):
            raise ValueError("growth assembly: ancestry_options must be a "
                             "nonempty list of place ids")
        pi = prop.place["parent_index"]
        if not (0 <= pi < len(ancestry_options)):
            raise ValueError("growth assembly: parent_index outside the "
                             "supplied ancestry_options — the validation and "
                             "assembly lists disagree (host bug)")
        place_id = _alloc("place", prop.place["name"], exists, taken)
        if not place_id:
            return None, "malformed:place.name_unsluggable"
        place_rows = [
            {"entity": place_id, "attribute": "kind", "value": "place",
             "timeless": True},
            {"entity": place_id, "attribute": "name",
             "value": prop.place["name"][:60]},
            {"entity": place_id, "attribute": "description",
             "value": prop.place["identity"]},
        ]
        containment = [_entity_row(place_id, "in", ancestry_options[pi], at)]
        passage = [_entity_row(origin, "connects_to", place_id, at),
                   _entity_row(place_id, "connects_to", origin, at)]

    anchor = place_id or origin
    encounter_rows: list[dict] = []
    person_id = companion_id = ""
    if prop.encounter is not None:
        person_id = _alloc("person", prop.encounter["name"], exists, taken)
        if not person_id:
            return None, "malformed:encounter.name_unsluggable"
        encounter_rows = [
            {"entity": person_id, "attribute": "kind", "value": "person",
             "timeless": True},
            {"entity": person_id, "attribute": "name",
             "value": prop.encounter["name"][:60]},
            {"entity": person_id, "attribute": "role",
             "value": prop.encounter["role"]},
            {"entity": person_id, "attribute": "drive",
             "value": prop.encounter["drive"]},
            {"entity": person_id, "attribute": "doing",
             "value": prop.encounter["doing"]},
            _entity_row(person_id, "in", anchor, at),
        ]
        comp = prop.encounter.get("companion")
        if comp is not None:
            companion_id = _alloc("person", comp["name"], exists, taken)
            if not companion_id:
                return None, "malformed:encounter.companion.name_unsluggable"
            encounter_rows += [
                {"entity": companion_id, "attribute": "kind",
                 "value": comp["kind"], "timeless": True},
                {"entity": companion_id, "attribute": "name",
                 "value": comp["name"][:60]},
                {"entity": companion_id, "attribute": "bond",
                 "value": comp["bond"]},
                _entity_row(companion_id, "in", anchor, at),
                _entity_row(companion_id, "accompanying", person_id, at),
            ]

    # the player's own displacement + the companion postcondition: ALL
    # standing companions move in the SAME atomic set — a place chunk with
    # no move is a map annotation, not a walk, so moves exist only when a
    # new place does (an encounter comes TO the road; nobody teleports).
    moves: list[dict] = []
    if place_id:
        moves = [_entity_row(protagonist, "in", place_id, at)]
        moves += [_entity_row(c, "in", place_id, at) for c in companions]

    texture = [{"entity": anchor, "attribute": f"detail_{int(at)}_{i + 1}",
                "value": t, "valid_from": at}
               for i, t in enumerate(prop.texture)]

    items = ordered_chunk_items(place=place_rows, containment=containment,
                                passage=passage, moves=moves,
                                encounter=encounter_rows, texture=texture)
    return AssembledChunk(items=tuple(items), assessment=prop.assessment,
                          place_id=place_id, person_id=person_id,
                          companion_id=companion_id), ""
