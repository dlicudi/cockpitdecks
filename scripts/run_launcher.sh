#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x "dist/cockpitdecks-launcher" ]]; then
  echo "[run] launcher not found at $ROOT_DIR/dist/cockpitdecks-launcher"
  echo "[run] build it first with scripts/build_launcher.sh"
  exit 1
fi

exec "$ROOT_DIR/dist/cockpitdecks-launcher"
