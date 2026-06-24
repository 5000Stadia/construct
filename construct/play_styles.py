"""Game types as maintained narrative directives (GAME-TYPES.md).

A game type is NOT a toggle matrix — it's one sharp paragraph of guidance the
narrator holds throughout the simulation (what to dramatize vs. hand-wave, the
tension posture, what winning means). The curated taxonomy (155 cards across 19
families) lives in `docs/design/GAME-TYPE-TAXONOMY.md` and is compiled to
`play_styles_data.STYLE_CARDS` by `scripts/build_play_styles.py`.

A scenario carries one PRIMARY type and optionally one or two SECONDARY types —
the engine MIXES them (founder: "most holodeck programs are compounds"). The
chosen directive(s) ride in the narrator briefing every turn so the agent's sense
of "what kind of game this is" never lapses.
"""

from __future__ import annotations

from construct.play_styles_data import STYLE_CARDS


def _norm(key: str) -> str:
    return (key or "").strip().lower()


def card(game_type: str) -> dict | None:
    """The full card for a game-type key (name/family/directive), or None."""
    return STYLE_CARDS.get(_norm(game_type))


def resolve(game_types) -> list[str]:
    """Normalize a str | list of game-type keys to an ordered, de-duplicated list
    of VALID keys (unknown keys dropped — free improvised narrative for the rest)."""
    if not game_types:
        return []
    if isinstance(game_types, str):
        game_types = [game_types]
    out: list[str] = []
    for g in game_types:
        k = _norm(g)
        if k in STYLE_CARDS and k not in out:
            out.append(k)
    return out


def directive_for(game_types) -> str | None:
    """The narrative directive for a game type or a BLEND of them, or None for free
    improvised narrative (nothing valid given). A single type returns its directive;
    multiple are combined under a 'hold all of these at once' preamble so the agent
    runs the compound (e.g. Heist + Social Drama + Political Intrigue)."""
    keys = resolve(game_types)
    if not keys:
        return None
    directives = [STYLE_CARDS[k]["directive"] for k in keys]
    if len(directives) == 1:
        return directives[0]
    return ("PLAY STYLES — this world BLENDS the styles below; hold ALL of them at "
            "once and let each govern the beats where it applies (the blend IS the "
            "experience, not a menu to pick from):\n\n" + "\n\n".join(directives))


def names(game_types) -> list[str]:
    """Human-facing card names for the resolved types (for logs/UX)."""
    return [STYLE_CARDS[k]["name"] for k in resolve(game_types)]


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


def match_many(labels) -> list[str]:
    """Resolve a list of free labels to an ordered, de-duplicated list of keys."""
    if isinstance(labels, str):
        labels = [labels]
    out: list[str] = []
    for lab in labels or []:
        k = match(lab)
        if k and k not in out:
            out.append(k)
    return out
