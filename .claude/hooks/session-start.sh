#!/bin/bash
# SessionStart hook for Claude Code on the web.
# Installs Python dependencies so tests (pytest) and the linter (ruff) work, and
# makes the src/ package importable for the session. Idempotent and safe to
# re-run; the container state is cached after this completes.
set -euo pipefail

# Only run in remote (Claude Code on the web) sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Install runtime + dev dependencies (includes pytest and ruff).
python -m pip install --quiet --disable-pip-version-check -r requirements.txt

# Make the src/ layout importable for tests, linting, and the `upr` CLI.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export PYTHONPATH="src"' >> "$CLAUDE_ENV_FILE"
fi

echo "UPR session ready: dependencies installed (pytest + ruff)."
