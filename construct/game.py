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

ARC_SCHEMA = {
    "type": "object",
    "properties": {
        "protagonist": {"type": "string", "description": "entity id, e.g. person:joel"},
        "theme": {"type": "string", "description": "the pitchable theme, one line"},
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


def _finalize_scenario(world: Any, name: str, title: str, provider: Provider,
                       spath: Path, endless: bool) -> dict:
    """Shared session-zero tail (both creation paths): once canon is
    established, author the hidden arc over it (lint-gated), seed
    knowledge frames, and write the scenario meta. ENTRY + DESTINATION."""
    from construct.arc.executor import arc_entities, turn_time

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
    cast = _seed_cast(arc.protagonist, people)
    seeded = seed_character_frames(world, provider, cast, digest)

    meta = {"title": title, "protagonist": arc.protagonist,
            "theme": proposal["theme"], "stance": "fiction", "mode": "pure",
            "arc_scope": sorted(e for e in arc_entities(arc) if reads.has_entity(e)),
            "seeded_frames": seeded, "endless": bool(endless)}
    spath.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def create_scenario_from_ingest(name: str, prose_path: Path,
                                provider: Provider, endless: bool = False) -> dict:
    """Session-zero Path A: fresh ingest of a work through OUR pipeline
    → pristine scenario."""
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
        logger.info("ingesting %d chunks from %s", len(chunks), prose_path)
        for i, chunk in enumerate(chunks, start=1):
            world.porcelain.ingest(chunk, source=f"doc:{prose_path.stem}", at=float(i))
            logger.info("chunk %d/%d ingested", i, len(chunks))
        return _finalize_scenario(world, name, title, provider, spath, endless)
    except BaseException:
        world.close()
        spath.unlink(missing_ok=True)
        spath.with_suffix(".meta.json").unlink(missing_ok=True)
        raise
    finally:
        world.close()


def create_scenario_from_interview(name: str, brief: str, provider: Provider,
                                   endless: bool = False) -> dict:
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
        return _finalize_scenario(world, name, title, provider, spath, endless)
    except BaseException:
        world.close()
        spath.unlink(missing_ok=True)
        spath.with_suffix(".meta.json").unlink(missing_ok=True)
        raise
    finally:
        world.close()


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
    return Arc(
        arc_id="arc:main", protagonist=protagonist, shape=shape,
        beats=tuple(beats), clocks=clocks, refusal_clock=refusal,
        climax_ready_k=k, climax_ready_beats=tuple(climax),
        phase_budget={Phase.SETUP: 5, Phase.RISING: 6, Phase.CRISIS: 3,
                      Phase.CLIMAX: 2, Phase.FALLING: 2},
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
