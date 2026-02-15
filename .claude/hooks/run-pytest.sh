#!/bin/bash
# Hook Claude Code : lance pytest apres chaque edit/write de fichier Python.
# Ne bloque pas l'agent (exit 0) mais affiche le resultat.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Ne lancer que pour les fichiers Python du projet (pas .venv, pas node_modules)
if [[ "$FILE_PATH" == *.py ]] && [[ "$FILE_PATH" != *".venv"* ]] && [[ "$FILE_PATH" != *"node_modules"* ]]; then
  cd "$CLAUDE_PROJECT_DIR" || exit 0

  # Lint rapide du fichier modifie
  .venv/bin/python -m ruff check "$FILE_PATH" --fix --quiet 2>/dev/null

  # Run tests (quiet, stop on first failure)
  .venv/bin/python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
fi

exit 0
