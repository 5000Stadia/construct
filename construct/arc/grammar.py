"""The arc grammar as dataclasses (ARC-LAYER §2).

These are the host's working representation of what gets committed to
the `plot:` frame via `ingest_structured(frame=...)` at session zero.
Serialization to engine items happens in the (post-freeze) adapter; this
module is pure structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from construct.arc.conditions import Expr

# --- the arc string vocabularies (audit 2026-10 arc F7) -------------------
# Every enum below is a `StrEnum` whose member VALUES are the exact strings the
# plot rows, JSON caches and prompts already carry: a member == its string, hashes
# like it, and serializes as it, so persistence is byte-identical and bare-string
# comparisons elsewhere keep working. Write the member at definition sites and
# comparisons; write `.value` (the plain str) where a row/item is composed.


class Phase(StrEnum):
    SETUP = "setup"
    RISING = "rising"
    CRISIS = "crisis"
    CLIMAX = "climax"
    FALLING = "falling"


class Weight(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    FLAVOR = "flavor"


class Rung(StrEnum):
    SURFACE = "surface"
    DRAW = "draw"
    CONVERGE = "converge"
    CONFRONT = "confront"
    REFUSAL = "refusal"


class BeatStatus(StrEnum):
    """A beat's stored `status` row (absent reads as PENDING)."""
    PENDING = "pending"
    ACHIEVED = "achieved"
    CLOSED = "closed"


class ClockStatus(StrEnum):
    """A clock's stored `status` row."""
    ARMED = "armed"
    FIRED = "fired"


class Rearm(StrEnum):
    """A clock's `rearm` policy."""
    ONCE = "once"
    REPEAT = "repeat"


class Lifecycle(StrEnum):
    """An arc's lifecycle (LIVING-WORLD-GENERATOR §3): ACTIVE is live, the other
    four are terminal."""
    ACTIVE = "active"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"
    INCOMPLETABLE = "incompletable"


#: The terminal lifecycles (everything but ACTIVE), in the stored order.
LIFECYCLE_TERMINALS: tuple[Lifecycle, ...] = (
    Lifecycle.WON, Lifecycle.LOST, Lifecycle.CANCELLED, Lifecycle.INCOMPLETABLE)


class Outcome(StrEnum):
    """`arc_outcome`'s binary classification (the narrative-shaped ending is
    `OutcomeShape`)."""
    WON = "won"
    LOST = "lost"


class Coverage(StrEnum):
    """Tri-state coverage of one causal pillar."""
    GENUINE = "genuine"
    FALSE = "false"
    UNFILLED = "unfilled"


class OutcomeShape(StrEnum):
    """The narrative-shaped ending vocabulary (CONCLUSIVE-OUTCOME-SPEC C1)."""
    TRIUMPH = "triumph"
    COSTLY_VICTORY = "costly_victory"
    BITTERSWEET = "bittersweet"
    PARTIAL = "partial"
    FAILURE = "failure"
    QUIET_FAILURE = "quiet_failure"


class WorldEvent(StrEnum):
    """An external result read alongside coverage (Contest's scoreboard)."""
    WIN = "win"
    LOSS = "loss"


class DeltaType(StrEnum):
    """The character-delta a ConclusionShape declares (ARC-LAYER §6)."""
    DRIVE_INVERTED = "drive_inverted"
    DESIRE_AT_COST = "desire_at_cost"
    DESIRE_RENOUNCED = "desire_renounced"
    IDENTITY_ACCEPTED = "identity_accepted"
    HOMECOMING_CHANGED = "homecoming_changed"


class CostDisposition(StrEnum):
    """How a shape's pillar coverage is READ at the conclusion (CATALOG §0)."""
    PERIL_REDEMPTION = "peril_redemption"
    REPAIR = "repair"
    SACRIFICE = "sacrifice"
    FAIL_FORWARD = "fail_forward"


class TerminalOwner(StrEnum):
    """What closes the story for a shape (Cx 141)."""
    COMMITMENT = "commitment"
    WORLD_EVENT = "world_event"


class PinScope(StrEnum):
    """A pin's scope kind (PINNED-AWARENESS)."""
    REGION = "region"
    TEMPORAL = "temporal"
    SOCIAL = "social"


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
    rearm: str = Rearm.ONCE  # a `Rearm` ("once" | "repeat")


@dataclass(frozen=True)
class ConclusionShape:
    """The destination: a state-shape plus a character delta (§6),
    evaluated continuously like a beat — three outcomes (continue /
    early success / repair-or-refusal)."""

    shape_id: str
    delta_type: str  # a `DeltaType` value (kept `str`: a stored row may carry any text)
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
    scope_kind: str  # a `PinScope` value ("region" | "temporal" | "social")
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
class Gauge:
    """A numeric quantity as a live dramatic constraint (GAUGE-PRIMITIVE.md): an
    `accrue` total (`gauge_level` on `gauge:<slug>`) that drains/replenishes each
    turn and, when it crosses its floor, ends the story. Host control data — the
    engine reads only the folded number; "the tank is tense" is never stored.

    Per turn the host appends a SIGNED delta = `base_delta` (the deterministic
    drift) + every `action_modifiers` keyword present in the player's action (a
    cheap substring match — running burns more air, resting buys some back). The
    LM is consulted only for residual rate the table doesn't know (a later add).
    `terminal_on_floor` folds `Quantity(<= floor)` into the arc's `failure_when`
    (the LOSS path; the positive `world_condition` still wins a same-tick tie).
    `costly_band` is the fraction of range below which a WIN colors as costly
    (per-shape config overrides this default)."""

    gauge_id: str           # "gauge:oxygen"
    label: str              # "oxygen reserve" — narrator phrasing
    baseline: float
    floor: float
    base_delta: float       # per-turn deterministic drift (signed)
    ceiling: float | None = None
    terminal_on_floor: bool = True
    costly_band: float = 0.25
    #: (keyword, signed_delta) — applied when the lowercased action contains the
    #: keyword. Deterministic, table-known action modulation (no model call).
    action_modifiers: tuple[tuple[str, float], ...] = ()


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
    #: Numeric dramatic constraints (GAUGE-PRIMITIVE.md): drained/replenished each
    #: turn; a terminal gauge's floor folds into `failure_when`. Empty = none.
    gauges: tuple[Gauge, ...] = ()

    def beat(self, beat_id: str) -> Beat:
        for b in self.beats:
            if b.beat_id == beat_id:
                return b
        raise KeyError(beat_id)
