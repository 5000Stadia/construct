"""Live refinement checks (logged):
1. The refined CLASSIFIER on AMBIGUOUS / subtle input — in vs out of character,
   record query vs interrogating a witness, fiat declaration. The LLM should just
   GET it (freedom + subtlety), so these lean on judgment, not keywords.
2. CONDUIT (the host persona) answering OOC turns end-to-end — incl. "have I won
   yet?" — voiced as the host, non-spoiling.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (input, what a human would say it is) — several deliberately subtle.
AMBIGUOUS = [
    ("Hand over the ledger, Cray.", "in-character command → action"),
    ("Tovan didn't steal anything.", "in-character dialogue → action"),
    ("I trust no one in this office.", "in-character reflection → action"),
    ("Tell me everything, Cray — now.", "interrogating a witness → action"),
    ("\"You signed the decommission order,\" I say to Cray.", "quoted dialogue → action"),
    ("I cross to the records vault.", "movement → action + moves_to"),
    ("is the vault locked?", "record query → question"),
    ("who is Cray?", "record query → question"),
    ("what does the master meter actually measure?", "record/lore query → question"),
    ("who is Cray again?", "meta memory-jog → question or ooc (borderline)"),
    ("wait, have I won yet?", "meta game-state → ooc"),
    ("what can I do here?", "meta → ooc"),
    ("ugh, I keep getting lost in the layout", "meta confusion → ooc"),
    ("save my progress", "meta → ooc"),
    ("(can we pause?)", "meta → ooc"),
    ("There's a hidden door behind Cray's desk.", "authoring by fiat → declaration"),
]

OOC_TURNS = [
    "have I won yet?",
    "what happens if I accuse the wrong person?",
    "how do I save?",
]


def main() -> None:
    from construct import Session, cohorts
    from construct.provider import CodexProvider

    logs = Path("logs"); logs.mkdir(exist_ok=True)
    ts = os.environ.get("LIVEPLAY_TS", "manual")
    log = (logs / f"refine-validation-{ts}.md").open("w")

    def w(line=""):
        log.write(line + "\n"); log.flush()

    prov = CodexProvider()

    w("# Refinement validation — intent, ambiguity, and Conduit\n")
    w("## 1. Classifier on ambiguous / subtle input\n")
    w("| input | a human would say | kind | moves_to |")
    w("|-------|-------------------|------|----------|")
    for text, expected in AMBIGUOUS:
        try:
            v = cohorts.classify(prov, text)
            w(f"| {text[:48]} | {expected.split('→')[-1].strip()} | "
              f"**{v.get('kind')}** | {v.get('moves_to') or ''} |")
        except Exception as exc:  # noqa: BLE001
            w(f"| {text[:48]} | {expected} | ERROR: {exc} | |")
    w()

    w("## 2. Conduit (host persona) answering OOC, end-to-end\n")
    w("Run through a real turn (classify → ooc → Conduit). The world does NOT "
      "advance; Conduit speaks as host, never spoiling the hidden win.\n")
    s = Session.open("anchor", player_id="refine_ooc", fresh=True, provider=prov)
    for text in OOC_TURNS:
        w(f"**You (out of character):** {text}\n")
        reply = s.turn(text)
        w(f"{reply.prose}\n")
    s.close()
    log.close()
    print(str(Path(log.name)))


if __name__ == "__main__":
    main()
