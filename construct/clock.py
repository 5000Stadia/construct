"""Diegetic time — the story's own clock, on a world-specific calendar
(`docs/design/DIEGETIC-TIME.md`).

Story time advances by what HAPPENS, not by turn count, and the SHAPE of time is
a property of the world (a world may have 72-hour days). This module is the pure,
deterministic host logic: a `Calendar` (the world's time model) and a `Clock` (the
current moment on it). The per-turn LLM estimate of *how much* time passed lives in
`cohorts.estimate_elapsed`; committing `time:now` to canon lives in the turn loop.
Phase is ALWAYS derived through the calendar — never a hardcoded 24h.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_HOURS_PER_DAY = 24

#: Default time-of-day bands as (start_fraction_of_day, name), ascending. The
#: phase for a within-day fraction f is the last band whose start ≤ f. Defined as
#: FRACTIONS so they scale to any `hours_per_day` (a 72h day's noon is hour 36).
DEFAULT_PHASES: list[tuple[float, str]] = [
    (0.00, "night"),
    (0.21, "dawn"),
    (0.29, "morning"),
    (0.46, "noon"),
    (0.54, "afternoon"),
    (0.71, "dusk"),
    (0.79, "evening"),
    (0.92, "night"),
]


@dataclass
class Calendar:
    """A time model — the world's default, or a single LOCATION's (a planet has its
    own orbital day). Default is Earth-like; overrides set `hours_per_day`/`phases`.
    `offset_minutes` is where this body sits in its cycle at t=0, so two places with
    the same day length can still be out of phase (noon here, midnight there)."""

    hours_per_day: int = DEFAULT_HOURS_PER_DAY
    phases: list[tuple[float, str]] = field(
        default_factory=lambda: list(DEFAULT_PHASES))
    offset_minutes: int = 0

    @property
    def minutes_per_day(self) -> int:
        return self.hours_per_day * 60

    def _local(self, minutes: int) -> int:
        """Universal elapsed → this body's LOCAL minutes (its own phase offset)."""
        return minutes + self.offset_minutes

    @property
    def phase_names(self) -> list[str]:
        # Distinct names in band order (night appears once for the menu).
        seen, out = set(), []
        for _, n in self.phases:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _band_starts(self) -> list[tuple[int, str]]:
        """Phase bands as (start_MINUTE_within_day, name), ascending — the single
        integer source of truth so `phase_of` and `next_phase_start` never
        disagree by a rounding minute."""
        mpd = self.minutes_per_day
        return [(int(round(s * mpd)), n) for s, n in self.phases]

    def phase_of(self, minutes: int) -> str:
        within = self._local(minutes) % self.minutes_per_day
        bands = self._band_starts()
        name = bands[0][1]
        for start, n in bands:
            if within >= start:
                name = n
            else:
                break
        return name

    def day_of(self, minutes: int) -> int:
        return self._local(minutes) // self.minutes_per_day + 1

    def hour_of(self, minutes: int) -> int:
        return int((self._local(minutes) % self.minutes_per_day) // 60)

    def next_phase_start(self, minutes: int, phase: str) -> int:
        """Universal-elapsed minutes at the NEXT onset of `phase` at/after
        `minutes` on THIS body (a forward 'wait until sunset'). Falls back to now
        if the phase is unknown."""
        mpd = self.minutes_per_day
        local = self._local(minutes)
        within = local % mpd
        day_start_local = local - within
        starts = sorted({m for m, n in self._band_starts() if n == phase})
        if not starts:
            return minutes
        future_today = [m for m in starts if m > within]
        target_local = (day_start_local + min(future_today) if future_today
                        else day_start_local + mpd + min(starts))
        return target_local - self.offset_minutes   # back to universal elapsed

    def to_dict(self) -> dict:
        return {"hours_per_day": self.hours_per_day,
                "phases": [[s, n] for s, n in self.phases],
                "offset_minutes": self.offset_minutes}

    @classmethod
    def from_dict(cls, data: dict | None) -> "Calendar":
        data = data or {}
        hpd = int(data.get("hours_per_day") or DEFAULT_HOURS_PER_DAY)
        raw = data.get("phases")
        phases = ([(float(s), str(n)) for s, n in raw] if raw else list(DEFAULT_PHASES))
        phases.sort()
        return cls(hours_per_day=hpd, phases=phases,
                   offset_minutes=int(data.get("offset_minutes") or 0))


@dataclass
class Clock:
    """The current diegetic moment on a `Calendar`. `minutes` is the absolute
    in-world accumulator since the story's start; `day`/`phase` derive from it."""

    minutes: int = 0
    calendar: Calendar = field(default_factory=Calendar)

    @property
    def phase(self) -> str:
        return self.calendar.phase_of(self.minutes)

    @property
    def day(self) -> int:
        return self.calendar.day_of(self.minutes)

    @property
    def hour(self) -> int:
        return self.calendar.hour_of(self.minutes)

    def advance(self, minutes: int) -> None:
        """Move time forward (never backward — story-time doesn't rewind)."""
        if minutes and minutes > 0:
            self.minutes += int(minutes)

    def jump_to_phase(self, phase: str) -> None:
        """Skip forward to the next onset of a time-of-day ('wait until sunset')."""
        self.minutes = self.calendar.next_phase_start(self.minutes, phase)

    def jump_days(self, days: int) -> None:
        """Skip whole days, preserving the time of day ('three days later')."""
        if days and days > 0:
            self.minutes += int(days) * self.calendar.minutes_per_day

    def render(self) -> str:
        """A compact phrase for the narrator briefing: 'Day 2, dusk'."""
        return f"Day {self.day}, {self.phase}"


# -- canon storage seam (DIEGETIC-TIME.md; accrue per Kernos 074) -----------
ELAPSED_ENTITY = "time:elapsed"
ELAPSED_ATTR = "elapsed_minutes"          # declared fold_policy=accrue in semantics.py
CALENDAR_ENTITY = "time:calendar"


def _state_value(porcelain, entity, attribute):
    try:
        st = porcelain.state(entity, attribute)
    except Exception:
        return None
    if isinstance(st, dict) and st.get("status") in ("known", "conflicted"):
        return (st.get("fact") or {}).get("value")
    return None


def _to_number(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v))
    except (TypeError, ValueError):
        return None


def _calendar_from(porcelain, entity: str) -> Calendar | None:
    """A calendar established ON `entity` — preferring a full `calendar`/`config`
    JSON blob, else a plain CONSTITUTIVE day-length attribute (a planet's day/night
    is a universal condition of that place, stored like any other physical truth —
    founder). None if the entity establishes no time model."""
    import json
    for attr in ("calendar", "config"):
        raw = _state_value(porcelain, entity, attr)
        if raw:
            try:
                return Calendar.from_dict(json.loads(raw) if isinstance(raw, str) else raw)
            except Exception:
                pass
    for attr in ("hours_per_day", "day_hours", "day_length_hours"):
        n = _to_number(_state_value(porcelain, entity, attr))
        if n and n > 0:
            return Calendar(hours_per_day=int(n))
    return None


def governing_calendar(world, location: str | None = None) -> Calendar:
    """The calendar governing time-of-day for the player's CURRENT place: the
    place's own established day/night (a planet's universal condition) → else the
    world default (`time:calendar`) → else Earth-like (the common case; non-Earth
    cycles are a rare authored detail). Per DIEGETIC-TIME.md."""
    p = world.porcelain
    for entity in ([location] if location else []) + [CALENDAR_ENTITY]:
        cal = _calendar_from(p, entity)
        if cal is not None:
            return cal
    return Calendar()


def read_clock(world, location: str | None = None) -> Clock:
    """The current diegetic moment: the folded elapsed total on the governing
    calendar (defaults: 0 minutes, Earth-like — so worlds with no clock seeded
    still read coherently)."""
    total = _state_value(world.porcelain, ELAPSED_ENTITY, ELAPSED_ATTR)
    minutes = int(total) if isinstance(total, (int, float)) else 0
    return Clock(minutes=minutes, calendar=governing_calendar(world, location))


def commit_elapsed(world, delta_minutes: int) -> None:
    """Append `+delta_minutes` to the accrue counter (seeding the baseline once).
    Append-only/monotonic — story-time never rewinds (Kernos 074)."""
    if not delta_minutes or delta_minutes <= 0:
        return
    p = world.porcelain
    if _state_value(p, ELAPSED_ENTITY, ELAPSED_ATTR) is None:
        p.ingest_structured([{"entity": ELAPSED_ENTITY, "attribute": ELAPSED_ATTR,
                              "value": 0, "value_type": "literal"}])
    p.ingest_structured([{"entity": ELAPSED_ENTITY, "attribute": ELAPSED_ATTR,
                          "value": int(delta_minutes), "value_type": "delta"}])


#: Explicit temporal language that warrants the MODEL estimate — a real wait / jump / rest /
#: travel-montage the deterministic table can't resolve (it may cross a phase or day boundary).
_TEMPORAL_MARKERS = (
    "wait", "until", "sleep", "asleep", "rest", "nap", "doze", "overnight", "tomorrow",
    "next day", "next morning", "hours", "hour later", "an hour", "days", "day later",
    "later", "dawn", "dusk", "sunrise", "sunset", "morning", "noon", "midday", "afternoon",
    "evening", "nightfall", "midnight", "week", "month", "year", "linger for", "all night",
)
#: Action-verb → minutes buckets for the deterministic estimate (TURN-LATENCY C, Cx 077).
# NB: "study" is intentionally OMITTED — it collides with the common room noun ("the study");
# examine/inspect/search/scour cover the intent without the false positive.
_EXAMINE_VERBS = frozenset({"examine", "inspect", "search", "scour",
                            "comb", "investigate", "scrutinize"})
_MOVE_VERBS = frozenset({"go", "walk", "head", "travel", "enter", "leave", "cross",
                         "climb", "descend", "follow", "approach", "return"})
_TAKE_VERBS = frozenset({"take", "grab", "pick", "pocket", "open", "use", "pour", "lift",
                         "hand", "give", "draw"})
_GLANCE_VERBS = frozenset({"look", "glance", "observe", "watch", "listen", "consider",
                           "think", "wait", "pause", "note"})


def deterministic_elapsed(action: str, *, moved: bool = False) -> dict | None:
    """A cheap, DETERMINISTIC diegetic-time delta for ordinary turns (DIEGETIC-TIME.md /
    TURN-LATENCY Lever C, Cx 077): most turns advance time predictably by their ACTION kind, so
    the per-turn `estimate_elapsed` MODEL call is skipped. Returns an estimate dict (the same
    `{advance_minutes}` shape `delta_from_estimate` consumes) for ordinary actions, or **None**
    when the input carries explicit TEMPORAL language (a wait/jump/rest/montage) that needs the
    model to resolve a phase- or day-boundary. Best-effort + monotonic — time only goes forward."""
    low = action.lower()
    if any(m in low for m in _TEMPORAL_MARKERS):
        return None  # explicit time language → defer to the model estimate (phase/day jump)
    toks = set(low.replace(",", " ").replace(".", " ").replace("?", " ").split())
    if toks & _EXAMINE_VERBS:
        return {"advance_minutes": 12}      # close inspection / searching
    if moved or (toks & _MOVE_VERBS):
        return {"advance_minutes": 6}       # local movement within the scene/site
    if toks & _TAKE_VERBS:
        return {"advance_minutes": 2}       # take / use a simple object
    if toks & _GLANCE_VERBS:
        return {"advance_minutes": 1}       # a look / brief beat
    return {"advance_minutes": 3}           # ordinary action / questioning a person


def delta_from_estimate(clock: Clock, estimate: dict) -> int:
    """Turn the `estimate_elapsed` cohort's output into a forward delta (minutes):
    a phase wait jumps to the next onset; a day-skip adds whole days; else the
    plain minute estimate. Always ≥ 0."""
    phase = (estimate.get("jump_to_phase") or "").strip()
    days = int(estimate.get("jump_days") or 0)
    if phase:
        return max(0, clock.calendar.next_phase_start(clock.minutes, phase) - clock.minutes)
    if days > 0:
        return days * clock.calendar.minutes_per_day + max(0, int(estimate.get("advance_minutes") or 0))
    return max(0, int(estimate.get("advance_minutes") or 0))
