"""The turn loop — TURN-LOOP.md's DAG over the frozen porcelain.

Serial mutation spine → assembly fan-out → narrator render → post
(render ingested as canon + concealment audit). One call = one turn;
state lives in the playthrough world file.

Read pattern: atoms read live canon directly (per-key folds are ~0.2ms
after pattern-buffer 037 made folds closure-scoped). Snapshots are taken
only where a materialized fact LIST is genuinely needed — the player-
frame briefing and the canon mirror. The earlier SnapshotReads batching
existed only for the pre-037 per-read cost (seconds per fold) and was
retired once that cost vanished (PB catch-up, re-measured 2026-06-16).

Failure policy (TURN-LOOP §5): spine steps loud-fail; fan-out cohorts
fail open with the drop logged; the narrator failing is the turn
failing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from construct import cohorts
from construct.adapter import PorcelainWorldReads
from construct.arc.executor import (
    SESSION,
    arc_concluded,
    arc_entities,
    arc_outcome,
    beat_pass,
    clock_pass,
    counters_from_session,
    navigate,
    turn_time,
)
from construct.arc.grammar import Arc
from construct.pins import resolve_active_pins
from construct.provider import Provider, ProviderError

logger = logging.getLogger(__name__)

_ABSENT = object()
_PIN_CAP = 6  # max pins surfaced per turn (Cx 062: cap + stable order)
#: The narrator's prose is staged here, NOT canon, so the ingest gate can
#: catch a contradiction of established canon before it overwrites it
#: (GATED-INGEST-COHORT; Cx round-robin). Non-contradicting rows promote to
#: canon; a row that changes an established value stays quarantined here for
#: arc review. Narrator-origin is stamped via `source` (PB 067).
_PROPOSED = "proposed:main"
_NARRATOR_SOURCE = "narrator"


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
    concluded: bool = False
    dropped_cohorts: list[str] = field(default_factory=list)
    furnished: list[str] = field(default_factory=list)
    point_reads: int = 0  # fallback per-key reads (the expensive kind)
    movement_status: str = ""  # route() passability: clear|blocked|obscured
    movement_obstruction: dict | None = None  # the blocking facts, for narration
    reveals: list = field(default_factory=list)  # (a,b) pairs correlated this turn (AKA reveal beats)
    outcome: str | None = None  # arc_outcome this turn: won|lost|None
    terminal: bool = False  # this turn ended the scenario (win_loss mode + outcome)
    pins: list = field(default_factory=list)  # (pin_id, scope_kind, salience) surfaced this turn
    contradictions: list = field(default_factory=list)  # narrator rows quarantined (changed established canon)

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


def _route_obstruction(p: Any, origin: str | None, target: str | None) -> dict | None:
    """First non-clear segment on origin->target via PB route() (RFC-003), or
    None. Fail-open: any route error => None => move proceeds unchecked. A
    `blocked` segment carries `evidence` (the portal's blocking fact); an
    `obscured` one a computed `unknown_basis`."""
    if not origin or not target or origin == target:
        return None
    try:
        r = p.route(origin, target)
    except Exception as exc:
        logger.warning("route() unavailable, movement unchecked: %s", exc)
        return None
    for seg in r.get("segments", []):
        if seg.get("status") in ("blocked", "obscured"):
            return seg
    return None


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


def _conclusion_recorded(reads: Any) -> bool:
    return bool(reads.events(kind="conclusion", frame=SESSION))


def terminal_outcome(reads: Any) -> str | None:
    """The recorded win/loss terminal of a `win_loss` scenario, or None if it
    hasn't ended (WIN-LOSS §10). Reads the SESSION receipt via `events()` (the
    same pattern as `_conclusion_recorded` — SESSION event rows are read by kind,
    not folded by `state()`); the outcome is encoded in the kind. Lets a
    transport stop ticking an ended story instead of re-rendering aftermath."""
    if reads.events(kind="arc_won", frame=SESSION):
        return "won"
    if reads.events(kind="arc_lost", frame=SESSION):
        return "lost"
    return None


def run_turn(world: Any, arc: Arc, provider: Provider, player_input: str,
             turn: int, scope: list[str] | None = None,
             mode: str = "pure", endless: bool = False,
             scenario_mode: str = "endless") -> TurnResult:
    """mode: 'pure' (canon-strict; the default for determined scenarios —
    declarations are refused, claimed items are adjudicated) or
    'coauthor' (the player may declare facts into the world).
    endless: when False (default) the arc concludes and the world settles
    into aftermath at its destination; when True the world has no terminal
    arc and carries on indefinitely (clocks/NPCs keep running)."""
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
        # The engine's refer (HD 003 fix) strips determiners and resolves
        # against a knows:-derived scope, so "where is my brass spoon?"
        # binds engine-side — the old host-side normalize-and-retry is
        # retired (PB catch-up).
        a = p.ask(player_input, frame=player_frame)
        prose = a.get("prose") if isinstance(a, dict) else getattr(a, "prose", None)
        facts = a.get("facts") if isinstance(a, dict) else getattr(a, "facts", [])
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
            # Passability (PB route(), RFC-003): a `blocked` way (a portal with a
            # blocking state/relation under the declared traversal policy) is not
            # walked — the narrator explains why. `obscured` (state unknown) is
            # allowed but flagged so the prose can hedge; missing capture degrades
            # to obscured/clear, never a false hard-block.
            origin = pre_chain[0] if pre_chain else None
            seg = _route_obstruction(p, origin, target)
            if seg and seg.get("status") == "blocked":
                trace.movement_status = "blocked"
                trace.movement_obstruction = seg
                logger.info("movement blocked: %s -> %s (%s)", arc.protagonist,
                            target, seg.get("evidence"))
            else:
                p.ingest_structured([{
                    "entity": arc.protagonist, "attribute": "in", "value": target,
                    "value_type": "entity", "valid_from": turn_time(turn),
                }])
                trace.movement_status = seg.get("status") if seg else "clear"
                if seg:
                    trace.movement_obstruction = seg
                logger.info("player moved: %s -> %s (%s)", arc.protagonist, target,
                            trace.movement_status)
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

    # 4. World tick (strict order; beats LAST). Atoms read LIVE canon
    #    directly: per-key folds are ~0.2ms post-engine-037 (were seconds
    #    pre-fix), so the SnapshotReads batching that existed only for the
    #    old cost is retired — and reading live is more correct (clocks
    #    and beats see this turn's own commits). Snapshots below are kept
    #    only where a materialized fact LIST is needed (briefing, mirror).
    counters = counters_from_session(live_reads, arc)
    trace.clocks_fired = clock_pass(world, arc, live_reads, counters, turn)

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
    achieved, closed, revealed = beat_pass(world, arc, live_reads, turn)
    trace.beats_achieved, trace.beats_closed = achieved, closed
    trace.reveals = revealed

    # ---- PINNED AWARENESS (PINNED-AWARENESS spec; reviews 060/062/063) ---
    # One awareness coordinate for the WHOLE assembly (Kernos 060 #2 / Cx #2):
    # region ancestry (the turn's current chain), the scene's present entities,
    # and the temporal window all resolve as-of the same `now`. Candidates come
    # from the arc's pin set (the host index, never a log scan).
    awareness_as_of = turn_time(turn)
    pin_subjects: set[tuple] = set()
    active_pins: list = []
    if arc.pins:
        present_entities = {e for (e, a), v in canon_table.items()
                            if a == "in" and v == scene}
        present_entities.add(arc.protagonist)
        try:  # `spent` pins recede permanently (Kernos 060 #6); none normally
            spent = {a for ev in live_reads.events(kind="pin_spent", frame=SESSION)
                     for a in ev.agents}
        except Exception:
            spent = set()
        active_pins = resolve_active_pins(
            arc.pins, ancestry=set(chain), present_entities=present_entities,
            as_of=awareness_as_of, spent=spent)
        pin_subjects = {ap.subject_key for ap in active_pins}
        trace.pins = [(ap.pin.pin_id, ap.pin.scope_kind, round(ap.salience, 3))
                      for ap in active_pins]

    # ---- ASSEMBLY FAN-OUT (reuses the tick's materializations) -----------
    # The protagonist's facts are recast as "you" and segregated — the
    # narrator must never see the player listed as a scene entity
    # (letter 025: the briefing itself was inviting third-person Marn).
    # A pinned subject is suppressed from the plain scene list and surfaced
    # ONLY in the PINS block, with its directive (dedupe, Kernos 060 #5).
    scene_lines, you_lines = [], []
    for f in player_snap.get("facts", []):
        if f["entity"] == arc.protagonist:
            you_lines.append(f"you · {f['attribute']} · {f['value']}")
        elif (f["entity"], f["attribute"]) in pin_subjects:
            continue
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

    # Conclusion detection (endless mode). Bounded worlds settle into
    # aftermath once the arc reaches its destination — the navigator
    # stops pushing toward an end already reached. Endless worlds note
    # the milestone but keep their pressure/clocks running indefinitely.
    concluded = arc_concluded(live_reads, arc)
    trace.concluded = concluded
    if concluded and not _conclusion_recorded(live_reads):
        p.ingest_structured([
            {"entity": f"event:conclusion_{turn}", "attribute": "kind",
             "value": "conclusion", "valid_from": turn_time(turn)},
        ], frame=SESSION)

    # Win/loss termination (WIN-LOSS §10): STRICTLY in `win_loss` mode (founder
    # ruling) — endless/freeplay never terminate. On the first won/lost, write
    # the one-time SESSION receipt; this turn renders the flavored aftermath, and
    # the transport stops ticking thereafter (Session reads terminal_outcome).
    outcome = arc_outcome(live_reads, arc)
    trace.outcome = outcome
    terminal = scenario_mode == "win_loss" and outcome is not None
    trace.terminal = terminal
    if terminal and terminal_outcome(live_reads) is None:
        p.ingest_structured([
            {"entity": f"event:arc_outcome_{turn}", "attribute": "kind",
             "value": f"arc_{outcome}", "valid_from": turn_time(turn)},
        ], frame=SESSION)

    counters = counters_from_session(live_reads, arc)
    rung = navigate(counters, len(diff), bool(achieved))
    if concluded and not endless:
        rung = None  # the arc has resolved; do not escalate toward a reached end
    trace.pacing = ("concluded" if (concluded and not endless)
                    else (rung.value if rung else "hold"))

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
    if active_pins:
        pin_lines = [f"[{ap.pin.scope_kind}] {ap.pin.directive}"
                     for ap in active_pins[:_PIN_CAP]]
        briefing_parts.append(
            "\nPINNED AWARENESS (foreground these — what is true and pressing "
            "here, ordered by urgency; weave in diegetically, do not list):\n"
            + "\n".join(pin_lines))
    if terminal:
        flavor = ("triumphant but earned — the goal is reached"
                  if outcome == "won" else
                  "somber — the goal is lost, the chance gone")
        briefing_parts.append(
            f"\nTHE STORY ENDS HERE ({outcome}). Render a final, buttoned-up "
            f"aftermath: {flavor}. Close the world's threads in the settled wake; "
            f"apply NO new pressure and open NO new hooks — this is the last beat.")
    elif concluded and not endless:
        briefing_parts.append("\nTHE ARC HAS RESOLVED — render this turn as "
                              "aftermath/denouement: the world responds to the "
                              "player in the settled wake of the story's end, "
                              "applying no new dramatic pressure.")
    if you_lines:
        briefing_parts.append("\nYOU (the player character; never a third party):\n"
                              + "\n".join(you_lines))
    briefing_parts.append(f"\nTHE PLAYER JUST DID (render exactly this, no more): "
                          f"{player_input}")
    if trace.movement_obstruction:
        seg = trace.movement_obstruction
        if trace.movement_status == "blocked":
            ev = seg.get("evidence") or []
            facts = "; ".join(
                f"{e.get('entity')} · {e.get('attribute')} · {e.get('value')}" for e in ev
            ) or "the way is obstructed"
            briefing_parts.append(
                f"\nMOVEMENT BLOCKED (render diegetically): the player tried to go there "
                f"but the way is barred — {facts}. Show the attempt and why it fails; "
                f"the player does NOT arrive.")
        else:  # obscured
            briefing_parts.append(
                "\nMOVEMENT UNCERTAIN (render diegetically): the state of the way can't be "
                "confirmed — render the passage as ambiguous; do NOT assert it is clearly open.")
    if trace.reveals:
        pairs = "; ".join(f"{a} is {b}" for a, b in trace.reveals)
        briefing_parts.append(
            f"\nREVEAL (render as the player's dawning recognition this turn): {pairs}. "
            f"Two figures the player took for separate are one. Dramatize the realization; "
            f"don't state it as a flat fact.")
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

    # ---- POST: INGEST GATE (GATED-INGEST-COHORT) --------------------------
    # The licensed narrator improvises freely WITHIN its grounding, but its
    # prose is not trusted straight to canon. Stage it in a quarantine frame,
    # then promote everything EXCEPT a row that overwrites an established canon
    # value (a contradiction) — those stay quarantined for arc review. New
    # facts and same-value restatements promote (so good improv — the drawer's
    # papers, the paperclip — is never blocked). Narrator-origin is stamped.
    pre_keys = {(row["entity"], row["attribute"]) for row in receipt_rows}
    pre_entities = {row["entity"] for row in receipt_rows}
    briefing_keys = set(player_table)
    license_tokens = set(
        f"{briefing}\n{player_input}".lower()
        .replace("’", "").replace("'", "")
        .replace(",", " ").replace(".", " ").replace(";", " ").replace(":", " ")
        .split())

    def _licensed(entity: str, attribute: str) -> bool:
        # Licensed = the narrator was GIVEN it: a briefing/player key, an entity
        # already in play, the scene, or an entity whose every name-token came
        # from the briefing+input (possessives normalized).
        if (entity, attribute) in briefing_keys or (entity, attribute) in pre_keys:
            return True
        if entity in pre_entities or entity == scene:
            return True
        name_tokens = entity.split(":", 1)[-1].replace("-", "_").split("_")
        return all(tok in license_tokens for tok in name_tokens if tok)

    canon_before = dict(canon_table)  # established values BEFORE this render
    staged = _receipt_rows(p.ingest(prose, scene=scene, at=turn_time(turn),
                                    source=_NARRATOR_SOURCE, frame=_PROPOSED))
    # the entities the narrator's prose touched (drop meta/assertion ids); read
    # their proposed-frame values (snapshot facts are fact-only — no meta noise)
    staged_entities = sorted({
        r["entity"] for r in staged
        if ":" in r["entity"] and not r["entity"].startswith(("a:", "attr:"))})
    proposed_vals = _table(_snap_or_empty(p, staged_entities, frame=_PROPOSED))

    promote: list[dict] = []
    contradictions: list[tuple] = []
    for (entity, attribute), newv in proposed_vals.items():
        established = canon_before.get((entity, attribute), _ABSENT)
        licensed_super = (entity, attribute) in pre_keys or (entity, attribute) in briefing_keys
        if established is not _ABSENT and established != newv and not licensed_super:
            contradictions.append((entity, attribute))  # narrator overwrote established truth
        else:
            promote.append({"entity": entity, "attribute": attribute, "value": newv})
    if promote:
        p.ingest_structured(promote, frame="canon")
        canon_table.update(_table(_snap_or_empty(p, snap_scope)))
        _mirror_rows(p, promote, player_frame, canon_table, trace)
    trace.contradictions = sorted(contradictions)

    leaked = [(it["entity"], it["attribute"]) for it in promote
              if not _licensed(it["entity"], it["attribute"])]
    audit = []
    if leaked:
        audit.append(f"unlicensed:{leaked[:5]}")
    if contradictions:
        audit.append(f"quarantined:{sorted(contradictions)[:5]}")
    trace.concealment_audit = "clean" if not audit else "FLAGGED: " + " ".join(audit)

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
