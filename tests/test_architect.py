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


def test_opening_beat_is_an_interview_question_with_sparks():
    # FOUNDER (2026-07-04, "with no question"): the new-build opening was a bare
    # either/or fork that ended without asking anything. The opening is now the
    # interview's FIRST BEAT: contrasting concrete sparks, the open door, surprise-me
    # — and it must END WITH A DIRECT QUESTION. Every interview reply asks.
    from construct.cohorts import architect_turn
    from construct.provider import StubProvider
    prov = StubProvider([{"reply": "…", "actions": []}])
    architect_turn(prov, history="", brief_so_far="", latest="something new please",
                   catalog=None, worlds=[], resumable="")
    prompt = prov.calls[0][0]
    assert "your FIRST move IS the interview's first beat" in prompt
    assert "never a bare either/or that ends without asking anything" in prompt
    assert "CONTRASTING sparks" in prompt
    assert "END WITH A DIRECT QUESTION" in prompt
    assert "EVERY interview reply ends with a QUESTION" in prompt
    assert "THE SPARK" in prompt                      # the personal-ingredient beat
    assert "odd little ingredient" in prompt
    # the old flat-fork mandate is gone
    assert "offer the fork plainly" not in prompt
    assert "Don't launch into the multi-step interview until they've picked" not in prompt


def test_pure_surprise_rolls_then_asks_then_builds_on_yes():
    # FOUNDER (2026-07-05): an empty-brief 'surprise me' must not fall to the
    # model's prior — the HOST rolls a shape from the taxonomy and ASKS candidly
    # ("how does an X sound?"); the build waits for the guest's yes, then uses
    # exactly the offered shape.
    from construct.architect import ArchitectState, BUILD, CONTINUE, architect_step
    from construct.play_styles_data import STYLE_CARDS
    from construct.provider import StubProvider
    prov = StubProvider([
        {"reply": "As you wish.",
         "actions": [{"tool": "begin_build", "detail": "", "mode": ""}]},
        {"reply": "Then it shall be.",
         "actions": [{"tool": "begin_build", "detail": "", "mode": ""}]},
    ])
    state = ArchitectState()                          # NOTHING brought — pure delegation
    # beat 1: the roll becomes a QUESTION, not a build
    r1 = architect_step(prov, state, "", "surprise me", [], resumable="", catalog=None)
    assert r1.outcome == CONTINUE
    assert "how does" in r1.reply.lower() and "sound" in r1.reply
    offered = list(state.surprise_offer)
    assert len(offered) == 2 and all(k in STYLE_CARDS for k in offered)
    assert STYLE_CARDS[offered[0]]["family"] != STYLE_CARDS[offered[1]]["family"]
    # beat 2: the guest's yes builds EXACTLY the offered shape
    r2 = architect_step(prov, state, "", "sounds great, go", [], resumable="",
                        catalog=None)
    assert r2.outcome == BUILD
    assert r2.brief["game_types"] == offered
    assert "surprise commission" in r2.brief["premise"]
    assert "murder case" in r2.brief["premise"]       # the explicit anti-default


def test_surprise_draw_prefers_families_absent_from_the_library(tmp_path, monkeypatch):
    # exclusion: a library already full of Investigation worlds pushes the draw
    # toward EVERY OTHER family — a collection grows breadth.
    import json
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    (tmp_path / "worlds" / "case1.meta.json").write_text(json.dumps(
        {"game_type": ["mystery_whodunnit", "detective_procedural"]}))
    from construct.architect import _surprise_draw
    from construct.play_styles_data import STYLE_CARDS
    for _ in range(12):                                # the PRIMARY never re-treads
        primary = _surprise_draw({"case1": "Case One"})[0]
        assert STYLE_CARDS[primary]["family"] != "Investigation & Epistemics"


def test_described_world_is_never_overridden_by_the_draw():
    # a guest who BROUGHT a world keeps it — the dice only roll on pure delegation.
    from construct.architect import ArchitectState, BUILD, architect_step
    from construct.provider import StubProvider
    prov = StubProvider([{"reply": "Building it now.",
                          "actions": [{"tool": "begin_build", "detail": "", "mode": ""}]}])
    state = ArchitectState(elements=["a drowned harbor town with a lighthouse keeper's secret"])
    result = architect_step(prov, state, "", "go", [], resumable="", catalog=None)
    assert result.outcome == BUILD
    assert result.brief["game_types"] == []            # untouched
    assert "surprise commission" not in result.brief["premise"]
    assert "drowned harbor town" in result.brief["premise"]


def test_architect_prompt_ranges_beyond_murder():
    # the prompt-attractor fixes: sparks span different play shapes; the agent is
    # told plainly this is not a murder-mystery machine.
    from construct.cohorts import architect_turn
    from construct.provider import StubProvider
    prov = StubProvider([{"reply": "…", "actions": []}])
    architect_turn(prov, history="", brief_so_far="", latest="ideas?",
                   catalog=None, worlds=[], resumable="")
    prompt = prov.calls[0][0]
    assert "THIS IS NOT A MURDER-MYSTERY MACHINE" in prompt
    assert "spanning DIFFERENT SHAPES OF PLAY, never two mysteries" in prompt
    assert "lighthouse murder" not in prompt           # the old murder-led example is gone


def test_reroll_surprise_declines_family_and_asks_again():
    # "roll again" → the declined FAMILY is retired for the session, a fresh shape
    # is offered, and the reply asks candidly again.
    from construct.architect import ArchitectState, CONTINUE, architect_step
    from construct.play_styles_data import STYLE_CARDS
    from construct.provider import StubProvider
    prov = StubProvider([
        {"reply": "As you wish.",
         "actions": [{"tool": "begin_build", "detail": "", "mode": ""}]},
        {"reply": "Of course.",
         "actions": [{"tool": "reroll_surprise", "detail": "", "mode": ""}]},
    ])
    state = ArchitectState()
    architect_step(prov, state, "", "surprise me", [], resumable="", catalog=None)
    first = list(state.surprise_offer)
    first_primary_family = STYLE_CARDS[first[0]]["family"]
    r2 = architect_step(prov, state, "", "hmm, roll again", [], resumable="",
                        catalog=None)
    assert r2.outcome == CONTINUE
    assert "sound" in r2.reply
    assert state.surprise_offer and state.surprise_offer != first
    assert first_primary_family in state.surprise_declined
    assert STYLE_CARDS[state.surprise_offer[0]]["family"] != first_primary_family


def test_guest_redirect_dissolves_the_offer():
    # the guest hears the roll and brings their OWN idea instead — the proposal
    # dissolves; their world is what gets built.
    from construct.architect import ArchitectState, architect_step
    from construct.provider import StubProvider
    prov = StubProvider([
        {"reply": "As you wish.",
         "actions": [{"tool": "begin_build", "detail": "", "mode": ""}]},
        {"reply": "Even better.",
         "actions": [{"tool": "add_element",
                      "detail": "a caravan crossing a glass desert", "mode": ""}]},
    ])
    state = ArchitectState()
    architect_step(prov, state, "", "surprise me", [], resumable="", catalog=None)
    assert state.surprise_offer
    architect_step(prov, state, "", "actually — a caravan crossing a glass desert",
                   [], resumable="", catalog=None)
    assert state.surprise_offer == []                  # dissolved
    assert state.elements == ["a caravan crossing a glass desert"]


def test_show_styles_flag_and_prompt_offer():
    # FOUNDER (2026-07-05): creation offers the FULL WALL of the 155 shapes. The
    # agent signals show_styles; the host renders. The opening beat offers it.
    from construct.architect import ArchitectState, CONTINUE, architect_step
    from construct.cohorts import architect_turn
    from construct.provider import StubProvider
    prov = StubProvider([{"reply": "Behold the wall.",
                          "actions": [{"tool": "show_styles", "detail": "", "mode": ""}]}])
    r = architect_step(prov, ArchitectState(), "", "what kinds of stories can you do?",
                       [], resumable="", catalog=None)
    assert r.outcome == CONTINUE and r.show_styles is True
    prompt = prov.calls[0][0]
    assert "show_styles: display the FULL WALL" in prompt
    assert "SEE EVERYTHING" in prompt                   # the opening beat's offer


def test_set_reality_lands_in_state_and_brief():
    # WORLD LAWS (#105): the reality register is an explicit interview
    # dimension (founder) — captured by tool, carried on the brief, ignored
    # when the value is not one of the three registers.
    p = StubProvider([
        _turn("Our own world then — 1920s Chicago as it truly was.",
              _act("set_reality", "real"),
              _act("add_element", "1920s Chicago, as real as rain")),
        _turn("Noted.", _act("set_reality", "dreamlike")),   # invalid → ignored
        _turn("Cooking now.", _act("begin_build")),
    ])
    s = ArchitectState()
    _step(p, s, "the real 1920s Chicago please")
    assert s.reality == "real"
    assert "Reality: the real world as it is" in s.summary()
    _step(p, s, "make it dreamlike too")
    assert s.reality == "real"                               # invalid value ignored
    r = _step(p, s, "go")
    assert r.outcome == BUILD
    assert r.brief["reality"] == "real"


def test_reality_round_trips_serialization():
    s = ArchitectState(reality="alternate")
    assert ArchitectState.from_dict(s.to_dict()).reality == "alternate"
