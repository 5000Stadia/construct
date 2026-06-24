"""End-to-end de-risk for the Atrium BUILD path: run the REAL generate-then-
ingest with a per-player scenario name (as the transport does), then open the
built world fresh and render its cold open. Prints each stage as it fires (the
notify pings come from these). Cleans up the throwaway scenario at the end.

    python scripts/verify_build_enter.py
"""
from __future__ import annotations

from construct.game import create_scenario_from_generated, _unpublish_scenario, slot_path
from construct.provider import CodexProvider
from construct.session import Session
from construct.transport_core import _humanize_stage

NAME = "live_verify_buildenter"
PLAYER = "verify:tester"


def main() -> int:
    provider = CodexProvider()

    def on_stage(msg: str) -> None:
        line = _humanize_stage(msg)
        print(f"[raw] {msg}")
        if line:
            print(f"   → PING: {line}")

    # Clean any prior run.
    try:
        _unpublish_scenario(NAME)
        s = slot_path(NAME, PLAYER)
        if s.exists():
            s.unlink()
    except Exception:
        pass

    print("=== building (this takes ~15 min) ===")
    create_scenario_from_generated(
        NAME, provider,
        seed="a noir mystery aboard a derelict space station; recycled air, neon corridors",
        endless=False, win_direction="catch whoever sabotaged the reactor",
        play_as="the station's onboard AI", on_stage=on_stage)

    print("\n=== entering the built world ===")
    session = Session.open(NAME, player_id=PLAYER, fresh=True, provider=provider,
                           mode_override="win_loss")
    opening = session.opening()
    print(opening[:1200])
    session.close()

    print("\n=== cleaning up throwaway scenario ===")
    _unpublish_scenario(NAME)
    if slot_path(NAME, PLAYER).exists():
        slot_path(NAME, PLAYER).unlink()
    print("OK — build + enter verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
