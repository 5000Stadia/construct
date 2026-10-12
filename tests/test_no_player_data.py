"""Player privacy guard (Kabe, 2026-10-12): real players' ids and their actual play
stay out of tracked files. A live world's name carries its player's transport id
(`live_telegram_<id>`), so a tracked file naming one is a leak. Tests use short fake
ids (`live_telegram_42`); a real Telegram or Discord id is far longer."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REAL_SLOT = re.compile(rb"(?:telegram|discord)_\d{6,}")


def _tracked() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [ROOT / p for p in out.decode().split("\0") if p]


def test_no_tracked_file_names_a_real_player_slot():
    leaks = []
    for path in _tracked():
        if not path.is_file() or path.suffix == ".world":
            continue
        match = REAL_SLOT.search(path.read_bytes())
        if match:
            leaks.append(f"{path.relative_to(ROOT)}: {match.group().decode()}")
    assert not leaks, "real player slots in tracked files:\n" + "\n".join(leaks)


def test_no_live_world_file_is_tracked():
    live = [str(p.relative_to(ROOT)) for p in _tracked()
            if p.parent.name == "worlds" and p.name.startswith("live_")]
    assert not live, f"live player worlds are tracked: {live}"
