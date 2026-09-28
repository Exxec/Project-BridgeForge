"""`bridgeforge check-impact` (ROADMAP P15 31.10): one finding's change across the queue after a scanner fix."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from bridgeforge.check_impact import check_impact
from tests.support import resolved_temp_dir


def _ws(queue: Path, name: str, before: int) -> None:
    (queue / name / "working").mkdir(parents=True)
    (queue / name / "working" / "mod_info.json").write_text("{}", encoding="utf-8")
    if before:
        (queue / name / "reports" / "escalations").mkdir(parents=True)
        (queue / name / "reports" / "escalations" / "x-check--mod.json").write_text(json.dumps({"findings": [{}] * before}), encoding="utf-8")


class CheckImpactTests(unittest.TestCase):
    def test_cleared_reduced_unchanged_and_new(self) -> None:
        now = {"A": 0, "B": 1, "C": 2, "D": 1}
        with resolved_temp_dir() as queue:
            for name, before in (("A", 2), ("B", 2), ("C", 2), ("D", 0)):
                _ws(queue, name, before)
            scan = lambda working: [SimpleNamespace(id="x-check")] * now[working.parent.name]  # noqa: E731
            only = check_impact(queue, "x-check", quiet=True, scan=scan)
            everything = check_impact(queue, "x-check", all_workspaces=True, quiet=True, scan=scan)
        self.assertEqual({r["workspace"]: r["verdict"] for r in only["mods"]}, {"A": "CLEARED", "B": "REDUCED", "C": "UNCHANGED"})
        self.assertEqual(everything["counts"]["NEW"], 1)


if __name__ == "__main__":
    unittest.main()
