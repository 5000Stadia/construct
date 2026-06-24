"""The Construct dialogue tool loop (CONSTRUCT-DIALOGUE.md) — stub-driven, no
live model. Verifies that the agent's emitted tool calls are dispatched against
the accumulating brief, that the guest can keep adding indefinitely, and that
terminal actions (begin_build / pick_world) end the dialogue with the right
hand-off."""

from construct.architect import (
    BUILD, CONTINUE, LOAD, RESUME, ArchitectState, architect_step)
from construct.provider import StubProvider


def _act(tool, detail="", mode=""):
    return {"tool": tool, "detail": detail, "mode": mode}


def _turn(reply, *actions):
    return {"reply": reply, "actions": list(actions)}


def _step(provider, state, msg, worlds=("anchor",), resumable=""):
    return architect_step(provider, state, history="", user_msg=msg,
                          worlds=list(worlds), resumable=resumable)


def test_add_element_and_role_accumulate():
    p = StubProvider([
        _turn("A station noir — I like it. Who are you in it?",
              _act("add_element", "a space-station noir")),
        _turn("An AI watching every camera — wonderful.",
              _act("set_role", "the station's AI")),
    ])
    s = ArchitectState()
    r1 = _step(p, s, "noir mystery on a space station")
    assert r1.outcome == CONTINUE
    assert s.elements == ["a space-station noir"]
    _step(p, s, "can I be the station AI?")
    assert s.play_as == "the station's AI"
    assert s.elements == ["a space-station noir"]  # role isn't an element


def test_multiple_actions_in_one_turn():
    p = StubProvider([
        _turn("A noir station, and you're its AI. Noted.",
              _act("add_element", "a space-station noir"),
              _act("set_role", "the station's AI"))])
    s = ArchitectState()
    _step(p, s, "noir station and I'm the AI")
    assert s.elements == ["a space-station noir"]
    assert s.play_as == "the station's AI"


def test_keep_adding_until_satisfied_then_build():
    p = StubProvider([
        _turn("Done.", _act("add_element", "a space-station noir")),
        _turn("A T-Rex with a machine gun. Bold. Anything else?",
              _act("add_element", "a T-Rex with a machine gun somewhere aboard")),
        _turn("Then I'll cook.", _act("begin_build"))])
    s = ArchitectState()
    _step(p, s, "noir station")
    _step(p, s, "oh and a T-Rex with a machine gun")
    r = _step(p, s, "that's it, go")
    assert r.outcome == BUILD
    assert r.brief["premise"] == ("a space-station noir — a T-Rex with a "
                                  "machine gun somewhere aboard")
    assert r.brief["mode"] == "endless"  # never set an ending → safe default


def test_set_ending_win_loss_then_endless():
    p = StubProvider([
        _turn("A real case to crack.",
              _act("set_ending", "uncover who sabotaged the reactor", "win_loss")),
        _turn("Open station it is.", _act("set_ending", "", "endless"))])
    s = ArchitectState()
    _step(p, s, "I want a real ending")
    assert s.mode == "win_loss"
    assert s.win_direction == "uncover who sabotaged the reactor"
    _step(p, s, "actually just let me roam")
    assert s.mode == "endless"
    assert s.win_direction == ""  # cleared when endless


def test_win_direction_flows_into_brief():
    p = StubProvider([
        _turn("A case.", _act("set_ending", "catch the saboteur", "win_loss")),
        _turn("Cooking.", _act("begin_build"))])
    s = ArchitectState(elements=["a station noir"])
    _step(p, s, "give me a case")
    r = _step(p, s, "go")
    assert r.brief["mode"] == "win_loss"
    assert r.brief["win_direction"] == "catch the saboteur"


def test_pick_existing_world_routes_to_load():
    p = StubProvider([_turn("Opening the anchor world.",
                            _act("pick_world", "anchor"))])
    s = ArchitectState()
    r = _step(p, s, "just give me the detective one", worlds=["anchor"])
    assert r.outcome == LOAD and r.world == "anchor"


def test_set_game_type_resolves_and_mixes_into_brief():
    # The Construct can settle a primary + secondary game type (a compound); free
    # labels resolve to taxonomy keys and flow into the build brief.
    p = StubProvider([
        _turn("A heist, with court politics underneath.",
              _act("set_game_type", "heist"),
              _act("set_game_type", "political intrigue")),
        _turn("Cooking.", _act("begin_build"))])
    s = ArchitectState(elements=["a noir station"])
    _step(p, s, "make it a heist tangled in palace politics")
    assert s.game_types == ["heist", "political_intrigue"]
    r = _step(p, s, "go")
    assert r.brief["game_types"] == ["heist", "political_intrigue"]


def test_set_game_type_drops_unknown_labels():
    p = StubProvider([_turn("Noted.", _act("set_game_type", "blorp nonsense"))])
    s = ArchitectState()
    _step(p, s, "make it a blorp")
    assert s.game_types == []   # unmatched → free improvised


def test_pick_world_by_spoken_title_resolves_to_name():
    # The guest names the TITLE; pick_world resolves it to the canonical id.
    p = StubProvider([_turn("Opening The Monsoon Ledger.",
                            _act("pick_world", "The Monsoon Ledger"))])
    s = ArchitectState()
    r = architect_step(p, s, history="", user_msg="open The Monsoon Ledger",
                       worlds=["colonial", "anchor"],
                       catalog={"colonial": "The Monsoon Ledger — a river-fort siege",
                                "anchor": "The Last Honest Meter"})
    assert r.outcome == LOAD and r.world == "colonial"


def test_resume_routes_when_a_saved_game_exists():
    p = StubProvider([_turn("Welcome back — picking up where you left off.",
                            _act("resume"))])
    s = ArchitectState()
    r = _step(p, s, "continue my game", resumable="anchor")
    assert r.outcome == RESUME and r.world == "anchor"


def test_resume_ignored_without_a_saved_game():
    # The agent must never fabricate a saved game to resume.
    p = StubProvider([_turn("You don't have a game in progress yet.",
                            _act("resume"))])
    s = ArchitectState()
    r = _step(p, s, "resume", resumable="")
    assert r.outcome == CONTINUE and r.world is None


def test_pick_invalid_world_is_ignored():
    # The agent must never route to a name not in the library.
    p = StubProvider([_turn("I don't have that one — here's what I do have.",
                            _act("pick_world", "nonexistent"))])
    s = ArchitectState()
    r = _step(p, s, "load Skyrim", worlds=["anchor"])
    assert r.outcome == CONTINUE and r.world is None


def test_begin_build_outranks_same_turn_pick():
    p = StubProvider([_turn("Building fresh.",
                            _act("pick_world", "anchor"),
                            _act("begin_build"))])
    s = ArchitectState(elements=["a noir station"])
    r = _step(p, s, "go", worlds=["anchor"])
    assert r.outcome == BUILD  # an explicit go is a build, not a load


def test_chat_changes_nothing():
    p = StubProvider([_turn("I can make almost anything — a noir city, a "
                            "dying colony, a court of mages.", _act("chat"))])
    s = ArchitectState()
    r = _step(p, s, "what kinds of worlds can you make?")
    assert r.outcome == CONTINUE
    assert s.elements == [] and s.play_as == "" and s.mode == ""
    assert "noir" in r.reply


def test_summary_renders_gathered_state_fresh():
    s = ArchitectState(elements=["a station noir"], play_as="the AI",
                       mode="win_loss", win_direction="catch the saboteur")
    text = s.summary()
    assert "a station noir" in text
    assert "the AI" in text
    assert "win/loss" in text and "catch the saboteur" in text


def test_to_brief_defaults_mode_endless():
    s = ArchitectState(elements=["a quiet village"])
    assert s.to_brief()["mode"] == "endless"
