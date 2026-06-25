"""Profiled generate-path run — WHAT IS SLOW, AND WHY.

Generates a hidden world from a (weird) genre seed and profiles every model call.
Because EVERY model call in Construct routes through `provider.complete(prompt,
schema, tier=...)` — engine extraction, durability classification, AND host
cohorts — wrapping that one method captures the whole cost picture:

  - per-PHASE wall time (Stage 0 construct the story … Stage 7 viability), via
    the build's stage callbacks;
  - the ingestion broken into its real phases: prose EXTRACTION (a model call per
    chunk) vs DURABILITY CLASSIFICATION (a model call per novel attribute) vs the
    local gate/fold (wall time not attributable to any model call);
  - a per-CATEGORY model profile (count, total, mean, max, tier) so the dominant
    cost is obvious;
  - TIER ANALYSIS: high-count main-tier categories are flagged as candidates to
    move to the cheap model (the founder's "lots of minor things" optimization).

Usage: SEED="..." NAME="..." [PLAY=1] .venv/bin/python scripts/timed_generate.py
"""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Host cohorts carry a stable task tag (provider.task_of); engine prompts are
# untagged and matched by prefix. Map both to readable profile categories.
from construct.provider import task_of  # noqa: E402

_TASK_CAT = {
    "sty": "story_authoring", "itr": "intro", "flv": "flavor", "arc": "arc_authoring",
    "skn": "knows_seeding", "itv": "interview", "gen": "generate_arc",
    "cls": "player_classify", "ndg": "nudge", "nar": "narrate", "npa": "npc",
    "npi": "npc", "ent": "host_chat",
    # build-path authoring + host cohorts that were bucketing as "other" — so the cast
    # RE-AUTHOR cost (the 3-attempt solvability/signature retry loop) is no longer hidden:
    "cast": "cast_authoring", "cst": "cast_authoring", "prm": "premise", "gty": "game_type",
    "gnr": "genre", "opn": "open_scene", "foy": "foyer", "ocr": "coref", "adapt": "make_it_real",
    "jdg": "judge_commitment", "wve": "weave", "npt": "npc", "elp": "time_estimate",
    "mem": "compact_memory", "fin": "finalize", "cnd": "conclude",
}
_ENGINE_PREFIX = [
    ("Extract world-state", "extraction"),
    ("Classify the lifetime", "durability_classify"),
    ("Resolve an unestablished aspect", "resolve_invent"),
]


def categorize(prompt: str) -> str:
    code = task_of(prompt)
    if code:
        return _TASK_CAT.get(code, code)
    for prefix, cat in _ENGINE_PREFIX:
        if prompt.startswith(prefix):
            return cat
    return "other"


def main() -> None:
    from construct import game
    from construct.provider import CodexProvider

    seed = os.environ.get("SEED", "a time-travel romance across two centuries")
    win = os.environ.get("WIN", "")  # the player's own win/loss framing (optional)
    play_as = os.environ.get("PLAY_AS", "")  # who the player wants to be (optional)
    name = os.environ.get("NAME", "timed")
    ts = os.environ.get("LIVEPLAY_TS", "manual")
    play = os.environ.get("PLAY") == "1"

    logs = Path("logs"); logs.mkdir(exist_ok=True)
    log = (logs / f"timed-generate-{name}-{ts}.md").open("w")

    def w(line=""):
        log.write(line + "\n"); log.flush()

    # clean any prior scenario of this name
    game.scenario_path(name).with_suffix(".meta.json").unlink(missing_ok=True)
    try:
        game.scenario_path(name).unlink()
    except FileNotFoundError:
        pass

    t0 = time.monotonic()
    marks: list[tuple[float, str]] = []
    calls: list[dict] = []  # {cat, tier, dur, at}

    def on_stage(msg: str) -> None:
        marks.append((time.monotonic() - t0, msg))

    provider = CodexProvider()
    # ---- the probe: wrap provider.complete to time + tag every model call ----
    _orig = provider.complete

    async def timed_complete(prompt, schema, *, tier="main", deliberate=False):
        start = time.monotonic()
        try:
            return await _orig(prompt, schema, tier=tier, deliberate=deliberate)
        finally:
            calls.append({"cat": categorize(prompt), "tier": tier,
                          "dur": time.monotonic() - start, "at": start - t0})
    provider.complete = timed_complete

    w(f"# Profiled generate run — seed: *{seed}*")
    w()
    w("Profiling every model call to find what's slow and why. The two phases you "
      "asked about — **construct the story** (Stage 0) and **ingest into the data "
      "structure** (Stage 1) — are called out in the headline; ingestion's internal "
      "phases (extraction vs durability-classification vs local gate) are in the "
      "category profile.")
    w()

    err, meta = None, None
    build_start = time.monotonic()
    try:
        meta = game.create_scenario_from_generated(name, provider, seed=seed,
                                                   on_stage=on_stage, win_direction=win,
                                                   play_as=play_as)
    except Exception as exc:  # noqa: BLE001 — ViabilityError or any build failure
        err = exc
    build_total = time.monotonic() - build_start

    # ---- stage wall-time table -----------------------------------------
    w("## Build phases (wall time)")
    w()
    w("| at (s) | Δ (s) | stage |")
    w("|-------:|------:|-------|")
    prev = 0.0
    for at, msg in marks:
        w(f"| {at:7.1f} | {at - prev:6.1f} | {msg.strip()[:78]} |")
        prev = at
    w(f"| {build_total:7.1f} | {build_total - prev:6.1f} | (build complete) |")
    w()

    def stage_start(prefix: str):
        for at, msg in marks:
            if msg.strip().startswith(prefix):
                return at
        return None

    s0, s1, s2 = stage_start("Stage 0"), stage_start("Stage 1"), stage_start("Stage 2")
    w("## Headline")
    w()
    if s0 is not None and s1 is not None:
        w(f"- **Construct the story (Stage 0, LLM authoring):** {s1 - s0:.1f}s")
    if s1 is not None and s2 is not None:
        w(f"- **Ingest into the data structure (Stage 1, prose → pattern-buffer):** "
          f"{s2 - s1:.1f}s")
    w(f"- **Total build:** {build_total:.1f}s")

    # ---- model-call category profile -----------------------------------
    by_cat: dict[str, list[float]] = defaultdict(list)
    by_cat_tier: dict[str, set] = defaultdict(set)
    for c in calls:
        by_cat[c["cat"]].append(c["dur"])
        by_cat_tier[c["cat"]].add(c["tier"])
    model_total = sum(c["dur"] for c in calls)
    w(f"- **Total time in model calls:** {model_total:.1f}s "
      f"({len(calls)} calls) — local/gate/overhead ≈ {build_total - model_total:.1f}s")
    w()

    w("## Model-call profile (the cost picture)")
    w()
    w("| category | tier | calls | total s | mean s | max s |")
    w("|----------|------|------:|--------:|-------:|------:|")
    for cat in sorted(by_cat, key=lambda k: -sum(by_cat[k])):
        ds = by_cat[cat]
        tiers = ",".join(sorted(by_cat_tier[cat]))
        w(f"| {cat} | {tiers} | {len(ds)} | {sum(ds):6.1f} | {sum(ds)/len(ds):5.1f} "
          f"| {max(ds):5.1f} |")
    w()

    # ---- tier-optimization candidates ----------------------------------
    w("## Tier analysis — cheap-model candidates")
    w()
    w("High-count **main**-tier categories are where 'lots of minor things' add up; "
      "if the cheap model returns the same result for them, the saving is "
      "count × (main mean − cheap mean). Mechanical/low-judgement categories are the "
      "safest to try on cheap.")
    w()
    main_cats = [(cat, by_cat[cat]) for cat in by_cat if "main" in by_cat_tier[cat]]
    main_cats.sort(key=lambda kv: -len(kv[1]))
    if main_cats:
        w("| main-tier category | calls | total s | mean s | note |")
        w("|--------------------|------:|--------:|-------:|------|")
        _NOTE = {
            "resolve_invent": "scene invention — judgement-light; try cheap",
            "npc": "NPC intent/action — try cheap, compare voice",
            "nudge": "already cheap by default",
            "narrate": "player-facing prose — keep main (quality-bearing)",
            "arc_authoring": "structural, low-frequency — keep main",
            "story_authoring": "the whole fiction — keep main",
            "generate_arc": "creative + grounded — keep main",
            "flavor": "voice distillation — keep main",
            "intro": "player-facing — keep main",
        }
        for cat, ds in main_cats:
            w(f"| {cat} | {len(ds)} | {sum(ds):6.1f} | {sum(ds)/len(ds):5.1f} "
              f"| {_NOTE.get(cat, 'review')} |")
    w()

    if err is not None:
        w(f"## Build did not publish\n\n`{type(err).__name__}: {err}`")
        log.close(); print(str(Path(log.name))); return

    w("## What it made")
    w("```")
    w(f"title: {meta.get('title')}")
    w(f"protagonist: {meta.get('protagonist')}")
    w(f"goal: {meta.get('goal_statement')}")
    w(f"style: {meta.get('style')}")
    w(f"\nintro:\n{meta.get('intro')}")
    w("```")
    w()

    if play:
        from construct import Session
        s = Session.open(name, player_id="founder", fresh=True, provider=provider)
        w("## A few live turns")
        w("```")
        w(s.opening())
        w("```")
        w()
        for n, text in enumerate([
            "I take stock of where I am and what stands in front of me.",
            "I follow whatever thread feels most alive here.",
        ], start=1):
            w(f"### Turn {n}")
            w(f"**You:** {text}")
            reply = s.turn(text)
            w(f"\n**Narrator:** {reply.prose}\n")
        s.close()

    log.close()
    print(str(Path(log.name)))


if __name__ == "__main__":
    main()
