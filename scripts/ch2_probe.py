"""Retry the CH2 continuation leg on the concluded bodycase harness slot (eval #81)."""
import asyncio
import time
from pathlib import Path

from construct.game import continue_episode
from construct.provider import CodexProvider
from construct.session import Session

log = Path(f"logs/ch2-bodycase-{int(time.time())}.md")


def w(s: str) -> None:
    with log.open("a") as f:
        f.write(s + "\n")
    print(s, flush=True)


prov = CodexProvider()
_SCHEMA = {"type": "object", "properties": {"input": {"type": "string"}},
           "required": ["input"]}


def move(tail: str, note: str) -> str:
    p = ("You are the PLAYER of a text interactive fiction (protagonist 'you'). Story so far "
         f"(all you know):\n{tail}\n\nYour stance: {note}\nWrite ONLY the player's next input "
         "(1-2 sentences, natural).")
    return asyncio.run(prov.complete(p, _SCHEMA, tier="cheap"))["input"].strip()


w("# CH2 continuation probe — bodycase harness slot\n")
meta2 = continue_episode("bodycase", prov, player_id="harness",
                         on_stage=lambda m: w(f"*build: {m}*"))
s2 = Session.open("bodycase", player_id="harness", provider=prov)
if meta2.get("continuation_intro"):
    s2._meta["continuation_intro"] = meta2["continuation_intro"]
opening = s2.opening()
w("## CH2 OPENING\n\n" + opening + "\n")
story = opening
for j, st in enumerate(["FOLLOW the new hook", "draw on lived knowledge",
                        "FOLLOW the thread", "push an edge"], 1):
    try:
        inp = move(story[-4500:], st)
        r = s2.turn(inp)
        w(f"\n## CH2 Turn {j}\n\n> **Player:** {inp}\n\n" + (r.prose or "(empty)") + "\n")
        story += f"\n\n> You: {inp}\n\n{r.prose}"
    except Exception as exc:  # noqa: BLE001
        w(f"\n## CH2 Turn {j} — ERROR: {exc}\n")
s2.close()
w("\n--- END ---")
print("LOG:", log, flush=True)
