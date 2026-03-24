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
if command -v brew &>/dev/null; then
  BREW_PREFIX="$(brew --prefix)"
  export DYLD_LIBRARY_PATH="$BREW_PREFIX/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
fi

cd "$HOME"
exec "$VENV/bin/python" -m cockpitdecks.start "$@"
