"""Scenario/playthrough management + session-zero ingest wiring.

The v1 model (letters 012/013): a scenario is the pristine genesis
`.world` (never written by play); each scenario has ONE playthrough
slot (`<name>.play.world`); "start from the beginning" recopies the
pristine file over the slot. Two files, one copy operation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, NamedTuple

from patternbuffer import World

from construct.adapter import PorcelainWorldReads
from construct.arc import io as arc_io
from construct.arc.conditions import (
    AtLeast,
    BeatAchieved,
    InFrame,
    Occurred,
    Quantity,
    StateIs,
    TurnsQuiet,
)
from construct.arc.grammar import Arc, Beat, Clock, ConclusionShape, Phase, Rung, Weight
from construct.arc.lint import lint_arc
from construct.provider import Provider, ProviderError, complete_sync, engine_tier_dispatch

logger = logging.getLogger(__name__)

WORLDS_DIR = Path("worlds")
#: The authoring side of the firewall: generated source bibles (the hidden
#: full story) live here — readable by the ingest pipeline and operator/audit,
#: NEVER surfaced in a play session. A runtime artifact (gitignored, per-user),
#: distinct from the committed `examples/` fixture (Kernos 063 B; Cx 063 #7).
GENERATED_DIR = Path("generated")

#: Batch size for the deferred durability-classification pass (the build's main
#: efficiency lever — see create_scenario_from_ingest). Groups N model-judged
#: rows per call: bigger = fewer round trips, smaller = less context per call.
CLASSIFY_BATCH_SIZE = int(os.getenv("CONSTRUCT_CLASSIFY_BATCH", "24"))

ARC_SCHEMA = {
    "type": "object",
    "properties": {
        "protagonist": {"type": "string", "description": "entity id, e.g. person:joel"},
        "theme": {"type": "string", "description": "the pitchable theme, one line"},
        "goal_statement": {"type": "string",
                           "description": "ONE vivid player-facing line of aspiration "
                           "for win_loss mode — the AIM in THIS world's genre. NAME the "
                           "premise stakes (the dragon, the blight, the missing child, "
                           "the locked heart); a beloved archetype is GOOD, not a flaw "
                           "— 'solve the mystery and name the killer', 'slay the dragon "
                           "and free the vale', 'win her heart across the years', 'bring "
                           "the fort through the monsoon alive'. Reveal the PROBLEM, "
                           "never the SOLUTION: no whodunit answer, no mechanism, no "
                           "specific hidden fact the player must discover."},
        "failure_when": {
            "type": "object",
            "description": "OPTIONAL loss terminal for win_loss mode — the story's DECISIVE failure "
            "event, authored from what THIS story is about ('IT'). Three kinds: 'event_occurs' = a "
            "decisive loss event (e.g. 'alarm_raised', 'player_unmasked', the protectee killed) — "
            "give a plausible event kind. 'player_learns' = a damning fact entering the player frame. "
            "'time_deadline' = ONLY when time is genuinely part of THIS story's thread (a bomb timer, "
            "the King arriving, a tide, dawn execution) — set `deadline_minutes` to the IN-WORLD "
            "minutes until the deadline; NEVER for a leisurely investigation/mystery, where time is "
            "pedantic. Omit `failure_when` entirely when the story has no decisive failure event (it "
            "simply stays open until the player concludes). Turns NEVER force a close.",
            "properties": {
                "kind": {"type": "string",
                         "enum": ["player_learns", "event_occurs", "time_deadline"]},
                "entity": {"type": "string",
                           "description": "event_occurs: the event kind; "
                                          "player_learns: the fact/entity id"},
                "attribute": {"type": "string", "description": "player_learns only"},
                "value": {"type": "string", "description": "player_learns only"},
                "deadline_minutes": {"type": "integer",
                                     "description": "time_deadline only: in-world minutes until "
                                                    "the fiction's clock runs out"},
            },
        },
        "delta_type": {"type": "string",
                       "enum": ["drive_inverted", "desire_at_cost", "desire_renounced",
                                "identity_accepted", "homecoming_changed"]},
        "tension": {"type": "array", "items": {"type": "string"},
                    "description": "[entity, stronger_drive, weaker_drive]"},
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "beat:<slug>"},
                    "phase": {"type": "string",
                              "enum": ["setup", "rising", "crisis", "climax", "falling"]},
                    "weight": {"type": "string", "enum": ["required", "optional"]},
                    "kind": {"type": "string", "enum": ["player_learns", "event_occurs"]},
                    "entity": {"type": "string",
                               "description": "for player_learns: the fact/entity id; "
                                              "for event_occurs: the event kind"},
                    "attribute": {"type": "string",
                                  "description": "player_learns only: the attribute"},
                    "value": {"type": "string",
                              "description": "player_learns only: the value"},
                },
                "required": ["id", "phase", "weight", "kind", "entity", "attribute", "value"],
            },
        },
    },
    "required": ["protagonist", "theme", "delta_type", "tension", "beats"],
}


def _world(path: Path, name: str, *, model=None, **kw) -> "World":
    """Single World-construction seam: injects Construct's attribute-
    semantics rule (RFC-001 / PB 042) so model-minted set-valued domain
    relations (contains/has_part/…) accumulate instead of last-write."""
    from construct.semantics import attribute_default
    return World(path, world_id=f"w:{name}", model=model,
                 attribute_default=attribute_default, **kw)


def scenario_path(name: str) -> Path:
    return WORLDS_DIR / f"{name}.world"


def slot_path(name: str, player_id: str | None = None) -> Path:
    """Per-player playthrough slot. player_id=None keeps the original
    single-slot name (`<scenario>.play.world`) so existing slots and the
    solo CLI are unchanged; a player_id (e.g. a Discord user id) keys a
    private slot (`<scenario>.<player_id>.play.world`) so two players
    never collide — a small extension of the single-slot model
    (letter 034).

    Each slot is a complete, never-joined world fork; forks share the
    scenario's `world_id` and isolation is the FILE boundary, not id
    uniqueness (pattern-buffer whitepaper A5, blessed letter 040). The
    file path is therefore the instance key. CAVEAT for any future
    multi-player roster/dashboard: key it on the file/slot, NEVER on the
    bare `world_id` string — that would collapse all forks into one (a
    host-layer mistake, not an engine bug)."""
    if player_id:
        return WORLDS_DIR / f"{name}.{_safe_player_id(player_id)}.play.world"
    return WORLDS_DIR / f"{name}.play.world"


def _safe_player_id(player_id: str) -> str:
    """Filesystem-safe slot segment; never empty."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", player_id).strip("_")
    return safe or "player"


def list_scenarios() -> list[dict]:
    out = []
    for path in sorted(WORLDS_DIR.glob("*.world")):
        if path.name.endswith(".play.world"):
            continue
        meta_path = path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        out.append({"name": path.stem, "path": str(path), **meta})
    return out


def _chunk_chapters(text: str, max_chars: int = 4000) -> list[str]:
    """Chapter chunks, further split at paragraph boundaries when long —
    extraction latency and output size scale with chunk size, and the
    scene cursor advances per chunk either way."""
    parts = [p for p in re.split(r"(?=^## )", text, flags=re.MULTILINE) if p.strip()]
    chunks: list[str] = []
    for part in parts:
        if len(part) <= max_chars:
            chunks.append(part)
            continue
        current = ""
        for para in part.split("\n\n"):
            if current and len(current) + len(para) + 2 > max_chars:
                chunks.append(current)
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current.strip():
            chunks.append(current)
    return chunks


def _slug(s: str) -> str:
    """Conform an id segment to the frozen porcelain id grammar
    (^[a-z][a-z0-9_]*:[a-z0-9_:]+$) — model proposals love hyphens."""
    return re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_")


def _beat_expr(beat: dict, player_frame: str):
    if beat["kind"] == "player_learns":
        return InFrame(player_frame, beat["entity"], beat["attribute"], beat["value"])
    return Occurred(beat["entity"])


def _failure_expr(spec: dict | None, player_frame: str):
    """Convert the optional authored loss terminal into an Expr, tolerantly. The loss is the
    story's DECISIVE failure event (founder "IT closes it"), authored per-story:
      - `time_deadline`: a fiction clock ran out (King's dinner, the bomb) → a `Quantity` over the
        diegetic story-clock (`time:elapsed.elapsed_minutes`). Authored ONLY when time is part of
        the thread; the deadline is in IN-WORLD MINUTES, never turns.
      - `event_occurs`: a decisive loss event (the protectee killed, the alarm raised) → `Occurred`.
      - `player_learns`: a damning fact entering the player frame → `InFrame`.
    A malformed/partial spec yields None (no authored loss; the story just stays open) — never a
    build-time crash."""
    if not spec:
        return None
    if spec.get("kind") == "time_deadline":
        mins = spec.get("deadline_minutes", spec.get("deadline_elapsed_minutes"))
        if not isinstance(mins, (int, float)) or isinstance(mins, bool) or mins <= 0:
            return None
        from construct.clock import ELAPSED_ATTR, ELAPSED_ENTITY
        return Quantity(ELAPSED_ENTITY, ELAPSED_ATTR, ">=", float(mins))
    if not spec.get("entity"):
        return None
    if spec.get("kind") == "player_learns":
        if not (spec.get("attribute") and spec.get("value")):
            return None
        return InFrame(player_frame, spec["entity"], spec["attribute"], spec["value"])
    return Occurred(spec["entity"])


def _emit(on_stage, msg: str) -> None:
    """Surface an ingestion stage update — to the supplied sink (CLI stdout,
    Discord, import-folder log) and always to the logger. Each stage names the
    pattern-buffer layer being exercised: progress *and* a live showcase of the
    adoption (founder request)."""
    logger.info(msg)
    if on_stage is not None:
        try:
            on_stage(msg)
        except Exception:  # a status sink must never sink a build
            pass


#: Kind-scoped traversal policy (PB RFC-003 / letter 058): which portal `kind`s
#: gate a passage, and on what. route() derives clear|blocked|obscured from a
#: portal entity's facts under this policy; an undeclared kind never gates
#: (fail-open → clear), and a declared-but-unstated portal reads `obscured`
#: (fail-safe → never a false-clear). The host declares vocabulary; the engine
#: derives. Keyed on the portal's folded `kind` VALUE (door/hatch/…), so it only
#: bites where extraction gave a portal-specific kind — reliable-capture work is
#: ongoing, but missing capture degrades safe.
TRAVERSAL_BLOCK_STATES = ("shut", "closed", "locked", "sealed", "rusted",
                          "barred", "jammed", "dead", "decommissioned",
                          "defunct", "failed", "broken", "collapsed", "welded")
TRAVERSAL_BLOCK_RELATIONS = ("guarded_by", "sealed_by", "barred_by", "locked_by")
TRAVERSAL_PORTAL_KINDS = ("door", "gate", "hatch", "portal", "lock", "elevator",
                          "lift", "shaft", "stairs", "stairway", "passage", "airlock")


def _declare_traversal_policy(world: Any) -> None:
    """Persist the kind-scoped traversal policy as `traversal:<kind>` rows so
    route() can derive passability. Opt-in by kind; safe-degrading."""
    items = []
    for kind in TRAVERSAL_PORTAL_KINDS:
        for st in TRAVERSAL_BLOCK_STATES:
            items.append({"entity": f"traversal:{kind}", "attribute": "blocks_when_state",
                          "value": st, "timeless": True})
        for rel in TRAVERSAL_BLOCK_RELATIONS:
            items.append({"entity": f"traversal:{kind}", "attribute": "blocks_when_relation",
                          "value": rel, "timeless": True})
    try:
        world.porcelain.ingest_structured(items)
        logger.info("declared traversal policy for %d portal kinds", len(TRAVERSAL_PORTAL_KINDS))
    except Exception as exc:
        logger.warning("traversal policy declaration skipped: %s", exc)


def _adjudicate_residue(world: Any, proposals: list[dict]) -> None:
    """Triage the coreference residue PB's reconcile() declined (letters
    056/058, validated on anchor in 018). The SAFE automated half only:
    a proposal with a relating edge between the two closures (`code` in
    containment/relating_edge, or any `related_rows`) is *not identity* —
    `reject()` it (sticky `distinct_from`, so it never re-proposes/merges).
    Everything else (same-kind-no-edge true coreferents AND ambiguous
    cross-kind) is LEFT as a proposal: auto-confirm carries homonym risk
    (two people named Cray), so genuine merges stay a deliberate call, not
    a build-time gamble. Engine surfaces structure; the host decides."""
    rejected = deferred = 0
    for pr in proposals:
        ad = pr.get("auto_decline") or {}
        relating = ad.get("code") in ("containment", "relating_edge") or ad.get("related_rows")
        if relating:
            try:
                world.porcelain.reject(pr["a"], pr["b"])
                rejected += 1
            except Exception as exc:
                logger.warning("residue reject %s~%s skipped: %s", pr.get("a"), pr.get("b"), exc)
        else:
            deferred += 1
    if rejected or deferred:
        logger.info("residue triage: %d rejected (relating edge), %d deferred "
                    "(adjudicable)", rejected, deferred)


def _author_world_laws(provider: Provider, brief: str, reality: str,
                       game_types: list | None) -> tuple[list[dict], str]:
    """WORLD LAWS (#105, Cx 470): author the universe's 1-4 governing dynamics
    from the brief, gated by the canonical family palette × reality register,
    linted deterministically (shallow checks) and judged by the anti-pastiche
    critic, with one feedback retry each. Returns (laws, reality_register) —
    fail-open to ([], reality): laws are enrichment; their absence never
    sinks a build."""
    from construct import cohorts, laws as laws_mod, play_styles

    families = laws_mod.families_of(play_styles.resolve(game_types))
    feedback = ""
    last_critic_pass: set[str] | None = None  # names the critic passed, FINAL attempt
    for attempt in range(3):
        try:
            out = cohorts.author_laws(
                provider, brief, reality, families,
                laws_mod.allowed_registers(families, reality),
                feedback=feedback)
        except Exception as exc:  # noqa: BLE001 — enrichment, never a gate
            logger.warning("law authoring skipped: %s", exc)
            return [], reality
        settled = (out.get("reality_register") or reality or "").strip()
        proposed = [law for law in (out.get("laws") or [])
                    if isinstance(law, dict)]
        if not proposed:
            return [], settled  # a world may honestly have no named laws
        # The gate is re-derived against the SETTLED register (the author may
        # have settled an undeclared one from the brief).
        last_critic_pass = None
        problems = laws_mod.lint_laws(
            proposed, laws_mod.allowed_registers(families, settled))
        if not problems:
            try:
                verdicts = {v.get("name", ""): v for v in
                            (cohorts.law_critic(provider, proposed)
                             .get("verdicts") or [])}
                problems = [f"{n}: {v.get('problem') or 'pastiche'}"
                            for n, v in verdicts.items()
                            if not v.get("passes", True)]
                last_critic_pass = {
                    str(law.get("name") or "") for law in proposed
                    if verdicts.get(str(law.get("name") or ""), {})
                    .get("passes", True)}
            except Exception as exc:  # noqa: BLE001 — critic is best-effort
                logger.warning("law critic skipped: %s", exc)
                problems = []
                last_critic_pass = {str(law.get("name") or "")
                                    for law in proposed}
        if not problems:
            logger.info("authored %d world law(s) [%s] (attempt %d): %s",
                        len(proposed), settled, attempt + 1,
                        [law.get("name") for law in proposed])
            return proposed, settled
        feedback = "; ".join(problems)
        logger.warning("world laws failed lint/critic (attempt %d): %s",
                       attempt + 1, problems)
    # Retries exhausted (Cx 475 blocker): a survivor must pass the shallow lint
    # AND hold a PASSING critic verdict from the final round — the critic's
    # semantic anti-pastiche judgment is the central bar (Cx 470 ruling 2) and
    # is never bypassed by exhaustion. Lint-failed final round → the critic
    # never judged it → nothing ships (law-less is the honest failure mode).
    survivors = [law for law in proposed
                 if not laws_mod.lint_laws(
                     [law], laws_mod.allowed_registers(families, settled))
                 and str(law.get("name") or "") in (last_critic_pass or set())]
    if survivors:
        logger.warning("shipping %d/%d law(s) that pass lint AND the critic "
                       "after retries", len(survivors), len(proposed))
    else:
        logger.warning("no law survived lint+critic after retries — shipping "
                       "law-less")
    return survivors, settled


def _finalize_scenario(world: Any, name: str, title: str, provider: Provider,
                       spath: Path, endless: bool, on_stage=None,
                       win_direction: str = "", play_as: str = "",
                       game_types: list | None = None,
                       source_step: float | None = None,
                       laws: list | None = None,
                       reality_register: str = "") -> dict:
    """Shared session-zero tail (both creation paths): once canon is
    established, author the hidden arc over it (lint-gated), seed
    knowledge frames, and write the scenario meta. ENTRY + DESTINATION.
    Emits per-stage status (stages 2-6) via `on_stage`.

    `source_step` (B' S2): set ONLY by the ingest path, where the source axis was spaced by
    SOURCE_STEP. Its presence marks a HORIZON world — the opening is staged at `opening_as_of`
    (just above chunk 1) and reads bind to a per-turn play horizon, NOT the timeline head.
    None (the interview path / single-timeframe worlds) → the legacy epoch-raise."""
    from construct.arc.executor import (
        arc_entities,
        compute_entry_epoch,
        horizon_metadata,
        set_entry_epoch,
        turn_time,
    )

    # Global coreference finalize pass (PB IDENTITY-RECALL-V1/V2, letters
    # 050-058): collapse cross-chunk coreferents the per-pass resolver couldn't
    # see, then triage the declined residue. Run BEFORE arc authoring and frame
    # seeding so both bind to reconciled identities. Idempotent; the containment
    # veto keeps it from fusing a container with its contents.
    _emit(on_stage, "Stage 2 · Reconciling identity · cross-chunk coreference "
                    "recall + structured-triage residue (PB)")
    try:
        result = world.porcelain.reconcile()
        proposals = result.get("proposals", [])
        if result.get("merges"):
            logger.info("identity reconcile: %d cross-chunk merge(s)", result["merges"])
        _adjudicate_residue(world, proposals)
    except Exception as exc:  # a finalize-pass failure must never sink a build
        logger.warning("identity reconcile skipped: %s", exc)

    # Passability policy (PB RFC-003): declare which portal kinds gate, so
    # route() can derive blocked/obscured/clear from portal facts at play time.
    _emit(on_stage, "Stage 3 · Declaring passability · RFC-003 traversal policy "
                    "for route() (PB)")
    _declare_traversal_policy(world)

    # AS-OF PLAY HORIZON (B' S2, Cx 253) vs. the legacy epoch-raise (Cx 127):
    #
    #  - HORIZON world (source_step set — ingested fiction with a spaced axis): the play origin
    #    is `opening_as_of` (just above chunk 1), NOT above the aftermath. Opening staging stamps
    #    at turn_time(0) == opening_as_of, supersedes chunk 1, and the source aftermath (≥ the
    #    next chunk at next_source_as_of) is simply EXCLUDED by reading as-of the horizon — no
    #    epoch-raise. The per-turn play horizon (Session) advances within [opening_as_of,
    #    next_source_as_of) and reads bind to it (S3), so beats/conditions never see the future.
    #  - LEGACY world (source_step None — interview/single-timeframe): keep the Cx-127 raise —
    #    pin the live-entry epoch ABOVE every pre-play `valid_from` so opening staging + live
    #    turns win the containment fold over any aftermath rows. A one-timeframe world
    #    (anchor/deduction) computes back to TURN_EPOCH → a no-op.
    opening_as_of: float | None = None
    next_source_as_of: float | None = None
    if source_step is not None:
        opening_as_of, next_source_as_of = horizon_metadata(source_step)
        entry_epoch = opening_as_of
        set_entry_epoch(entry_epoch)
        logger.info("horizon world: opening_as_of=%.1f, next_source_as_of=%.1f (step %.0f)",
                    opening_as_of, next_source_as_of, source_step)
    else:
        entry_epoch = compute_entry_epoch(world)
        set_entry_epoch(entry_epoch)
        if entry_epoch > 1000.0:
            logger.info("scenario entry epoch raised to %.1f (above pre-play valid_from)",
                        entry_epoch)

    # WORLD LAWS (#105): the universe's governing dynamics land as ordinary
    # canon BEFORE the arc, so the destination can turn on a law and the cast
    # can embody one. Written through the same doorway as everything else;
    # the single-source renders below feed every downstream author (Cx 470
    # test bar: cast, arc, adjudication share the SAME law objects).
    laws = [law for law in (laws or []) if isinstance(law, dict)]
    from construct import laws as laws_mod
    _laws_block = laws_mod.laws_block(laws)
    if laws:
        _emit(on_stage, "Stage 3.5 · Committing the world's deep laws · "
                        f"{len(laws)} governing dynamic(s) as canon")
        try:
            world.porcelain.ingest_structured(laws_mod.law_rows(laws))
        except Exception as exc:  # noqa: BLE001 — enrichment, never a gate
            logger.warning("law canon rows skipped: %s", exc)

    _emit(on_stage, "Stage 4 · Authoring the hidden arc over canon")
    reads = PorcelainWorldReads(world)
    people = _known_people(world)
    digest = _world_digest(world)
    # The allowlist of real entity ids a player_learns beat may gate on
    # (lint check 1-referents rejects any other). Given explicitly — the
    # arc author otherwise invents thematic fact:/obj: ids absent from
    # canon, which fails lint (live finding, interview-built worlds).
    known_ids = sorted(e for e in _canon_entity_ids(world)
                       if e.startswith(("person:", "fact:", "obj:", "place:")))

    arc = None
    last_findings: list = []
    # The protagonist MUST be a STAGED person (Cx 160): everything downstream — cast
    # staging, knows:<protagonist> delivery, pillar coverage — keys off arc.protagonist,
    # so an unlocatable role id (person:detective) silently darkens the whole world.
    # Protagonist ELIGIBILITY reads at HEAD, even for horizon worlds (Cx 255 audit → reversed on
    # the emberroad evidence; Cx 261 ruling). THE INVARIANT IS THE CODE SPLIT, not a heuristic:
    # head eligibility may only choose a real STAGED person (not a kindless role) — it must NOT
    # decide opening STATE. "Is this a real person somewhere on the source map" and "is this
    # person already placed at the opening horizon" are different questions. Opening state comes
    # entirely from `_opening_scene_place` staging + the horizon-bound runtime reads below.
    # (A saga's opening chapters are often ATMOSPHERIC and place no cast, so the cast's `in` rows
    # first appear mid-text; `as_of=opening_as_of` here emptied the allowlist and failed the build.)
    located_people = _locatable_people(world, known_ids)
    # #104 (the seaside-bookstore deadlock, Cx 470 §6): a generated world whose prose
    # placed NOBODY leaves located_people EMPTY — the protagonist guard then fails
    # every attempt, the fallback returns None, and the build dies with a misleading
    # `[]`. A bare world is a STAGING gap, not a bad pick: deterministically place
    # the first known person at the world's first place so the guard has ground to
    # stand on. The guard's teeth for the MISPICK case (located non-empty, author
    # chose an unlocated id) are unchanged.
    if not located_people:
        _people = [e for e in known_ids if str(e).startswith("person:")]
        _places = sorted(e for e in _canon_entity_ids(world)
                         if str(e).startswith("place:"))
        if _people and _places:
            # honor the player's asked-for role when choosing WHO gets staged
            _want = {w for w in (play_as or "").lower().replace(":", " ").split()
                     if len(w) > 3}

            def _pscore(pid: str) -> int:
                _nm = str(world.porcelain.state(pid, "name") or "")
                return len(_want & set((pid + " " + _nm).lower()
                                       .replace(":", " ").split()))
            _anchor_person = (max(_people, key=_pscore) if _want else _people[0])
            _anchor_place = _places[0]
            world.porcelain.ingest_structured([
                {"entity": _anchor_person, "attribute": "in",
                 "value": _anchor_place, "value_type": "entity"}])
            located_people = [_anchor_person]
            logger.warning("no located people at arc authoring — staged %s at %s "
                           "so the protagonist guard has ground (bare-world fix)",
                           _anchor_person, _anchor_place)
    proto_feedback = ""
    _guard_failed_proposal: dict | None = None
    from construct.cohorts import FICTION_CRAFT
    play_as_note = (
        f"THE PLAYER HAS ASKED TO PLAY AS: '{play_as.strip()}'. The `protagonist` "
        f"MUST be that figure — pick the matching person: id from AVAILABLE IDS (the "
        f"character the story wrote for this role); do not pick someone else.\n"
        if play_as.strip() else "")
    for attempt in range(3):
        proposal = complete_sync(provider,
            "You are authoring the hidden arc for a text-construct scenario "
            "(novel-arc mode: the mystery IS the arc).\n\n" + FICTION_CRAFT +
            "Below is the world's "
            "people+entity digest. Choose the protagonist (the natural "
            "point-of-view character), the thematic conclusion shape, and "
            "4-6 path-independent beats.\n"
            "INSIST ON AN INTERESTING DESTINATION. The win — the conclusion shape's "
            "world_condition, reached when the climax beats are achieved — must be a "
            "HARD-WON climax: a genuine achievement the player reaches ONLY through "
            "real progress across the whole arc (bring the killer to justice, slay "
            "the dragon, lift the curse, get the ring to the fire). It must NOT be "
            "true at the start, nor reachable in the opening turn — never a born-true "
            "or trivially-satisfied state. The climax beats are discoveries or acts "
            "that take the arc to earn; a player_learns beat gates on a fact the "
            "protagonist does NOT already know. Make the destination worth playing "
            "toward.\n"
            + play_as_note +
            "Also emit `goal_statement`: ONE vivid player-facing line of "
            "aspiration in THIS world's genre, shown to the player at the start. "
            "NAME the premise stakes; a beloved archetype is GOOD ('solve the "
            "mystery and name the killer', 'slay the dragon and free the vale', "
            "'win her heart across the years', 'bring the fort through the monsoon "
            "alive'). Reveal the PROBLEM, never the SOLUTION: never the whodunit "
            "answer, the mechanism, or the specific hidden fact to be discovered.\n"
            "OPTIONALLY emit `failure_when`: the story's DECISIVE failure — authored from what THIS "
            "story is about. Use kind `event_occurs` for a decisive loss event (detection, capture, "
            "the protectee killed — a plausible event kind like 'alarm_raised'/'player_unmasked'). "
            "Use kind `time_deadline` with `deadline_minutes` (IN-WORLD minutes) ONLY when time is "
            "genuinely part of THIS story's thread — a bomb timer, the King arriving, a tide, a dawn "
            "execution. Do NOT add a time deadline to a leisurely investigation/mystery/slice-of-life "
            "(time there is pedantic and gets in the way — turns are free; the player takes as long "
            "as they need). Omit `failure_when` entirely when the story has no decisive failure.\n"
            "HARD RULE: a `player_learns` beat's `entity` MUST be one of the "
            "AVAILABLE IDS below verbatim (do NOT invent new fact:/obj: ids); "
            "its attribute/value should match a triple in the digest. For a "
            "thematic beat with no matching entity, use `event_occurs` with a "
            "plausible event kind instead.\n"
            "HARD RULE: a `player_learns` beat's `entity` MUST NOT be the PROTAGONIST "
            "themselves — the protagonist cannot LEARN a fact about themselves by "
            "investigating (you can't interview yourself). A self-realization or a deed the "
            "protagonist does is an ACT: use `event_occurs` (or a conclusory commitment) for "
            "it, never `player_learns` on the protagonist's own id.\n\n"
            + (f"{_laws_block}\nTHE DESTINATION SHOULD TURN ON A LAW where it "
               f"serves the story: the climax of a lawful world is a "
               f"law-moment — the code confronted, the delta exposed, the "
               f"metaphysic's cost paid. Never contradict a law.\n\n"
               if _laws_block else "")
            + f"AVAILABLE IDS (use these exact strings):\n{known_ids}\n\n"
            f"WORLD DIGEST:\n{digest}\n\n"
            + (f"THE PLAYER HAS CHOSEN THEIR WIN/LOSS — honour it. Author the "
               f"conclusion shape's `world_condition` toward this victory and, if "
               f"they named a way to lose, the `failure_when` toward that defeat; "
               f"set `goal_statement` to THEIR framing (the AIM). Keep the specific "
               f"hidden answer concealed — never restate the solution: <<<WIN\n"
               f"{win_direction.strip()}\nWIN>>>\n\n" if win_direction.strip() else "")
            + (f"PRIOR ATTEMPT FAILED LINT: {last_findings}; fix those — the "
               f"named entities are not in AVAILABLE IDS.\n"
               if last_findings else "")
            + proto_feedback,
            ARC_SCHEMA, tier="main", deliberate=True, task="arc")
        arc = _build_arc(proposal)
        findings = lint_arc(arc, reads)
        blocking = [f for f in findings if f.check != "2-paths"]
        if blocking:
            last_findings = [f"{f.check}: {f.message}" for f in blocking]
            logger.warning("arc lint failed (attempt %d): %s", attempt + 1, last_findings)
            arc = None
            continue
        # PROTAGONIST GUARD (Cx 160/162): the chosen protagonist must be a STAGED person, or
        # the cast can't be staged around it and clue delivery goes dark. The guard has TEETH
        # even at ZERO located people — it must NOT be gated on `located_people and ...` (that
        # would skip the check and let an unstageable protagonist into cast authoring +
        # arc_to_items on the ingest path, which never runs the viability gate). Re-author with
        # the located allowlist; keep the linted proposal for the fallback. Empty allowlist →
        # the loop exhausts, the fallback returns None, and we raise (never publish).
        #
        # THE PLAYER'S FIGURE IS STAGED, NEVER SWAPPED (#107, founder's Minutes Before
        # Bullets): when the author picked exactly the figure the player asked to BE and
        # that person is merely an UNPLACED stub, rejecting the pick trades the player's
        # chosen identity for whichever stranger happened to hold a location (he asked for
        # the defense apprentice; play cast him as a retrieval lead). Identity outranks
        # staging: give the asked-for figure ground — an ordinary `in` row at the world's
        # populated opening place — exactly the #104 anchor move, scoped to the play_as match.
        if (arc.protagonist not in located_people
                and play_as.strip() and arc.protagonist in known_ids):
            def _toks(s: str) -> set[str]:
                return set(s.lower().replace(":", " ").replace("_", " ").split())
            _want = {w for w in _toks(play_as) if len(w) > 3}
            _pick = _toks(arc.protagonist)
            if _want & _pick:
                _places = sorted(e for e in _canon_entity_ids(world)
                                 if str(e).startswith("place:"))
                # prefer the place where the located cast already stands (the
                # opening scene), so the player wakes among the story's people
                _crowd: dict[str, int] = {}
                for _lp in located_people:
                    try:
                        _ch = world.porcelain.locate(_lp)
                        if _ch:
                            _crowd[_ch[0]] = _crowd.get(_ch[0], 0) + 1
                    except Exception:  # noqa: BLE001
                        continue
                _ground = (max(_crowd, key=_crowd.get) if _crowd
                           else (_places[0] if _places else None))
                if _ground:
                    world.porcelain.ingest_structured([
                        {"entity": arc.protagonist, "attribute": "in",
                         "value": _ground, "value_type": "entity"}])
                    located_people = list(located_people) + [arc.protagonist]
                    logger.warning(
                        "protagonist %s matched play_as but was unplaced — staged "
                        "at %s (identity outranks staging, #107)",
                        arc.protagonist, _ground)
        if arc.protagonist not in located_people:
            _guard_failed_proposal = proposal
            proto_feedback = (
                f"PRIOR ATTEMPT CHOSE protagonist {arc.protagonist!r}, which is NOT a "
                f"staged character in this world. The protagonist MUST be one of these "
                f"LOCATED person ids (the characters the prose actually placed in the "
                f"world): {located_people}. Pick the point-of-view character from THESE.\n")
            logger.warning("protagonist %s not located (attempt %d); re-authoring against %s",
                           arc.protagonist, attempt + 1, located_people)
            arc = None
            continue
        if findings:
            logger.warning("arc lints with soft findings: %s", findings)
        break
    if arc is None and _guard_failed_proposal is not None:
        # Deterministic fallback (Cx 160 #1/#2): the author stayed stubborn. Rewrite the
        # last LINTED proposal's protagonist to a located person and REBUILD from it (NOT a
        # shallow dataclasses.replace — _build_arc bakes knows:<protagonist> into every beat
        # / failure_when / premise, so a replace would leave stale gates). Re-lint + re-guard.
        _real = _fallback_protagonist(world, located_people, play_as)
        if _real is not None:
            logger.warning("protagonist fallback: rebinding %s -> %s and rebuilding arc",
                           _guard_failed_proposal.get("protagonist"), _real)
            _guard_failed_proposal["protagonist"] = _real
            _candidate = _build_arc(_guard_failed_proposal)
            if not [f for f in lint_arc(_candidate, reads) if f.check != "2-paths"] \
                    and _candidate.protagonist in located_people:
                arc = _candidate
                # Sync the working proposal to the corrected one (Cx 162): downstream
                # meta/theme/goal_statement reads must come from the rebound proposal, not a
                # later lint-failed loop attempt.
                proposal = _guard_failed_proposal
    if arc is None:
        # #104 diagnosability: the old message printed only lint findings — an empty
        # `[]` hid that every attempt died at the PROTAGONIST GUARD.
        _tried = (_guard_failed_proposal or {}).get("protagonist")
        raise RuntimeError(
            f"arc failed lint/protagonist guard after 3 attempts — lint: "
            f"{last_findings or 'clean'}; guard: tried {_tried!r} against located "
            f"people {located_people or 'NONE (bare world)'}")

    # Resolve the game type(s) UP FRONT — player-chosen if given, else derived from the
    # fiction. The cast/pillar shape (below) AND the meta directive both need it; deriving
    # it only at meta-build time (as before) meant the cast block saw `game_types=None` on
    # the generate path and never fired (live-test finding 2026-06-23).
    from construct import cohorts as _co  # local: `cohorts` is rebound later in this fn
    from construct import play_styles as _ps
    resolved_game_types = _ps.resolve(game_types)
    if not resolved_game_types:
        try:
            # Strong signal: theme + the world digest (the intro isn't authored until after
            # the cast block, so we can't use it here as the old late-derivation did).
            _desc = (proposal.get("theme", "") + "\n\n" + digest)[:2000]
            _gt = _co.classify_game_type(provider, title, _desc)
            resolved_game_types = _ps.match_many(
                [_gt.get("primary", "")] + (_gt.get("secondary") or []))
        except Exception as exc:
            logger.warning("game-type derivation skipped: %s", exc)
            resolved_game_types = []

    # The POPULATED CAST (STORY-SHAPES §8): author the causal PILLARS + the people who hold
    # the clues that fill them, over the just-authored arc. GATED on solvability and fully
    # fail-open — a world that can't be authored fairly stays on the legacy (pillar-less)
    # terminal path rather than shipping an unsolvable mystery. Enrichment, never a blocker.
    cast_nodes: tuple = ()
    cast_proposal: dict | None = None
    try:
        from construct.story_shapes import author_signature_directive, shapes_for
        _prof = shapes_for(resolved_game_types) if resolved_game_types else None
        _shape = (_prof or {}).get("shape")
        _shapes = [_prof["shape"], *_prof["secondary"]] if _prof else []
        if _shape:
            import dataclasses as _dc

            from construct import cohorts as _co
            from construct.cast import (
                beat_delivery_targets,
                build_pillars,
                cast_from_proposal,
                check_solvability,
                disambiguate_cast_identities,
                validate_beat_delivery,
                validate_signature_support,
            )
            # IDENTITY COHERENCE (#92, Cx 404): the canon identity text a reused person id
            # must be compatible with — read once per id, best-effort.
            _idreads = PorcelainWorldReads(world)

            def _identity_of(pid: str) -> str | None:
                try:
                    bits = [_idreads.state(pid, a) for a in ("role", "title")]
                    s = " ".join(str(b) for b in bits if b)
                    return s or None
                except Exception:  # noqa: BLE001
                    return None
            # The author-insist half of GENRE-SIGNATURE-ELEMENTS (Cx 097): the fundamental
            # elements the generated fiction MUST establish for this shape, fed to the cohort.
            _sig_dir = author_signature_directive(resolved_game_types)
            # BEAT-DELIVERY-COHERENCE (obs #3): the arc's InFrame rising beats the cast MUST make
            # deliverable, so the SETUP→RISING→CRISIS ladder fires (not just the Occurred climax).
            _beat_targets = beat_delivery_targets(arc.beats)
            # Re-author up to 3x, feeding back the solvability problems (mirrors the arc
            # lint retry) — most misses are one required pillar lacking a none/pressure
            # genuine clue, which the feedback fixes. Still fail-open to pillar-less.
            _feedback = ""
            for _attempt in range(3):
                _cprop = _co.author_cast(provider, digest, proposal.get("theme", ""),
                                         _shape, arc.protagonist, people, feedback=_feedback,
                                         signature_directive=_sig_dir,
                                         beat_targets=_beat_targets,
                                         laws_directive=_laws_block)
                # IDENTITY COHERENCE GATE (#92, Cx 404 A): a reused canon person id whose
                # established role contradicts the proposed conception is DISAMBIGUATED on
                # the RAW proposal (the persisted meta["cast"] must carry the fresh id too —
                # remapping only the typed nodes would reintroduce the collision on reload).
                _cprop, _remaps = disambiguate_cast_identities(
                    _cprop, _identity_of, set(known_ids))
                if _remaps:
                    logger.info("cast identity collision(s) disambiguated: %s", _remaps)
                _cast, _specs = cast_from_proposal(_cprop)
                _req = [pid for pid, _label, required in _specs if required]
                # Validate holders against canon ids too (Cx 032: a clue on a phantom NPC
                # can never be interviewed) — known_ids is the canon allowlist above.
                # For DEDUCTION, also gate on PHYSICAL staging (INVESTIGATION-SHAPE.md §3d):
                # every required holder + the culprit must be reachable in play, with a
                # spoon-fed opening (>=2 at_scene + a first_witness). A malformed whodunit
                # cast must fail here (→ re-author / pillar-less), never be patched by improv.
                # Admit authored HYBRID holders (obj:/place: sites/artifacts the player EXAMINES —
                # GENRE-SIGNATURE-ELEMENTS / Discovery, Cx 109): they don't pre-exist in canon, but
                # we seed them as reachable canon at staging below, so they're legal holders here.
                _hybrid = {n.node_id for n in _cast
                           if n.node_id.startswith(("obj:", "place:"))}
                # Disambiguated fresh persons (#92) are admitted as cast-authored canon
                # below, exactly like hybrids — legal holders here.
                _problems = check_solvability(
                    _req, _cast, known_ids=set(known_ids) | _hybrid | set(_remaps.values()),
                    require_staging=(_shape == "deduction"))
                # GENRE-SIGNATURE-ELEMENTS lint (Cx 097): the genre's hard signature promises
                # must actually ship (e.g. a deduction cast needs a strong red herring + a
                # cross-suspicion edge). Merged into the same feedback/retry loop as solvability.
                _problems = _problems + validate_signature_support(_shapes, _cast)
                # BEAT-DELIVERY-COHERENCE lint (obs #3): every REQUIRED rising beat must have a
                # live-reachable clue surfacing its fact — else the ladder is dead and the arc
                # rushes its climax. Merged into the same feedback/retry loop.
                _problems = _problems + validate_beat_delivery(_beat_targets, _cast)
                if not _problems and _cast:
                    arc = _dc.replace(arc,
                                      pillars=build_pillars(_specs, _cast, arc.protagonist))
                    cast_nodes, cast_proposal = _cast, _cprop
                    # ADMIT disambiguated persons as cast-authored canon (#92, Cx 404 req 3):
                    # a fresh person:<slug>_N exists nowhere yet — seed kind/name/role (+
                    # pronouns if authored) so presence, staging, and reference all work.
                    if _remaps:
                        _admit: list[dict] = []
                        _by_id = {str(m.get("id")): m for m in (_cprop.get("cast") or [])}
                        for _orig, _fresh in _remaps.items():
                            _m = _by_id.get(_fresh, {})
                            _admit.append({"entity": _fresh, "attribute": "kind",
                                           "value": "person", "timeless": True})
                            _admit.append({"entity": _fresh, "attribute": "name",
                                           "value": _orig.split(":", 1)[-1]
                                           .replace("_", " ").title()})
                            if _m.get("surface_role"):
                                _admit.append({"entity": _fresh, "attribute": "role",
                                               "value": str(_m["surface_role"])[:120]})
                            if (_m.get("pronouns") or "") in ("he/him", "she/her",
                                                              "they/them"):
                                _admit.append({"entity": _fresh, "attribute": "pronouns",
                                               "value": _m["pronouns"], "timeless": True})
                        world.porcelain.ingest_structured(_admit)
                        logger.info("admitted %d disambiguated cast identit(ies) as canon",
                                    len(_remaps))
                    logger.info("authored %d pillar(s) + %d cast member(s) for %s (attempt %d)",
                                len(arc.pillars), len(_cast), _shape, _attempt + 1)
                    break
                _feedback = "; ".join(_problems) or "the cast had no members"
                logger.warning("cast not solvable (attempt %d): %s", _attempt + 1, _problems)
            else:
                logger.warning("cast unsolvable after retries — shipping pillar-less (legacy)")
                logger.info("authored %d pillar(s) + %d cast member(s) for %s",
                            len(arc.pillars), len(_cast), _shape)
    except Exception as exc:  # cast authoring NEVER sinks a build
        logger.warning("cast authoring skipped: %s", exc)
        cast_nodes, cast_proposal = (), None

    world.porcelain.ingest_structured(
        arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    # The portfolio manifest (LIVING-WORLD-GENERATOR P1): session zero authors
    # one (main) arc, so the registry is a single-entry portfolio. It is written
    # explicitly (rather than relying on the fail-open default) so the multi-arc
    # load path is exercised uniformly; side arcs are added by the P2 generator.
    world.porcelain.ingest_structured(
        arc_io.portfolio_items([arc.arc_id], main_arc_id=arc.arc_id))
    world.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(0)},
    ], frame="session:main")

    # NPC-knows seeding (P4 frame-scoped secrecy); reversible (knows:
    # frames only).
    _emit(on_stage, "Stage 5 · Seeding character knowledge · frame-scoped "
                    "secrecy (knows:<id>, P4) (PB)")
    cast = _seed_cast(arc.protagonist, people)
    from construct.arc.executor import arc_protected_keys
    seeded = seed_character_frames(world, provider, cast, digest,
                                   protagonist=arc.protagonist,
                                   protected=arc_protected_keys(arc))
    # Seed each cast member's CLUES into their own knows:<npc> frame — the diegetic pieces
    # they can surface when interviewed (the clue/pillar metadata stays host-side). The
    # protagonist never holds these (they DISCOVER them in play, §8). Fail-open per frame.
    if cast_nodes:
        from construct.cast import cast_seed_plan
        for _frame, _items in cast_seed_plan(cast_nodes):
            if _frame == f"knows:{arc.protagonist}":
                continue  # never pre-seed the player with the answers
            try:
                world.porcelain.ingest_structured(_items, frame=_frame)
            except Exception as exc:  # one bad frame must not sink the seal
                logger.warning("cast clue seed for %s skipped: %s", _frame, exc)
        # CAST IDENTITY (#87, the Tin Ear gender drift): each member's authored pronouns as
        # ordinary timeless canon truth — the render reads it and holds voice consistent.
        try:
            from construct.cast import cast_identity_plan
            _idrows = cast_identity_plan(cast_nodes)
            if _idrows:
                world.porcelain.ingest_structured(_idrows)
                logger.info("seeded %d cast pronoun row(s)", len(_idrows))
        except Exception as exc:  # identity seeding must never sink the seal
            logger.warning("cast identity seed skipped: %s", exc)
        # STAGE the cast in PLACE (INVESTIGATION-SHAPE.md §3a/§3c-layer-1): write ordinary
        # canon `in` facts so the at_scene cast is co-located with the protagonist's crime
        # scene and remote suspects sit in referable places to travel to. The scene place is
        # the protagonist's own resolved location (narration = ground truth — we anchor on
        # where the player actually is). No location → no staging (the gate already required
        # at_scene members for deduction; a missing scene is logged, never invented here).
        try:
            from construct.cast import cast_location_plan
            # AS-OF PLAY HORIZON (Cx 255 blocking #1, generalized): anchor the opening cast to
            # where the protagonist is AT THE OPENING, never the timeline head (the aftermath).
            # `_opening_scene_place` prefers the opening-horizon location, falls back to the
            # protagonist's EARLIEST source location (a saga whose opening chapters are
            # atmospheric and place no cast — emberroad), and only then to head (legacy).
            _scene_place = _opening_scene_place(world, arc.protagonist, opening_as_of)
            if _scene_place:
                _loc_items = cast_location_plan(cast_nodes, _scene_place)
                # STAGE THE PROTAGONIST at the opening scene too (Cx 255 generalized): in a
                # horizon world their source `in` rows may all sit ABOVE the opening (placed
                # only mid-journey), so without this they'd have NO location at the play horizon
                # and the opening would render nowhere. Stamped at turn_time(0) like the cast.
                _loc_items = [it for it in _loc_items
                              if not (it.get("entity") == arc.protagonist
                                      and it.get("attribute") == "in")]
                _loc_items.append({"entity": arc.protagonist, "attribute": "in",
                                   "value": _scene_place, "value_type": "entity"})
                if _loc_items:
                    # Stamp the opening `in` rows on the ENTRY axis (turn_time(0) == entry_epoch)
                    # so they WIN the containment fold over any aftermath `in` the source prose
                    # narrated (obs #3 half 3). Place DEFINITIONS (kind/name) stay timeless.
                    for _it in _loc_items:
                        if _it.get("attribute") == "in":
                            _it["valid_from"] = turn_time(0)
                    world.porcelain.ingest_structured(_loc_items)
                    logger.info("staged %d cast location fact(s) at scene %s (entry epoch %.1f)",
                                len(_loc_items), _scene_place, turn_time(0))
                # HYBRID holders (obj:/place: the player EXAMINES — Discovery, Cx 109): admit them
                # as real canon entities (kind) so they're referable + present for the EXAMINE
                # channel. Their `in` is staged above; their clue rides the player frame (no
                # knows:<obj> frame — cast_seed_plan already skips non-person holders).
                _hk = [{"entity": n.node_id, "attribute": "kind",
                        "value": "object" if n.node_id.startswith("obj:") else "place",
                        "timeless": True}
                       for n in cast_nodes if n.node_id.startswith(("obj:", "place:"))]
                if _hk:
                    world.porcelain.ingest_structured(_hk)
                    logger.info("admitted %d hybrid obj/place holder(s) as canon", len(_hk))
            else:
                logger.warning("no resolved scene place for %s — cast staging skipped",
                               arc.protagonist)
        except Exception as exc:  # staging must never sink the seal
            logger.warning("cast location staging skipped: %s", exc)

        # LAW EMBODIMENT LINKS (#105, Cx 470 ruling 5): the cast author declared
        # which members/institutions exist BECAUSE of which law — written as
        # queryable canon (law:<slug> embodied_by <entity>), never prose-only.
        if laws and cast_proposal is not None:
            try:
                _emb = laws_mod.embodiment_rows(
                    laws, cast_proposal.get("law_embodiment") or [],
                    _canon_entity_ids(world))
                if _emb:
                    world.porcelain.ingest_structured(_emb)
                    logger.info("linked %d law embodiment(s) to canon", len(_emb))
            except Exception as exc:  # noqa: BLE001 — links must never sink a seal
                logger.warning("law embodiment links skipped: %s", exc)

        # OPENING-GROUNDING (founder 2026-06-30): author the player's STANDING relationship to
        # each present/known cast member into knows:<protagonist>, so the grounded cold open
        # (Session._player_grounding) introduces each as who-they-are-TO-the-player, not a
        # third-party intro. Fail-open; non-spoiler (protected keys screened here + at render).
        try:
            seed_player_relationships(world, provider, arc.protagonist, cast_nodes, digest,
                                      protected=arc_protected_keys(arc))
        except Exception as exc:  # relationship authoring NEVER sinks the seal
            logger.warning("player-relationship seeding skipped: %s", exc)

    _emit(on_stage, "Stage 5.5 · Distilling narrative flavor · genre/voice overlay "
                    "+ per-entity feel (host annotation; engine stays vanilla)")
    style = _author_flavor(world, provider, digest, reads)

    _emit(on_stage, "Stage 6 · Sealing the scenario")
    meta = {"title": title, "protagonist": arc.protagonist,
            "theme": proposal["theme"], "stance": "fiction", "mode": "pure",
            # The world-level STYLE/voice overlay (NARRATIVE-FLAVOR-INGEST): a
            # one-time render directive fed to the narrator every turn (HOW to
            # write, never facts). Scenario-level, like theme.
            "style": style,
            # `mode` (pure/coauthor) is turn-loop input authority — never
            # overloaded. `scenario_mode` is the win/loss-vs-freeplay axis
            # (WIN-LOSS §10, Cx 063): separate field so the declaration-denial
            # guard can't be silently disabled. Inert until termination is wired.
            "scenario_mode": "endless" if endless else "win_loss",
            # Scope = arc referents (now incl. pillar clue-fact entities) UNION the cast
            # node ids, so interview delivery actually sees present cast NPCs at play time
            # (Cx 032 blocker 1 — the scope is the candidate set for presence/interview).
            "arc_scope": sorted(
                {e for e in arc_entities(arc) if reads.has_entity(e)}
                | {n.node_id for n in cast_nodes if reads.has_entity(n.node_id)}),
            # The portfolio manifest mirror on meta (LIVING-WORLD-GENERATOR P1):
            # which arc is main (terminal-bearing) and the active arc ids.
            "main_arc": arc.arc_id, "arc_ids": [arc.arc_id],
            # The scenario entry epoch (obs #3 half 3): the live-play time origin, ABOVE every
            # pre-play valid_from, so the opening staging + live turns win the containment fold
            # over aftermath rows the source narrated. Play re-establishes it on the contextvar
            # (Session). Absent / == TURN_EPOCH for one-timeframe worlds (a no-op).
            "entry_epoch": entry_epoch,
            "seeded_frames": seeded, "endless": bool(endless)}
    # WORLD LAWS (#105): the sealed law objects + the reality register ride
    # meta for the turn loop's cheap read (canon law:* rows stay the truth).
    if laws:
        meta["laws"] = laws
    if reality_register:
        meta["reality_register"] = reality_register
    # AS-OF PLAY HORIZON (B' S2): a HORIZON world records its opening coordinate + the
    # fail-closed ceiling so Session binds every read to `opening_as_of + turns` (S3). Absent
    # on legacy/interview worlds → Session reads the timeline head (the epoch-raise path).
    if opening_as_of is not None:
        meta["opening_as_of"] = opening_as_of
        meta["next_source_as_of"] = next_source_as_of
        meta["source_step"] = source_step
    # The populated cast (STORY-SHAPES §8), host-side control data the turn loop reads for
    # interview delivery (which NPC holds which clue, gated by reveal_condition). Stored as
    # the raw proposal; the session rebuilds typed nodes via cast.cast_from_proposal. Only
    # present when a solvable cast was authored (else the world plays the legacy path).
    if cast_proposal is not None:
        meta["cast"] = cast_proposal
    # The player-facing aim is a derivative of the hidden destination, NOT a
    # plot:/canon row (Kernos ruling): a leak-checked line on the scenario
    # seal, shown only in win_loss mode. Freeplay/endless has no fixed aim.
    if not endless:
        meta["goal_statement"] = _player_goal(proposal, world, win_direction)
    # The thematic introduction (founder, 2026-06): the premise/stakes in voice,
    # ending on the player's non-spoiling aim — shown at the opening. Authored
    # last (it needs the style + the aim). Fail-open: never sinks the build.
    _emit(on_stage, "Stage 6.1 · Authoring the thematic introduction "
                    "(premise/stakes → the non-spoiling aim)")
    from construct import cohorts
    aim = meta.get("goal_statement") or "find your way through the story to its end"
    try:
        # DISCLOSURE (founder, #105): laws the character inherently understands
        # are introduced as lived context; discovered laws never surface here.
        _known_laws = laws_mod.laws_block(laws_mod.understood_laws(laws))
        meta["intro"] = (cohorts.author_intro(provider, digest, proposal["theme"],
                                              style, aim,
                                              laws_directive=_known_laws)
                         .get("intro") or "").strip()
    except Exception as exc:
        logger.warning("thematic intro skipped: %s", exc)
        meta["intro"] = ""
    # A short genre/story-type shelf-tag (founder): so the library can tell a guest
    # what STYLE each title is. Fail-open — a missing tag just omits it.
    try:
        meta["genre"] = cohorts.classify_genre(provider, title,
                                                meta.get("intro") or proposal["theme"])
    except Exception as exc:
        logger.warning("genre tag skipped: %s", exc)
    # The BACK-OF-THE-BOOK PREMISE (founder): a concrete, canon-faithful where/when/
    # what-system blurb the Foyer grounds its pregame world-intro in — authored FROM
    # the digest so it describes the REAL world (not the model improvising one from a
    # thin theme), and distinct from the voice `style` and the thematic `intro`.
    # Fail-open: the Foyer falls back to intro/style+theme if absent.
    _emit(on_stage, "Stage 6.2 · Authoring the back-of-the-book premise")
    try:
        meta["premise"] = (cohorts.author_premise(
            provider, digest, proposal["theme"], meta.get("genre", ""))
            .get("premise") or "").strip()
    except Exception as exc:
        logger.warning("premise authoring skipped: %s", exc)
        meta["premise"] = ""
    # The GAME TYPE(S) — the maintained play-style directive(s) the narrator holds
    # all game (GAME-TYPES.md). Player-chosen at build if given; else DERIVED from
    # the fiction (also how ingested worlds get a type — locked to what it is).
    # Resolved up front (before the cast block) so the cast/pillar shape and this directive
    # agree; just record it on meta here.
    if resolved_game_types:
        meta["game_type"] = resolved_game_types
    # #95 DEATH POLICY (DEATH-TESTAMENT.md, Cx 422): does the player character's death
    # end this story? One build-time judgment; per-chapter granularity (continuation
    # re-derives). Fail-open to `shielded` — no world kills by accident.
    try:
        _dp = cohorts.classify_death_policy(
            provider, meta.get("genre", ""),
            ", ".join(resolved_game_types or []), meta.get("premise", ""))
        meta["death_policy"] = (_dp.get("policy") or "shielded").strip()
        meta["death_policy_reason"] = (_dp.get("reason") or "").strip()
    except Exception as exc:
        logger.warning("death policy derivation skipped: %s", exc)
        meta["death_policy"] = "shielded"
    # THE BUILD SEAL (BUILD-SESSION take-up, PB 094): both creation paths open a
    # porcelain build session (`begin_build`) — every ingest defers durability
    # classification, and this ONE `seal_build` pass classifies the session's
    # rows and restores inline mode. Rules-only by default (BUILD LATENCY #3 /
    # PB 081: ~272s/build saved; ambiguous attrs take the doctrine's asymmetric
    # STATE default — correctness-safe); CONSTRUCT_FAST_CLASSIFY=0 sends
    # ambiguous rows to the batch LM pass instead. No session open (a caller
    # that never entered build mode) → nothing to seal, quietly.
    _fast_classify = os.getenv("CONSTRUCT_FAST_CLASSIFY", "1") != "0"
    try:
        _emit(on_stage, "Stage 6.2 · Classifying durability · "
                        + ("RULES (zero model calls — the build's main efficiency win)"
                           if _fast_classify else "BATCHED grouped model calls"))
        _seal = world.porcelain.seal_build(model=not _fast_classify)
        logger.info("build sealed: %s row(s) classified (seq %s)",
                    _seal.get("classified"), _seal.get("seq_range"))
    except RuntimeError:
        pass  # no build session open — nothing deferred, nothing to seal
    except Exception as exc:  # never sink a build on the optimization
        logger.warning("durability classification failed: %s", exc)
    spath.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def create_scenario_from_ingest(name: str, prose_path: Path,
                                provider: Provider, endless: bool = False,
                                on_stage=None, win_direction: str = "",
                                play_as: str = "", game_types: list | None = None,
                                laws: list | None = None,
                                reality_register: str = "") -> dict:
    """Session-zero Path A: fresh ingest of a work through OUR pipeline
    → pristine scenario. Emits per-stage status via `on_stage`. `win_direction`
    (optional) is the player's own chosen win/loss framing, threaded to the arc
    author + the player-facing goal. `laws`/`reality_register` (#105) arrive
    only from the GENERATED path (the fiction was written on them); a real
    ingested book keeps its own implicit constitution — never retrofitted."""
    WORLDS_DIR.mkdir(exist_ok=True)
    spath = scenario_path(name)
    if spath.exists():
        raise FileExistsError(f"scenario {name!r} already exists at {spath}")

    text = prose_path.read_text()
    title = text.splitlines()[0].lstrip("# ").strip() or name
    world = _world(spath, name, model=engine_tier_dispatch(provider),
                   stance="fiction", title=title,
                   description=f"Ingested from {prose_path.name} via Construct session-zero")
    try:
        # WORLD-A: chunked ingest, scene cursor advancing per chunk.
        # DEFER durability classification (the engine's supported "harness defers
        # to batch" mode): per-row inline classification was ~400 serial cheap-
        # model calls — ~65% of a ~35-min build (profiled). With it deferred, the
        # rows land unclassified (read as the STATE default meanwhile), and one
        # BATCHED pass at the end of _finalize classifies them in grouped calls —
        # "same judgments, fewer round trips" (engine classify_all docstring).
        world.porcelain.begin_build()
        from construct.arc.executor import SOURCE_STEP
        chunks = _chunk_chapters(text)
        _emit(on_stage, f"Stage 1 · Ingesting prose → pattern-buffer · model "
                        f"extraction → assertions, provenance-tracked ({len(chunks)} chunks)")
        # BUILD LATENCY #3 Win 2 (PB 081): EXTRACTION is the slow LM step and the chunks are
        # independent (coreference is the Stage-2 reconcile pass). `porcelain.extract` is
        # READ-ONLY (no buffer write), so run all chunk extractions CONCURRENTLY (PB's only
        # write-serialization constraint is the single SQLite connection — extraction never
        # writes), then `ingest_structured` the results SERIALLY in chunk order. ~311s of serial
        # extraction collapses toward the slowest single chunk. Default on; CONSTRUCT_PARALLEL_
        # EXTRACT=0 restores the serial path.
        #
        # AS-OF-PLAY-HORIZON is preserved exactly: each chunk's rows are committed with the cursor
        # advanced to i*SOURCE_STEP (S2 spacing) + cursor_authoritative=True (S1 — the cursor
        # governs valid_from; diegetic dates demote to source_valid_from), and classify is DEFERRED
        # to the finalize rules pass (Win 1). Fail-open per chunk preserved on both extract + ingest.
        _parallel_extract = os.getenv("CONSTRUCT_PARALLEL_EXTRACT", "1") != "0"
        skipped = 0
        items_by_chunk: dict[int, list] = {}
        if _parallel_extract and len(chunks) > 1:
            from concurrent.futures import ThreadPoolExecutor
            cap = max(1, int(os.getenv("CONSTRUCT_EXTRACT_CONCURRENCY", "8")))
            with ThreadPoolExecutor(max_workers=cap) as pool:
                futs = {i: pool.submit(world.porcelain.extract, chunk, extract="full")
                        for i, chunk in enumerate(chunks, start=1)}
                for i, fut in futs.items():
                    try:
                        items_by_chunk[i] = fut.result()
                        _emit(on_stage, f"   …chunk {i}/{len(chunks)} extracted")
                    except Exception as exc:  # noqa: BLE001 — one bad chunk must not sink
                        skipped += 1
                        logger.warning("chunk %d/%d extract failed (%s: %s) — skipping",
                                       i, len(chunks), type(exc).__name__, str(exc)[:200])
                        _emit(on_stage, f"   …chunk {i}/{len(chunks)} SKIPPED ({type(exc).__name__})")
        for i, chunk in enumerate(chunks, start=1):
            try:
                if _parallel_extract and len(chunks) > 1:
                    items = items_by_chunk.get(i)
                    if items is None:
                        continue  # extract already failed + logged
                    # advance the cursor to this chunk's coordinate, then commit serially
                    world.ingestor.cursor.advance(float(i) * SOURCE_STEP)
                    world.porcelain.ingest_structured(
                        items, classify="defer", cursor_authoritative=True)
                else:
                    # serial path (legacy / single chunk): extract+ingest in one call
                    world.porcelain.ingest(chunk, source=f"doc:{prose_path.stem}",
                                           at=float(i) * SOURCE_STEP,
                                           cursor_authoritative=True)
                    _emit(on_stage, f"   …chunk {i}/{len(chunks)} extracted")
            except Exception as exc:  # noqa: BLE001 — one bad chunk must not sink
                # A single extraction/ingest defect (e.g. a cycle-forming containment edge the
                # model wrote) raises a hard engine invariant. Fail OPEN per chunk: log loudly,
                # drop that chunk's facts, keep building — the viability gate still catches a
                # world too thin to play.
                skipped += 1
                logger.warning("chunk %d/%d ingest failed (%s: %s) — skipping; the "
                               "build continues", i, len(chunks),
                               type(exc).__name__, str(exc)[:200])
                _emit(on_stage, f"   …chunk {i}/{len(chunks)} SKIPPED "
                                f"({type(exc).__name__})")
                continue
        if skipped:
            logger.warning("ingest completed with %d/%d chunk(s) skipped", skipped, len(chunks))
        return _finalize_scenario(world, name, title, provider, spath, endless,
                                  on_stage, win_direction=win_direction,
                                  play_as=play_as, game_types=game_types,
                                  source_step=SOURCE_STEP,
                                  laws=laws, reality_register=reality_register)
    except BaseException:
        world.close()
        spath.unlink(missing_ok=True)
        spath.with_suffix(".meta.json").unlink(missing_ok=True)
        raise
    finally:
        world.close()


def create_scenario_from_interview(name: str, brief: str, provider: Provider,
                                   endless: bool = False, on_stage=None,
                                   win_direction: str = "", play_as: str = "",
                                   game_types: list | None = None,
                                   reality_register: str = "") -> dict:
    """Session-zero Path B: build a world LIVE from a brief (no source
    text). An interviewer cohort expands the brief into the constitutive
    spine — charter, places + lateral graph, key NPCs with dispositional
    spines, the opening situation — committed as `stated` canon, then the
    shared tail authors the arc and seeds frames. The brief is the human's
    input (genre/setting/characters/situation, however much they give)."""
    from construct import cohorts

    WORLDS_DIR.mkdir(exist_ok=True)
    spath = scenario_path(name)
    if spath.exists():
        raise FileExistsError(f"scenario {name!r} already exists at {spath}")

    # WORLD LAWS (#105): constitution first, so the spine is authored ON the
    # laws (institutions exist because of them). Fail-open to law-less.
    _emit(on_stage, "Stage 0 · Authoring the world's deep laws · the universe's "
                    "governing dynamics (register-gated)")
    laws, reality = _author_world_laws(provider, brief, reality_register,
                                       game_types)
    from construct import laws as _laws_mod
    _emit(on_stage, "Stage 1 · Interviewing → pattern-buffer · expanding the brief "
                    "into a constitutive spine (stated canon)")
    spine = cohorts.interview_world(provider, brief, play_as=play_as,
                                    laws_directive=_laws_mod.laws_block(laws))
    title = (spine.get("title") or name).strip()
    world = _world(spath, name, model=engine_tier_dispatch(provider),
                   stance="fiction", title=title,
                   description=spine.get("description", "Built live via Construct interview"))
    try:
        items = spine.get("items", [])
        if not items:
            raise RuntimeError("interview produced no world spine")
        # Authoring time: the interviewer is the author → `stated` canon
        # (the gate's default for structured items). Cursor at the opening.
        world.porcelain.begin_build(at=1.0)
        world.porcelain.ingest_structured(items)
        logger.info("interview authored %d spine items", len(items))
        # game_types pass-through (parity with the ingest path): a caller may FORCE the
        # game-type(s)/shape (else _finalize derives it from the digest). The interview path is
        # single-spine, so no source-axis spacing → no source_step (legacy/head reads).
        return _finalize_scenario(world, name, title, provider, spath, endless,
                                  on_stage, win_direction=win_direction,
                                  play_as=play_as, game_types=game_types,
                                  laws=laws, reality_register=reality)
    except BaseException:
        world.close()
        spath.unlink(missing_ok=True)
        spath.with_suffix(".meta.json").unlink(missing_ok=True)
        raise
    finally:
        world.close()


class ViabilityError(RuntimeError):
    """A generated scenario was ingested but failed the post-ingest
    viability gate (STARTUP-ENTRY / Cx 063 #6). The published `.world`/
    `.meta.json` are removed; the generated source is preserved for audit
    at `source_path`. Raised so the caller surfaces an actionable failure
    instead of a playable-but-broken scenario."""

    def __init__(self, name: str, source_path: Path, problems: list[str]) -> None:
        self.name = name
        self.source_path = source_path
        self.problems = problems
        super().__init__(
            f"generated scenario {name!r} failed the viability gate "
            f"({'; '.join(problems)}); source preserved at {source_path}")


def _save_generated_prose(name: str, work: dict) -> Path:
    """Persist the authored bible to the authoring side of the firewall,
    collision-proof (never clobber an existing world's source). Ensures a
    leading `# Title` line so the ingest pipeline reads the title."""
    GENERATED_DIR.mkdir(exist_ok=True)
    title = (work.get("title") or name).strip()
    prose = (work.get("prose") or "").strip()
    if not prose:
        raise RuntimeError("story-author produced no prose")
    # Ensure an h1 title line (the ingest pipeline reads the title from line 1).
    # A leading h2 ('## chapter') is NOT a title — prepend one above it.
    if not prose.lstrip().startswith("# "):
        prose = f"# {title}\n\n{prose}"
    path, n = GENERATED_DIR / f"{name}.md", 2
    while path.exists():
        path, n = GENERATED_DIR / f"{name}_{n}.md", n + 1
    path.write_text(prose)
    return path


def _unpublish_scenario(name: str) -> None:
    """Remove a published scenario's `.world`/`.meta.json` (+ any play
    slot). Used when the viability gate rejects a generated world; the
    generated source is deliberately NOT touched (kept for audit)."""
    spath = scenario_path(name)
    spath.unlink(missing_ok=True)
    spath.with_suffix(".meta.json").unlink(missing_ok=True)
    slot_path(name).unlink(missing_ok=True)


def _assess_viability(name: str, meta: dict) -> list[str]:
    """Post-ingest viability gate (Cx 063 #6, PB 064: expressible on shipped
    reads). Returns a list of problems — empty means playable. Checks entry
    material (title, a resolvable protagonist, ≥2 people, ≥1 place), that the
    arc seeded (arc_scope + a knowledge frame), and a cold establishing-set
    read renders a non-empty 'world at rest'. Arc lint already passed (it is
    fatal in `_finalize_scenario`), so it is not re-checked here."""
    problems: list[str] = []
    if not meta.get("title"):
        problems.append("no title")
    protagonist = meta.get("protagonist")
    if not protagonist:
        problems.append("no protagonist")
    if not meta.get("arc_scope"):
        problems.append("empty arc_scope")
    if not meta.get("seeded_frames"):
        problems.append("no character knowledge seeded")

    world = _world(scenario_path(name), name)
    try:
        reads = PorcelainWorldReads(world)
        ids = _canon_entity_ids(world)
        people = [e for e in ids if e.startswith("person:")]
        places = [e for e in ids if e.startswith("place:")]
        if len(people) < 2:
            problems.append(f"too few people for entry ({len(people)})")
        if not places:
            problems.append("no places for entry")
        if protagonist and not reads.has_entity(protagonist):
            problems.append(f"protagonist {protagonist} absent from canon")
        # The protagonist must be STAGED, not merely present (Cx 160): an unlocated role
        # id passes has_entity but leaves the cast unstageable and clue delivery dark — the
        # exact real-build failure. This is the staging-invariant teeth at the viability gate.
        elif protagonist and not world.porcelain.locate(protagonist):
            problems.append(f"protagonist {protagonist} has no resolved location "
                            f"(unstageable — cast cannot be placed around it)")
        scope = meta.get("arc_scope") or []
        if scope:
            snap = world.porcelain.snapshot(sorted(scope), lens="establishing_set")
            if not snap.get("facts"):
                problems.append("establishing set is empty (no coherent cold-open)")
        # Born-won guard: a win_loss world whose destination is already satisfied at
        # genesis would END on turn 1 (the dragon-wins-immediately failure). The win
        # must be a hard-won climax, not a born-true state. Fail-open on arc-load.
        if meta.get("scenario_mode") == "win_loss":
            try:
                from construct.arc.conditions import Truth, evaluate
                _arc = arc_io.arc_from_frame(reads)
                if evaluate(_arc.shape.world_condition, reads) is Truth.TRUE:
                    problems.append("win condition already satisfied at genesis — the "
                                    "story would be won on turn 1 (the destination must "
                                    "be a hard-won climax, not a born-true state)")
            except Exception as exc:  # never crash the gate on an arc-load hiccup
                logger.warning("born-won viability check skipped: %s", exc)
    finally:
        world.close()
    return problems


def create_scenario_from_generated(name: str, provider: Provider, *, seed: str = "",
                                   endless: bool = False, on_stage=None,
                                   win_direction: str = "", play_as: str = "",
                                   game_types: list | None = None,
                                   reality_register: str = "") -> dict:
    """Session-zero Path 2 (STARTUP-ENTRY §3): author a complete HIDDEN story
    from an optional seed, save it on the authoring side of the firewall,
    ingest it through the UNCHANGED six-stage pipeline, then GATE on
    post-ingest viability before declaring the scenario built. Prose-first is
    Construct's showcase loop (fiction → projection). On gate failure the
    generated source is preserved for audit and the published world is removed
    (ViabilityError) — never a playable-but-broken scenario (Cx 063 #6)."""
    from construct import cohorts

    WORLDS_DIR.mkdir(exist_ok=True)
    if scenario_path(name).exists():
        raise FileExistsError(f"scenario {name!r} already exists")

    _emit(on_stage, "Stage 0 · Authoring the hidden source story · prose-first "
                    "(the showcase loop: fiction → projection)")
    # World-structural author-insist (GENRE-SIGNATURE-ELEMENTS.md / Cx 099 #3): when the genre is
    # CHOSEN upfront, the world-build authoring gets the shape's author-insist signature too — so
    # non-cast-shaped elements (the_clock, the_place_as_character, the_made_thing) are established
    # in the source fiction, not only the cast. Grows on demand: empty when game_types is unknown
    # (surprise-me), where the cast-shaped signature still rides author_cast after shape derivation.
    from construct.story_shapes import author_signature_directive as _asd
    _story_sig = _asd(game_types) if game_types else ""
    # WORLD LAWS (#105): the constitution is authored FIRST, so the source
    # fiction is generated ON the laws — institutions exist because of them
    # (the Jedi property), not as retrofitted texture. Fail-open: a law-less
    # world builds exactly as before.
    _emit(on_stage, "Stage 0 · Authoring the world's deep laws · the universe's "
                    "governing dynamics (register-gated)")
    laws, reality = _author_world_laws(provider, seed, reality_register,
                                       game_types)
    from construct import laws as _laws_mod
    _laws_dir = _laws_mod.laws_block(laws)
    work = cohorts.author_story(provider, seed=seed, win_direction=win_direction,
                                play_as=play_as, signature_directive=_story_sig,
                                laws_directive=_laws_dir)
    prose_path = _save_generated_prose(name, work)
    _emit(on_stage, f"   …hidden bible saved (authoring side of the firewall) "
                    f"→ {prose_path}")

    meta = create_scenario_from_ingest(name, prose_path, provider,
                                       endless=endless, on_stage=on_stage,
                                       win_direction=win_direction, play_as=play_as,
                                       game_types=game_types,
                                       laws=laws, reality_register=reality)

    _emit(on_stage, "Stage 7 · Viability gate · entry material + cold-open smoke "
                    "over shipped reads")
    problems = _assess_viability(name, meta)
    if problems:
        _unpublish_scenario(name)
        raise ViabilityError(name, prose_path, problems)
    _emit(on_stage, "   …viable — scenario published")
    return meta


def _canon_entity_ids(world: Any) -> set[str]:
    """All entity ids that appear in canon — the porcelain roster verb
    (BOUNDED-READS take-up, PB 092/094): frame-bound by construction."""
    return set(world.porcelain.entities("canon"))


def _known_people(world: Any) -> list[str]:
    """Person entities in canon."""
    return sorted(e for e in _canon_entity_ids(world) if e.startswith("person:"))


#: Cap on entities offered to the flavor cohort (people/places/things).
FLAVOR_ENTITY_CAP = 40


def _author_flavor(world: Any, provider: Provider, digest: str, reads: Any) -> str:
    """Distill the fiction's narrative flavor at ingest (NARRATIVE-FLAVOR-INGEST):
    a world-level STYLE/voice directive (returned, → scenario meta) and a
    per-entity FEEL written as an ordinary attribute on each people/place/thing
    (canon + player-frame mirror, so the narrator's scene read surfaces it). The
    engine never sees 'flavor' as a concept — it's host annotation over vanilla
    facts. Fail-open: a flavor-cohort failure must never sink the build (returns
    '' / writes no feels)."""
    from construct import cohorts
    ids = sorted(e for e in _canon_entity_ids(world)
                 if e.startswith(("person:", "place:", "obj:")))[:FLAVOR_ENTITY_CAP]
    try:
        flavor = cohorts.author_flavor(provider, digest, ids)
    except Exception as exc:  # never sink the build on a flavor miss
        logger.warning("flavor cohort skipped: %s", exc)
        return ""
    player_frame = f"knows:{reads.state('arc:main', 'protagonist', frame='plot:main') or ''}"
    items = []
    clues = []  # (entity, feel) flagged as a clue → an escalating foreshadow pin
    for f in flavor.get("feels", []):
        entity, feel = f.get("entity"), f.get("feel")
        if entity and feel and reads.has_entity(entity):
            items.append({"entity": entity, "attribute": "feel", "value": feel})
            if f.get("clue") and entity.startswith(("person:", "place:", "obj:")):
                clues.append((entity, feel))
    if items:
        world.porcelain.ingest_structured(items)                     # canon
        if player_frame != "knows:":
            world.porcelain.ingest_structured(items, frame=player_frame)  # scene-visible
        logger.info("flavor: %d entity feels written", len(items))
    if clues:
        _author_foreshadow_pins(world, clues)
    return (flavor.get("style") or "").strip()


def _author_foreshadow_pins(world: Any, clues: list[tuple[str, str]]) -> None:
    """Mint escalating foreshadowing pins from clue-feels and append them to the
    arc's plot rows + pin_index (NARRATIVE-FLAVOR-INGEST v2). A person-clue →
    social pin (fires when present), a place-clue → region pin (fires in scope);
    `escalates=True` so the clue grows louder as the player closes in. Fail-open:
    a pin-authoring miss never sinks the build."""
    from construct.arc.grammar import Pin
    from construct.arc.io import pin_to_items
    p = world.porcelain
    try:
        # pin_index is stored as a JSON-list literal, but read it defensively:
        # state() may hand back the raw string, an already-parsed list, or nothing.
        raw = p.state("arc:main", "pin_index", frame="plot:main")
        if isinstance(raw, str):
            existing = json.loads(raw or "[]")
        elif isinstance(raw, list):
            existing = raw
        else:
            existing = []  # absent or unexpected shape → start clean (fail-open)
        new_ids, items = [], []
        for i, (entity, feel) in enumerate(clues):
            pin_id = f"pin:clue_{_slug(entity)}_{i}"
            # place-clue → region (fires when you're within it); person/object-clue
            # → social presence (fires when the suspect/object is in the scene).
            scope = "region" if entity.startswith("place:") else "social"
            pin = Pin(pin_id=pin_id, scope_kind=scope, subject_entity=entity,
                      directive=feel, anchor=entity, severity=0.6, escalates=True)
            items += pin_to_items(pin, "arc:main")
            new_ids.append(pin_id)
        p.ingest_structured(items, frame="plot:main")
        p.ingest_structured([{"entity": "arc:main", "attribute": "pin_index",
                              "value": json.dumps(existing + new_ids),
                              "value_type": "literal", "timeless": True}],
                            frame="plot:main")
        logger.info("flavor: %d foreshadow pins authored", len(new_ids))
    except Exception as exc:
        logger.warning("foreshadow-pin authoring skipped: %s", exc)


#: Fallback shown when the authored goal leaks a hidden term (fail-closed):
#: win_loss always gets an aim line, never a spoiling one.
_DEFAULT_GOAL = "See your story through to its end."


def _hidden_terms(world: Any, proposal: dict) -> set[str]:
    """The tokens a player-facing goal must NOT contain — the ANSWERS the arc
    keeps hidden, NOT the premise. A genre-true aim names the world's stakes
    ("lift the blight", "toss the ring into the fire", "see the lost child
    home") — those reference PREMISE entities (the problem, the setting), which
    the player already knows from the intro and which the goal SHOULD evoke. The
    spoiler is the SOLUTION: what the player must DISCOVER. So the forbidden set
    is only the `player_learns` beat VALUES (the culprit, the cure, the secret)
    plus a `player_learns` failure value — never the whole world vocabulary
    (that over-broad set is what forced every goal back to boilerplate).
    Short tokens (<3 chars) are dropped as noise. Fail-closed on the answers."""
    terms: set[str] = set()

    def _add_entity(raw: str) -> None:
        # ONLY a discovered ENTITY identity is a spoiler (the 'Dr. Archibald'
        # the player must name). A value that is an entity-id reference
        # (person:/obj:/fact:…) contributes its local-part tokens; a plain
        # literal value or a premise noun does NOT — naming the dragon, the
        # blight, the winter is the AIM the player asked for, never a leak.
        raw = str(raw)
        if ":" not in raw:
            return
        for tok in re.split(r"[^a-z0-9]+", raw.split(":", 1)[-1].lower()):
            if len(tok) >= 3:
                terms.add(tok)

    for b in proposal.get("beats", []):
        if b.get("kind") == "player_learns":
            _add_entity(b.get("value", ""))
    fw = proposal.get("failure_when") or {}
    if fw.get("kind") == "player_learns":
        _add_entity(fw.get("value", ""))
    return terms


def _goal_statement_safe(goal: str, forbidden: set[str]) -> bool:
    """True iff `goal` is non-empty and shares no whole word with the
    forbidden set — a structural token check, not a lint we hope holds."""
    if not goal or not goal.strip():
        return False
    words = {w for w in re.split(r"[^a-z0-9]+", goal.lower()) if w}
    return words.isdisjoint(forbidden)


def _player_goal(proposal: dict, world: Any, win_direction: str = "") -> str:
    """The player-facing aim for win_loss mode. Precedence: the authored
    `goal_statement` if it passes the leak-check; else the PLAYER'S OWN chosen
    win framing (`win_direction`) if given — they authored it, so it is their
    fiction to state, only blocked if it literally spells out the hidden ANSWER;
    else the generic default. Fail-closed on the SOLUTION (never spoil the
    discovered answer), but never let the leak-guard refuse the player the very
    fiction they asked for (founder, WIN-LOSS §10)."""
    forbidden = _hidden_terms(world, proposal)
    goal = (proposal.get("goal_statement") or "").strip()
    if goal and _goal_statement_safe(goal, forbidden):
        return goal
    chosen = (win_direction or "").strip()
    if chosen and _goal_statement_safe(chosen, forbidden):
        return chosen  # the player's own aim — honour it
    if goal or chosen:
        leaked = {w for w in re.split(r"[^a-z0-9]+", f"{goal} {chosen}".lower())
                  if w in forbidden}
        logger.warning("goal/win framing names a hidden identity %s; using the "
                       "default", sorted(leaked))
    return _DEFAULT_GOAL


#: Cap on characters seeded with a knowledge frame — the protagonist
#: plus the most-present NPCs. Each is one good-tier call, so bound it.
SEED_CAST_CAP = int(os.getenv("CONSTRUCT_SEED_CAST_CAP", "5"))

#: Concurrency for per-character knowledge seeding (Kernos letter 044). The
#: seed calls are independent, so >1 fans the slow good-tier model calls out
#: over a bounded thread pool (~15-min from-scratch interview build → ~the
#: slowest single seed). Bounded to respect provider rate limits. Default
#: 1 = sequential, the prior behavior unchanged. A safe, reversible opt-in.
SEED_CONCURRENCY = max(1, int(os.getenv("CONSTRUCT_SEED_CONCURRENCY", "3")))


def _seed_cast(protagonist: str, people: list[str]) -> list[str]:
    """The protagonist first (the player inherits this frame), then the
    other key characters, capped."""
    others = [p for p in people if p != protagonist]
    return [protagonist, *others][:SEED_CAST_CAP]


def seed_character_frames(world: Any, provider: Provider,
                          characters: list[str], digest: str,
                          protagonist: str = "",
                          protected: set | None = None) -> list[str]:
    """Author each character's private `knows:<id>` frame from canon
    (frame-scoped secrecy, P4). Returns the ids actually seeded. Writes
    ONLY to knows: frames — never canon or plot: — so it is fully
    reversible (see reseed_character_frames). Fail-open per character: a
    failed authoring call skips that character, never the scenario.

    CONCEALMENT (bug-fix 2026-06-22): the PROTAGONIST must NOT be seeded
    with the arc's hidden answer — the player DISCOVERS the protected
    (entity, attribute) facts in play, never starts knowing them
    (STORY-SHAPE-AND-RESOLUTION; the live harness caught the player being
    seeded that Cray signed the decommission order, i.e. the whole
    mystery). When `protagonist`/`protected` are given, those keys are
    stripped from the protagonist's seed (other characters are unaffected —
    an NPC may legitimately know the secret).

    The per-character seed calls are independent (each authors one frame
    from the already-fixed `digest`; no call reads another's output), so
    with `CONSTRUCT_SEED_CONCURRENCY` > 1 the slow good-tier model calls
    fan out over a bounded thread pool (Kernos letter 044). Appends stay
    sequential and in cast order — PB's buffer is single-writer, so we
    never issue concurrent writes; only the model calls run concurrently.
    Default 1 = the prior sequential behavior, byte-for-byte."""
    from construct import cohorts

    def _author(char: str) -> tuple[str, list[dict] | None]:
        """One character's seed call. Returns (char, items), or (char, None)
        on a provider failure — the fail-open-per-frame contract."""
        try:
            out = cohorts.seed_knows(provider, char, digest)
        except ProviderError as exc:
            logger.warning("knowledge seeding failed for %s: %s", char, exc)
            return char, None
        items = [{"entity": f["entity"], "attribute": f["attribute"], "value": f["value"]}
                 for f in out.get("facts", []) if f.get("entity") and f.get("attribute")]
        return char, items

    if SEED_CONCURRENCY > 1 and len(characters) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=SEED_CONCURRENCY) as pool:
            results = list(pool.map(_author, characters))   # order-preserving
    else:
        results = [_author(char) for char in characters]

    protected = protected or set()
    seeded: list[str] = []
    for char, items in results:
        if items and char == protagonist and protected:
            # Strip the arc's hidden answer from the PLAYER's starting knowledge —
            # they earn it through play, never begin knowing it.
            kept = [it for it in items
                    if (it["entity"], it["attribute"]) not in protected]
            if len(kept) != len(items):
                logger.info("protagonist seed: stripped %d protected (hidden-answer) "
                            "fact(s) from knows:%s", len(items) - len(kept), char)
            items = kept
        if items:
            world.porcelain.ingest_structured(items, frame=f"knows:{char}")
            seeded.append(char)
            logger.info("seeded knows:%s with %d facts", char, len(items))
    return seeded


def seed_player_relationships(world: Any, provider: Provider, protagonist: str,
                              cast_nodes: tuple, digest: str,
                              protected: set | None = None) -> int:
    """Author the player's STANDING relationship to each PERSON cast member into the
    `knows:<protagonist>` frame (OPENING-GROUNDING, founder 2026-06-30) — so the grounded cold
    open introduces a present character as who-they-are-TO-the-player, not a third-party intro.
    Writes `relationship_to_<id>` rows; the render path (`Session._player_grounding`) consumes
    them. Returns the count written. Fail-open: any miss leaves the build untouched (the open
    still grounds from the protagonist's other lived-context facts). Reversible — knows: only.

    NON-SPOILER: the cohort is instructed to author only the player's KNOWN standing, never the
    solution; as a host-side backstop any value brushing the arc's protected vocabulary is
    dropped at RENDER (`_value_leaks`). We also skip a `relationship_to_<id>` whose (entity,
    attribute) lands in `protected` (defensive — relationship keys are not normally protected)."""
    from construct import cohorts
    roster = [{"id": n.node_id,
               "surface_role": getattr(n, "surface_role", ""),
               "shape_role": getattr(n, "shape_role", "")}
              for n in cast_nodes
              if n.node_id.startswith("person:") and n.node_id != protagonist]
    reads = PorcelainWorldReads(world)
    # THE GEOGRAPHY OF SELF, INTIMATE (founder 2026-07-03, Brackenmere): "if I live in this
    # place… I should have a MORE intimate explanation of my relationship with the starting
    # location, not less." The opening place CHAIN joins the roster so the cohort authors the
    # causes, motivation, and history that brought the player under this roof — consumed by
    # the cold open's WHERE-YOU-ARE grounding.
    try:
        for _pid in (world.porcelain.locate(protagonist) or []):
            _pid = str(_pid)
            if not _pid.startswith("place:"):
                continue
            _pnm = reads.state(_pid, "name") or _pid.split(":", 1)[-1].replace("_", " ")
            roster.append({"id": _pid,
                           "surface_role": f"the opening location ({_pnm}) — the player's "
                                           f"own starting ground"})
    except Exception:  # noqa: BLE001 — the chain is enrichment, never a build gate
        pass
    if not roster:
        return 0
    prot_role = reads.state(protagonist, "role") or ""
    try:
        out = cohorts.author_player_relationships(provider, prot_role, roster, digest)
    except Exception as exc:  # authoring NEVER sinks a build
        logger.warning("player-relationship authoring skipped: %s", exc)
        return 0
    valid_ids = {r["id"] for r in roster}
    protected = protected or set()
    # Concealment at AUTHOR time (Cx 337): never persist a relationship value that brushes the
    # arc's hidden vocabulary into knows:<prot> — defense in depth alongside the render screen,
    # using the SAME shared token set so the two cannot drift.
    from construct.arc.executor import concealed_tokens, value_leaks
    concealed = concealed_tokens(protected)
    rows: list[dict] = []
    for rel in out.get("relationships", []):
        target, phrase = rel.get("target"), (rel.get("relationship") or "").strip()
        if not target or not phrase or target not in valid_ids:
            continue                                  # only real, in-roster cast
        attr = f"relationship_to_{target}"
        if (protagonist, attr) in protected:
            continue
        if value_leaks(phrase, concealed):            # a leaked value never reaches storage
            logger.info("player-relationship to %s dropped (brushes concealed vocabulary)", target)
            continue
        rows.append({"entity": protagonist, "attribute": attr, "value": phrase})
    if rows:
        world.porcelain.ingest_structured(rows, frame=f"knows:{protagonist}")
        logger.info("seeded %d player-relationship fact(s) into knows:%s",
                    len(rows), protagonist)
    return len(rows)


def reseed_character_frames(name: str, provider: Provider,
                            characters: list[str] | None = None) -> list[str]:
    """Re-author knowledge frames on the PRISTINE scenario without
    touching canon or the arc — the reversibility hook (founder letter
    041): if a seeded frame is wrong at play time, regenerate it in
    isolation. Retracts the prior knows: rows for each character, then
    re-seeds. Returns the ids reseeded."""
    spath = scenario_path(name)
    if not spath.exists():
        raise FileNotFoundError(f"no scenario {name!r}")
    meta_path = spath.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    targets = characters or meta.get("seeded_frames", [])
    world = _world(spath, name, model=engine_tier_dispatch(provider))
    try:
        digest = _world_digest(world)
        for char in targets:                       # clear the old frame first
            from construct.adapter import frame_facts as _ff
            for row in _ff(world, f"knows:{char}"):
                world.porcelain.retract(row.id, "reseed: re-authoring knowledge frame")
        # Honor the protagonist's concealment filter on reseed too (same bug-fix).
        from construct.adapter import PorcelainWorldReads
        from construct.arc.executor import arc_protected_keys
        protagonist, protected = "", set()
        try:
            _arc = arc_io.arc_from_frame(PorcelainWorldReads(world))
            protagonist, protected = _arc.protagonist, arc_protected_keys(_arc)
        except Exception:
            logger.warning("reseed: could not load arc for protected-key filter")
        seeded = seed_character_frames(world, provider, targets, digest,
                                       protagonist=protagonist, protected=protected)
    finally:
        world.close()
    meta["seeded_frames"] = sorted(set(meta.get("seeded_frames", [])) | set(seeded))
    meta_path.write_text(json.dumps(meta, indent=2))
    return seeded


def knows_inspect(name: str, character: str, contrast: str | None = None) -> dict:
    """Inspect a character's authored knowledge frame on the pristine
    scenario (read-only; no model). With `contrast`, return the
    divergence between two characters' frames over the same world — the
    criterion-(g) headline: provably different information states (play
    the detective vs the clerk who hid the core). All deterministic."""
    spath = scenario_path(name)
    if not spath.exists():
        raise FileNotFoundError(f"no scenario {name!r}")
    if ":" not in character:
        character = f"person:{character}"
    if contrast and ":" not in contrast:
        contrast = f"person:{contrast}"
    meta_path = spath.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    world = _world(spath, name)                          # model=None: reads are LLM-free
    try:
        # Inspect over the whole canon cast + key entities (not just the
        # arc scope) so a seeded secret on any entity shows in the diff.
        ids = _canon_entity_ids(world)
        scope = sorted(
            {e for e in ids if e.startswith(("person:", "obj:", "fact:", "place:"))}
            | set(meta.get("arc_scope", [])))

        def facts(frame: str) -> dict[tuple[str, str], object]:
            if not scope:
                return {}
            snap = world.porcelain.snapshot(scope, frame=frame)
            return {(f["entity"], f["attribute"]): f["value"]
                    for f in snap.get("facts", [])}

        cf = facts(f"knows:{character}")
        result: dict = {"character": character, "scope_size": len(scope),
                        "knows": cf, "seeded": meta.get("seeded_frames", [])}
        if contrast:
            of = facts(f"knows:{contrast}")
            result["contrast"] = contrast
            result["only_character"] = {k: v for k, v in cf.items() if k not in of}
            result["only_contrast"] = {k: v for k, v in of.items() if k not in cf}
        return result
    finally:
        world.close()


def who_knows_inspect(name: str, entity: str, attribute: str,
                      value: object = None) -> dict:
    """The INVERSE of knows_inspect (WHO-KNOWS-INVERSE-V1, PB 071): which
    characters' knowledge frames hold a fact — computed by the engine
    (`p.who_knows`), not stored. The frame-scoped-secrecy showcase: "which NPCs
    know the culprit?" Folded-not-raw (superseded/retracted beliefs drop),
    identity-aware. Read-only on the pristine scenario; no model."""
    spath = scenario_path(name)
    if not spath.exists():
        raise FileNotFoundError(f"no scenario {name!r}")
    world = _world(spath, name)                          # model=None: reads are LLM-free
    try:
        frames = world.porcelain.who_knows(entity, attribute, value)
        characters = sorted(f.split("knows:", 1)[1] for f in frames
                            if f.startswith("knows:"))
        return {"entity": entity, "attribute": attribute, "value": value,
                "frames": frames, "characters": characters}
    finally:
        world.close()


def _world_digest(world: Any, limit: int = 6000) -> str:
    """A people+key-entity snapshot digest for authoring calls."""
    ids = _canon_entity_ids(world)
    people = sorted(e for e in ids if e.startswith("person:"))
    others = sorted(e for e in ids if e.startswith(("obj:", "fact:", "place:")))[:40]
    scope = people + others
    return json.dumps(world.porcelain.snapshot(scope))[:limit] if scope else "(empty)"


def _locatable_people(world: Any, known_ids: list[str],
                      *, as_of: float | None = None) -> list[str]:
    """The `person:*` ids that are actually STAGED somewhere in canon (Cx 160 #3).
    `has_entity` is too weak — a generic extracted role like `person:detective`
    carries a `kind` row but `locate()` is empty, so it would pass a mere-existence
    check yet leave the cast unstageable. The protagonist must be one of THESE.

    `as_of` is supported for callers wanting located-as-of a coordinate, but the PRODUCTION
    protagonist-eligibility path deliberately calls this at HEAD (Cx 261): eligibility is an
    identity/staged-person guard only; OPENING STATE is decided by `_opening_scene_place` +
    horizon-bound reads, not here. (An `as_of=opening_as_of` eligibility filter is too strong for
    atmospheric saga bibles whose opening chapters place no cast — it empties the allowlist.)"""
    return [e for e in known_ids
            if e.startswith("person:") and world.porcelain.locate(e, as_of=as_of)]


def _opening_scene_place(world: Any, protagonist: str,
                         opening_as_of: float | None) -> str | None:
    """The place to anchor the opening tableau on (cast staging). Resolution order:
    1. the protagonist's location AT the opening horizon (the well-formed-bible case — the
       opening chapter placed them); else
    2. their EARLIEST source location (a saga whose hero is first placed mid-text: their
       introduction/home — NEVER the head, which is the aftermath the horizon excludes); else
    3. head (single-timeframe / legacy worlds).
    This is the Cx-255 blocking-#1 fix generalized to bibles whose opening is atmospheric."""
    p = world.porcelain
    if opening_as_of is not None:
        chain = p.locate(protagonist, as_of=opening_as_of)
        if chain:
            return chain[0]
        # earliest placed location (min valid_from `in` row) — their introduction, not the end
        from construct.adapter import frame_facts as _ffo
        earliest_vf: float | None = None
        for r in _ffo(world, "canon", entity=protagonist, attribute="in"):
            if r.valid_from is not None and (earliest_vf is None
                                             or r.valid_from < earliest_vf):
                earliest_vf = r.valid_from
        if earliest_vf is not None:
            chain = p.locate(protagonist, as_of=earliest_vf)
            if chain:
                logger.info("opening scene for %s anchored to earliest source location "
                            "(as-of %.0f): %s", protagonist, earliest_vf, chain[0])
                return chain[0]
    chain = p.locate(protagonist)  # head (legacy / last resort)
    return chain[0] if chain else None


def _fallback_protagonist(world: Any, located: list[str], play_as: str) -> str | None:
    """Deterministic last-resort binding (Cx 160 #2/#4) when the author stays
    stubborn: pick a LOCATED person — the durable map identity. `play_as` is only a
    TIE-BREAKER among located candidates (token overlap with id/name), never a
    license to fabricate a location for a bad role id. None if nothing is located."""
    if not located:
        return None
    want = {w for w in play_as.lower().replace(":", " ").split() if len(w) > 3}
    if want:
        def _score(pid: str) -> int:
            name = str(world.porcelain.state(pid, "name") or "")
            toks = set((pid + " " + name).lower().replace(":", " ").split())
            return len(want & toks)
        best = max(located, key=_score)
        if _score(best) > 0:
            return best
    return sorted(located)[0]  # stable: the first located person


class ReplanOutcome(NamedTuple):
    """The result of a mid-story re-plan attempt, tagged so the turn-loop caller can
    route the three cases distinctly (Cx 212): `replanned` (install `arc`),
    `provider_error` (fail-open — keep the current arc + the committed reshape), and
    `no_replacement` (a coherent 'nothing good to pursue' — route OLD-main-arc fallout,
    never install a broken arc nor silently leave a stale one)."""
    reason: str               # "replanned" | "provider_error" | "no_replacement"
    arc: Arc | None = None

    @property
    def ok(self) -> bool:
        return self.reason == "replanned" and self.arc is not None


def author_replan(world: Any, arc: Arc, provider: Provider, *,
                  reshape_summary: str, turn: int) -> ReplanOutcome:
    """WORLD-CHANGING-AGENCY step 4: after a reshape made the old destination stale,
    author the BEST coherent NEW main arc from the reshaped world — the prior arc is
    FUEL, not a rail (the founder's "guide it to where the best story is; there is
    always still a story"). Mid-story: NOT a new chapter (no episode boundary) and NOT
    a side thread. Reuses the arc-authoring cohort, enforces the SAME protagonist, and
    builds with a fresh `arc:replan_<turn>` id so beat/clock ids never collide with the
    old main arc. Returns a tagged `ReplanOutcome` (Cx 212) so the caller can tell a
    transient provider failure (fail-open) from a true no-replacement (route fallout)."""
    from construct import cohorts
    known_ids = sorted(e for e in _canon_entity_ids(world)
                       if e.startswith(("person:", "fact:", "obj:", "place:")))
    trigger = (
        "THE WORLD JUST CHANGED THIS TURN — a player's act reshaped an established "
        "truth, so the story's old destination may now be stale. This is NOT a new "
        "chapter and NOT a side thread: author the BEST, most engaging COHERENT MAIN "
        "arc to pursue FROM HERE given what just changed. The prior destination is "
        "fuel, not a rail — follow the change to where the best story now lives, in "
        "the player's direction. There is always still a story.")
    fuel = (f"WHAT JUST CHANGED THIS TURN: {reshape_summary}\n"
            f"THE PRIOR DESTINATION (now possibly moot — reuse what still serves): "
            f"{arc.shape.delta_type} / {getattr(arc.shape, 'premise', '')}")
    try:
        proposal = cohorts.generate_arc(
            provider, trigger=trigger, fuel=fuel, available_ids=known_ids, style="",
            present_characters=", ".join(_known_people(world)) or "(carry the cast)",
            protagonist=arc.protagonist)
    except Exception:
        logger.exception("author_replan: provider error — fail-open (keep current arc)")
        return ReplanOutcome("provider_error")
    # A coherent "nothing to pursue" (no beats proposed) is a NO_REPLACEMENT (route fallout),
    # distinct from a transient failure — and checked BEFORE _build_arc (which can't build a
    # beatless arc). This is the only path that should trip the old-main-arc fallout.
    if not (isinstance(proposal, dict) and proposal.get("beats")):
        logger.warning("author_replan: no coherent replacement proposed — route fallout")
        return ReplanOutcome("no_replacement")
    proposal["protagonist"] = arc.protagonist  # hard invariant: same player (Cx 138)
    try:
        new_arc = _build_arc(proposal, arc_id=f"arc:replan_{turn}")
    except Exception:
        # A build glitch on an otherwise-populated proposal is a transient fault, not a
        # narrative "no replacement" — fail-open rather than fabricate a story consequence.
        logger.exception("author_replan: build error — fail-open (keep current arc)")
        return ReplanOutcome("provider_error")
    if not new_arc.beats:
        return ReplanOutcome("no_replacement")
    return ReplanOutcome("replanned", new_arc)


def _build_arc(proposal: dict, arc_id: str = "arc:main") -> Arc:
    """Build an Arc from an authoring proposal. `arc_id` defaults to the main
    arc; a non-main (side) arc gets a per-arc refusal-clock id so two arcs never
    collide on `clock:refusal` in the shared `plot:main` frame (the one real
    multi-arc collision — LIVING-WORLD-GENERATOR P1)."""
    is_main = arc_id == "arc:main"
    slug = arc_id.split(":", 1)[1]
    # Non-main arcs suffix their beat ids with the arc slug so two arcs sharing
    # `plot:main` never collide on a beat status row (and the escalation/pressure
    # clock ids derived from the beat id inherit that uniqueness). The main arc
    # keeps bare `beat:<slug>` ids — byte-for-byte the pre-portfolio behavior.
    bsuffix = "" if is_main else f"_{slug}"
    protagonist = proposal["protagonist"]
    player_frame = f"knows:{protagonist}"
    beats = []
    for b in proposal["beats"]:
        raw = b["id"].split(":", 1)[-1]
        beats.append(Beat(
            beat_id=f"beat:{_slug(raw)}{bsuffix}",
            phase=Phase(b["phase"]),
            weight=Weight(b["weight"]),
            achievable_via=_beat_expr(b, player_frame),
        ))
    climax = [b.beat_id for b in beats if b.phase in (Phase.CLIMAX, Phase.CRISIS)] \
        or [beats[-1].beat_id]
    k = max(1, min(2, len(climax) - 1)) if len(climax) > 1 else 1
    shape = ConclusionShape(
        shape_id=f"shape:{slug}",
        delta_type=proposal["delta_type"],
        tension=tuple(proposal["tension"][:3]) if len(proposal["tension"]) >= 3
        else (protagonist, "drive:a", "drive:b"),
        world_condition=AtLeast(k, tuple(BeatAchieved(bid) for bid in climax)),
        premise=StateIs(protagonist, "kind", "person"),
        refusal_variant_id="shape:refused",
    )
    clocks = tuple(
        Clock(clock_id=f"clock:escalate_{b.beat_id.split(':', 1)[1]}",
              fires_when=TurnsQuiet(4 + 2 * i),
              effects=({"entity": f"event:pressure_{b.beat_id.split(':', 1)[1]}",
                        "attribute": "kind", "value": "pressure"},),
              bound_to=b.beat_id,
              rung=(Rung.SURFACE, Rung.DRAW, Rung.CONVERGE)[min(i, 2)])
        for i, b in enumerate(beats) if b.weight is Weight.REQUIRED
    )
    # The refusal clock is NO LONGER a quiet-turn timer (founder ruling 2026-06-25 / Cx 176): turns
    # never force a close, and a turn-count refusal would even write a fabricated `refusal_conclusion`
    # into canon. It is now an EXPLICIT-ABANDONMENT clock — it fires only when an
    # `event:abandoned_<arc>` occurrence is committed (the player decisively walks away / refuses, a
    # negative commitment), never on silence/contemplation. Absent that event it never fires, so a
    # no-deadline story stays open indefinitely and nothing fabricated enters the log.
    refusal_id = "clock:refusal" if is_main else f"clock:refusal_{slug}"
    concludes = "event:world_concludes" if is_main else f"event:world_concludes_{slug}"
    abandon = "event:abandoned" if is_main else f"event:abandoned_{slug}"
    refusal = Clock(clock_id=refusal_id, fires_when=Occurred(abandon),
                    effects=({"entity": concludes, "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to=arc_id, rung=Rung.REFUSAL)
    failure_when = _failure_expr(proposal.get("failure_when"), player_frame)
    return Arc(
        arc_id=arc_id, protagonist=protagonist, shape=shape,
        beats=tuple(beats), clocks=clocks, refusal_clock=refusal,
        climax_ready_k=k, climax_ready_beats=tuple(climax),
        phase_budget={Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3,
                      Phase.CLIMAX: 2, Phase.FALLING: 2},
        failure_when=failure_when,
    )


def start_playthrough(name: str, fresh: bool, player_id: str | None = None) -> Path:
    spath, slot = scenario_path(name), slot_path(name, player_id)
    if not spath.exists():
        raise FileNotFoundError(f"no scenario {name!r} (looked at {spath})")
    if fresh or not slot.exists():
        shutil.copyfile(spath, slot)  # the one copy operation (letter 013)
        logger.info("playthrough slot (re)created from pristine scenario")
    return slot


def episode_checkpoint_path(name: str, player_id: str | None = None) -> Path:
    """The per-player EPISODE-START checkpoint: a copy of the slot taken the
    moment a new episode opens over the EXISTING world (no re-ingest — the world
    is already in its end-of-last-episode state). It lets `/restart` roll the
    CURRENT episode back to its opening without discarding earlier episodes' canon.
    Absent for a first/only episode — the pristine `.world` IS that checkpoint
    (a slot is just a recopy of it). See docs/design/EPISODIC-CONTINUATION.md."""
    if player_id:
        return WORLDS_DIR / f"{name}.{_safe_player_id(player_id)}.ep.checkpoint.world"
    return WORLDS_DIR / f"{name}.ep.checkpoint.world"


def checkpoint_episode_start(name: str, player_id: str | None = None) -> Path | None:
    """Snapshot the current slot as the episode-start checkpoint (one file copy),
    so `/restart` can restore THIS episode. For episode one there is no prior
    slot to checkpoint and the pristine scenario serves; returns None then."""
    slot = slot_path(name, player_id)
    if not slot.exists():
        return None
    cp = episode_checkpoint_path(name, player_id)
    shutil.copyfile(slot, cp)
    logger.info("episode-start checkpoint written for %s", name)
    return cp


def restore_episode_start(name: str, player_id: str | None = None) -> bool:
    """Roll the slot back to the CURRENT episode's opening. Returns True when a
    checkpoint existed (episode >=2, mid-progression rollback); False otherwise
    (caller falls back to a pristine fresh start = the first episode's opening)."""
    cp = episode_checkpoint_path(name, player_id)
    if not cp.exists():
        return False
    shutil.copyfile(cp, slot_path(name, player_id))
    logger.info("restored %s to episode-start checkpoint", name)
    return True


def restore_original(name: str, player_id: str | None = None) -> None:
    """Wipe back to the factory-fresh ORIGINAL scenario: drop the play slot AND
    any episode checkpoint, so the next fresh entry recopies the pristine `.world`
    (episode one, untouched). Discards ALL episode progression and live canon."""
    slot_path(name, player_id).unlink(missing_ok=True)
    episode_checkpoint_path(name, player_id).unlink(missing_ok=True)


def open_playthrough(name: str, provider: Provider,
                     player_id: str | None = None) -> tuple[Any, Arc, dict]:
    slot = slot_path(name, player_id)
    if not slot.exists():
        raise FileNotFoundError(
            f"no playthrough slot for {name!r} — run `construct play {name} --fresh`")
    # A slot is a COPY of the pristine scenario buffer, so it carries the
    # scenario's world_id (`w:<name>`). Per-player isolation is the
    # separate FILE (a fork), not a distinct world_id — same as the
    # original single-slot model. Passing a different id would trip the
    # engine's stored-world_id check.
    world = _world(slot, name, model=engine_tier_dispatch(provider))
    meta_path = scenario_path(name).with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    # Reconstruct the PORTFOLIO from the plot: frame (~21ms/arc post-037). The
    # main (terminal-bearing) arc is returned as `arc` (backward-compatible 3-
    # tuple); side arcs ride on a runtime meta key the Session reads. A legacy
    # single-arc `arc_cache` (pre-portfolio) is wrapped as a one-arc portfolio;
    # a world with no portfolio manifest fails open to a single `arc:main`.
    reads = PorcelainWorldReads(world)
    if "arc_cache" in meta:
        arcs = [arc_io.arc_from_cache(meta["arc_cache"])]
    else:
        arcs = arc_io.portfolio_from_frame(reads)
    if not arcs:
        raise RuntimeError(f"scenario {name!r}: no arcs could be reconstructed")
    main_arc_id = arc_io.main_arc_from_frame(reads)
    arc = next((a for a in arcs if a.arc_id == main_arc_id), arcs[0])
    meta["_side_arcs"] = [a for a in arcs if a.arc_id != arc.arc_id]
    meta["main_arc"] = arc.arc_id
    return world, arc, meta


def _episode_fuel(reads: Any, prior_arc: Arc, prior_title: str = "",
                  prior_outcome: str | None = None, history: str = "") -> str:
    """The seed for the NEXT episode's arc — the unresolved thread the just-ended story leaves
    behind (CONCLUDE→CONTINUE). Prefers a STANDING canon consequence chained to the prior arc's
    terminal (the 'book-2 hook' — e.g. the real culprit walks free), falling back to the prior
    arc's thematic tension. Host-side fuel string; never a stored row.

    TWO continuation modes (founder), both seeded here:
      1. DANGLING THREAD (rule of cool): an unresolved hook from the last story → the next case
         continues it (the freed culprit becomes the new quarry).
      2. CLEAN SOLVE → NEW CASE (the Sherlock pattern): no live thread; a FRESH case arrives, and
         the prior victory becomes REPUTATION — "the detective who solved <prior_title>". Time has
         passed; their name precedes them.
    The prior title + outcome are ALWAYS woven in (the reputation callback) so even a clean solve
    continues with continuity, not a cold reset."""
    from construct.arc.executor import SESSION
    threads: list[str] = []
    # 1. a STANDING consequence chained to the last terminal (the book-2 hook), if any
    try:
        terms = reads.events(kind="arc_won", frame=SESSION) + reads.events(kind="arc_lost", frame=SESSION)
        latest = max((e for e in terms if e.at is not None), key=lambda e: e.at, default=None)
        if latest is not None:
            for e in (x for x in reads.events() if latest.event_id in (x.caused_by or ())):
                threads.append(f"an unresolved consequence of the last case: {e.kind.replace('_', ' ')}")
    except Exception:  # fuel is best-effort — never sink the continuation
        logger.exception("episode fuel: consequence read failed")
    try:
        ent, strong, weak = prior_arc.shape.tension
        threads.append(f"a lingering tension between {strong.split(':')[-1]} and "
                       f"{weak.split(':')[-1]}")
    except Exception:
        pass
    # the REPUTATION callback — always present, the continuity even on a clean solve
    rep = (f"The protagonist is now KNOWN for the last case (\"{prior_title}\", which they "
           f"{'closed' if prior_outcome == 'won' else 'saw through to its hard end'}); time has "
           f"passed and their reputation precedes them.") if prior_title else \
          "Time has passed since the last case; the protagonist's reputation precedes them."
    if threads:
        tail = (rep + " A thread is still live to pull on: " + "; ".join(threads)
                + ". The next case grows from it.")
    else:
        tail = rep + " A NEW case now finds them — fresh, but met by someone whose name is made."
    # THE ENTIRE PREVIOUS ADVENTURE is the lead-in (founder): author the next fiction AGAINST the
    # full lived history (the narrative-memory ledger), not just a distilled thread — so callbacks
    # are chosen from everything that actually happened, and the world genuinely continues.
    if history.strip():
        return ("THE STORY SO FAR — the entire previous adventure, your lead-in (continue FROM "
                "this; mine it for the richest callbacks):\n" + history.strip() + "\n\n" + tail)
    return tail


def _tension_axis(arc) -> str:
    """A short 'X against Y' read of an arc's drive axis, or '' if unavailable."""
    try:
        _e, strong, weak = arc.shape.tension
        return (f"{strong.split(':')[-1].replace('_', ' ')} against "
                f"{weak.split(':')[-1].replace('_', ' ')}")
    except Exception:
        return ""


def _continuation_intro(prior_title: str, prior_outcome: str, prior_arc, proposal: dict,
                        new_arc, prior_shape: dict | None = None,
                        door_place: str | None = None,
                        callback: str | None = None) -> str:
    """The next episode's COLD-OPEN directive (founder, 2026-06-26): bridge WHERE THE LAST
    STORY LANDED to WHERE THIS ONE IS HEADED, leaving the narrator free to find the most
    interesting connection between those two SPECIFIC points. Deliberately NOT a formula —
    no obligatory 'time has passed' + 'you made a name on that one' (that opener was
    4-for-4 identical across episodes). The bridge is creatively interpretive so we don't
    swap one template for another."""
    # THE SHAPE, not the binary (founder ruling / #88 S4a): the bridge is authored from the
    # graded outcome — a wrong close travels as a stain, a costly one as a toll, a triumph as a
    # name — never from won/lost.
    _shape = prior_shape or {}
    _grade, _oshape, _basis = (_shape.get("grade", ""), _shape.get("outcome_shape", ""),
                               _shape.get("basis", ""))
    if _grade == "wrong" or _oshape in ("failure", "quiet_failure"):
        solved = "closed it on the WRONG answer — that stain and its fallout travel with them"
    elif _oshape == "costly_victory" or _grade == "pyrrhic":
        solved = "carried it home, but at a toll that shows"
    elif _oshape in ("bittersweet", "partial") or _grade == "partial":
        solved = "resolved it in the main, though something in it still doesn't sit square"
    else:
        solved = "solved" if prior_outcome == "won" else "saw it through to its hard end"
    landed = f"they {solved}" + (f' "{prior_title}"' if prior_title else " the last case")
    if _basis:
        landed += f" ({_basis})"
    prior_axis = _tension_axis(prior_arc)
    if prior_axis:
        landed += f" — its drama turned on {prior_axis}"
    headed = ((proposal or {}).get("hook") or "").strip() or "a new situation is beginning to surface"
    new_axis = _tension_axis(new_arc)
    return (
        "THIS IS A NEW CHAPTER for the same protagonist — BRIDGE it, do not reset.\n"
        f"WHERE THE LAST STORY LANDED: {landed}. That is the ground — situational and "
        "emotional — they carry out of it.\n"
        f"WHERE THIS ONE IS HEADED: {headed}"
        + (f" (its drive: {new_axis})." if new_axis else ".") + "\n"
        "Open with a SHORT, narratively interesting bridge between those two specific points — "
        "find the most compelling connection and play it (a consequence come home, an echo or a "
        "reversal of the last case, a changed self meeting an unchanged world, an old face or an "
        "old debt, or simply the next thing that pulls them in). You have FULL creative latitude "
        "on HOW they connect: time may pass or not; a reputation may matter, cut against them, or "
        "never come up. Do NOT default to a formula — no obligatory 'time has passed' or 'you made "
        "a name on that one'. Let these two stories decide the bridge, then let the new case surface."
        + (f"\nTHE DOORWAY (engine truth — the map already places them): the new chapter opens at "
           f"{door_place.split(':', 1)[-1].replace('_', ' ')}, after time has passed. Open THERE — "
           f"do not restage the last scene, and give the character nothing they do not already carry. "
           f"PRESENCE TRUTH holds at the opening too: stage ONLY people the world places there — an "
           f"undeclared clerk or passer-by narrated as present will be honestly DENIED a turn later "
           f"and read as a ghost. A hook may arrive by note, sound, or word carried — never by an "
           f"invented person standing in the room."
           if door_place else "")
        + (f"\nA CONSEQUENCE CALLBACK (#96 — the world shows the player their effect; surface "
           f"this ONE diegetically as part of the bridge — a front page on the rack, a changed "
           f"greeting, a name traveling — never a system note): {callback}"
           if callback else ""))


def _episode_doorway(world: Any, protagonist: str | None, epoch: float,
                     turn: int) -> str | None:
    """THE EPISODE DOORWAY (#88 S4, Cx 375 blocking requirement / 380 fix): the bridge to the
    next chapter is ENGINE TRUTH — never prompt-only prose. (i) TIME: jump to the next calendar
    phase (the classic "by morning…" seam); (ii) PLACE: the protagonist returns to the prior
    episode's OPENING place (their base), never left standing at the terminal scene unless that
    WAS the base; (iii) ITEMS: adds NOTHING (possessions carry as-is). Each leg fail-open +
    loud. Returns the doorway place (or None)."""
    from construct.arc.executor import turn_time
    door_place = None
    try:
        from construct.clock import commit_elapsed, read_clock
        clk = read_clock(world)
        cal = clk.calendar
        phases = [n for _f, n in cal.phases]
        cur = clk.phase
        nxt = phases[(phases.index(cur) + 1) % len(phases)] if cur in phases else None
        jump = 0
        if nxt:
            jump = cal.next_phase_start(clk.minutes, nxt) - clk.minutes
        if jump <= 0:
            jump = int(cal.hours_per_day * 60 // 3)  # a solid rest regardless
        commit_elapsed(world, jump)
        logger.info("episode doorway: time +%s min (into %s)", jump, nxt or "the next stretch")
    except Exception as exc:  # noqa: BLE001
        logger.warning("episode doorway time-jump skipped: %s", exc)
    try:
        if protagonist:
            open_chain = world.porcelain.locate(protagonist, as_of=epoch + 0.5)
            door_place = open_chain[0] if open_chain else None
            now_chain = world.porcelain.locate(protagonist)
            if door_place and (now_chain[0] if now_chain else None) != door_place:
                world.porcelain.ingest_structured([{
                    "entity": protagonist, "attribute": "in", "value": door_place,
                    "value_type": "entity", "valid_from": turn_time(turn)}])
                logger.info("episode doorway: %s returns to %s", protagonist, door_place)
    except Exception as exc:  # noqa: BLE001
        logger.warning("episode doorway relocation skipped: %s", exc)
    return door_place


def continue_episode(name: str, provider: Provider, player_id: str | None = None,
                     on_stage=None) -> dict:
    """CONCLUDE→CONTINUE (the Series hook): from a CONCLUDED slot, author the NEXT episode's
    hidden arc — seeded from the just-ended story's unresolved thread (the book-2 hook) — install
    it as the new MAIN arc, mark the episode boundary (so the prior win/loss receipt no longer
    freezes play), and checkpoint the boundary. The world (canon, your character, the ledger) all
    carry over; only a fresh hidden arc is woven over it. Emits the same narrative build-progress
    stages a fresh build does (NARRATIVE phrasing — no internal jargon). Returns the updated meta."""
    from construct import cohorts
    from construct.arc import io as arc_io
    from construct.arc.executor import (
        PLOT, SESSION, compute_entry_epoch, set_entry_epoch, turn_time,
    )
    slot = slot_path(name, player_id)
    if not slot.exists():
        raise FileNotFoundError(f"no playthrough slot for {name!r} to continue")
    _emit(on_stage, "Reflecting on how your story ended")
    world = _world(slot, name, model=engine_tier_dispatch(provider))
    reads = PorcelainWorldReads(world)
    meta_path = scenario_path(name).with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    # The episode's write origin (Cx 253 §4): for a HORIZON world the origin STAYS at
    # `opening_as_of` — the new chapter's arc rows + turns advance the play horizon within the
    # reserved band (turn_time(turn) = opening_as_of + turn supersedes prior); raising it above
    # the source aftermath (compute_entry_epoch) would reintroduce the old above-everything
    # behavior and re-expose future source rows. Legacy worlds keep the Cx-127 raise.
    _opening = meta.get("opening_as_of")
    epoch = float(_opening) if _opening is not None else compute_entry_epoch(world)
    # SCOPED write context (Cx 383): the raised continuation epoch must never outlive this
    # call — Session.open restores the per-slot epoch for actual play; leaking it poisons
    # turn_time() for whoever runs next in the process (test order proved it).
    _epoch_tok = set_entry_epoch(epoch)
    try:
        turn = next_turn_number(world)
        prior_main_id = arc_io.main_arc_from_frame(reads)
        prior_arcs = arc_io.portfolio_from_frame(reads)
        prior_main = next((a for a in prior_arcs if a.arc_id == prior_main_id),
                          prior_arcs[0] if prior_arcs else None)

        _emit(on_stage, "Dreaming up the next chapter")
        from construct.turnloop import terminal_outcome
        prior_title = meta.get("title", "")
        prior_outcome = terminal_outcome(reads)   # 'won'/'lost' of the just-ended episode
        # #95 PERMANENCE (Cx 422): the story ended at the protagonist's death — there is
        # no next chapter, for anyone. Refused BEFORE any generator or prompt work.
        if prior_outcome == "died":
            world.close()
            raise RuntimeError(
                "this story ended at the protagonist's death — the world's story "
                "rests; there is no next chapter")
        # The ENTIRE previous adventure (the narrative-memory ledger — compacted, regenerable from the
        # lossless arch:turn_* archive) is the lead-in for authoring the next fiction (founder).
        history = (reads.state("session:narrative_memory", "text", frame=SESSION) or "")[:4500]
        fuel = _episode_fuel(reads, prior_main, prior_title, prior_outcome, history) if prior_main else \
            "The previous chapter has closed; a new thread stirs in its wake."
        known_ids = sorted(e for e in _canon_entity_ids(world)
                           if e.startswith(("person:", "fact:", "obj:", "place:")))
        # The continuation prompt poses the founder's two questions so the next case is callback-aware,
        # not a cold reset: (1) what does the WORLD look like now? (2) which CALLBACKS make the most
        # interesting fiction? Grow the next case from the richest one.
        # ---- #96 S3: SETTLED HISTORY (Cx 414 constraint 3) --------------------------------
        # The closed chapter's ANSWERED questions become durable CLOSED HISTORY — callback
        # material, never a mystery to reopen. Recorded as a session literal (the notebook
        # and future opens read it) and fed to the generator with the explicit prohibition.
        _settled_lines: list[str] = []
        try:
            if prior_main is not None:
                for _atom in (getattr(prior_main.shape, "premise", None),
                              getattr(prior_main.shape, "world_condition", None)):
                    _se, _sa = getattr(_atom, "entity", None), getattr(_atom, "attribute", None)
                    if _se and _sa:
                        _settled_lines.append(
                            f"{_se} · {_sa} · {getattr(_atom, 'value', '')} — ANSWERED")
            from construct.adapter import frame_facts as _ffs
            for _row in _ffs(world, SESSION):
                if (str(_row.entity).startswith("card:")
                        and str(_row.attribute) == "weave_state"):
                    _settled_lines.append(f"{_row.entity}: {_row.value} — closed")
            _settled_lines = _settled_lines[:12]
            world.porcelain.ingest_structured(
                [{"entity": f"settled:episode_{turn}", "attribute": "record",
                  "value": json.dumps({"title": prior_title,
                                       "outcome": prior_outcome or "",
                                       "settled": _settled_lines})[:4000],
                  "value_type": "literal", "valid_from": turn_time(turn)}],
                frame=SESSION)
        except Exception:  # noqa: BLE001 — settled history is enrichment, never a gate
            _settled_lines = []
        # ---- #96 S4: PERSONAL THREADS (Cx 414 constraint 4) -------------------------------
        # Promises made, bonds formed, debts incurred — first-class continuation fuel, not
        # lossy prose memory. One cheap structured extraction over the ledger; stored as a
        # session literal; named to the generator as threads to HONOR or consciously pay off.
        _personal: list[dict] = []
        try:
            if history.strip():
                _pt = cohorts.extract_personal_threads(provider, history)
                _personal = [t for t in (_pt.get("threads") or [])
                             if isinstance(t, dict) and (t.get("thread") or "").strip()][:6]
                if _personal:
                    world.porcelain.ingest_structured(
                        [{"entity": "session:personal_threads", "attribute": "record",
                          "value": json.dumps(_personal)[:3000], "value_type": "literal",
                          "valid_from": turn_time(turn)}], frame=SESSION)
        except Exception:  # noqa: BLE001 — threads are enrichment, never a gate
            _personal = []
        trigger = (
            "the previous chapter has closed and the SAME protagonist continues. Before you author, "
            "weigh two things. (1) WHAT DOES THE WORLD LOOK LIKE AS WE CONTINUE — what the last case "
            "changed, who is still around, what the protagonist is now KNOWN for, what wounds or debts "
            "or doors it opened. (2) WHICH CALLBACKS MAKE FOR THE MOST INTERESTING FICTION DIRECTION — "
            "a recurring figure returning, a consequence coming home to roost, a rival or ally back in "
            "play, an unfinished bond, the reputation that now both opens and closes doors. Grow the "
            "next case from the RICHEST callback — continuity that pays off, never a cold reset."
            + (("\nCLOSED HISTORY (the last chapter's ANSWERED questions — history now, usable "
                "as callbacks, NEVER re-opened as mysteries; the crew remembers its own "
                "resolutions):\n" + "\n".join(f"- {s}" for s in _settled_lines))
               if _settled_lines else "")
            + (("\nPERSONAL THREADS TO HONOR (the player's own commitments — carry each "
                "forward visibly or consciously pay it off; never drop one as optional "
                "flavor):\n" + "\n".join(
                    f"- {t.get('thread')} [{t.get('status', 'open')}]" for t in _personal))
               if _personal else "")
            + "\nGive the new chapter its OWN `title` — never the prior chapter's.")
        prior_protagonist = prior_main.protagonist if prior_main else None
        proposal = cohorts.generate_arc(
            provider, trigger=trigger,
            fuel=fuel, available_ids=known_ids, style=meta.get("style", ""),
            present_characters=", ".join(_known_people(world)) or "(carry the established cast)",
            protagonist=prior_protagonist or "")
        # HARD INVARIANT (Cx 138): the next chapter is the SAME protagonist's — the generator's prompt
        # is pinned, but enforce it deterministically too (generate_arc descends from the side-arc
        # author, which otherwise picks an NPC). Override the proposal's protagonist before building so
        # a stray pick can never silently switch the player character out from under them.
        if prior_protagonist:
            proposal["protagonist"] = prior_protagonist
        new_id = f"arc:ep_{turn}"
        new_arc = _build_arc(proposal, arc_id=new_id)
        if prior_protagonist and new_arc.protagonist != prior_protagonist:
            raise RuntimeError(
                f"continuation protagonist drift: {new_arc.protagonist!r} != {prior_protagonist!r}")

        _emit(on_stage, "Setting the new threads in motion")
        world.porcelain.ingest_structured(
            arc_io.arc_to_items(new_arc, frame=PLOT) + arc_io.index_items(new_arc, frame=PLOT),
            frame=PLOT)
        # The new arc becomes MAIN; the concluded arc stays in the portfolio as past (its terminal
        # receipt is now BEHIND the episode boundary, so it no longer ends the scenario).
        all_ids = [a.arc_id for a in prior_arcs] + [new_id]
        # RETRACT the sealed portfolio rows, THEN append the replacement (Cx 167). The portfolio
        # rows are classified CONSTITUTIVE, and a constitutive fold does NOT recency-supersede —
        # PB serves the EARLIEST and marks the key conflicted, so neither a timeless nor a
        # valid_from write would override it; the reopened episode would silently run the OLD
        # main arc (its stale session:reckoning_ready then trips turn-1 expiry). Append-only
        # retraction of the visible rows clears the conflict so the new manifest reads clean.
        from construct.adapter import frame_facts as _ffp
        for _row in _ffp(world, PLOT, entity="arc:portfolio"):
            if _row.entity == "arc:portfolio" and _row.attribute in ("arc_ids", "main_arc"):
                world.porcelain.retract(_row.id, "continuation: superseding the portfolio manifest")
        world.porcelain.ingest_structured(
            arc_io.portfolio_items(all_ids, main_arc_id=new_id, frame=PLOT,
                                   valid_from=turn_time(turn)), frame=PLOT)
        # The EPISODE BOUNDARY: terminal_outcome reads win/loss receipts only SINCE this marker, so
        # the prior episode's ending no longer freezes the new one (PB is append-only).
        world.porcelain.ingest_structured(
            [{"entity": f"event:episode_start_{turn}", "attribute": "kind",
              "value": "episode_start", "valid_from": turn_time(turn)}], frame=SESSION)
        # THE DOORWAY'S OPENING EPOCH (Cx 382 blocker): `epoch` above is the WRITE origin — for a
        # played NON-horizon slot compute_entry_epoch RAISES it above prior plays (correct for
        # writes, wrong for looking up where the episode OPENED: locate at raised+0.5 sees the
        # terminal scene). Prefer the slot's durable episode epoch, then scenario meta, then the
        # write origin as a last resort. Captured HERE — BEFORE the _epi_rows persist below
        # overwrites the slot row with the new episode's raised epoch (reading after would read
        # back our own write and re-poison the lookup).
        _open_epoch = None
        try:
            _sv = reads.state("session:episode", "entry_epoch", frame=SESSION)
            _open_epoch = float(_sv) if _sv is not None else None
        except Exception:  # noqa: BLE001
            _open_epoch = None
        if _open_epoch is None:
            _me = meta.get("entry_epoch")
            _open_epoch = float(_me) if _me is not None else epoch
        # THE EPISODE DOORWAY (#88 S4, Cx 375 blocking requirement): the bridge to the next chapter
        # is ENGINE TRUTH written before the checkpoint — never prompt-only prose. (i) TIME: jump to
        # the next calendar phase (the classic "by morning…" seam) so the new chapter never opens in
        # the same minute; (ii) PLACE: the protagonist returns to the prior episode's OPENING place
        # (their base — bureau/gatehouse/home), never left standing at the terminal scene unless that
        # WAS the base; (iii) ITEMS: the doorway adds NOTHING (possessions carry as-is; intro prose
        # may not mint). Fail-open per leg — a miss leaves that dimension unchanged, loudly.
        _door_place = _episode_doorway(world, prior_protagonist, _open_epoch, turn)
        # HOOK-CAST STAGING (#90, Cx 387): a person the new chapter's hook puts ON STAGE must
        # exist as canon presence BEFORE the opening renders — prose-only staging made the live
        # ch2 hook witness vanish a turn later ("no one is in the room"). Ordinary kind/name/
        # role/in rows at the doorway place; at most two; fail-open per entry.
        _hook_ids: list[str] = []
        try:
            _stage_place = _door_place
            if _stage_place is None and prior_protagonist:
                _ploc = world.porcelain.locate(prior_protagonist)
                _stage_place = _ploc[0] if _ploc else None
            _hc_rows: list[dict] = []
            for _hc in (proposal.get("hook_cast") or [])[:2]:
                _hid = str((_hc or {}).get("id") or "").strip()
                if not _hid.startswith("person:") or not _stage_place:
                    continue
                if not PorcelainWorldReads(world).has_entity(_hid):
                    _hc_rows.append({"entity": _hid, "attribute": "kind", "value": "person",
                                     "timeless": True})
                    if _hc.get("name"):
                        _hc_rows.append({"entity": _hid, "attribute": "name",
                                         "value": str(_hc["name"])[:60]})
                    if _hc.get("role"):
                        _hc_rows.append({"entity": _hid, "attribute": "role",
                                         "value": str(_hc["role"])[:120]})
                _hc_rows.append({"entity": _hid, "attribute": "in", "value": _stage_place,
                                 "value_type": "entity", "valid_from": turn_time(turn)})
                _hook_ids.append(_hid)
            if _hc_rows:
                world.porcelain.ingest_structured(_hc_rows)
                logger.info("staged %d hook-cast row(s) (%s) at %s",
                            len(_hc_rows), _hook_ids, _stage_place)
        except Exception:  # staging must never sink the continuation
            logger.exception("hook-cast staging failed (continuing without)")
            _hook_ids = []
        # DURABLE PER-PLAYER episode epoch (Cx 138 #2): persist the raised epoch into THIS slot's
        # session frame so the reopened Session stamps episode-N+1 turns ABOVE the boundary (scenario
        # meta is shared + stale; the slot is per-player). Session prefers this over meta["entry_epoch"].
        # Recompute the cold-open presentation scope from the NEW arc (Cx 189 #2): EP2 must NOT inherit
        # EP1's `arc_scope`. The stale scope carried the old episode's cast (and any polluted aliases)
        # into the new chapter's opening, making EP2 read as a warped replay instead of a fresh case.
        # The staged hook cast joins the scope (#90) — presence/npc candidates enumerate FROM scope,
        # so an unscoped hook witness would be invisible even with honest canon rows.
        from construct.arc.executor import arc_entities as _arc_entities
        _reads2 = PorcelainWorldReads(world)
        _ep2_scope = sorted({e for e in _arc_entities(new_arc) if _reads2.has_entity(e)}
                            | set(_hook_ids))
        # PERSIST epoch AND the new scope per-slot in the session frame (Cx 191): the live reopen via
        # Session.open reloads the SHARED, stale scenario meta — so the returned meta isn't enough.
        # Session prefers these slot rows over meta (mirrors the entry_epoch fix). Scope is a JSON-blob
        # literal so the classifier never mistypes it.
        _epi_rows = [{"entity": "session:episode", "attribute": "entry_epoch", "value": epoch}]
        if _ep2_scope:
            _epi_rows.append({"entity": "session:episode", "attribute": "arc_scope",
                              "value": json.dumps(_ep2_scope), "value_type": "literal"})
        world.porcelain.ingest_structured(_epi_rows, frame=SESSION)
        # THE SHAPE RECEIPT is the continuation's truth (founder ruling): read the latest terminal
        # event's grade/shape/basis rows (row-level — the receipt is session bookkeeping, not a fold).
        _prior_shape: dict = {}
        try:
            from construct.adapter import frame_facts as _ffr
            _rc_rows = [r for r in _ffr(world, SESSION)
                        if str(r.entity).startswith("event:arc_outcome_")
                        and r.attribute in ("grade", "outcome_shape", "basis")]
            # group by the LATEST receipt ENTITY first (Cx 380: latest-row-per-attr could mix a
            # stale prior grade with a newer receipt that lacks one), then read that entity's attrs.
            _latest = max((str(r.entity) for r in _rc_rows),
                          key=lambda e: int(e.rsplit("_", 1)[-1]) if e.rsplit("_", 1)[-1].isdigit()
                          else -1, default=None)
            for _r in _rc_rows:
                if str(_r.entity) == _latest:
                    _prior_shape[_r.attribute] = _r.value
        except Exception:  # noqa: BLE001
            _prior_shape = {}
        # #96 S2 SURFACING (Cx 414): ONE unsurfaced consequence callback rides the bridge —
        # the founder's newspaper seam (the world showing the player their effect). The
        # presentation receipt keeps a strong callback deliberate, never accidental spam.
        _callback = None
        try:
            _cons = [e for _k in ("word_spreads", "reputation_changes", "debt_called",
                                  "door_closed", "ally_returns")
                     for e in reads.events(kind=_k)]
            from construct.adapter import frame_facts as _ffu
            _surfaced = {str(r.entity) for r in _ffu(world, SESSION,
                                                     attribute="surfaced_turn")}
            _fresh_cons = [e for e in _cons if e.event_id not in _surfaced]
            if _fresh_cons:
                _ev = max(_fresh_cons, key=lambda e: (getattr(e, "at", 0) or 0))
                # row-level read: event-entity attrs never fold via state() (the shape-
                # receipt precedent) — scan visible rows for the detail directly.
                _dtl = next((str(r.value) for r in _ffu(world, "canon",
                             entity=_ev.event_id, attribute="detail")), None)
                _callback = (_ev.kind.replace("_", " ")
                             + (f" — {_dtl}" if _dtl else ""))
                world.porcelain.ingest_structured(
                    [{"entity": _ev.event_id, "attribute": "surfaced_turn",
                      "value": turn, "valid_from": turn_time(turn)}], frame=SESSION)
        except Exception:  # noqa: BLE001 — the callback is enrichment, never a gate
            _callback = None
        world.close()

        _emit(on_stage, "Opening the next chapter")
        checkpoint_episode_start(name, player_id)  # this episode's opening = the rollback point
        meta["main_arc"] = new_id
        meta["arc_ids"] = all_ids
        meta["entry_epoch"] = epoch
        # #96 S3 (Cx 414): the new chapter gets its OWN title — from the proposal, with a
        # deterministic differ if the generator echoed the old one.
        _new_title = (proposal.get("title") or "").strip()
        if _new_title and _new_title.lower() != (prior_title or "").strip().lower():
            meta["title"] = _new_title
        elif prior_title:
            meta["title"] = f"{prior_title} — Chapter {len(all_ids)}"
        # #95 (Cx 422): death_policy is PER-CHAPTER — re-derive against the new chapter's
        # premise/hook (a shielded drawing-room story may go to war in ch3). Fail-open:
        # a derivation hiccup keeps the prior chapter's policy.
        try:
            _dp = cohorts.classify_death_policy(
                provider, meta.get("genre", ""),
                ", ".join(meta.get("game_type") or []),
                (proposal.get("hook") or proposal.get("theme") or meta.get("premise", "")))
            meta["death_policy"] = (_dp.get("policy") or
                                    meta.get("death_policy", "shielded")).strip()
            meta["death_policy_reason"] = (_dp.get("reason") or "").strip()
        except Exception:  # noqa: BLE001
            logger.exception("continuation death-policy re-derivation skipped")
        if _ep2_scope:                              # scope the new chapter to its OWN arc (Cx 189 #2)
            meta["arc_scope"] = _ep2_scope
        # The cold-open continuation note (founder, 2026-06-26): bridge WHERE THE LAST STORY LANDED to
        # WHERE THIS ONE IS HEADED, creatively — NOT the old time-pass + "you made a name" formula (it
        # was 4-for-4 identical). Consumed by the opening briefing; never a stored row.
        meta["continuation_intro"] = _continuation_intro(
            prior_title, prior_outcome, prior_main, proposal, new_arc,
            prior_shape=_prior_shape, door_place=_door_place, callback=_callback)
        return meta
    finally:
        from construct.arc import executor as _arc_executor
        _arc_executor._ENTRY_EPOCH.reset(_epoch_tok)


def next_turn_number(world: Any) -> int:
    return len(world.porcelain.events(kind="turn", frame="session:main"))
