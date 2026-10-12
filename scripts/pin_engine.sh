#!/usr/bin/env bash
# Install the pattern-buffer engine at the commit named in engine.pin into .venv.
# Live bots load whatever is installed here, so the engine only moves when this runs.
# To bump: run the full suite against the new pattern-buffer commit, put its full sha
# in engine.pin (one line, committed with the suite result in the message), then run this.
set -euo pipefail
cd "$(dirname "$0")/.."
PB_REPO="${PB_REPO:-$HOME/pattern-buffer}"
SHA="$(tr -d '[:space:]' < engine.pin)"
SRC="$(mktemp -d)"
trap 'rm -rf "$SRC"' EXIT
git -C "$PB_REPO" archive "$SHA" | tar -x -C "$SRC"     # the exact commit, nothing uncommitted
.venv/bin/pip uninstall -y -q patternbuffer pbuffer 2>/dev/null || true
.venv/bin/pip install -q --no-deps "$SRC"
.venv/bin/python -c "import patternbuffer, sys; print('engine:', patternbuffer.__file__)"
echo "pinned pattern-buffer ${SHA}"
