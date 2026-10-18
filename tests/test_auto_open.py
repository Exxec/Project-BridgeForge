from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge import scan_registry
from bridgeforge.auto_open import auto_open, render
from bridgeforge.cli import main
from tests.support import resolved_temp_dir

AUTO_ID = "hullmod-instance-state"  # tier auto, no fixer needed to be real: only the tier matters here


def _workspace(queue: Path, name: str, classification: str = "REVIEW", finding_id: str = AUTO_ID, *, registered: bool = True) -> Path:
    workspace = queue / name
    (workspace / "working").mkdir(parents=True)
    (workspace / "working" / "mod_info.json").write_text('{"id": "%s"}' % name.lower(), encoding="utf-8")
    scan = workspace / "reports" / "scan-1"
    scan.mkdir(parents=True)
    finding = {"id": finding_id, "classification": classification, "file": "data/x.java", "evidence": ["e"]}
    scan_file = scan / "bridgeforge.compat.json"
    scan_file.write_text(json.dumps({"findings": [finding]}), encoding="utf-8")
    if registered:  # a CURRENT scan: the registry holds the fingerprint of working/ as it is now
        scan_registry.register(workspace, scan_file, workspace / "working", {})
    return workspace


def _revived(workspace: Path, approved: list[str] | None = None) -> None:
    revive = workspace / "reports" / "revive"
    revive.mkdir(parents=True)
    (revive / "REVIVE.json").write_text(json.dumps({"status": "FIXES_PENDING", "approved": approved or []}), encoding="utf-8")


def _packet(workspace: Path, fixer: dict) -> None:
    folder = workspace / "reports" / "escalations"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "p.json").write_text(json.dumps({"finding": AUTO_ID, "fixer": fixer}), encoding="utf-8")


def _reasons(result: dict) -> dict[str, str]:
    return {name: rows[0]["reason"] for name, rows in result["mods"].items()}


class AutoOpenTests(unittest.TestCase):
    def _queue(self, root: Path) -> Path:
        from bridgeforge.automation import tier_for

        self.assertEqual(tier_for(AUTO_ID), "auto")
        queue = root / "In operation"
        _workspace(queue, "Never")
        approval = _workspace(queue, "Approval")
        _revived(approval)
        refused = _workspace(queue, "Refused")
        _revived(refused)
        _packet(refused, {"state": "FIXER_REFUSED", "reason": "field is read in a nested class"})
        stale = _workspace(queue, "Stale")
        _revived(stale)
        (stale / "working" / "mod_info.json").write_text('{"id": "stale", "changed": "after the scan"}', encoding="utf-8")
        unexplained = _workspace(queue, "Odd", classification="SAFE")
        _revived(unexplained)
        approved_by_run = _workspace(queue, "RunApproved")
        _revived(approved_by_run, approved=[AUTO_ID])
        legacy = _workspace(queue, "Legacy", registered=False)  # a scan folder from before the registry
        _revived(legacy)
        clean = _workspace(queue, "Clean", finding_id="json-hash-comment")  # not auto-tier open work: tier none
        _revived(clean)
        return queue

    def test_one_reason_per_case(self):
        with resolved_temp_dir() as root:
            result = auto_open(self._queue(root))
        self.assertEqual(_reasons(result), {"Never": "NEVER_REVIVED", "Approval": "NOT_APPROVED", "Refused": "FIXER_REFUSED",
                                            "Stale": "STALE_SCAN", "Odd": "UNEXPLAINED", "RunApproved": "UNEXPLAINED",
                                            "Legacy": "UNKNOWN_SCAN"})
        self.assertEqual(result["totals"], {"NOT_APPROVED": 1, "FIXER_REFUSED": 1, "NEVER_REVIVED": 1, "STALE_SCAN": 1,
                                            "UNKNOWN_SCAN": 1, "INCOMPLETE_SCAN": 0, "UNEXPLAINED": 2})
        legacy = result["mods"]["Legacy"][0]
        self.assertIn("would otherwise be NOT_APPROVED", legacy["detail"])
        self.assertEqual(result["mods"]["Stale"][0]["scan_state"], "STALE")
        refused = result["mods"]["Refused"][0]
        self.assertEqual(refused["detail"], "field is read in a nested class")
        self.assertEqual(result["by_finding"][AUTO_ID]["UNEXPLAINED"], 2)

    def test_standing_approval_and_ledger_refusal(self):
        with resolved_temp_dir() as root:
            queue = self._queue(root)
            (queue / "AUTOMATION_POLICY.json").write_text(json.dumps({"approved_fixers": {AUTO_ID: {"reason": "r"}}}), encoding="utf-8")
            ledger = queue / "Approval" / "reports" / "escalations" / "ledger.jsonl"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(json.dumps({"finding": AUTO_ID, "state": "FIXER_REFUSED", "reason": "newest wins"}) + "\n", encoding="utf-8")
            reasons = _reasons(auto_open(queue))
        self.assertEqual(reasons["Approval"], "FIXER_REFUSED")   # the ledger refusal beats the missing approval
        self.assertEqual(reasons["Never"], "NEVER_REVIVED")
        self.assertEqual(reasons["Odd"], "UNEXPLAINED")

    def test_render_lists_unexplained_and_skips_tiers_other_than_auto(self):
        with resolved_temp_dir() as root:
            queue = self._queue(root)
            result = auto_open(queue)
            text = render(result)
        self.assertIn("| `hullmod-instance-state` |", text)
        self.assertIn("UNEXPLAINED is an automation bug: Odd, RunApproved", text)
        self.assertNotIn("Clean", result["mods"])

    def test_cli(self):
        with resolved_temp_dir() as root:
            queue = self._queue(root)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["auto-open", str(queue), "--json"]), 0)
                self.assertEqual(main(["auto-open", str(root / "missing")]), 2)
        self.assertEqual(json.loads(out.getvalue())["totals"]["NEVER_REVIVED"], 1)
        self.assertIn("] Approval:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
