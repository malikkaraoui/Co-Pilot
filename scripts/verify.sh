#!/usr/bin/env bash
# Verification complete : lint + tests Python + tests extension.
# Usage : bash scripts/verify.sh
set -euo pipefail

echo "=== Guard Vitest ESM ==="
if [ -f vitest.config.js ]; then
  echo "ERREUR: vitest.config.js (CJS) detecte -- utiliser vitest.config.mjs (ESM)"
  exit 1
fi
echo "OK (vitest.config.mjs uniquement)"

echo ""
echo "=== Ruff lint ==="
python -m ruff check .

echo ""
echo "=== Tests Python ==="
python -m pytest tests/ -x -q --tb=short

echo ""
echo "=== Tests extension ==="
npm run test:extension

echo ""
echo "=== Tout est vert ==="
