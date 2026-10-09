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
import threading  # noqa: F401  (kept importable; the mixins use their own)
import time  # noqa: F401  (tests patch `transport_core.time.sleep`)
from pathlib import Path
from typing import Any, Callable

from construct import registry
from construct.transport.atrium import AtriumMixin
from construct.transport.commands import CommandsMixin
from construct.transport.events import InboundEvent, Outbound, chunk  # noqa: F401
from construct.transport.foyer_flow import FoyerMixin
from construct.transport.helpers import (  # noqa: F401
    _ASKING, _MODES, _empty_creation, _extract_code, _safe, _valid_mode)
from construct.transport.lifecycle import LifecycleMixin
from construct.transport.messages import (  # noqa: F401
    BUILD_HEADS_UP, BUILD_RETRY_DELAY_S, GREETING, HELP, OPENING_HEADS_UP, STATIC_REJECT,
    WELCOME_IMAGE)
from construct.transport.operator_tools import OperatorMixin
from construct.transport.prompts import (  # noqa: F401
    _CANCEL_WORDS, _RESTART_STEPS, PENDING_CONTINUE, PENDING_EXIT, PENDING_RESTART_CHARACTER,
    PENDING_RESTART_DEPTH, PENDING_RESTART_NOTES, Pending, PendingMixin, _affirmative, _pick)
from construct.transport.relay import RelayMixin
from construct.transport.shelf import (  # noqa: F401
    ShelfMixin, _GENRE_EMOJI, _genre_emoji, _logline, _resolve_removal, _styles_wall)
from construct.transport.stages import (  # noqa: F401
    _BUILD_STEP_TOTAL, _STAGE_LINES, _humanize_stage, _StageProgress)

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

#: SCENE-IMAGERY delivery (founder image fix). The render started DURING the turn (it has had the
#: whole turn to cook), so a short post-turn join catches the common case and shows the picture
#: BEFORE the new-scene prose — without blocking the text reply on a slow render. If it isn't ready
#: in `IMAGE_BEFORE_TEXT_S`, the text ships now and the picture is sent LATE (a follow-up photo) when
#: the render finishes within `IMAGE_LATE_S`, instead of being dropped. Module-level so tests tune them.
IMAGE_BEFORE_TEXT_S = 12.0
IMAGE_LATE_S = 180.0


class TransportCore(PendingMixin, ShelfMixin, OperatorMixin, LifecycleMixin,
                    CommandsMixin, AtriumMixin, FoyerMixin, RelayMixin):
    """One per running transport. Holds the open sessions keyed by player_id;
    routing is synchronous (the adapter serializes per-player by handing
    events one at a time).

    The class is assembled from the mixins in `construct.transport.*` (one per
    seam: pending prompts, the shelf, operator tools, lifecycle, commands, the
    Atrium/start menu, the Foyer, the turn relay); this file keeps the
    constructor and the `handle` precedence."""

    def __init__(self, conn, *, platform: str, msg_limit: int,
                 session_factory: Callable[..., Any] | None = None,
                 log_dir: Path | str | None = None,
                 feedback_dir: Path | str | None = None,
                 provider: Any | None = None,
                 builder: Callable[..., Any] | None = None,
                 notify: Callable[[str, str], None] | None = None,
                 photo: Callable[[str, str, str], None] | None = None) -> None:
        self._conn = conn
        self._platform = platform
        self._limit = msg_limit
        self._sessions: dict[str, Any] = {}
        # Armed prompts: pid -> {kind: Pending}. Prompts of different kinds CAN be armed
        # together (a command passes through an armed prompt and leaves it, so e.g. the
        # chapter-end continue plus a /restart wizard step, or /ooc's exit confirm);
        # `handle` consults them in a fixed precedence. The restart steps are exclusive.
        self._pending: dict[str, dict[str, Pending]] = {}
        # Players whose last /ooc was a plot-protective deflection — a renewed push
        # escalates (honesty + offer a new scenario). An escalation flag, not a prompt.
        self._ooc_pressed: set[str] = set()
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
        # SCENE-IMAGERY: a (chat_id, image_path, caption) sink for delivering a fresh
        # location's picture OUT OF BAND (after the text, when the parallel render is
        # done). Injected by the transport adapter; no-op (text-only) when absent.
        self._photo_fn = photo

    def _provider(self) -> Any:
        if self._provider_obj is None:
            from construct.provider import default_provider
            self._provider_obj = default_provider()
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
        # FINALIZATION BARRIER (TURN-LATENCY dumbfire, Cx 266 #2): before routing ANY event —
        # a turn, a command that reads the session (/status, /note), or one that
        # replaces/drops it (/restart, /wipe, /play, continue) — drain any prior turn's
        # pending settle. The adapter normally already ran it post-send; this guarantees no
        # command can read stale state or discard a session while its finalizer is pending
        # (covers the outbox-recovery path that delivers a reply without settling). Idempotent.
        _open = self._sessions.get(pid)
        if _open is not None:
            _open.flush_settle()
        # A live, readable transcript per player (USER/BOT lines) — written to
        # the gitignored log dir. /dump snapshots it on demand (operator ask).
        self._log(ev, "USER", ev.text)
        low = text.lower()
        # The /restart confirm steps are DESTRUCTIVE: only an exact choice answers
        # them. A COMMAND passes through (falls to command routing below) and leaves
        # the prompt armed; an ambiguous answer is re-asked by the step's handler,
        # which owns its own state (it disarms only on a decision).
        if not low.startswith("/"):
            for kind, step in ((PENDING_RESTART_NOTES, self._do_restart_notes),
                               (PENDING_RESTART_CHARACTER, self._do_restart_original),
                               (PENDING_RESTART_DEPTH, self._do_restart)):
                if self._peek(pid, kind):
                    out = step(pid, ev, low)  # already an Outbound
                    self._log(ev, "BOT", "\n".join(out.chunks))
                    return out
        if self._peek(pid, PENDING_CONTINUE):
            # CONCLUDE→CONTINUE (founder 2026-07-02, auto-continue): the story ended; any
            # in-fiction message ROLLS INTO the next chapter. COMMANDS PASS THROUGH and keep
            # the state armed (live bug: a /feedback here was swallowed as a "no" and ended
            # the founder's story). An explicit decline ("no"/"stop"/"quit") still rests it.
            if low.startswith("/"):
                pass  # fall through to command routing below; next chapter stays offered
            elif low.strip() in ("no", "stop", "quit", "rest", "not now", "no thanks"):
                self._disarm(pid, PENDING_CONTINUE)
                out = self._reply(ev, "Then the story rests here — a good place to leave it. "
                                      "Say /restart to play again, or start something new anytime.")
                self._log(ev, "BOT", "\n".join(out.chunks))
                return out
            else:
                self._disarm(pid, PENDING_CONTINUE)
                out = self._do_continue(pid, ev)
                self._log(ev, "BOT", "\n".join(out.chunks))
                return out
        if self._peek(pid, PENDING_EXIT):
            # The player asked (out of character) to leave/start over; this message
            # is their yes/no. Affirm → step out; anything else → carry on.
            self._disarm(pid, PENDING_EXIT)
            if _affirmative(low):
                out = self._reply(ev, self._exit(pid, ev))
            else:
                out = self._reply(ev, "Alright — staying in the story. Carry on.")
        elif low == "/restart" or low.startswith("/play"):
            # /play was a silent fresh-open that ERASED a run with no confirmation —
            # the unsafe twin of /restart (founder audit 2026-07-05). Merged: with no
            # saved progress they open fresh at once; with a save, the guided
            # confirmation flow decides how far back.
            if low.startswith("/play") and not self._resumable(ev):
                # legacy /play with nothing saved: open fresh at once (nothing to
                # protect). /restart ALWAYS runs the guided flow — keep/redo is
                # meaningful even before a slot exists.
                out = self._reply(ev, self._command(pid, ev, "/play", now=now))
                self._log(ev, "BOT", "\n".join(out.chunks))
                return out
            title = self._title_of(registry.scenario_for(self._conn, ev.platform,
                                                          ev.external_id))
            # A fresh /restart supersedes any half-answered earlier one.
            for step in _RESTART_STEPS:
                self._disarm(pid, step)
            if self._in_episodes(pid, ev):
                # Multi-episode playthrough → the two depths are meaningful.
                self._arm(pid, PENDING_RESTART_DEPTH)
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
                self._arm(pid, PENDING_RESTART_CHARACTER)
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

    def settle(self, ev: InboundEvent) -> None:
        """Run the just-played turn's DEFERRED bookkeeping (TURN-LATENCY dumbfire), AFTER
        the reply has been sent. The adapter calls this immediately post-send so the PB
        writes (extract→canon, mirror, transcript, compact, time) overlap the player's
        reading instead of padding the wait. A no-op when there is no open play session or
        nothing is pending; the next turn's start-of-turn join is the correctness backstop,
        so this is purely the latency win. Never raises (the session swallows settle errors)."""
        pid = registry.player_for(self._conn, ev.platform, ev.external_id)
        if pid is None:
            return
        session = self._sessions.get(pid)
        if session is not None:
            session.flush_settle()


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
