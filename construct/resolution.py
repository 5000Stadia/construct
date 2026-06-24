"""Action resolution — the pre-rolled outcome deck (ACTION-RESOLUTION.md).

When the turn loop judges a player action UNCERTAIN (real resistance / a notable
unknown — combat, a risky leap, an iffy lie), it draws the next outcome TIER from a
pre-rolled deck. Assured actions (a proficient character doing a commonplace thing)
never draw — they just succeed.

The deck is the founder's latency-conscious design: NO per-check model call. A
shuffled bag of 100 tiers honoring a fixed distribution is generated deterministically
from a per-playthrough seed; each draw advances a persisted cursor; a fresh batch is
generated (same seed, next batch index) when the 100 is spent. Only the seed + cursor
live on the session frame (small, replayable), so the whole deck is reproducible.

Tier dictates WHAT happens (succeed/fail + the twist); the narrator improvises HOW.
"""
from __future__ import annotations

import random
from typing import Any

SESSION = "session:main"
_DECK_ENTITY = "session:resolution"
_BAG_SIZE = 100

#: tier key -> the narrator directive gloss. Fail-forward: every outcome has a twist.
TIERS: dict[str, str] = {
    "terrible_failure":
        "a TERRIBLE FAILURE — the attempt fails badly and brings a real, immediate "
        "negative consequence",
    "failure_opportunity":
        "a FAILURE — the attempt does not work, but it opens a NEW, unexpected "
        "opportunity the player can seize",
    "success_cost":
        "a SUCCESS WITH A COST — the attempt works, but at an unexpected price "
        "(something is lost, spent, noticed, or set in motion)",
    "complete_success":
        "a COMPLETE SUCCESS — the attempt works cleanly AND yields an additional boon",
}

#: The fixed distribution (founder, skewed to success): out of 100 draws.
_DISTRIBUTION: dict[str, int] = {
    "terrible_failure": 10,
    "failure_opportunity": 20,
    "success_cost": 55,
    "complete_success": 15,
}

#: The canonical (unshuffled) bag — the multiset the per-batch shuffle permutes.
_BAG: list[str] = [t for t, n in _DISTRIBUTION.items() for _ in range(n)]
assert len(_BAG) == _BAG_SIZE, "resolution bag must total 100"


def _batch(seed: int, index: int) -> list[str]:
    """The shuffled 100-tier bag for batch `index`, deterministic in (seed, index).
    Same seed+index → same order, so the deck is fully reproducible from the two
    persisted ints — no need to store the list itself."""
    rng = random.Random(f"{seed}-{index}")  # str seed (a tuple isn't a valid seed)
    bag = list(_BAG)
    rng.shuffle(bag)
    return bag


def _state(reads: Any) -> tuple[int, int]:
    """(seed, cursor) from the session frame; (0, 0) sentinel before first draw."""
    def _int(attr: str) -> int | None:
        v = reads.state(_DECK_ENTITY, attr, frame=SESSION)
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    return _int("seed") or 0, _int("cursor") or 0


def draw_tier(reads: Any, p: Any, *, seed_source: int | None = None) -> str:
    """Draw the NEXT outcome tier, advancing the persisted cursor (and minting the
    deck seed on the first draw). Refills automatically every 100 draws. Pure host
    logic — no model call. `reads` reads the (seed, cursor) state; `p` is the
    PORCELAIN (the turn loop's `p`), used to persist them. `seed_source` lets tests
    pin the seed; otherwise a fresh random seed is minted once and persisted."""
    seed, cursor = _state(reads)
    if seed == 0:  # first ever draw — mint + persist the playthrough's deck seed
        seed = seed_source if seed_source is not None else random.Random().randint(1, 2**31)
    tier = _batch(seed, cursor // _BAG_SIZE)[cursor % _BAG_SIZE]
    p.ingest_structured([
        {"entity": _DECK_ENTITY, "attribute": "seed", "value": str(seed), "timeless": True},
        {"entity": _DECK_ENTITY, "attribute": "cursor", "value": str(cursor + 1),
         "timeless": True},
    ], frame=SESSION)
    return tier


def directive(tier: str, uncertain_of: str = "") -> str:
    """The RESOLUTION directive added to the narrator briefing for a drawn tier."""
    gloss = TIERS.get(tier, TIERS["success_cost"])
    stake = f" (what was uncertain: {uncertain_of})" if uncertain_of else ""
    return (f"RESOLUTION — the player's attempt resolves as {gloss}{stake}. Render this "
            f"outcome diegetically as what HAPPENS — do not state odds, dice, or that a "
            f"check occurred; the result simply unfolds. The twist (consequence / "
            f"opportunity / cost / boon) is concrete and becomes part of the world.")
