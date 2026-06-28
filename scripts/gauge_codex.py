"""One-shot Codex health gauge: build a single small interview world, timed. Reports whether
Codex recovered (build completes in a normal window) and whether the interview-path protagonist
guard fails (systematic interview-spine issue vs. degraded thin spine)."""
import logging, time, traceback
from pathlib import Path
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
from construct.game import create_scenario_from_interview, scenario_path
from construct.provider import CodexProvider
for suf in (".world", ".meta.json"):
    scenario_path("gauge_bond").with_suffix(suf).unlink(missing_ok=True)
brief = "A slow-burn romance between two people thrown together by a long winter in a remote lighthouse station."
t0 = time.time()
try:
    meta = create_scenario_from_interview("gauge_bond", brief, CodexProvider(), game_types=["romance"])
    print(f"GAUGE OK in {time.time()-t0:.0f}s — title={meta.get('title')!r} cast={bool(meta.get('cast'))} gt={meta.get('game_type')}")
except Exception as exc:
    print(f"GAUGE FAILED in {time.time()-t0:.0f}s — {exc}")
