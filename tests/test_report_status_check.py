"""96.5 A9: the pre-push report check uses report_status's list of statuses, not a copy of its own."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from bridgeforge.report_status import REPORT_STATUSES
from tests.support import resolved_temp_dir

ROOT = Path(__file__).resolve().parents[1]


def _check_module():
    spec = importlib.util.spec_from_file_location("report_status_check", ROOT / "tools" / "report-status-check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(root: Path, name: str, text: str) -> Path:
    path = root / name / "working" / "reports" / "REVIVAL_REPORT.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(text.encode("utf-8"))
    return path


class ReportStatusCheckTests(unittest.TestCase):
    def test_every_known_status_passes_and_a_report_without_one_fails(self) -> None:
        check = _check_module()
        with resolved_temp_dir() as root:
            for status in sorted(REPORT_STATUSES):
                _report(root, status, f"# Revival report\n\n**{status}**\n")
            self.assertEqual(check.reports_without_status(root), [])
            bad = _report(root, "none", "# Revival report\n\nREADYISH, not a status\n")
            self.assertEqual(check.reports_without_status(root), [bad])
            self.assertEqual(check.main([str(root)]), 1)

    def test_a_closed_not_revivable_report_passes(self) -> None:
        # The script's old list lacked NOT_REVIVABLE, which `close --status` writes (95.15).
        self.assertIn("NOT_REVIVABLE", REPORT_STATUSES)
        with resolved_temp_dir() as root:
            _report(root, "closed", "# Revival report\n\nNOT_REVIVABLE\n")
            self.assertEqual(_check_module().main([str(root)]), 0)

    def test_the_prepush_script_has_no_status_list_of_its_own(self) -> None:
        script = (ROOT / "tools" / "prepush-check.ps1").read_text(encoding="utf-8")
        self.assertIn("report-status-check.py", script)
        for status in ("READY_WITH_REVIEW_ITEMS", "ESCALATION_REQUIRED", "LIVE_VALIDATED"):
            self.assertNotIn(status, script)

    def test_the_retired_tools_scripts_are_gone(self) -> None:
        # master_log.py (item 65) and archive's per-archive readme zips replaced them.
        for name in ("build-done-master-log.ps1", "copy-done-archives-with-readme.ps1"):
            self.assertFalse((ROOT / "tools" / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
