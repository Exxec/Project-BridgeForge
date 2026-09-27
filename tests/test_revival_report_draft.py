from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.revival_report_draft import draft_revival_report, write_revival_report_draft
from bridgeforge.revival_audit import audit_revival
from tests.support import resolved_temp_dir


def _clean_mod(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod_info.json").write_text(
        '{"id":"fixture","name":"Fixture","gameVersion":"0.98a","dependencies":[{"id":"lw_lazylib","name":"LazyLib"}]}',
        encoding="utf-8",
    )
    (root / "data" / "weapons").mkdir(parents=True)
    (root / "data" / "weapons" / "weapon_data.csv").write_text("id,name\nfixture_gun,Fixture Gun\n", encoding="utf-8")
    return root


class DraftHonoursBaselineTests(unittest.TestCase):
    def test_a_manual_finding_the_baseline_accepts_is_listed_not_blocking(self) -> None:
        import json

        from bridgeforge.baseline import finding_baseline_key
        from bridgeforge.models import TargetProfile
        from bridgeforge.scanner import scan_mod

        with resolved_temp_dir() as root:
            vanilla_core = root / "vanilla-core"
            vanilla_core.mkdir()
            mod_dir = _clean_mod(root / "Fixture")
            (mod_dir / "data" / "weapons" / "weapon_data.csv").write_text("id,name\nfixture_gun,Fixture Gun,extra,more\n", encoding="utf-8")
            manual = [f for f in scan_mod(mod_dir, TargetProfile()).findings if f.classification == "MANUAL"]
            blocked = draft_revival_report(mod_dir, vanilla_core=vanilla_core)
            (mod_dir / "reports").mkdir()
            (mod_dir / "reports" / "baseline.json").write_text(json.dumps({"findings": [finding_baseline_key(f) for f in manual]}), encoding="utf-8")
            accepted = draft_revival_report(mod_dir, vanilla_core=vanilla_core)
        self.assertTrue(manual)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual((accepted["status"], accepted["accepted_by_baseline"]), ("OK", len(manual)))
        self.assertIn("## Accepted by baseline", accepted["report_text"])
        self.assertIn(f"[{manual[0].id}]", accepted["report_text"])


class DraftRevivalReportTests(unittest.TestCase):
    """A clean mod (0 MANUAL, compile PASS) can skip hand-authoring REVIVAL_REPORT.md/PLAN.md."""

    def test_a_clean_mod_gets_a_drafted_ready_for_live_test_report_and_plan(self) -> None:
        with resolved_temp_dir() as root:
            mod_dir = _clean_mod(root / "Fixture")
            draft = draft_revival_report(mod_dir, vanilla_core=None)
            self.assertEqual(draft["status"], "BLOCKED")
            self.assertTrue(any("vanilla-core" in reason for reason in draft["blocking"]))

    def test_without_manual_findings_and_with_a_real_vanilla_core_stub_drafts_ok(self) -> None:
        with resolved_temp_dir() as root:
            vanilla_core = root / "vanilla-core"
            vanilla_core.mkdir()
            mod_dir = _clean_mod(root / "Fixture")
            draft = draft_revival_report(mod_dir, vanilla_core=vanilla_core)
            self.assertEqual(draft["status"], "OK")
            self.assertEqual(draft["completion_status"], "READY_FOR_LIVE_TEST")
            self.assertTrue(draft["report_text"].rstrip().endswith("READY_FOR_LIVE_TEST"))
            self.assertIn("LazyLib", draft["report_text"])
            self.assertIn("- [x] COMPILE", draft["plan_text"])
            self.assertIn("- [ ] LIVE STARSECTOR TEST", draft["plan_text"])

    def test_a_manual_finding_blocks_the_draft(self) -> None:
        with resolved_temp_dir() as root:
            vanilla_core = root / "vanilla-core"
            vanilla_core.mkdir()
            mod_dir = root / "Fixture"
            (mod_dir).mkdir(parents=True)
            # No mod_info.json at all -> missing-mod-info, a MANUAL finding.
            draft = draft_revival_report(mod_dir, vanilla_core=vanilla_core)
            self.assertEqual(draft["status"], "BLOCKED")
            self.assertTrue(any("missing-mod-info" in reason for reason in draft["blocking"]))

    def test_write_creates_both_files_and_refuses_to_clobber_without_force(self) -> None:
        with resolved_temp_dir() as root:
            vanilla_core = root / "vanilla-core"
            vanilla_core.mkdir()
            mod_dir = _clean_mod(root / "Fixture")
            written = write_revival_report_draft(mod_dir, vanilla_core=vanilla_core)
            self.assertEqual(written["status"], "WRITTEN")
            report_path = mod_dir / "reports" / "REVIVAL_REPORT.md"
            plan_path = mod_dir / "reports" / "REVIVAL_PLAN.md"
            self.assertTrue(report_path.is_file())
            self.assertTrue(plan_path.is_file())

            refused = write_revival_report_draft(mod_dir, vanilla_core=vanilla_core)
            self.assertEqual(refused["status"], "REFUSED")
            self.assertEqual(len(refused["existing"]), 2)

            forced = write_revival_report_draft(mod_dir, vanilla_core=vanilla_core, force=True)
            self.assertEqual(forced["status"], "WRITTEN")

    def test_the_drafted_pair_satisfies_audit_revivals_own_structural_checks(self) -> None:
        """The point of drafting is that `release`'s own gate (audit_revival) can read it - not
        just that it looks like a report. Package attestation is skipped (no archive yet), so
        audit_revival should report REVIEW (a warning about the missing archive), never FAIL."""
        with resolved_temp_dir() as root:
            vanilla_core = root / "vanilla-core"
            vanilla_core.mkdir()
            mod_dir = _clean_mod(root / "Fixture")
            write_revival_report_draft(mod_dir, vanilla_core=vanilla_core)
            audit = audit_revival(mod_dir)
            self.assertEqual(audit["status"], "REVIEW")
            self.assertEqual(audit["declared_completion_status"], "READY_FOR_LIVE_TEST")
            error_ids = [issue["id"] for issue in audit["issues"] if issue["severity"] == "ERROR"]
            self.assertEqual(error_ids, [])
