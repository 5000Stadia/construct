"""Parse the curated game-type taxonomy (docs/design/GAME-TYPE-TAXONOMY.md) into a
data module the engine loads (construct/play_styles_data.py). Re-run whenever the
taxonomy MD changes. The MD is the human source of truth; the .py is generated.

    python scripts/build_play_styles.py
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path("docs/design/GAME-TYPE-TAXONOMY.md")
OUT = Path("construct/play_styles_data.py")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s


def main() -> int:
    lines = SRC.read_text().splitlines()
    cards: dict[str, dict] = {}
    family = ""
    name = None
    for ln in lines:
        m = re.match(r"^##\s*Family\s*\d+\s*[—-]\s*(.+)$", ln.strip())
        if m:
            family = m.group(1).strip()
            continue
        m = re.match(r"^-\s*\*\*Name:\*\*\s*(.+)$", ln.strip())
        if m:
            name = m.group(1).strip()
            continue
        m = re.match(r"^-\s*\*\*Directive:\*\*\s*`?(.+?)`?\s*$", ln.strip())
        if m and name:
            directive = m.group(1).strip().strip("`").strip()
            key = _slug(name)
            cards[key] = {"name": name, "family": family, "directive": directive}
            name = None
    if len(cards) < 150:
        raise SystemExit(f"parsed only {len(cards)} cards — taxonomy format changed?")

    header = ('"""Game-type cards — GENERATED from docs/design/GAME-TYPE-TAXONOMY.md\n'
              "by scripts/build_play_styles.py. Do not hand-edit; edit the taxonomy MD\n"
              'and re-run. Keyed by a slug of the card name."""\n\n'
              "STYLE_CARDS = {\n")
    body = []
    for key, c in cards.items():
        body.append(f"    {key!r}: {{\n"
                    f"        'name': {c['name']!r},\n"
                    f"        'family': {c['family']!r},\n"
                    f"        'directive': {c['directive']!r},\n"
                    f"    }},\n")
    OUT.write_text(header + "".join(body) + "}\n")
    print(f"wrote {len(cards)} cards → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
