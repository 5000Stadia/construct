"""Per-location image prompts for an external AI image generator (SCENE-IMAGERY).

When the player enters a fresh location, Construct already mints and commits a
stable `description` on that place (``turnloop.furnish_scene``). This module turns
that committed setting prose into a standalone text-to-image PROMPT — figures and
the player stripped out, the founder's house style ("a highly detailed oil
painting") always appended — and caches it by a hash of the description, keyed per
scenario. So:

* same location + unchanged description  → NO image work, nothing re-sent (the
  conversation stays text-only until the place changes);
* a new/changed location  → the hash changes, so a FRESH prompt + asset are made,
  and the picture itself signals the scene shift.

**Two-phase, parallel-friendly (founder):** detection is split from rendering so a
turn is never blocked on an image.

* :func:`plan_scene` — pure, fast, NO model call: hashes the description, reads the
  manifest, and says fresh-or-cached. The turn loop calls only this.
* :func:`render` / :func:`render_async` — the heavy path (the prompt cohort + the
  generator): the transport fires this IN PARALLEL the moment a fresh scene is
  detected, so the text reply goes out immediately and the picture is delivered
  (via a ``deliver`` callback) as soon as it's ready.

Default-on, lazy, fail-open, opt-out via ``CONSTRUCT_SCENE_IMAGES=0``. Image
GENERATION is pluggable: set :data:`dispatcher`, or ``CONSTRUCT_IMAGE_CMD``, or an
``OPENAI_API_KEY`` (the built-in gpt-image-1 backend). With nothing wired, the
manifest (``worlds/<scenario>.images.json``) IS the deliverable — prompts ready to
feed any generator — and play is byte-for-byte text-only as before.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from construct.game import WORLDS_DIR

logger = logging.getLogger(__name__)

#: The founder's house style — appended to every prompt so the whole world reads as
#: one elegant, slightly otherworldly gallery. Always present regardless of what the
#: model returns (we compose it deterministically, not via the cohort). A touch of the
#: world's genre is layered on per scene (see `compose_prompt`).
HOUSE_STYLE = ("a detailed oil color painting — rich textured brushwork, painterly "
               "light and depth, elegant and quietly otherworldly, fine-art quality")

_FLAG_ENV = "CONSTRUCT_SCENE_IMAGES"
_CMD_ENV = "CONSTRUCT_IMAGE_CMD"

#: Optional host-set dispatcher: ``(SceneImage) -> str | None``. SYNCHRONOUS — it
#: must have written ``rec.asset_path`` by the time it returns (so the file can be
#: sent). Return the written path (or None). Wire to a real backend if you don't
#: want the built-in OpenAI one.
dispatcher: Callable[["SceneImage"], str | None] | None = None


@dataclass
class SceneImage:
    """One location's image record. ``status`` is ``"fresh"`` (the location is new
    or its description changed — render + show) or ``"cached"`` (unchanged — do
    nothing). ``description``/``world_brief`` are carried plan→render; ``prompt``
    and ``asset_path`` are filled by :func:`render` (or read from the manifest for a
    cached hit)."""

    place_id: str
    place_name: str
    description_hash: str
    asset_path: str
    status: str  # "fresh" | "cached"
    description: str = ""
    world_brief: str = ""
    genre: str = ""
    prompt: str = ""

    @property
    def fresh(self) -> bool:
        return self.status == "fresh"


def enabled() -> bool:
    """Scene imagery is ON unless explicitly disabled (founder: don't value the off
    state). ``CONSTRUCT_SCENE_IMAGES`` set to a falsey value opts a world out."""
    return os.getenv(_FLAG_ENV, "1").strip().lower() not in ("0", "false", "no", "off", "")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "scene"


def _hash(description: str) -> str:
    return hashlib.sha256((description or "").strip().encode("utf-8")).hexdigest()[:16]


def manifest_path(scenario: str) -> Path:
    return WORLDS_DIR / f"{_slug(scenario)}.images.json"


def _asset_path(scenario: str, place_id: str, h: str) -> str:
    # Where a generator should write the asset; relative + deterministic so the same
    # description always maps to the same file (reuse) and a change maps to a new one.
    return str(Path("images") / _slug(scenario) / f"{_slug(place_id)}-{h}.png")


def _load_manifest(scenario: str) -> dict:
    p = manifest_path(scenario)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text() or "{}")
    except Exception:
        logger.warning("scene-image manifest unreadable: %s", p)
        return {}


def _save_manifest(scenario: str, manifest: dict) -> None:
    p = manifest_path(scenario)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def compose_prompt(content: str, genre: str = "") -> str:
    """The final generator prompt: the cohort's unpeopled setting content + the house
    style (always), with a light touch of the world's genre. Kept deterministic so the
    style can never be dropped by the model."""
    content = (content or "").strip().rstrip(".")
    style = HOUSE_STYLE
    genre = (genre or "").strip().strip(".,")
    if genre:
        style += f", with a touch of {genre} atmosphere"
    return f"{content}.\n\nStyle: {style}."


def plan_scene(scenario: str, place_id: str | None, place_name: str,
               description: str | None, *, world_brief: str = "",
               genre: str = "") -> SceneImage | None:
    """FAST, pure detection (no model call) — safe to call every turn. Returns a
    :class:`SceneImage` flagged ``fresh`` (new/changed location → the caller should
    :func:`render` it) or ``cached`` (unchanged → do nothing), or None when disabled
    / nothing to depict. A cached hit carries the prior prompt+asset from the
    manifest; a fresh one carries the source description for rendering."""
    if not enabled() or not place_id or not (description or "").strip():
        return None
    h = _hash(description)
    prior = _load_manifest(scenario).get(place_id)
    if prior and prior.get("description_hash") == h and prior.get("prompt"):
        return SceneImage(place_id=place_id, place_name=place_name, description_hash=h,
                          asset_path=prior.get("asset_path", _asset_path(scenario, place_id, h)),
                          status="cached", prompt=prior["prompt"], description=description,
                          world_brief=world_brief, genre=genre)
    return SceneImage(place_id=place_id, place_name=place_name, description_hash=h,
                      asset_path=_asset_path(scenario, place_id, h), status="fresh",
                      description=description, world_brief=world_brief, genre=genre)


def render(scenario: str, rec: SceneImage, *, provider: Any = None,
           deliver: Callable[["SceneImage"], None] | None = None) -> SceneImage:
    """The HEAVY path (prompt cohort + generator). Mints the unpeopled prompt, runs
    the dispatcher to write the asset, records the manifest, and — if ``deliver`` is
    given and the asset file exists — hands the finished image to it (e.g. the
    transport's send-photo). Safe to run in a background thread; fail-open."""
    try:
        content = ""
        if provider is not None:
            from construct import cohorts
            content = (cohorts.image_prompt(provider, place_name=rec.place_name,
                                            description=rec.description,
                                            world_brief=rec.world_brief) or {}).get("prompt", "")
        rec.prompt = compose_prompt(content or rec.description, rec.genre)
        manifest = _load_manifest(scenario)
        manifest[rec.place_id] = {"place_name": rec.place_name,
                                  "description_hash": rec.description_hash,
                                  "prompt": rec.prompt, "asset_path": rec.asset_path}
        _save_manifest(scenario, manifest)
        _dispatch(rec)
        if deliver is not None and Path(rec.asset_path).exists():
            deliver(rec)
        logger.info("scene image rendered: %s", rec.place_id)
    except Exception:
        logger.debug("render failed for %s/%s", scenario, rec.place_id, exc_info=True)
    return rec


def render_async(scenario: str, rec: SceneImage, *, provider: Any = None,
                 deliver: Callable[["SceneImage"], None] | None = None) -> None:
    """Fire :func:`render` on a daemon thread — the parallel path (founder: request
    the image ASAP, never block the turn's text). The picture is delivered via
    ``deliver`` whenever it's ready, after the text has already gone out."""
    threading.Thread(target=render, args=(scenario, rec),
                     kwargs={"provider": provider, "deliver": deliver},
                     daemon=True, name="scene-image").start()


def note_scene(scenario: str, place_id: str | None, place_name: str,
               description: str | None, *, provider: Any = None,
               world_brief: str = "", genre: str = "") -> SceneImage | None:
    """Synchronous plan+render convenience (CLI / tests / non-async callers): detect,
    and render in-line only when fresh. Returns the record or None."""
    rec = plan_scene(scenario, place_id, place_name, description,
                     world_brief=world_brief, genre=genre)
    if rec is None or not rec.fresh:
        return rec
    return render(scenario, rec, provider=provider)


def _dispatch(rec: SceneImage) -> None:
    """Synchronously produce the asset file from the prompt. Backends, in order:
    explicit :data:`dispatcher` → ``CONSTRUCT_IMAGE_CMD`` → built-in OpenAI
    (``OPENAI_API_KEY``) → none (manifest-only). Never raises."""
    try:
        if dispatcher is not None:
            dispatcher(rec)
            return
        cmd = os.getenv(_CMD_ENV, "").strip()
        if cmd:
            Path(rec.asset_path).parent.mkdir(parents=True, exist_ok=True)
            filled = cmd.replace("{prompt}", rec.prompt).replace("{out}", rec.asset_path)
            subprocess.run(shlex.split(filled), timeout=180, check=False)
            return
        if os.getenv("OPENAI_API_KEY", "").strip():
            _openai_dispatch(rec)
    except Exception:
        logger.debug("image dispatch failed for %s", rec.place_id, exc_info=True)


def _openai_dispatch(rec: SceneImage) -> None:
    """Built-in backend: OpenAI Images (gpt-image-1). Synchronous; writes a PNG to
    ``rec.asset_path``. Gated on ``OPENAI_API_KEY`` (model via ``CONSTRUCT_IMAGE_MODEL``,
    size via ``CONSTRUCT_IMAGE_SIZE``). Never raises."""
    try:
        import httpx
        key = os.environ["OPENAI_API_KEY"].strip()
        model = os.getenv("CONSTRUCT_IMAGE_MODEL", "gpt-image-1")
        size = os.getenv("CONSTRUCT_IMAGE_SIZE", "1024x1024")
        resp = httpx.post("https://api.openai.com/v1/images/generations",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "prompt": rec.prompt, "size": size,
                                "n": 1}, timeout=180)
        resp.raise_for_status()
        b64 = resp.json()["data"][0]["b64_json"]
        out = Path(rec.asset_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(b64))
        logger.info("openai image written: %s", out)
    except Exception:
        logger.warning("openai image generation failed for %s", rec.place_id, exc_info=True)
