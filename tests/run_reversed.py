"""Run every test case in reverse discovery order, to expose order dependence (ROADMAP 70 H2.5; used by the weekly workflow)."""
from __future__ import annotations

import sys
import unittest
from collections.abc import Iterator


def flatten(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main() -> int:
    loaded = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(reversed(list(flatten(loaded)))))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
