import pytest

from construct.cli import build_parser, main


def test_scenarios_parses():
    args = build_parser().parse_args(["scenarios"])
    assert args.command == "scenarios"


def test_new_requires_source():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["new"])
    args = build_parser().parse_args(["new", "--ingest", "examples/the_last_honest_meter.md"])
    assert args.ingest.endswith("the_last_honest_meter.md")


def test_play_bare_resumes_then_loops():
    # Bare `play <scenario>` is valid now (resume + REPL); the mode flags
    # remain optional and mutually exclusive (letter 032).
    args = build_parser().parse_args(["play", "anchor"])
    assert args.scenario == "anchor" and not args.fresh and not args.resume
    fresh = build_parser().parse_args(["play", "anchor", "--fresh"])
    assert fresh.fresh and not fresh.resume
    with pytest.raises(SystemExit):
        build_parser().parse_args(["play", "anchor", "--fresh", "--resume"])


def test_play_repl_loop(monkeypatch, capsys):
    # The REPL is a thin client of Session — verified without engine or
    # model by stubbing Session.open (letter 034).
    import construct
    import construct.cli as cli

    inputs = iter(["", "I look around the council tier", ":debug on", ":quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    calls = []

    class _Reply:
        def __init__(self):
            self.prose = "The tier curves around you."
            self.ok = True
            self.trace = type("T", (), {"to_dict": staticmethod(lambda: {"turn": 1})})()

    class _FakeSession:
        def opening(self):
            return "Anchor\nYou are person:marn, at place:council_tier."
        def turn(self, line):
            calls.append(("turn", line))
            return _Reply()
        def close(self):
            calls.append("closed")

    monkeypatch.setattr(cli, "_provider", lambda: object())
    monkeypatch.setattr(construct.Session, "open",
                        classmethod(lambda cls, *a, **k: _FakeSession()))

    rc = cli.main(["play", "anchor"])
    assert rc == 0
    # exactly one real turn ran (empty line skipped, :debug/:quit are meta)
    assert calls.count(("turn", "I look around the council tier")) == 1
    assert "closed" in calls          # session closed on exit
    assert "The tier curves around you." in capsys.readouterr().out


def test_turn_shape():
    args = build_parser().parse_args(
        ["turn", "anchor.play", "I open the drawer.", "--debug"])
    assert args.playthrough == "anchor.play"
    assert args.player_input == "I open the drawer."
    assert args.debug is True


def test_scenarios_empty_library(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["scenarios"])
    assert rc == 0
    assert "No scenarios yet" in capsys.readouterr().out


def test_new_interview_parses_inline_brief():
    args = build_parser().parse_args(["new", "--interview", "a drowned harbor town"])
    assert args.interview == "a drowned harbor town"


def test_new_interview_empty_brief_is_loud(capsys, monkeypatch):
    # --interview with no inline brief and no input → loud no-op (rc 2).
    monkeypatch.setattr("builtins.input", lambda _p="": "")
    rc = main(["new", "--interview"])
    assert rc == 2
    assert "nothing to build" in capsys.readouterr().err


def test_new_generate_parses_seed_and_is_mutually_exclusive():
    args = build_parser().parse_args(["new", "--generate", "a noir harbor"])
    assert args.generate == "a noir harbor"
    # bare --generate is the 'surprise me' const
    assert build_parser().parse_args(["new", "--generate"]).generate == ""
    # generate/ingest/interview are mutually exclusive sources
    with pytest.raises(SystemExit):
        build_parser().parse_args(["new", "--generate", "x", "--ingest", "y.md"])


def test_start_menu_routes_to_generate(monkeypatch, capsys):
    # The guided menu is a surface over the flags: choosing "generate" must
    # delegate to the same build path with the chosen mode + seed.
    from construct import cli
    # generate, freeplay, name, play-as (blank), seed
    answers = iter(["2", "f", "myworld", "", "a noir harbor"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(answers))
    captured = {}

    def _fake_new(ns):
        captured["ns"] = ns
        return 0

    monkeypatch.setattr(cli, "_cmd_new", _fake_new)
    rc = main(["start"])
    assert rc == 0
    ns = captured["ns"]
    assert ns.generate == "a noir harbor" and ns.name == "myworld"
    assert ns.endless is True  # freeplay → endless/no-terminal
    assert ns.ingest is None and ns.interview is None
    assert ns.play_as == ""  # blank play-as is fine


def test_shell_is_the_default_command():
    assert build_parser().parse_args(["shell"]).command == "shell"
    assert build_parser().parse_args([]).command is None  # bare `construct` → shell


def test_entry_agent_sees_options_and_routes():
    from construct.cohorts import entry_agent
    from construct.provider import StubProvider
    prov = StubProvider([{"action": "load", "target": "anchor", "seed": "",
                          "path": "", "reply": "Loading anchor."}])
    out = entry_agent(prov, "play the honest meter one", ["anchor"], ["anchor"])
    assert out["action"] == "load" and out["target"] == "anchor"
    prompt = prov.calls[0][0]
    assert "INGESTED SETTINGS" in prompt and "anchor" in prompt
    assert prov.calls[0][2] == "cheap"  # router, not the narrator


def test_shell_open_load_known_and_unknown(monkeypatch, capsys):
    import construct
    from construct.cli import _shell_open
    opened = {}
    monkeypatch.setattr(construct.Session, "open",
                        classmethod(lambda cls, name, provider=None: opened.setdefault("n", name)))
    assert _shell_open(None, {"action": "load", "target": "anchor"}, ["anchor"]) is not None
    assert opened["n"] == "anchor"
    # an unknown setting is refused, not invented
    assert _shell_open(None, {"action": "load", "target": "ghost"}, ["anchor"]) is None
    assert "don't have a setting" in capsys.readouterr().err


def test_shell_open_create_routes_to_generate(monkeypatch, tmp_path):
    import construct
    import construct.game as game
    from construct.cli import _shell_open
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    seen = {}
    monkeypatch.setattr(game, "create_scenario_from_generated",
                        lambda name, prov, seed="", on_stage=None: seen.update(name=name, seed=seed))
    monkeypatch.setattr(construct.Session, "open",
                        classmethod(lambda cls, name, provider=None: "SESSION"))
    out = _shell_open(None, {"action": "create", "seed": "a noir harbor"}, [])
    assert out == "SESSION" and seen["seed"] == "a noir harbor"


def test_start_menu_play_with_empty_library_is_loud(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "worlds").mkdir()
    monkeypatch.setattr("builtins.input", lambda _p="": "1")  # play, but nothing exists
    rc = main(["start"])
    assert rc == 2
    assert "No worlds yet" in capsys.readouterr().err
