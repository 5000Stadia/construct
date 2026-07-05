"""World laws — universal dynamics as first-class canon (WORLD-LAWS.md, #105).

The founder's Star Wars question: a build never authors a NAMED, novel,
universe-governing dynamic (the Force → Jedi → Empire causal stack), so the
model's prior fills the vacuum with trope pastiche. This module is the
constitution stage: the canonical family→register palette (Cx 470 ruling 1 —
DATA beside the game-type taxonomy, never derived from reality register
alone), the reality-register overlay, the deterministic lint (the shallow
checks only — Cx 470 ruling 2: novelty is the critic's judgment, not a string
check), and the single-source renders every consumer shares (Cx 470 test bar:
cast, arc, and adjudication receive the SAME law objects, not divergent
prompt summaries).

Laws are ordinary canon (`law:<slug>` rows, kind=world_law) — the pin is only
the briefing directive, never the law itself (Cx 470 ruling 5). Enforcement
rides existing rails: the narrator briefing (a reserved lane AHEAD of the
capped pins — ruling 4), and a compact THE LAWS block on every improv/deny/
adjudication call that may grant world change (ruling 3).
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

#: The five registers a law may govern in (WORLD-LAWS.md §register gate).
REGISTERS = ("metaphysical", "systemic", "social", "environmental", "delta")

#: The three reality registers (founder constraint 2): REAL Earth as it is;
#: ALTERNATE Earth (real plus authored deltas); SECONDARY world (invented whole).
REALITY_REGISTERS = ("real", "alternate", "secondary")

#: Family → default register palette (WORLD-LAWS.md table; Cx 470 ruling 1:
#: canonical data — a REAL courtroom drama and a REAL romance share Earth but
#: must not invite the same registers). `metaphysical` policy: "expects" (the
#: family's premise usually IS one), "yes" (welcome), "invited" (only if the
#: brief/reality register explicitly opens it), "rarely" (a quiet tone-law at
#: most), "no" (A Few Good Men / Pelican Brief live here — never the Force).
FAMILY_PALETTE: dict[str, dict[str, Any]] = {
    "Investigation & Epistemics":       {"registers": ("systemic", "social"), "metaphysical": "invited"},
    "Puzzle, Escape & Decoding":        {"registers": ("systemic", "environmental"), "metaphysical": "invited"},
    "Schemes & Infiltration":           {"registers": ("systemic", "social"), "metaphysical": "invited"},
    "Action, Combat & Pursuit":         {"registers": ("systemic", "environmental"), "metaphysical": "invited"},
    "Survival, Scarcity & Endurance":   {"registers": ("environmental", "systemic"), "metaphysical": "invited"},
    "Exploration, Wonder & Place":      {"registers": ("environmental", "metaphysical"), "metaphysical": "yes"},
    "Social, Relationship & Intimacy":  {"registers": ("social", "systemic"), "metaphysical": "rarely"},
    "Politics, Factions & Institutions": {"registers": ("systemic",), "metaphysical": "invited"},
    "Horror, Dread & the Uncanny":      {"registers": ("metaphysical", "environmental"), "metaphysical": "yes"},
    "Stewardship, Building & Management": {"registers": ("systemic", "environmental"), "metaphysical": "invited"},
    "Creativity, Craft & Performance":  {"registers": ("social", "systemic"), "metaphysical": "invited"},
    "Professional & Procedural Competence": {"registers": ("systemic",), "metaphysical": "no"},
    "Moral, Psychological & Literary Drama": {"registers": ("social", "systemic"), "metaphysical": "rarely"},
    "Comedy, Farce & Chaos":            {"registers": ("social",), "metaphysical": "yes"},
    "Competition, Status & Proving Grounds": {"registers": ("systemic", "social"), "metaphysical": "invited"},
    "Mythic, Spiritual & Symbolic":     {"registers": ("metaphysical",), "metaphysical": "expects"},
    "Time, Reality & Metafiction":      {"registers": ("metaphysical",), "metaphysical": "expects"},
    "Communication, Collection & Interpretation": {"registers": ("systemic", "social"), "metaphysical": "invited"},
    "Transgression, Power & Ensemble Forms": {"registers": ("social", "systemic"), "metaphysical": "invited"},
}

#: The calibration exhibits (fed to the authoring prompt as exemplars) — a
#: law NAMED after one of these is a copied answer, lint-rejected.
CALIBRATION_NAMES = frozenset({"the force", "the code", "the statute of secrecy"})

#: The five mandatory parts of a law object (WORLD-LAWS.md §law object).
LAW_PARTS = ("name", "rule", "cost_limit", "embodiment", "texture")


def families_of(game_types: list[str] | None) -> list[str]:
    """The distinct card families behind resolved game-type keys, in order."""
    from construct.play_styles_data import STYLE_CARDS
    seen: list[str] = []
    for k in game_types or []:
        fam = (STYLE_CARDS.get(k) or {}).get("family")
        if fam and fam not in seen:
            seen.append(fam)
    return seen


def allowed_registers(families: list[str] | None, reality: str) -> set[str]:
    """The registers this build may author laws in — the family palette union
    (canonical data) overlaid by the reality register (Cx 470 ruling 1):

    - REAL: SYSTEMIC/SOCIAL/ENVIRONMENTAL only — no METAPHYSICAL, no DELTA
      (invention stays plausible-real; A Few Good Men never gets the Force).
    - ALTERNATE: the same real-Earth discipline PLUS the delta register —
      each divergence is authored AS a law; un-deltaed material defaults to
      real-Earth truth.
    - SECONDARY: the palette decides. METAPHYSICAL rides in only when some
      family's policy invites it (yes/expects/invited); "rarely"/"no"
      families keep their domain respect even in an invented world.

    No/unknown families → the reality register's own defaults (a briefless
    surprise build still gets a principled gate)."""
    fams = [f for f in (families or []) if f in FAMILY_PALETTE]
    base: set[str] = set()
    meta_policies: set[str] = set()
    for f in fams:
        base |= set(FAMILY_PALETTE[f]["registers"])
        meta_policies.add(FAMILY_PALETTE[f]["metaphysical"])
    if not fams:
        base = {"systemic", "social", "environmental"}
        meta_policies = {"invited"}

    real_earth = base & {"systemic", "social", "environmental"} or {
        "systemic", "social", "environmental"}
    if reality == "real":
        return real_earth
    if reality == "alternate":
        return real_earth | {"delta"}
    # secondary (and unset → treated as secondary, the least-gated register;
    # the author cohort settles the register explicitly before authoring)
    allowed = set(base) - {"delta"}
    if meta_policies & {"yes", "expects", "invited"}:
        allowed.add("metaphysical")
    else:
        allowed.discard("metaphysical")
    return allowed


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "law"


def lint_laws(laws: list[dict], allowed: set[str]) -> list[str]:
    """The deterministic lint — SHALLOW structural checks only (Cx 470
    ruling 2: five-part completeness, register-in-gate, proper name, copied
    calibration names, texture-only anti-trope answers). Whether the law's
    consequences genuinely change is the law-critic's semantic judgment,
    never pretended here. Returns problems (empty = clean)."""
    from construct.resolve import is_proper_named
    problems: list[str] = []
    if not laws:
        return problems
    if len(laws) > 4:
        problems.append(f"{len(laws)} laws authored — a world holds 1-4 "
                        "(intensity scales with ambition, never a pile)")
    seen_names: set[str] = set()
    for i, law in enumerate(laws):
        name = str(law.get("name") or "").strip()
        tag = name or f"law #{i + 1}"
        for part in LAW_PARTS:
            if not str(law.get(part) or "").strip():
                problems.append(f"{tag}: missing its {part.upper()} — every law "
                                "carries all five parts (NAME/RULE/COST/"
                                "EMBODIMENT/TEXTURE)")
        reg = str(law.get("register") or "").strip().lower()
        if reg not in REGISTERS:
            problems.append(f"{tag}: register {reg!r} is not one of {REGISTERS}")
        elif reg not in allowed:
            problems.append(f"{tag}: register {reg!r} is not permitted for this "
                            f"world (allowed: {sorted(allowed)}) — respect the "
                            "domain; author within its registers")
        if name and not is_proper_named(name):
            problems.append(f"{tag}: the NAME must be a proper, ownable, "
                            "speakable-in-world name (never 'the magic' / "
                            "'the curse' — case is the evidence)")
        if name.lower() in CALIBRATION_NAMES:
            problems.append(f"{tag}: names a calibration exhibit — invent this "
                            "world's OWN law, never copy the exemplars")
        if name.lower() in seen_names:
            problems.append(f"{tag}: duplicate law name")
        seen_names.add(name.lower())
        # texture-only anti-trope answer: the changed consequence must not be
        # a restatement of the texture (different texture is not different;
        # different CONSEQUENCES are).
        cc = str(law.get("changed_consequence") or "").strip().lower()
        tx = str(law.get("texture") or "").strip().lower()
        if law.get("nearest_borrowed_shape") and not cc:
            problems.append(f"{tag}: names a borrowed shape but no "
                            "changed_consequence — twist the borrowed element "
                            "until its CONSEQUENCES change")
        if cc and tx and cc == tx:
            problems.append(f"{tag}: changed_consequence merely restates the "
                            "TEXTURE — consequences are behavior, institutions, "
                            "costs, climax possibilities, not surface detail")
        if str(law.get("disclosure") or "").strip() not in ("understood",
                                                            "discovered"):
            problems.append(f"{tag}: disclosure must be 'understood' (the "
                            "character inherently knows it — introduced in the "
                            "opening) or 'discovered' (the universe reveals it "
                            "in play — woven, never stated)")
    return problems


def understood_laws(laws: list[dict]) -> list[dict]:
    """The laws the player's character INHERENTLY knows (founder disclosure
    ruling): these are lived context — the intro and opening grounding
    introduce them openly."""
    return [law for law in laws if law.get("disclosure") != "discovered"]


def discovered_laws(laws: list[dict]) -> list[dict]:
    """The laws the universe only reveals in play ('magic is real and you're
    a wizard, Harry'): never stated up front — the narrator weaves their
    EDGES; the player uncovers them."""
    return [law for law in laws if law.get("disclosure") == "discovered"]


def laws_block(laws: list[dict]) -> str:
    """THE LAWS — the compact full-object block every consumer shares (Cx 470
    ruling 3 + test bar: author_cast, arc generation, and deny/grant
    adjudication receive the SAME rendered objects). Empty laws → ''. """
    if not laws:
        return ""
    lines = ["THE LAWS OF THIS WORLD (binding universal dynamics — canon; "
             "nothing in play may contradict them; a law marked UNDISCOVERED "
             "still binds, but the player does not yet know it — enforce it "
             "without naming it):"]
    for law in laws:
        hidden = " · UNDISCOVERED" if law.get("disclosure") == "discovered" else ""
        lines.append(
            f"- {law.get('name', '?')} [{law.get('register', '?')}{hidden}]: "
            f"{law.get('rule', '')} "
            f"COST/LIMIT: {law.get('cost_limit', '')} "
            f"EMBODIED BY: {law.get('embodiment', '')} "
            f"TEXTURE: {law.get('texture', '')}")
    return "\n".join(lines)


def law_lines(laws: list[dict]) -> str:
    """The one-line-per-law briefing lane — rendered every turn AHEAD of the
    ordinary capped pins (Cx 470 ruling 4: the constitution never gets pushed
    out of the narrator's awareness by a busy turn's clue/social pins).
    Split by disclosure (founder): 'understood' laws are open lived context;
    'discovered' laws bind silently — the narrator weaves their edges and
    never states them until the player uncovers them."""
    if not laws:
        return ""
    lines = ["WORLD LAWS (the universe's governing dynamics — always true, "
             "always binding; let them shape what is possible, what things "
             "cost, and how people behave; never contradict them):"]
    for law in understood_laws(laws):
        lines.append(f"- {law.get('name', '?')}: {law.get('rule', '')} "
                     f"(its price: {law.get('cost_limit', '')})")
    hidden = discovered_laws(laws)
    if hidden:
        lines.append(
            "STILL UNDISCOVERED (these govern the world but the player does "
            "NOT yet know them — never state or name them; let their EDGES "
            "show — consequences, residues, things that don't add up — and "
            "reward the player who pulls the thread):")
        for law in hidden:
            lines.append(f"- {law.get('name', '?')}: {law.get('rule', '')} "
                         f"(its price: {law.get('cost_limit', '')})")
    return "\n".join(lines)


def law_rows(laws: list[dict]) -> list[dict]:
    """The canon rows — explicit and boring (Cx 470 ruling 5): `law:<slug>`
    entities with kind=world_law + the law parts as queryable attributes.
    The source of truth lives HERE; pins/blocks are derived briefings."""
    rows: list[dict] = []
    for law in laws:
        lid = f"law:{_slug(str(law.get('name') or ''))}"
        rows.append({"entity": lid, "attribute": "kind", "value": "world_law",
                     "timeless": True})
        for attr in ("name", "register", "rule", "cost_limit", "texture",
                     "disclosure"):
            v = str(law.get(attr) or "").strip()
            if v:
                rows.append({"entity": lid, "attribute": attr, "value": v,
                             "timeless": True})
    return rows


def embodiment_rows(laws: list[dict], links: list[dict],
                    known_ids: set[str]) -> list[dict]:
    """Embodiment links — written AFTER cast authoring (Cx 470 ruling 5:
    author_cast declares which institutions/members exist BECAUSE of which
    law; never prose-only — the causal stack must be queryable). Each link is
    {"law": <name-or-slug>, "embodied_by": <canon entity id>}; unknown
    entities are dropped (a link may only point at real canon)."""
    by_slug = {_slug(str(law.get("name") or "")): law for law in laws}
    by_name = {str(law.get("name") or "").strip().lower(): law for law in laws}
    rows: list[dict] = []
    for link in links or []:
        raw = str(link.get("law") or "").strip()
        law = by_slug.get(_slug(raw)) or by_name.get(raw.lower())
        target = str(link.get("embodied_by") or "").strip()
        if not law or target not in known_ids:
            continue
        lid = f"law:{_slug(str(law.get('name') or ''))}"
        rows.append({"entity": lid, "attribute": "embodied_by", "value": target,
                     "value_type": "entity", "timeless": True})
    return rows


#: The reality register's standing adjudication contract, one line per
#: register (WORLD-LAWS.md §reality register) — threaded beside the laws
#: block so "in a real-world register…" clauses have an explicit referent,
#: INCLUDING the no-law case (Cx 475 note).
_REALITY_LINES = {
    "real": ("THE REALITY REGISTER: REAL — actual Earth, actual era. Invention "
             "stays plausible-real; real institutions and physics hold; nothing "
             "metaphysical or physics-breaking is possible here."),
    "alternate": ("THE REALITY REGISTER: ALTERNATE EARTH — our world PLUS its "
                  "authored delta laws. Everything NOT covered by a delta "
                  "defaults to real-Earth truth; police that seam."),
    "secondary": ("THE REALITY REGISTER: SECONDARY WORLD — an invented whole. "
                  "Its laws are the only Earth it has; hold them absolutely."),
}


def reality_line(reality: str) -> str:
    """The one-line reality contract for runtime consumers; '' when unset."""
    return _REALITY_LINES.get((reality or "").strip().lower(), "")


def laws_from_meta(meta: dict | None) -> list[dict]:
    """The sealed law objects off scenario meta (the turn loop's cheap read;
    the canon law:* rows remain the queryable truth)."""
    laws = (meta or {}).get("laws")
    return [law for law in laws if isinstance(law, dict)] if isinstance(laws, list) else []
