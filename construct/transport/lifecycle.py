"""Lifecycle transitions out of play: the `/restart` wizard, `/exit`, and the
chapter-end continue."""

from __future__ import annotations

import logging

from construct import registry
from construct.transport.events import InboundEvent, Outbound
from construct.transport.helpers import _empty_creation, _valid_mode
from construct.transport.messages import GREETING
from construct.transport.prompts import (
    _CANCEL_WORDS, PENDING_RESTART_CHARACTER, PENDING_RESTART_DEPTH,
    PENDING_RESTART_NOTES, _pick)
from construct.transport.stages import _humanize_stage

logger = logging.getLogger("construct.transport_core")  # one logger name, as before the split


class LifecycleMixin:
    """Restart wizard, exit, and continue."""

    def _do_restart(self, pid: str, ev: InboundEvent, answer: str) -> Outbound:
        """Answer to the `/restart` confirm (step one — how far back):
        - 'episode' → restart THIS episode from its start: roll the slot back to the
          episode checkpoint (character carries over, no Foyer). For a first/only
          episode with no checkpoint, fall back to a clean copy with the saved
          character re-applied.
        - 'original' → go all the way back to the original scenario; ask step two
          (keep the same character, or redo the interview).
        'cancel' → keep playing. Anything else is ambiguous → re-ask (still armed)."""
        from construct.game import restore_episode_start
        plat, ext = ev.platform, ev.external_id
        scen = registry.scenario_for(self._conn, plat, ext)
        choice = _pick(answer, {"original": ("original", "2"),
                                "episode": ("episode", "1"),
                                "cancel": _CANCEL_WORDS})
        if choice is None:
            title = self._title_of(scen)
            return self._reply(
                ev, f"I didn't catch that — restarting erases your saved progress in "
                    f"{title}. Answer with one word:\n• “episode” — restart just this "
                    f"episode from its start (your character carries over).\n• "
                    f"“original” — all the way back to the very start of the original "
                    f"scenario.\n• “cancel” — keep playing.")
        self._disarm(pid, PENDING_RESTART_DEPTH)
        if choice == "original":
            self._arm(pid, PENDING_RESTART_CHARACTER)
            return self._reply(
                ev, "All the way back to the original. Do you want to keep the "
                    "character and elements you set up last time, or redo that "
                    "interview from scratch?\n• “keep” — same character, fresh "
                    "world.\n• “redo” — start the character interview over.\n• "
                    "“cancel” — keep playing.")
        if choice == "episode":
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
        else (ambiguous) → re-ask, prompt stays armed."""
        plat, ext = ev.platform, ev.external_id
        scen = registry.scenario_for(self._conn, plat, ext)
        choice = _pick(answer, {"keep": ("keep", "1"), "redo": ("redo", "2"),
                                "cancel": _CANCEL_WORDS})
        if choice is None:
            return self._reply(
                ev, "I didn't catch that — answer with one word:\n• “keep” — same "
                    "character, fresh world.\n• “redo” — start the character interview "
                    "over.\n• “cancel” — keep playing.")
        self._disarm(pid, PENDING_RESTART_CHARACTER)
        if choice == "cancel":
            return self._reply(ev, "Kept your game as is — carry on.")
        keep_character = choice == "keep"
        if registry.list_notes(self._conn, plat, ext, scen):
            self._arm(pid, PENDING_RESTART_NOTES, keep_character=keep_character)
            return self._reply(
                ev, "And your notes for this story — keep them, or wipe them for a "
                    "clean slate?\n• “keep” — keep your notes.\n• “wipe” — clear "
                    "them.\n• “cancel” — don't restart after all.")
        return self._execute_restart_original(pid, ev, keep_character=keep_character,
                                              wipe_notes=False)

    def _do_restart_notes(self, pid: str, ev: InboundEvent, answer: str) -> Outbound:
        """`/restart → original` step three — the notes: 'wipe' clears this story's
        notes, 'keep' carries them into the fresh start, 'cancel' aborts the whole
        restart (nothing dropped). Anything ambiguous re-asks and stays armed: the
        restart is never executed, nor notes destroyed, on a guess."""
        choice = _pick(answer, {"keep": ("keep",), "wipe": ("wipe",),
                                "cancel": _CANCEL_WORDS})
        if choice is None:
            return self._reply(
                ev, "I didn't catch that — your notes for this story: answer with one "
                    "word:\n• “keep” — keep your notes.\n• “wipe” — clear them.\n• "
                    "“cancel” — don't restart after all.")
        decision = self._disarm(pid, PENDING_RESTART_NOTES)
        if choice == "cancel":
            return self._reply(ev, "Kept your game as is — carry on.")
        return self._execute_restart_original(
            pid, ev, keep_character=bool(decision and decision.data.get("keep_character")),
            wipe_notes=choice == "wipe")

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
        return self._opening_reply(ev, pid, session, preamble=preamble)

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

    def _exit(self, pid: str, ev: InboundEvent) -> str:
        """Leave the current scenario for the start menu — clear `started` (so the
        next message re-enters the Atrium) and any in-progress dialogue, drop the
        cached session; the saved playthrough slot is untouched (resumable)."""
        registry.set_started(self._conn, ev.platform, ev.external_id, False)
        registry.clear_chargen(self._conn, ev.platform, ev.external_id)
        self._sessions.pop(pid, None)
        self._clear_pending(pid)
        registry.set_creation(self._conn, ev.platform, ev.external_id, _empty_creation())
        self._send_welcome_image(ev)  # the projector image leads the welcome menu
        return ("Stepped out — your story is saved where you left it.\n\n" + GREETING)

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
            return self._opening_reply(ev, pid, session)
        except Exception as exc:
            logger.exception("continuation opening failed for %s", pid)
            return self._reply(ev, f"(the next chapter opened, but its scene didn't render: {exc})")
