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
class Pillar:
    """A CAUSE of the conclusion (STORY-SHAPES §0a/§8): a causal element whose
    coverage helps determine the narrated conclusory scene (the EFFECT) — never a
    win/loss verdict. Coverage is tri-state, computed host-side from the PLAYER
    frame: 'genuine' (a genuine clue established the cause), 'false' (a red herring
    is held as true — a wrong case built on it), 'unfilled' (neither).

    Pillars are host-side control data; the engine never reads them. `genuine_via`
    / `false_via` are conditions over the player's knowledge frame (the clues they
    have actually surfaced), so coverage advances as the player interviews the cast
    (the surface pillars fill through, §8). `required` pillars are the causes that
    must be addressed for the case to land; optional pillars enrich it."""

    pillar_id: str
    label: str
    required: bool = True
    genuine_via: Expr | None = None
    false_via: Expr | None = None


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
class Pin:
    """A pinned-awareness channel entry (PINNED-AWARENESS spec): an existing
    canon fact/condition marked awareness-bearing — foregrounded every turn
    its scope is active, ranked by salience. The base abstraction of which a
    clock is the temporal-spending specialization (Kernos 060 #1). Stored in
    a host-owned frame, NEVER canon; the engine never reads pins; minting is
    host-only (never an agent tool, Kernos 060 #7).

    Scope (first build: region / temporal / social-entity-presence only —
    group presence deferred, Cx 062 #4):
    - region   → active while `anchor` is in the protagonist's containment
      ancestry (computed once/turn; O(1) membership per pin).
    - temporal → active while `awareness_as_of ∈ [valid_from, valid_to)`.
    - social   → active while `anchor` (a single entity) is present in scene.
    `directive` is the host-facing phrasing the narrator weaves in (the
    meaning layer); the subject is read in the player frame for dedupe and
    salience, never briefed raw (no leak, Cx 062 #3)."""

    pin_id: str
    scope_kind: str  # "region" | "temporal" | "social"
    subject_entity: str
    directive: str
    subject_attribute: str | None = None
    anchor: str | None = None  # region ancestor / social entity
    valid_from: float | None = None
    valid_to: float | None = None
    severity: float = 1.0  # [0,1] base weight, modulates salience
    #: A foreshadowing/clue pin: its salience ESCALATES with arc progress, so the
    #: clue gets louder as the player closes in on the reveal (the good-DM
    #: clue-trail, NARRATIVE-FLAVOR-INGEST v2). Steady when False.
    escalates: bool = False


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
    #: The pinned-awareness channel (PINNED-AWARENESS): host-owned, briefed
    #: every turn a pin's scope is active. Empty = no pins.
    pins: tuple[Pin, ...] = ()
    #: The causal pillars of the conclusion (STORY-SHAPES §0a/§8). Coverage is
    #: derived host-side (executor.arc_coverage); the conclusory scene is narrated
    #: as the EFFECT of this coverage, not a win/loss verdict. Empty = the arc uses
    #: the legacy world_condition terminal only (backward compatible).
    pillars: tuple[Pillar, ...] = ()

    def beat(self, beat_id: str) -> Beat:
        for b in self.beats:
            if b.beat_id == beat_id:
                return b
        raise KeyError(beat_id)
