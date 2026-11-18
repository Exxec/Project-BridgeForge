"""Print the test modules a push runs, one per line (ROADMAP-3 96.5 C5): the cross-cutting tests, the tests named after a
changed module and the tests that import one. The rule is `bridgeforge.merge_train.test_modules_for`, shared with merge-train.

Usage: python tools/prepush-select.py CHANGED_PATH...
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(ROOT))
    from bridgeforge.merge_train import select_test_modules

    modules, notes = select_test_modules(argv, ROOT / "tests")
    for note in notes:
        print(f"pre-push: {note}", file=sys.stderr)
    for module in modules:
        print(module)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
