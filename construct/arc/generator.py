"""The opportunistic DM generator (LIVING-WORLD-GENERATOR P2a+P2b+P2c).

A paced, fail-open host orchestration that mints fresh side arcs from the world's
standing tensions, through the EXISTING arc grammar, into the hidden `plot:` frame
(concealment = the membrane). Three triggers share all six guards:

P2a — REGENERATIVE: a dead arc's P1 fallout seeds one successor.
P2b — OPPORTUNISTIC: the player's committed delta touches a spine-carrying NPC or
      produces a salient event → the DM wakes and proposes a new development.
P2c — AMBIENT: diegetic time (not turn count) has been quiet for AMBIENT_QUIET_MIN
      minutes → the world throws something up (endless mode only).

Six guards from PB letter 072 §5 / Cx's leg (all three triggers):

  1. slack-pacing off lineage receipts (a cooldown since the last ATTEMPT + a cap
     on concurrent active generated arcs) — never the fluctuating thread count;
  2. fallout lineage (`generated_from` provenance on every minted arc);
  3. fingerprint dedupe (the same tension can't regenerate);
  4. depth cap (death→fallout→death chains are bounded);
  5. mint-time coherence preflight (lint + referents + premise reachability);
  6. the committed-delta read is the trigger source (the caller passes post-gate
     fallout/threads, never raw prose).

Plus the dramatic right-of-way guard (§B): NO generation while the main arc is in
CRISIS or CLIMAX — silent, no receipt (it is right-of-way, not a DM judgment).

All bookkeeping lives in hidden `plot:`/`session:` frames as the generator's own
plan/audit — membrane-clean (PB 072 §2). The generator NEVER writes canon.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from construct import cohorts
from construct.arc import io as arc_io
from construct.arc.conditions import EventRow, Truth, atoms_of, evaluate
from construct.arc.executor import (
    PLOT,
    SESSION,
    Fallout,
    current_epoch,
    current_phase,
    stored_lifecycle,
    turn_time,
)
from construct.arc.grammar import Arc, Phase
from construct.arc.lint import lint_arc
from construct.provider import Provider

logger = logging.getLogger(__name__)

#: Concurrent active generated arcs allowed at once (anti-quest-soup).
GEN_ACTIVE_CAP = 3
#: Max generation depth along a death→regenerate lineage (anti-loop).
GEN_DEPTH_CAP = 2
#: Min turns since the last generation ATTEMPT before another may fire (paced
#: off the lineage receipt, NOT the live thread count — Cx #2).
GEN_COOLDOWN = 2

LIFECYCLE_TERMINALS = ("won", "lost", "cancelled", "incompletable")

#: Routine bookkeeping event kinds excluded from the "first-time kind" salience
#: signal — internal host/engine events are not player-caused developments (§A).
ROUTINE_EVENT_KINDS: frozenset[str] = frozenset({
    "turn", "player_action", "arc_touch", "arc_terminal", "arc_won",
    "arc_lost", "generation_attempt", "generation_declined", "conclusion",
    "commitment", "seal_incoherence",
})

#: Diegetic-minute quiet threshold for the ambient trigger (§C, P2c).
#: Half an in-world day; genre-tunable in a later slice.
AMBIENT_QUIET_MIN: float = 720.0


# --- guard reads (all hidden-frame bookkeeping) -------------------------

def _last_try_turn(reads: Any) -> int:
    """The turn of the last generation TRY — a success OR a cohort-cost decline.
    Pacing keys off this so consecutive failures don't call the DM every turn
    (Codex review: declines were previously unpaced)."""
    marks = [e.at for e in reads.events(kind="generation_attempt", frame=SESSION)]
    marks += [e.at for e in reads.events(kind="generation_declined", frame=SESSION)]
    _epoch = current_epoch()
    return max((int(m - _epoch) for m in marks if m is not None and m >= _epoch),
               default=-(10 ** 9))


def _active_generated(reads: Any, side_arcs: list[Arc]) -> int:
    n = 0
    for a in side_arcs:
        if reads.state(a.arc_id, "generated", frame=PLOT) == "yes" and \
                stored_lifecycle(reads, a) not in LIFECYCLE_TERMINALS:
            n += 1
    return n


def _pacing_ok(reads: Any, side_arcs: list[Arc], turn: int) -> bool:
    if _active_generated(reads, side_arcs) >= GEN_ACTIVE_CAP:
        return False
    return (turn - _last_try_turn(reads)) >= GEN_COOLDOWN


def _fingerprint(proposal: dict) -> str:
    """A stable fingerprint of the SITUATION a proposed arc is about: its sorted
    tension + the entities its beats gate on. Deliberately NOT keyed on the
    trigger source, so the same situation can't regenerate from a different dead
    arc (Codex review: source-scoping let identical tensions reappear)."""
    tension = sorted(str(t) for t in proposal.get("tension", []))
    gated = sorted({b.get("entity", "") for b in proposal.get("beats", [])})
    raw = json.dumps([tension, gated], sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _seen_fingerprint(reads: Any, fp: str) -> bool:
    return reads.state(f"gen:fp:{fp}", "kind", frame=SESSION) == "gen_fingerprint"


def _parent_depth(reads: Any, source: str) -> int:
    """Generation depth of the arc this fallout came from (0 for a hand-authored
    or main arc). `source` is `event:arc_terminal_<slug>` → parent `arc:<slug>`."""
    if not source.startswith("event:arc_terminal_"):
        return 0
    slug = source[len("event:arc_terminal_"):]
    raw = reads.state(f"arc:{slug}", "gen_depth", frame=PLOT)
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def _id_slug(s: str) -> str:
    """Entity-id-safe local part: PB's identity gate (rightly) rejects ids with
    embedded colons/odd characters as malformed — a reason like
    'lint:1-referents' or a source like 'event:arc_terminal_x' must be slugged
    before riding an id. The RAW string still travels as the row VALUE."""
    import re
    return re.sub(r"[^a-z0-9_]+", "_", (s or "").lower()).strip("_") or "x"


def _lineage_exhausted(reads: Any, source: str) -> bool:
    return reads.state(f"gen:exhausted_{_id_slug(source)}", "kind",
                       frame=SESSION) == "exhausted_for_generation"


# --- salience pre-filter (P2b, §A) -------------------------------------

def salient_moments(fact_rows: list[dict], events: list,
                    prior_kinds: set[str], spined: set[str]) -> list[str]:
    """Deterministic, zero-model-call salience read over the turn's committed delta.

    Returns human-phrased fuel lines describing the qualifying moments found;
    an empty list means the turn is not salient (no cohort call, no receipt).
    Pure function: all inputs are passed in; no hidden reads (§A, Cx 496 amendment 1).

    Three qualifying signals:
      1. spine-touch — a fact row touching a person in `spined`;
      2. first-time event kind — an event kind not seen before the window,
         excluding ROUTINE_EVENT_KINDS and ids starting "event:tick_";
      3. causal ripple — a window event with a non-empty `caused_by` tuple.
    """
    lines: list[str] = []
    # 1. Spine-touch: any fact row whose entity or value is a spined NPC.
    for row in fact_rows:
        entity = row.get("entity", "")
        value = str(row.get("value", ""))
        if entity in spined or value in spined:
            attr = row.get("attribute", "")
            lines.append(
                f"the player's action touched {entity!r} (attribute {attr!r} → {value!r})"
                f", who has a standing drive or fear"
            )
            break  # one spine-touch line is enough
    # 2. First-time event kind and 3. causal ripple.
    for ev in events:
        kind = ev.kind if isinstance(ev, EventRow) else ev.get("kind", "")
        ev_id = ev.event_id if isinstance(ev, EventRow) else ev.get("event_id", "")
        caused_by = (ev.caused_by if isinstance(ev, EventRow)
                     else tuple(ev.get("caused_by", ())))
        if ev_id.startswith("event:tick_"):
            # Off-screen world motion is ambient's domain (§A, discovery-gating parity).
            continue
        if kind in ROUTINE_EVENT_KINDS:
            # A bookkeeping kind is never a dramatic moment — even one carrying
            # causal linkage (else a routine turn/arc event with caused_by would
            # make EVERY turn salient and the filter would stop filtering).
            continue
        if kind not in prior_kinds:
            lines.append(
                f"a new kind of event occurred this turn: {kind!r} "
                f"(not seen before in this story)"
            )
        if caused_by:
            lines.append(
                f"event {ev_id!r} (kind={kind!r}) rippled from {caused_by!r}, "
                f"a durable consequence just landed"
            )
    return lines


# --- dramatic right-of-way (§B) ----------------------------------------

def main_at_peak(reads: Any, main_arc: Arc) -> bool:
    """True when the main arc is in CRISIS or CLIMAX — no generation while the
    protagonist's story is at its peak (silent gate, no receipt — §B)."""
    return current_phase(reads, main_arc) in (Phase.CRISIS, Phase.CLIMAX)


# --- ambient clock (P2c, §C) -------------------------------------------

def _last_development_min(world: Any, reads: Any, minutes_now: float,
                          turn: int) -> float:
    """The diegetic-minute stamp of the most recent development (any mint, beat
    achieved, clock fired, or fallout emitted).

    Seed-on-absent is a WRITE-ONCE baseline (§C, Cx 498): if the row is missing
    or malformed, write current diegetic minutes before returning them — the
    quiet-timer starts "now", never at genesis. A read-only seed that merely
    returns "now" reseeds every check and the interval never accrues (ambient
    would be structurally dead on fresh worlds)."""
    raw = reads.state("session:ambient", "last_development_min", frame=SESSION)
    if raw is None:
        # No baseline yet — write it so the timer accrues from this turn.
        _mark_development(world, minutes_now, turn)
        return minutes_now
    try:
        return float(raw)
    except (TypeError, ValueError):
        # Malformed row — overwrite with a clean baseline.
        _mark_development(world, minutes_now, turn)
        return minutes_now


def _mark_development(world: Any, minutes_now: float, turn: int) -> None:
    """Write the diegetic-minute stamp of the most recent development into the
    hidden session frame (`session:ambient/last_development_min`). Called at every
    mint (all triggers), beat achieved, clock fired, and fallout emitted (§C)."""
    world.porcelain.ingest_structured([
        {"entity": "session:ambient", "attribute": "last_development_min",
         "value": minutes_now, "valid_from": turn_time(turn)},
    ], frame=SESSION)


# --- guard writes -------------------------------------------------------

def _record_decline(world: Any, turn: int, reason: str) -> None:
    eid = f"event:gen_declined_{turn}_{_id_slug(reason)}"
    world.porcelain.ingest_structured([
        {"entity": eid, "attribute": "kind", "value": "generation_declined",
         "valid_from": turn_time(turn)},
        {"entity": eid, "attribute": "reason", "value": reason,
         "valid_from": turn_time(turn)},
    ], frame=SESSION)
    logger.info("generation declined (turn %d): %s", turn, reason)


def _mark_exhausted(world: Any, source: str, turn: int) -> None:
    world.porcelain.ingest_structured([
        {"entity": f"gen:exhausted_{_id_slug(source)}", "attribute": "kind",
         "value": "exhausted_for_generation", "valid_from": turn_time(turn)},
    ], frame=SESSION)


def _record_attempt(world: Any, arc: Arc, source: str, depth: int, fp: str,
                    turn: int) -> None:
    # The lineage receipt + fingerprint marker (session) — paces and dedupes.
    world.porcelain.ingest_structured([
        {"entity": f"event:gen_attempt_{turn}", "attribute": "kind",
         "value": "generation_attempt", "valid_from": turn_time(turn)},
        {"entity": f"event:gen_attempt_{turn}", "attribute": "minted",
         "value": arc.arc_id, "valid_from": turn_time(turn)},
        {"entity": f"gen:fp:{fp}", "attribute": "kind", "value": "gen_fingerprint",
         "valid_from": turn_time(turn)},
    ], frame=SESSION)
    # The provenance on the arc itself (plot) — lineage + depth for the cap.
    world.porcelain.ingest_structured([
        {"entity": arc.arc_id, "attribute": "generated", "value": "yes", "timeless": True},
        {"entity": arc.arc_id, "attribute": "generated_from", "value": source, "timeless": True},
        {"entity": arc.arc_id, "attribute": "gen_depth", "value": depth, "timeless": True},
    ], frame=PLOT)


# --- coherence preflight (guard #5) -------------------------------------

def _preflight(arc: Arc, reads: Any) -> tuple[bool, str]:
    """A proposed arc is checked BEFORE it exists: its protagonist and tension
    entity must already EXIST in the world (the grounding guard — `lint_arc` only
    validates BEAT referents, so an invented protagonist/tension would otherwise
    slip through and later get canonized by the P1 fallout — Codex BLOCKER); it
    must pass the arc linter (referents + structure; `2-paths` is advisory, as at
    session zero); its premise must not be already FALSE (TRUE/INDETERMINATE ok);
    and no required beat may be born already unreachable."""
    if not reads.has_entity(arc.protagonist):
        return False, "ungrounded_protagonist"
    tension_entity = arc.shape.tension[0] if arc.shape.tension else None
    if not tension_entity or not reads.has_entity(tension_entity):
        return False, "ungrounded_tension"
    findings = lint_arc(arc, reads)
    blocking = [f for f in findings if f.check != "2-paths"]
    if blocking:
        return False, "lint:" + ",".join(f.check for f in blocking)[:60]
    if evaluate(arc.shape.premise, reads) is Truth.FALSE:
        return False, "premise_false"
    for beat in arc.beats:
        if beat.unreachable_if is not None and \
                evaluate(beat.unreachable_if, reads) is Truth.TRUE:
            return False, "born_unreachable"
    return True, "ok"


#: Entity-id token shapes the hook must never carry to the player (the sole
#: player-facing P2a channel). The hook is model text, so it's scrubbed host-side
#: (Codex: concealment was prompt-only) — a stripped or system-speak hook is dropped.
_ID_TOKEN = re.compile(r"\b(?:person|place|obj|fact|arc|beat|clock|shape|event|"
                       r"knows|plot|session|drive|fear):[a-z0-9_:]+", re.IGNORECASE)


def _sanitize_hook(hook: str) -> str:
    """Drop a hook that leaks raw entity ids or system-speak; otherwise return it.
    Conservative: any id-shaped token or schema word voids the hook (fail-quiet —
    the development still exists as an arc, it just isn't announced this turn)."""
    if not hook:
        return ""
    if _ID_TOKEN.search(hook):
        logger.warning("generated hook dropped (leaked an id token): %r", hook[:80])
        return ""
    return hook.strip()


# --- shared mint path (all triggers) ------------------------------------

def _mint_side_arc(world: Any, reads: Any, provider: Provider,
                   trigger: str, fuel: str, source: str, side_arcs: list[Arc],
                   ctx: dict, turn: int,
                   main_protagonist: str, depth: int) -> tuple[Arc, str] | None:
    """The shared mint path for all three triggers (§E, §D).

    cohort → fingerprint dedupe → _build_arc → player-protagonist reject →
    preflight → commit arc+portfolio → _record_attempt (explicit depth) →
    sanitized hook. Returns (arc, hook) on success, else None. EVERY miss here
    leaves a `generation_declined` receipt (each is a DM judgment) — the one
    silent skip is the right-of-way gate, which lives in the turn loop and
    returns before this path is ever entered (§B).
    """
    try:
        proposal = cohorts.generate_arc(
            provider, trigger=trigger, fuel=fuel,
            available_ids=ctx.get("available_ids", []), style=ctx.get("style", ""),
            present_characters=ctx.get("present_characters", "(none in scene)"))
    except Exception as exc:  # noqa: BLE001 — a cohort miss never breaks the turn
        logger.warning("generate_arc cohort failed: %s", exc)
        _record_decline(world, turn, "cohort_error")
        return None

    fp = _fingerprint(proposal)
    if _seen_fingerprint(reads, fp):
        _record_decline(world, turn, "duplicate")
        return None

    arc_id = f"arc:gen_{turn}"
    try:
        from construct.game import _build_arc  # deferred — avoids an import cycle
        arc = _build_arc(proposal, arc_id=arc_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("generated arc failed to build: %s", exc)
        _record_decline(world, turn, "build_error")
        return None

    # Player-protagonist guard (§D, Cx 496 amendment 4): P2b/P2c always mint
    # NPC-protagonist arcs; a proposal naming the player's protagonist is a
    # normal decline (a DM judgment, unlike the silent right-of-way gate).
    if arc.protagonist == main_protagonist:
        _record_decline(world, turn, "player_protagonist")
        return None

    ok, reason = _preflight(arc, reads)
    if not ok:
        _record_decline(world, turn, reason)
        return None

    # Commit: the arc into the hidden plot frame + the portfolio registration
    # (superseding the sealed list) + the provenance/receipts.
    world.porcelain.ingest_structured(
        arc_io.arc_to_items(arc, frame=PLOT) + arc_io.index_items(arc, frame=PLOT),
        frame=PLOT)
    world.porcelain.ingest_structured(
        arc_io.portfolio_add_items(reads, arc_id, valid_from=turn_time(turn)), frame=PLOT)
    _record_attempt(world, arc, source, depth, fp, turn)
    logger.info("generated arc %s from %s (depth %d)", arc_id, source, depth)
    return arc, _sanitize_hook(proposal.get("hook") or "")


# --- the regenerative trigger (P2a) -------------------------------------

def generate_from_fallout(world: Any, reads: Any, provider: Provider,
                          fallout: Fallout, side_arcs: list[Arc], ctx: dict,
                          turn: int) -> tuple[Arc, str] | None:
    """Try to mint ONE new side arc from a just-emitted fallout. Returns
    (arc, hook) on success, else None. Fully fail-open: any miss records a
    decline receipt and leaves the world quiet."""
    source = fallout.term_id
    if _lineage_exhausted(reads, source) or not _pacing_ok(reads, side_arcs, turn):
        return None
    parent_depth = _parent_depth(reads, source)
    if parent_depth >= GEN_DEPTH_CAP:
        _mark_exhausted(world, source, turn)
        _record_decline(world, turn, "depth_cap")
        return None

    fuel = (f"{fallout.directive} (standing consequence: {fallout.entity} "
            f"{fallout.attribute}={fallout.value}; the {fallout.lifecycle} of "
            f"{fallout.arc_id}).")
    # Regenerative arcs carry the main protagonist as the boundary (they share
    # the _mint_side_arc path; the player-protagonist guard keeps the world
    # moving *at* the player, not *as* them).
    main_protagonist = ctx.get("main_protagonist", "")
    return _mint_side_arc(world, reads, provider,
                          trigger="a thread just closed (regenerative)",
                          fuel=fuel, source=source, side_arcs=side_arcs,
                          ctx=ctx, turn=turn,
                          main_protagonist=main_protagonist,
                          depth=parent_depth + 1)


# --- the opportunistic trigger (P2b) ------------------------------------

def generate_opportunistic(world: Any, reads: Any, provider: Provider,
                           moments: list[str], side_arcs: list[Arc],
                           ctx: dict, turn: int,
                           main_protagonist: str) -> tuple[Arc, str] | None:
    """Try to mint ONE new side arc from the player's committed delta.

    `moments` is a non-empty list of salient-moment lines (the output of
    `salient_moments`; the caller guarantees non-empty before calling). Returns
    (arc, hook) on success, else None. Depth 0 (§D, Cx 496 amendment 5).
    """
    source = f"player_delta:{turn}"
    fuel = "Player actions this turn opened a development:\n" + "\n".join(
        f"  - {m}" for m in moments)
    return _mint_side_arc(world, reads, provider,
                          trigger="the player's actions opened a door (opportunistic)",
                          fuel=fuel, source=source, side_arcs=side_arcs,
                          ctx=ctx, turn=turn,
                          main_protagonist=main_protagonist, depth=0)


# --- the ambient trigger (P2c) ------------------------------------------

def generate_ambient(world: Any, reads: Any, provider: Provider,
                     side_arcs: list[Arc], ctx: dict, turn: int,
                     main_protagonist: str) -> tuple[Arc, str] | None:
    """Try to mint ONE new side arc to break a diegetic silence.

    Called only when `scenario_mode == "endless"` and the diegetic quiet
    threshold is crossed (§C). Fuel comes from standing threads + present NPC
    spines already in `ctx`. Returns (arc, hook) on success, else None.
    Depth 0 (§D, Cx 496 amendment 5).
    """
    source = f"ambient:{turn}"
    present = ctx.get("present_characters", "(none in scene)")
    style = ctx.get("style", "")
    fuel = (f"The world has been quiet for a while. Standing NPC spines and "
            f"present characters:\n{present}\nStyle: {style}")
    return _mint_side_arc(world, reads, provider,
                          trigger="the world has been quiet a while (ambient)",
                          fuel=fuel, source=source, side_arcs=side_arcs,
                          ctx=ctx, turn=turn,
                          main_protagonist=main_protagonist, depth=0)
