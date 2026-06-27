"""Debug: ingest emberroad under the B' spaced-axis policy and dump, per person, where they
are located at HEAD vs at opening_as_of, plus the min valid_from of their `in` rows — to see
whether chunk 1 actually places anyone (the _locatable_people(as_of=opening) empty-set bug)."""
from __future__ import annotations
import logging
from pathlib import Path
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from construct.game import _chunk_chapters, _world, scenario_path, engine_tier_dispatch
from construct.provider import CodexProvider
from construct.arc.executor import SOURCE_STEP, horizon_metadata

BIBLE = Path("generated/emberroad.md")
prov = CodexProvider()
text = BIBLE.read_text()
title = text.splitlines()[0].lstrip("# ").strip()
spath = Path("worlds/_debug_emberroad.world")
spath.unlink(missing_ok=True)
spath.with_suffix(".meta.json").unlink(missing_ok=True)
w = _world(spath, "_debug_emberroad", model=engine_tier_dispatch(prov), stance="fiction", title=title)
w.ingestor.classify_inline = False
chunks = _chunk_chapters(text)
print(f"{len(chunks)} chunks; SOURCE_STEP={SOURCE_STEP}")
for i, chunk in enumerate(chunks, start=1):
    try:
        w.porcelain.ingest(chunk, source="doc:emberroad", at=float(i) * SOURCE_STEP,
                           cursor_authoritative=True)
        print(f"  chunk {i} -> at={i*SOURCE_STEP}")
    except Exception as exc:
        print(f"  chunk {i} SKIPPED: {exc}")
w.porcelain.reconcile()
opening, nxt = horizon_metadata(SOURCE_STEP)
print(f"opening_as_of={opening} next_source_as_of={nxt}\n")

# every person entity + its in-row coordinates
from collections import defaultdict
rows_by_ent = defaultdict(list)
for r in w.buffer.all_rows():
    if r.attribute == "in":
        rows_by_ent[r.entity].append((getattr(r, "valid_from", None), r.value))

people = sorted({r.entity for r in w.buffer.all_rows()
                 if r.entity.startswith("person:")})
print(f"{len(people)} person entities\n")
for e in people:
    head = w.porcelain.locate(e)
    op = w.porcelain.locate(e, as_of=opening)
    ins = sorted((vf if vf is not None else -1, v) for vf, v in rows_by_ent.get(e, []))
    print(f"{e}\n   head={head}  opening={op}\n   in-rows={ins}")
w.close()
spath.unlink(missing_ok=True)
spath.with_suffix(".meta.json").unlink(missing_ok=True)
print("\n(debug world cleaned up)")
