#!/usr/bin/env sh
# The Construct one-line installer (the AgentPost entry pattern):
#   curl -fsSL https://raw.githubusercontent.com/5000Stadia/construct/main/scripts/install.sh | sh
#
# Clone-anchored by design: the Construct's worlds, save-games, and config all
# live under its own checkout (worlds/ is the world library), so the installer
# keeps ONE home checkout and puts a `construct` command on PATH that always
# runs from it — play from any directory.
set -eu

python=${PYTHON:-python3}
home_dir=${CONSTRUCT_INSTALL_DIR:-"$HOME/.local/share/construct"}
bin_dir=${CONSTRUCT_BIN_DIR:-"$HOME/.local/bin"}
repo=${CONSTRUCT_REPO:-"https://github.com/5000Stadia/construct.git"}
ref=${CONSTRUCT_REF:-main}

if ! command -v "$python" >/dev/null 2>&1; then
    printf 'construct: Python 3.11+ is required; %s was not found\n' "$python" >&2
    exit 1
fi
if ! command -v git >/dev/null 2>&1; then
    printf 'construct: git is required\n' >&2
    exit 1
fi

if [ -d "$home_dir/.git" ]; then
    git -C "$home_dir" fetch --quiet origin "$ref"
    git -C "$home_dir" checkout --quiet "$ref"
    git -C "$home_dir" pull --quiet --ff-only origin "$ref"
else
    git clone --quiet --branch "$ref" "$repo" "$home_dir"
fi

if [ ! -x "$home_dir/.venv/bin/python" ]; then
    "$python" -m venv "$home_dir/.venv"
fi
"$home_dir/.venv/bin/python" -m pip install --quiet --upgrade pip
"$home_dir/.venv/bin/python" -m pip install --quiet -e "$home_dir"

mkdir -p "$bin_dir"
cat > "$bin_dir/construct" <<WRAP
#!/bin/sh
# The Construct runs from its home checkout (worlds live there).
cd "$home_dir" && exec "$home_dir/.venv/bin/construct" "\$@"
WRAP
chmod +x "$bin_dir/construct"

printf 'The Construct installed: %s\n' "$bin_dir/construct"
printf 'World library + saves live in: %s/worlds\n' "$home_dir"
printf 'Start playing:  construct start\n'
case ":${PATH:-}:" in
    *":$bin_dir:"*) ;;
    *) printf 'Add %s to your PATH first.\n' "$bin_dir" ;;
esac
