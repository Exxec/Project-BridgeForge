"""ROADMAP 70 H1.5: accepted-finding baselines are stamped with the mod version and go stale when it changes."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.baseline import accept_findings, load_baseline_keys
from bridgeforge.baseline_audit import accept_workspace, audit_queue, audit_workspace, stamp_baseline, summary
from bridgeforge.cli import main
from tests.support import resolved_temp_dir


def _workspace(queue: Path, name: str, version: str, baseline: dict | None = None) -> Path:
    working = queue / name / "working"
    (working / "reports").mkdir(parents=True)
    (working / "mod_info.json").write_text(json.dumps({"id": name.lower(), "version": version}), encoding="utf-8")
    if baseline is not None:
        (working / "reports" / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    return queue / name


class BaselineAuditTests(unittest.TestCase):
    def test_a_version_change_makes_a_stamped_baseline_stale_and_a_reason_renews_it(self) -> None:
        """Zorg18: its port-bug findings sat accepted while bf.7 shipped without the fixes for them."""
        with resolved_temp_dir() as queue:
            ws = _workspace(queue, "Zorg", "V18+bf.7", {"findings": ["procgen-call-argument-suspect|ZorgGen|method:generate"]})
            self.assertEqual(audit_workspace(ws)["status"], "UNSTAMPED")  # a legacy baseline has no stamp
            stamp_baseline(ws / "working" / "reports" / "baseline.json", ws / "working", "port bugs, owner accepted", "2026-10-01")
            row = audit_workspace(ws)
            self.assertEqual((row["status"], row["stamped_version"], row["without_reason"]), ("OK", "V18+bf.7", 0))
            (ws / "working" / "mod_info.json").write_text(json.dumps({"id": "zorg", "version": "V18+bf.8"}), encoding="utf-8")
            row = audit_workspace(ws)
            self.assertEqual((row["status"], row["stamped_version"], row["current_version"]), ("STALE_VERSION", "V18+bf.7", "V18+bf.8"))
            with self.assertRaises(ValueError):
                accept_workspace(ws, "   ")  # a written reason is required
            self.assertEqual(accept_workspace(ws, "re-read at bf.8: still a stale scanner match")["status"], "OK")
            payload = json.loads((ws / "working" / "reports" / "baseline.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["stamp"]["version"], "V18+bf.8")
            self.assertEqual(payload["reasons"]["procgen-call-argument-suspect|ZorgGen|method:generate"], "port bugs, owner accepted")  # kept

    def test_the_old_findings_format_still_loads_and_no_baseline_is_its_own_status(self) -> None:
        with resolved_temp_dir() as queue:
            ws = _workspace(queue, "A", "1.0", {"findings": ["k1", "k2"]})
            stamp_baseline(ws / "working" / "reports" / "baseline.json", ws / "working")
            self.assertEqual(load_baseline_keys(ws / "working" / "reports" / "baseline.json"), {"k1", "k2"})
            bare = _workspace(queue, "B", "1.0")
            self.assertEqual(audit_workspace(bare)["status"], "NO_BASELINE")
            self.assertEqual(summary(audit_queue(queue)), {"OK": 1, "STALE_VERSION": 0, "UNSTAMPED": 0, "NO_BASELINE": 1})

    def test_accepting_findings_stamps_them_with_a_reason_and_keeps_earlier_keys(self) -> None:
        with resolved_temp_dir() as queue:
            ws = _workspace(queue, "A", "2.0", {"findings": ["old"]})
            path = accept_findings(ws / "working", ["new"], "owner ruling 2026-10-12")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["findings"], ["new", "old"])
            self.assertEqual(payload["stamp"]["version"], "2.0")
            self.assertEqual(payload["reasons"], {"new": "owner ruling 2026-10-12", "old": "owner ruling 2026-10-12"})

    def test_the_commands_list_and_stamp_legacy_baselines(self) -> None:
        with resolved_temp_dir() as queue:
            _workspace(queue, "Legacy", "1.0", {"findings": ["x"]})
            _workspace(queue, "Fresh", "1.0", {"findings": ["y"], "stamp": {"version": "0.9", "date": "2026-01-01"}})
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["baseline-audit", "--queue", str(queue), "--json"]), 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["summary"], {"OK": 0, "STALE_VERSION": 1, "UNSTAMPED": 1, "NO_BASELINE": 0})
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["baseline-accept", "--all-unstamped", "--queue", str(queue), "--reason", "legacy start of the clock"]), 0)
                self.assertEqual(main(["baseline-accept", "--queue", str(queue), "--reason", "r"]), 2)  # needs a workspace or --all-unstamped
            self.assertEqual(audit_workspace(queue / "Legacy")["status"], "OK")
            self.assertEqual(audit_workspace(queue / "Fresh")["status"], "STALE_VERSION")  # not touched by --all-unstamped


class ArchiveGateBaselineTests(unittest.TestCase):
    def _gate(self, ws: Path) -> dict:
        from unittest import mock

        from bridgeforge import live_trust

        with mock.patch.object(live_trust, "audit_shipped", return_value={"status": "PASS", "unexplained": []}), \
                mock.patch.object(live_trust, "live_status", return_value={"status": "CURRENT"}):
            return live_trust.archive_gate(ws)

    def test_a_stale_or_unstamped_baseline_blocks_archiving_until_renewed_or_waived_with_a_reason(self) -> None:
        with resolved_temp_dir() as queue:
            ws = _workspace(queue, "Zorg", "V18+bf.8", {"findings": ["k"]})
            blocked = self._gate(ws)
            self.assertFalse(blocked["allowed"])
            self.assertIn("baseline UNSTAMPED", blocked["problems"][0])
            stamp_baseline(ws / "working" / "reports" / "baseline.json", ws / "working", "accepted")
            self.assertTrue(self._gate(ws)["allowed"])
            (ws / "working" / "mod_info.json").write_text(json.dumps({"id": "zorg", "version": "V18+bf.9"}), encoding="utf-8")
            stale = self._gate(ws)
            self.assertFalse(stale["allowed"])
            self.assertIn("baseline STALE_VERSION", stale["problems"][0])
            (ws / "reports").mkdir(exist_ok=True)
            (ws / "reports" / "SHIPPED_CHANGES.json").write_text(json.dumps({"baseline": "  "}), encoding="utf-8")
            self.assertFalse(self._gate(ws)["allowed"])  # a blank reason is no reason
            (ws / "reports" / "SHIPPED_CHANGES.json").write_text(json.dumps({"baseline": "re-read at bf.9, unchanged findings"}), encoding="utf-8")
            self.assertTrue(self._gate(ws)["allowed"])

    def test_a_workspace_with_no_baseline_is_not_blocked(self) -> None:
        with resolved_temp_dir() as queue:
            self.assertTrue(self._gate(_workspace(queue, "Plain", "1.0"))["allowed"])

if __name__ == "__main__":
    unittest.main()
