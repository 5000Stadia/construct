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
    source.add_argument("--interview", nargs="?", const="", metavar="BRIEF",
                        help="build a world LIVE from a brief (genre/setting/"
                             "characters/situation). Pass the brief inline, or "
                             "omit it to be prompted.")
    source.add_argument("--generate", nargs="?", const="", metavar="SEED",
                        help="prose-first: author a complete hidden story from "
                             "an optional seed, then ingest it (the showcase "
                             "loop). Pass a seed inline, or omit for 'surprise me'.")
    new.add_argument("--name", help="scenario name (default: prose stem, or 'world')")
    new.add_argument("--endless", action="store_true",
                     help="no terminal arc: the world carries on past the arc's "
                          "destination instead of settling into aftermath")

    sub.add_parser("start", help="guided session-zero menu: pick a world "
                                 "(play / generate / provide) and a mode")

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
    play.add_argument("--at", metavar="COORD", type=float, default=None,
                      help="ENTER at a timeline coordinate: the establishing view is "
                           "taken as-of it (e.g. --at 2 to enter as of chapter 2). "
                           "Recorded on a fresh start; default is the timeline head.")

    knows = sub.add_parser(
        "knows", help="inspect a character's knowledge frame; --contrast shows two diverge")
    knows.add_argument("scenario")
    knows.add_argument("character", help="entity id or bare name (e.g. marn or person:marn)")
    knows.add_argument("--contrast", metavar="OTHER",
                       help="another character: show what each knows that the other doesn't")

    imp = sub.add_parser("import", help="ingest a document (.txt/.md) into the library, "
                                        "or watch a drop folder")
    imp.add_argument("path", nargs="?",
                     help="a .txt/.md file to ingest (omit with --watch)")
    imp.add_argument("--watch", action="store_true",
                     help="poll the import folder and ingest drops as they land")
    imp.add_argument("--dir", metavar="DIR", default="import",
                     help="import folder for --watch (default: import/)")
    imp.add_argument("--name", help="scenario name (default: unique slug of the filename)")
    imp.add_argument("--endless", action="store_true", help="no terminal arc")

    turn = sub.add_parser("turn", help="process exactly one player turn (one-shot; scripting/tests)")
    turn.add_argument("playthrough", help="scenario name (its single slot is the save)")
    turn.add_argument("player_input", metavar="INPUT")
    turn.add_argument("--debug", action="store_true",
                      help="emit the turn trace: briefing frame list, cohort "
                           "trace, concealment audit, beats/clocks/nudges")

    setup = sub.add_parser("setup", help="optional: set up Telegram for phone continuity")
    setup.add_argument("target", nargs="?", choices=["telegram"],
                       help="'telegram' runs the bot-token wizard")

    sub.add_parser("telegram", help="run the Telegram transport (needs `setup telegram` first)")

    inv = sub.add_parser("invite", help="mint a one-time invite code for a transport")
    inv.add_argument("platform", choices=["telegram", "loopback"])
    inv.add_argument("--scenario", default="anchor", help="scenario the invite grants")

    lb = sub.add_parser("loopback", help="run the offline self-test channel (file-driven transport)")
    lb.add_argument("--in", dest="inbound", default=None, help="inbound JSONL path")
    lb.add_argument("--out", dest="outbox", default=None, help="outbox JSONL path")

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
    from construct.game import (ViabilityError, create_scenario_from_generated,
                                create_scenario_from_ingest,
                                create_scenario_from_interview)
    endless = getattr(args, "endless", False)
    def _stage(msg: str) -> None:  # live progress + PB-layer showcase on stdout
        print(msg, flush=True)
    if getattr(args, "generate", None) is not None:
        name = args.name or "world"
        try:
            meta = create_scenario_from_generated(name, _provider(), seed=args.generate,
                                                  endless=endless, on_stage=_stage)
        except ViabilityError as exc:
            print(f"Generated world was not playable: {'; '.join(exc.problems)}.\n"
                  f"The source story is kept for inspection at {exc.source_path}.",
                  file=sys.stderr)
            return 1
    elif args.interview is not None:
        brief = args.interview.strip()
        if not brief:
            print("Describe the world you want — genre, setting, key characters, "
                  "the opening situation. (One paragraph is plenty.)")
            try:
                brief = input("brief> ").strip()
            except (EOFError, KeyboardInterrupt):
                brief = ""
        if not brief:
            print("No brief given; nothing to build.", file=sys.stderr)
            return 2
        name = args.name or "world"
        meta = create_scenario_from_interview(name, brief, _provider(),
                                              endless=endless, on_stage=_stage)
    else:
        prose = Path(args.ingest)
        name = args.name or prose.stem.replace(" ", "_")
        meta = create_scenario_from_ingest(name, prose, _provider(),
                                           endless=endless, on_stage=_stage)
    print(f"Scenario {name!r} created: {meta['title']}")
    print(f"  protagonist: {meta['protagonist']}")
    print(f"  theme: {meta['theme']}")
    print(f"Play it: construct play {name}")
    return 0


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _cmd_start(args: argparse.Namespace) -> int:
    """The guided session-zero menu (STARTUP-ENTRY §4): two questions —
    WHICH world (play existing / generate new / provide fiction) and WHICH
    mode (win/loss or freeplay). A surface OVER the flags: it builds the
    same Namespaces and delegates to `_cmd_play`/`_cmd_new`, so every path
    stays independently reachable by flag for scripting/headless play
    (Kernos 063 B: surface, not gate)."""
    from construct.game import list_scenarios

    print("Construct — session zero.")
    print("  1) play an existing world")
    print("  2) generate a new world (prose-first: author a hidden story, then ingest)")
    print("  3) provide your own fiction to ingest")
    choice = _ask("choose 1-3> ")

    if choice == "1":
        rows = list_scenarios()
        if not rows:
            print("No worlds yet — build one with option 2 or 3.", file=sys.stderr)
            return 2
        for i, r in enumerate(rows, 1):
            print(f"  {i}) {r['name']} — {r.get('title', '')}")
        try:
            name = rows[int(_ask('world #> ')) - 1]["name"]
        except (ValueError, IndexError):
            print("No such world.", file=sys.stderr)
            return 2
        return _cmd_play(argparse.Namespace(
            scenario=name, fresh=False, resume=False, debug=False, at=None))

    if choice not in ("2", "3"):
        print("Nothing chosen.", file=sys.stderr)
        return 2

    # Both build paths share the win/loss-vs-freeplay question (freeplay maps
    # to the endless/no-terminal arc; win/loss is the terminating mode).
    endless = _ask("mode — [w]in/loss or [f]reeplay? ").lower().startswith("f")
    name = _ask("name for the new world> ") or "world"
    ns = argparse.Namespace(name=name, endless=endless,
                            generate=None, interview=None, ingest=None)
    if choice == "2":
        ns.generate = _ask("optional seed (genre/premise, or blank to surprise me)> ")
    else:
        path = _ask("path to your .txt/.md fiction> ")
        if not path:
            print("No file given.", file=sys.stderr)
            return 2
        ns.ingest = path
    return _cmd_new(ns)


def _cmd_play(args: argparse.Namespace) -> int:
    """The interactive REPL (letter 032): a thin client of the session
    API (letter 034) — open once, loop turn→print, saved every turn."""
    from construct import Session

    # First-load menu (Cx 065): offered only on an interactive terminal when
    # Telegram is neither configured nor dismissed. Default (Enter) is
    # zero-friction CLI play; never gates headless/scripted runs.
    if sys.stdin.isatty():
        from construct import setup as _setup
        if _setup.first_load_menu() == "telegram":
            try:
                _setup.setup_telegram()
            except Exception as exc:
                print(f"(Telegram setup skipped: {exc})", file=sys.stderr)

    session = Session.open(args.scenario, fresh=args.fresh, provider=_provider(),
                           as_of=getattr(args, "at", None))
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


def _cmd_import(args: argparse.Namespace) -> int:
    from construct.library import (ingest_document, scan_import_folder,
                                   watch_import_folder)
    def _stage(msg: str) -> None:
        print(msg, flush=True)
    if args.watch:
        try:
            watch_import_folder(_provider(), import_dir=args.dir, on_stage=_stage)
        except KeyboardInterrupt:
            print("\nstopped watching.")
        return 0
    if not args.path:
        print("Give a .txt/.md file to import, or --watch a folder.", file=sys.stderr)
        return 2
    try:
        name, meta = ingest_document(args.path, _provider(), name=args.name,
                                     endless=args.endless, on_stage=_stage)
    except (FileNotFoundError, ValueError) as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 2
    print(f"Imported into the library: {meta['title']}  (play: construct play {name})")
    return 0


def _registry_path():
    from construct.setup import CONSTRUCT_DIR
    return CONSTRUCT_DIR / "registry.sqlite"


def _cmd_setup(args: argparse.Namespace) -> int:
    from construct import setup
    if args.target == "telegram":
        try:
            setup.setup_telegram()
            return 0
        except Exception as exc:
            print(f"setup failed: {exc}", file=sys.stderr)
            return 1
    # bare `construct setup` → the same first-load offer, explicitly invoked
    choice = setup.first_load_menu()
    if choice == "telegram":
        try:
            setup.setup_telegram()
        except Exception as exc:
            print(f"setup failed: {exc}", file=sys.stderr)
            return 1
    return 0


def _cmd_telegram(args: argparse.Namespace) -> int:
    from construct import setup, telegram_bot
    token = setup.read_token()
    if not token:
        print("Telegram is not set up. Run: construct setup telegram", file=sys.stderr)
        return 2
    print("Telegram transport running (Ctrl-C to stop).")
    try:
        telegram_bot.serve(_registry_path(), token)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def _cmd_invite(args: argparse.Namespace) -> int:
    import time
    from construct import registry
    conn = registry.connect(_registry_path())
    code = registry.mint_invite(conn, args.platform, args.scenario, now=time.time())
    print(f"Invite code: {code}")
    print(f"  platform: {args.platform}   scenario: {args.scenario}   (single-use, 72h)")
    return 0


def _cmd_loopback(args: argparse.Namespace) -> int:
    from construct import loopback
    from construct.setup import CONSTRUCT_DIR
    inbound = args.inbound or str(CONSTRUCT_DIR / "loopback.in.jsonl")
    outbox = args.outbox or str(CONSTRUCT_DIR / "loopback.out.jsonl")
    print(f"Loopback self-test channel: in={inbound} out={outbox} (Ctrl-C to stop).")
    try:
        loopback.serve(inbound, outbox, _registry_path())
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scenarios":
        return _cmd_scenarios()
    if args.command == "new":
        return _cmd_new(args)
    if args.command == "start":
        return _cmd_start(args)
    if args.command == "play":
        return _cmd_play(args)
    if args.command == "knows":
        return _cmd_knows(args)
    if args.command == "turn":
        return _cmd_turn(args)
    if args.command == "import":
        return _cmd_import(args)
    if args.command == "setup":
        return _cmd_setup(args)
    if args.command == "telegram":
        return _cmd_telegram(args)
    if args.command == "invite":
        return _cmd_invite(args)
    if args.command == "loopback":
        return _cmd_loopback(args)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
