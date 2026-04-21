#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT_DIR/.venv"

if ! command -v uv &>/dev/null; then
  echo "[run] uv not found — install it: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

echo "[run] syncing dependencies..."
uv sync --all-extras --project "$ROOT_DIR" --quiet

# Ensure libhidapi is visible for StreamDeck USB access.
BREW_BIN=""
if command -v brew &>/dev/null; then
  BREW_BIN="$(command -v brew)"
elif [[ -x /opt/homebrew/bin/brew ]]; then
  BREW_BIN="/opt/homebrew/bin/brew"
elif [[ -x /usr/local/bin/brew ]]; then
  BREW_BIN="/usr/local/bin/brew"
fi

if [[ -n "$BREW_BIN" ]]; then
  BREW_PREFIX="$("$BREW_BIN" --prefix)"
  export PATH="$BREW_PREFIX/bin:$BREW_PREFIX/sbin:$PATH"
  export HOMEBREW_PREFIX="$BREW_PREFIX"
  export DYLD_LIBRARY_PATH="$BREW_PREFIX/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
  export DYLD_FALLBACK_LIBRARY_PATH="$BREW_PREFIX/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
fi

cd "$HOME"
exec "$VENV/bin/python" -m cockpitdecks.start "$@"
