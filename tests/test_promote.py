import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bridgeforge.build_tag import apply_build_tag
from bridgeforge.cli import main
from bridgeforge.promote import promote_mod
from bridgeforge.project_board import project_board
from bridgeforge.release import ReleaseError, _load_policy, _release_basename, _licence_gate
from bridgeforge.revival_audit import REQUIRED_VALIDATIONS
from bridgeforge.archive_intake import _tree_sha256
from tests.support import resolved_temp_dir
from tests.test_release import _clean_fixture_mod, _write_empty_baseline


def fixture(root):
    folder = root / "In operation/Fixture"
    working = folder / "working"
    working.mkdir(parents=True)
    _clean_fixture_mod(working)
    apply_build_tag(working, record_manifest=False)
    reports = folder / "reports"
    reports.mkdir()
    (reports / "REVIVAL_PLAN.md").write_text("# Approved fixture plan\n\nTotal score: 0\nComplexity level: LOW\n", encoding="utf-8")
    lines = ["# Fixture report", ""]
    for label in REQUIRED_VALIDATIONS:
        evidence = "LIVE TEST NOT PERFORMED" if label == "LIVE STARSECTOR TEST" else "PASS"
        lines.append(f"- {label} - {evidence}")
    (reports / "REVIVAL_REPORT.md").write_text("\n".join(lines) + "\n\nREADY_FOR_LIVE_TEST\n", encoding="utf-8")
    baseline = reports / "baseline.json"
    _write_empty_baseline(baseline)
    paths = {}
    for key, document in (("behavior_diff", {"schema_version": 1, "status": "PASS", "blocking_count": 0, "deltas": []}),
                          ("behavior_risks", {"schema_version": 1, "risks": []}),
                          ("behavior_unknowns", {"schema_version": 1, "unknowns": []})):
        paths[key] = reports / (key + ".json")
        paths[key].write_text(json.dumps(document), encoding="utf-8")
    return folder, {"original": working / "jars/fixture.jar", "baseline": baseline, **paths}


class PromotionTests(unittest.TestCase):
    def test_dry_run_is_read_only_and_apply_preserves_declared_live_gate(self):
        with resolved_temp_dir() as root:
            folder, options = fixture(root)
            before = _tree_sha256(root)
            result = promote_mod("Fixture", root, **options)
            self.assertEqual(result["status"], "DRY_RUN_READY", result)
            self.assertEqual(_tree_sha256(root), before)
            self.assertFalse((root / "Done").exists())
            result = promote_mod("Fixture", root, apply=True, **options)
            self.assertEqual(result["status"], "PROMOTED", result)
            self.assertEqual(result["completion_status"], "READY_FOR_LIVE_TEST")
            self.assertTrue(result["package_audit"]["package_attestation"]["exact_match"])
            row = project_board(root)["mods"][-1]
            self.assertEqual(row["stage"], "REPORT_DECLARED_READY_FOR_LIVE_TEST")
            self.assertIn("fixture_mod-1.0+bf.1", row["evidence"]["report"])
            self.assertFalse((root / "Done/Fixture/.promotion.lock").exists())

    def test_prior_release_and_reports_are_retained_unrelated_contents_stay(self):
        with resolved_temp_dir() as root:
            folder, options = fixture(root)
            promote_mod("Fixture", root, apply=True, **options)
            target = root / "Done/Fixture"
            old_release = target / "fixture_mod-1.0+bf.1"
            old_hash = _tree_sha256(old_release)
            old_zip = (target / "fixture_mod-1.0+bf.1.zip").read_bytes()
            original = target / "original"
            original.mkdir()
            (original / "untouched.bin").write_bytes(b"upstream")
            (target / "user-notes.txt").write_text("keep", encoding="utf-8")
            apply_build_tag(folder / "working", record_manifest=False)
            second = promote_mod("Fixture", root, apply=True, **options)
            self.assertEqual(second["status"], "PROMOTED")
            retention = Path(second["retained_at"])
            self.assertEqual(_tree_sha256(retention / old_release.name), old_hash)
            self.assertEqual((retention / (old_release.name + ".zip")).read_bytes(), old_zip)
            self.assertTrue((retention / "reports" / old_release.name / "REVIVAL_REPORT.md").is_file())
            self.assertFalse(old_release.exists())
            self.assertTrue((target / "fixture_mod-1.0+bf.2").is_dir())
            self.assertEqual((original / "untouched.bin").read_bytes(), b"upstream")
            self.assertEqual((target / "user-notes.txt").read_text(encoding="utf-8"), "keep")

    def test_missing_invalid_report_or_unscored_plan_blocks_without_writes(self):
        with resolved_temp_dir() as root:
            folder, options = fixture(root)
            report = folder / "reports/REVIVAL_REPORT.md"
            original_report = report.read_text(encoding="utf-8")
            for text in ("READY\n", original_report.replace("COMPILE - PASS", "COMPILE - FAIL (historical PASS)"),
                         original_report.replace("READY_FOR_LIVE_TEST", "READY"),
                         original_report.replace("READY_FOR_LIVE_TEST", "READY").replace(
                             "LIVE TEST NOT PERFORMED", "FAIL (historical PASS)")):
                report.write_text(text, encoding="utf-8")
                result = promote_mod("Fixture", root, apply=True, **options)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertFalse((root / "Done").exists())
            report.write_text(original_report, encoding="utf-8")
            (folder / "reports/REVIVAL_PLAN.md").write_text("# Unscored\n", encoding="utf-8")
            self.assertIn("explicit-plan-score-and-level-required", promote_mod("Fixture", root, **options)["blocking_reasons"])

    def test_behavior_or_licence_gate_blocks_and_keeps_previous_release(self):
        with resolved_temp_dir() as root:
            folder, options = fixture(root)
            promote_mod("Fixture", root, apply=True, **options)
            target = root / "Done/Fixture"
            before = _tree_sha256(target)
            options["behavior_risks"].write_text('{"schema_version":1,"risks":[{"id":"R","level":"HIGH","status":"OPEN"}]}', encoding="utf-8")
            self.assertEqual(promote_mod("Fixture", root, apply=True, **options)["status"], "BLOCKED")
            self.assertEqual(_tree_sha256(target), before)
            options["behavior_risks"].write_text('{"schema_version":1,"risks":[]}', encoding="utf-8")
            policy = folder / "reports/policy.json"
            policy.write_text('{"default":{"local_only":true}}', encoding="utf-8")
            self.assertEqual(promote_mod("Fixture", root, apply=True, policy=policy, **options)["status"], "BLOCKED")
            self.assertEqual(_tree_sha256(target), before)

    def test_unrelated_collision_and_existing_lock_are_not_overwritten(self):
        with resolved_temp_dir() as root:
            _, options = fixture(root)
            target = root / "Done/Fixture"
            target.mkdir(parents=True)
            collision = target / "fixture_mod-1.0+bf.1.zip"
            collision.write_bytes(b"user archive")
            with self.assertRaisesRegex(ValueError, "unrelated"):
                promote_mod("Fixture", root, apply=True, **options)
            self.assertEqual(collision.read_bytes(), b"user archive")
            collision.unlink()
            lock = target / ".promotion.lock"
            lock.write_text("prior interrupted session", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                promote_mod("Fixture", root, apply=True, **options)
            self.assertEqual(lock.read_text(encoding="utf-8"), "prior interrupted session")

    def test_publication_failure_restores_previous_release_bytes(self):
        with resolved_temp_dir() as root:
            folder, options = fixture(root)
            promote_mod("Fixture", root, apply=True, **options)
            target = root / "Done/Fixture"
            before = _tree_sha256(target)
            apply_build_tag(folder / "working", record_manifest=False)
            rename = Path.rename

            def fail_zip(path, destination):
                if path.name.endswith("bf.2.zip") and Path(destination).parent == target:
                    raise OSError("forced publication failure")
                return rename(path, destination)

            with patch.object(Path, "rename", fail_zip), self.assertRaisesRegex(OSError, "forced"):
                promote_mod("Fixture", root, apply=True, **options)
            self.assertEqual(_tree_sha256(target), before)
            self.assertFalse((target / ".promotion.lock").exists())

    def test_cli_promote_dry_run(self):
        with resolved_temp_dir() as root:
            _, options = fixture(root)
            arguments = ["promote", "Fixture", "--repo-root", str(root), "--json"]
            for key, value in options.items():
                arguments.extend(["--" + key.replace("_", "-"), str(value)])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(arguments), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "DRY_RUN_READY")


class PolicySafetyTests(unittest.TestCase):
    def test_missing_malformed_and_non_boolean_policy_fail_closed(self):
        with resolved_temp_dir() as root:
            path = root / "policy.json"
            with self.assertRaises(ReleaseError):
                _load_policy(path)
            for text in ("bad json", "[]", '{"mods":[]}', '{"default":{"local_only":"false"}}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ReleaseError):
                    _load_policy(path)
            with patch("bridgeforge.release.DEFAULT_POLICY_PATH", root / "missing.json"), self.assertRaises(ReleaseError):
                _load_policy(None)
        self.assertEqual(_licence_gate("exigency", "Exigency", None)["status"], "FAIL")

    def test_release_basename_rejects_escape_and_device_names(self):
        for mod_id, version in (("../escape", "1"), ("safe", "../../escape"), ("CON", None), ("safe", "x:stream")):
            with self.subTest(mod_id=mod_id, version=version), self.assertRaises(ReleaseError):
                _release_basename(mod_id, version, Path("fixture"))


if __name__ == "__main__":
    unittest.main()
