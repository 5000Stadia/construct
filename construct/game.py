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
from typing import Any

from patternbuffer import World

from construct.adapter import PorcelainWorldReads
from construct.arc import io as arc_io
from construct.arc.conditions import (
    AtLeast,
    BeatAchieved,
    InFrame,
    Occurred,
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

ARC_SCHEMA = {
    "type": "object",
    "properties": {
        "protagonist": {"type": "string", "description": "entity id, e.g. person:joel"},
        "theme": {"type": "string", "description": "the pitchable theme, one line"},
        "goal_statement": {"type": "string",
                           "description": "ONE non-spoiling line of player-facing "
                           "aspiration for win_loss mode — the AIM, never the "
                           "mechanism/culprit/solution. E.g. 'solve the mystery and "
                           "name the culprit', 'survive the journey to safer ground'. "
                           "Must NOT contain any entity id, character name, or the "
                           "hidden answer."},
        "failure_when": {
            "type": "object",
            "description": "OPTIONAL loss terminal for win_loss mode — the ONE "
            "event that ends the story in defeat (e.g. the player is detected, "
            "captured, killed). Prefer kind 'event_occurs' with a plausible "
            "event kind (e.g. 'alarm_raised', 'player_unmasked'); omit entirely "
            "for survive-the-timeout scenarios (the refusal clock backstops).",
            "properties": {
                "kind": {"type": "string", "enum": ["player_learns", "event_occurs"]},
                "entity": {"type": "string",
                           "description": "event_occurs: the event kind; "
                                          "player_learns: the fact/entity id"},
                "attribute": {"type": "string", "description": "player_learns only"},
                "value": {"type": "string", "description": "player_learns only"},
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
    """Convert the optional authored loss terminal into an Expr, tolerantly.
    event_occurs needs only an event kind; player_learns needs the full
    triple. A malformed/partial spec yields None (loss falls back to the
    refusal clock) — never a build-time crash."""
    if not spec or not spec.get("entity"):
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


def _finalize_scenario(world: Any, name: str, title: str, provider: Provider,
                       spath: Path, endless: bool, on_stage=None) -> dict:
    """Shared session-zero tail (both creation paths): once canon is
    established, author the hidden arc over it (lint-gated), seed
    knowledge frames, and write the scenario meta. ENTRY + DESTINATION.
    Emits per-stage status (stages 2-6) via `on_stage`."""
    from construct.arc.executor import arc_entities, turn_time

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
    for attempt in range(3):
        proposal = complete_sync(provider,
            "You are authoring the hidden arc for a text-construct scenario "
            "(novel-arc mode: the mystery IS the arc). Below is the world's "
            "people+entity digest. Choose the protagonist (the natural "
            "point-of-view character), the thematic conclusion shape, and "
            "4-6 path-independent beats.\n"
            "Also emit `goal_statement`: ONE non-spoiling player-facing line of "
            "aspiration — the AIM only (e.g. 'solve the mystery and name the "
            "culprit', 'survive the journey to safer ground'). It must NEVER "
            "contain a character name, an entity id, the mechanism, or the "
            "hidden answer; it is shown to the player at the start.\n"
            "OPTIONALLY emit `failure_when`: the ONE event that ends the story "
            "in defeat (detection, capture, death). Prefer kind `event_occurs` "
            "with a plausible event kind (e.g. 'alarm_raised', 'player_unmasked'); "
            "omit it for survive-the-timeout scenarios.\n"
            "HARD RULE: a `player_learns` beat's `entity` MUST be one of the "
            "AVAILABLE IDS below verbatim (do NOT invent new fact:/obj: ids); "
            "its attribute/value should match a triple in the digest. For a "
            "thematic beat with no matching entity, use `event_occurs` with a "
            "plausible event kind instead.\n\n"
            f"AVAILABLE IDS (use these exact strings):\n{known_ids}\n\n"
            f"WORLD DIGEST:\n{digest}\n\n"
            + (f"PRIOR ATTEMPT FAILED LINT: {last_findings}; fix those — the "
               f"named entities are not in AVAILABLE IDS.\n"
               if last_findings else ""),
            ARC_SCHEMA, tier="main", deliberate=True)
        arc = _build_arc(proposal)
        findings = lint_arc(arc, reads)
        blocking = [f for f in findings if f.check != "2-paths"]
        if not blocking:
            if findings:
                logger.warning("arc lints with soft findings: %s", findings)
            break
        last_findings = [f"{f.check}: {f.message}" for f in blocking]
        logger.warning("arc lint failed (attempt %d): %s", attempt + 1, last_findings)
        arc = None
    if arc is None:
        raise RuntimeError(f"arc failed lint after 3 attempts: {last_findings}")

    world.porcelain.ingest_structured(
        arc_io.arc_to_items(arc) + arc_io.index_items(arc))
    world.porcelain.ingest_structured([
        {"entity": "event:turn_0", "attribute": "kind", "value": "turn",
         "valid_from": turn_time(0)},
    ], frame="session:main")

    # NPC-knows seeding (P4 frame-scoped secrecy); reversible (knows:
    # frames only).
    _emit(on_stage, "Stage 5 · Seeding character knowledge · frame-scoped "
                    "secrecy (knows:<id>, P4) (PB)")
    cast = _seed_cast(arc.protagonist, people)
    seeded = seed_character_frames(world, provider, cast, digest)

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
            "arc_scope": sorted(e for e in arc_entities(arc) if reads.has_entity(e)),
            "seeded_frames": seeded, "endless": bool(endless)}
    # The player-facing aim is a derivative of the hidden destination, NOT a
    # plot:/canon row (Kernos ruling): a leak-checked line on the scenario
    # seal, shown only in win_loss mode. Freeplay/endless has no fixed aim.
    if not endless:
        meta["goal_statement"] = _player_goal(proposal, world)
    spath.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def create_scenario_from_ingest(name: str, prose_path: Path,
                                provider: Provider, endless: bool = False,
                                on_stage=None) -> dict:
    """Session-zero Path A: fresh ingest of a work through OUR pipeline
    → pristine scenario. Emits per-stage status via `on_stage`."""
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
        chunks = _chunk_chapters(text)
        _emit(on_stage, f"Stage 1 · Ingesting prose → pattern-buffer · model "
                        f"extraction → assertions, provenance-tracked ({len(chunks)} chunks)")
        for i, chunk in enumerate(chunks, start=1):
            world.porcelain.ingest(chunk, source=f"doc:{prose_path.stem}", at=float(i))
            _emit(on_stage, f"   …chunk {i}/{len(chunks)} extracted")
        return _finalize_scenario(world, name, title, provider, spath, endless, on_stage)
    except BaseException:
        world.close()
        spath.unlink(missing_ok=True)
        spath.with_suffix(".meta.json").unlink(missing_ok=True)
        raise
    finally:
        world.close()


def create_scenario_from_interview(name: str, brief: str, provider: Provider,
                                   endless: bool = False, on_stage=None) -> dict:
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

    _emit(on_stage, "Stage 1 · Interviewing → pattern-buffer · expanding the brief "
                    "into a constitutive spine (stated canon)")
    spine = cohorts.interview_world(provider, brief)
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
        world.ingestor.cursor.advance(1.0)
        world.porcelain.ingest_structured(items)
        logger.info("interview authored %d spine items", len(items))
        return _finalize_scenario(world, name, title, provider, spath, endless, on_stage)
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
        scope = meta.get("arc_scope") or []
        if scope:
            snap = world.porcelain.snapshot(sorted(scope), lens="establishing_set")
            if not snap.get("facts"):
                problems.append("establishing set is empty (no coherent cold-open)")
    finally:
        world.close()
    return problems


def create_scenario_from_generated(name: str, provider: Provider, *, seed: str = "",
                                   endless: bool = False, on_stage=None) -> dict:
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
    work = cohorts.author_story(provider, seed=seed)
    prose_path = _save_generated_prose(name, work)
    _emit(on_stage, f"   …hidden bible saved (authoring side of the firewall) "
                    f"→ {prose_path}")

    meta = create_scenario_from_ingest(name, prose_path, provider,
                                       endless=endless, on_stage=on_stage)

    _emit(on_stage, "Stage 7 · Viability gate · entry material + cold-open smoke "
                    "over shipped reads")
    problems = _assess_viability(name, meta)
    if problems:
        _unpublish_scenario(name)
        raise ViabilityError(name, prose_path, problems)
    _emit(on_stage, "   …viable — scenario published")
    return meta


def _canon_entity_ids(world: Any) -> set[str]:
    """All entity ids that appear in canon — a session-zero/world-build
    scan (not the hot turn path), so reading rows directly is fine and
    far more robust than relying on event participation."""
    ids: set[str] = set()
    for row in world.buffer.all_rows():
        if getattr(row, "frame", "canon") == "canon":
            ids.add(row.entity)
    return ids


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
            if f.get("clue") and entity.startswith(("person:", "place:")):
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
        existing = json.loads(p.state("arc:main", "pin_index", frame="plot:main") or "[]")
        new_ids, items = [], []
        for i, (entity, feel) in enumerate(clues):
            pin_id = f"pin:clue_{_slug(entity)}_{i}"
            scope = "social" if entity.startswith("person:") else "region"
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
_DEFAULT_GOAL = "Uncover the truth and see the story through to its end."


def _hidden_terms(world: Any, proposal: dict) -> set[str]:
    """The tokens a player-facing goal must NOT contain — the names and
    answers the arc keeps hidden. Drawn from every canon entity id (its
    local-part word tokens) plus each beat's answer entity/value. Short
    tokens (<3 chars) are dropped as noise. This is the forbidden set the
    leak-check tests the goal against; over-inclusion only costs a fall
    back to the generic goal, never a leak (WIN-LOSS §10, Cx fail-closed)."""
    terms: set[str] = set()

    def _add(raw: str) -> None:
        local = str(raw).split(":", 1)[-1]
        for tok in re.split(r"[^a-z0-9]+", local.lower()):
            if len(tok) >= 3:
                terms.add(tok)

    for eid in _canon_entity_ids(world):
        _add(eid)
    for b in proposal.get("beats", []):
        _add(b.get("entity", ""))
        _add(b.get("value", ""))
    return terms


def _goal_statement_safe(goal: str, forbidden: set[str]) -> bool:
    """True iff `goal` is non-empty and shares no whole word with the
    forbidden set — a structural token check, not a lint we hope holds."""
    if not goal or not goal.strip():
        return False
    words = {w for w in re.split(r"[^a-z0-9]+", goal.lower()) if w}
    return words.isdisjoint(forbidden)


def _player_goal(proposal: dict, world: Any) -> str:
    """The non-spoiling player-facing aim for win_loss mode: the authored
    `goal_statement` if it passes the leak-check, else the generic default.
    Fail-closed — a leaky goal is dropped, never shown (WIN-LOSS §10)."""
    goal = (proposal.get("goal_statement") or "").strip()
    if goal and _goal_statement_safe(goal, _hidden_terms(world, proposal)):
        return goal
    if goal:
        logger.warning("goal_statement rejected (leaks a hidden term); "
                       "using the generic default")
    return _DEFAULT_GOAL


#: Cap on characters seeded with a knowledge frame — the protagonist
#: plus the most-present NPCs. Each is one good-tier call, so bound it.
SEED_CAST_CAP = int(os.getenv("CONSTRUCT_SEED_CAST_CAP", "5"))

#: Concurrency for per-character knowledge seeding (Kernos letter 044). The
#: seed calls are independent, so >1 fans the slow good-tier model calls out
#: over a bounded thread pool (~15-min from-scratch interview build → ~the
#: slowest single seed). Bounded to respect provider rate limits. Default
#: 1 = sequential, the prior behavior unchanged. A safe, reversible opt-in.
SEED_CONCURRENCY = max(1, int(os.getenv("CONSTRUCT_SEED_CONCURRENCY", "1")))


def _seed_cast(protagonist: str, people: list[str]) -> list[str]:
    """The protagonist first (the player inherits this frame), then the
    other key characters, capped."""
    others = [p for p in people if p != protagonist]
    return [protagonist, *others][:SEED_CAST_CAP]


def seed_character_frames(world: Any, provider: Provider,
                          characters: list[str], digest: str) -> list[str]:
    """Author each character's private `knows:<id>` frame from canon
    (frame-scoped secrecy, P4). Returns the ids actually seeded. Writes
    ONLY to knows: frames — never canon or plot: — so it is fully
    reversible (see reseed_character_frames). Fail-open per character: a
    failed authoring call skips that character, never the scenario.

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

    seeded: list[str] = []
    for char, items in results:
        if items:
            world.porcelain.ingest_structured(items, frame=f"knows:{char}")
            seeded.append(char)
            logger.info("seeded knows:%s with %d facts", char, len(items))
    return seeded


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
            for row in world.buffer.visible(frame=f"knows:{char}"):
                world.porcelain.retract(row.id, "reseed: re-authoring knowledge frame")
        seeded = seed_character_frames(world, provider, targets, digest)
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


def _build_arc(proposal: dict) -> Arc:
    protagonist = proposal["protagonist"]
    player_frame = f"knows:{protagonist}"
    beats = []
    for b in proposal["beats"]:
        raw = b["id"].split(":", 1)[-1]
        beats.append(Beat(
            beat_id=f"beat:{_slug(raw)}",
            phase=Phase(b["phase"]),
            weight=Weight(b["weight"]),
            achievable_via=_beat_expr(b, player_frame),
        ))
    climax = [b.beat_id for b in beats if b.phase in (Phase.CLIMAX, Phase.CRISIS)] \
        or [beats[-1].beat_id]
    k = max(1, min(2, len(climax) - 1)) if len(climax) > 1 else 1
    shape = ConclusionShape(
        shape_id="shape:main",
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
    refusal = Clock(clock_id="clock:refusal", fires_when=TurnsQuiet(15),
                    effects=({"entity": "event:world_concludes", "attribute": "kind",
                              "value": "refusal_conclusion"},),
                    bound_to="arc:main", rung=Rung.REFUSAL)
    failure_when = _failure_expr(proposal.get("failure_when"), player_frame)
    return Arc(
        arc_id="arc:main", protagonist=protagonist, shape=shape,
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
    # Reconstruct the arc from the plot: frame (~21ms post-037). A stamped
    # arc_cache from an older scenario is ignored — the frame is the truth.
    arc = arc_io.arc_from_cache(meta["arc_cache"]) if "arc_cache" in meta \
        else arc_io.arc_from_frame(PorcelainWorldReads(world))
    return world, arc, meta


def next_turn_number(world: Any) -> int:
    return len(world.porcelain.events(kind="turn", frame="session:main"))
