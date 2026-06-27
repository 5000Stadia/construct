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
  generator): fired IN PARALLEL the moment a fresh scene is detected (during the
  turn), so generation overlaps the NPC/narration work. The transport then blocks up
  to a bounded join (`Session.pending_image`) to preserve the founder's layout —
  image first, then the new scene's prose — falling through to text-only if the asset
  isn't ready in time.

Default-on, lazy, fail-open, opt-out via ``CONSTRUCT_SCENE_IMAGES=0``. Image
GENERATION is pluggable; the DEFAULT backend is the **Codex OAuth subscription** (the
Responses `image_generation` tool — the same credential that powers all of Construct's
text, no separate API key, no separate billing). Order: an explicit :data:`dispatcher`
→ ``CONSTRUCT_IMAGE_CMD`` → Codex subscription → ``OPENAI_API_KEY`` (gpt-image-1) →
none; force one with ``CONSTRUCT_IMAGE_BACKEND`` (codex|openai|cmd|none). With no
backend, the manifest (``worlds/<scenario>.images.json``) IS the deliverable and play
is byte-for-byte text-only.
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
HOUSE_STYLE = ("a traditional oil painting on canvas — unmistakably painted, with "
               "visible brushstrokes, impasto texture and glazed depth, rich pigment and "
               "masterful painterly light, detailed and elegant, quietly otherworldly, "
               "museum-quality fine art (NOT a photograph, NOT a 3D render)")

_FLAG_ENV = "CONSTRUCT_SCENE_IMAGES"
_CMD_ENV = "CONSTRUCT_IMAGE_CMD"

#: Where generated image assets are written (overridable for tests so they never
#: touch the repo tree). Gitignored at the repo root.
IMAGES_DIR = Path("images")

#: Serializes the load→modify→save of a scenario's manifest across the background
#: render threads (in-process), so two concurrent renders can't read the same JSON
#: and last-write-wins over each other's prompt records (Cx 236 note 2).
_manifest_lock = threading.Lock()

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
    contents: str = ""
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
    # Where a generator should write the asset; deterministic so the same description
    # always maps to the same file (reuse) and a change maps to a new one.
    return str(IMAGES_DIR / _slug(scenario) / f"{_slug(place_id)}-{h}.png")


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
    # Atomic replace (Cx 236 note 2): write a sibling temp then os.replace, so a
    # crash mid-write can never leave a half-written/corrupt manifest.
    p = manifest_path(scenario)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    os.replace(tmp, p)


def compose_prompt(content: str, genre: str = "") -> str:
    """The final generator prompt: the cohort's setting content + a hard depict-only
    constraint (so the generator can't invent props/items the prose doesn't have) + the
    house style, with the world's genre as visual MOOD only (never added content). Kept
    deterministic so neither the constraint nor the style can be dropped by the model."""
    content = (content or "").strip().rstrip(".")
    style = HOUSE_STYLE
    genre = (genre or "").strip().strip(".,")
    if genre:
        style += f", in the visual mood and palette of {genre}"
    return (f"{content}.\n\n"
            "Show a believably furnished, lived-in room: ordinary period-appropriate "
            "furniture and fixtures are welcome, but add NO living people and NO "
            "discrete interactable or plot items that aren't named above (no keys, "
            "weapons, documents, letters, or a body the scene didn't specify).\n"
            f"Style: {style}.")


def plan_scene(scenario: str, place_id: str | None, place_name: str,
               description: str | None, *, world_brief: str = "",
               genre: str = "", contents: str = "") -> SceneImage | None:
    """FAST, pure detection (no model call) — safe to call every turn. Returns a
    :class:`SceneImage` flagged ``fresh`` (new/changed location OR changed contents →
    the caller should :func:`render` it) or ``cached`` (unchanged → do nothing), or
    None when disabled / nothing to depict. The hash folds in the room CONTENTS, so a
    body appearing (or any change to what's in the room) refreshes the image."""
    description, contents = (description or "").strip(), (contents or "").strip()
    if not enabled() or not place_id or not (description or contents):
        return None
    h = _hash(description + "\x1f" + contents)
    prior = _load_manifest(scenario).get(place_id)
    if prior and prior.get("description_hash") == h and prior.get("prompt"):
        return SceneImage(place_id=place_id, place_name=place_name, description_hash=h,
                          asset_path=prior.get("asset_path", _asset_path(scenario, place_id, h)),
                          status="cached", prompt=prior["prompt"], description=description,
                          world_brief=world_brief, genre=genre, contents=contents)
    return SceneImage(place_id=place_id, place_name=place_name, description_hash=h,
                      asset_path=_asset_path(scenario, place_id, h), status="fresh",
                      description=description, world_brief=world_brief, genre=genre,
                      contents=contents)


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
                                            world_brief=rec.world_brief,
                                            contents=rec.contents) or {}).get("prompt", "")
        rec.prompt = compose_prompt(content or rec.description or rec.contents, rec.genre)
        _dispatch(rec)
        asset_ok = Path(rec.asset_path).exists()
        # Persist the manifest AFTER dispatch (Cx 238 #1): cache the record only when
        # the asset actually landed, OR when no backend is configured (then the
        # prompt-only manifest is itself the deliverable). If a backend IS configured
        # but produced nothing (a failure, or the OpenAI billing limit), DON'T cache —
        # so the scene retries on a later visit instead of reading as done forever.
        if asset_ok or not _backend_configured():
            with _manifest_lock:  # serialize concurrent same-scenario renders (Cx 236 #2)
                manifest = _load_manifest(scenario)
                manifest[rec.place_id] = {"place_name": rec.place_name,
                                          "description_hash": rec.description_hash,
                                          "prompt": rec.prompt, "asset_path": rec.asset_path}
                _save_manifest(scenario, manifest)
        else:
            logger.info("scene image: backend produced no asset — not caching, will "
                        "retry on next visit: %s", rec.place_id)
        if deliver is not None and asset_ok:
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
               world_brief: str = "", genre: str = "", contents: str = "") -> SceneImage | None:
    """Synchronous plan+render convenience (CLI / tests / non-async callers): detect,
    and render in-line only when fresh. Returns the record or None."""
    rec = plan_scene(scenario, place_id, place_name, description,
                     world_brief=world_brief, genre=genre, contents=contents)
    if rec is None or not rec.fresh:
        return rec
    return render(scenario, rec, provider=provider)


def _codex_available() -> bool:
    """Whether the Codex OAuth credential is present — the DEFAULT image backend, the
    same ChatGPT subscription that powers all of Construct's text (no separate API key,
    no separate billing). Image pixels come from the Responses `image_generation` tool
    over the `/codex/responses` endpoint."""
    from pathlib import Path as _P
    return (_P.home() / ".codex" / "auth.json").exists()


def _selected_backend() -> str:
    """Which generation backend to use: an explicit `dispatcher` always wins; otherwise
    `CONSTRUCT_IMAGE_BACKEND` (codex|openai|cmd|none) forces it, else auto-detect in the
    order custom-command → Codex subscription → OpenAI API key → none."""
    if dispatcher is not None:
        return "dispatcher"
    forced = os.getenv("CONSTRUCT_IMAGE_BACKEND", "").strip().lower()
    if forced in ("none", "off", "0", "false", "no"):
        return "none"
    if forced in ("codex", "openai", "cmd"):
        return forced
    if os.getenv(_CMD_ENV, "").strip():
        return "cmd"
    if _codex_available():
        return "codex"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    return "none"


def _backend_configured() -> bool:
    """Whether an image-GENERATION backend is wired. When none is, a render legitimately
    produces no asset and the prompt-only manifest is the deliverable; when one IS, a
    missing asset means generation failed and should be retried, not cached (Cx 238 #1)."""
    return _selected_backend() != "none"


def _dispatch(rec: SceneImage) -> None:
    """Synchronously produce the asset file from the prompt. Backend per
    :func:`_selected_backend` (default: the Codex subscription). Never raises."""
    try:
        backend = _selected_backend()
        if backend == "dispatcher":
            dispatcher(rec)
        elif backend == "cmd":
            Path(rec.asset_path).parent.mkdir(parents=True, exist_ok=True)
            filled = os.getenv(_CMD_ENV, "").replace("{prompt}", rec.prompt).replace(
                "{out}", rec.asset_path)
            subprocess.run(shlex.split(filled), timeout=180, check=False)
        elif backend == "codex":
            _codex_dispatch(rec)
        elif backend == "openai":
            _openai_dispatch(rec)
    except Exception:
        logger.debug("image dispatch failed for %s", rec.place_id, exc_info=True)


def _codex_dispatch(rec: SceneImage) -> None:
    """Built-in DEFAULT backend: generate via the Codex OAuth subscription — the
    Responses `image_generation` tool over `/codex/responses`, reusing Construct's own
    `CodexProvider` auth/headers (no separate OpenAI API key, no separate billing).
    Synchronous; writes a PNG to ``rec.asset_path``. Never raises."""
    import asyncio

    import httpx

    from construct.provider import CodexProvider

    p = CodexProvider()
    auth = p._read_auth()
    headers = p._headers(auth)
    url = f"{p._base_url}/codex/responses"
    model = os.getenv("CONSTRUCT_IMAGE_MODEL_CODEX", p._cheap_model)
    size = os.getenv("CONSTRUCT_IMAGE_SIZE", "1536x1024")  # landscape scene framing
    quality = os.getenv("CONSTRUCT_IMAGE_QUALITY", "auto")  # detail comes from the STYLE prompt,
    tool = {"type": "image_generation"}                     # not from forcing high-res (founder)
    if size and size.lower() != "auto":
        tool["size"] = size
    if quality and quality.lower() != "auto":
        tool["quality"] = quality
    body = {
        "model": model,
        "instructions": ("Use the image_generation tool to render EXACTLY the described "
                         "setting and only the objects it names. Do not add any objects, "
                         "items, props, captions, text, or people that are not in the "
                         "description — especially no interactable items (keys, weapons, "
                         "documents). A described corpse stays; living people do not."),
        "input": [{"role": "user", "content": rec.prompt}],
        "store": False, "stream": True, "tools": [tool],
    }

    async def _run() -> str | None:
        img = None
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=30)) as http:
            async with http.stream("POST", url, headers=headers, json=body) as resp:
                resp.raise_for_status()
                buffer = ""
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        idx = buffer.index("\n\n")
                        block, buffer = buffer[:idx], buffer[idx + 2:]
                        data = "\n".join(l[5:].strip() for l in block.split("\n")
                                         if l.startswith("data:")).strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            ev = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        et = ev.get("type", "")
                        # the FULL image arrives on output_item.done as item.result
                        if et == "response.output_item.done":
                            item = ev.get("item", {})
                            if item.get("type") == "image_generation_call" and item.get("result"):
                                img = item["result"]
                        elif et in ("response.completed", "response.done"):
                            for item in ev.get("response", {}).get("output", []):
                                if item.get("type") == "image_generation_call" and item.get("result"):
                                    img = item["result"]
                        # fallbacks: a top-level result, then a streamed partial preview
                        r = ev.get("result")
                        if isinstance(r, str) and len(r) > 100:
                            img = r
                        pi = ev.get("partial_image_b64")
                        if not img and isinstance(pi, str) and len(pi) > 100:
                            img = pi
        return img

    img_b64 = asyncio.run(_run())
    if img_b64:
        out = Path(rec.asset_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(img_b64))
        logger.info("codex image written: %s", out)
    else:
        logger.warning("codex image generation returned no image for %s", rec.place_id)


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
