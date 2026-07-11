"""DRIFT D3 live acceptance — alternative-path repair, real CodexProvider.

The spec's D3 close-out (DRIFT-HANDLING.md §7), run against the whole folded
contract (cr rounds 1-7):

  T1  settle in (baseline fiction).
  --  the miller DIES in canon (the D-HARD world-state that forecloses the
      authored route; he is also the witness's driving entity).
  T2  the beat closes D-HARD; repair finds the LIVE second carrier (Carter),
      HOST-re-mints the beat's own mechanic as beat:discover_r1, and the
      cohort's hook renders diegetically — a new road opens in the fiction.
  T3  the channel is KILLED (canon alive=false — the mutation repair AND
      delivery both reject); the player addresses the dead man: no clue is
      delivered, and no npc_turn cohort receipt is written.
  --  the ledgers BURN (the second required beat's D-HARD trigger; its ONLY
      holder is the dead Carter).
  T4  the second beat closes; repair declines no_delivery_channel — no
      zombie re-mint is created; the budget survives.
  --  the player's abandonment lands (event:abandoned).
  T5  the refusal fires; arc_lifecycle reads INCOMPLETABLE — the honest
      terminal, never an immortal pending beat.

Usage:  .venv/bin/python scripts/probe_d3_repair.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("probe_d3")

TS = int(time.time())
LOG_PATH = Path(f"logs/probe_d3-{TS}.md")
LOG_PATH.parent.mkdir(exist_ok=True)
_lines: list[str] = []

NAME = "probe_d3_repair"


def _log(*parts) -> None:
    msg = " ".join(str(p) for p in parts)
    print(msg, flush=True)
    _lines.append(msg)


def _flush() -> None:
    LOG_PATH.write_text("\n".join(_lines) + "\n")


def _wipe() -> None:
    for p in Path("worlds").glob(f"{NAME}*"):
        p.unlink(missing_ok=True)


def _author() -> None:
    from patternbuffer import World
    from patternbuffer.testing import StubModel, rule_classifier_fallback
    from construct.semantics import attribute_default
    from construct.arc import io as arc_io
    from construct.arc.conditions import InFrame, Occurred, StateIs
    from construct.arc.executor import SESSION, turn_time
    from construct.arc.grammar import (Arc, Beat, Clock, ConclusionShape, Phase,
                                       Rung, Weight)

    _wipe()
    path = Path(f"worlds/{NAME}.world")
    rule = rule_classifier_fallback()

    def fallback(prompt, schema):
        if prompt.startswith("Classify the lifetime"):
            return rule(prompt, schema)
        return {"items": []}

    w = World(path, world_id=f"w:{NAME}", model=StubModel(fallback=fallback),
              stance="fiction", title="The Wet Mill", attribute_default=attribute_default)
    w.ingestor.cursor.advance(1.0)
    w.ingest_structured([
        {"entity": "place:village", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:village", "attribute": "name", "value": "Bracken village", "timeless": True},
        {"entity": "place:taproom", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:taproom", "attribute": "name", "value": "the taproom", "timeless": True},
        {"entity": "place:taproom", "attribute": "in", "value": "place:village", "timeless": True},
        {"entity": "place:taproom", "attribute": "description",
         "value": "The inn's low taproom: settle fire, rain on the panes, a few corner tables.",
         "timeless": True},
        {"entity": "place:mill", "attribute": "kind", "value": "place", "timeless": True},
        {"entity": "place:mill", "attribute": "name", "value": "the wet mill", "timeless": True},
        {"entity": "place:mill", "attribute": "in", "value": "place:village", "timeless": True},
        # the player
        {"entity": "person:vale", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:vale", "attribute": "name", "value": "Vale", "timeless": True},
        {"entity": "person:vale", "attribute": "in", "value": "place:taproom"},
        {"entity": "person:vale", "attribute": "role",
         "value": "an assessor sent to settle the mill accounts", "timeless": True},
        # the AUTHORED route: the miller, away at the mill
        {"entity": "person:miller", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:miller", "attribute": "name", "value": "Aldous the miller", "timeless": True},
        {"entity": "person:miller", "attribute": "in", "value": "place:mill"},
        {"entity": "person:miller", "attribute": "role", "value": "the miller", "timeless": True},
        # the SECOND carrier: the mill's carter, in the taproom
        {"entity": "person:carter", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:carter", "attribute": "name", "value": "Brann the carter", "timeless": True},
        {"entity": "person:carter", "attribute": "in", "value": "place:taproom"},
        {"entity": "person:carter", "attribute": "role",
         "value": "the mill's carter, who hauled every load the books describe", "timeless": True},
        {"entity": "person:carter", "attribute": "drive",
         "value": "to see the shortfall pinned where it belongs, not on the wagons",
         "timeless": True},
        # the innkeeper (texture)
        {"entity": "person:keeper", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:keeper", "attribute": "name", "value": "Sef the innkeeper", "timeless": True},
        {"entity": "person:keeper", "attribute": "in", "value": "place:taproom"},
        {"entity": "person:keeper", "attribute": "role", "value": "the innkeeper", "timeless": True},
        # the hidden truths + their objects (the fact entity REGISTERS like a
        # real build would — run 2 finding: a kind-less fact fails has_entity
        # and the repair lint honestly declines the re-mint as impossible)
        {"entity": "fact:shortfall", "attribute": "kind", "value": "fact",
         "timeless": True},
        {"entity": "fact:shortfall", "attribute": "culprit", "value": "person:factor",
         "timeless": True},
        {"entity": "fact:shortfall", "attribute": "proof", "value": "ledger_hand",
         "timeless": True},
        {"entity": "person:factor", "attribute": "kind", "value": "person", "timeless": True},
        {"entity": "person:factor", "attribute": "name", "value": "the grain factor", "timeless": True},
        {"entity": "person:factor", "attribute": "in", "value": "place:village"},
        {"entity": "obj:ledgers", "attribute": "kind", "value": "object", "timeless": True},
        {"entity": "obj:ledgers", "attribute": "name", "value": "the mill ledgers", "timeless": True},
        {"entity": "obj:ledgers", "attribute": "in", "value": "place:mill"},
    ])

    discover = Beat(
        "beat:discover", Phase.CLIMAX, Weight.REQUIRED,
        achievable_via=InFrame("knows:person:vale", "fact:shortfall", "culprit",
                               "person:factor"),
        unreachable_if=StateIs("person:miller", "state", "dead"),
    )
    attest = Beat(
        "beat:attest", Phase.CLIMAX, Weight.REQUIRED,
        achievable_via=InFrame("knows:person:vale", "fact:shortfall", "proof",
                               "ledger_hand"),
        unreachable_if=StateIs("obj:ledgers", "state", "burned"),
    )
    refusal = Clock("clock:refusal", Occurred("event:abandoned"),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    shape = ConclusionShape(
        "shape:main", "desire_at_cost",
        ("person:vale", "drive:the_truth_of_the_books", "fear:a_false_report"),
        world_condition=InFrame("knows:person:vale", "fact:shortfall", "culprit",
                                "person:factor"),
        premise=InFrame("canon", "fact:shortfall", "culprit", "person:factor"),
        refusal_variant_id="shape:refused",
    )
    arc = Arc(
        arc_id="arc:main", protagonist="person:vale", shape=shape,
        beats=(discover, attest), clocks=(), refusal_clock=refusal,
        climax_ready_k=1, climax_ready_beats=("beat:discover",),
        phase_budget={Phase.SETUP: 5, Phase.RISING: 5, Phase.CRISIS: 3,
                      Phase.CLIMAX: 2, Phase.FALLING: 2},
    )
    items = arc_io.arc_to_items(arc) + arc_io.index_items(arc)
    items += arc_io.portfolio_items(["arc:main"], main_arc_id="arc:main")
    w.porcelain.ingest_structured(items)
    w.porcelain.ingest_structured(
        [{"entity": "event:turn_0", "attribute": "kind", "value": "turn",
          "valid_from": turn_time(0)}], frame=SESSION)
    w.close()

    path.with_suffix(".meta.json").write_text(json.dumps({
        "title": "The Wet Mill", "protagonist": "person:vale",
        "stance": "fiction", "mode": "pure", "scenario_mode": "endless",
        "style": ("Rain-country procedural, plain prose. The village keeps its own "
                  "hours; people cross the green on their errands."),
        "intro": ("You are Vale, an assessor sent to settle the wet mill's accounts — "
                  "a shortfall someone will answer for. Aldous the miller waits at the "
                  "mill with the ledgers. You have taken a corner table in the taproom; "
                  "Brann the carter nurses a cup by the fire, and Sef the innkeeper "
                  "minds the hearth."),
        "goal_statement": "learn who is behind the mill shortfall",
        "arc_scope": ["person:vale", "person:miller", "person:carter", "person:keeper",
                      "person:factor", "place:taproom", "place:mill", "place:village",
                      "fact:shortfall", "obj:ledgers"],
        "main_arc": "arc:main", "arc_ids": ["arc:main"],
        "cast": {
            "pillars": [{"id": "pillar:books", "label": "the mill books",
                         "required": True}],
            "cast": [{
                "id": "person:miller",
                "location": "place:mill",
                "surface_role": "the miller with the ledgers",
                "clues": [{
                    "clue_id": "clue:ledger", "pillar_id": "pillar:books",
                    "fact": {"entity": "fact:shortfall", "attribute": "culprit",
                             "value": "person:factor"},
                }],
            }, {
                "id": "person:carter",
                "location": "place:taproom",
                "surface_role": "the carter who hauled the loads",
                "clues": [{
                    "clue_id": "clue:loads", "pillar_id": "pillar:books",
                    "fact": {"entity": "fact:shortfall", "attribute": "culprit",
                             "value": "person:factor"},
                    "reveal_gate": "pressure",
                }, {
                    "clue_id": "clue:hand", "pillar_id": "pillar:books",
                    "fact": {"entity": "fact:shortfall", "attribute": "proof",
                             "value": "ledger_hand"},
                    "reveal_gate": "pressure",
                }],
            }],
        },
    }, indent=2))
    _log(f"  [author] world written to {path}")


def _turn(s, move: str, label: str):
    _log(f"\n  > {label}")
    _log(f"    PLAYER: {move!r}")
    r = s.turn(move)
    s.flush_settle()
    t = r.trace
    _log(f"    PROSE (first 400): {(r.prose or '')[:400]!r}")
    _log(f"    drift={getattr(t, 'drift', None)} repairs={getattr(t, 'repairs', None)}")
    if getattr(t, "repair_directive", ""):
        _log(f"    REPAIR DIRECTIVE: {t.repair_directive!r}")
    _log(f"    learned={getattr(t, 'learned_clues', None)} "
         f"cohorts={[c for c in getattr(t, 'cohort_calls', []) if 'npc_turn' in c or 'rpr' in c or 'repair' in c]}")
    _flush()
    return r


def main() -> None:
    _log("=" * 70)
    _log("PROBE D3 — DRIFT alternative-path repair live acceptance (spec §7 D3)")
    _log("=" * 70)
    _author()

    from construct.session import Session
    from construct.provider import CodexProvider
    from construct.adapter import PorcelainWorldReads
    from construct.arc import drift
    from construct.arc.executor import PLOT, SESSION, active_beats, arc_lifecycle, turn_time

    s = Session.open(NAME, provider=CodexProvider(), player_id="probe_d3", fresh=True)
    p = s._world.porcelain  # probe-only reach
    reads = PorcelainWorldReads(s._world)
    verdicts: list[tuple[str, bool, str]] = []

    def V(name: str, ok: bool, detail: str = "") -> None:
        verdicts.append((name, bool(ok), detail))
        _log(f"    [{'PASS' if ok else 'FAIL'}] {name} {detail}")

    # ---- T1: baseline
    _turn(s, "I take stock of the taproom and my notes.", "T1 settle-in")

    # ---- the D-HARD closure: the miller dies in canon
    _log("\n  [probe] canon mutation: the miller dies (the authored route forecloses)")
    p.ingest_structured([
        {"entity": "person:miller", "attribute": "state", "value": "dead",
         "valid_from": turn_time(2)},
    ])

    # ---- T2: closure + repair (the live second carrier) + the hook renders
    r2 = _turn(s, "I go over the delivery tallies line by line.",
               "T2 the road dies; a new one opens")
    t2 = r2.trace
    V("T2 beat closed D-HARD",
      ("beat:discover", "D-HARD") in (t2.drift or []), str(t2.drift))
    V("T2 repair re-minted _r1",
      (t2.repairs or []) == [("beat:discover", "beat:discover_r1", "replace")],
      str(t2.repairs))
    V("T2 hook directive present", bool(getattr(t2, "repair_directive", "")))
    w = drift.read_closure_witness(reads, "beat:discover")
    V("T2 witness drives the miller",
      (w or {}).get("driving_entities") == ["person:miller"], str((w or {}).get("driving_entities")))
    live = [b.beat_id for b in active_beats(reads, s._arc)]
    V("T2 active set carries the replacement", "beat:discover_r1" in live, str(live))
    V("T2 spend == 1", drift.repair_spent(reads, "arc:main") == 1,
      str(drift.repair_spent(reads, "arc:main")))

    # ---- kill the channel: the carter dies (repair AND delivery reject this)
    _log("\n  [probe] canon mutation: the carter dies (alive=false — the channel-kill)")
    p.ingest_structured([
        {"entity": "person:carter", "attribute": "alive", "value": "false",
         "valid_from": turn_time(3)},
    ])

    # ---- T3: the dead man cannot deliver, and no cohort receipt is written
    r3 = _turn(s, "I press Brann the carter: who signed for the missing loads?",
               "T3 the corpse cannot speak")
    t3 = r3.trace
    V("T3 no clue from the dead holder", not (t3.learned_clues or []),
      str(t3.learned_clues))
    V("T3 no npc_turn receipt for the dead holder",
      not any("person:carter" in c for c in (t3.cohort_calls or [])),
      str([c for c in (t3.cohort_calls or []) if "npc_turn" in c]))

    # ---- the second D-HARD: the ledgers burn (its ONLY holder is dead)
    _log("\n  [probe] canon mutation: the ledgers burn (the second route forecloses)")
    p.ingest_structured([
        {"entity": "obj:ledgers", "attribute": "state", "value": "burned",
         "valid_from": turn_time(4)},
    ])

    # ---- T4: the honest decline — no zombie re-mint
    r4 = _turn(s, "I sit with what little I have and think it through.",
               "T4 no road can open")
    t4 = r4.trace
    V("T4 attest closed D-HARD",
      any(b == "beat:attest" and c == "D-HARD" for b, c in (t4.drift or [])),
      str(t4.drift))
    V("T4 no repair minted", not (t4.repairs or []), str(t4.repairs))
    reasons = {rr.value for e in reads.events(kind="repair_declined", frame=SESSION)
               for rr in reads.frame_rows(SESSION, entity=e.event_id)
               if rr.attribute == "reason"}
    V("T4 declined no_delivery_channel", "no_delivery_channel" in reasons,
      str(sorted(reasons)))
    V("T4 no zombie beat rows",
      reads.state("beat:attest_r1", "part_of", frame=PLOT) is None)
    V("T4 budget survived the decline",
      drift.repair_spent(reads, "arc:main") == 1,
      str(drift.repair_spent(reads, "arc:main")))

    # ---- the abandonment: the refusal backstop
    _log("\n  [probe] canon mutation: the player's abandonment lands (event:abandoned)")
    p.ingest_structured([
        {"entity": "event:abandon_probe", "attribute": "kind",
         "value": "event:abandoned", "valid_from": turn_time(5)},
    ])

    # ---- T5: the refusal fires; incompletable, never a zombie
    r5 = _turn(s, "I close my case and call for my coat.", "T5 the verdict")
    t5 = r5.trace
    V("T5 refusal fired", "clock:refusal" in (t5.clocks_fired or []),
      str(t5.clocks_fired))
    V("T5 lifecycle reads INCOMPLETABLE",
      arc_lifecycle(reads, s._arc) == "incompletable",
      arc_lifecycle(reads, s._arc))
    V("T5 no repair burned on the verdict", not (t5.repairs or []), str(t5.repairs))

    _log("\n" + "=" * 70)
    fails = [v for v in verdicts if not v[1]]
    _log(f"VERDICTS: {len(verdicts) - len(fails)}/{len(verdicts)} PASS")
    for name, ok, detail in verdicts:
        _log(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")
    _log("=" * 70)
    _flush()
    s.close()
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
