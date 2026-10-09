"""The turn relay: routing an in-play message to the session, the reply and
interim-notify channels, and scene/opening image delivery."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from construct import registry
from construct.transport.events import InboundEvent, Outbound, chunk
from construct.transport.helpers import _core_module, _valid_mode
from construct.transport.messages import OPENING_HEADS_UP
from construct.transport.prompts import PENDING_CONTINUE, PENDING_EXIT

logger = logging.getLogger("construct.transport_core")  # one logger name, as before the split


class RelayMixin:
    """In-play turn routing, replies and image delivery."""

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
            self._arm(pid, PENDING_EXIT)
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
            if not getattr(reply, "can_continue", True):
                # #95 (Cx 422): a DEATH terminal is the end of this world's story — no
                # next-chapter arm, no "the story goes on". The testament was the close.
                prose = (prose.rstrip() + "\n\n— — —\n**— The End —**\n"
                         "This story rests here. /exit returns to the menu whenever "
                         "you're ready.")
            else:
                # CONCLUDE→CONTINUE (founder 2026-07-02: "should just say 'End Chapter #' and
                # continue automatically — the player can quit whenever they want"): announce the
                # chapter's END; the player's next in-fiction message ROLLS INTO the next chapter
                # (no yes/no gate). /exit (or any command) still works as itself.
                self._arm(pid, PENDING_CONTINUE)
                prose = (prose.rstrip() + "\n\n— — —\n**— End of Chapter —**\nThe story goes on: "
                         "say anything to begin the next chapter, or /exit to rest here.")
        self._deliver_scene_image(ev, pid)
        return self._reply(ev, prose)

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

    def _deliver_scene_image(self, ev: InboundEvent, pid: str) -> None:
        """SCENE-IMAGERY: show a fresh location's picture JUST BEFORE its prose
        (founder's layout: image → new-scene text). The render was started in
        parallel during the turn (Session `on_scene`), so here we only join it
        (bounded) and send the photo NOW — before the text reply is returned, so the
        image lands first. A same-location turn has no pending render → nothing sent,
        so the conversation stays text-only until the scene actually moves."""
        if self._photo_fn is None:
            return
        session = self._sessions.get(pid)
        if session is None:
            return
        try:
            holder = session.take_pending_image()  # the {rec, done} render holder, or None
        except Exception:
            logger.exception("scene-image take failed for %s", pid)
            return
        if not holder:
            return
        rec = holder.get("rec")
        if not (rec and getattr(rec, "asset_path", "")):
            return
        chat_id, done, path = ev.chat_id, holder.get("done"), rec.asset_path

        def _send_if_landed(caption: str = "") -> bool:
            if Path(path).exists():
                try:
                    self._photo_fn(chat_id, path, caption)
                    return True
                except Exception:
                    logger.exception("scene-image send failed for %s", pid)
            return False

        # SHORT join for the ideal "image → new-scene prose" layout; the render had the whole
        # turn to cook, so this usually catches it. Never block the text reply on a slow one.
        if done is None or done.wait(_core_module().IMAGE_BEFORE_TEXT_S):
            _send_if_landed()       # rides right before the prose → no caption needed
            return
        # Not ready quickly → ship the text now, send the picture LATE when it finishes (instead
        # of dropping it). Daemon thread; touches no PB, only the photo sink. Caption it with the
        # scene name (Cx 284) since it arrives AFTER the text, out of the image→prose order.
        scene_name = str(getattr(rec, "place_name", "") or "")

        def _late() -> None:
            if done.wait(_core_module().IMAGE_LATE_S):
                _send_if_landed(scene_name)
        threading.Thread(target=_late, daemon=True, name="scene-image-late").start()

    def _opening_reply(self, ev: InboundEvent, pid: str, session: Any,
                       *, preamble: str = "") -> Outbound:
        """Deliver a cold open in the founder's layout: the FRAMING (title + premise)
        first, THEN the location picture, THEN the localized room narration — so the
        painting introduces the room before the prose walks you in. Falls back to one
        combined message when there's no picture (no backend / not ready / no sink)."""
        # PLEASE-WAIT ON EVERY OPENING PATH (founder 2026-07-02): the opening render
        # (staging + narrator + picture) runs long and used to leave SOME entry paths
        # silent (saved-character restart, continuation). The heads-up lives HERE so
        # every road to an opening announces itself. Best-effort; never logged as a turn.
        self._notify(ev, OPENING_HEADS_UP)
        try:
            framing, scene = session.opening_parts()
        except Exception:
            logger.exception("opening_parts failed for %s", pid)
            try:
                return self._reply(ev, ((preamble + "\n\n") if preamble else "") + session.opening())
            except Exception:
                return self._reply(ev, preamble or "(the scene didn't render)")
        head = "\n\n".join(p for p in (preamble, framing) if p)
        rec = None
        if self._photo_fn is not None:
            try:
                rec = session.pending_image()  # join the render started by opening_parts
            except Exception:
                logger.exception("opening image join failed for %s", pid)
        have_image = bool(rec and getattr(rec, "asset_path", "")
                          and Path(rec.asset_path).exists())
        if have_image and scene:
            if head:
                self._notify(ev, head)                  # message 1: framing
            self._photo_fn(ev.chat_id, rec.asset_path, "")  # the location picture
            return self._reply(ev, scene)               # message 2: the room
        if have_image:  # picture but no separate room narration → picture then framing
            self._photo_fn(ev.chat_id, rec.asset_path, "")
            return self._reply(ev, head)
        return self._reply(ev, "\n\n".join(p for p in (head, scene) if p))
