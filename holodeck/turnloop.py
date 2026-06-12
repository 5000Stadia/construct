"""The turn loop — TURN-LOOP.md's DAG over the frozen porcelain.

Serial mutation spine → assembly fan-out → narrator render → post
(render ingested as canon + concealment audit). One call = one turn;
state lives in the playthrough world file.

Read pattern (letter 022 / read-path scaling finding): the turn takes a
FEW materializations (canon scope, player frame, plot statuses) and
evaluates its many per-atom reads against them via SnapshotReads — one
rendered view, not N point reads. Point reads remain only for values
outside the cached scope (new entities), counted in the trace.

Failure policy (TURN-LOOP §5): spine steps loud-fail; fan-out cohorts
fail open with the drop logged; the narrator failing is the turn
failing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from holodeck import cohorts
from holodeck.adapter import PorcelainWorldReads
from holodeck.arc.executor import (
    PLOT,
    SESSION,
    arc_entities,
    beat_pass,
    clock_pass,
    counters_from_session,
    navigate,
    turn_time,
)
from holodeck.arc.grammar import Arc
from holodeck.provider import Provider, ProviderError
from holodeck.snapreads import SnapshotReads

logger = logging.getLogger(__name__)

_ABSENT = object()


@dataclass
class TurnTrace:
    """The --debug emission: a formatting of session/audit rows, never a
    second bookkeeping (CLI.md)."""

    turn: int
    classified: str = ""
    briefing_frames: list[str] = field(default_factory=list)
    cohort_calls: list[str] = field(default_factory=list)
    clocks_fired: list[str] = field(default_factory=list)
    beats_achieved: list[str] = field(default_factory=list)
    beats_closed: list[str] = field(default_factory=list)
    pacing: str = "hold"
    nudge: str | None = None
    irony_delta_size: int = -1
    concealment_audit: str = "not-run"
    player_boundary: str = "clean"
    adjudication: str = "allowed"
    dropped_cohorts: list[str] = field(default_factory=list)
    furnished: list[str] = field(default_factory=list)
    point_reads: int = 0  # fallback per-key reads (the expensive kind)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class TurnResult:
    prose: str
    trace: TurnTrace


def _player_frame(arc: Arc) -> str:
    return f"knows:{arc.protagonist}"


def _receipt_rows(receipt: Any) -> list[dict]:
    return receipt.to_dict()["rows"] if hasattr(receipt, "to_dict") else receipt["rows"]


def _snap_or_empty(p: Any, scope: list[str], frame: str = "canon") -> dict:
    if not scope:
        return {"facts": []}
    snap = p.snapshot(sorted(set(scope)), frame=frame)
    if "error" in snap:
        logger.warning("snapshot error for %s on %s: %s", frame, scope, snap["error"])
        return {"facts": []}
    return snap


def _plot_status_table(p: Any, arc: Arc, trace: TurnTrace) -> dict:
    """Beat/clock statuses from one plot-frame snapshot; per-key fallback
    when ids predate the slugify rule (snapshot rejects them)."""
    ids = [b.beat_id for b in arc.beats] + \
          [c.clock_id for c in arc.clocks] + [arc.refusal_clock.clock_id]
    snap = p.snapshot(ids, frame=PLOT) if ids else {"facts": []}
    if "error" not in snap and snap.get("facts"):
        return {"facts": [f for f in snap["facts"] if f["attribute"] == "status"]}
    facts = []
    for entity in ids:
        st = p.state(entity, "status", frame=PLOT)
        trace.point_reads += 1
        if st["status"] in ("known", "conflicted"):
            facts.append({"entity": entity, "attribute": "status",
                          "value": st["fact"]["value"]})
    return {"facts": facts}


def _mirror_rows(p: Any, rows: list[dict], frame: str,
                 canon_table: dict[tuple[str, str], object], trace: TurnTrace) -> None:
    """Mirror freshly-ingested canon facts into a knows: frame. Values
    come from the canon snapshot; point-read fallback for out-of-scope
    entities only."""
    items = []
    for row in rows:
        if row.get("frame") not in (None, "canon"):
            continue
        key = (row["entity"], row["attribute"])
        value = canon_table.get(key, _ABSENT)
        if value is _ABSENT:
            st = p.state(row["entity"], row["attribute"])
            trace.point_reads += 1
            if st["status"] != "known":
                continue
            value = st["fact"]["value"]
        items.append({"entity": row["entity"], "attribute": row["attribute"],
                      "value": value})
    if items:
        p.ingest_structured(items, frame=frame)


def furnish_scene(p: Any, scene: str | None, player_frame: str,
                  canon_table: dict, trace: TurnTrace) -> None:
    """Fiction-mode scene furnishing (letter 020 finding B): seed the
    description thunk through the gate, force via `resolve()` (resolver
    authority, generated provenance, constraint inheritance), mirror to
    the player frame. Memoized — stable on return; lazy — current scene
    only."""
    if scene is None or canon_table.get((scene, "description")) is not None:
        return
    st = p.state(scene, "description")
    trace.point_reads += 1
    if st["status"] != "unknown":
        return
    p.ingest_structured([{
        "entity": scene, "attribute": "description",
        "value": {"policy": "invent_under_canon"},
        "value_type": "unresolved",
    }])
    out = p.resolve(scene, "description")
    if out.get("status") != "resolved":
        logger.warning("scene furnish did not resolve: %s -> %s", scene, out.get("status"))
        return
    items = [{"entity": f["entity"], "attribute": f["attribute"], "value": f["value"]}
             for f in out.get("facts", []) if f.get("value") is not None]
    if items:
        p.ingest_structured(items, frame=player_frame)
        for item in items:
            canon_table[(item["entity"], item["attribute"])] = item["value"]
    trace.furnished.append(f"{scene}·description")
    logger.info("scene furnished: %s", scene)


def _table(snap: dict) -> dict[tuple[str, str], object]:
    return {(f["entity"], f["attribute"]): f["value"] for f in snap.get("facts", [])}


def adjudicate(world: Any, p: Any, protagonist: str, scene: str | None,
               requires: list[str]) -> str | None:
    """The Adjudicate faculty (letter 028, finding E): locate() is the
    rules lawyer. Each claimed item must resolve AND be at hand (its
    containment chain reaching the player or the current scene). Returns
    None if the action stands, else the denial reason. Deterministic
    after refer()."""
    for description in requires:
        res = world.refer(description, frame="canon")
        if getattr(res, "status", None) != "resolved" or not getattr(res, "entity_id", None):
            return (f"{description!r} is not a thing you are known to have — "
                    f"it has never been established in this world's canon")
        entity = res.entity_id
        chain = p.locate(entity)
        if protagonist not in chain and (scene is None or scene not in chain):
            where = chain[0] if chain else "nowhere known"
            return (f"{description!r} ({entity}) is not at hand — "
                    f"it is at {where}")
    return None


def normalize_question(question: str) -> str:
    """Possessive/article stripping for the ask() retry (letter 027
    finding D, host half): 'my brass measuring spoon' → 'brass measuring
    spoon'. The engine half (ask-path refer parity) is PB's."""
    import re
    return re.sub(r"\b(my|our|the|that|this|his|her|their)\s+", "", question,
                  flags=re.IGNORECASE)


def _protagonist_tokens(protagonist: str) -> list[str]:
    """Name fragments that mark third-person rendering of the player
    ('person:marn' -> 'marn'). Deterministic guard input (letter 025)."""
    slug = protagonist.split(":", 1)[-1]
    return [t for t in slug.replace("-", "_").split("_") if len(t) > 2]


def names_protagonist(text: str, protagonist: str) -> bool:
    lowered = f" {text.lower()} "
    return any(f" {tok}" in lowered.replace("’", " ").replace("'", " ")
               .replace(",", " ").replace(".", " ").replace(";", " ")
               for tok in _protagonist_tokens(protagonist))


def run_turn(world: Any, arc: Arc, provider: Provider, player_input: str,
             turn: int, scope: list[str] | None = None,
             mode: str = "pure") -> TurnResult:
    """mode: 'pure' (canon-strict; the default for determined scenarios —
    declarations are refused, claimed items are adjudicated) or
    'coauthor' (the player may declare facts into the world)."""
    p = world.porcelain
    live_reads = PorcelainWorldReads(world)
    trace = TurnTrace(turn=turn)
    player_frame = _player_frame(arc)

    # ---- SERIAL SPINE -----------------------------------------------------
    # 1. Classify (cheap; fail-open to action). Movement intent rides
    #    the same call.
    moves_to, requires = "", []
    try:
        verdict = cohorts.classify(provider, player_input)
        kind = verdict["kind"]
        moves_to = verdict.get("moves_to", "") or ""
        requires = [r for r in verdict.get("requires", []) if r]
        trace.cohort_calls.append("classify:cheap")
    except ProviderError as exc:
        kind = "action"
        trace.dropped_cohorts.append(f"classify ({exc})")
    trace.classified = kind

    if kind == "question":
        def _ask(q: str):
            a = p.ask(q, frame=player_frame)
            pr = a.get("prose") if isinstance(a, dict) else getattr(a, "prose", None)
            fx = a.get("facts") if isinstance(a, dict) else getattr(a, "facts", [])
            answered = a.get("answered") if isinstance(a, dict) else getattr(a, "answered", bool(fx))
            return answered, pr, fx

        answered, prose, facts = _ask(player_input)
        if not answered and not facts:
            normalized = normalize_question(player_input)
            if normalized != player_input:  # bounded retry (finding D, host half)
                answered, prose, facts = _ask(normalized)
        if not prose:
            prose = "; ".join(
                f"{f['entity']} {f['attribute']}: {f['value']}" for f in facts
            ) or "You can't say for certain."
        trace.concealment_audit = "n/a (ask path, frame-scoped)"
        return TurnResult(prose=prose, trace=trace)
    if kind == "ooc":
        return TurnResult(
            prose="(out of character) Noted. The world holds; say the word to continue.",
            trace=trace)

    if kind == "declaration" and mode == "pure":
        trace.adjudication = "denied: declarations are co-author moves; this scenario is canon-strict"
        return TurnResult(
            prose="(canon-strict) This world's facts are already written — "
                  "you can act in it, but not author it. State what you DO.",
            trace=trace)

    # 1b. Adjudication (letter 028, finding E): locate() is the rules
    #     lawyer. A failed precondition means the action DOES NOT COMMIT;
    #     the failure renders honestly and is receipted, never silent.
    pre_chain = p.locate(arc.protagonist)
    pre_scene = pre_chain[0] if pre_chain else None
    if requires and mode == "pure":
        denial = adjudicate(world, p, arc.protagonist, pre_scene, requires)
        if denial:
            trace.adjudication = f"denied: {denial}"
            prose = cohorts.narrate(
                provider,
                f"SCENE: you are at {pre_scene or 'an unresolved place'}.\n"
                f"THE PLAYER ATTEMPTED: {player_input}\n"
                f"ADJUDICATION (binding): the attempt FAILS — {denial}. "
                f"Render the failure honestly and diegetically; the world "
                f"does not bend.",
                arc.protagonist)
            trace.cohort_calls.append("narrate:main")
            p.ingest_structured([
                {"entity": f"event:turn_{turn}", "attribute": "kind",
                 "value": "turn", "valid_from": turn_time(turn)},
                {"entity": f"event:turn_{turn}", "attribute": "adjudication",
                 "value": trace.adjudication, "valid_from": turn_time(turn)},
            ], frame=SESSION)
            return TurnResult(prose=prose, trace=trace)

    # 2. Ingest the player's effect (loud-fail).
    receipt_rows = _receipt_rows(
        p.ingest(player_input, source=arc.protagonist, at=turn_time(turn)))

    # 2b. Movement (letter 026): the player's relocation commits
    #     deterministically — refer() resolves the destination as the
    #     player named it, the move goes through the gate as a stated
    #     item, and single-parent semantics supersede the old location.
    #     Unresolved destinations fall back to whatever extraction did,
    #     loudly logged.
    if moves_to:
        res = world.refer(moves_to, frame="canon")
        status = getattr(res, "status", None)
        target = getattr(res, "entity_id", None)
        if status == "resolved" and target:
            p.ingest_structured([{
                "entity": arc.protagonist, "attribute": "in", "value": target,
                "value_type": "entity", "valid_from": turn_time(turn),
            }])
            logger.info("player moved: %s -> %s", arc.protagonist, target)
        else:
            logger.warning("movement destination %r did not resolve (%s); "
                           "relying on extraction", moves_to, status)

    # 3. Scene + the canon materialization (ONE snapshot serves the tick).
    chain = p.locate(arc.protagonist)
    scene = chain[0] if chain else None
    if scope is None:
        scope = sorted(e for e in arc_entities(arc) if live_reads.has_entity(e))
        trace.point_reads += len(arc_entities(arc))
    snap_scope = list(scope) + ([scene] if scene else [])
    canon_snap = _snap_or_empty(p, snap_scope)
    canon_table = _table(canon_snap)

    _mirror_rows(p, receipt_rows, player_frame, canon_table, trace)
    touched = {row["entity"] for row in receipt_rows}
    if touched & arc_entities(arc):
        p.ingest_structured([
            {"entity": f"event:arc_touch_{turn}", "attribute": "kind",
             "value": "arc_touch", "valid_from": turn_time(turn)},
        ], frame=SESSION)

    # 4. World tick (strict order; beats LAST). Reads served from the
    #    materializations; writes go through the gate as ever.
    plot_snap = _plot_status_table(p, arc, trace)
    snap_reads = SnapshotReads(
        {"canon": canon_snap, PLOT: plot_snap}, events_fn=live_reads.events)
    counters = counters_from_session(snap_reads, arc)
    trace.clocks_fired = clock_pass(world, arc, snap_reads, counters, turn)

    furnish_scene(p, scene, player_frame, canon_table, trace)

    npcs = [e for e in scope
            if e.startswith("person:") and e != arc.protagonist
            and canon_table.get((e, "in")) == scene]
    for npc in npcs:  # decisions could parallelize; commits stay serial
        try:
            sheet = json.dumps(p.snapshot(npc, frame=f"knows:{npc}",
                                          lens="character_sheet"))[:4000]
            decision = cohorts.npc_world_action(provider, npc, sheet,
                                                json.dumps(canon_snap)[:4000],
                                                arc.protagonist)
            trace.cohort_calls.append(f"npc_action:{npc}:main")
            if decision["acts"] and decision["action"]:
                p.ingest(decision["action"], source=npc, at=turn_time(turn))
                canon_snap = _snap_or_empty(p, snap_scope)  # refresh: canon moved
                canon_table = _table(canon_snap)
        except ProviderError as exc:
            trace.dropped_cohorts.append(f"npc_action:{npc} ({exc})")

    player_snap = _snap_or_empty(p, snap_scope, frame=player_frame)
    snap_reads = SnapshotReads(
        {"canon": canon_snap, player_frame: player_snap, PLOT: plot_snap},
        events_fn=live_reads.events)
    achieved, closed = beat_pass(world, arc, snap_reads, turn)
    trace.beats_achieved, trace.beats_closed = achieved, closed

    # ---- ASSEMBLY FAN-OUT (reuses the tick's materializations) -----------
    # The protagonist's facts are recast as "you" and segregated — the
    # narrator must never see the player listed as a scene entity
    # (letter 025: the briefing itself was inviting third-person Marn).
    scene_lines, you_lines = [], []
    for f in player_snap.get("facts", []):
        if f["entity"] == arc.protagonist:
            you_lines.append(f"you · {f['attribute']} · {f['value']}")
        else:
            scene_lines.append(f"{f['entity']} · {f['attribute']} · {f['value']}")
    trace.briefing_frames = [player_frame]

    # Irony delta via the designed sixth read (frame_diff) — restored
    # after PB's indexed read path landed (letter 024; measured 0.68s on
    # the live world vs >250s pre-fix).
    player_table = _table(player_snap)
    diff = p.frame_diff("canon", player_frame, sorted(set(snap_scope)))
    threads = [f"{f['entity']} · {f['attribute']} · {f['value']}" for f in diff][:12]
    trace.irony_delta_size = len(diff)

    counters = counters_from_session(snap_reads, arc)
    rung = navigate(counters, len(diff), bool(achieved))
    trace.pacing = rung.value if rung else "hold"

    nudge_directive = None
    if rung and threads:
        try:
            pick = cohorts.nudge_pick(provider, rung.value, threads,
                                      "\n".join(scene_lines), arc.protagonist)
            trace.cohort_calls.append("nudge_pick:cheap")
            # Deterministic player-boundary guard (letter 025): a
            # directive that names the protagonist is re-asked once,
            # then DROPPED (fail-open) — pressure, never puppetry.
            if names_protagonist(pick["directive"], arc.protagonist):
                pick = cohorts.nudge_pick(provider, rung.value, threads,
                                          "\n".join(scene_lines), arc.protagonist)
                trace.cohort_calls.append("nudge_pick:cheap(re-ask)")
            if names_protagonist(pick["directive"], arc.protagonist):
                trace.dropped_cohorts.append("nudge (named the protagonist twice)")
            else:
                nudge_directive = pick["directive"]
                trace.nudge = nudge_directive
        except ProviderError as exc:
            trace.dropped_cohorts.append(f"nudge_pick ({exc})")

    npc_intents: list[str] = []
    for npc in npcs:  # sequential in v0; frame-scoped per NPC
        try:
            sheet = json.dumps(p.snapshot(npc, frame=f"knows:{npc}",
                                          lens="character_sheet"))[:4000]
            intent = cohorts.npc_intent(provider, npc, sheet,
                                        "\n".join(scene_lines)[:4000], arc.protagonist)
            trace.cohort_calls.append(f"npc_intent:{npc}:main")
            if intent["speaks"]:
                npc_intents.append(f"{npc}: wants {intent['intent']}"
                                   + (f" (voice: {intent['line_hint']})"
                                      if intent.get("line_hint") else ""))
        except ProviderError as exc:
            trace.dropped_cohorts.append(f"npc_intent:{npc} ({exc})")

    # ---- BRIEFING (no plot:, structurally — player-frame reads only) ----
    briefing_parts = [
        f"SCENE ({player_frame}):",
        "\n".join(scene_lines) or "(nothing established here yet — the grid shows through)",
    ]
    if you_lines:
        briefing_parts.append("\nYOU (the player character; never a third party):\n"
                              + "\n".join(you_lines))
    briefing_parts.append(f"\nTHE PLAYER JUST DID (render exactly this, no more): "
                          f"{player_input}")
    if npc_intents:
        briefing_parts.append("\nPRESENT CHARACTERS (play them by their wants):\n"
                              + "\n".join(npc_intents))
    if nudge_directive:
        briefing_parts.append(f"\nPACING DIRECTIVE (weave in diegetically): {nudge_directive}")
    briefing = "\n".join(briefing_parts)

    # ---- RENDER (loud-fail) ----------------------------------------------
    prose = cohorts.narrate(provider, briefing, arc.protagonist)
    trace.cohort_calls.append("narrate:main")
    # Deterministic player-boundary guard on the render: prose naming
    # the protagonist in third person gets ONE re-ask with the violation
    # named; a second violation ships but is flagged in the trace and
    # session receipts (visible to the live tester, never silent).
    if names_protagonist(prose, arc.protagonist):
        prose = cohorts.narrate(
            provider,
            briefing + f"\n\nVIOLATION TO FIX: your previous render named "
            f"{arc.protagonist} as a third-person character. They are 'you'. "
            f"Re-render without naming them.",
            arc.protagonist)
        trace.cohort_calls.append("narrate:main(re-ask)")
    if names_protagonist(prose, arc.protagonist):
        trace.player_boundary = "FLAGGED: protagonist named in third person"

    # ---- POST: render is canon; concealment audit -------------------------
    pre_keys = {(row["entity"], row["attribute"]) for row in receipt_rows}
    post_rows = _receipt_rows(p.ingest(prose, scene=scene, at=turn_time(turn)))
    canon_table.update(_table(_snap_or_empty(p, snap_scope)))
    _mirror_rows(p, post_rows, player_frame, canon_table, trace)

    briefing_keys = set(player_table)
    pre_entities = {row["entity"] for row in receipt_rows}
    # The license is what the narrator was GIVEN: the briefing (scene
    # facts incl. furnished descriptions, NPC intents, the nudge
    # directive) plus the player's own words. What it invents beyond
    # that stays flagged (letters 011/020/025). Token-subset matching:
    # an extracted entity is licensed when every word of its name was
    # given ("upper ribs patchwork dome" ⊆ "upper ribs of the Patchwork
    # Dome"; possessives normalized).
    license_tokens = set(
        f"{briefing}\n{player_input}".lower()
        .replace("’", "").replace("'", "")
        .replace(",", " ").replace(".", " ").replace(";", " ").replace(":", " ")
        .split())

    def _licensed(row: dict) -> bool:
        key = (row["entity"], row["attribute"])
        if key in briefing_keys or key in pre_keys:
            return True
        if row["entity"] in pre_entities or row["entity"] == scene:
            return True
        name_tokens = row["entity"].split(":", 1)[-1].replace("-", "_").split("_")
        return all(tok in license_tokens for tok in name_tokens if tok)

    leaked = [
        (row["entity"], row["attribute"]) for row in post_rows
        if row.get("frame") in (None, "canon") and not _licensed(row)
    ]
    trace.concealment_audit = "clean" if not leaked else f"FLAGGED: {leaked[:5]}"

    p.ingest_structured([
        {"entity": f"event:turn_{turn}", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(turn)},
        {"entity": f"event:turn_{turn}", "attribute": "pacing", "value": trace.pacing,
         "valid_from": turn_time(turn)},
        {"entity": f"event:turn_{turn}", "attribute": "concealment_audit",
         "value": trace.concealment_audit, "valid_from": turn_time(turn)},
        {"entity": f"event:turn_{turn}", "attribute": "player_boundary",
         "value": trace.player_boundary, "valid_from": turn_time(turn)},
    ], frame=SESSION)

    return TurnResult(prose=prose, trace=trace)


run_turn_sync = run_turn  # the v0 loop is synchronous end to end
