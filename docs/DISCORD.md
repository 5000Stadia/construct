# Playing Construct over Discord

Play a holonovel from your phone (or anywhere) by DMing a Discord bot —
**without exposing your machine to the inbound internet.** The bot is
*outbound-only*: it dials out to Discord exactly like any bot, so there
is no open port, no tunnel, and no public URL. Discord relays your
messages to the bot running on your machine; nothing reaches in.

The bot is a **dumb pipe**: your message → Construct runs the turn →
the prose comes back. No model runs in the bot itself; Construct does
all the work. It's a peer to the CLI, not a separate game.

---

## A. Install + a local play check first (CLI)

Get it running locally before wiring Discord — if `construct play`
works, the bot will too (the bot is just another front end on the same
session API).

```bash
cd construct                                  # the repo
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[discord]'                   # core engine + the Discord transport
```

The model provider is the **Codex (ChatGPT-subscription) default** — it
reads `~/.codex/auth.json`; if you see a 401, run `codex login`. No API
key or credits are required.

Confirm local play:

```bash
construct scenarios                  # lists the shipped world: "anchor"
construct play anchor                # interactive prompt; type, then :quit
```

If that renders a scene, you're ready to wire Discord.

---

## B. Create the Discord bot (one-time, ~5 minutes)

1. **Create the application + bot.** Go to
   <https://discord.com/developers/applications> → **New Application**,
   name it (e.g. "Construct"). Open the **Bot** tab → **Add Bot**.
2. **Copy the token.** On the Bot tab, **Reset Token** → copy it. This
   is a secret — treat it like a password. (You'll set it as an env var
   below; **never commit it to git** — it is not stored in the repo.)
3. **Enable the Message Content intent.** Still on the Bot tab, under
   **Privileged Gateway Intents**, turn on **MESSAGE CONTENT INTENT**
   (the bot must read your DM text). DMs need no other privileged
   intent.
4. **Invite the bot to yourself.** On the **OAuth2 → URL Generator**
   tab, tick scope **`bot`**, and bot permissions **Send Messages** +
   **Read Message History**. Copy the generated URL, open it, and
   authorize. (For DM-only play you don't need to add it to any
   server — authorizing the app lets you DM it. If your client won't
   open a DM, add it to any server you own with that invite, then DM it
   from there.)

---

## C. Run the bot

```bash
source .venv/bin/activate
export CONSTRUCT_DISCORD_TOKEN="paste-your-bot-token-here"
# optional — the world a new player starts in (default: anchor):
export CONSTRUCT_DISCORD_SCENARIO="anchor"

python -m construct.discord_bot
```

You'll see `Construct Discord bot online as <name>`. Leave it running
(it holds your playthroughs open and saves every turn). A missing token
fails loud and tells you this; a bad token fails loud from Discord.

**If the bot goes quiet after a network blip,** restart the process
(`Ctrl-C`, run it again). discord.py usually auto-reconnects, but a
server-side gateway close can occasionally wedge it; a restart forces a
fresh connection. Nothing is lost — every turn is already saved to the
slot. (Optional knob: `CONSTRUCT_DISCORD_MAX_RETRY_SLEEP_SEC`, default
10, caps how long a rate-limit retry waits.)

> Keep the token out of git. Put it in your shell profile or a local
> `.env` you never commit — the repo gitignores world/state files and
> never stores secrets.

---

## D. Play

**DM the bot** and just type what you do, line after line. A turn takes
about a minute on the good-tier narrator; the bot posts *"the world
turns…"* and then replaces it with the scene, so it never looks hung.
Progress saves every turn — close Discord and come back; you resume
where you left off.

Session-control commands (these are bot controls, not in-world actions):

| Command | Effect |
|---|---|
| `!help` | the command list |
| `!scenarios` | list available worlds |
| `!play <name>` | start `<name>` **fresh** (restarts that world) |
| `!resume [name]` | resume your current world (or `<name>`) |

Everything else you type is an in-world turn. Asking the world a
question, "what can I do?", and meta-asides all route correctly on their
own — there is no separate chat mode.

Each Discord user gets their own private playthrough (keyed by your
Discord id), so multiple people can play the same world without
colliding.

---

## Scope (v1)

DM-based single-player, by design (it's what the founder uses). Shared
channels / multiplayer in one scene — where two players' knowledge
frames would make genuine information asymmetry possible — is a later
extension, not built yet. The transport stays a thin outbound pipe; the
rich multi-user experience, if it comes, is an adopting host's job
(e.g. Kernos via the adapter), never bolted into Construct.
