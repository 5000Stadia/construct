"""First-load menu + Telegram setup wizard.

Construct stays CLI-first. This adds a tiny opt-in surface so a trusted tester
can continue "on the go" via Telegram, without web deployment or a member
system (Cx 065).

Secrets discipline (Codex spec review):
- the bot token is prompted LOCALLY (no echo, no CLI arg, no shell history) and
  NEVER travels through any LLM/transport path;
- it is written to a `0600` file created with that mode (not chmod-after-write);
- only the NON-secret bot username is persisted to `config.json`;
- the token is embedded in Telegram request URLs, so every error/log path
  REDACTS it — a bad token fails loud but never prints the URL.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from construct.game import WORLDS_DIR

logger = logging.getLogger(__name__)

CONSTRUCT_DIR = WORLDS_DIR / ".construct"      # under the gitignored worlds/
CONFIG_PATH = CONSTRUCT_DIR / "config.json"    # non-secret
TOKEN_PATH = CONSTRUCT_DIR / "telegram_token"  # 0600, secret
TOKEN_ENV = "CONSTRUCT_TELEGRAM_TOKEN"
#: .env files checked for the token (gitignored). Drop a line
#: `CONSTRUCT_TELEGRAM_TOKEN=123:ABC…` in either and `construct telegram`
#: picks it up — no interactive wizard needed.
DOTENV_PATHS = [Path(".env"), CONSTRUCT_DIR / ".env"]


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except json.JSONDecodeError:
            logger.warning("config.json malformed; treating as empty")
    return {}


def save_config(cfg: dict) -> None:
    CONSTRUCT_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _token_from_dotenv() -> str | None:
    """Read CONSTRUCT_TELEGRAM_TOKEN from a `.env` file (KEY=VALUE lines;
    quotes + comments tolerated). Lets the operator drop the token in a file
    rather than run the wizard. Never logged."""
    for path in DOTENV_PATHS:
        if not path.exists():
            continue
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key.strip() == TOKEN_ENV:
                    val = val.strip().strip('"').strip("'")
                    if val:
                        return val
        except OSError:
            continue
    return None


def read_token() -> str | None:
    """The token, in precedence order: the environment, a `.env` file
    (DOTENV_PATHS), then the 0600 secrets file. Never logged."""
    env = os.environ.get(TOKEN_ENV)
    if env:
        return env.strip()
    dot = _token_from_dotenv()
    if dot:
        return dot
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text().strip() or None
    return None


def save_token(token: str) -> None:
    """Write the token to a file CREATED with 0600 (never world-readable, not
    even momentarily)."""
    CONSTRUCT_DIR.mkdir(parents=True, exist_ok=True)
    # Open with O_CREAT|O_WRONLY|O_TRUNC and mode 0600 so it is never created
    # world-readable; re-chmod existing file too (umask could have widened it).
    fd = os.open(str(TOKEN_PATH), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode())
    finally:
        os.close(fd)
    os.chmod(TOKEN_PATH, 0o600)


def redact(text: str, token: str | None) -> str:
    """Strip a token from any string before it is printed/logged."""
    return text.replace(token, "***") if token else text


def is_configured() -> bool:
    return read_token() is not None


def validate_token(token: str, *, get=None) -> dict:
    """Validate via Telegram `getMe`; return the `result` dict (bot identity).
    Raises ValueError with a REDACTED, actionable message on failure — never
    printing the request URL (which embeds the token)."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    if get is None:
        import httpx
        get = lambda u: httpx.get(u, timeout=15)  # noqa: E731
    try:
        resp = get(url)
        data = resp.json()
    except Exception as exc:
        raise ValueError(f"could not reach Telegram ({redact(str(exc), token)}); "
                         f"check your connection and paste the token from "
                         f"@BotFather again") from None
    if not data.get("ok"):
        raise ValueError("Telegram rejected the token — paste the token from "
                         "@BotFather again")
    return data["result"]


def setup_telegram(*, prompt=None, get=None, out=print) -> str:
    """Interactive wizard: guide the operator through @BotFather, take the
    token locally (no echo), validate it, store it 0600, persist the bot
    username. Returns the bot username."""
    if prompt is None:
        import getpass
        prompt = getpass.getpass
    out("Open Telegram and message @BotFather:")
    out("  1. Send /newbot, choose a display name and a username.")
    out("  2. Copy the token it gives you (looks like 123456:ABC-...).")
    token = (prompt("Paste the bot token (input hidden): ") or "").strip()
    if not token:
        raise ValueError("no token entered")
    result = validate_token(token, get=get)
    username = result.get("username", "")
    save_token(token)
    cfg = load_config()
    cfg["telegram_bot_username"] = username
    save_config(cfg)
    out(f"\nTelegram connected as @{username}.")
    out("Start the transport: construct telegram")
    out("Invite a tester:     construct invite telegram --scenario anchor")
    return username


def first_load_menu(*, input_fn=input, out=print) -> str:
    """Shown on interactive `construct play` when Telegram is neither
    configured nor dismissed. Returns 'play' | 'telegram' | 'dismiss'.
    Default (bare Enter) is zero-friction CLI play."""
    cfg = load_config()
    if is_configured() or cfg.get("telegram_dismissed"):
        return "play"
    out("Play in this terminal?            [Enter]")
    out("Set up Telegram for phone play?   [t]")
    out("Don't ask again?                  [s]")
    try:
        choice = input_fn("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = ""
    if choice == "t":
        return "telegram"
    if choice == "s":
        cfg["telegram_dismissed"] = True
        save_config(cfg)
        return "dismiss"
    return "play"
