from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.revival_audit import REQUIRED_VALIDATIONS, audit_revival


def _report(status: str = "READY") -> str:
    lines = ["# Revival Report", "", "## Validation", ""]
    lines.extend(f"- {label} — PASS" for label in REQUIRED_VALIDATIONS)
    lines.extend(["", "## Status", "", f"**{status}**", ""])
    return "\n".join(lines)


class RevivalAuditTests(unittest.TestCase):
    def _candidate(self, root: Path, report: str | None = None) -> Path:
        candidate = root / "Candidate"
        reports = candidate / "reports"
        reports.mkdir(parents=True)
        (reports / "REVIVAL_PLAN.md").write_text("# Plan\n", encoding="utf-8")
        (reports / "REVIVAL_REPORT.md").write_text(report or _report(), encoding="utf-8")
        (candidate / "mod_info.json").write_text('{"id":"fixture"}\n', encoding="utf-8")
        return candidate

    def test_exact_wrapped_archive_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = self._candidate(root)
            archive = root / "Candidate.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for path in candidate.rglob("*"):
                    if path.is_file():
                        bundle.write(path, Path("Candidate") / path.relative_to(candidate))
            result = audit_revival(candidate, archive)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["package_attestation"]["exact_match"])
            self.assertEqual(len(result["package_attestation"]["archive_sha256"]), 64)

    def test_reports_missing_evidence_and_archive_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = self._candidate(root, "# Report\n\n**READY**\n")
            archive = root / "Candidate.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Candidate/mod_info.json", "different")
            result = audit_revival(candidate, archive)
            ids = [item["id"] for item in result["issues"]]
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("validation-stage-missing", ids)
            self.assertIn("package-content-mismatch", ids)

    def test_stale_plan_checkbox_is_review_not_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = self._candidate(root)
            (candidate / "reports" / "REVIVAL_PLAN.md").write_text("- [ ] COMPILE\n", encoding="utf-8")
            result = audit_revival(candidate)
            self.assertEqual(result["status"], "REVIEW")
            self.assertIn("plan-validation-state-stale", {item["id"] for item in result["issues"]})

    def test_duplicate_completion_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = _report().replace("## Status", "**READY**\n\n## Status")
            candidate = self._candidate(root, report)
            result = audit_revival(candidate)
            self.assertEqual(result["status"], "FAIL")
            self.assertIsNone(result["declared_completion_status"])
            issue = next(item for item in result["issues"] if item["id"] == "completion-status-invalid")
            self.assertEqual(issue["evidence"].count("READY"), 2)

    def test_non_final_completion_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = self._candidate(root, _report() + "Post-status narrative.\n")
            result = audit_revival(candidate)
            self.assertEqual(result["status"], "FAIL")
            self.assertIsNone(result["declared_completion_status"])
            issue = next(item for item in result["issues"] if item["id"] == "completion-status-invalid")
            self.assertIn("final:false", issue["evidence"])


if __name__ == "__main__":
    unittest.main()
