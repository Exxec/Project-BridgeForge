"""Is a pull request documentation only? (ROADMAP-3 96.5 C3)

Reads the changed paths, one per line, on stdin and prints `docs_only=true` or `docs_only=false`, the line GitHub Actions
reads from $GITHUB_OUTPUT. A change is documentation only when every path is a Markdown file outside the folders whose files
the package or the tests read as input. A documentation-only pull request runs only the test modules in
`tests/doc_tests.json`; `--doc-tests` prints them for `python -m unittest`. A push to main always runs everything.

The CI scope job runs this on the runner's own Python 3, before any setup, so it uses nothing newer than 3.10.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
DOC_TESTS = ROOT / "tests" / "doc_tests.json"
# Markdown under these folders is input, not documentation: package data (bridgeforge/kit_resources/TRIAL_GUIDE.md),
# test fixtures, the probe mod, tool notes and the CI configuration.
CODE_FOLDERS = ("bridgeforge", "tests", "probe-mod", "tools", ".github")


def docs_only(paths: list[str]) -> bool:
    """True when there is at least one path and every one is a Markdown file outside CODE_FOLDERS."""
    names = [p.strip().replace("\\", "/") for p in paths if p.strip()]
    if not names:
        return False
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".md" or path.parts[0] in CODE_FOLDERS:
            return False
    return True


def doc_test_modules() -> list[str]:
    return [f"tests.{module}" for module in json.loads(DOC_TESTS.read_text(encoding="utf-8"))["modules"]]


def main(argv: list[str]) -> int:
    if argv == ["--doc-tests"]:
        print(" ".join(doc_test_modules()))
        return 0
    if argv:
        print("usage: python tools/ci-scope.py [--doc-tests] < changed-paths", file=sys.stderr)
        return 2
    print("docs_only=" + ("true" if docs_only(sys.stdin.read().splitlines()) else "false"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
