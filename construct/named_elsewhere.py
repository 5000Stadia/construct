"""NAMED BUT NOT HERE: things the player's line names that the player knows are elsewhere.

Spec: docs/design/OPENING-SETTLE-AND-ELSEWHERE.md, Part A (cr GREEN at r3). R20 run 7:
the player asked to see a sack and a hearth in the next room, the scene list (rightly)
held neither, and the narrator brought both into the cell.

The rule is one-sided. An EMISSION rests on the player frame alone: the name the player
used, and the thing's player-frame containment path up to its nearest place. The canon
context passed in (the scene's features, the scene's ancestors) can only SUPPRESS a line,
never produce one, so no whereabouts the player has not learned reaches the narrator.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from construct.adapter import frame_facts
from construct.resolve import is_deixis
from construct.text import human_name_typed_id

logger = logging.getLogger(__name__)

#: At most this many lines a turn (spec: the 4 cap).
NAMED_ELSEWHERE_CAP = 4
#: The upward containment walk stops after this many hops (cycle-safe besides).
_MAX_HOPS = 4
#: Labels shorter than this never match ("it", "ox" would fire on everything).
_MIN_LABEL = 3
_LABEL_ATTRS = ("name", "alias")
_CONTAINMENT = ("in", "part_of")


def _folded(world: Any, entity: str, frame: str, as_of: float | None) -> dict:
    """The entity's folded facts in `frame`, attribute -> value (empty on any read error)."""
    try:
        snap = world.porcelain.snapshot([entity], frame=frame, as_of=as_of)
    except Exception:  # noqa: BLE001 — a failed read is "not known", never a broken turn
        return {}
    return {f["attribute"]: f["value"] for f in (snap.get("facts") or [])
            if f.get("entity") == entity}


def _known_path(world: Any, entity: str, frame: str, as_of: float | None) -> list[str]:
    """The entity's player-frame containment path upward, nearest first: follows `in`,
    else `part_of`, for at most `_MAX_HOPS` hops, stopping at a cycle or an unknown."""
    path: list[str] = []
    seen = {entity}
    cur = entity
    for _ in range(_MAX_HOPS):
        facts = _folded(world, cur, frame, as_of)
        nxt = next((str(facts[a]) for a in _CONTAINMENT if facts.get(a)), "")
        if not nxt or nxt in seen:
            break
        path.append(nxt)
        seen.add(nxt)
        cur = nxt
    return path


def _labels(world: Any, frame: str, as_of: float | None, protagonist: str) -> list[tuple[str, str]]:
    """(entity, label) for every player-frame name/alias that could match a line:
    no people (they keep CALLED FOR SOMEONE NOT HERE), no short labels, no deixis."""
    out: list[tuple[str, str]] = []
    for attr in _LABEL_ATTRS:
        for row in frame_facts(world, frame, attribute=attr, as_of=as_of):
            ent, label = str(row.entity), str(row.value or "").strip()
            if (ent.startswith("person:") or ent == protagonist
                    or len(label) < _MIN_LABEL or is_deixis(label)):
                continue
            out.append((ent, label))
    return out


def named_elsewhere(world: Any, *, player_frame: str, player_input: str, protagonist: str,
                    scene: str | None, scene_features: list, ancestors: list,
                    as_of: float | None = None,
                    cap: int = NAMED_ELSEWHERE_CAP) -> list[tuple[str, str, str]]:
    """`(entity, the label the player used, the nearest place's display name)` for each
    thing the player's line names that the player frame places elsewhere, in the order
    named, at most `cap`.

    - Known here (no line): the thing's path reaches the here-set: the scene, its
      features, or the protagonist (carried).
    - Underdetermined (no line): its nearest place is an ancestor of the scene; "in the
      fortress" while the player stands in a room of the fortress proves nothing.
    - No player-frame path to a place (no line): nothing is asserted from canon.
    Directional on purpose (cr r2 P1): a shared ancestor never makes two rooms one."""
    if not scene or not player_input.strip():
        return []
    here = {scene, protagonist, *map(str, scene_features)}
    above = set(map(str, ancestors))
    hits: list[tuple[int, str, str]] = []
    for ent, label in _labels(world, player_frame, as_of, protagonist):
        m = re.search(rf"(?<!\w){re.escape(label)}(?!\w)", player_input, re.IGNORECASE)
        if m:
            hits.append((m.start(), ent, label))
    out: list[tuple[str, str, str]] = []
    done: set[str] = set()
    for _pos, ent, label in sorted(hits, key=lambda h: (h[0], -len(h[2]))):
        if ent in done or ent in here:
            continue
        done.add(ent)
        path = _known_path(world, ent, player_frame, as_of)
        if any(node in here for node in path):
            continue  # known here (on a table here, in this room's alcove, carried)
        place = next((node for node in path if node.startswith("place:")), "")
        if not place or place in above:
            continue  # no known place, or only a coarse ancestor: underdetermined
        pname = _folded(world, place, player_frame, as_of).get("name")
        out.append((ent, label, str(pname) if pname else human_name_typed_id(place)))
        if len(out) >= cap:
            break
    return out
