"""Regenerate the generated files (ROADMAP-3 item 80.1) and clear the merge driver marker.

Runs `python -m tests.test_cli_golden --write` (tests/cli_help_golden.json) and `python -m bridgeforge docs-index`
(docs/COMMANDS.md, docs/CHECKS.md) from the repository root. Use after a merge or rebase that touched them; see
tools/merge-regen.py. Review the diff before committing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ("tests/cli_help_golden.json", "docs/COMMANDS.md", "docs/CHECKS.md")
STEPS = (
    ("-m", "tests.test_cli_golden", "--write"),
    ("-m", "bridgeforge", "docs-index"),
)


def regenerate(root: Path = ROOT, python: str = sys.executable) -> int:
    for step in STEPS:
        code = subprocess.run([python, *step], cwd=root).returncode
        if code != 0:
            print(f"regen-generated: `python {' '.join(step)}` failed with {code}", file=sys.stderr)
            return code
    git_dir = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], capture_output=True, text=True, cwd=root)
    if git_dir.returncode == 0:
        marker = Path(git_dir.stdout.strip()) / "bf-regen-needed"
        if marker.exists():
            marker.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(regenerate())
