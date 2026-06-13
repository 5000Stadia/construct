"""Scenario/playthrough management + session-zero ingest wiring.

The v1 model (letters 012/013): a scenario is the pristine genesis
`.world` (never written by play); each scenario has ONE playthrough
slot (`<name>.play.world`); "start from the beginning" recopies the
pristine file over the slot. Two files, one copy operation.
"""

from __future__ import annotations

import json
import logging
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
from construct.provider import Provider, complete_sync, engine_tier_dispatch

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


def scenario_path(name: str) -> Path:
    return WORLDS_DIR / f"{name}.world"


def slot_path(name: str) -> Path:
    return WORLDS_DIR / f"{name}.play.world"


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


def create_scenario_from_ingest(name: str, prose_path: Path,
                                      provider: Provider) -> dict:
    """Session-zero Path A: fresh ingest through OUR pipeline → pristine
    scenario. Stages per SESSION-ZERO.md; checkpoints to session:main."""
    WORLDS_DIR.mkdir(exist_ok=True)
    spath = scenario_path(name)
    if spath.exists():
        raise FileExistsError(f"scenario {name!r} already exists at {spath}")

    text = prose_path.read_text()
    title = text.splitlines()[0].lstrip("# ").strip() or name
    world = World(spath, world_id=f"w:{name}", model=engine_tier_dispatch(provider),
                  stance="fiction", title=title,
                  description=f"Ingested from {prose_path.name} via Holodeck session-zero")
    try:
        # WORLD-A: chunked ingest, scene cursor advancing per chunk.
        chunks = _chunk_chapters(text)
        logger.info("ingesting %d chunks from %s", len(chunks), prose_path)
        seen_entities: set[str] = set()
        for i, chunk in enumerate(chunks, start=1):
            receipt = world.porcelain.ingest(
                chunk, source=f"doc:{prose_path.stem}", at=float(i))
            rows = receipt.to_dict()["rows"] if hasattr(receipt, "to_dict") else receipt["rows"]
            seen_entities.update(row["entity"] for row in rows)
            logger.info("chunk %d/%d ingested (%d rows)", i, len(chunks), len(rows))

        # ENTRY + DESTINATION: one arc-author call over the ingested world,
        # then deterministic construction + lint (bounded retries).
        reads = PorcelainWorldReads(world)
        people = sorted({e for e in seen_entities if e.startswith("person:")}
                        | set(_known_people(world)))
        scope = people + sorted({e for e in seen_entities
                                 if e.startswith(("fact:", "obj:", "place:"))})[:40]
        digest = (json.dumps(world.porcelain.snapshot(scope))[:6000]
                  if scope else "(nothing ingested)")

        arc = None
        last_findings: list = []
        for attempt in range(3):
            proposal = complete_sync(provider, 
                "You are authoring the hidden arc for a text-construct scenario "
                "(novel-arc mode: the mystery IS the arc). Below is the ingested "
                "world's people digest. Choose the protagonist (the natural "
                "point-of-view character), the thematic conclusion shape, and "
                "4-6 path-independent beats. player_learns beats must reference "
                "entity/attribute/value triples PRESENT in the digest; "
                "event_occurs beats name a plausible event kind.\n\n"
                f"WORLD DIGEST:\n{digest}\n\n"
                + (f"PRIOR ATTEMPT FAILED LINT: {last_findings}; fix those.\n"
                   if last_findings else ""),
                ARC_SCHEMA, tier="main", deliberate=True)  # planning-class: pays for reasoning
            arc = _build_arc(proposal)
            findings = lint_arc(arc, reads)
            blocking = [f for f in findings if f.check != "2-paths"]  # see note below
            if not blocking:
                if findings:
                    logger.warning("arc lints with soft findings: %s", findings)
                break
            last_findings = [f"{f.check}: {f.message}" for f in blocking]
            logger.warning("arc lint failed (attempt %d): %s", attempt + 1, last_findings)
            arc = None
        if arc is None:
            raise RuntimeError(f"arc failed lint after 3 attempts: {last_findings}")

        player_frame = f"knows:{arc.protagonist}"
        world.porcelain.ingest_structured(
            arc_io.arc_to_items(arc) + arc_io.index_items(arc))
        from construct.arc.executor import turn_time
        world.porcelain.ingest_structured([
            {"entity": "event:turn_0", "attribute": "kind", "value": "turn",
             "valid_from": turn_time(0)},
        ], frame="session:main")

        from construct.arc.executor import arc_entities
        meta = {"title": title, "protagonist": arc.protagonist,
                "theme": proposal["theme"], "stance": "fiction",
                # canon-strict by default for ingested/determined worlds
                # (letter 028): players act in the world, never author it.
                "mode": "pure",
                # Derived, disposable caches (rebuildable from plot:):
                # the immutable arc structure + the lint-verified entity
                # scope — at play-world scale, point reads cost minutes.
                "arc_cache": arc_io.arc_to_cache(arc),
                "arc_scope": sorted(e for e in arc_entities(arc)
                                    if reads.has_entity(e))}
        spath.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
        return meta
    except BaseException:
        # No half-scenarios: a failed session zero leaves nothing behind
        # (loud-fail; the exception carries the diagnostic).
        world.close()
        spath.unlink(missing_ok=True)
        spath.with_suffix(".meta.json").unlink(missing_ok=True)
        raise
    finally:
        world.close()


def _known_people(world: Any) -> list[str]:
    """Person entities known to the world (registry scan via events +
    state probes is engine-internal; we read the identity registry the
    porcelain way: people appear as event agents/patients and kind rows)."""
    people = set()
    for ev in world.porcelain.events():
        people.update(a for a in ev.get("agents", []) if str(a).startswith("person:"))
        people.update(p for p in ev.get("patients", []) if str(p).startswith("person:"))
    return sorted(people)


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


def start_playthrough(name: str, fresh: bool) -> Path:
    spath, slot = scenario_path(name), slot_path(name)
    if not spath.exists():
        raise FileNotFoundError(f"no scenario {name!r} (looked at {spath})")
    if fresh or not slot.exists():
        shutil.copyfile(spath, slot)  # the one copy operation (letter 013)
        logger.info("playthrough slot (re)created from pristine scenario")
    return slot


def open_playthrough(name: str, provider: Provider) -> tuple[Any, Arc, dict]:
    slot = slot_path(name)
    if not slot.exists():
        raise FileNotFoundError(
            f"no playthrough slot for {name!r} — run `construct play {name} --fresh`")
    world = World(slot, world_id=f"w:{name}", model=engine_tier_dispatch(provider))
    meta_path = scenario_path(name).with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if "arc_cache" in meta:
        arc = arc_io.arc_from_cache(meta["arc_cache"])
    else:
        # Fallback: reconstruct from the frame (slow at scale; the cache
        # is just a derived copy of these same rows).
        arc = arc_io.arc_from_frame(PorcelainWorldReads(world))
    return world, arc, meta


def next_turn_number(world: Any) -> int:
    return len(world.porcelain.events(kind="turn", frame="session:main"))
