import pytest

from holodeck.cli import build_parser, main


def test_scenarios_parses():
    args = build_parser().parse_args(["scenarios"])
    assert args.command == "scenarios"


def test_new_requires_source():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["new"])
    args = build_parser().parse_args(["new", "--ingest", "examples/the_last_honest_meter.md"])
    assert args.ingest.endswith("the_last_honest_meter.md")


def test_play_requires_mode():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["play", "anchor"])
    args = build_parser().parse_args(["play", "anchor", "--fresh"])
    assert args.fresh and not args.resume
    with pytest.raises(SystemExit):
        build_parser().parse_args(["play", "anchor", "--fresh", "--resume"])


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
