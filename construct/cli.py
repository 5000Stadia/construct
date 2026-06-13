"""The player CLI (docs/design/CLI.md, Kernos letters 017/019).

One-shot per turn: stateless per call, stateful via the playthrough
slot. Wired to the frozen porcelain (porcelain-v0.1).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="construct",
        description="A text construct: persistent interactive fiction, played turn by turn.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scenarios", help="list the scenario library (charter self-ID)")

    new = sub.add_parser("new", help="session zero: create a pristine scenario")
    source = new.add_mutually_exclusive_group(required=True)
    source.add_argument("--ingest", metavar="PATH", help="ingest a work of fiction")
    source.add_argument("--interview", action="store_true",
                        help="live interview (post-first-playable)")
    new.add_argument("--name", help="scenario name (default: prose filename stem)")

    play = sub.add_parser("play", help="establish or resume the playthrough slot")
    play.add_argument("scenario")
    mode = play.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fresh", action="store_true",
                      help="start from the beginning (recopy pristine scenario over the slot)")
    mode.add_argument("--resume", action="store_true",
                      help="open the playthrough slot at its head")

    turn = sub.add_parser("turn", help="process exactly one player turn")
    turn.add_argument("playthrough", help="scenario name (its single slot is the save)")
    turn.add_argument("player_input", metavar="INPUT")
    turn.add_argument("--debug", action="store_true",
                      help="emit the turn trace: briefing frame list, cohort "
                           "trace, concealment audit, beats/clocks/nudges")

    return parser


def _provider():
    from construct.provider import CodexProvider
    return CodexProvider()


def _cmd_scenarios() -> int:
    from construct.game import list_scenarios
    rows = list_scenarios()
    if not rows:
        print("No scenarios yet. Create one: construct new --ingest <prose.md>")
        return 0
    for row in rows:
        print(f"{row['name']:24s} {row.get('stance', '?'):8s} "
              f"{row.get('title', '(untitled)')} — {row.get('theme', '')}")
    return 0


def _cmd_new(args: argparse.Namespace) -> int:
    from construct.game import create_scenario_from_ingest
    if args.interview:
        print("construct new --interview: post-first-playable (letter 017)", file=sys.stderr)
        return 2
    prose = Path(args.ingest)
    name = args.name or prose.stem.replace(" ", "_")
    meta = create_scenario_from_ingest(name, prose, _provider())
    print(f"Scenario {name!r} created: {meta['title']}")
    print(f"  protagonist: {meta['protagonist']}")
    print(f"  theme: {meta['theme']}")
    print(f"Start playing: construct play {name} --fresh")
    return 0


def _cmd_play(args: argparse.Namespace) -> int:
    from construct.game import open_playthrough, start_playthrough
    start_playthrough(args.scenario, fresh=args.fresh)
    world, arc, _meta = open_playthrough(args.scenario, _provider())
    try:
        snap = world.porcelain.snapshot(arc.protagonist, frame=f"knows:{arc.protagonist}",
                                        lens="establishing_set")
        opening = [f"You are {arc.protagonist}."]
        chain = world.porcelain.locate(arc.protagonist)
        if chain:
            opening.append(f"You are at {chain[0]}.")
        opening.append('The world holds. Take your first turn: '
                       f'construct turn {args.scenario} "<what you do>"')
        print("\n".join(opening))
    finally:
        world.close()
    return 0


def _cmd_turn(args: argparse.Namespace) -> int:
    from construct.game import next_turn_number, open_playthrough
    from construct.turnloop import run_turn

    world, arc, meta = open_playthrough(args.playthrough, _provider())
    try:
        turn = next_turn_number(world)
        result = run_turn(world, arc, _provider(), args.player_input, turn,
                          scope=meta.get("arc_scope") or None,
                          mode=meta.get("mode", "pure"))
        print(result.prose)
        if args.debug:
            print("\n--- TURN TRACE ---", file=sys.stderr)
            print(json.dumps(result.trace.to_dict(), indent=2), file=sys.stderr)
    finally:
        world.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scenarios":
        return _cmd_scenarios()
    if args.command == "new":
        return _cmd_new(args)
    if args.command == "play":
        return _cmd_play(args)
    if args.command == "turn":
        return _cmd_turn(args)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
