"""The player CLI (docs/design/CLI.md, Kernos letters 017/019/032).

Two surfaces over ONE turn function (`construct.turnloop.run_turn`):

- `construct play <scenario>` — the interactive REPL: load/resume once,
  then read → turn → print, line after line, until you exit. This is
  the standalone play interface (letter 032).
- `construct turn <scenario> "<input>"` — the one-shot command, intact
  for scripting, tests, and the live-tester. The REPL is a loop around
  this same machinery, never a reimplementation.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
import threading
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

EXIT_WORDS = {":quit", ":exit", ":q"}
HELP_TEXT = (
    "Just type what you do, in plain language, and press Enter.\n"
    "  :debug on|off   show/hide the per-turn trace\n"
    "  :help           this message\n"
    "  :quit / :exit   leave (your progress is saved every turn)\n"
    "  Ctrl-D          same as :quit"
)


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

    play = sub.add_parser(
        "play", help="play interactively: load/resume the scenario, then a prompt loop")
    play.add_argument("scenario")
    # Not required: bare `play <scenario>` RESUMES the slot, then loops.
    mode = play.add_mutually_exclusive_group()
    mode.add_argument("--fresh", action="store_true",
                      help="start from the beginning (recopy pristine scenario over the slot)")
    mode.add_argument("--resume", action="store_true",
                      help="resume the playthrough slot (the default)")
    play.add_argument("--debug", action="store_true",
                      help="start with the per-turn trace on (toggle in-session with :debug)")

    knows = sub.add_parser(
        "knows", help="inspect a character's knowledge frame; --contrast shows two diverge")
    knows.add_argument("scenario")
    knows.add_argument("character", help="entity id or bare name (e.g. marn or person:marn)")
    knows.add_argument("--contrast", metavar="OTHER",
                       help="another character: show what each knows that the other doesn't")

    turn = sub.add_parser("turn", help="process exactly one player turn (one-shot; scripting/tests)")
    turn.add_argument("playthrough", help="scenario name (its single slot is the save)")
    turn.add_argument("player_input", metavar="INPUT")
    turn.add_argument("--debug", action="store_true",
                      help="emit the turn trace: briefing frame list, cohort "
                           "trace, concealment audit, beats/clocks/nudges")

    return parser


def _provider():
    from construct.provider import CodexProvider
    return CodexProvider()


class _Spinner:
    """A quiet, honest 'the world turns…' indicator on stderr while a
    ~50s good-tier turn runs. No-op when stderr isn't a TTY (scripts,
    pipes) so captured output stays clean."""

    def __init__(self, label: str = "the world turns") -> None:
        self._label = label
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = sys.stderr.isatty()

    def __enter__(self) -> "_Spinner":
        if self._active:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def _spin(self) -> None:
        start = time.monotonic()
        for frame in itertools.cycle("|/-\\"):
            if self._stop.is_set():
                break
            elapsed = int(time.monotonic() - start)
            sys.stderr.write(f"\r  ({self._label}… {frame} {elapsed}s)")
            sys.stderr.flush()
            self._stop.wait(0.5)

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        if self._active:
            sys.stderr.write("\r" + " " * 40 + "\r")
            sys.stderr.flush()


def _print_trace(trace) -> None:
    print("\n--- TURN TRACE ---", file=sys.stderr)
    print(json.dumps(trace.to_dict(), indent=2), file=sys.stderr)


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
    print(f"Play it: construct play {name}")
    return 0


def _cmd_play(args: argparse.Namespace) -> int:
    """The interactive REPL (letter 032): a thin client of the session
    API (letter 034) — open once, loop turn→print, saved every turn."""
    from construct import Session

    session = Session.open(args.scenario, fresh=args.fresh, provider=_provider())
    debug = args.debug
    print(f"  {session.opening()}\n")
    print("Type what you do. (:help for commands, :quit to leave.)")
    try:
        while True:
            try:
                raw = input("\n> ")
            except (EOFError, KeyboardInterrupt):
                print("\nThe world holds. (saved)")
                break

            line = raw.strip()
            if not line:
                continue
            if line in EXIT_WORDS:
                print("The world holds. (saved)")
                break
            if line in (":help", ":h", ":?"):
                print(HELP_TEXT)
                continue
            if line.startswith(":debug"):
                arg = line.split(maxsplit=1)
                debug = (len(arg) == 2 and arg[1].lower() in ("on", "true", "1"))
                print(f"(debug {'on' if debug else 'off'})")
                continue
            if line.startswith(":"):
                print(f"(unknown command {line!r}; :help for the list)")
                continue

            with _Spinner():
                reply = session.turn(line)
            if not reply.ok:
                print(reply.prose, file=sys.stderr)
                continue
            print(reply.prose)
            if debug and reply.trace is not None:
                _print_trace(reply.trace)
    finally:
        session.close()
    return 0


def _fmt_facts(facts: dict) -> str:
    if not facts:
        return "    (nothing)"
    return "\n".join(f"    {e} · {a} · {v}" for (e, a), v in sorted(facts.items()))


def _cmd_knows(args: argparse.Namespace) -> int:
    from construct.game import knows_inspect
    r = knows_inspect(args.scenario, args.character, contrast=args.contrast)
    if args.contrast:
        print(f"Only {r['character']} knows (hidden from {r['contrast']}):")
        print(_fmt_facts(r["only_character"]))
        print(f"\nOnly {r['contrast']} knows (hidden from {r['character']}):")
        print(_fmt_facts(r["only_contrast"]))
        if not r["only_character"] and not r["only_contrast"]:
            print("\n(the two frames are identical over the arc scope)")
    else:
        print(f"{r['character']} knows ({len(r['knows'])} facts over the arc scope):")
        print(_fmt_facts(r["knows"]))
    return 0


def _cmd_turn(args: argparse.Namespace) -> int:
    from construct import Session

    with Session.open(args.playthrough, provider=_provider()) as session:
        reply = session.turn(args.player_input)
        print(reply.prose)
        if args.debug and reply.trace is not None:
            _print_trace(reply.trace)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scenarios":
        return _cmd_scenarios()
    if args.command == "new":
        return _cmd_new(args)
    if args.command == "play":
        return _cmd_play(args)
    if args.command == "knows":
        return _cmd_knows(args)
    if args.command == "turn":
        return _cmd_turn(args)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
