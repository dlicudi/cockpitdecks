#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT_DIR/.venv"

if [[ ! -d "$VENV" ]]; then
  echo "[run] venv not found at $VENV"
  echo "[run] create it first: python3 -m venv $VENV && $VENV/bin/pip install -e '.[development,streamdeck,loupedeck,weather]'"
  exit 1
fi

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
