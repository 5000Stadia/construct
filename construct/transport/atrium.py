"""The start menu: the invite gate, the Atrium dialogue, entering a world, and
the build-and-enter flow."""

from __future__ import annotations

import logging
import time

from construct import registry
from construct.transport.events import InboundEvent, Outbound
from construct.transport.helpers import _empty_creation, _extract_code, _safe, _valid_mode
from construct.transport.messages import (
    BUILD_HEADS_UP, BUILD_RETRY_DELAY_S, GREETING, STATIC_REJECT, WELCOME_IMAGE)
from construct.transport.shelf import _styles_wall
from construct.transport.stages import _StageProgress

logger = logging.getLogger("construct.transport_core")  # one logger name, as before the split


class AtriumMixin:
    """Gate, Atrium dialogue, world entry and build."""

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
                return self._greeting_reply(ev)
        return self._reply(ev, STATIC_REJECT)  # uniform; never leaks the reason

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
            return self._greeting_reply(ev)

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
                menu = self._world_menu(
                    resumable, viewer=f"live_{ev.platform}_{ev.external_id}_")
                if menu:
                    reply = f"{reply}\n\n{menu}" if reply else menu
            if getattr(result, "show_styles", False):
                wall = _styles_wall()
                if wall:
                    reply = f"{reply}\n\n{wall}" if reply else wall
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
        state is cleared either way, as is every pending prompt."""
        self._clear_pending(pid)
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
        return self._opening_reply(ev, pid, session, preamble=preamble)

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

        # DELAYED RETRY (founder 2026-07-06, the dropped-stream build sink): one
        # failed attempt gets a breath and a fresh try BEFORE the guest ever
        # sees a failure — most build deaths are transient provider spells, and
        # the guest already invested a whole interview. Only a second failure
        # surfaces the general message (their brief stays intact either way).
        last_exc: Exception | None = None
        for _attempt in range(2):
            try:
                # Re-scan for a free name each attempt: a failed run cleans up
                # after itself, but if anything lingers the retry must not trip
                # over the corpse (FileExistsError) — it just takes the next slot.
                while scenario_path(name).exists():
                    _n += 1
                    name = f"{base}_{_n}"
                slot = slot_path(name, pid)
                if slot.exists():
                    slot.unlink()  # fresh name → paranoia only
                self._build(name=name, provider=self._provider(),
                            seed=brief.get("premise", ""),
                            endless=brief.get("mode") != "win_loss",
                            win_direction=brief.get("win_direction", ""),
                            play_as=brief.get("play_as", ""),
                            game_types=brief.get("game_types") or [],
                            reality_register=brief.get("reality", ""),
                            on_stage=on_stage)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                logger.exception("build failed for %s (attempt %d)", pid,
                                 _attempt + 1)
                if _attempt == 0:
                    self._notify(ev, "(hit a snag mid-build — taking a breath "
                                     "and trying again…)")
                    time.sleep(BUILD_RETRY_DELAY_S)
        if last_exc is not None:
            return self._reply(
                ev, f"(I couldn't quite stabilize that world — {last_exc}. Tell "
                    f"me what to change, or we can try again.)")
        registry.set_scenario(self._conn, ev.platform, ev.external_id, name)
        self._notify(ev, "Your world is ready. Let's settle who you are in it…")
        return self._enter_world(pid, ev, scenario=name,
                                 mode=brief.get("mode"), preamble="")

    def _send_welcome_image(self, ev: InboundEvent) -> None:
        """Show the fixed projector image just before the welcome menu (founder). It's
        a static bundled asset — never generated, always the same — sent best-effort
        over the photo side-channel so the picture lands before the menu text. No-op
        if there's no photo sink (CLI) or the asset is missing."""
        if self._photo_fn is None:
            return
        try:
            if WELCOME_IMAGE.exists():
                self._photo_fn(ev.chat_id, str(WELCOME_IMAGE), "")
        except Exception:
            logger.exception("welcome image send failed for %s", ev.external_id)

    def _greeting_reply(self, ev: InboundEvent) -> Outbound:
        """The projector welcome: the static image, then the menu."""
        self._send_welcome_image(ev)
        return self._reply(ev, GREETING)
