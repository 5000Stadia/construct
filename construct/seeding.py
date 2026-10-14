"""Registry-first seeding through pattern-buffer's build library (SEEDING-LIBRARY-WIRING r2.1,
cr GREEN; pattern-buffer BUILD-LIBRARY-V1 r1.8.3).

Today every chunk's extraction invents its own ids and stage 2 repairs the result. With the
library, the story's author lists the cast as a manifest, code mints every id from it, each
chunk's extraction sees only the candidates known by then, an ambiguous mention lands on a
provisional `mention:` id with a proposal, and one serial writer commits it all. Identity is
decided once, by code.

This module holds construct's side: the manifest's validation, one repair, the category
fallback, the time mapping onto the source axis, extraction with one retry, the commit, and
holding the author's same-named entries apart. `CONSTRUCT_BUILD_LIBRARY=0` keeps the
per-chunk path exactly (a rollback without a code change)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: The rollback switch (rule 10): "0" selects today's per-chunk path.
LIBRARY_ENV = "CONSTRUCT_BUILD_LIBRARY"

#: Provisional ids the library mints for ambiguous mentions (rule 8): kept out of every
#: roster and every build stop; their facts stay on them, invisible to play.
MENTION_PREFIX = "mention:"


def library_enabled() -> bool:
    return os.getenv(LIBRARY_ENV, "1") != "0"


def is_mention(entity: Any) -> bool:
    return str(entity or "").startswith(MENTION_PREFIX)


def manifest_path(prose_path: Path) -> Path:
    """The manifest saved beside the prose, on the authoring side of the firewall."""
    return prose_path.with_suffix(".manifest.json")


def manifest_from_author(raw: Any) -> dict | None:
    """The author's manifest in the library's JSON shape (`Manifest.from_dict`): the schema
    carries namesakes as objects `{a, b, anchor_quote}`, the library as lists."""
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        return None
    namesakes = []
    for n in raw.get("namesakes") or []:
        if isinstance(n, dict):
            namesakes.append([n.get("a", ""), n.get("b", ""), n.get("anchor_quote", "")])
        elif isinstance(n, (list, tuple)):
            namesakes.append(list(n))
    return {"entries": list(raw["entries"]), "namesakes": namesakes}


def load_manifest(prose_path: Path) -> dict | None:
    path = manifest_path(prose_path)
    if not path.exists():
        return None
    try:
        return manifest_from_author(json.loads(path.read_text()))
    except (OSError, ValueError) as exc:
        logger.warning("manifest at %s unreadable (%s); the category passes stand in", path, exc)
        return None


def text_by_chapter(chunks: list[str]) -> dict[int, str]:
    """Rule 4: construct's existing chunks, numbered from 1, are the library's chapters, so
    time stays on the source axis (one SOURCE_STEP per chunk). A leading chunk holding only
    headings (the story's `# Title` line) is folded into the first chapter: otherwise the
    story's first chapter would be chapter 2, above `opening_as_of`, and with gate-stamped
    identity its whole cast would be invisible at the opening."""
    parts = [c for c in chunks if c.strip()]
    if len(parts) > 1 and all(line.lstrip().startswith("#") or not line.strip()
                              for line in parts[0].splitlines()):
        parts = [parts[0].rstrip() + "\n\n" + parts[1], *parts[2:]]
    return {i: c for i, c in enumerate(parts, start=1)}


def build_registry(texts: dict[int, str], manifest_data: dict | None, prose: str,
                   repair: Callable[[str, dict, list], Any], model: Callable,
                   on_stage: Callable[[str], None]):
    """Rule 3: validate the author's manifest; on `ManifestError`, ONE repair call with the
    full problem list; if that fails too, the library's own category passes (logged
    `manifest_fallback`). No manifest (imported prose): the category passes directly.
    Returns (registry, source) with source one of author / repaired / category_passes."""
    from patternbuffer.build import Manifest, ManifestError, Registry, category_passes

    if manifest_data is not None:
        try:
            return Registry.from_manifest(Manifest.from_dict(manifest_data), texts), "author"
        except ManifestError as exc:
            logger.warning("manifest invalid (%d problem(s)); one repair", len(exc.problems))
            on_stage(f"   …manifest: {len(exc.problems)} problem(s), one repair")
            try:
                fixed = manifest_from_author(repair(prose, manifest_data, exc.problems))
                if fixed is not None:
                    return (Registry.from_manifest(Manifest.from_dict(fixed), texts),
                            "repaired")
            except ManifestError as exc2:
                logger.warning("manifest_fallback: repair still invalid (%d problem(s))",
                               len(exc2.problems))
            except Exception as exc2:  # noqa: BLE001 — a failed repair call falls back
                logger.warning("manifest_fallback: repair call failed: %s", exc2)
            logger.warning("manifest_fallback: the category passes stand in")
            on_stage("   …manifest_fallback: naming the cast from the prose")
    return Registry.from_manifest(category_passes(texts, model), texts), "category_passes"


def chunk_times(chunks: list, source_step: float) -> dict[int, float]:
    """Rule 4: `time_of(i) = chunk.chapter * SOURCE_STEP + k`, k the chunk's index within its
    chapter, so chapter 1 keeps the band below `opening_as_of` and a chapter split at a reveal
    gets distinct, increasing times."""
    seen: dict[int, int] = {}
    out: dict[int, float] = {}
    for c in chunks:
        k = seen.get(c.chapter, 0)
        seen[c.chapter] = k + 1
        out[c.index] = float(c.chapter) * source_step + k
    return out


def _raised_once(result: Any) -> bool:
    """r2.2: the chunk made exactly one call, and it raised (pattern-buffer's precise test;
    an error text alone can also follow the library's own retry)."""
    attempts = getattr(result, "attempts", ()) or ()
    return len(attempts) == 1 and attempts[0].raw is None


def extract_with_retry(chunks: list, registry: Any, model: Callable,
                       on_stage: Callable[[str], None], workers: int = 8) -> list:
    """Rule 5 (r2.2): at most two model calls per chunk, ever. The library re-asks a chunk
    whose RETURNED answer refused it (`retries=1`); construct re-runs only a chunk whose one
    call RAISED, with `retries=0`. A chunk still in error stops the build with its first
    cause, before any commit. Every dropped handle is logged and counted (it carries no fact,
    so it never stops a build)."""
    from patternbuffer.build import extract

    results = extract(chunks, registry, model, workers=workers, retries=1)
    # the INITIAL failing attempt (attempts[0]), not the final error the library's retry left
    first_cause = {r.index: ((r.attempts[0].error if getattr(r, "attempts", None) else None)
                             or r.error) for r in results if r.error}
    raised = [c for c, r in zip(chunks, results) if r.error and _raised_once(r)]
    if raised:
        logger.warning("extract: %d chunk(s) raised; one re-run: %s", len(raised),
                       [(r.index, r.error) for r in results if r.error and _raised_once(r)])
        again = {r.index: r for r in extract(raised, registry, model, workers=workers,
                                             retries=0)}
        results = [again.get(r.index, r) for r in results]
    dropped = [d for r in results for d in (getattr(r, "dropped_handles", ()) or ())]
    for d in dropped:
        logger.info("extract: dropped handle chunk %s %s %s %r candidates=%s", d.chunk,
                    d.kind, d.handle, d.name, list(d.candidates))
    for r in results:
        on_stage(f"   …chunk {r.index} {'REFUSED' if r.error else 'extracted'}")
    if dropped:
        on_stage(f"   …{len(dropped)} dropped handle(s)")
    still = [r for r in results if r.error]
    if still:
        bad = still[0]
        raise RuntimeError(f"ingest failed: chunk {bad.index} refused; "
                           f"first cause: {first_cause.get(bad.index, bad.error)}")
    return results


def same_named_entry_pairs(registry: Any) -> list[tuple[str, str]]:
    """Rule 7's candidates: every pair of manifest entries sharing a normalised name, not
    already declared namesakes. Entries only (never a `mention:` id or an escape). The build
    module holds them apart (identity verbs live there; R34 P1)."""
    from patternbuffer.build.text import name_key

    entries = [i for i in registry.identities if not i.is_persona]
    declared = {frozenset((a, b)) for a, b, _q in registry.namesakes}
    out: list[tuple[str, str]] = []
    for x in range(len(entries)):
        for y in range(x + 1, len(entries)):
            a, b = entries[x], entries[y]
            if frozenset((a.id, b.id)) in declared:
                continue
            if {name_key(n) for n in a.names} & {name_key(n) for n in b.names}:
                out.append((a.id, b.id))
    return out


def ingest_library(world: Any, chunks: list[str], prose: str, manifest_data: dict | None,
                   *, model: Callable, repair: Callable[[str, dict, list], Any],
                   source_step: float, on_stage: Callable[[str], None]) -> Any:
    """The library path of Stage 1, inside the build session the caller began: registry,
    plan, extract (one retry), commit at gate-stamped identity. Returns the registry; the
    build module then holds the same-named entries apart (rule 7) and hands
    `registry.entries()` to the cast author (rule 9)."""
    from patternbuffer.build import CommitRefused, commit, plan

    texts = text_by_chapter(chunks)
    registry, source = build_registry(texts, manifest_data, prose, repair, model, on_stage)
    on_stage(f"   …registry: {len(registry.identities)} identities ({source})")
    longest = max((len(t.split()) for t in texts.values()), default=1)
    planned = plan(texts, registry, max_words=max(longest * 2, 1))
    results = extract_with_retry(planned, registry, model, on_stage)
    times = chunk_times(planned, source_step)
    try:
        receipt = commit(world, registry, results, time_of=lambda i: times[i],
                         ingest_kwargs={"classify": "defer", "cursor_authoritative": True})
    except CommitRefused as exc:
        raise RuntimeError(f"ingest failed: commit refused ({exc.code}): {exc}") from exc
    logger.info("library build: %d minted, %d mention(s), %d escape(s), %d proposal(s) left "
                "open (%s)", len(receipt.minted), receipt.mentions, receipt.escapes,
                receipt.proposals, source)
    return registry


def cast_note(entries: list[dict]) -> str:
    """Rule 9: the cast author's view of the story's own cast list (id, names, type, role),
    so it reuses "Hester Rook, sergeant" rather than minting a twin."""
    lines = []
    for e in entries or []:
        if e.get("type") not in ("person", "animal", "creature"):
            continue
        kind = e["type"] + (f", {e['species']}" if e.get("species") else "")
        role = f"; {e['role']}" if e.get("role") else ""
        lines.append(f"{e['id']}: {'; '.join(e.get('names') or [])} ({kind}{role})")
    return "\n".join(lines)
