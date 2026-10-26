"""Run every test case in reverse discovery order, to expose order dependence (ROADMAP 70 H2.5; used by the weekly workflow)."""
from __future__ import annotations

import sys
import unittest
from collections.abc import Iterator
from pathlib import Path


def flatten(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main() -> int:
    # Discover as CI does (`unittest discover -s tests`): tests/ is not a package, so top_level_dir="." refused it
    # ("Start directory is not importable"; every weekly run until 2026-10-26). The repo root stays importable for the
    # tests' own `from tests.support import ...`.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    loaded = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(reversed(list(flatten(loaded)))))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
