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
    # The REPL loops run_turn and exits cleanly on :quit — verified
    # without engine or model: stub game/turnloop seams.
    import construct.cli as cli

    inputs = iter(["", "I look around the council tier", ":debug on", ":quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    calls = []

    class _World:
        class porcelain:
            @staticmethod
            def locate(_e):
                return ["place:council_tier"]
        def close(self):
            calls.append("closed")

    class _Arc:
        protagonist = "person:marn"

    class _Result:
        prose = "The tier curves around you."
        class trace:
            @staticmethod
            def to_dict():
                return {"turn": 1}

    monkeypatch.setattr(cli, "_provider", lambda: object())
    monkeypatch.setattr("construct.game.start_playthrough", lambda *a, **k: None)
    monkeypatch.setattr("construct.game.open_playthrough",
                        lambda *a, **k: (_World(), _Arc(), {"title": "Anchor"}))
    monkeypatch.setattr("construct.game.next_turn_number", lambda _w: 1)

    def fake_turn(world, arc, provider, line, turn, scope=None, mode="pure"):
        calls.append(("turn", line))
        return _Result()
    monkeypatch.setattr("construct.turnloop.run_turn", fake_turn)

    rc = cli.main(["play", "anchor"])
    assert rc == 0
    # exactly one real turn ran (empty line skipped, :debug/:quit are meta)
    assert calls.count(("turn", "I look around the council tier")) == 1
    assert "closed" in calls          # world closed on exit
    out = capsys.readouterr()
    assert "The tier curves around you." in out.out


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


def test_new_interview_not_yet(capsys):
    rc = main(["new", "--interview"])
    assert rc == 2
    assert "post-first-playable" in capsys.readouterr().err
