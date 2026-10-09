"""Small shared helpers: mode normalization, name safety, the Atrium blob, the
invite-code reader."""

from __future__ import annotations

from construct.text import file_safe


def _extract_code(text: str) -> str | None:
    """Pull a `CONS-…` code out of a message (case-insensitive, first token
    that looks like one). Returns the canonical upper-cased code or None."""
    for tok in text.replace("\n", " ").split():
        if tok.upper().startswith("CONS-") and len(tok) > 6:
            return tok.upper()
    return None


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


def _empty_creation() -> dict:
    """A fresh, greeted-but-not-yet-conversing Atrium state."""
    return {"history": [], "state": {}}


def _safe(s: str) -> str:
    """Filesystem-safe scenario-name segment; never empty."""
    return file_safe(s or "") or "x"


def _core_module():
    """The `construct.transport_core` module, resolved at CALL time. The few
    module-level knobs tests patch (REBOOT_DELAY_S, IMAGE_BEFORE_TEXT_S,
    IMAGE_LATE_S) live there, so a mixin reads them through this accessor and a
    `monkeypatch.setattr(transport_core, ...)` still takes effect."""
    from construct import transport_core
    return transport_core
