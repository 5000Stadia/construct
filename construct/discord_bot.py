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
import math
import os
import sys
from collections import deque

from construct import Session
from construct.game import list_scenarios, scenario_path

logger = logging.getLogger(__name__)

TOKEN_ENV = "CONSTRUCT_DISCORD_TOKEN"
SCENARIO_ENV = "CONSTRUCT_DISCORD_SCENARIO"          # default scenario for a new player
DEFAULT_SCENARIO = "anchor"
TURNING = "*the world turns…*"
PREFIX = "!"
DISCORD_MAX_LEN = 2000                               # Discord's hard per-message limit
MERGE_WINDOW_SEC = float(os.getenv("CONSTRUCT_DISCORD_MERGE_WINDOW_SEC", "2.0"))
INTERCHUNK_DELAY_SEC = float(os.getenv("CONSTRUCT_DISCORD_INTERCHUNK_DELAY_SEC", "1.0"))
# Gateway watchdog: Discord can close the gateway server-side and
# discord.py's auto-reconnect doesn't always recover it — the bot then
# goes deaf with healthy-looking process state (the Kernos 2026-05-19
# failure). A broken heartbeat for this many consecutive checks forces a
# clean os.execv restart (fresh IDENTIFY). Generous, to never false-fire
# on a quiet bot; env-tunable; set interval=0 to disable.
WATCHDOG_INTERVAL_SEC = float(os.getenv("CONSTRUCT_DISCORD_WATCHDOG_INTERVAL_SEC", "60"))
WATCHDOG_LATENCY_MAX_SEC = float(os.getenv("CONSTRUCT_DISCORD_WATCHDOG_LATENCY_MAX_SEC", "60"))
WATCHDOG_STRIKES = int(os.getenv("CONSTRUCT_DISCORD_WATCHDOG_STRIKES", "3"))


def heartbeat_unhealthy(latency: float, threshold: float = WATCHDOG_LATENCY_MAX_SEC) -> bool:
    """True when discord.py's heartbeat RTT signals a dead gateway:
    NaN/inf (never connected or lost), or implausibly large (Kernos
    watches `client.latency` exactly this way)."""
    if latency is None or math.isnan(latency) or math.isinf(latency):
        return True
    return latency > threshold


class _SeenIds:
    """Bounded set of recently-seen message ids — Discord re-delivers
    events on gateway reconnect / missed ACKs, and a re-delivered DM
    must not run the turn twice (the Kernos dedup lesson). Drops the
    oldest half when full so memory stays bounded."""

    def __init__(self, maxlen: int = 256) -> None:
        self._ids: dict[int, None] = {}
        self._maxlen = maxlen

    def seen(self, message_id: int) -> bool:
        if message_id in self._ids:
            return True
        if len(self._ids) >= self._maxlen:
            for old in list(self._ids)[: self._maxlen // 2]:
                del self._ids[old]
        self._ids[message_id] = None
        return False


def coalesce_leading_turns(buf: deque) -> tuple[str, str, object]:
    """Pop the next unit of work off a player's mailbox. A command is
    one unit. A run of contiguous in-world turns merges into ONE turn
    (the Kernos merge-window lesson: a barrage of rapid lines becomes a
    single coherent turn, in order — never N concurrent turns), stopping
    at the next command so command ordering is preserved. Returns
    (text, kind, channel) where kind is 'cmd' or 'turn'."""
    kind, body, channel = buf.popleft()
    if kind == "cmd":
        return body, "cmd", channel
    parts = [body]
    while buf and buf[0][0] == "turn":
        parts.append(buf.popleft()[1])
    return "\n\n".join(p for p in parts if p), "turn", channel


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


class _Mailbox:
    """One player's serialized inbox: a deque of (kind, body, channel)
    plus a wake event and a single worker task. One worker per player
    means turns for a player NEVER run concurrently (concurrent
    `session.turn` on one .world would interleave SQLite writes)."""

    def __init__(self) -> None:
        self.buf: deque = deque()
        self.wake = asyncio.Event()
        self.task: asyncio.Task | None = None


class _Pipe:
    """Routes text in and out, one serialized mailbox per Discord user.
    No engine logic lives here — only transport."""

    def __init__(self, default_scenario: str,
                 merge_window: float = MERGE_WINDOW_SEC) -> None:
        self._default = default_scenario
        self._merge_window = merge_window
        self._sessions: dict[int, Session] = {}
        self._mailboxes: dict[int, _Mailbox] = {}

    # -- sessions ---------------------------------------------------------

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

    # -- per-player serialized mailbox ------------------------------------

    def submit(self, user_id: int, channel, body: str) -> None:
        """Enqueue an inbound DM and ensure the player's worker is
        running. Returns immediately — `on_message` never blocks, and a
        barrage just stacks in the deque to be coalesced."""
        kind = "cmd" if body.startswith(PREFIX) else "turn"
        mb = self._mailboxes.setdefault(user_id, _Mailbox())
        mb.buf.append((kind, body, channel))
        mb.wake.set()
        if mb.task is None or mb.task.done():
            mb.task = asyncio.ensure_future(self._run_player(user_id, mb))

    async def _run_player(self, user_id: int, mb: _Mailbox) -> None:
        while True:
            if not mb.buf:
                mb.wake.clear()
                await mb.wake.wait()
                continue
            kind = mb.buf[0][0]
            if kind == "turn":
                # Merge window: let a barrage land, then coalesce the
                # leading run of turns into ONE turn.
                await asyncio.sleep(self._merge_window)
            text, kind, channel = coalesce_leading_turns(mb.buf)
            try:
                if kind == "cmd":
                    await channel.send(self.handle_command(user_id, text))
                else:
                    await self._play_turn(user_id, channel, text)
            except Exception:  # one bad unit never kills the worker
                logger.exception("mailbox unit failed for user %s", user_id)

    async def _play_turn(self, user_id: int, channel, text: str) -> None:
        placeholder = await channel.send(TURNING)
        try:
            session = self.session_for(user_id)
            async with _best_effort_typing(channel):    # typing 429 must not kill the turn
                result = await asyncio.to_thread(session.turn, text)
            parts = chunk(result.prose)
            await placeholder.edit(content=parts[0])
            for extra in parts[1:]:          # long narration: never truncate
                await asyncio.sleep(INTERCHUNK_DELAY_SEC)   # don't shotgun → 429
                await channel.send(extra)
        except Exception as exc:  # bot stays up
            logger.exception("turn failed in discord transport")
            await placeholder.edit(content=f"(the turn could not complete: {exc})")

    def handle_command(self, user_id: int, body: str) -> str:
        return _handle_command(self, user_id, body) or HELP

    def close_all(self) -> None:
        for mb in self._mailboxes.values():
            if mb.task is not None:
                mb.task.cancel()
        self._mailboxes.clear()
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


import contextlib


@contextlib.asynccontextmanager
async def _best_effort_typing(channel):
    """Show the native typing indicator if we can; never let a typing
    failure (e.g. a 429 on the typing route) abort the turn that follows
    (the Kernos per-call-degradation lesson)."""
    cm = None
    try:
        cm = channel.typing()
        await cm.__aenter__()
    except Exception:
        cm = None
        logger.debug("typing indicator unavailable; proceeding")
    try:
        yield
    finally:
        if cm is not None:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass


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
    client = discord.Client(
        intents=intents,
        # Narration is model-generated text posted to Discord — never let
        # it ping @everyone/@here/roles/users (general hardening, not a
        # Kernos note, but the same defensive instinct).
        allowed_mentions=discord.AllowedMentions.none(),
    )
    # Cap discord.py's retry-on-429 sleep so a rate-limit can't compound
    # into a long backoff (the Kernos-bot lesson). The constructor clamps
    # to 30s, so set it directly after construction.
    try:
        client.http.max_ratelimit_timeout = float(
            os.getenv("CONSTRUCT_DISCORD_MAX_RETRY_SLEEP_SEC", "10"))
    except Exception:  # never let a resilience knob block startup
        logger.warning("could not set max_ratelimit_timeout; using discord.py default")
    pipe = _Pipe(default_scenario or os.getenv(SCENARIO_ENV, DEFAULT_SCENARIO))
    seen = _SeenIds()

    async def _gateway_watchdog() -> None:
        """Auto-recover a wedged gateway: a broken heartbeat for
        WATCHDOG_STRIKES consecutive checks forces a clean restart (fresh
        IDENTIFY), since discord.py's auto-reconnect doesn't always
        recover a server-side close."""
        strikes = 0
        while True:
            await asyncio.sleep(WATCHDOG_INTERVAL_SEC)
            if heartbeat_unhealthy(client.latency):
                strikes += 1
                logger.warning("gateway heartbeat unhealthy (latency=%s) strike %d/%d",
                               client.latency, strikes, WATCHDOG_STRIKES)
                if strikes >= WATCHDOG_STRIKES:
                    logger.error("gateway wedged %d checks — restarting via execv", strikes)
                    if getattr(client, "_construct_pipe", None):
                        client._construct_pipe.close_all()
                    os.execv(sys.executable, [sys.executable, *sys.argv])
            else:
                strikes = 0

    @client.event
    async def on_ready() -> None:
        logger.info("Construct Discord bot online as %s", client.user)
        if WATCHDOG_INTERVAL_SEC > 0 and getattr(client, "_watchdog_task", None) is None:
            client._watchdog_task = asyncio.ensure_future(_gateway_watchdog())

    @client.event
    async def on_message(message) -> None:
        if message.author == client.user:
            return
        if getattr(message.author, "bot", False):    # ignore other bots (loop/pollution guard)
            return
        # DM-based single-player only in v1 (founder's scope).
        if message.guild is not None:
            return
        if seen.seen(message.id):                     # Discord re-delivers on reconnect
            logger.debug("dropping duplicate message id %s", message.id)
            return
        body = (message.content or "").strip()
        if not body:
            return
        # Enqueue and return immediately — the per-player worker
        # serializes turns and coalesces a barrage. on_message never
        # blocks and never runs a turn concurrently with another.
        pipe.submit(message.author.id, message.channel, body)

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
    except Exception as exc:  # friendly, specific fixes for the common setup misconfigs
        import discord
        if isinstance(exc, discord.PrivilegedIntentsRequired):
            raise SystemExit(
                "Discord refused the connection: the MESSAGE CONTENT INTENT is off.\n"
                "Enable it: Developer Portal → your app → Bot → Privileged Gateway "
                "Intents → MESSAGE CONTENT INTENT (see docs/DISCORD.md step B3).") from exc
        if isinstance(exc, discord.LoginFailure):
            raise SystemExit(
                f"Discord rejected the token in ${TOKEN_ENV}. Re-copy it from the "
                "Bot tab (Reset Token) and re-export it (docs/DISCORD.md step B2).") from exc
        raise
    finally:
        getattr(client, "_construct_pipe", None) and client._construct_pipe.close_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
