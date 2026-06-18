"""Library ingestion — turn a dropped document into a pattern-buffer scenario,
the same pipeline that built the example world. Powers two delivery channels
(an import folder + Discord file drop), both thin layers over
`create_scenario_from_ingest`; per-stage status flows through `on_stage`.

Drop a `.txt`/`.md` into the import folder (or hand the bot one) and it lands in
the library alongside `anchor` — no CLI incantation required."""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Callable

from construct.game import (WORLDS_DIR, _slug, create_scenario_from_ingest,
                            scenario_path)
from construct.provider import Provider

logger = logging.getLogger(__name__)

#: Document types the library accepts. Plain prose only — no parsing magic.
INGEST_SUFFIXES = (".txt", ".md")

#: Default drop folder (poll target). Override per call.
IMPORT_DIR = Path("import")

OnStage = Callable[[str], None]


def _unique_name(stem: str) -> str:
    """A scenario name from a filename stem, conformed to the id grammar and
    made unique against the existing library (never overwrite a scenario)."""
    base = _slug(stem) or "world"
    name, n = base, 2
    while scenario_path(name).exists():
        name, n = f"{base}_{n}", n + 1
    return name


def ingest_document(path: str | Path, provider: Provider, *, on_stage: OnStage | None = None,
                    name: str | None = None, endless: bool = False) -> tuple[str, dict]:
    """Ingest ONE document into the library as a fresh scenario. Returns
    (scenario_name, meta). Name defaults to a unique slug of the filename stem
    so a drop never clobbers an existing world. Raises on a bad type / missing
    file; the build's own per-stage status flows through `on_stage`."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in INGEST_SUFFIXES:
        raise ValueError(f"unsupported document type {path.suffix!r} — use .txt or .md")
    name = name or _unique_name(path.stem)
    if on_stage:
        on_stage(f"Importing {path.name} → new scenario {name!r}")
    meta = create_scenario_from_ingest(name, path, provider, endless=endless, on_stage=on_stage)
    if on_stage:
        on_stage(f"✓ {meta.get('title', name)} is in the library — play: construct play {name}")
    return name, meta


def ingest_bytes(filename: str, data: bytes | str, provider: Provider, *,
                 on_stage: OnStage | None = None, endless: bool = False) -> tuple[str, dict]:
    """Ingest a document delivered as bytes (e.g. a Discord attachment): write
    it to a temp file and delegate to `ingest_document`. The filename gives the
    type (.txt/.md) and the scenario name. Returns (scenario_name, meta)."""
    import tempfile
    suffix = Path(filename).suffix.lower()
    if suffix not in INGEST_SUFFIXES:
        raise ValueError(f"unsupported document type {suffix!r} — use .txt or .md")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / Path(filename).name
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return ingest_document(p, provider, on_stage=on_stage, endless=endless)


def scan_import_folder(provider: Provider, *, import_dir: str | Path = IMPORT_DIR,
                       on_stage: OnStage | None = None,
                       processed_dir: str | Path | None = None) -> list[tuple[str, dict]]:
    """Ingest every new `.txt`/`.md` in the import folder, moving each to
    `processed/` after a successful build (so a rescan won't redo it). Returns
    [(filename, meta | {"error": ...})]. One bad file never sinks the batch."""
    import_dir = Path(import_dir)
    import_dir.mkdir(parents=True, exist_ok=True)
    processed = Path(processed_dir) if processed_dir else import_dir / "processed"
    results: list[tuple[str, dict]] = []
    for p in sorted(import_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in INGEST_SUFFIXES:
            continue
        try:
            _name, meta = ingest_document(p, provider, on_stage=on_stage)
            processed.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(processed / p.name))
            results.append((p.name, meta))
        except Exception as exc:  # fail-open per file; the batch lives
            logger.exception("library import failed for %s", p)
            if on_stage:
                on_stage(f"✗ {p.name} failed: {exc}")
            results.append((p.name, {"error": str(exc)}))
    return results


def watch_import_folder(provider: Provider, *, import_dir: str | Path = IMPORT_DIR,
                        on_stage: OnStage | None = None, interval: float = 5.0) -> None:
    """Poll the import folder forever, ingesting new drops as they land
    (Ctrl-C to stop). The same poll-watch shape used across the project."""
    import_dir = Path(import_dir)
    import_dir.mkdir(parents=True, exist_ok=True)
    if on_stage:
        on_stage(f"Watching {import_dir}/ for .txt/.md drops (Ctrl-C to stop)…")
    while True:
        scan_import_folder(provider, import_dir=import_dir, on_stage=on_stage)
        time.sleep(interval)
