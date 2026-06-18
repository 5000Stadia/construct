"""The arc grammar as dataclasses (ARC-LAYER §2).

These are the host's working representation of what gets committed to
the `plot:` frame via `ingest_structured(frame=...)` at session zero.
Serialization to engine items happens in the (post-freeze) adapter; this
module is pure structure.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from construct.arc.conditions import Expr


class Phase(enum.Enum):
    SETUP = "setup"
    RISING = "rising"
    CRISIS = "crisis"
    CLIMAX = "climax"
    FALLING = "falling"


class Weight(enum.Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    FLAVOR = "flavor"


class Rung(enum.Enum):
    SURFACE = "surface"
    DRAW = "draw"
    CONVERGE = "converge"
    CONFRONT = "confront"
    REFUSAL = "refusal"


@dataclass(frozen=True)
class Beat:
    """A world-state condition with narrative weight; never a scripted
    scene. Path-independent by definition (§2.2)."""

    beat_id: str
    phase: Phase
    weight: Weight
    achievable_via: Expr
    unreachable_if: Expr | None = None
    #: A reveal beat (PB AKA-CORRELATION-V1, element 3): when achieved, the two
    #: entities are `correlate`d — declared facets of one identity, as-of this
    #: turn — WITHOUT merging. Before the beat they read separate (mystery holds);
    #: after, the explicit correlated/union read links them. None = ordinary beat.
    correlates: tuple[str, str] | None = None


@dataclass(frozen=True)
class Clock:
    """A pre-authored conditional process, run by the host's
    deterministic executor (§2.4). `effects` are opaque structured items
    destined for `ingest_structured`; every effect must carry a
    `caused_by` chain into existing canon (the diegesis invariant —
    auditable, §9d)."""

    clock_id: str
    fires_when: Expr
    effects: tuple[dict, ...]
    bound_to: str | None = None  # beat_id or arc_id
    rung: Rung | None = None
    rearm: str = "once"  # "once" | "repeat"


@dataclass(frozen=True)
class ConclusionShape:
    """The destination: a state-shape plus a character delta (§6),
    evaluated continuously like a beat — three outcomes (continue /
    early success / repair-or-refusal)."""

    shape_id: str
    delta_type: str  # drive_inverted | desire_at_cost | desire_renounced
    #               | identity_accepted | homecoming_changed
    tension: tuple[str, str, str]  # (entity, stronger_drive, weaker_drive)
    world_condition: Expr
    premise: Expr
    refusal_variant_id: str


@dataclass(frozen=True)
class Arc:
    """The hidden authored destination, complete (§2.1)."""

    arc_id: str
    protagonist: str
    shape: ConclusionShape
    beats: tuple[Beat, ...]
    clocks: tuple[Clock, ...]
    refusal_clock: Clock
    climax_ready_k: int
    climax_ready_beats: tuple[str, ...]
    phase_budget: dict[Phase, int] = field(default_factory=dict)
    #: An optional explicit LOSS terminal for win_loss mode (WIN-LOSS §4/§10):
    #: the event/state that ends the story in defeat (detection, capture,
    #: death). When it holds, `arc_outcome` reads `"lost"` — alongside the
    #: refusal clock, which always backstops. None = loss only by refusal
    #: timeout. Never a player-facing row; evaluated host-side over reads.
    failure_when: Expr | None = None

    def beat(self, beat_id: str) -> Beat:
        for b in self.beats:
            if b.beat_id == beat_id:
                return b
        raise KeyError(beat_id)
