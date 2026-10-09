"""Pending prompts: the questions a player owes us an answer to, plus the
yes/no and pick-one answer readers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from construct.text import alnum_words


# Pending prompts: the questions a player owes us an answer to. One tagged state
# per KIND, held per player (see TransportCore._arm / _peek / _disarm).
PENDING_EXIT = "exit"                        # "leave the story?" yes/no


PENDING_RESTART_DEPTH = "restart_depth"      # /restart step 1: episode / original / cancel


PENDING_RESTART_CHARACTER = "restart_character"  # step 2: keep / redo / cancel


PENDING_RESTART_NOTES = "restart_notes"      # step 3: keep / wipe notes / cancel


PENDING_CONTINUE = "continue"                # chapter ended: say anything to roll on


# The three /restart steps are ONE wizard: only one step is ever armed, and arming
# a step supersedes any other (a fresh /restart replaces a half-answered one).
_RESTART_STEPS = (PENDING_RESTART_NOTES, PENDING_RESTART_CHARACTER,
                  PENDING_RESTART_DEPTH)


@dataclass(frozen=True)
class Pending:
    """One armed prompt: its `kind` (a PENDING_* tag) and any `data` the later
    steps need (e.g. the restart wizard's keep_character choice)."""
    kind: str
    data: dict = field(default_factory=dict)


def _affirmative(text: str) -> bool:
    """A yes-ish answer to the 'leave the story?' confirm."""
    t = (text or "").strip().lower().rstrip("!. ")
    return t in {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
                 "do it", "exit", "quit", "leave", "new story", "start over"}


_CANCEL_WORDS = ("cancel", "stop", "nvm", "never", "no")


def _pick(answer: str, choices: dict[str, tuple[str, ...]]) -> str | None:
    """Which ONE of `choices` did the answer pick? Matches the exact choice words as
    WHOLE WORDS (never substrings: "yes" is not "wipe", "new" is not "redo", and a
    word inside another word never counts). Returns None when no choice matches or
    when two different choices both do — the caller re-asks and keeps the prompt
    armed, so a destructive path never runs on an ambiguous answer."""
    words = set(alnum_words(answer or ""))
    hit = {name for name, keys in choices.items() if words & set(keys)}
    return next(iter(hit)) if len(hit) == 1 else None


class PendingMixin:
    """Per-player armed-prompt state (`self._pending`)."""

    def _arm(self, pid: str, kind: str, **data: Any) -> None:
        """Arm a prompt for the player. Arming a /restart step supersedes any other
        step of the wizard; other kinds are independent."""
        slots = self._pending.setdefault(pid, {})
        if kind in _RESTART_STEPS:
            for step in _RESTART_STEPS:
                slots.pop(step, None)
        slots[kind] = Pending(kind, data)

    def _peek(self, pid: str, kind: str) -> Pending | None:
        """The player's armed prompt of this kind, or None. Does not disarm."""
        return self._pending.get(pid, {}).get(kind)

    def _disarm(self, pid: str, kind: str) -> Pending | None:
        """Disarm and return the player's prompt of this kind (None if not armed)."""
        slots = self._pending.get(pid)
        if slots is None:
            return None
        armed = slots.pop(kind, None)
        if not slots:
            del self._pending[pid]
        return armed

    def _clear_pending(self, pid: str) -> None:
        """Disarm EVERY pending prompt for the player. A player who leaves or enters a
        world must not carry a stale arm into the next one (e.g. /exit after "End of
        Chapter" must not let the next start-menu message build a new chapter).
        `_ooc_pressed` is an escalation flag, not a prompt, so it is not touched."""
        self._pending.pop(pid, None)
