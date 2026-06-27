"""The transport-agnostic core — the dumb pipe shared by every chat
transport (Telegram, the offline loopback, any future adapter).

It consumes a NORMALIZED `InboundEvent` and returns an `Outbound` (chat id +
already-chunked reply). It owns exactly what is transport-independent:
- the **invite gate** (unknown senders get a static rejection with ZERO model
  or `Session` allocation — the gate sits before any session is opened);
- **command routing** (`/help /play /resume /scenarios`) and in-world turns;
- **scenario scope** (a claimed player is locked to the scenario their invite
  granted — `/play other` cannot escape it);
- **session routing** via an injectable factory (so offline tests use a fake
  `Session`, never `CodexProvider`);
- **reply chunking** at the adapter-provided message limit.

IO (`getUpdates`/`sendMessage`, file queues) and exactly-once persistence
(offset/dedup/outbox) live in the adapters, not here (Codex spec review).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from construct import registry

logger = logging.getLogger(__name__)

#: Where per-player transcripts and /dump snapshots are written. Under the
#: already-gitignored `worlds/`, so chat logs never enter version control.
DEFAULT_LOG_DIR = Path("worlds/.construct/transcripts")

#: Where `/feedback` notes land — the operator's (my) dev inbox. A live note
#: dropped mid-play, bundled with a snippet of the last few turns, so a problem
#: can be picked up and fixed without leaving the session.
DEFAULT_FEEDBACK_DIR = Path("dev_inbox")

#: There is NO idle monitoring — every gap between turns, however long, is still
#: mid-session (founder). Leaving a story happens only on an explicit `/exit` or a
#: confirmed out-of-character "let's do a new story" request.

#: Delay before the `/reboot` re-exec, so the confirmation reply is actually sent
#: before the process is replaced. Module-level so tests can zero it.
REBOOT_DELAY_S = 1.5


def _affirmative(text: str) -> bool:
    """A yes-ish answer to the 'leave the story?' confirm."""
    t = (text or "").strip().lower().rstrip("!. ")
    return t in {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
                 "do it", "exit", "quit", "leave", "new story", "start over"}

STATIC_REJECT = (
    "This Construct bot is invite-only. Send the CONS- invite code the operator "
    "gave you to begin.")
HELP = ("Just type what you want to do — no commands needed; the story responds, "
        "and it saves automatically each turn. If you ever want them: /play "
        "(restart fresh), /resume (continue), /status (time & place now; /status "
        "pin toggles the header atop each reply), /scenarios (your world), /dump "
        "(save this chat to a log), /ooc <question> (ask the engine out of "
        "character — what's available, how it works), 📝 /note <text> (jot a note — "
        "your journal follows you across adventures; /notes lists them, /del # removes "
        "one), /exit (step out to the start menu — your game is saved), /feedback "
        "<note> (flag the operator), /help.")

#: The Construct's first words — a SIMPLE welcome (founder: "first message should
#: be a simple greeting… if the user knows what's up they'll just load what they
#: want"). The rich showcase of worlds/saved games/new-build is the Construct
#: cohort's job WHEN ASKED, not a wall of options up front.
GREETING = (
    "📽️ Welcome to the Construct Projector — online and ready.\n\n"
    "Pick a path:\n"
    "🆕 New — create a new world\n"
    "📂 Browse — say “list” to see the ready-made worlds\n"
    "▶️ Resume — pick up a saved game where you left off\n\n"
    "What'll it be?")

#: Sent the moment a build begins (the long generate-then-ingest). The per-phase
#: pings follow via the notify channel (INGEST-PROGRESS-NOTIFICATIONS.md).
BUILD_HEADS_UP = (
    "🌐 Constructing your world — the initial build may take ~20 minutes. "
    "I'll tell you the moment the doors open.")


@dataclass(frozen=True)
class InboundEvent:
    """A transport-neutral inbound message. `update_ids` are the source
    update ids this event covers (one normally; several when an adapter
    coalesces a burst) — the adapter uses them for exactly-once bookkeeping."""

    platform: str
    external_id: str
    chat_id: str
    text: str
    update_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Outbound:
    chat_id: str
    chunks: list[str] = field(default_factory=list)


def chunk(text: str, limit: int) -> list[str]:
    """Split `text` into ≤`limit` pieces, never silently truncating (the
    Kernos-bot lesson). Prefers a newline boundary, then a hard cut. Always
    returns ≥1 chunk (empty text → one empty string, so a turn always
    answers)."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks or [""]


class TransportCore:
    """One per running transport. Holds the open sessions keyed by player_id;
    routing is synchronous (the adapter serializes per-player by handing
    events one at a time)."""

    def __init__(self, conn, *, platform: str, msg_limit: int,
                 session_factory: Callable[..., Any] | None = None,
                 log_dir: Path | str | None = None,
                 feedback_dir: Path | str | None = None,
                 provider: Any | None = None,
                 builder: Callable[..., Any] | None = None,
                 notify: Callable[[str, str], None] | None = None) -> None:
        self._conn = conn
        self._platform = platform
        self._limit = msg_limit
        self._sessions: dict[str, Any] = {}
        # Players we've asked "leave the story?" — their next message is the yes/no.
        self._pending_exit: set[str] = set()
        # Players whose last /ooc was a plot-protective deflection — a renewed push
        # escalates (honesty + offer a new scenario).
        self._ooc_pressed: set[str] = set()
        # Players we've asked "restart?" — their next message picks episode / original / cancel.
        self._pending_restart: set[str] = set()
        # Players who chose "original" on /restart — their next message picks
        # keep-my-character / redo-the-interview / cancel.
        self._pending_restart_original: set[str] = set()
        # Players mid-original-restart who still owe the notes keep/wipe answer.
        # pid -> {"keep_character": bool}
        self._pending_restart_notes: dict[str, dict] = {}
        # Players whose story just CONCLUDED — their next message is the continue? yes/no
        # (CONCLUDE→CONTINUE: a new episode/case for the same protagonist).
        self._pending_continue: set[str] = set()
        self._session_factory = session_factory or _default_session_factory
        self._log_dir = Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR
        self._feedback_dir = (Path(feedback_dir) if feedback_dir is not None
                              else DEFAULT_FEEDBACK_DIR)
        # The Construct dialogue (Atrium) needs a model provider for the
        # architect cohort + the build; both lazy so CLI/tests that never reach
        # creation pay nothing. `builder` runs the long generate-then-ingest;
        # `notify` sends interim progress messages (the build pings) OUTSIDE the
        # one-reply turn — injected by the adapter, no-op when absent.
        self._provider_obj = provider
        self._builder = builder
        self._notify_fn = notify

    def _provider(self) -> Any:
        if self._provider_obj is None:
            from construct.provider import CodexProvider
            self._provider_obj = CodexProvider()
        return self._provider_obj

    def _build(self, **kw) -> Any:
        if self._builder is None:
            from construct.game import create_scenario_from_generated
            self._builder = create_scenario_from_generated
        return self._builder(**kw)

    def handle(self, ev: InboundEvent, *, now: float) -> Outbound:
        """Route one inbound event to a reply. Never raises for an in-world
        failure — a transport must survive every turn."""
        text = ev.text.strip()
        pid = registry.player_for(self._conn, ev.platform, ev.external_id)
        if pid is None:
            return self._gate(ev, text, now=now)
        # A live, readable transcript per player (USER/BOT lines) — written to
        # the gitignored log dir. /dump snapshots it on demand (operator ask).
        self._log(ev, "USER", ev.text)
        low = text.lower()
        if pid in self._pending_restart_notes:
            decision = self._pending_restart_notes.pop(pid)
            out = self._do_restart_notes(pid, ev, low, decision)  # already an Outbound
            self._log(ev, "BOT", "\n".join(out.chunks))
            return out
        if pid in self._pending_restart_original:
            self._pending_restart_original.discard(pid)
            out = self._do_restart_original(pid, ev, low)  # already an Outbound
            self._log(ev, "BOT", "\n".join(out.chunks))
            return out
        if pid in self._pending_restart:
            self._pending_restart.discard(pid)
            out = self._do_restart(pid, ev, low)  # already an Outbound
            self._log(ev, "BOT", "\n".join(out.chunks))
            return out
        if pid in self._pending_continue:
            # CONCLUDE→CONTINUE: the story ended; this message is the continue? yes/no.
            self._pending_continue.discard(pid)
            if _affirmative(low):
                out = self._do_continue(pid, ev)
            else:
                out = self._reply(ev, "Then the story rests here — a good place to leave it. "
                                      "Say /restart to play again, or start something new anytime.")
            self._log(ev, "BOT", "\n".join(out.chunks))
            return out
        if pid in self._pending_exit:
            # The player asked (out of character) to leave/start over; this message
            # is their yes/no. Affirm → step out; anything else → carry on.
            self._pending_exit.discard(pid)
            if _affirmative(low):
                out = self._reply(ev, self._exit(pid, ev))
            else:
                out = self._reply(ev, "Alright — staying in the story. Carry on.")
        elif low == "/restart":
            title = self._title_of(registry.scenario_for(self._conn, ev.platform,
                                                          ev.external_id))
            if self._in_episodes(pid, ev):
                # Multi-episode playthrough → the two depths are meaningful.
                self._pending_restart.add(pid)
                out = self._reply(
                    ev, f"Restarting erases your saved progress in {title}. How far "
                        f"back?\n• “episode” — restart just this episode from its "
                        f"start (your character carries over).\n• “original” — go all "
                        f"the way back to the very start of the original scenario.\n• "
                        f"“cancel” — keep playing.")
            else:
                # Single episode (no episode progression yet) → no episode/original
                # choice; it's just a restart (founder). Go straight to the only
                # meaningful question — same character, or redo them.
                self._pending_restart_original.add(pid)
                out = self._reply(
                    ev, f"Restart {title} from the beginning? You'll lose your saved "
                        f"progress.\n• “keep” — restart but keep your character\n• "
                        f"“redo” — restart and rebuild your character\n• “cancel” — "
                        f"keep playing.")
        elif low == "/wipe":
            out = self._reply(ev, self._wipe(pid, ev, now=now))
        elif low == "/disconnect":
            out = self._reply(ev, self._disconnect(pid, ev))
        elif low == "/reboot":
            out = self._reply(ev, self._reboot(ev))
        elif low.startswith("/dump"):
            out = self._reply(ev, self._dump(ev))
        elif low == "/exit":
            out = self._reply(ev, self._exit(pid, ev))
        elif text.startswith("/"):
            out = self._reply(ev, self._command(pid, ev, text, now=now))
        else:
            out = self._turn(pid, ev, text)
        self._log(ev, "BOT", "\n".join(out.chunks))
        return out

    def _do_restart(self, pid: str, ev: InboundEvent, answer: str) -> Outbound:
        """Answer to the `/restart` confirm (step one — how far back):
        - 'episode' → restart THIS episode from its start: roll the slot back to the
          episode checkpoint (character carries over, no Foyer). For a first/only
          episode with no checkpoint, fall back to a clean copy with the saved
          character re-applied.
        - 'original' → go all the way back to the original scenario; ask step two
          (keep the same character, or redo the interview).
        Anything else → cancel."""
        from construct.game import restore_episode_start
        a = answer.strip().lower()
        plat, ext = ev.platform, ev.external_id
        scen = registry.scenario_for(self._conn, plat, ext)
        if any(k in a for k in ("original", "very start", "very beginning",
                                "all the way", "start start", "beginning beginning",
                                "everything", "2")):
            self._pending_restart_original.add(pid)
            return self._reply(
                ev, "All the way back to the original. Do you want to keep the "
                    "character and elements you set up last time, or redo that "
                    "interview from scratch?\n• “keep” — same character, fresh "
                    "world.\n• “redo” — start the character interview over.\n• "
                    "“cancel” — keep playing.")
        if any(k in a for k in ("episode", "this", "current", "top", "again",
                                "restart", "1")):
            registry.set_started(self._conn, plat, ext, False)
            registry.clear_chargen(self._conn, plat, ext)
            mode = _valid_mode(registry.get_mode(self._conn, plat, ext))
            if restore_episode_start(scen, pid):
                # Slot rolled back to this episode's opening — resume it (the
                # character is already in the world; no Foyer, earlier episodes
                # survive).
                return self._enter_world(
                    pid, ev, scenario=scen, mode=mode, fresh=False,
                    preamble="Restarting this episode from the top.")
            # No checkpoint (legacy slot) — pristine copy + re-apply the saved
            # character so "this episode" still keeps who they are.
            return self._restart_keep_character(
                pid, ev, scen, mode, "Restarting this episode from the top.")
        return self._reply(ev, "Kept your game as is — carry on.")

    def _do_restart_original(self, pid: str, ev: InboundEvent, answer: str) -> Outbound:
        """`/restart → original` step two — the character: 'keep' → re-apply the same
        character (skip the Foyer); 'redo' → re-run the interview. Either way ALL
        episode progress + checkpoints drop. If the player has notes for this story,
        ask the keep/wipe question (step three) before acting; else act now. Anything
        else → cancel."""
        a = answer.strip().lower()
        plat, ext = ev.platform, ev.external_id
        scen = registry.scenario_for(self._conn, plat, ext)
        if any(k in a for k in ("redo", "fresh", "scratch", "new", "interview",
                                "again", "2")):
            keep_character = False
        elif any(k in a for k in ("keep", "same", "character", "elements", "1")):
            keep_character = True
        else:
            return self._reply(ev, "Kept your game as is — carry on.")
        if registry.list_notes(self._conn, plat, ext, scen):
            self._pending_restart_notes[pid] = {"keep_character": keep_character}
            return self._reply(
                ev, "And your notes for this story — keep them, or wipe them for a "
                    "clean slate?\n• “keep” — keep your notes.\n• “wipe” — clear "
                    "them.\n• “cancel” — don't restart after all.")
        return self._execute_restart_original(pid, ev, keep_character=keep_character,
                                              wipe_notes=False)

    def _do_restart_notes(self, pid: str, ev: InboundEvent, answer: str,
                          decision: dict) -> Outbound:
        """`/restart → original` step three — the notes: 'wipe' clears this story's
        notes, 'keep' carries them into the fresh start. Ambiguous → keep (never
        destroy by accident). 'cancel' aborts the whole restart (nothing dropped)."""
        a = answer.strip().lower()
        if any(k in a for k in ("cancel", "stop", "nvm", "never", "no,")):
            return self._reply(ev, "Kept your game as is — carry on.")
        wipe = any(k in a for k in ("wipe", "clear", "clean", "delete", "yes"))
        return self._execute_restart_original(
            pid, ev, keep_character=decision.get("keep_character", False),
            wipe_notes=wipe)

    def _execute_restart_original(self, pid: str, ev: InboundEvent, *,
                                  keep_character: bool, wipe_notes: bool) -> Outbound:
        """Perform the factory-fresh original restart: drop all episode progress +
        checkpoints; optionally wipe this story's notes; re-enter (same character, or
        a fresh Foyer)."""
        from construct.game import restore_original
        plat, ext = ev.platform, ev.external_id
        scen = registry.scenario_for(self._conn, plat, ext)
        restore_original(scen, pid)
        if wipe_notes:
            registry.clear_notes(self._conn, plat, ext, scen)
        mode = _valid_mode(registry.get_mode(self._conn, plat, ext))
        note_tag = " with a clean notebook" if wipe_notes else " (your notes kept)"
        if keep_character:
            return self._restart_keep_character(
                pid, ev, scen, mode,
                f"Back to the very beginning — same character{note_tag}.")
        registry.set_started(self._conn, plat, ext, False)
        registry.clear_chargen(self._conn, plat, ext)
        self._drop_slot(scen, pid)  # pristine copy → re-runs the Foyer
        return self._enter_world(
            pid, ev, scenario=scen, mode=mode, fresh=True,
            preamble=f"Back to the very beginning — a fresh character{note_tag}.")

    def _restart_keep_character(self, pid: str, ev: InboundEvent, scen: str,
                                mode: str | None, preamble: str) -> Outbound:
        """Open a clean copy of `scen` and re-apply the player's saved character
        WITHOUT re-running the Foyer (then re-checkpoint the playable start). Falls
        back to a normal fresh entry (which runs the Foyer) if no saved character."""
        from construct.foyer import CharacterSheet
        self._drop_slot(scen, pid)  # ensure a pristine copy on the fresh open
        saved = registry.get_character(self._conn, ev.platform, ev.external_id)
        if not saved:
            registry.set_started(self._conn, ev.platform, ev.external_id, False)
            registry.clear_chargen(self._conn, ev.platform, ev.external_id)
            return self._enter_world(pid, ev, scenario=scen, mode=mode,
                                     preamble=preamble, fresh=True)
        try:
            session = self._sessions[pid] = self._session_factory(
                scenario=scen, player_id=pid, fresh=True, mode_override=mode)
            session.apply_character(CharacterSheet.from_dict(saved))
        except Exception as exc:
            logger.exception("restart keep-character failed for %s", pid)
            return self._reply(ev, f"(could not reopen your world: {exc})")
        if mode:
            registry.set_mode(self._conn, ev.platform, ev.external_id, mode)
        registry.set_scenario(self._conn, ev.platform, ev.external_id, scen)
        registry.clear_creation(self._conn, ev.platform, ev.external_id)
        registry.clear_chargen(self._conn, ev.platform, ev.external_id)
        registry.mark_started(self._conn, ev.platform, ev.external_id)
        self._checkpoint_episode(ev, pid)  # the fresh playable start
        opening = session.opening()
        return self._reply(ev, f"{preamble}\n\n{opening}" if preamble else opening)

    def _drop_slot(self, scenario: str, pid: str) -> None:
        try:
            from construct.game import slot_path
            slot_path(scenario, pid).unlink(missing_ok=True)
        except Exception:
            logger.exception("slot drop failed for %s/%s", scenario, pid)

    def _in_episodes(self, pid: str, ev: InboundEvent) -> bool:
        """Is the player in a MULTI-episode playthrough (past episode one)? Only
        then do `/restart`'s episode-vs-original depths mean anything (founder: with
        no episodes, "it's just restart"). Episodic continuation isn't built yet, so
        there's no episode-2 state — always False for now; this is the hook the
        Series engine flips when EPISODIC-CONTINUATION ships."""
        return False

    def _wipe_data(self, pid: str, ev: InboundEvent) -> None:
        """Clear THIS player's play DATA — slots, any built world, episode
        checkpoints, transcript, notes, in-memory session/pending — and reset their
        progression to the fresh greeting. Does NOT touch the claim (no kick-out)."""
        plat, ext = ev.platform, ev.external_id
        scen = registry.scenario_for(self._conn, plat, ext) or "anchor"
        try:
            from construct.game import (slot_path, _unpublish_scenario,
                                        episode_checkpoint_path)
            slot_path(scen, pid).unlink(missing_ok=True)
            episode_checkpoint_path(scen, pid).unlink(missing_ok=True)
            built = f"live_{_safe(plat)}_{_safe(ext)}"
            slot_path(built, pid).unlink(missing_ok=True)
            episode_checkpoint_path(built, pid).unlink(missing_ok=True)
            _unpublish_scenario(built)        # remove their per-player built world
            self._transcript_path(ev).unlink(missing_ok=True)
        except Exception:
            logger.exception("wipe cleanup failed for %s", pid)
        self._sessions.pop(pid, None)
        self._pending_exit.discard(pid)
        self._ooc_pressed.discard(pid)
        self._pending_restart.discard(pid)
        self._pending_restart_original.discard(pid)
        self._pending_restart_notes.pop(pid, None)
        try:
            registry.clear_notes(self._conn, plat, ext)
        except Exception:
            logger.exception("note clear failed during wipe for %s", pid)
        registry.set_started(self._conn, plat, ext, False)
        registry.clear_creation(self._conn, plat, ext)
        registry.clear_chargen(self._conn, plat, ext)

    def _wipe(self, pid: str, ev: InboundEvent, *, now: float = 0.0) -> str:
        """HIDDEN operator self-wipe (`/wipe`, not in HELP): clear ALL the player's
        data + saves and reset to the fresh greeting — but DO NOT kick them out. The
        claim stays; no new code needed (founder: /wipe wipes everything, never
        un-auths). Their next message lands on the brand-new-user greeting."""
        self._wipe_data(pid, ev)
        return ("Wiped — clean slate, no saves. You're still connected; your next "
                "message starts you fresh.")

    def _disconnect(self, pid: str, ev: InboundEvent) -> str:
        """HIDDEN (`/disconnect`, not in HELP): the full kick-out — wipe data AND
        UN-CLAIM, so the operator can test the brand-new-user CLAIM flow from zero.
        Returning needs a fresh code minted locally (`construct invite`); the bot
        NEVER issues one itself (founder)."""
        self._wipe_data(pid, ev)
        registry.forget_player(self._conn, ev.platform, ev.external_id)
        return ("Disconnected — data wiped and you're un-claimed. To return, mint a "
                "fresh code locally with `construct invite` and send it here.")

    def _reboot(self, ev: InboundEvent) -> str:
        """HIDDEN operator command (`/reboot`, not in HELP): re-exec the bot
        process so freshly-deployed code takes effect WITHOUT a shell. The
        confirmation goes out first; then a short-delay daemon thread re-execs
        the original command line (`sys.orig_argv`), re-reading source and
        `.env`. Non-destructive — saved games live on disk; only the in-memory
        process is replaced (and any in-flight pending-confirm state is cleared).
        Named `/reboot`, not `/restart` (which restarts the player's STORY). If
        the re-exec raises, the current process keeps running on the old code
        (logged), so a botched reboot never takes the bot offline."""
        import os
        import sys
        import threading
        import time
        logger.warning("operator /reboot from %s:%s — re-exec in %.1fs via %r",
                       ev.platform, ev.external_id, REBOOT_DELAY_S, sys.orig_argv)

        def _exec() -> None:
            time.sleep(REBOOT_DELAY_S)
            try:
                os.execv(sys.orig_argv[0], sys.orig_argv)
            except Exception:
                logger.exception("/reboot re-exec failed; staying on current code")

        self._reboot_thread = threading.Thread(target=_exec, daemon=True, name="reboot")
        self._reboot_thread.start()
        return ("♻️ Rebooting the Construct — reloading the latest code. Give me a few "
                "seconds, then send any message (e.g. “new”, “list”, or /help).")

    def _exit(self, pid: str, ev: InboundEvent) -> str:
        """Leave the current scenario for the start menu — clear `started` (so the
        next message re-enters the Atrium) and any in-progress dialogue, drop the
        cached session; the saved playthrough slot is untouched (resumable)."""
        registry.set_started(self._conn, ev.platform, ev.external_id, False)
        registry.clear_chargen(self._conn, ev.platform, ev.external_id)
        self._sessions.pop(pid, None)
        registry.set_creation(self._conn, ev.platform, ev.external_id, _empty_creation())
        return ("Stepped out — your story is saved where you left it.\n\n" + GREETING)

    def _ooc(self, pid: str, ev: InboundEvent, text: str) -> str:
        """`/ooc <question or suggestion>` — talk to the ENGINE out of character,
        like a construct projector guest addressing the ship's computer. Questions get answered;
        creative suggestions are received in the spirit of good improv / rule of cool
        ('I'll see what I can do') and recorded for the narrator to weave in IF they
        fit — EXCEPT ones that would thwart the game type's payoff (e.g. guessing a
        whodunnit's culprit), which are met with gentle resistance, not a 'no'.
        Answered by the host; no turn, no time progression."""
        text = (text or "").strip()
        if not text:
            return ("Out of character — ask me anything (what's available, how this "
                    "works) or float an idea ('what if it was his brother all "
                    "along?'). I'll answer, and weave in what fits. e.g. /ooc what "
                    "can I play?")
        from construct import play_styles
        from construct.game import scenario_path
        started = registry.is_started(self._conn, ev.platform, ev.external_id)
        scen = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        worlds = ", ".join(w["title"] for w in self._library()) or "(none)"
        game_types = ""
        context = (f"Ready-made worlds: {worlds}. The player can open a ready-made "
                   "world, resume, build a new one, ask things, or /exit to the "
                   "start. Auto-saves every turn.")
        if started:
            import json
            try:
                meta = json.loads(scenario_path(scen).with_suffix(".meta.json").read_text())
                game_types = ", ".join(play_styles.names(meta.get("game_type")))
            except Exception:
                pass
            context = f"The player is in: {self._title_of(scen)}. " + context
        else:
            context = "The player is at the start menu, not in a story. " + context
        # The hidden answers (host-side) so protection is proportional to the real
        # secret — only while a session is open; never surfaced to the player.
        secrets = ""
        session = self._sessions.get(pid)
        if session is not None:
            try:
                secrets = session.concealed_truths()
            except Exception:
                logger.exception("concealed_truths failed for %s", pid)
        try:
            from construct.cohorts import ooc_respond
            out = ooc_respond(self._provider(), text, game_types=game_types,
                              context_note=context, pressed=pid in self._ooc_pressed,
                              secrets=secrets)
        except Exception:
            logger.exception("/ooc failed for %s", pid)
            return "(couldn't reach the engine just now — try again.)"
        # Track the protect/press state: a protective deflection arms escalation;
        # anything else (answer, weave, the escalation itself) resets it.
        if out.get("protected") and not out.get("offer_new"):
            self._ooc_pressed.add(pid)
        else:
            self._ooc_pressed.discard(pid)
        # Pressed past protection → the engine offered a NEW scenario; route a "yes"
        # through the existing exit-confirm (exit → Atrium → build a fresh world).
        if out.get("offer_new"):
            self._pending_exit.add(pid)
        # A fitting suggestion the engine agreed to try → record it for the narrator.
        weave = (out.get("weave") or "").strip()
        if weave and session is not None:
            try:
                session.note_wish(weave)
            except Exception:
                logger.exception("note_wish failed for %s", pid)
        return out.get("reply") or "Noted."

    def _title_of(self, scenario: str) -> str:
        try:
            import json
            from construct.game import scenario_path
            mp = scenario_path(scenario).with_suffix(".meta.json")
            if mp.exists():
                return json.loads(mp.read_text()).get("title") or "your story"
        except Exception:
            logger.exception("title lookup failed for %s", scenario)
        return "your story"

    # -- gate: the only thing an un-claimed sender can do is present a code --
    def _gate(self, ev: InboundEvent, text: str, *, now: float) -> Outbound:
        code = _extract_code(text)
        if code:
            pid = registry.claim_invite(self._conn, code, ev.platform,
                                        ev.external_id, now=now)
            if pid:
                # Open the Construct dialogue (the Atrium): greet, and seed an
                # empty creation blob so the next message starts the conversation.
                registry.set_creation(self._conn, ev.platform, ev.external_id,
                                      _empty_creation())
                return self._reply(ev, GREETING)
        return self._reply(ev, STATIC_REJECT)  # uniform; never leaks the reason

    # -- the library the Construct showcases (by title, not raw id) ----------
    def _library(self) -> list[dict]:
        """Every shelf-ready world, each as {name, title, logline}. The guest sees the
        TITLE (a campaign/novel name set at ingest), never the raw scenario id. Includes
        PLAYER-BUILT worlds (`live_*`) — they're SHARED options for everyone (founder:
        pool the good generated worlds), while each player who picks one gets their OWN
        save (a separate per-player slot from the shared pristine). Excludes only play
        slots and any world missing a title (an incomplete/test artifact)."""
        out: list[dict] = []
        try:
            from construct.game import list_scenarios
            for s in list_scenarios():
                name = s["name"]
                title = (s.get("title") or "").strip()
                if not title or title == name:
                    continue  # no real title → not shelf-ready, skip it
                genre = (s.get("genre") or s.get("genre_era") or "").strip()
                out.append({"name": name, "title": title, "genre": genre,
                            "logline": _logline(s)})
        except Exception:
            logger.exception("library listing failed")
        return out

    def _catalog(self) -> dict[str, str]:
        """{name: 'Title — genre/hook'} for the Construct to speak (so the guest
        sees the STYLE of each title — founder); pick_world resolves to the name.
        Prefers the authored genre tag, falling back to the logline hook."""
        return {w["name"]: (f"{w['title']} — {w['genre']}" if w["genre"]
                            else (f"{w['title']} — {w['logline']}" if w["logline"]
                                  else w["title"]))
                for w in self._library()}

    def _world_menu(self, resumable: str = "") -> str:
        """A clean, scannable menu of the ready-made worlds (founder: 'more menu
        clean' — emoji to separate sections). Host-rendered for consistency, one
        world per line with a genre emoji; the Construct's prose introduces it."""
        lib = self._library()
        if not lib:
            return ""
        # Plain text + emoji only — the Telegram sender uses no parse_mode, so
        # markdown would show literal asterisks. Emoji + line breaks do the work.
        lines = ["📂 READY-MADE WORLDS"]
        for w in lib:
            tag = f" — {w['genre']}" if w["genre"] else (
                f" — {w['logline']}" if w["logline"] else "")
            lines.append(f"{_genre_emoji(w['genre'], w['title'])} {w['title']}{tag}")
        if resumable:
            lines.append("")
            lines.append(f"▶️ Resume — {self._title_of(resumable)}")
        lines.append("")
        lines.append("✨ …or describe a new world and I'll shape it with you.")
        return "\n".join(lines)

    def _command(self, pid: str, ev: InboundEvent, text: str, *, now: float = 0.0) -> str:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if cmd == "/help":
            return HELP
        if cmd == "/feedback":
            note = parts[1] if len(parts) > 1 else ""
            return self._feedback(ev, note)
        if cmd == "/scenarios":
            return f"Your world: {scenario}."
        if cmd == "/status":
            return self._status(pid, ev, parts[1].strip().lower() if len(parts) > 1 else "")
        if cmd == "/ooc":
            return self._ooc(pid, ev, parts[1] if len(parts) > 1 else "")
        if cmd == "/notes":
            return self._notes(pid, ev, parts[1].strip().lower() if len(parts) > 1 else "")
        if cmd == "/note":
            return self._note(pid, ev, parts[1].strip() if len(parts) > 1 else "", now=now)
        if cmd == "/del":
            return self._del(pid, ev, parts[1] if len(parts) > 1 else "")
        if cmd in ("/play", "/resume"):
            # Scenario scope is locked to the invite (Codex): the argument, if
            # any, is ignored — a player cannot reach an ungranted scenario.
            fresh = cmd == "/play"
            mode = _valid_mode(registry.get_mode(self._conn, ev.platform, ev.external_id))
            try:
                self._sessions[pid] = self._session_factory(
                    scenario=scenario, player_id=pid, fresh=fresh,
                    mode_override=mode)
            except Exception as exc:
                logger.exception("session open failed for %s", pid)
                return f"(could not open {scenario}: {exc})"
            return self._sessions[pid].opening()
        return f"Unknown command. {HELP}"

    # -- /status: the time|location header (toggle) + an on-demand one-liner ---
    def _status(self, pid: str, ev: InboundEvent, arg: str) -> str:
        """`/status pin` toggles the always-on time|location header; bare `/status`
        returns it once, WITHOUT running a turn or advancing time."""
        if arg == "pin":
            on = not registry.get_status_pin(self._conn, ev.platform, ev.external_id)
            registry.set_status_pin(self._conn, ev.platform, ev.external_id, on)
            return ("Status header ON — time and place ride atop each reply."
                    if on else
                    "Status header OFF — type /status anytime to check time and place.")
        if not registry.is_started(self._conn, ev.platform, ev.external_id):
            return "(no story open yet — step into one first.)"
        line = self._status_line(pid, ev)
        return line or "(time and place unavailable just now.)"

    def _status_line(self, pid: str, ev: InboundEvent) -> str:
        """The session's `time | location` one-liner — opening the world read-only
        if it isn't cached. Pure reads (no turn, no time progression)."""
        session = self._sessions.get(pid)
        if session is None:
            mode = _valid_mode(registry.get_mode(self._conn, ev.platform, ev.external_id))
            scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
            try:
                session = self._sessions[pid] = self._session_factory(
                    scenario=scenario, player_id=pid, fresh=False, mode_override=mode)
            except Exception:
                logger.exception("status open failed for %s", pid)
                return ""
        try:
            return session.status_line()
        except Exception:
            logger.exception("status_line failed for %s", pid)
            return ""

    # -- /note, /notes: the player's journal (zero-turn, never canon) ---------
    def _note(self, pid: str, ev: InboundEvent, text: str, *, now: float = 0.0) -> str:
        """`/note <text>` records a player note for their own future reference,
        stamped with the current time|place. `/note` with no text → usage. Never
        runs a turn or advances time."""
        if not text:
            return "📝 Add a note with `/note <your note>`. `/notes` shows them all."
        scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if not scenario:
            return "📝 (step into a world first — then jot all the notes you like.)"
        # Best-effort context from an ALREADY-OPEN session only (don't force a
        # world open just to stamp a note); None if no live session.
        context = None
        session = self._sessions.get(pid)
        if session is not None:
            try:
                context = session.status_line()
            except Exception:
                logger.exception("note context read failed for %s", pid)
        try:
            registry.add_note(self._conn, ev.platform, ev.external_id,
                              scenario, text, context, now)
            total = len(registry.list_notes(self._conn, ev.platform, ev.external_id,
                                             scenario))
        except Exception:
            logger.exception("add_note failed for %s", pid)
            return "📝 (couldn't save that note — try again?)"
        return f"📝 Noted. ({total} note{'s' if total != 1 else ''} — /notes to see them.)"

    def _notes(self, pid: str, ev: InboundEvent, arg: str) -> str:
        """`/notes` lists this character's notes (they carry across episodes of the
        same scenario, not to a different adventure); `/notes clear` drops them.
        Zero-turn, zero-time."""
        scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if not scenario:
            return "📝 (step into a world first — then jot all the notes you like.)"
        if arg == "clear":
            n = registry.clear_notes(self._conn, ev.platform, ev.external_id, scenario)
            return (f"🗑️ Cleared {n} note{'s' if n != 1 else ''}." if n else
                    "📝 No notes to clear.")
        notes = registry.list_notes(self._conn, ev.platform, ev.external_id, scenario)
        if not notes:
            return "📝 No notes yet — jot one with `/note <your note>`."
        lines = ["📝 Your notes:"]
        for i, n in enumerate(notes, start=1):
            ctx = f"🕂 [{n['context']}] " if n.get("context") else ""
            lines.append(f"{i}. {ctx}{n['text']}")
        lines.append("— `/del #` removes one you no longer need.")
        return "\n".join(lines)

    def _del(self, pid: str, ev: InboundEvent, arg: str) -> str:
        """`/del #` deletes the #-th note as listed by `/notes`. Zero-turn."""
        scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if not scenario:
            return "📝 (no notes here yet.)"
        try:
            position = int(arg.strip().lstrip("#"))
        except (ValueError, AttributeError):
            return "📝 Which note? Use `/del #` (the number shown in /notes)."
        deleted = registry.delete_note(self._conn, ev.platform, ev.external_id,
                                       scenario, position)
        if deleted is None:
            return f"📝 There's no note {position}. `/notes` shows the current list."
        snippet = deleted["text"]
        if len(snippet) > 50:
            snippet = snippet[:47] + "…"
        return f"🗑️ Deleted note {position}: “{snippet}”."

    def _turn(self, pid: str, ev: InboundEvent, text: str) -> Outbound:
        # Phase-first routing (a session may already be OPEN during the Foyer, so
        # the started-flag — not the session object — decides the phase):
        #   not started + a chargen blob          → the FOYER (character creation);
        #   not started, no chargen, no session   → the ATRIUM (Construct dialogue);
        #   not started but a session is open      → in play (an explicit /play);
        #   started                                → in play (resume if not cached).
        if not registry.is_started(self._conn, ev.platform, ev.external_id):
            if registry.get_chargen(self._conn, ev.platform, ev.external_id) is not None:
                return self._foyer(pid, ev, text)
            if pid not in self._sessions:
                return self._atrium(pid, ev, text)
            # else: a session is already open (e.g. via /play) → play it.
        session = self._sessions.get(pid)
        if session is None:
            mode = _valid_mode(registry.get_mode(self._conn, ev.platform, ev.external_id))
            scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
            try:
                session = self._sessions[pid] = self._session_factory(
                    scenario=scenario, player_id=pid, fresh=False, mode_override=mode)
            except Exception as exc:
                logger.exception("auto-open failed for %s", pid)
                return self._reply(ev, f"(could not open your world: {exc})")
        reply = session.turn(text)
        if getattr(reply, "exit_requested", False):
            # The player stepped out of character to ask for a new story / to quit.
            # Confirm before leaving (their next message is the yes/no).
            self._pending_exit.add(pid)
            title = self._title_of(registry.scenario_for(self._conn, ev.platform,
                                                          ev.external_id))
            return self._reply(
                ev, f"Leaving {title} and returning to the start? Your story is "
                    f"saved where you left it — say “yes” to step out, or anything "
                    f"else to stay.")
        prose = reply.prose
        # The time|location header (founder): host-injected atop the reply when the
        # pin is on — read AFTER the turn so it reflects the new moment, and never
        # routed through the narrator (outside the agent's context). It appears ONLY
        # when the line CHANGED from the last one shown (a new time-phase or a new
        # place) — a movement/progression indicator, not wallpaper on every turn.
        if registry.get_status_pin(self._conn, ev.platform, ev.external_id):
            try:
                line = session.status_line()
                last = registry.get_last_status(self._conn, ev.platform, ev.external_id)
                if line and line != last:
                    prose = f"{line}\n\n{prose}"
                    registry.set_last_status(self._conn, ev.platform, ev.external_id, line)
            except Exception:
                logger.exception("status header failed for %s", pid)
        if getattr(reply, "ended", False):
            # CONCLUDE→CONTINUE (founder): the story just landed — always OFFER the next
            # chapter (a dangling thread continues, OR a fresh case finds the now-renowned
            # protagonist). Their next message is the yes/no.
            self._pending_continue.add(pid)
            prose = (prose.rstrip() + "\n\n— — —\nThe case is closed, and word of it will "
                     "travel. **Continue to the next chapter?** (yes / no)")
        return self._reply(ev, prose)

    def _do_continue(self, pid: str, ev: InboundEvent) -> Outbound:
        """CONCLUDE→CONTINUE: author + enter the NEXT episode over the evolved world — the same
        protagonist, their reputation and the prior case's wake carried forward. A real (shorter)
        build; progress streams via the notify channel in narrative phrasing."""
        from construct.game import continue_episode
        scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if not scenario:
            return self._reply(ev, "(there's no story here to continue)")
        self._notify(ev, "Carrying your story forward — a new chapter is being written. It's "
                         "quicker than a fresh world; I'll call out each step.")
        try:
            meta = continue_episode(
                scenario, self._provider(), player_id=pid,
                on_stage=lambda m: self._notify(ev, _humanize_stage(m) or f"· {m}…"))
        except Exception as exc:
            logger.exception("continue_episode failed for %s", pid)
            return self._reply(ev, f"(couldn't carry the story forward: {exc})")
        # Reopen the in-place-advanced slot (NOT a pristine recopy) and render the continuation
        # cold open — the new main arc is read from the plot frame continue_episode just wrote.
        self._sessions.pop(pid, None)
        try:
            session = self._sessions[pid] = self._session_factory(
                scenario=scenario, player_id=pid, fresh=False)
        except Exception as exc:
            logger.exception("reopen after continue failed for %s", pid)
            return self._reply(ev, f"(couldn't open the next chapter: {exc})")
        if meta.get("continuation_intro"):  # per-player, transient — frames this opening only
            try:
                session._meta["continuation_intro"] = meta["continuation_intro"]
            except Exception:
                logger.exception("continuation note injection failed for %s", pid)
        try:
            return self._reply(ev, session.opening())
        except Exception as exc:
            logger.exception("continuation opening failed for %s", pid)
            return self._reply(ev, f"(the next chapter opened, but its scene didn't render: {exc})")

    # -- the Atrium: the Construct dialogue (session-zero over chat) --------
    def _atrium(self, pid: str, ev: InboundEvent, text: str) -> Outbound:
        """One turn of the construct projector-arrival conversation. The Construct talks
        naturally and emits tool calls; on a terminal tool (begin_build /
        pick_world) we open or build the world and enter it."""
        from construct.architect import (
            BUILD, CONTINUE, LOAD, RESUME, ArchitectState, architect_step)

        blob = registry.get_creation(self._conn, ev.platform, ev.external_id)
        if blob is None:
            # Claimed before the dialogue existed (or never greeted) — greet now;
            # the next message starts the conversation.
            registry.set_creation(self._conn, ev.platform, ev.external_id,
                                  _empty_creation())
            return self._reply(ev, GREETING)

        history_list = list(blob.get("history") or [])
        state = ArchitectState.from_dict(blob.get("state"))
        # The library the guest may pick_world: the curated ready-mades (by title),
        # plus whatever world they're currently pointed at (e.g. one they built).
        catalog = self._catalog()
        granted = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if granted and granted not in catalog:
            catalog[granted] = granted
        worlds = list(catalog)
        resumable = self._resumable(ev)
        try:
            result = architect_step(self._provider(), state, "\n".join(history_list[-12:]),
                                    text, worlds, resumable=resumable, catalog=catalog)
        except Exception:
            logger.exception("architect step failed for %s", pid)
            return self._reply(ev, "(the Construct flickered for a moment — say that again?)")

        history_list += [f"GUEST: {text}", f"CONSTRUCT: {result.reply}"]
        if result.outcome == CONTINUE:
            registry.set_creation(self._conn, ev.platform, ev.external_id,
                                  {"history": history_list, "state": state.to_dict()})
            reply = result.reply
            if result.show_library:
                menu = self._world_menu(resumable)
                if menu:
                    reply = f"{reply}\n\n{menu}" if reply else menu
            return self._reply(ev, reply)
        if result.outcome == LOAD and result.world:
            return self._enter_world(pid, ev, scenario=result.world, mode=None,
                                     preamble=result.reply)
        if result.outcome == RESUME and result.world:
            # Reopen the saved game where they left off (not a fresh copy).
            mode = _valid_mode(registry.get_mode(self._conn, ev.platform, ev.external_id))
            return self._enter_world(pid, ev, scenario=result.world, mode=mode,
                                     preamble=result.reply, fresh=False)
        if result.outcome == BUILD:
            return self._build_and_enter(pid, ev, result.brief or {}, result.reply)
        # No terminal world (shouldn't happen) — keep the dialogue alive.
        registry.set_creation(self._conn, ev.platform, ev.external_id,
                              {"history": history_list, "state": state.to_dict()})
        return self._reply(ev, result.reply)

    def _resumable(self, ev: InboundEvent) -> str:
        """The world the guest has a saved game in (a play slot exists), or ""
        — what the architect's `resume` tool may reopen."""
        try:
            from construct.game import slot_path
            scen = registry.scenario_for(self._conn, ev.platform, ev.external_id)
            pid = registry.player_id_for(ev.platform, ev.external_id)
            if scen and slot_path(scen, pid).exists():
                return scen
        except Exception:
            logger.exception("resumable check failed")
        return ""

    def _enter_world(self, pid: str, ev: InboundEvent, *, scenario: str,
                     mode: str | None, preamble: str, fresh: bool = True) -> Outbound:
        """Open `scenario` for the player (fresh copy, or resume the slot when
        fresh=False). A FRESH entry hands off to the FOYER (character creation)
        before turn one; a RESUME goes straight back into the story. The Atrium
        state is cleared either way."""
        try:
            session = self._sessions[pid] = self._session_factory(
                scenario=scenario, player_id=pid, fresh=fresh, mode_override=mode)
        except Exception as exc:
            logger.exception("enter-world failed for %s", pid)
            return self._reply(ev, f"(could not open your world: {exc})")
        if mode:
            registry.set_mode(self._conn, ev.platform, ev.external_id, mode)
        # Repoint the player at the world they entered, so /resume finds it.
        registry.set_scenario(self._conn, ev.platform, ev.external_id, scenario)
        registry.clear_creation(self._conn, ev.platform, ev.external_id)

        # Fresh entry → the Foyer (CHARACTER-CREATION.md): settle WHO before turn
        # one. Resume (or a session that can't describe its protagonist) skips it.
        if fresh:
            setup = None
            try:
                setup = session.character_setup()
            except Exception:
                logger.exception("character_setup failed for %s", pid)
            if setup and setup.get("role"):
                return self._begin_foyer(ev, setup, preamble)

        registry.mark_started(self._conn, ev.platform, ev.external_id)
        registry.clear_chargen(self._conn, ev.platform, ev.external_id)
        opening = session.opening()
        return self._reply(ev, f"{preamble}\n\n{opening}" if preamble else opening)

    # -- the Foyer: character creation, the WHO phase before turn one --------
    def _begin_foyer(self, ev: InboundEvent, setup: dict, preamble: str) -> Outbound:
        """Open the Foyer: seed the chargen state and speak the Construct's
        role-introduction. The player's next messages shape their character."""
        try:
            from construct.foyer import foyer_open
            intro = foyer_open(self._provider(), role=setup.get("role", ""),
                               anchors=setup.get("anchors") or [],
                               defaults=setup.get("defaults") or {},
                               theme=setup.get("theme", ""),
                               world_brief=setup.get("world_brief", ""))
        except Exception:
            logger.exception("foyer open failed for %s", ev.external_id)
            intro = ("Before you step in — who are you in this story? Tell me your "
                     "name, or anything you'd like to settle, and say when you're ready.")
        registry.set_chargen(self._conn, ev.platform, ev.external_id,
                             {"history": [f"CONSTRUCT: {intro}"], "sheet": {},
                              "setup": setup})
        return self._reply(ev, f"{preamble}\n\n{intro}" if preamble else intro)

    def _foyer(self, pid: str, ev: InboundEvent, text: str) -> Outbound:
        """One turn of the Foyer. The Construct shapes the character with the
        player; on `done` it ingests the sheet as canon and opens the story."""
        from construct.foyer import CharacterSheet, foyer_step

        blob = registry.get_chargen(self._conn, ev.platform, ev.external_id)
        if blob is None:  # defensive — routing guarantees it's present
            return self._atrium(pid, ev, text)
        setup = blob.get("setup") or {}
        sheet = CharacterSheet.from_dict(blob.get("sheet"))
        history = list(blob.get("history") or [])

        session = self._sessions.get(pid)
        if session is None:
            # Re-open after a restart (the world slot persists; resume it).
            mode = _valid_mode(registry.get_mode(self._conn, ev.platform, ev.external_id))
            scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
            try:
                session = self._sessions[pid] = self._session_factory(
                    scenario=scenario, player_id=pid, fresh=False, mode_override=mode)
            except Exception as exc:
                logger.exception("foyer re-open failed for %s", pid)
                return self._reply(ev, f"(could not reopen your world: {exc})")

        try:
            result = foyer_step(self._provider(), sheet, "\n".join(history[-12:]),
                                text, role=setup.get("role", ""),
                                anchors=setup.get("anchors") or [],
                                defaults=setup.get("defaults") or {},
                                theme=setup.get("theme", ""),
                                world_brief=setup.get("world_brief", ""))
        except Exception:
            logger.exception("foyer step failed for %s", pid)
            return self._reply(ev, "(the Construct paused a moment — say that again?)")

        history += [f"GUEST: {text}", f"CONSTRUCT: {result.reply}"]
        if not result.done:
            registry.set_chargen(self._conn, ev.platform, ev.external_id,
                                 {"history": history, "sheet": sheet.to_dict(),
                                  "setup": setup})
            return self._reply(ev, result.reply)

        # Ready → ingest the character as canon, then open the story.
        try:
            session.apply_character(sheet)
        except Exception:
            logger.exception("apply_character failed for %s (continuing)", pid)
        # Persist the finished sheet durably (for /restart "keep my character")
        # and checkpoint the now-playable world as this episode's start, so
        # /restart "this episode" can roll back here without re-running the Foyer.
        registry.set_character(self._conn, ev.platform, ev.external_id, sheet.to_dict())
        self._checkpoint_episode(ev, pid)
        registry.mark_started(self._conn, ev.platform, ev.external_id)
        registry.clear_chargen(self._conn, ev.platform, ev.external_id)
        registry.clear_creation(self._conn, ev.platform, ev.external_id)
        opening = session.opening()
        return self._reply(ev, f"{result.reply}\n\n{opening}")

    def _checkpoint_episode(self, ev: InboundEvent, pid: str) -> None:
        """Snapshot the player's current slot as this episode's start checkpoint —
        the playable, character-applied opening state. Best-effort; never sinks a
        turn. See docs/design/EPISODIC-CONTINUATION.md."""
        try:
            from construct.game import checkpoint_episode_start
            scen = registry.scenario_for(self._conn, ev.platform, ev.external_id)
            if scen:
                checkpoint_episode_start(scen, pid)
        except Exception:
            logger.exception("episode checkpoint failed for %s", pid)

    def _build_and_enter(self, pid: str, ev: InboundEvent, brief: dict,
                         preamble: str) -> Outbound:
        """Run the long generate-then-ingest for the assembled brief, streaming
        per-phase progress via the notify channel (the chat does not sit empty),
        then enter the freshly-built world. On failure, stay in the Atrium."""
        from construct.game import scenario_path, slot_path
        # Each build ADDS a world to the (shared) library — a unique name per build, so a
        # player accumulates a collection instead of clobbering their one world (founder).
        base = f"live_{_safe(ev.platform)}_{_safe(ev.external_id)}"
        name, _n = f"{base}_1", 1
        while scenario_path(name).exists():
            _n += 1
            name = f"{base}_{_n}"
        self._notify(ev, preamble)
        self._notify(ev, BUILD_HEADS_UP)

        progress = _StageProgress()  # overall [k/N] across the build's phases

        def on_stage(msg: str) -> None:
            line = progress.line(msg)
            if line:
                self._notify(ev, line)

        try:
            slot = slot_path(name, pid)
            if slot.exists():
                slot.unlink()  # fresh name → paranoia only
            self._build(name=name, provider=self._provider(),
                        seed=brief.get("premise", ""),
                        endless=brief.get("mode") != "win_loss",
                        win_direction=brief.get("win_direction", ""),
                        play_as=brief.get("play_as", ""),
                        game_types=brief.get("game_types") or [],
                        on_stage=on_stage)
        except Exception as exc:
            logger.exception("build failed for %s", pid)
            return self._reply(
                ev, f"(I couldn't quite stabilize that world — {exc}. Tell me what "
                    f"to change, or we can try again.)")
        registry.set_scenario(self._conn, ev.platform, ev.external_id, name)
        self._notify(ev, "Your world is ready. Let's settle who you are in it…")
        return self._enter_world(pid, ev, scenario=name,
                                 mode=brief.get("mode"), preamble="")

    def _notify(self, ev: InboundEvent, text: str) -> None:
        """Send an interim message NOW (outside the one-reply turn) — best-effort,
        chunked. A dropped progress ping must never sink the build."""
        if not (self._notify_fn and text):
            return
        for piece in chunk(text, self._limit):
            try:
                self._notify_fn(ev.chat_id, piece)
            except Exception:
                logger.exception("notify failed for %s", ev.external_id)

    def _reply(self, ev: InboundEvent, text: str) -> Outbound:
        return Outbound(chat_id=ev.chat_id, chunks=chunk(text, self._limit))

    # -- transcript + /dump ------------------------------------------------
    def _transcript_path(self, ev: InboundEvent) -> Path:
        import re
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", ev.external_id).strip("_") or "player"
        return self._log_dir / f"{ev.platform}_{safe}.log"

    def _log(self, ev: InboundEvent, role: str, text: str) -> None:
        """Append one line to the player's live transcript. Best-effort — a
        logging failure must never sink a turn."""
        try:
            path = self._transcript_path(ev)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as fh:
                fh.write(f"{role}: {text}\n\n")
        except Exception:
            logger.exception("transcript write failed for %s", ev.external_id)

    def _dump(self, ev: InboundEvent) -> str:
        """`/dump`: report the on-disk transcript (the running chat history,
        in a gitignored location) so the operator can read it."""
        path = self._transcript_path(ev)
        exchanges = 0
        if path.exists():
            exchanges = sum(1 for ln in path.read_text().splitlines() if ln.startswith("USER:"))
        return f"Transcript: {path.resolve()} ({exchanges} exchanges so far)."

    # -- /feedback: a live note + recent turns, dropped into the operator inbox
    def _recent_transcript(self, ev: InboundEvent, *, exchanges: int = 6) -> str:
        """The last `exchanges` USER/BOT pairs from this player's transcript,
        as a readable block. Best-effort; empty string if nothing logged yet."""
        path = self._transcript_path(ev)
        if not path.exists():
            return ""
        try:
            # Records are written as "ROLE: text\n\n" — split on the blank line.
            records = [r.strip() for r in path.read_text().split("\n\n") if r.strip()]
        except Exception:
            logger.exception("transcript read failed for %s", ev.external_id)
            return ""
        return "\n\n".join(records[-(exchanges * 2):])

    def _feedback(self, ev: InboundEvent, note: str) -> str:
        """`/feedback <note>`: bundle the player's note with a snippet of the
        last few turns and drop it into the operator's dev inbox, so a problem
        flagged mid-play can be picked up and fixed without leaving the session
        (founder ask). Best-effort: a write failure tells the player plainly."""
        note = (note or "").strip()
        if not note:
            return ("Add your note after the command — e.g. "
                    "/feedback the opening felt flat and ignored my name.")
        snippet = self._recent_transcript(ev)
        try:
            path = self._write_feedback(ev, note, snippet)
        except Exception as exc:
            logger.exception("feedback write failed for %s", ev.external_id)
            return f"(couldn't record that feedback: {exc})"
        logger.info("feedback from %s recorded at %s", ev.external_id, path)
        return ("Got it — flagged to the operator with the last few turns "
                "attached. Thanks; I'll take a look. Carry on whenever "
                "you're ready.")

    def _write_feedback(self, ev: InboundEvent, note: str, snippet: str) -> Path:
        """Write one feedback letter into the dev inbox. Filename is sortable +
        unique per (player, count) so rapid notes never clobber each other."""
        from datetime import datetime, timezone

        d = self._feedback_dir
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        import re
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", ev.external_id).strip("_") or "player"
        # Disambiguate same-second notes from the same player.
        n = sum(1 for _ in d.glob(f"feedback-{ts}-{safe}*.md"))
        suffix = f"-{n}" if n else ""
        path = d / f"feedback-{ts}-{safe}{suffix}.md"
        body = (
            f"# Live feedback — {ev.platform}:{ev.external_id}\n\n"
            f"**When:** {ts}\n\n"
            f"## Note\n\n{note}\n\n"
            f"## Last few turns\n\n"
            f"{snippet or '(no transcript yet)'}\n")
        path.write_text(body)
        return path


def _extract_code(text: str) -> str | None:
    """Pull a `CONS-…` code out of a message (case-insensitive, first token
    that looks like one). Returns the canonical upper-cased code or None."""
    for tok in text.replace("\n", " ").split():
        if tok.upper().startswith("CONS-") and len(tok) > 6:
            return tok.upper()
    return None


#: Keyword cues for the session-zero mode interview. A brand-new player's first
#: message is read into a mode. We bias to a CONCLUSIVE story only on a clear
#: ending-signal; everything ambiguous falls to freeplay (the safe default —
#: a story can't be forced on someone who didn't ask for stakes).
_WIN_LOSS_CUES = (
    "end", "ending", "win", "won", "lose", "lost", "stakes", "goal", "finish",
    "conclu", "victory", "defeat", "story", "climax", "quest", "beat the",
    "complete", "objective", "mission",
)
_ENDLESS_CUES = (
    "free", "freeplay", "explore", "roam", "wander", "sandbox", "endless",
    "open-ended", "open ended", "no win", "no end", "just live", "no stakes",
    "no goal",
)


#: Onboarding sentinel stored in the registry `mode` column: "the mode question
#: has been shown; the player's next message is the answer." Never reaches a
#: Session (normalized away by `_valid_mode`).
_ASKING = "__asking__"
#: The concrete modes a Session understands.
_MODES = ("win_loss", "endless")


def _valid_mode(mode: str | None) -> str | None:
    """Normalize a stored mode for `Session.open(mode_override=…)`: a real mode
    passes through; the onboarding sentinel / anything unknown → None (let the
    scenario's authored default stand)."""
    return mode if mode in _MODES else None


def _interpret_mode(text: str) -> str:
    """Read a player's free-text first message into a scenario mode. Returns
    "win_loss" only on a clear ending-signal; "endless" otherwise (the safe
    default — see `MODE_PROMPT`). Endless cues win an explicit tie (a request
    to roam should never be overridden into forced stakes)."""
    low = (text or "").lower()
    if any(cue in low for cue in _ENDLESS_CUES):
        return "endless"
    if any(cue in low for cue in _WIN_LOSS_CUES):
        return "win_loss"
    return "endless"


def _default_session_factory(*, scenario: str, player_id: str, fresh: bool,
                             mode_override: str | None = None):
    from construct import Session
    return Session.open(scenario, player_id=player_id, fresh=fresh,
                        mode_override=mode_override)


# -- the Atrium (Construct dialogue) helpers -------------------------------

def _empty_creation() -> dict:
    """A fresh, greeted-but-not-yet-conversing Atrium state."""
    return {"history": [], "state": {}}


def _logline(scenario: dict) -> str:
    """A one-line hook for a library world, from its ingest-time meta — the first
    sentence of the description/intro, else the theme. Empty if nothing usable."""
    text = (scenario.get("description") or scenario.get("intro")
            or scenario.get("theme") or "").strip().replace("\n", " ")
    if not text:
        return ""
    # First sentence (bounded), so the catalog stays a clean one-liner.
    import re
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return (first[:157] + "…") if len(first) > 158 else first


#: Genre/title keyword → a single leading emoji for the world menu (first match
#: wins; a generic globe otherwise). Tasteful, not a zoo (founder).
_GENRE_EMOJI = (
    (("noir", "mystery", "detective", "whodunnit"), "🕵️"),
    (("harbor", "naval", "sea", "berth", "ship", "port"), "⚓"),
    (("winter", "frost", "snow", "ice", "ashenpeak"), "❄️"),
    (("gothic", "horror", "haunt", "ghost"), "🕯️"),
    (("romance", "romantic"), "💞"),
    (("political", "intrigue", "bureaucratic", "bureau"), "⚖️"),
    (("heist", "thief"), "💎"),
    (("western",), "🤠"),
    (("war", "military", "battle"), "⚔️"),
    (("dark", "blight", "grim"), "🌑"),
    (("fantasy", "quest", "dragon", "magic", "myth", "eldervale"), "🗡️"),
    (("sci-fi", "science fiction", "space", "station", "future", "cyber"), "🛸"),
    (("survival", "thriller", "disaster", "colonial"), "🪨"),
)


def _genre_emoji(genre: str, title: str = "") -> str:
    """Pick a leading emoji — the authored GENRE drives it; the title is only a
    fallback (so a 'fantasy quest' titled *Frost Tongue* reads 🗡️, not ❄️)."""
    for hay in (genre.lower(), title.lower()):
        if not hay:
            continue
        for keys, emoji in _GENRE_EMOJI:
            if any(k in hay for k in keys):
                return emoji
    return "🌍"


def _safe(s: str) -> str:
    """Filesystem-safe scenario-name segment; never empty."""
    import re
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s or "").strip("_") or "x"


#: Raw build stage line (substring) → the warm, player-facing progress line we
#: stream during a build. Lines with no mapping are internal and stay silent
#: (the per-chunk "extracted" lines are collapsed into one rolling counter).
_STAGE_LINES = (
    ("Authoring the hidden source story", "· Authoring the source story…"),
    ("Ingesting prose", "· Ingesting it into the pattern-buffer…"),
    ("Reconciling identity", "· Reconciling identities (coreference)…"),
    ("Declaring passability", "· Recording how the places connect…"),
    ("Authoring the hidden arc", "· Weaving the hidden arc into a private frame…"),
    ("Seeding character knowledge", "· Seeding each character's knowledge frame…"),
    ("thematic introduction", "· Composing your way in…"),
    ("back-of-the-book premise", "· Composing your way in…"),
    # The build's LONGEST stage (~most of the wall-clock — hundreds of serial classify calls):
    # surface it so the player isn't left staring at one line through the silent bottleneck.
    ("Classifying durability", "· Classifying what's durable vs. fleeting…"),
    ("Distilling narrative flavor", "· Distilling tone & texture…"),
    ("Sealing the scenario", "· Sealing the world snapshot…"),
    ("Viability gate", "· Final checks before the doors open…"),
)


def _humanize_stage(msg: str) -> str | None:
    """Turn a raw `game._emit` stage line into a warm progress ping, or None to
    stay silent (internal steps / noise). The per-chunk extraction lines all
    collapse to ONE populating phase (so they don't spam, and so the overall
    counter advances by phase, not by chunk)."""
    import re
    text = (msg or "").strip()
    if re.search(r"chunk (\d+)/(\d+) extracted", text):
        return "· Entering people, places & things into the pattern-buffer…"
    for needle, line in _STAGE_LINES:
        if needle in text:
            return line
    return None


#: How many distinct phases the full build streams — the overall `[k/N]`
#: denominator. Numbering is by first appearance (robust to emission order), and
#: not every build hits all of them, so the bar may finish a step or two short.
_BUILD_STEP_TOTAL = len({line for _, line in _STAGE_LINES})


class _StageProgress:
    """Per-build OVERALL-completion numbering. Each DISTINCT humanized phase
    advances a `[k/N]` counter shown on every progress line, so the player sees
    progress toward the whole build rather than a phase-local fraction (founder).
    A repeated phase — chiefly the populating chunks, which collapse to one line —
    is shown once and never re-advances or re-emits."""

    def __init__(self, total: int = _BUILD_STEP_TOTAL) -> None:
        self._total = max(total, 1)
        self._seen: set[str] = set()
        self._step = 0

    def line(self, msg: str) -> str | None:
        base = _humanize_stage(msg)
        if not base or base in self._seen:
            return None  # internal/noise, or a phase already shown (no spam)
        self._seen.add(base)
        self._step = min(self._step + 1, self._total)
        body = base[2:] if base.startswith("· ") else base
        return f"· [{self._step}/{self._total}] {body}"
