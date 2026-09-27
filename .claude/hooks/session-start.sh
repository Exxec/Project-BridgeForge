#!/bin/bash
# Claude Code on the web: install what the test suite and linter need.
# Tests run from the checkout (python -m bridgeforge.test_guard), so the package itself is not installed.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore \
  "psutil>=5.9" "py7zr>=1.0" ruff coverage
