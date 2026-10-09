"""The Foyer: character creation, the WHO phase before turn one."""

from __future__ import annotations

import logging

from construct import registry
from construct.transport.events import InboundEvent, Outbound
from construct.transport.helpers import _valid_mode

logger = logging.getLogger("construct.transport_core")  # one logger name, as before the split


class FoyerMixin:
    """Character-creation flow."""

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
                               world_brief=setup.get("world_brief", ""),
                               suggested_name=setup.get("suggested_name", ""))
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

        # Ready → ingest the character as canon, then open the story. apply_character
        # (grounding + relationship authoring) is itself slow, so ping BEFORE it; the
        # opening render's own heads-up fires inside _opening_reply (all paths).
        self._notify(ev, "✒️ Weaving who you are into the world — your character is being "
                         "bound to the story…")
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
        return self._opening_reply(ev, pid, session, preamble=result.reply)

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
