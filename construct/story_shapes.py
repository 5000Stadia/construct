"""Story shapes — the nine engine behaviors over the 155 game types (STORY-SHAPES.md).

A game type carries narrative FLAVOR (its directive); its SHAPE is the engine behavior:
what the tension thread's medium, withheld value, commitment-capture FORM, judgment, and
payoff are. Shapes are BLENDABLE — a world has a primary shape plus secondaries (most
holodeck programs are compounds). Most types inherit their shape from their family; the
weak fits Cx flagged (Mythic/Moral → Transformation, not Discovery/Bond) are corrected
here. This is host-side control data — never canon (PB boundary, Cx 025).
"""
from __future__ import annotations

from construct.play_styles import _norm
from construct.play_styles_data import STYLE_CARDS

#: The nine shapes and their schema defaults (STORY-SHAPES.md §3/§4). Per-card profiles
#: may override any field; these are the behavior defaults a shape carries.
SHAPES: dict[str, dict] = {
    "deduction": {
        "medium": "clues, evidence, testimony, contradictions, red herrings",
        "withheld_kind": "answer", "commitment_kind": "claim",
        "judgment_type": "claim-vs-fact", "payoff_kind": "reveal"},
    "bond": {
        "medium": "emotional beats — vulnerability, friction, gesture, choice",
        "withheld_kind": "unearned_intimacy", "commitment_kind": "relational_state",
        "judgment_type": "relationship-vs-consequence", "payoff_kind": "connection_or_rupture"},
    "endurance": {
        "medium": "mounting threat, scarcity, a clock",
        "withheld_kind": "relief", "commitment_kind": "achieved_state",
        "judgment_type": "action-vs-resistance", "payoff_kind": "outlast_escape_fall"},
    "contest": {
        "medium": "escalating rounds against rivals; scouting, training, the climb",
        "withheld_kind": "the_proof", "commitment_kind": "achieved_state",
        # proof-vs-standard, NOT score-vs-objective: the scoreboard is a separate world
        # EVENT combined with pillar coverage, so "proved himself, lost the decision"
        # (Rocky) is representable (CATALOG §0 finding 5). score-vs-objective re-couples
        # the win to the scoreboard and breaks that case.
        "judgment_type": "proof-vs-standard", "payoff_kind": "win_loss_proved"},
    "gambit": {
        "medium": "leverage, maneuver, complications, misdirection",
        "withheld_kind": "hand_and_twist", "commitment_kind": "executed_action",
        "judgment_type": "plan-vs-board", "payoff_kind": "lands_or_collapses"},
    "discovery": {
        "medium": "the unfolding of place, cosmos, or meaning",
        "withheld_kind": "wonder", "commitment_kind": "understanding",
        "judgment_type": "arrival-vs-cost", "payoff_kind": "awe_understanding"},
    "mastery": {
        "medium": "incremental competence, setbacks, a standard",
        "withheld_kind": "achievement", "commitment_kind": "achieved_state",
        "judgment_type": "artifact-or-system-state", "payoff_kind": "made_thing_or_run_system"},
    "farce": {
        "medium": "compounding complications, snowballing disorder",
        "withheld_kind": "blowup", "commitment_kind": "comic_resolution",
        "judgment_type": "comic-order", "payoff_kind": "punchline_comeuppance"},
    "transformation": {
        "medium": "ordeal, choice, identity",
        "withheld_kind": "changed_self", "commitment_kind": "choice_identity",
        "judgment_type": "identity-vs-ordeal", "payoff_kind": "who_you_become"},
}

#: Family → PRIMARY shape. Cx 025 corrections honored: Mythic & Moral/Psych → Transformation
#: (ordeal/value-choice, NOT Discovery/Bond); Stewardship/Professional → Mastery (system/
#: procedure subtype); Time/Reality → Discovery primary with a Deduction streak.
FAMILY_SHAPE: dict[str, str] = {
    "Investigation & Epistemics": "deduction",
    "Puzzle, Escape & Decoding": "deduction",
    "Communication, Collection & Interpretation": "deduction",
    "Social, Relationship & Intimacy": "bond",
    "Moral, Psychological & Literary Drama": "transformation",
    "Survival, Scarcity & Endurance": "endurance",
    "Horror, Dread & the Uncanny": "endurance",
    "Action, Combat & Pursuit": "contest",
    "Competition, Status & Proving Grounds": "contest",
    "Politics, Factions & Institutions": "gambit",
    "Schemes & Infiltration": "gambit",
    "Transgression, Power & Ensemble Forms": "gambit",
    "Exploration, Wonder & Place": "discovery",
    "Time, Reality & Metafiction": "discovery",
    "Mythic, Spiritual & Symbolic": "transformation",
    "Creativity, Craft & Performance": "mastery",
    "Stewardship, Building & Management": "mastery",
    "Professional & Procedural Competence": "mastery",
    "Comedy, Farce & Chaos": "farce",
}

#: Family → default SECONDARY shapes (the blends Cx named).
FAMILY_SECONDARY: dict[str, list[str]] = {
    "Horror, Dread & the Uncanny": ["discovery"],
    "Mythic, Spiritual & Symbolic": ["discovery"],
    "Time, Reality & Metafiction": ["deduction"],
    "Moral, Psychological & Literary Drama": ["bond"],
}

#: Per-TYPE primary-shape overrides where a specific type breaks its family default.
#: (Empty for now — filled as live play surfaces a misfit; the family map is the base.)
TYPE_SHAPE: dict[str, str] = {}


#: One-line narrator discipline per shape — "earn the payoff," generalized to every
#: genre (the universal that concealment was the deduction-special-case of). Rides in
#: the narrator briefing so a romance builds intimacy (not clues) and a survival story
#: withholds relief (not an answer).
_SHAPE_LINE: dict[str, str] = {
    "deduction": "Lay a trail of clues toward the hidden answer; reveal it ONLY when the "
                 "player has assembled enough — never hand it over, and deflect demands for it.",
    "bond": "Build the relationship through earned emotional beats; the connection (or "
            "its rupture) must be EARNED — a premature declaration rings hollow and is rebuffed.",
    "endurance": "Mount the threat and the scarcity; never grant easy relief or safety — "
                 "survival is earned through play and may not come.",
    "contest": "Escalate the challenge; the victory must be fought for, never gifted — and "
               "the meaningful win may differ from the scoreboard.",
    "gambit": "Let the scheme unfold through maneuver and complication; keep your hand and "
              "the twist concealed until it lands.",
    "discovery": "Unfold the place and its meaning gradually; the wonder and the "
                 "understanding are earned through exploration, never front-loaded.",
    "mastery": "Build competence through practice and setback; the achievement is earned by "
               "accumulation, never granted.",
    "farce": "Compound the complications and let the chaos snowball toward the comic blowup "
             "— don't resolve it early.",
    "transformation": "Press the ordeal and the hard choices; the changed self must be "
                      "earned and PROVEN by action, never merely declared.",
}


#: Per-shape conclusion profile (STORY-SHAPES §0a + CATALOG §0). The three §0a
#: dimensions per engine: how the conclusion is TRIGGERED, how the cost-ledger COLORS it,
#: and the default pacing clock. `cost_disposition` is load-bearing: it tells the
#: conclusion selector how to READ coverage — `peril_redemption`/`repair`/`sacrifice`
#: read GENUINE coverage as the sound ending; `fail_forward` (comedy) INVERTS it (a
#: false-filled engine pillar = the comic engine live = the desired blowup). Per-card
#: profiles may override. Host-side control data, never canon.
SHAPE_CONCLUSION: dict[str, dict] = {
    "deduction":      {"trigger": "pillars",        "cost_disposition": "peril_redemption", "clock": "none"},
    "bond":           {"trigger": "pillars",        "cost_disposition": "repair",           "clock": "none"},
    "endurance":      {"trigger": "event_deadline", "cost_disposition": "sacrifice",        "clock": "soft"},
    "contest":        {"trigger": "commitment",     "cost_disposition": "peril_redemption", "clock": "none",
                       "reads_world_event": True},  # the scoreboard (finding 5)
    "gambit":         {"trigger": "commitment",     "cost_disposition": "peril_redemption", "clock": "none"},
    "discovery":      {"trigger": "pillars",        "cost_disposition": "sacrifice",        "clock": "none"},
    "mastery":        {"trigger": "commitment",     "cost_disposition": "peril_redemption", "clock": "none"},
    "farce":          {"trigger": "event_deadline", "cost_disposition": "fail_forward",     "clock": "soft"},
    "transformation": {"trigger": "choice",         "cost_disposition": "peril_redemption", "clock": "soft"},
}


#: Per-shape SIGNATURE ELEMENTS (GENRE-SIGNATURE-ELEMENTS.md, Cx 097 GREEN-shape) — the
#: fundamental elements that ARE the spirit of each genre, embodied (not engined) through two
#: channels: `author` (the generated fiction MUST establish it) and `narrator` (live improv
#: leans into it, governed by NARRATION-DISCIPLINE). Host-side control data, never canon.
#: Each element: {"name", "element" (one-line directive), "channels": ("author"|"narrator", ...)}.
SHAPE_SIGNATURE: dict[str, list[dict]] = {
    "deduction": [
        {"name": "red_herrings", "channels": ("author", "narrator"),
         "element": "plant at least one false lead with a tell; the narrator may improvise more "
                    "live, each one debunkable in play (never a dead-end)"},
        {"name": "cross_suspicion", "channels": ("author", "narrator"),
         "element": "the suspects point at one another — play the web so testimony must be weighed"},
        {"name": "alibis_and_contradictions", "channels": ("author",),
         "element": "suspects carry alibis that corroborate or conflict; the contradictions are the trail"},
        {"name": "culprit_present_and_surfaceable", "channels": ("author",),
         "element": "the answer is reachable in play, never offstage"},
        {"name": "the_earned_reveal", "channels": ("narrator",),
         "element": "reveal only when the player has assembled enough — never hand it over"},
    ],
    "bond": [
        {"name": "earned_intimacy_beats", "channels": ("narrator",),
         "element": "build connection through vulnerability and gesture — never a declared shortcut"},
        {"name": "real_friction_that_tests", "channels": ("author", "narrator"),
         "element": "a genuine source of conflict between the parties, pressed live"},
        {"name": "misread_corrected", "channels": ("author", "narrator"),
         "element": "a guard-with-a-crack: a misread or wound surfaced and then repaired"},
        {"name": "the_costly_gesture", "channels": ("narrator",),
         "element": "connection is proven by a choice that costs something"},
        {"name": "a_two_sided_other", "channels": ("author",),
         "element": "the other party has their own wants and wounds, not a mirror"},
    ],
    "endurance": [
        {"name": "mounting_threat", "channels": ("narrator",),
         "element": "escalate the pressure; never grant easy relief or safety"},
        {"name": "scarcity_and_resource_pressure", "channels": ("author", "narrator"),
         "element": "real constraints authored, spent and felt in play"},
        {"name": "the_clock", "channels": ("author",),
         "element": "a deadline or closing window bounds the ordeal"},
        {"name": "isolation", "channels": ("author", "narrator"),
         "element": "help is far; the protagonist is thrown on their own resources"},
        {"name": "the_glimpsed_dread", "channels": ("narrator",),
         "element": "the threat is felt before it is seen (horror blend)"},
    ],
    "contest": [
        {"name": "escalating_rounds", "channels": ("narrator",),
         "element": "each challenge harder than the last; the victory is fought for, never gifted"},
        {"name": "the_worthy_rival", "channels": ("author", "narrator"),
         "element": "an opponent with their own arc and credibility — authored AND kept credible round to round"},
        {"name": "preparation_pays", "channels": ("author", "narrator"),
         "element": "scouting and training are authored and made to matter"},
        {"name": "scoreboard_vs_meaning", "channels": ("narrator",),
         "element": "the meaningful win may differ from the literal result"},
    ],
    "gambit": [
        {"name": "factions_with_competing_agendas", "channels": ("author",),
         "element": "real players whose interests cross"},
        {"name": "the_plan_and_its_execution", "channels": ("author", "narrator"),
         "element": "a scheme with moving parts that the player works"},
        {"name": "complications_force_adaptation", "channels": ("narrator",),
         "element": "the board shifts; the player must improvise around the break"},
        {"name": "the_concealed_twist_or_betrayal", "channels": ("author", "narrator"),
         "element": "planted, kept hidden until it lands"},
    ],
    "discovery": [
        {"name": "gradual_unfolding", "channels": ("narrator",),
         "element": "place and meaning revealed in layers, never front-loaded"},
        {"name": "the_sense_of_wonder", "channels": ("narrator",),
         "element": "awe is the payoff; let it breathe"},
        {"name": "the_place_as_character", "channels": ("author",),
         "element": "a richly-layered, internally-coherent place authored to explore"},
        {"name": "competing_explanations", "channels": ("author", "narrator"),
         "element": "rival theories or disputed readings of what it means — interpretive, not pure scenic reveal"},
        {"name": "the_cost_of_knowing", "channels": ("author", "narrator"),
         "element": "understanding has a price; arrival is not free"},
    ],
    "mastery": [
        {"name": "incremental_competence", "channels": ("narrator",),
         "element": "skill accrues through practice; it is never granted"},
        {"name": "setbacks_that_teach", "channels": ("author", "narrator"),
         "element": "authored failure points that advance understanding"},
        {"name": "a_clear_standard", "channels": ("author",),
         "element": "an explicit bar or benchmark the work is measured against"},
        {"name": "the_made_thing_or_run_system", "channels": ("author",),
         "element": "a concrete artifact or system is the payoff"},
    ],
    "farce": [
        {"name": "mistaken_identity_or_cross_purposes", "channels": ("author", "narrator"),
         "element": "a misunderstanding engine seeded and stoked"},
        {"name": "compounding_complications", "channels": ("narrator",),
         "element": "each fix makes it worse; the snowball is the point"},
        {"name": "comic_timing_and_the_blowup", "channels": ("narrator",),
         "element": "escalate toward the set-piece blowup; do not resolve it early"},
        {"name": "false_coverage_is_engine_live", "channels": ("author",),
         "element": "the comic premise running is the desired state, not a failure"},
    ],
    "transformation": [
        {"name": "the_old_self_made_legible", "channels": ("author",),
         "element": "establish the starting self and its temptation up front, so the change can be proven against it"},
        {"name": "the_defining_choice", "channels": ("author", "narrator"),
         "element": "a real dilemma with stakes, pressed live"},
        {"name": "the_ordeal", "channels": ("narrator",),
         "element": "change is forced through hardship, not comfort"},
        {"name": "the_cost_of_change", "channels": ("narrator",),
         "element": "becoming someone new costs the old self something"},
        {"name": "proven_by_action_not_declared", "channels": ("narrator",),
         "element": "the changed self is shown, never merely stated"},
    ],
}


def _signature_for(shapes: list[str], channel: str) -> list[dict]:
    """Signature elements across the given shapes whose channels include `channel`
    ('author'|'narrator'), de-duplicated by name (a blend's shared element appears once)."""
    seen: set[str] = set()
    out: list[dict] = []
    for s in shapes:
        for el in SHAPE_SIGNATURE.get(s, ()):
            if channel in el["channels"] and el["name"] not in seen:
                seen.add(el["name"])
                out.append(el)
    return out


def signature_elements(game_types, channel: str) -> list[dict]:
    """The signature elements for a world's game-type(s) on one channel ('author'|'narrator'),
    primary + secondary shapes unioned. Empty list if nothing resolves."""
    prof = shapes_for(game_types)
    if not prof:
        return []
    return _signature_for([prof["shape"], *prof["secondary"]], channel)


def author_signature_directive(game_types) -> str:
    """The AUTHOR-INSIST block for world/cast authoring — the signature elements the generated
    fiction MUST establish for this world's shape(s). '' if nothing resolves. (Narrator-emphasize
    elements ride `shape_directive`; this is the build-time half.)"""
    els = signature_elements(game_types, "author")
    if not els:
        return ""
    lines = "\n".join(f"- {el['element']}" for el in els)
    return ("GENRE SIGNATURE — the generated fiction MUST establish these (they are the spirit of "
            "this genre; a story missing them rings false):\n" + lines)


def conclusion_profile(game_types) -> dict | None:
    """The conclusion profile for a world's game-type(s) — the PRIMARY shape's
    SHAPE_CONCLUSION entry (trigger / cost_disposition / clock). The cost_disposition
    here is what the conclusion selector reads to set coverage polarity. None if nothing
    resolves (→ legacy world_condition terminal)."""
    prof = shapes_for(game_types)
    if not prof:
        return None
    return SHAPE_CONCLUSION.get(prof["shape"])


#: Genre families that carry inherent PERIL/THRILLER tension → the AMPLIFIED suspense build-up
#: before the conclusion (founder; Cx 113: drive the amplifier off a genre-HAZARD signal, NOT
#: cost_disposition, which over-fires for mastery/contest/discovery). Physical peril or thriller
#: pressure; every other family gets the gentler GENERAL mounting-stakes clause.
_PERIL_FAMILIES = frozenset({
    "Survival, Scarcity & Endurance",
    "Horror, Dread & the Uncanny",
    "Action, Combat & Pursuit",
})


def suspense_profile(game_types) -> str:
    """'peril' if ANY of the world's game-types is a peril/thriller family (→ the amplified
    suspense build-up), else 'general' (the gentler default). Cx 113: a genre-hazard signal, not
    the conclusion cost_disposition (which answers how coverage is READ, not suspense intensity)."""
    from construct.play_styles import resolve
    for k in (resolve(game_types) or []):
        card = STYLE_CARDS.get(_norm(k))
        if card and card.get("family") in _PERIL_FAMILIES:
            return "peril"
    return "general"


def shape_directive(game_types) -> str:
    """The STORY-SHAPE briefing block for a world's game-type(s) — the per-shape
    'earn the payoff' discipline the narrator holds every turn (generalizes concealment
    to every genre). Primary + secondary shapes' lines. '' if nothing resolves."""
    prof = shapes_for(game_types)
    if not prof:
        return ""
    shapes = [prof["shape"], *prof["secondary"]]
    lines = [f"- {_SHAPE_LINE[s]}" for s in shapes if s in _SHAPE_LINE]
    if not lines:
        return ""
    block = ("STORY SHAPE (how this story earns its payoff — hold this discipline; it is "
             f"NOT a clue hunt unless deduction is named): this plays as "
             f"{' + '.join(shapes)}.\n" + "\n".join(lines))
    # NARRATOR-EMPHASIZE signature elements (GENRE-SIGNATURE-ELEMENTS.md): the genre's spirit
    # the live narrator should lean into. Unioned across primary+secondary, de-duped by name.
    sig = _signature_for(shapes, "narrator")
    if sig:
        block += ("\nEMBODY THE GENRE (lean into these live — improvise them where they fit; "
                  "anything you invent that creates a new player-pursuable thread must serve the "
                  "destination or be left uncreated):\n"
                  + "\n".join(f"- {el['element']}" for el in sig))
    return block


def shape_for(game_type: str) -> dict | None:
    """The shape PROFILE for one game-type key: {shape, secondary, **behavior defaults},
    or None for an unknown type (→ free improvised narrative)."""
    key = _norm(game_type)
    card = STYLE_CARDS.get(key)
    if not card:
        return None
    prim = TYPE_SHAPE.get(key) or FAMILY_SHAPE.get(card.get("family", ""))
    if not prim:
        return None
    sec = list(FAMILY_SECONDARY.get(card.get("family", ""), []))
    return {"shape": prim, "secondary": sec, **SHAPES[prim]}


def shapes_for(game_types) -> dict | None:
    """The BLENDED shape profile for a world's game-type(s). The first valid type's
    shape is PRIMARY; the rest contribute SECONDARY shapes (plus each family's named
    blend). Returns the primary's behavior defaults with the union of secondaries, or
    None if nothing resolves. (Most worlds are compounds — anchor = mystery + political
    intrigue → deduction + gambit.)"""
    from construct.play_styles import resolve
    keys = resolve(game_types)
    if not keys:
        return None
    primary_profile = shape_for(keys[0])
    if primary_profile is None:
        return None
    prim = primary_profile["shape"]
    secondary: list[str] = list(primary_profile["secondary"])
    for k in keys[1:]:
        p = shape_for(k)
        if p and p["shape"] != prim and p["shape"] not in secondary:
            secondary.append(p["shape"])
        for s in (p or {}).get("secondary", []):
            if s != prim and s not in secondary:
                secondary.append(s)
    return {"shape": prim, "secondary": secondary, **SHAPES[prim]}
