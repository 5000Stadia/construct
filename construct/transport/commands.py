"""Slash-command routing and the zero-turn commands (`/status`, `/notebook`,
notes, `/ooc`)."""

from __future__ import annotations

import logging

from construct import registry
from construct.transport.events import InboundEvent
from construct.transport.helpers import _valid_mode
from construct.transport.messages import HELP
from construct.transport.prompts import PENDING_EXIT

logger = logging.getLogger("construct.transport_core")  # one logger name, as before the split


class CommandsMixin:
    """The in-world slash commands."""

    def _command(self, pid: str, ev: InboundEvent, text: str, *, now: float = 0.0) -> str:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        scenario = registry.scenario_for(self._conn, ev.platform, ev.external_id)
        if cmd == "/help":
            return HELP
        if cmd == "/feedback":
            note = parts[1] if len(parts) > 1 else ""
            return self._feedback(ev, note)
        if cmd in ("/scenarios", "/world"):
            title = self._title_of(scenario) or scenario
            return f"You're in “{title}”. (/exit steps out to the start menu.)"
        if cmd == "/status":
            return self._status(pid, ev, parts[1].strip().lower() if len(parts) > 1 else "")
        if cmd == "/ooc":
            return self._ooc(pid, ev, parts[1] if len(parts) > 1 else "")
        if cmd in ("/notebook", "/journal", "/case"):
            return self._notebook(pid)
        if cmd == "/notes":
            return self._notes(pid, ev, parts[1].strip().lower() if len(parts) > 1 else "")
        if cmd == "/note":
            return self._note(pid, ev, parts[1].strip() if len(parts) > 1 else "", now=now)
        if cmd == "/del":
            return self._del(pid, ev, parts[1] if len(parts) > 1 else "")
        if cmd == "/remove":
            return self._remove_world(pid, ev, parts[1].strip() if len(parts) > 1 else "")
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
            self._arm(pid, PENDING_EXIT)
        # A fitting suggestion the engine agreed to try → record it for the narrator.
        weave = (out.get("weave") or "").strip()
        if weave and session is not None:
            try:
                session.note_wish(weave)
            except Exception:
                logger.exception("note_wish failed for %s", pid)
        return out.get("reply") or "Noted."

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
    def _notebook(self, pid: str) -> str:
        """`/notebook` — the CASE-BOARD (#83): the character's own knowledge (their
        `knows:` frame) rendered as a diegetic notebook. Zero-turn, zero-time, zero
        model calls; needs a live session (the notebook is the character's, not the
        player's — /notes holds the player's own jottings)."""
        session = self._sessions.get(pid)
        if session is None:
            return "📓 (resume your game first — the notebook belongs to your character.)"
        try:
            return session.journal()
        except Exception:
            logger.exception("/notebook failed for %s", pid)
            return "📓 (the notebook wouldn't open — try again?)"

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
