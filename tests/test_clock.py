"""Diegetic time — the world-specific clock (DIEGETIC-TIME.md). Pure host logic,
no model: calendar phase derivation scales to any day length, time advances and
never rewinds, and the player's waits jump forward correctly."""

from construct.clock import Calendar, Clock, DEFAULT_HOURS_PER_DAY


def test_default_calendar_phases():
    c = Calendar()
    assert c.hours_per_day == DEFAULT_HOURS_PER_DAY
    assert c.phase_of(0) == "night"
    assert c.phase_of(12 * 60) == "noon"        # midday on a 24h day
    assert c.phase_of(8 * 60) == "morning"
    assert c.phase_of(23 * 60) == "night"


def test_phases_scale_to_a_72_hour_day():
    # Founder's case: a world with 72-hour days. Noon is hour 36, not 12.
    c = Calendar(hours_per_day=72)
    assert c.phase_of(36 * 60) == "noon"
    assert c.phase_of(12 * 60) != "noon"        # still morning-ish on a long day
    assert c.minutes_per_day == 72 * 60


def test_day_rolls_over():
    c = Calendar()                               # 24h
    assert c.day_of(0) == 1
    assert c.day_of(24 * 60) == 2
    assert c.day_of(50 * 60) == 3


def test_advance_never_rewinds():
    clk = Clock(minutes=600)
    clk.advance(30)
    assert clk.minutes == 630
    clk.advance(-100)                            # story-time doesn't go backward
    assert clk.minutes == 630


def test_jump_to_phase_goes_forward():
    c = Calendar()
    clk = Clock(minutes=10 * 60, calendar=c)     # 10:00, morning
    clk.jump_to_phase("dusk")                    # "wait until sunset"
    assert clk.phase == "dusk"
    assert clk.minutes > 10 * 60                 # moved forward, same day
    assert clk.day == 1


def test_jump_to_phase_already_past_rolls_to_next_day():
    c = Calendar()
    clk = Clock(minutes=20 * 60, calendar=c)     # 20:00, evening — dawn already passed
    clk.jump_to_phase("dawn")
    assert clk.phase == "dawn"
    assert clk.day == 2                           # next morning


def test_jump_days_preserves_time_of_day():
    c = Calendar()
    clk = Clock(minutes=14 * 60, calendar=c)     # 14:00, afternoon
    clk.jump_days(3)
    assert clk.day == 4
    assert clk.phase == "afternoon"               # same time, three days on


def test_two_planets_desync_on_one_universal_counter():
    # Founder's space adventure: each planet maps the SAME elapsed time to its own
    # local time-of-day, out of phase. One universal counter, two calendars.
    elapsed = 6 * 60                              # 6h of real time have passed
    planet_a = Calendar(hours_per_day=24, offset_minutes=12 * 60)   # +12h: it's evening
    planet_b = Calendar(hours_per_day=24, offset_minutes=0)         # morning
    assert planet_a.phase_of(elapsed) != planet_b.phase_of(elapsed)
    # A longer-day planet scales too.
    long_planet = Calendar(hours_per_day=40)
    assert long_planet.day_of(50 * 60) == 2       # a 40h day rolls over at hour 40


def test_offset_jump_returns_to_universal_minutes():
    # Wait-until-dusk on an offset body returns a universal-elapsed target whose
    # local phase is dusk.
    cal = Calendar(hours_per_day=24, offset_minutes=300)
    clk = Clock(minutes=0, calendar=cal)
    clk.jump_to_phase("dusk")
    assert clk.phase == "dusk"
    assert clk.minutes >= 0


class _FakeP:
    def __init__(self, facts):
        self.facts = facts  # (entity, attr) -> value

    def state(self, entity, attribute, frame="canon", as_of=None):
        if (entity, attribute) in self.facts:
            return {"status": "known", "fact": {"value": self.facts[(entity, attribute)]}}
        return {"status": "unknown"}


class _FakeW:
    def __init__(self, facts):
        self.porcelain = _FakeP(facts)


def test_governing_calendar_defaults_to_earth():
    from construct.clock import governing_calendar
    w = _FakeW({})                                   # no calendar anywhere
    assert governing_calendar(w, "place:office").hours_per_day == 24


def test_planet_day_length_is_a_constitutive_attribute():
    # Founder: a non-Earth world's day/night is a universal condition of that
    # planet — read straight off the place as a plain constitutive attribute.
    from construct.clock import governing_calendar
    w = _FakeW({("place:kestrel_9", "hours_per_day"): 72})
    assert governing_calendar(w, "place:kestrel_9").hours_per_day == 72
    # A different planet with no override falls back to Earth-default.
    assert governing_calendar(w, "place:earthlike").hours_per_day == 24


def test_render_and_roundtrip():
    c = Calendar(hours_per_day=30, phases=[[0.0, "dark"], [0.5, "light"]])
    assert Calendar.from_dict(c.to_dict()).hours_per_day == 30
    clk = Clock(minutes=20 * 60, calendar=c)
    assert "Day 1" in clk.render()
    assert clk.phase in ("dark", "light")


def test_estimate_elapsed_cohort_shape():
    from construct import cohorts
    from construct.provider import StubProvider
    p = StubProvider([{"advance_minutes": 0, "jump_to_phase": "dusk",
                       "jump_days": 0, "reason": "waits for sunset"}])
    out = cohorts.estimate_elapsed(p, now="Day 1, morning", hours_per_day=24,
                                   phases=["dawn", "noon", "dusk", "night"],
                                   action="I wait until sunset", narration="")
    assert out["jump_to_phase"] == "dusk"


def test_deterministic_elapsed_skips_model_for_ordinary_turns():
    # TURN-LATENCY Lever C (Cx 077): ordinary turns get a deterministic minute delta (no model
    # call); explicit temporal language returns None → the caller falls back to the model.
    from construct.clock import deterministic_elapsed
    # ordinary actions → a deterministic estimate by kind
    assert deterministic_elapsed("I examine the doctor's bag closely")["advance_minutes"] == 12
    assert deterministic_elapsed("I go to the study")["advance_minutes"] == 6
    assert deterministic_elapsed("I ask Hobbes who he saw")["advance_minutes"] == 3
    assert deterministic_elapsed("I look around the parlor")["advance_minutes"] == 1
    assert deterministic_elapsed("I take the candle")["advance_minutes"] == 2
    assert deterministic_elapsed("I press the doctor", moved=True)["advance_minutes"] == 6
    # explicit temporal language → defer to the model (None)
    assert deterministic_elapsed("I wait until sunset") is None
    assert deterministic_elapsed("I sleep through the night") is None
    assert deterministic_elapsed("Three days later, I return") is None
