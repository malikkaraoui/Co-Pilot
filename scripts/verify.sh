#!/usr/bin/env bash
# Verification complete : lint + tests Python + tests extension.
# Usage : bash scripts/verify.sh
set -euo pipefail

PY_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PY_BIN=".venv/bin/python"
fi

echo "=== Guard Vitest ESM ==="
if [ -f vitest.config.js ]; then
  echo "ERREUR: vitest.config.js (CJS) detecte -- utiliser vitest.config.mjs (ESM)"
  exit 1
fi
echo "OK (vitest.config.mjs uniquement)"

echo ""
echo "=== Ruff lint ==="
"$PY_BIN" -m ruff check .

echo ""
echo "=== Tests Python ==="
"$PY_BIN" -m pytest tests/ -x -q --tb=short

echo ""
echo "=== Tests extension ==="
npm run test:extension

echo ""
echo "=== Tout est vert ==="
