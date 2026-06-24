"""LIVE long-form validation of the narrative-memory Ledger (logged for the founder).

Plays the generated dragon world for ~9 turns with a SMALL window (RECENT_TURNS=3,
COMPACT_BATCH=2) so the real `compact_memory` cohort actually FIRES (~turn 6) — the
one part the unit tests stub. The decisive test: an early VOW (turn 2) ages out of
the verbatim window; does the compacted NARRATIVE MEMORY carry it forward so the
narrator still honours it many turns later (memory, not retrieval)?

Logs each turn's prose, whether compaction fired, and the evolving narrative memory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Tune the window SMALL so compaction fires within a short live run (read at import).
os.environ.setdefault("CONSTRUCT_RECENT_TURNS", "3")
os.environ.setdefault("CONSTRUCT_COMPACT_BATCH", "2")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCENARIO = "memtestworld"
MEM = "session:narrative_memory"
SESSION = "session:main"
KNIGHT = "person:knight"
KF = f"knows:{KNIGHT}"


def author_endless_world():
    """A compact ENDLESS fantasy world (no win terminal, so it can't end on turn 1
    — the bug that foiled the first run). Vivid named entities seeded into the
    player frame; a non-terminating arc; a fantasy voice."""
    import json
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from construct.arc import io as arc_io
    from construct.arc.conditions import InFrame, TurnsQuiet
    from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
    from construct.arc.executor import turn_time
    from construct.game import scenario_path, WORLDS_DIR
    from construct.semantics import attribute_default

    WORLDS_DIR.mkdir(exist_ok=True)
    spath = scenario_path(SCENARIO)
    for suf in (".world", ".meta.json"):
        (spath if suf == ".world" else spath.with_suffix(".meta.json")).unlink(missing_ok=True)
    for slot in WORLDS_DIR.glob(f"{SCENARIO}.*.world"):
        slot.unlink()
    rule = rule_classifier_fallback()

    def fb(prompt, schema):
        return rule(prompt, schema) if prompt.startswith("Classify the lifetime") else {"items": []}

    w = World(spath, world_id=f"w:{SCENARIO}", model=StubModel(fallback=fb),
              stance="fiction", title="The Long Winter of Ashenpeak",
              attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)
    canon = [
        {"entity": "place:abbey", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": KNIGHT, "attribute": "kind", "value": "person", "timeless": True},
        {"entity": KNIGHT, "attribute": "in", "value": "place:abbey"},
        {"entity": "obj:altar", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:altar", "attribute": "name", "value": "the abbey altar", "timeless": True},
        {"entity": "obj:altar", "attribute": "in", "value": "place:abbey"},
        {"entity": "person:monk", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:monk", "attribute": "name", "value": "the eldest monk", "timeless": True},
        {"entity": "obj:bell", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:bell", "attribute": "name", "value": "the spring-feast bell", "timeless": True},
        {"entity": "fact:fire", "attribute": "kind", "value": "proposition", "timeless": True},
    ]
    w.ingest_structured(canon)
    w.porcelain.ingest_structured([
        {"entity": KNIGHT, "attribute": "in", "value": "place:abbey"},
        {"entity": "obj:altar", "attribute": "in", "value": "place:abbey"},
        {"entity": "obj:altar", "attribute": "name", "value": "the abbey altar"},
        {"entity": "person:monk", "attribute": "in", "value": "place:abbey"},
        {"entity": "person:monk", "attribute": "name", "value": "the eldest monk"},
        {"entity": "obj:bell", "attribute": "name", "value": "the spring-feast bell"},
    ], frame=KF)
    beat = Beat("beat:never", Phase.CLIMAX, Weight.REQUIRED,
                achievable_via=InFrame(KF, "fact:fire", "truth", "never"))
    refusal = Clock("clock:refusal", TurnsQuiet(999),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape("shape:main", "drive_inverted", (KNIGHT, "drive:duty", "drive:fear"),
                            world_condition=InFrame(KF, "fact:fire", "truth", "never"),
                            premise=InFrame("canon", KNIGHT, "kind", "person"),
                            refusal_variant_id="shape:refused")
    arc = Arc("arc:main", KNIGHT, shape, (beat,), (), refusal, 1, ("beat:never",),
              {Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3, Phase.CLIMAX: 2,
               Phase.FALLING: 2})
    w.porcelain.ingest_structured(arc_io.arc_to_items(arc) + arc_io.index_items(arc)
                                  + arc_io.portfolio_items(["arc:main"]))
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame=SESSION)
    w.close()
    spath.with_suffix(".meta.json").write_text(json.dumps({
        "title": "The Long Winter of Ashenpeak", "protagonist": KNIGHT, "stance": "fiction",
        "mode": "pure", "scenario_mode": "endless", "endless": True,
        "style": "Austere medieval winter-fable: ash-cold, monastic, plain grave "
                 "diction, wonder and dread entering like breath in frost.",
        "intro": "Ashenpeak lies under a vowed silence of snow; the abbey bells hang "
                 "frozen and the folk count crusts against a winter that will not break.",
        "arc_scope": [KNIGHT, "person:monk", "obj:altar", "obj:bell", "fact:fire", "place:abbey"],
        "main_arc": "arc:main", "arc_ids": ["arc:main"],
    }, indent=2))

# Thread-building inputs. Turn 2 plants a VOW that must persist via memory after it
# ages out of the 3-beat verbatim window (boundary 5; first compaction ~turn 6).
TURNS = [
    "I stand in the frozen vale and take the measure of the abbey and the black heights above.",
    "I kneel at the abbey altar and swear a vow aloud: I will break the long winter before the bell tolls for the spring feast.",
    "I seek out the eldest monk and ask what the mountain's fire truly is.",
    "I search the abbey's oldest records for any account of the dragon.",
    "I gather what gear the vale can spare and start up toward the heights.",
    "I read the snow as I climb — tracks, scorch, anything that betrays the beast.",
    "I make camp on the ridge and watch the lair through the failing dusk.",
    "I look for a way into the lair that is not the front maw.",
    "I steel myself, the vale far below, and press toward the dragon.",
]


def main() -> None:
    from construct import Session
    from construct.provider import CodexProvider

    logs = Path("logs"); logs.mkdir(exist_ok=True)
    ts = os.environ.get("LIVEPLAY_TS", "manual")
    log = (logs / f"liveplay-memory-{ts}.md").open("w")

    def w(line=""):
        log.write(line + "\n"); log.flush()

    w("# Live long-form validation — the narrative-memory Ledger")
    w()
    author_endless_world()
    w(f"World: **{SCENARIO}** (endless). Window tuned small (RECENT_TURNS=3, COMPACT_BATCH=2) so "
      f"the real `compact_memory` cohort fires within a short run. **The test:** the "
      f"VOW sworn at the altar on turn 2 ages out of the verbatim window — does the "
      f"compacted NARRATIVE MEMORY carry it so the narrator still honours it later "
      f"(memory, not fact-retrieval)?")
    w()

    s = Session.open(SCENARIO, player_id="memtest", fresh=True, provider=CodexProvider())
    p = s._world.porcelain

    def memory_now():
        st = p.state(MEM, "text", frame=SESSION)
        return st["fact"]["value"] if st.get("status") == "known" else ""

    w("## Opening\n```")
    w(s.opening())
    w("```\n")

    for n, text in enumerate(TURNS, start=1):
        w(f"### Turn {n}")
        w(f"**You:** {text}\n")
        reply = s.turn(text)
        w(f"**Narrator:** {reply.prose}\n")
        fired = bool(reply.trace and "compact_memory:main" in reply.trace.cohort_calls)
        mem = memory_now()
        w(f"`compaction_fired={fired}`")
        if mem:
            w(f"\n**NARRATIVE MEMORY now:**\n> " + mem.replace("\n", "\n> "))
        w()

    # Decisive checks.
    w("## Verdict\n```")
    final_mem = memory_now().lower()
    w(f"narrative memory present: {bool(final_mem)}")
    w(f"memory carries the VOW (altar/vow/winter/feast): "
      f"{any(k in final_mem for k in ('vow', 'altar', 'feast', 'swore', 'swear'))}")
    # archive recoverability: the turn-1 beat is still retrievable verbatim
    arch1 = p.state('arch:turn_1', 'prose', frame=SESSION)
    w(f"archive turn_1 retrievable: {arch1.get('status') == 'known'}")
    # membrane: narrative memory is NOT in canon
    w(f"narrative memory kept OUT of canon: {p.state(MEM, 'text')['status'] != 'known'}")
    w("```")
    s.close()
    log.close()
    print(str(Path(log.name)))


if __name__ == "__main__":
    main()
