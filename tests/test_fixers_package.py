"""B2 pins the pre-split facade and registry order from main at fcf9bf97."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from bridgeforge import fixers

BASELINE = json.loads(Path(__file__).with_name("fixers_api_baseline.json").read_text(encoding="utf-8"))


class FixersPackageContractTests(unittest.TestCase):
    def test_supported_findings_keep_the_pre_split_order(self) -> None:
        self.assertEqual(list(fixers.SUPPORTED_FINDINGS), BASELINE["supported"])

    def test_dispatch_keeps_the_pre_split_order_including_retired_handler(self) -> None:
        self.assertEqual(list(fixers._FIXER_FUNCS), BASELINE["dispatch"])
        self.assertTrue(all(callable(handler) for handler in fixers._FIXER_FUNCS.values()))

    def test_facade_preserves_every_pre_split_defined_name(self) -> None:
        self.assertEqual([name for name in BASELINE["exports"] if not hasattr(fixers, name)], [])


if __name__ == "__main__":
    unittest.main()
