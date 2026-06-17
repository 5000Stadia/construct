"""One-off: re-ingest the frozen fixture against the current engine
(42fc3b3: containment veto + reconcile recall pass), run the host-side
reconcile() finalize pass, and print a scorecard for PB's 050 — does the
core-×3 under-merge collapse, is the container↔contents fusion gone, and
what proposal residue is left to adjudicate. Not part of the package."""
import json
import logging
from pathlib import Path

from construct.game import _chunk_chapters, _world
from construct.provider import CodexProvider, engine_tier_dispatch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("restamp")

PROSE = Path("examples/the_last_honest_meter.md")
OUT = Path("worlds/anchor2.world")
OUT.unlink(missing_ok=True)
Path("worlds/anchor2.meta.json").unlink(missing_ok=True)

provider = CodexProvider()
text = PROSE.read_text()
world = _world(OUT, "anchor2", model=engine_tier_dispatch(provider),
               stance="fiction", title=text.splitlines()[0].lstrip("# ").strip())
scorecard = {}
try:
    chunks = _chunk_chapters(text)
    log.info("ingesting %d chunks", len(chunks))
    for i, chunk in enumerate(chunks, start=1):
        world.porcelain.ingest(chunk, source=f"doc:{PROSE.stem}", at=float(i))
        log.info("chunk %d/%d done", i, len(chunks))

    # entity census BEFORE reconcile
    def core_entities():
        return sorted({r.entity for r in world.buffer.visible()
                       if "core" in r.entity and r.entity.startswith("obj:")})
    before = core_entities()

    # the host finalize pass (not auto-run by ingest, not on porcelain)
    merged = world.registry.reconcile()
    log.info("reconcile() performed %d merge(s)", merged)

    after = core_entities()
    # resolve each core variant + the drawer (veto check)
    res = {e: world.registry.resolve(e) for e in before}
    drawer_checks = {}
    for d in ("obj:false_drawer", "obj:memory_core", "obj:master_meter_memory_core", "obj:core"):
        try:
            drawer_checks[d] = world.registry.resolve(d)
        except Exception as ex:
            drawer_checks[d] = f"ERR {ex}"
    # how many DISTINCT identities do the core variants collapse to?
    distinct_core = sorted({world.registry.resolve(e) for e in before})
    # proposal residue (maybe_same_as)
    proposals = []
    for r in world.buffer.visible():
        if r.attribute == "maybe_same_as":
            proposals.append((r.entity, r.value, getattr(r, "status", None)))
    # false_drawer fusion check
    fd = world.registry.resolve("obj:false_drawer") if any(
        "false_drawer" in r.entity for r in world.buffer.visible()) else "(no false_drawer entity)"

    scorecard = {
        "engine_commit": "42fc3b3",
        "core_variants_before": before,
        "core_variants_after_count": len(after),
        "core_resolve_map": res,
        "core_collapses_to_N_identities": len(distinct_core),
        "distinct_core_identities": distinct_core,
        "false_drawer_resolves_to": fd,
        "false_drawer_fused_to_core": isinstance(fd, str) and "core" in fd,
        "reconcile_merges": merged,
        "maybe_same_as_proposals": proposals,
    }
finally:
    world.close()

print("\n==================== SCORECARD ====================")
print(json.dumps(scorecard, indent=2, default=str))
print("===================================================")
