"""Presentation copy: the fixed strings a transport speaks."""

from __future__ import annotations

from pathlib import Path


STATIC_REJECT = (
    "This Construct bot is invite-only. Send the CONS- invite code the operator "
    "gave you to begin.")


HELP = (
    "Just type what you want to do — the story answers, and every turn saves "
    "itself. Commands, when you want them:\n"
    "\n"
    "🎭 YOUR STORY\n"
    "/resume — pick up exactly where you left off\n"
    "/restart — start this story over (asks how far back before touching anything)\n"
    "/exit — step out to the start menu; your game stays saved\n"
    "/world — which story you're in right now\n"
    "\n"
    "🧭 AT A GLANCE\n"
    "/status — the in-world time and place (add “pin” to keep it atop every reply)\n"
    "📓 /notebook — your character's own case-notes: the people, places, and "
    "things they've learned so far (also answers to /journal and /case)\n"
    "\n"
    "📝 YOUR NOTES\n"
    "/note <text> — jot a private note to yourself; it follows your character "
    "across adventures\n"
    "/notes — list your notes · /del 2 — delete note №2\n"
    "\n"
    "🗂 THE SHELF\n"
    "/remove <title> — retire a world from the shelf (its files are archived, "
    "never deleted)\n"
    "\n"
    "🛠 THE ENGINE\n"
    "/ooc <question> — step outside the story and ask the host anything (what "
    "worlds exist, how something works, what a rule means)\n"
    "/feedback <what happened> — report a bug or something that felt wrong "
    "DIRECTLY TO THE DEVELOPER; your last few turns are attached automatically "
    "so it can be investigated\n"
    "/dump — save this whole chat to a log file\n"
    "/help — this menu")


#: The Construct's first words — a SIMPLE welcome (founder: "first message should
#: be a simple greeting… if the user knows what's up they'll just load what they
#: want"). The rich showcase of worlds/saved games/new-build is the Construct
#: cohort's job WHEN ASKED, not a wall of options up front.
GREETING = (
    "📽️ Welcome to the Construct Projector — online and ready.\n\n"
    "Pick a path:\n"
    "🆕 New — create a new world\n"
    "📂 Browse — say “list” to see the ready-made worlds\n"
    "▶️ Resume — pick up a saved game where you left off\n\n"
    "What'll it be?")


#: A FIXED, bundled projector image shown just before the welcome menu — a static part
#: of the project (never generated, never changes). Best-effort over the photo channel.
WELCOME_IMAGE = Path(__file__).resolve().parent.parent / "assets" / "welcome.png"


#: Sent the moment a build begins (the long generate-then-ingest). The per-phase
#: pings follow via the notify channel (INGEST-PROGRESS-NOTIFICATIONS.md).
BUILD_HEADS_UP = (
    "🌐 Constructing your world — the initial build may take ~20 minutes. "
    "I'll tell you the moment the doors open.")


#: The breath between a failed build attempt and its automatic retry (founder
#: 2026-07-06): long enough for a transient provider spell to pass, short
#: enough that the guest isn't left wondering.
BUILD_RETRY_DELAY_S = 20.0


#: Fired the instant the character is settled (the name turn), BEFORE the opening scene
#: renders — that first turn takes a bit (staging + the opening render), so the chat doesn't
#: sit silent while it works (founder).
OPENING_HEADS_UP = (
    "✨ Settling you into the world — the opening scene is being prepared. "
    "One moment…")
