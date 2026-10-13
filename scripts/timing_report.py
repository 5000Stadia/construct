"""Turn a CONSTRUCT_TIMING_LOG file into the tables for optimizing build and turn time.

    .venv/bin/python scripts/timing_report.py LOG.jsonl > report.md

Sections:
1. Build stages: wall time, model calls, the calls' summed time, and that sum over wall
   ("x parallel": above 1 means calls overlapped).
2. Steps: every kind of model call (host task code or engine prompt head), with count,
   total, mean, p50, p90 and max seconds, tier and model, re-asks, transient retries and
   errors. The biggest totals are where model choice or batching pays.
3. Turns: wall time per turn, its slowest steps, and the deferred settle after it.
4. Concurrency: the most calls in flight at once, per phase.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]


def _max_overlap(calls: list[dict]) -> int:
    edges = sorted([(c["t0"], 1) for c in calls] + [(c["t1"], -1) for c in calls])
    cur = best = 0
    for _, d in edges:
        cur += d
        best = max(best, cur)
    return best


def load(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def report(rows: list[dict]) -> str:
    out: list[str] = []
    calls = [r for r in rows if r.get("ev") == "call"]
    stages = [r for r in rows if r.get("ev") == "stage"]
    turn_starts = {r["turn"]: r for r in rows if r.get("ev") == "turn_start"}
    turn_ends = {r["turn"]: r for r in rows if r.get("ev") == "turn_end"}
    settles = [r for r in rows if r.get("ev") == "settle"]
    by_phase: dict[str, list[dict]] = defaultdict(list)
    for c in calls:
        by_phase[c.get("phase", "")].append(c)

    models = sorted({(c.get("tier"), c.get("model")) for c in calls})
    out.append("# Timing report\n")
    out.append(f"{len(calls)} model calls, {sum(c['s'] for c in calls):.0f} s of call time. "
               "Models: " + ", ".join(f"{t}={m}" for t, m in models) + "\n")

    # 1. build stages
    if stages:
        build_end = min((r["t"] for r in turn_starts.values()), default=None)
        if build_end is None:
            build_end = max([c["t1"] for c in calls] + [stages[-1]["t"]])
        out.append("## 1. Build stages\n")
        out.append("| Stage | Wall s | Calls | Call s | x parallel |")
        out.append("|---|---:|---:|---:|---:|")
        total = 0.0
        for i, st in enumerate(stages):
            end = stages[i + 1]["t"] if i + 1 < len(stages) else build_end
            wall = max(0.0, end - st["t"])
            total += wall
            inside = [c for c in calls if st["t"] <= c["t0"] < end]
            cs = sum(c["s"] for c in inside)
            par = f"{cs / wall:.1f}" if wall > 0 and inside else "-"
            out.append(f"| {st['label'][:70]} | {wall:.0f} | {len(inside)} | {cs:.0f} | {par} |")
        out.append(f"| **build total** | **{total:.0f}** | | | |\n")

    # 2. steps
    out.append("## 2. Steps (every kind of model call)\n")
    out.append("| Step | Tier / model | n | Total s | Mean | p50 | p90 | Max | Re-asks | Retries | Errors | Prompt chars (mean) |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    steps: dict[tuple, list[dict]] = defaultdict(list)
    for c in calls:
        steps[(c.get("step", "?"), c.get("tier"), c.get("model"))].append(c)
    for (step, tier, model), cs in sorted(steps.items(), key=lambda kv: -sum(c["s"] for c in kv[1])):
        xs = [c["s"] for c in cs]
        out.append(
            f"| {step} | {tier} / {model} | {len(cs)} | {sum(xs):.0f} | {sum(xs) / len(xs):.1f} "
            f"| {_pct(xs, .5):.1f} | {_pct(xs, .9):.1f} | {max(xs):.1f} "
            f"| {sum(c.get('reasks', 0) for c in cs)} | {sum(c.get('retries', 0) for c in cs)} "
            f"| {sum(1 for c in cs if not c.get('ok', True))} "
            f"| {sum(c.get('prompt_chars', 0) for c in cs) // len(cs)} |")
    out.append("")

    # 3. turns
    if turn_starts:
        out.append("## 3. Turns\n")
        out.append("| Turn | Wall s | Calls | Call s | x parallel | Slowest steps (s) | Settle after (s) |")
        out.append("|---:|---:|---:|---:|---:|---|---:|")
        for n in sorted(turn_starts):
            st, en = turn_starts[n], turn_ends.get(n)
            if en is None:
                continue
            wall = en["t"] - st["t"]
            inside = [c for c in calls if st["t"] <= c["t0"] < en["t"]]
            cs = sum(c["s"] for c in inside)
            agg: dict[str, float] = defaultdict(float)
            for c in inside:
                agg[c.get("step", "?")] += c["s"]
            top = ", ".join(f"{k} {v:.0f}" for k, v in sorted(agg.items(), key=lambda kv: -kv[1])[:4])
            nxt = turn_starts.get(n + 1, {}).get("t", float("inf"))
            sett = sum(r["s"] for r in settles if en["t"] <= r["t0"] < nxt)
            par = f"{cs / wall:.1f}" if wall > 0 and inside else "-"
            flag = "" if en.get("ok", True) else " (failed)"
            out.append(f"| {n}{flag} | {wall:.0f} | {len(inside)} | {cs:.0f} | {par} | {top} | {sett:.0f} |")
        out.append("")

    # 4. concurrency
    out.append("## 4. Concurrency (most calls in flight at once)\n")
    out.append("| Phase | Calls | Max in flight |")
    out.append("|---|---:|---:|")
    for ph, cs in sorted(by_phase.items(), key=lambda kv: kv[1][0]["t0"]):
        out.append(f"| {ph or '-'} | {len(cs)} | {_max_overlap(cs)} |")
    out.append("")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    sys.stdout.write(report(load(argv[1])) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
