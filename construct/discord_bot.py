"""A thin, outbound-only Discord transport for Construct (letter 034).

A SEPARATE process with its OWN bot token — a peer to the REPL, not a
plugin, not a Kernos integration. It is a dumb pipe: a player's DM →
`Session.turn(text)` → post the prose back. There is NO model in the
relay path; Construct's cohorts do all the LLM work. The bot never
interprets, rewrites, or comments — words reach `turn()` verbatim, prose
comes back verbatim.

Outbound-only: the bot dials out to Discord exactly like the Kernos bot;
nothing inbound is opened (no port, tunnel, or public URL). Setup is in
docs/DISCORD.md.

Run it:  python -m construct.discord_bot      (token in $CONSTRUCT_DISCORD_TOKEN)
"""

from __future__ import annotations

import asyncio
import logging
import os

from construct import Session
from construct.game import list_scenarios, scenario_path
from construct.session import slot_exists

logger = logging.getLogger(__name__)

TOKEN_ENV = "CONSTRUCT_DISCORD_TOKEN"
SCENARIO_ENV = "CONSTRUCT_DISCORD_SCENARIO"          # default scenario for a new player
DEFAULT_SCENARIO = "anchor"
TURNING = "*the world turns…*"
PREFIX = "!"
DISCORD_MAX_LEN = 2000                               # Discord's hard per-message limit


def chunk(text: str, limit: int = DISCORD_MAX_LEN) -> list[str]:
    """Split prose to fit Discord's per-message limit, preferring newline
    boundaries — narration can exceed 2000 chars and must never be
    truncated (the Kernos-bot lesson). Always returns ≥1 chunk."""
    text = text or "(the world is quiet)"
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n ")
    return chunks

HELP = (
    "**Construct — play by DM.** Just type what you do, line after line.\n"
    "`!scenarios` — list worlds · `!play <name>` — switch/restart fresh\n"
    "`!resume` — resume current world · `!help` — this message\n"
    "Each turn takes ~a minute (the world turns…); progress saves every turn."
)


class _Pipe:
    """Holds one open Session per Discord user. No engine logic lives
    here — only routing text in and out."""

    def __init__(self, default_scenario: str) -> None:
        self._default = default_scenario
        self._sessions: dict[int, Session] = {}

    def _open(self, user_id: int, scenario: str, *, fresh: bool) -> Session:
        old = self._sessions.pop(user_id, None)
        if old is not None:
            old.close()
        session = Session.open(scenario, player_id=f"discord:{user_id}", fresh=fresh)
        self._sessions[user_id] = session
        return session

    def session_for(self, user_id: int) -> Session:
        if user_id not in self._sessions:
            self._open(user_id, self._default, fresh=False)
        return self._sessions[user_id]

    def play(self, user_id: int, scenario: str, *, fresh: bool) -> Session:
        if not scenario_path(scenario).exists():
            raise FileNotFoundError(scenario)
        return self._open(user_id, scenario, fresh=fresh)

    def close_all(self) -> None:
        for s in self._sessions.values():
            s.close()
        self._sessions.clear()


def _handle_command(pipe: _Pipe, user_id: int, body: str) -> str | None:
    """Session-control commands (not in-world). Returns a reply string,
    or None if `body` is not a command and should go to the turn path."""
    if not body.startswith(PREFIX):
        return None
    parts = body[len(PREFIX):].split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    arg = parts[1].strip() if len(parts) == 2 else ""
    if cmd in ("help", "h", "?", ""):
        return HELP
    if cmd == "scenarios":
        rows = list_scenarios()
        if not rows:
            return "No scenarios yet."
        return "**Worlds:**\n" + "\n".join(
            f"• `{r['name']}` — {r.get('title', '?')}" for r in rows)
    if cmd in ("play", "fresh"):
        scenario = arg or pipe.session_for(user_id).scenario
        try:
            session = pipe.play(user_id, scenario, fresh=True)
        except FileNotFoundError:
            return f"No scenario `{scenario}`. Try `!scenarios`."
        return f"**{session.opening()}**\n\nType what you do."
    if cmd == "resume":
        scenario = arg or pipe.session_for(user_id).scenario
        try:
            session = pipe.play(user_id, scenario, fresh=False)
        except FileNotFoundError:
            return f"No scenario `{scenario}`. Try `!scenarios`."
        return f"**{session.opening()}**\n\nType what you do."
    return f"Unknown command `{body}`. `!help` for the list."


def build_client(default_scenario: str | None = None):
    """Construct the discord client. discord.py is imported HERE so the
    core engine never depends on it (gated like the Codex live smoke)."""
    try:
        import discord
    except ModuleNotFoundError as exc:  # fail loud, name the fix
        raise SystemExit(
            "discord.py is not installed. Install the bot extra:\n"
            "  pip install -e '.[discord]'\n"
            "(the core engine does not depend on it.)") from exc

    intents = discord.Intents.default()
    intents.message_content = True       # required to read DM text
    intents.dm_messages = True
    client = discord.Client(intents=intents)
    # Cap discord.py's retry-on-429 sleep so a rate-limit can't compound
    # into a long backoff (the Kernos-bot lesson). The constructor clamps
    # to 30s, so set it directly after construction.
    try:
        client.http.max_ratelimit_timeout = float(
            os.getenv("CONSTRUCT_DISCORD_MAX_RETRY_SLEEP_SEC", "10"))
    except Exception:  # never let a resilience knob block startup
        logger.warning("could not set max_ratelimit_timeout; using discord.py default")
    pipe = _Pipe(default_scenario or os.getenv(SCENARIO_ENV, DEFAULT_SCENARIO))

    @client.event
    async def on_ready() -> None:
        logger.info("Construct Discord bot online as %s", client.user)

    @client.event
    async def on_message(message) -> None:
        if message.author == client.user:
            return
        # DM-based single-player only in v1 (founder's scope).
        if message.guild is not None:
            return
        body = (message.content or "").strip()
        if not body:
            return

        reply = _handle_command(pipe, message.author.id, body)
        if reply is not None:
            await message.channel.send(reply)
            return

        # An in-world turn. Post a placeholder, show the native typing
        # indicator, run the blocking turn OFF the event loop, then
        # replace the placeholder with the (chunked) prose.
        placeholder = await message.channel.send(TURNING)
        try:
            session = pipe.session_for(message.author.id)
            async with message.channel.typing():
                result = await asyncio.to_thread(session.turn, body)
            parts = chunk(result.prose)
            await placeholder.edit(content=parts[0])
            for extra in parts[1:]:          # long narration: never truncate
                await message.channel.send(extra)
        except Exception as exc:  # bot stays up
            logger.exception("turn failed in discord transport")
            await placeholder.edit(content=f"(the turn could not complete: {exc})")

    client._construct_pipe = pipe  # for clean shutdown / tests
    return client


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    token = os.getenv(TOKEN_ENV)
    if not token:
        raise SystemExit(
            f"No Discord token. Set ${TOKEN_ENV} (see docs/DISCORD.md). "
            "It must never be committed to git.")
    client = build_client()
    try:
        client.run(token)
    finally:
        getattr(client, "_construct_pipe", None) and client._construct_pipe.close_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
