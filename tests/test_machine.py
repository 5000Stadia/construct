import pytest

from holodeck.session_zero import Path, SessionZeroMachine, Stage, StageError


def run_through(machine: SessionZeroMachine, upto: Stage) -> None:
    payloads = {Stage.PATH: {"path": "B"}}
    while machine.current_stage is not None and machine.current_stage != upto:
        stage = machine.current_stage
        machine.complete(stage, payloads.get(stage))


def test_full_run_in_order():
    m = SessionZeroMachine()
    assert m.current_stage is Stage.GREET
    run_through(m, Stage.START)
    m.complete(Stage.START)
    assert m.is_complete
    assert m.path is Path.LIVE


def test_out_of_order_rejected():
    m = SessionZeroMachine()
    with pytest.raises(StageError):
        m.complete(Stage.ENTRY)


def test_path_requires_payload():
    m = SessionZeroMachine()
    m.complete(Stage.GREET)
    m.complete(Stage.PROVIDER)
    with pytest.raises(StageError):
        m.complete(Stage.PATH, {})


def test_prefilled_sections_switch():
    m = SessionZeroMachine()
    m.complete(Stage.GREET)
    m.complete(Stage.PROVIDER)
    m.complete(Stage.PATH, {"path": "A"})
    assert "charter" in m.prefilled_sections
    live = SessionZeroMachine()
    live.complete(Stage.GREET)
    live.complete(Stage.PROVIDER)
    live.complete(Stage.PATH, {"path": "B"})
    assert live.prefilled_sections == frozenset()


def test_prefilled_before_path_is_error():
    m = SessionZeroMachine()
    with pytest.raises(StageError):
        _ = m.prefilled_sections


def test_resume_from_checkpoints():
    m = SessionZeroMachine()
    m.complete(Stage.GREET)
    m.complete(Stage.PROVIDER)
    m.complete(Stage.PATH, {"path": "A"})
    persisted = m.checkpoints()

    resumed = SessionZeroMachine(persisted)
    assert resumed.current_stage is Stage.WORLD
    assert resumed.path is Path.INGEST
    assert resumed.checkpoints() == persisted  # nothing lost


def test_launch_resume_short_circuits():
    m = SessionZeroMachine()
    m.complete(Stage.GREET, {"launch": "resume", "scenario": "anchor"})
    assert m.is_complete
    assert m.checkpoints()[-1]["payload"]["scenario"] == "anchor"


def test_launch_fresh_short_circuits():
    m = SessionZeroMachine()
    m.complete(Stage.GREET, {"launch": "fresh", "scenario": "anchor"})
    assert m.is_complete


def test_launch_requires_valid_payload():
    with pytest.raises(StageError):
        SessionZeroMachine().complete(Stage.GREET, {"launch": "replay", "scenario": "x"})
    with pytest.raises(StageError):
        SessionZeroMachine().complete(Stage.GREET, {"launch": "resume"})


def test_complete_after_done_is_error():
    m = SessionZeroMachine()
    m.complete(Stage.GREET, {"launch": "resume", "scenario": "anchor"})
    with pytest.raises(StageError):
        m.complete(Stage.PROVIDER)
