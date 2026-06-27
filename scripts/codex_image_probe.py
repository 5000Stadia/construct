"""Empirical probe: can the Codex OAuth /responses endpoint generate IMAGES?

Uses Construct's own CodexProvider auth/headers/base_url and sends a Responses
request with the built-in `image_generation` tool, then reports every SSE event
type seen and whether any image bytes came back. Read-only diagnostic — writes the
image to images/_probe/codex-test.png iff it works.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections import Counter
from pathlib import Path

import httpx

from construct.provider import CodexProvider


async def main() -> None:
    p = CodexProvider()
    auth = p._read_auth()
    headers = p._headers(auth)
    url = f"{p._base_url}/codex/responses"
    for model in (p._main_model, p._cheap_model):
        body = {
            "model": model,
            "instructions": "Use the image_generation tool to create the requested image.",
            "input": [{"role": "user",
                       "content": "A simple test image: a single red circle centered on a white background."}],
            "store": False,
            "stream": True,
            "tools": [{"type": "image_generation"}],
        }
        print(f"\n=== model={model}  url={url} ===")
        events: Counter = Counter()
        img_b64 = None
        err = None
        try:
            async with asyncio.timeout(120):
                async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=30)) as http:
                    async with http.stream("POST", url, headers=headers, json=body) as resp:
                        print("status:", resp.status_code)
                        if resp.status_code >= 400:
                            await resp.aread()
                            print("error body:", resp.text[:600])
                            continue
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
                                t = ev.get("type", "")
                                events[t] += 1
                                # final response carries output items
                                if t in ("response.completed", "response.done"):
                                    for item in ev.get("response", {}).get("output", []):
                                        if item.get("type") == "image_generation_call" and item.get("result"):
                                            img_b64 = item["result"]
                                # streamed partial/final image
                                for k in ("result", "partial_image_b64", "image_b64", "b64_json"):
                                    if isinstance(ev.get(k), str) and len(ev[k]) > 100:
                                        img_b64 = ev[k]
        except Exception as exc:  # noqa: BLE001
            err = repr(exc)
        print("event types:", dict(events))
        if err:
            print("exception:", err)
        if img_b64:
            out = Path("images/_probe/codex-test.png")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(base64.b64decode(img_b64))
            print(f"*** IMAGE RETURNED — {out.stat().st_size} bytes -> {out} ***")
        else:
            print("no image bytes in the stream")


if __name__ == "__main__":
    asyncio.run(main())
