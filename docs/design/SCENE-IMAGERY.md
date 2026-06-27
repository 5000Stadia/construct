# SCENE-IMAGERY — a picture of every new location

A per-location image, painted in one consistent house style, shown **just before
the prose** of each new place the player enters. The picture is the visual cue that
the scene has *moved*; while the player stays put, the conversation is text-only.

```
-image-
(prose for this location)
Player: I go to the backyard
-image-                         ← scene changed → a new picture leads the new prose
(prose for the backyard)
Player: I do stuff here
(more prose — no new image, same place)
```

This is a **host feature** — no engine change. It rides on a fact the engine
*already* commits.

## The fact it rides on

When the player first enters a place, `turnloop.furnish_scene` mints and commits a
stable `description` on that `place:<id>` (resolver, `invent_under_canon`,
memoized). So a concrete, canon-consistent setting description **already exists** and
is **stable across re-entry**. Scene-imagery just reads it; it never invents a second
source of truth.

## Pipeline

1. **Detect (fast, pure — every turn).** `imagery.plan_scene` hashes the place's
   committed `description` and compares it to the per-scenario manifest. New or
   *changed* description → `fresh`; unchanged → `cached`. **No model call**, so the
   turn is never taxed. `Session._note_scene_image` runs this.
2. **Start rendering ASAP, in parallel.** The detection hook is fired *inside the
   turn* (`run_turn(on_scene=…)`, right after `furnish_scene`), so on a fresh scene
   the slow work (prompt cohort + image generation) runs on a daemon thread **while
   the NPC actions + narration are still being composed**. The text is never blocked
   waiting on a picture.
3. **Mint the prompt.** `cohorts.image_prompt` rewrites the narration-prose
   description into a text-to-image prompt for an **unpeopled** setting:
   - **KEEP** the fixed, scene-defining details that would look *wrong if omitted* —
     a broken-down wagon, a slain body with a dagger in its back, spilled blood, an
     overturned chair. A **corpse is part of the set** and stays.
   - **DROP** every **living** figure — the protagonist, "you", living NPCs,
     onlookers. Living characters stay *theatre of the mind* (in the prose, not the
     picture).
   - The model never names the art style; the host appends it deterministically.
4. **House style + genre touch.** `imagery.compose_prompt` always appends the house
   style — *"a detailed oil color painting — rich textured brushwork, painterly light
   and depth, elegant and quietly otherworldly, fine-art quality"* — plus a light
   touch of the world's **listed genre / game-type** (dumped in for per-story
   variety, e.g. *"with a touch of mystery whodunnit, social drama atmosphere"*).
5. **Generate the asset.** `imagery._dispatch` produces the file from the prompt.
   Backends, in order: an explicit `imagery.dispatcher` callable → `CONSTRUCT_IMAGE_CMD`
   (`{prompt}`/`{out}`) → the built-in **OpenAI Images** backend (`OPENAI_API_KEY`,
   `gpt-image-1`) → none. With **no backend wired the manifest is still produced** —
   the prompts sit ready to feed any generator — and play is byte-for-byte text-only.
6. **Deliver before the prose.** When the turn returns, the transport joins the
   in-flight render (`Session.pending_image`, bounded ~30 s) and — if the asset is
   ready — sends the photo through the photo side-channel **before** the text reply
   goes out. The picture lands first; the prose follows.

## Reuse / refresh

The asset path is `images/<scenario>/<place>-<hash>.png`, keyed by the description
hash. Same place + unchanged description → same hash → **reuse the existing asset**,
nothing re-sent. A changed description (a reshape, a fire that guts the room) → new
hash → **fresh asset**, delivered as the next scene image. The hash *is* the
change-detector; nothing else has to decide "did it change".

## Configuration (`.env`, default ON)

| var | default | effect |
|---|---|---|
| `CONSTRUCT_SCENE_IMAGES` | `1` (on) | set falsey to opt a world out entirely |
| `OPENAI_API_KEY` | — | enables the built-in gpt-image-1 backend |
| `CONSTRUCT_IMAGE_MODEL` | `gpt-image-1` | OpenAI image model |
| `CONSTRUCT_IMAGE_SIZE` | `1024x1024` | OpenAI image size |
| `CONSTRUCT_IMAGE_CMD` | — | custom generator command (`{prompt}`,`{out}`) |

The feature (capture + prompt manifest) is default-on; **actual image generation
needs a backend** (an `OPENAI_API_KEY`, a `CONSTRUCT_IMAGE_CMD`, or a wired
`dispatcher`). Until one is set, the world plays text-only with the prompts ready.

## Files

- `construct/imagery.py` — `plan_scene` / `render` / `render_async` / `note_scene`,
  the manifest, `compose_prompt`, the dispatcher + OpenAI backend.
- `construct/cohorts.py` — `image_prompt` (the unpeopled-setting prompt cohort, task `img`).
- `construct/turnloop.py` — `run_turn(on_scene=…)`, fired right after `furnish_scene`.
- `construct/session.py` — `_note_scene_image`, `_start_render`, `pending_image`,
  `_scene_genre`, `Reply.image`.
- `construct/transport_core.py` — `Outbound.image`, `_deliver_scene_image`, `photo` sink.
- `construct/telegram_bot.py` — `TelegramClient.send_photo`, the `_photo` wiring.
- `tests/test_imagery.py`, `tests/test_telegram.py::TestSceneImageDelivery`.

## Backlog (Cx 236 — non-blocking, GREEN for live testing)

- **Folded:** in-process manifest lock + atomic replace (no last-write-wins drop /
  half-written manifest); doc wording corrected to "parallel render, bounded join".
- **Folded (self-heal on backend failure):** the manifest is now written *after*
  dispatch and a scene is cached only when the asset actually landed (or when no
  backend is configured, where the prompt-only manifest is the deliverable). A
  configured backend that produces nothing — a failure, or the OpenAI billing hard
  limit — is **not** cached, so the scene **retries** on the next visit and images
  appear automatically once the backend recovers (no manual manifest-clear).
- **Deferred:** the slow-but-*successful* render that finishes *after* the bounded
  join — the asset is cached, but a cached scene isn't re-rendered, so its photo isn't
  re-delivered on a later visit (acceptable while the backend stays inside the join
  window). Re-showing a cached image on *return* to a prior location is likewise not
  yet wired (today an image shows on first entry to each place). `CONSTRUCT_IMAGE_CMD`
  prompt interpolation remains brittle (quotes/newlines/flag-like text) — prefer
  stdin/env/temp-file; the built-in OpenAI backend is unaffected.

## Boundaries honored

- **Engine untouched** — reads the committed `place.description`; commits nothing new
  to canon. Pure host orchestration.
- **Detection never taxes a turn; delivery is bounded** — detection is a pure hash
  check (no model call); rendering runs off-thread, overlapping the turn's
  NPC/narration work. The transport then blocks up to the bounded join (~30 s) to keep
  the image *before* the prose; a slow/failed/absent generator falls through to
  text-only, never breaking the turn's text or its exactly-once delivery.
