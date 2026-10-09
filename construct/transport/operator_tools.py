"""Operator tools: `/wipe`, `/disconnect`, `/reboot`, the transcript, `/dump`
and `/feedback`."""

from __future__ import annotations

import logging
from pathlib import Path

from construct import registry
from construct.text import file_safe
from construct.transport.events import InboundEvent
from construct.transport.helpers import _core_module, _safe

logger = logging.getLogger("construct.transport_core")  # one logger name, as before the split


class OperatorMixin:
    """Hidden operator commands and the transcript/feedback files."""

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
        self._clear_pending(pid)
        self._ooc_pressed.discard(pid)
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
                       ev.platform, ev.external_id, _core_module().REBOOT_DELAY_S, sys.orig_argv)

        def _exec() -> None:
            time.sleep(_core_module().REBOOT_DELAY_S)
            try:
                os.execv(sys.orig_argv[0], sys.orig_argv)
            except Exception:
                logger.exception("/reboot re-exec failed; staying on current code")

        self._reboot_thread = threading.Thread(target=_exec, daemon=True, name="reboot")
        self._reboot_thread.start()
        return ("♻️ Rebooting the Construct — reloading the latest code. Give me a few "
                "seconds, then send any message (e.g. “new”, “list”, or /help).")

    # -- transcript + /dump ------------------------------------------------
    def _transcript_path(self, ev: InboundEvent) -> Path:
        safe = file_safe(ev.external_id) or "player"
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
        safe = file_safe(ev.external_id) or "player"
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
