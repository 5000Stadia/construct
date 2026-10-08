"""Typed scenario metadata and the per-playthrough layering over it.

Two small, host-side types (audit 2026-10 tier 2 #4, world.md F1):

* ``ScenarioMeta`` — the frozen, typed view of a scenario's ``<name>.meta.json``.
  It serializes to EXACTLY the keys, values and key order it was loaded with
  (unknown keys ride in ``extra``), so every existing world round-trips
  byte-identically. It is an accessor, not a schema change: the JSON format and the
  meaning of every field are untouched.
* ``PlaythroughState`` — the ONE place that applies "the slot's ``session:episode.*``
  rows override the shared scenario meta". The scenario meta is shared and stale (the
  build-time / chapter-one truth); the slot is per-player and current. ``Session``
  takes this instead of re-deriving the precedence inline.

Two different things were both called "mode"; they are now two enums:

* ``InputAuthority`` — ``meta["mode"]``: ``pure`` / ``coauthor``, the turn-loop input
  authority.
* ``ScenarioMode`` — ``meta["scenario_mode"]`` (and the player's session-zero choice):
  ``win_loss`` / ``endless``. (The session also has an un-stored third default,
  ``bounded``, used only when the key is absent and no override is given.)

KNOWN WART (audit B9, deliberately NOT fixed here): ``endless`` (a bool) and
``scenario_mode`` both persist the win/loss-vs-freeplay axis and can disagree — e.g. a
freeplay-built shared world (``endless=True``) opened with ``mode_override="win_loss"``
yields ``_scenario_mode == "win_loss"`` AND ``_endless == True``. ``ScenarioMeta``
carries both fields verbatim so the contradiction is visible in one place.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ScenarioMode(StrEnum):
    """``meta["scenario_mode"]``: does the story build to an ending or carry on?"""
    WIN_LOSS = "win_loss"
    ENDLESS = "endless"


class InputAuthority(StrEnum):
    """``meta["mode"]``: who may author canon through the player's input."""
    PURE = "pure"
    COAUTHOR = "coauthor"


def _coerce(enum_cls: type[Enum], value: Any) -> Any:
    """The enum member for a known stored string; anything else is kept VERBATIM so an
    odd old value still round-trips (a str-enum equals — and serializes as — its value)."""
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return value


def _plain(value: Any) -> Any:
    """Enum members serialize as their plain stored string."""
    return value.value if isinstance(value, Enum) else value


_ENUM_FIELDS: dict[str, type[Enum]] = {
    "mode": InputAuthority,
    "scenario_mode": ScenarioMode,
}


@dataclass(frozen=True)
class ScenarioMeta:
    """A scenario's ``.meta.json``, typed. Frozen: derive changes with ``evolve``.

    Values are NOT coerced (apart from the two enums above): a field holds exactly what
    the file held. A field's attribute is its natural default when its key is absent;
    use ``has(key)`` / ``get(key, default)`` when absent-vs-present matters (the
    existing readers rely on ``meta.get(key, default)`` semantics).
    """

    title: str = ""
    protagonist: str = ""
    theme: str = ""
    stance: str = ""
    mode: InputAuthority | str = InputAuthority.PURE
    style: str = ""
    scenario_mode: ScenarioMode | str | None = None
    arc_scope: list = field(default_factory=list)
    main_arc: str = ""
    arc_ids: list = field(default_factory=list)
    entry_epoch: float | None = None
    seeded_frames: list = field(default_factory=list)
    endless: bool = False            # duplicates scenario_mode (audit B9)
    laws: list = field(default_factory=list)
    reality_register: str = ""
    opening_as_of: float | None = None
    next_source_as_of: float | None = None
    source_step: Any = None
    cast: Any = None
    goal_statement: str = ""
    intro: str = ""
    genre: str = ""
    premise: str = ""
    game_type: list = field(default_factory=list)
    death_policy: str = ""
    death_policy_reason: str = ""
    result_events: Any = None
    arc_cache: Any = None            # legacy single-arc (pre-portfolio) worlds
    #: Keys this class has no typed field for (runtime/legacy/test keys) — preserved
    #: verbatim so old worlds round-trip.
    extra: dict = field(default_factory=dict)
    #: Every key present, in file order (absent vs null matters; so does byte order).
    _keys: tuple = field(default=(), repr=False, compare=False)
    #: The scenario name this was loaded from (``save`` needs it).
    _name: str = field(default="", repr=False, compare=False)

    # -- construction ---------------------------------------------------------------
    @classmethod
    def from_json(cls, raw: Mapping[str, Any], *, name: str = "") -> ScenarioMeta:
        """Build from a parsed ``.meta.json`` mapping (unknown keys -> ``extra``)."""
        known = _KNOWN_FIELDS
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for key, value in raw.items():
            if key in known:
                kwargs[key] = _coerce(_ENUM_FIELDS[key], value) if key in _ENUM_FIELDS else value
            else:
                extra[key] = value
        return cls(**kwargs, extra=extra, _keys=tuple(raw), _name=name)

    @classmethod
    def load(cls, name: str) -> ScenarioMeta:
        """Read ``worlds/<name>.meta.json`` (empty meta when the file is absent — the
        long-standing ``{}`` fallback). Malformed JSON raises, as ``json.loads`` did."""
        meta_path = _meta_path(name)
        raw = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        return cls.from_json(raw, name=name)

    # -- serialization --------------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        """The ``.meta.json`` dict: EXACTLY the keys that were present, in file order,
        with plain-string enum values. (Values are shared with this instance, not
        copied — treat the result as read-only or copy before mutating nested values.)"""
        out: dict[str, Any] = {}
        for key in self._keys:
            out[key] = self.extra[key] if key in self.extra else _plain(getattr(self, key))
        return out

    def save(self) -> None:
        """Write ``worlds/<name>.meta.json`` (same formatting the host always used)."""
        if not self._name:
            raise ValueError("ScenarioMeta.save: no scenario name (use save_to(path))")
        self.save_to(_meta_path(self._name))

    def save_to(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), indent=2))

    # -- reads ----------------------------------------------------------------------
    def has(self, key: str) -> bool:
        return key in self._keys

    def get(self, key: str, default: Any = None) -> Any:
        """``dict.get`` semantics over the stored keys (present-but-null stays null)."""
        if key not in self._keys:
            return default
        if key in self.extra:
            return self.extra[key]
        return _plain(getattr(self, key))

    # -- changes --------------------------------------------------------------------
    def evolve(self, **changes: Any) -> ScenarioMeta:
        """A copy with these keys set (typed fields or extras). A newly set key is
        appended to the key order, so it serializes like a ``meta[key] = value`` did."""
        typed: dict[str, Any] = {}
        extra = dict(self.extra)
        keys = list(self._keys)
        for key, value in changes.items():
            if key in _KNOWN_FIELDS:
                typed[key] = _coerce(_ENUM_FIELDS[key], value) if key in _ENUM_FIELDS else value
            else:
                extra[key] = value
            if key not in keys:
                keys.append(key)
        return replace(self, **typed, extra=extra, _keys=tuple(keys))


_KNOWN_FIELDS: frozenset[str] = frozenset(
    f.name for f in fields(ScenarioMeta) if f.name not in ("extra", "_keys", "_name"))


def _meta_path(name: str) -> Path:
    # Lazy: game imports this module, and tests repoint game.WORLDS_DIR.
    from construct.game import scenario_path
    return scenario_path(name).with_suffix(".meta.json")


# ---------------------------------------------------------------------------------------
# PlaythroughState — the slot's session:episode.* rows laid over the scenario meta
# ---------------------------------------------------------------------------------------

#: The per-player slot rows that override the shared scenario meta, as
#: (key in ``slot_rows``, entity, attribute). All read from the ``session:main`` frame.
SLOT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("episode.arc_scope", "session:episode", "arc_scope"),
    ("episode.entry_epoch", "session:episode", "entry_epoch"),
    ("episode.chapter_title", "session:episode", "chapter_title"),
    ("episode.death_policy", "session:episode", "death_policy"),
    ("scope.independent_extra", "session:scope", "independent_extra"),
)


def read_slot_rows(world: Any) -> dict[str, Any]:
    """Read the ``SLOT_ROWS`` off an open playthrough world. A row that is absent, or
    whose read fails (logged), is simply missing from the result — the scenario meta
    then stands for it, exactly as before."""
    from construct.adapter import PorcelainWorldReads
    reads = PorcelainWorldReads(world)
    rows: dict[str, Any] = {}
    for key, entity, attribute in SLOT_ROWS:
        try:
            value = reads.state(entity, attribute, frame="session:main")
        except Exception:
            logger.exception("slot row %s read failed; falling back to scenario meta", key)
            continue
        if value is not None:
            rows[key] = value
    return rows


class PlaythroughState:
    """The scenario meta as THIS player's slot currently sees it.

    PRECEDENCE (written once, here): a slot ``session:episode.*`` row beats the shared,
    build-time scenario meta — ``game.continue_episode`` writes them per player on a
    CONCLUDE->CONTINUE because the ``.meta.json`` is shared and stale (Cx 138 #2, Cx 191,
    audit B2). Absent rows (a first chapter, a ``/restart`` to chapter one) leave the
    scenario meta untouched.

    * ``scope``             episode.arc_scope  > meta["arc_scope"]  (``None`` when neither)
    * ``slot_scope_loaded`` True when the slot supplied the scope (episode-local baseline)
    * ``entry_epoch``       episode.entry_epoch > meta["entry_epoch"] > TURN_EPOCH
    * ``meta``              the scenario meta dict with the slot's chapter title /
                            death policy laid over ``title`` / ``death_policy``
    * ``independent_extra`` the episode-local independent scope origins (a set)
    """

    def __init__(self, meta: ScenarioMeta | Mapping[str, Any],
                 slot_rows: Mapping[str, Any]) -> None:
        from construct.arc.executor import TURN_EPOCH
        scenario = meta.to_json() if isinstance(meta, ScenarioMeta) else meta
        # A private shallow copy: the session mutates its meta (continuation_intro).
        self.meta: dict[str, Any] = dict(scenario)

        self.scope: list | None = self.meta.get("arc_scope") or None
        self.slot_scope_loaded = False
        slot_scope = slot_rows.get("episode.arc_scope")
        if slot_scope:
            try:
                self.scope = json.loads(slot_scope) if isinstance(slot_scope, str) else slot_scope
                self.slot_scope_loaded = True
            except Exception:
                logger.exception("episode scope read failed; falling back to scenario meta")

        self.independent_extra: set[str] = set()
        extra_raw = slot_rows.get("scope.independent_extra")
        if extra_raw:
            try:
                self.independent_extra = set(
                    json.loads(extra_raw) if isinstance(extra_raw, str) else extra_raw)
            except Exception:
                logger.exception("persisted independent-scope read failed; continuing without")

        slot_epoch = slot_rows.get("episode.entry_epoch")
        self.entry_epoch = float(slot_epoch if slot_epoch is not None
                                 else (self.meta.get("entry_epoch", TURN_EPOCH) or TURN_EPOCH))

        for row, key in (("episode.chapter_title", "title"),
                         ("episode.death_policy", "death_policy")):
            value = slot_rows.get(row)
            if isinstance(value, str) and value.strip():
                self.meta[key] = value.strip()

    @classmethod
    def from_world(cls, meta: ScenarioMeta | Mapping[str, Any], world: Any) -> PlaythroughState:
        """Read the slot rows off ``world`` and layer them over ``meta``."""
        return cls(meta, read_slot_rows(world))
