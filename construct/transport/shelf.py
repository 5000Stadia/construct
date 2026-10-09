"""The shelf: the library of shelf-ready worlds, the world menu, `/remove`,
and the play-styles wall."""

from __future__ import annotations

import logging

from construct import registry
from construct.transport.events import InboundEvent

logger = logging.getLogger("construct.transport_core")  # one logger name, as before the split


def _logline(scenario: dict) -> str:
    """A one-line hook for a library world, from its ingest-time meta — the first
    sentence of the description/intro, else the theme. Empty if nothing usable."""
    text = (scenario.get("description") or scenario.get("intro")
            or scenario.get("theme") or "").strip().replace("\n", " ")
    if not text:
        return ""
    # First sentence (bounded), so the catalog stays a clean one-liner.
    import re
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return (first[:157] + "…") if len(first) > 158 else first


#: Genre/title keyword → a single leading emoji for the world menu (first match
#: wins; a generic globe otherwise). Tasteful, not a zoo (founder).
_GENRE_EMOJI = (
    (("noir", "mystery", "detective", "whodunnit"), "🕵️"),
    (("harbor", "naval", "sea", "berth", "ship", "port"), "⚓"),
    (("winter", "frost", "snow", "ice", "ashenpeak"), "❄️"),
    (("gothic", "horror", "haunt", "ghost"), "🕯️"),
    (("romance", "romantic"), "💞"),
    (("political", "intrigue", "bureaucratic", "bureau"), "⚖️"),
    (("heist", "thief"), "💎"),
    (("western",), "🤠"),
    (("war", "military", "battle"), "⚔️"),
    (("dark", "blight", "grim"), "🌑"),
    (("fantasy", "quest", "dragon", "magic", "myth", "eldervale"), "🗡️"),
    (("sci-fi", "science fiction", "space", "station", "future", "cyber"), "🛸"),
    (("survival", "thriller", "disaster", "colonial"), "🪨"),
)


def _genre_emoji(genre: str, title: str = "") -> str:
    """Pick a leading emoji — the authored GENRE drives it; the title is only a
    fallback (so a 'fantasy quest' titled *Frost Tongue* reads 🗡️, not ❄️)."""
    for hay in (genre.lower(), title.lower()):
        if not hay:
            continue
        for keys, emoji in _GENRE_EMOJI:
            if any(k in hay for k in keys):
                return emoji
    return "🌍"


def _styles_wall() -> str:
    """The full wall of play-shapes (founder 2026-07-05): all 155 card names grouped
    by their 19 families — host-rendered, plain text + emoji (the Telegram sender
    uses no parse_mode). Compact: family headers with dot-joined names, so the wall
    reads as nineteen short paragraphs, not 155 lines."""
    try:
        from construct.play_styles_data import STYLE_CARDS
    except Exception:  # noqa: BLE001
        return ""
    fams: dict[str, list[str]] = {}
    for c in STYLE_CARDS.values():
        fams.setdefault(c["family"], []).append(c["name"])
    lines = [f"🎭 THE WALL — {len(STYLE_CARDS)} shapes of play"]
    for fam in sorted(fams):
        lines.append("")
        lines.append(f"— {fam} —")
        lines.append(" · ".join(sorted(fams[fam])))
    lines.append("")
    lines.append("Name any of them (blends welcome) — or describe your own.")
    return "\n".join(lines)


def _resolve_removal(arg: str, catalog: dict[str, str]) -> str | None:
    """Map a /remove argument to a scenario name — by name, exact title, or a
    unique title substring (case-insensitive). Ambiguity resolves to nothing."""
    low = arg.strip().lower()
    if low in {k.lower() for k in catalog}:
        return next(k for k in catalog if k.lower() == low)
    hits = [k for k, t in catalog.items()
            if low == str(t).split(" — ")[0].split(" · ")[0].strip().lower()]
    if not hits:
        hits = [k for k, t in catalog.items() if low in str(t).lower()]
    return hits[0] if len(hits) == 1 else None


class ShelfMixin:
    """The world library and shelf commands."""

    def _title_of(self, scenario: str) -> str:
        try:
            import json
            from construct.game import scenario_path
            mp = scenario_path(scenario).with_suffix(".meta.json")
            if mp.exists():
                return json.loads(mp.read_text()).get("title") or "your story"
        except Exception:
            logger.exception("title lookup failed for %s", scenario)
        return "your story"

    # -- the library the Construct showcases (by title, not raw id) ----------
    def _library(self) -> list[dict]:
        """Every shelf-ready world, each as {name, title, logline}. The guest sees the
        TITLE (a campaign/novel name set at ingest), never the raw scenario id. Includes
        PLAYER-BUILT worlds (`live_*`) — they're SHARED options for everyone (founder:
        pool the good generated worlds), while each player who picks one gets their OWN
        save (a separate per-player slot from the shared pristine). Excludes only play
        slots and any world missing a title (an incomplete/test artifact)."""
        out: list[dict] = []
        try:
            from construct.game import list_scenarios
            for s in list_scenarios():
                name = s["name"]
                title = (s.get("title") or "").strip()
                if not title or title == name:
                    continue  # no real title → not shelf-ready, skip it
                genre = (s.get("genre") or s.get("genre_era") or "").strip()
                out.append({"name": name, "title": title, "genre": genre,
                            "logline": _logline(s)})
        except Exception:
            logger.exception("library listing failed")
        return out

    def _catalog(self) -> dict[str, str]:
        """{name: 'Title — genre/hook'} for the Construct to speak (so the guest
        sees the STYLE of each title — founder); pick_world resolves to the name.
        Prefers the authored genre tag, falling back to the logline hook.
        Player-built worlds are tagged so the agent can answer provenance
        questions ('did I make one?') truthfully."""
        return {w["name"]: (f"{w['title']} — {w['genre']}" if w["genre"]
                            else (f"{w['title']} — {w['logline']}" if w["logline"]
                                  else w["title"]))
                          + (" · player-built" if w["name"].startswith("live_")
                             else " · preloaded")
                for w in self._library()}

    def _world_menu(self, resumable: str = "", viewer: str = "") -> str:
        """A clean, scannable menu of the ready-made worlds (founder: 'more menu
        clean' — emoji to separate sections). Host-rendered for consistency, one
        world per line with a genre emoji; the Construct's prose introduces it.
        PROVENANCE (founder 2026-07-05, 'did I make one?'): the shelf splits into
        the preloaded house worlds and the player-built ones (`live_*` — the
        transport's own naming carries provenance); `viewer` (a `live_<platform>_
        <id>_` prefix) marks this guest's own creations."""
        lib = self._library()
        if not lib:
            return ""
        house = [w for w in lib if not w["name"].startswith("live_")]
        built = [w for w in lib if w["name"].startswith("live_")]

        def _line(w: dict) -> str:
            tag = f" — {w['genre']}" if w["genre"] else (
                f" — {w['logline']}" if w["logline"] else "")
            yours = " · yours" if viewer and w["name"].startswith(viewer) else ""
            return f"{_genre_emoji(w['genre'], w['title'])} {w['title']}{tag}{yours}"

        # Plain text + emoji only — the Telegram sender uses no parse_mode, so
        # markdown would show literal asterisks. Emoji + line breaks do the work.
        lines = []
        if house:
            lines.append("📂 THE HOUSE SHELF (preloaded)")
            lines += [_line(w) for w in house]
        if built:
            if lines:
                lines.append("")
            lines.append("🛠️ BUILT BY PLAYERS")
            lines += [_line(w) for w in built]
        if resumable:
            lines.append("")
            lines.append(f"▶️ Resume — {self._title_of(resumable)}")
        lines.append("")
        lines.append("✨ …or describe a new world and I'll shape it with you.")
        return "\n".join(lines)

    # -- /remove: retire a world from the shelf (non-destructive attic move) ---
    def _remove_world(self, pid: str, ev: InboundEvent, arg: str) -> str:
        """FOUNDER (2026-07-05): built worlds accumulate on the shared shelf — let the
        front end retire one. NON-DESTRUCTIVE (the anchor precedent): every file moves
        to worlds/attic/, never deleted; per-player play slots are untouched. The world
        you're currently INSIDE can't be pulled out from under you."""
        if not arg:
            names = ", ".join(f"“{w['title']}”" for w in self._library()) or "(none)"
            return (f"Which world shall I retire to the attic? Say /remove <title>. "
                    f"On the shelf: {names}")
        from construct.game import scenario_path
        catalog = self._catalog()
        target = _resolve_removal(arg, catalog)
        if target is None:
            return (f"I don't see “{arg}” on the shelf. /remove with no argument "
                    f"lists what's there.")
        current = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if target == current:
            return ("That's the world you're standing in — step out first "
                    "(build or pick another), then /remove it.")
        try:
            import shutil
            base = scenario_path(target)
            attic = base.parent / "attic"
            attic.mkdir(exist_ok=True)
            moved = 0
            for f in sorted(base.parent.glob(f"{target}.*")):
                if f.is_file():
                    shutil.move(str(f), str(attic / f.name))
                    moved += 1
            title = catalog.get(target, target).split(" — ")[0]
            logger.info("world %s retired to the attic (%d files)", target, moved)
            return (f"“{title}” is retired to the attic — off the shelf, nothing "
                    f"deleted. ({moved} files moved; saved games untouched.)")
        except Exception as exc:  # noqa: BLE001
            logger.exception("remove failed for %s", target)
            return f"(couldn't retire that world: {exc})"
