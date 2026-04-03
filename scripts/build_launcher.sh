#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/pyinstaller" ]]; then
  PYINSTALLER=".venv/bin/pyinstaller"
elif [[ -x ".venv/Scripts/pyinstaller.exe" ]]; then
  PYINSTALLER=".venv/Scripts/pyinstaller.exe"
else
  echo "[build] pyinstaller not found in .venv"
  exit 1
fi

echo "[build] cleaning cockpitdecks build artifacts"
python -c "import shutil, os; [shutil.rmtree(d) for d in ('build','dist') if os.path.exists(d)]"

echo "[build] building cockpitdecks"
"$PYINSTALLER" --clean cockpitdecks.spec

if [[ -f "$ROOT_DIR/dist/cockpitdecks.exe" ]]; then
  echo "Build complete: $ROOT_DIR/dist/cockpitdecks.exe"
else
  echo "Build complete: $ROOT_DIR/dist/cockpitdecks"
fi
