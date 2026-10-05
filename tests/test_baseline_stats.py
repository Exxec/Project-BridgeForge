"""baseline-stats (ROADMAP 48): checks ranked by accepted-as-harmless findings."""
from __future__ import annotations

import json
import unittest

from bridgeforge.baseline_stats import baseline_stats, render
from tests.support import resolved_temp_dir


class BaselineStatsTests(unittest.TestCase):
    def test_counts_accepted_keys_per_check_across_workspaces(self) -> None:
        with resolved_temp_dir() as root:
            for name, keys in (("A", ["x|f|e", "x|g|e", "y|f|e"]), ("B", ["x|h|e"]), ("C", [])):
                reports = root / name / "working" / "reports"
                reports.mkdir(parents=True)
                (reports / "baseline.json").write_text(json.dumps({"findings": keys}), encoding="utf-8")
            (root / "D" / "working").mkdir(parents=True)  # no baseline
            result = baseline_stats(root)
        self.assertEqual(result["workspaces_with_baseline"], 3)
        self.assertEqual([(r["id"], r["accepted"], r["mods"]) for r in result["checks"]], [("x", 3, 2), ("y", 1, 1)])
        self.assertIn("| `x` | 3 | 2 | A, B |", render(result))


if __name__ == "__main__":
    unittest.main()
