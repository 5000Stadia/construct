"""Experiment 2 — Flicker Replay (Emberroad2).

The ORIGINAL emberroad had a live incident: following "Lysa" (split
person:lysa / person:lysa_fen) and "Harth" (person:harth vs place:harth
homonym) made companions flicker in/out of presence.

The rebuilt world (emberroad2) sealed with:
  - the harth homonym REJECTED (same_as merge: person:harth -> place:harth)
  - lysa remaining as a background split (person:lysa + person:lysa_fen)

This replay probes whether the render now holds across 7 turns targeting
both split identities, then runs a state-audit at close.

Output: logs/replay-flicker-<ts>.md
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from construct import Session
from construct.adapter import PorcelainWorldReads
from construct.provider import CodexProvider

logging.basicConfig(level=logging.WARNING)

WORLD_NAME = "emberroad2"


def main() -> None:
    logs = Path("logs")
    logs.mkdir(exist_ok=True)
    ts = int(time.time())
    log_path = logs / f"replay-flicker-{ts}.md"

    provider = CodexProvider()
    s = Session.open(WORLD_NAME, player_id="founder", fresh=True, provider=provider)

    out = log_path.open("w", encoding="utf-8")

    def w(line: str = "") -> None:
        out.write(line + "\n")
        out.flush()

    w("# Replay — Flicker Probe (Emberroad2)")
    w()
    w("World: `emberroad2` — *The Ember That Burned Cold*")
    w()
    w("**Purpose:** Probe whether the Lysa-split and Harth-homonym fixes hold.")
    w("Lysa exists as two entities (person:lysa and person:lysa_fen).")
    w("Harth: person:harth was merged into place:harth via same_as at seal time.")
    w()
    w("## Opening")
    w()
    opening = s.opening()
    w("```")
    w(opening)
    w("```")
    w()

    def play(n: int, text: str, note: str = "") -> "Reply":  # noqa: F821
        if note:
            w(f"> _{note}_")
            w()
        w(f"### Turn {n}")
        w(f"**You:** {text}")
        w()
        reply = s.turn(text)
        prose = reply.prose or "(no prose)"
        w(f"**Narrator:** {prose}")
        w()
        t = reply.trace
        if t:
            w(
                f"`lifecycle={t.lifecycle}` · `arc_fallout={t.arc_fallout}` · "
                f"`ended={reply.ended}`"
            )
        else:
            w(f"(turn did not complete: ok={reply.ok})")
        w()
        return reply

    try:
        play(1, "I ask after Lysa — where is she now?",
             note="Lysa-locate probe. Checks if engine resolves 'Lysa' to a single entity.")

        play(2, "I go to find Lysa and greet her.",
             note="Lysa-locate + greeting. Does she appear in scene without flicker?")

        play(3, "I ask Lysa to walk with me a while.",
             note="Companion probe — Lysa as travelling companion.")

        play(4, "We walk on; I check Lysa is still beside me.",
             note="Presence-hold probe — the ORIGINAL flicker site. "
                  "Lysa should still be present without having self-exited.")

        play(5, "I ask about Harth — the place or the person?",
             note="Disambiguation probe. harth homonym: person:harth was merged into place:harth. "
                  "Engine should resolve 'Harth' as a PLACE.")

        play(6, "I travel toward Harth.",
             note="Place-sense probe — movement toward Harth as a location.")

        play(7, "I look for Harth himself.",
             note="Person-sense probe — engine should handle this gracefully "
                  "(place not person) without confusion.")

    finally:
        w("---")
        w()
        w("## State Audit")
        w()

        p = s._world.porcelain
        protagonist = s.protagonist

        w("### Entity locations")
        w()
        for eid in ["person:lysa", "person:lysa_fen", "person:harth", "place:harth", protagonist]:
            try:
                chain = p.locate(eid)
                w(f"- `{eid}` → `{chain}`")
            except Exception as exc:
                w(f"- `{eid}` → ERROR: {exc}")
        w()

        w("### Protagonist location")
        w()
        prot_loc = s.location()
        w(f"- Protagonist (`{protagonist}`) is at: `{prot_loc}`")
        w()

        w("### Lysa presence / companion state")
        w()
        # Check if Lysa is in same location as protagonist
        for lysa_id in ["person:lysa", "person:lysa_fen"]:
            try:
                lysa_chain = p.locate(lysa_id)
                prot_chain = p.locate(protagonist)
                co_present = bool(lysa_chain and prot_chain and lysa_chain[0] == prot_chain[0])
                w(f"- `{lysa_id}` location: `{lysa_chain}` | co-present with protagonist: {co_present}")
            except Exception as exc:
                w(f"- `{lysa_id}` locate error: {exc}")
        w()

        w("### Harth identity audit")
        w()
        # Check same_as / merge status
        for eid in ["person:harth", "place:harth"]:
            try:
                facts = p.facts("canon", entity=eid)
                rel_attrs = ["same_as", "distinct_from", "maybe_same_as", "kind", "in"]
                relevant = [f for f in facts if f.get("attribute") in rel_attrs]
                w(f"- `{eid}` relevant facts:")
                for f in relevant:
                    w(f"  - `{f.get('attribute')}`: `{f.get('value')}` (valid_from={f.get('valid', [None,None])[0]})")
                if not relevant:
                    w(f"  - (no relevant facts)")
            except Exception as exc:
                w(f"- `{eid}` error: {exc}")
        w()

        w("### Transcript prose contradiction check")
        w()
        w("Grep the prose above for Lysa present then absent without movement:")
        w("(manual: look for 'Lysa' appearing/disappearing without a travel turn between)")
        w()
        w("### Identity resolution check")
        w()
        # Check if person:lysa and person:lysa_fen are considered same
        try:
            lysa_facts = p.facts("canon", entity="person:lysa")
            lysa_same_as = [f for f in lysa_facts if f.get("attribute") == "same_as"]
            lysa_maybe = [f for f in lysa_facts if f.get("attribute") == "maybe_same_as"]
            lysa_distinct = [f for f in lysa_facts if f.get("attribute") == "distinct_from"]
            w(f"- person:lysa same_as: {[f.get('value') for f in lysa_same_as]}")
            w(f"- person:lysa maybe_same_as: {[f.get('value') for f in lysa_maybe]}")
            w(f"- person:lysa distinct_from: {[f.get('value') for f in lysa_distinct]}")
        except Exception as exc:
            w(f"- Lysa identity check error: {exc}")
        w()

        s.close()

    out.close()
    print(str(log_path))


if __name__ == "__main__":
    main()
