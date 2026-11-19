#!/usr/bin/env bash
# Pre-commit checks for a BridgeForge change, run from the checkout root (bridgeforge-pr skill, step 3).
# Fast (under a minute); the full suite still has to run before the commit.
# Usage: bash .claude/skills/bridgeforge-pr/scripts/checks.sh [path-to-python]
set -u
PY="${1:-.venv/Scripts/python.exe}"
[ -x "$PY" ] || PY="$(git rev-parse --show-toplevel 2>/dev/null)/.venv/Scripts/python.exe"
failed=0
step() { printf '\n== %s\n' "$1"; }

step "ruff"
RUFF_PIN="$(sed -n 's/^required-version = "==\(.*\)"$/\1/p' pyproject.toml)"
uvx "ruff@${RUFF_PIN:-latest}" check . || failed=1

step "roadmap-lint"
"$PY" -m bridgeforge roadmap-lint || failed=1

step "docs index (regenerates docs/CHECKS.md and docs/COMMANDS.md when stale)"
"$PY" -m bridgeforge docs-index || failed=1

step "generated files and release notes"
"$PY" -m unittest tests.test_cli_golden tests.test_checks_index tests.test_roadmap_lint tests.test_release_notes 2>&1 | tail -3
[ "${PIPESTATUS[0]}" -eq 0 ] || failed=1

step "changes"
git status --short
if git status --short | grep -q '^.. bridgeforge/' && ! git status --short | grep -q 'changelog.d/'; then
    echo "NOTE: code changed but no changelog.d/ fragment is staged or new"
fi

if [ "$failed" -ne 0 ]; then
    echo; echo "CHECKS FAILED"; exit 1
fi
echo; echo "checks passed; now run the full suite (step 4)"
