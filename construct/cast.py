"""The populated cast — the surface pillars fill through (STORY-SHAPES §8, CATALOG §0).

Host-side control data over the engine's `knows:<npc>` frames; ZERO new PB primitive.
A `CastNode` points at ordinary facts an NPC surfaces in dialogue (`Clue.surface_fact`);
the clue/pillar metadata stays host-side. ONE generic schema across all nine shapes
(§8.3) — only the labels differ by shape (witness/rival/guide/...). The deterministic
solvability check (§8.2) guarantees every required pillar is reachable through genuine
clues and that red herrings never block the minimum solvable path.

The bridge to the conclusion engine: a clue learned in play is written as an ordinary
fact into `knows:<protagonist>`; `build_pillars` turns each pillar's distributed clues
into `genuine_via`/`false_via` Exprs over the player frame, so `executor.arc_coverage`
reads coverage with no engine involvement. Interviewing the cast IS how pillars fill.
"""

from __future__ import annotations

from dataclasses import dataclass

from construct.arc.conditions import AnyOf, InFrame
from construct.arc.grammar import Pillar

#: Coverage effect a clue has on its pillar when surfaced into the player frame.
COVERAGE_EFFECTS = ("genuine", "false", "context")
#: How a clue becomes available (the cost/condition of learning it).
REVEAL_MODES = ("volunteered", "pressed", "traded", "contradicted")
#: ASK channel: none/trust/pressure (questioning a person). EXAMINE channel (EXAMINE-CHANNEL.md):
#: `examined` (a look at the object surfaces it) and `scrutiny` (close inspection earns it — the
#: EXAMINE analogue of `pressure`). `object_seen` stays a HOOK/glance/ambient condition, NEVER
#: required evidence (Cx 073).
REVEAL_CONDITIONS = ("none", "trust", "pressure", "object_seen", "examined", "scrutiny")
#: The reveal conditions LIVE delivery supports — the solvability gate counts ONLY these (a clue
#: gated on an un-delivered signal is NOT live-reachable; Cx 032 blocker 2). ASK delivers
#: none/pressure; the EXAMINE channel (turnloop examine-delivery) delivers examined/scrutiny.
#: `object_seen`/`trust` are NOT live (hooks/glances/unwired) — never count for required evidence.
LIVE_REVEAL_CONDITIONS = frozenset({"none", "pressure", "examined", "scrutiny"})


@dataclass(frozen=True)
class Clue:
    """A piece a cast member holds that, when surfaced, advances (or misleads) a
    pillar. `surface_fact` (entity, attribute, value) is the ordinary fact seeded
    into the holder's `knows:<npc>` frame and, once learned, written into
    `knows:<protagonist>`. `coverage_effect`: 'genuine' (a true cause), 'false' (a
    red herring held as a cause), 'context' (texture — can never false-fill a pillar
    on its own). A STRONG red herring (`is_red_herring` + effect 'false') MUST name a
    reachable `debunked_by` clue (§8.2)."""

    clue_id: str
    pillar_id: str
    surface_fact: tuple[str, str, str]
    coverage_effect: str = "genuine"
    is_red_herring: bool = False
    reveal_mode: str = "volunteered"
    reveal_condition: str = "none"
    debunked_by: str | None = None
    #: The non-spoiling HOOK (CARD-WEAVING.md / Cx 039): the "why this is worth pursuing"
    #: teaser the narrator may pepper to PROPOSE this card without delivering it — e.g.
    #: "the heir flinches when the will is mentioned". CRITICAL safety seam: the hook is NOT
    #: the `surface_fact`. Proposing a hook informs the player's choice; it must NEVER fill a
    #: pillar or mirror a protected answer into the player frame (only authorized DELIVERY —
    #: interview → `learn_clue_items` — does that). Empty = no authored hook (not floor-bearing).
    hook_text: str = ""


@dataclass(frozen=True)
class CastNode:
    """One important cast member (host-side profile over `knows:<npc>`). `shape_role`
    is the shape-specific label (witness/suspect for Deduction, rival/mentor for
    Contest, guide for Discovery, …) — the SAME schema, different label (§8.3).
    `holds_clues` are the pieces engaging this member surfaces."""

    node_id: str
    shape_role: str = "witness"
    surface_role: str = ""
    holds_clues: tuple[Clue, ...] = ()
    #: Where this member is in PLAY, so they can actually be reached (INVESTIGATION-SHAPE.md
    #: §3a; the live whodunit failed because cast NPCs had no location → "no location is never
    #: present" → unreachable). 'at_scene' = present at the crime scene from turn 1 (lives
    #: there / reported it); 'nearby' = elsewhere in the same site, reachable by movement;
    #: 'offscene' = elsewhere, reachable only after discovery opens a route. Resolves to an
    #: ordinary sourced `in` fact (`cast_location_plan`), never a derived roster.
    presence: str = "nearby"
    #: The place entity this member is in (a `place:*` id). For 'at_scene' the host overrides
    #: this with the crime-scene place; for nearby/offscene it's their authored whereabouts.
    location: str = ""
    #: Whether this member is THE FIRST WITNESS — the at_scene figure who introduces the cast
    #: of characters in the opening (genre-faithful spoon-feed; §3b). At most one per cast.
    first_witness: bool = False
    #: Whether this member is the CULPRIT (the solution subject). The explicit deterministic
    #: subject the staging gate proves reachable (Cx 057 #2) — without it the gate can't prove
    #: the genre promise that the actual culprit surfaces as involved. At most one per cast.
    is_culprit: bool = False


#: The presence tiers a cast member can occupy in play (INVESTIGATION-SHAPE.md §3a).
PRESENCE_TIERS = ("at_scene", "nearby", "offscene")


def all_clues(cast: tuple[CastNode, ...]) -> list[Clue]:
    """Every clue held across the cast, flattened."""
    return [c for node in cast for c in node.holds_clues]


def clues_for_pillar(pillar_id: str, cast: tuple[CastNode, ...]) -> list[Clue]:
    return [c for c in all_clues(cast) if c.pillar_id == pillar_id]


def _live_reachable(clue: Clue) -> bool:
    """A clue v1 interview delivery can actually surface: its reveal_condition is in
    `LIVE_REVEAL_CONDITIONS` (Cx 032 blocker 2). Used by the solvability gate so it never
    counts a `trust`/`object_seen`-gated clue that can't be reached in play today."""
    return clue.reveal_condition in LIVE_REVEAL_CONDITIONS


def genuine_reachable(pillar_id: str, cast: tuple[CastNode, ...]) -> int:
    """How many genuine, non-red-herring, LIVE-reachable clues across the cast cover this
    pillar — the §8.2 reachability count (≥1 required per required pillar). A clue behind an
    unsupported gate (trust/object_seen) does NOT count (Cx 032 blocker 2)."""
    return sum(1 for c in clues_for_pillar(pillar_id, cast)
               if c.coverage_effect == "genuine" and not c.is_red_herring
               and _live_reachable(c))


def _reachable_nodes(cast: tuple[CastNode, ...]) -> set[str]:
    """The set of cast members PHYSICALLY reachable in play (INVESTIGATION-SHAPE.md §3d).
    Seed = `at_scene` members ∪ `nearby` members with a referable place (reachable from the
    scene NOW). Then a fixpoint: an `offscene` (or any placed) member becomes reachable once a
    LIVE-DELIVERABLE clue held by an ALREADY-reachable member NAMES them (their node_id appears
    as the entity or value of that clue's surface_fact = the discovery chain) AND they have a
    place to travel to. The naming clue must itself be live-reachable (reveal_condition ∈
    LIVE_REVEAL_CONDITIONS) — a `trust`/`object_seen` edge the turn loop can't surface is a DEAD
    edge and must NOT confer reachability (Cx 061 #2). A member with no place to go to is never
    reachable (Cx 057: `nearby`-without-place ≡ offscene; an unplaced offscene member is
    stranded)."""
    by_id = {n.node_id: n for n in cast}

    def _locatable(n: CastNode) -> bool:
        return n.presence == "at_scene" or bool(n.location)

    reachable = {n.node_id for n in cast
                 if n.presence == "at_scene" or (n.presence == "nearby" and n.location)}
    changed = True
    while changed:
        changed = False
        for n in cast:
            if n.node_id in reachable or not _locatable(n):
                continue
            named = any(n.node_id in (c.surface_fact[0], c.surface_fact[2])
                        for rid in reachable for c in by_id[rid].holds_clues
                        if _live_reachable(c))
            if named:
                reachable.add(n.node_id)
                changed = True
    return reachable


def check_solvability(required_pillar_ids: list[str], cast: tuple[CastNode, ...],
                      known_ids: set | None = None,
                      require_staging: bool = False) -> list[str]:
    """The §8.2 CI check (Cx 032-hardened). Returns problems (empty = solvable):
    - every required pillar has ≥1 genuine clue that is LIVE-reachable (a supported
      reveal_condition) — never one stranded behind trust/object_seen;
    - every STRONG red herring (effect 'false') has a `debunked_by` that EXISTS and is
      itself live-reachable (an unreachable debunker can't correct the wrong case);
    - when `known_ids` is given, every clue's HOLDER is a real/reachable entity (a clue on
      a non-present phantom can never be interviewed).

    When `require_staging` (the Deduction investigation-shape gate, INVESTIGATION-SHAPE.md
    §3d, Cx 057), ALSO require: every required pillar's genuine clue is held by a PHYSICALLY
    reachable member; an explicit culprit (`is_culprit`) exists and is reachable; and the
    opening-promise holds (≥1 `at_scene` first witness, ≥2 `at_scene` members)."""
    problems: list[str] = []
    by_id = {c.clue_id: c for c in all_clues(cast)}
    for pid in required_pillar_ids:
        if genuine_reachable(pid, cast) < 1:
            problems.append(f"pillar {pid}: no genuine LIVE-reachable clue "
                            f"(check reveal_condition ∈ {sorted(LIVE_REVEAL_CONDITIONS)})")
    for node in cast:
        if known_ids is not None and node.holds_clues and node.node_id not in known_ids:
            problems.append(f"cast member {node.node_id}: not a known/reachable entity")
        for c in node.holds_clues:
            if c.is_red_herring and c.coverage_effect == "false":
                deb = by_id.get(c.debunked_by) if c.debunked_by else None
                if not c.debunked_by:
                    problems.append(f"strong red herring {c.clue_id}: missing debunked_by")
                elif deb is None:
                    problems.append(
                        f"red herring {c.clue_id}: debunked_by {c.debunked_by!r} is unreachable")
                elif not _live_reachable(deb):
                    problems.append(
                        f"red herring {c.clue_id}: debunker {c.debunked_by!r} is gated behind "
                        f"an unsupported reveal_condition ({deb.reveal_condition})")
    if require_staging:
        reachable = _reachable_nodes(cast)
        req = set(required_pillar_ids)
        # Blocker 1 (Cx 061): EVERY holder of a genuine, live-reachable, required clue must be
        # physically reachable — not just one per pillar. A genuine required clue on an
        # unreachable holder is a dead card (the player can pursue it and hit a wall), the
        # exact "important member holds a live clue but can never be interviewed" failure.
        for node in cast:
            if node.node_id in reachable:
                continue
            for c in node.holds_clues:
                if (c.pillar_id in req and c.coverage_effect == "genuine"
                        and not c.is_red_herring and _live_reachable(c)):
                    problems.append(f"holder {node.node_id}: holds a genuine required clue "
                                    f"({c.clue_id}) but is PHYSICALLY unreachable in play "
                                    f"(no at_scene/nearby place / no live naming chain)")
                    break
        # Singleton subjects (Cx 061 #4): exactly ONE culprit and exactly ONE first witness —
        # multiple culprits means the solution's deterministic subject is no longer singular.
        culprits = [n for n in cast if n.is_culprit]
        if len(culprits) != 1:
            problems.append(f"staging: need exactly ONE is_culprit, found {len(culprits)} "
                            f"(the solution subject must be singular)")
        for cu in culprits:
            if cu.node_id not in reachable:
                problems.append(f"culprit {cu.node_id}: not physically reachable in play "
                                f"(stranded offscene with no live naming chain)")
        at_scene = [n for n in cast if n.presence == "at_scene"]
        if len(at_scene) < 2:
            problems.append(f"opening promise: need ≥2 at_scene members, found {len(at_scene)}")
        first_witnesses = [n for n in cast if n.first_witness]
        if len(first_witnesses) != 1:
            problems.append(f"opening promise: need exactly ONE first_witness, found "
                            f"{len(first_witnesses)} (the witness who introduces the cast)")
        elif first_witnesses[0].presence != "at_scene":
            problems.append(f"opening promise: first_witness {first_witnesses[0].node_id} is "
                            f"not at_scene (they must be present to introduce the cast)")
    return problems


def validate_signature_support(shapes, cast: tuple[CastNode, ...]) -> list[str]:
    """Light AUTHORING lint (GENRE-SIGNATURE-ELEMENTS.md, Cx 097): prove the genre's HARD
    signature promises actually shipped — author-insist via prompt can ASK, this CHECKS the
    fairness promises players get stuck on. NOT a per-element engine; reuses existing material.
    Returns problems (empty = ok). `shapes` is the world's shape list (primary + secondary).

    Lints DEDUCTION for v1 (it has the live baseline): a strong red herring must EXIST (its
    debunker reachability is `check_solvability`'s job) and a cross-suspicion edge must exist
    (some clue's fact references ANOTHER cast member). Other shapes are prompt + live-acceptance
    only — grow a lint only where live validation shows a concrete gap (don't pre-build checks)."""
    shapes = [shapes] if isinstance(shapes, str) else list(shapes or [])
    problems: list[str] = []
    if "deduction" in shapes:
        clues = all_clues(cast)
        if not any(c.is_red_herring and c.coverage_effect == "false" for c in clues):
            problems.append("deduction signature: no STRONG red herring present "
                            "(need a clue with is_red_herring + coverage_effect 'false') — a "
                            "mystery without a false lead rings false")
        ids = {n.node_id for n in cast}
        people = [n for n in cast if n.node_id.startswith("person:")]
        if len(people) < 2:
            problems.append(f"deduction signature: cross-suspicion needs ≥2 suspect/person "
                            f"nodes, found {len(people)}")
        elif not any(_live_reachable(c) and ref in ids and ref != n.node_id
                     for n in cast for c in n.holds_clues
                     for ref in (c.surface_fact[0], c.surface_fact[2])):
            # Cx 099: the edge must be LIVE-reachable, not merely authored — a trust/object_seen
            # cross-edge can't surface under current delivery, so it doesn't count as shipped.
            problems.append("deduction signature: no LIVE-reachable cross-suspicion edge — no "
                            "live-reachable clue's fact references another cast member (the "
                            "suspects don't point at one another in play)")
    return problems


def is_solvable(required_pillar_ids: list[str], cast: tuple[CastNode, ...]) -> bool:
    return not check_solvability(required_pillar_ids, cast)


def cast_location_plan(cast: tuple[CastNode, ...], scene_place: str
                       ) -> list[dict]:
    """Session-zero STAGING (INVESTIGATION-SHAPE.md §3a/§3c-layer-1): place each cast member
    so they can actually be reached. Emits ORDINARY sourced canon facts (no derived roster, no
    reachability flag): for each member an `in` fact (`at_scene` → the crime-scene place;
    `nearby`/`offscene` → their authored `location`), PLUS a canonical definition for every
    non-scene place referenced (`kind=place` + a `name` derived from the id) so movement can
    `world.refer` to it (Cx 057: a route destination must be a referable place). A member with
    no resolvable place yields no `in` row (the staging gate flags any required holder so
    stranded). The crime-scene place is assumed already canonical (the protagonist is there)."""
    items: list[dict] = []
    places: set[str] = set()
    for node in cast:
        place = scene_place if node.presence == "at_scene" else node.location
        if not place:
            continue
        items.append({"entity": node.node_id, "attribute": "in", "value": place,
                      "value_type": "entity"})
        if place != scene_place:
            places.add(place)
    for place in sorted(places):
        name = place.split(":", 1)[-1].replace("_", " ").strip()
        items.append({"entity": place, "attribute": "kind", "value": "place"})
        if name:
            items.append({"entity": place, "attribute": "name", "value": name})
    return items


def build_pillars(pillar_specs: list[tuple[str, str, bool]],
                  cast: tuple[CastNode, ...],
                  protagonist: str) -> tuple[Pillar, ...]:
    """Turn distributed clues into Pillars whose `genuine_via`/`false_via` are Exprs
    over the PLAYER frame (`knows:<protagonist>`). A pillar is GENUINELY covered when
    ANY of its genuine clues' facts is in the player frame, and FALSELY covered when
    any of its red-herring/false clues' facts is — so coverage advances exactly as the
    player learns clues by interviewing the cast (`executor.arc_coverage` reads it).
    `pillar_specs` is [(pillar_id, label, required)]; 'context' clues feed neither
    condition (texture only)."""
    frame = f"knows:{protagonist}"
    pillars: list[Pillar] = []
    for pid, label, required in pillar_specs:
        clues = clues_for_pillar(pid, cast)
        genuine = [c for c in clues if c.coverage_effect == "genuine" and not c.is_red_herring]
        false_ = [c for c in clues if c.coverage_effect == "false"]
        genuine_via = _any_in_frame(frame, genuine)
        false_via = _any_in_frame(frame, false_)
        pillars.append(Pillar(pillar_id=pid, label=label, required=required,
                              genuine_via=genuine_via, false_via=false_via))
    return tuple(pillars)


def cast_from_proposal(proposal: dict) -> tuple[tuple[CastNode, ...],
                                                list[tuple[str, str, bool]]]:
    """Parse a generation-cohort proposal into typed objects (the bridge from the model
    call to the deterministic layer). Returns (cast, pillar_specs) where pillar_specs is
    [(pillar_id, label, required)] ready for `build_pillars`. Fail-soft: a malformed clue
    (missing the 3-part fact) is dropped, never crashes authoring — the solvability check
    is the gate that catches an under-covered result."""
    pillar_specs: list[tuple[str, str, bool]] = []
    for p in proposal.get("pillars", []):
        pid = p.get("id")
        if pid:
            pillar_specs.append((pid, p.get("label", ""), bool(p.get("required", True))))
    cast: list[CastNode] = []
    for n in proposal.get("cast", []):
        nid = n.get("id")
        if not nid:
            continue
        clues: list[Clue] = []
        for c in n.get("clues", []):
            f = c.get("fact") or {}
            e, a, v = f.get("entity"), f.get("attribute"), f.get("value")
            cid, pid = c.get("clue_id"), c.get("pillar_id")
            if not (cid and pid and e and a and v is not None):
                continue  # drop a malformed clue; solvability will flag any resulting gap
            clues.append(Clue(
                clue_id=cid, pillar_id=pid, surface_fact=(e, a, str(v)),
                coverage_effect=c.get("coverage_effect", "genuine"),
                is_red_herring=bool(c.get("is_red_herring", False)),
                reveal_mode=c.get("reveal_mode", "volunteered"),
                reveal_condition=c.get("reveal_condition", "none"),
                debunked_by=c.get("debunked_by") or None,
                hook_text=(c.get("hook_text") or c.get("hook") or "").strip(),
            ))
        _presence = n.get("presence", "nearby")
        if _presence not in PRESENCE_TIERS:
            _presence = "nearby"  # fail-soft to the reachable middle tier
        cast.append(CastNode(node_id=nid, shape_role=n.get("shape_role", "witness"),
                             surface_role=n.get("surface_role", ""), holds_clues=tuple(clues),
                             presence=_presence, location=(n.get("location") or "").strip(),
                             first_witness=bool(n.get("first_witness", False)),
                             is_culprit=bool(n.get("is_culprit", False))))
    return tuple(cast), pillar_specs


def floor_clues(cast: tuple[CastNode, ...],
                required_pillar_ids: list[str]) -> list[Clue]:
    """The PROPOSAL-FLOOR set (CARD-WEAVING.md §3 / Cx 039): the genuine, non-red-herring
    clues for REQUIRED pillars that carry a `hook_text`. These are the cards whose hooks
    MUST be peppered over the run so the player's choices are informed (genre proposes,
    player disposes) — the dramatic spine the live test was missing. Clues without a hook
    can't be proposed softly, so they're not floor-bearing here."""
    req = set(required_pillar_ids)
    return [c for c in all_clues(cast)
            if c.pillar_id in req and c.coverage_effect == "genuine"
            and not c.is_red_herring and c.hook_text]


def floor_debt(cast: tuple[CastNode, ...], required_pillar_ids: list[str],
               proposed_ids: set) -> list[Clue]:
    """Floor cards whose hook has NOT yet been proposed or delivered (`proposed_ids` is the
    host-tracked set of clue ids already hook_proposed|delivered). The remaining debt the
    weave governor works down — empty = the floor is satisfied, every required hook is on
    the table."""
    return [c for c in floor_clues(cast, required_pillar_ids)
            if c.clue_id not in proposed_ids]


def cast_seed_plan(cast: tuple[CastNode, ...]) -> list[tuple[str, list[dict]]]:
    """Session-zero seeding: each clue's `surface_fact` becomes an ordinary fact in its
    HOLDER's `knows:<npc>` frame — the diegetic knowledge the NPC can surface in dialogue
    (the clue/pillar metadata stays host-side, never seeded). Returns [(frame, items)] so
    the caller ingests per frame (one frame per cast member). A node with no clues yields
    no rows. This is what makes the cast genuinely KNOW the pieces the player must gather."""
    plan: list[tuple[str, list[dict]]] = []
    for node in cast:
        # ASK channel only: seed a `knows:<npc>` frame for PERSON holders. OBJECT/SITE holders
        # (EXAMINE channel, Cx 073) get NO `knows:obj` frame — their clue fact lives as PROTECTED
        # canon truth (arc_protected_keys), surfaced into the player frame only on EXAMINE delivery.
        if not node.node_id.startswith("person:"):
            continue
        items = [{"entity": e, "attribute": a, "value": v}
                 for (e, a, v) in (c.surface_fact for c in node.holds_clues)]
        if items:
            plan.append((f"knows:{node.node_id}", items))
    return plan


def learn_clue_items(clue: Clue) -> list[dict]:
    """The item(s) written into `knows:<protagonist>` when the player LEARNS a clue
    (surfaces it by interviewing the holder). Writing the `surface_fact` into the player
    frame is exactly what advances pillar coverage (`build_pillars` reads the player frame).
    The caller ingests with `frame=knows:<protagonist>`."""
    e, a, v = clue.surface_fact
    return [{"entity": e, "attribute": a, "value": v}]


def revealable_clues(node: CastNode, *, trust: bool = False, pressure: bool = False,
                     examined: bool = False, scrutiny: bool = False,
                     objects_seen: frozenset = frozenset()) -> list[Clue]:
    """The clues `node` will surface THIS interaction, gating by `reveal_condition`:
    ASK channel — 'none' always; 'trust'/'pressure' when that lever is present. EXAMINE
    channel (EXAMINE-CHANNEL.md) — 'examined' when the object is being looked at; 'scrutiny'
    when it's being CLOSELY inspected (the examine analogue of pressure). 'object_seen' when
    the relevant object is in `objects_seen` (a hook/glance, never required evidence). The host
    calls this when the player questions a person OR inspects an object, then writes each
    returned clue via `learn_clue_items`. (`scrutiny` implies `examined`.)"""
    out = []
    for c in node.holds_clues:
        cond = c.reveal_condition
        if cond == "none" \
                or (cond == "trust" and trust) \
                or (cond == "pressure" and pressure) \
                or (cond == "examined" and (examined or scrutiny)) \
                or (cond == "scrutiny" and scrutiny) \
                or (cond == "object_seen" and c.surface_fact[0] in objects_seen):
            out.append(c)
    # Truth wins the per-turn slot: genuine clues lead, then context, then false/red-herring
    # material (stable within each rank). The live whodunit run failed because a freely-
    # revealed herring ('none') sat first in the holder's list and consumed the single
    # delivery slot, starving the genuine pressure clue behind it (the player learned Orme's
    # misdirection, never his carbolic tell, and accused the wrong man). Rank on BOTH
    # coverage_effect AND is_red_herring (Cx 049 non-blocking) so a 'false'/'context' clue
    # missing the herring flag can't jump a genuine clue either. The trailing material still
    # surfaces on a later visit or when no genuine clue is left to give.
    out.sort(key=_reveal_rank)
    return out


def _reveal_rank(c: Clue) -> int:
    """Delivery priority: genuine non-herring (0) before context (1) before false/herring
    (2). Lower sorts first; stable within a rank preserves authored order."""
    if c.is_red_herring or c.coverage_effect == "false":
        return 2
    if c.coverage_effect == "context":
        return 1
    return 0


def _any_in_frame(frame: str, clues: list[Clue]):
    """AnyOf(InFrame(frame, *fact)) over the clues' surface facts, or None when empty.
    A single clue collapses to a bare InFrame (AnyOf of one is fine, but the bare atom
    keeps the serialized Expr minimal)."""
    atoms = [InFrame(frame, e, a, v) for (e, a, v) in (c.surface_fact for c in clues)]
    if not atoms:
        return None
    if len(atoms) == 1:
        return atoms[0]
    return AnyOf(tuple(atoms))
