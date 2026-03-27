#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[build] cleaning cockpitdecks build artifacts"
python3 -c "import shutil, os; [shutil.rmtree(d) for d in ('build','dist') if os.path.exists(d)]"

echo "[build] building cockpitdecks"
.venv/bin/pyinstaller --clean cockpitdecks.spec

echo "Build complete: $ROOT_DIR/dist/cockpitdecks"
