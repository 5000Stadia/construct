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
