from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from bridgeforge.test_guard import changed_paths, main, parse_unittest_output, save_result, snapshot, suite_line
from tests.support import resolved_temp_dir


class TestGuardTests(unittest.TestCase):
    def test_detects_dirty_file_edits_and_ignored_release_changes(self):
        with resolved_temp_dir() as root:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("probe-mod/releases/\n", encoding="utf-8")
            (root / "dirty.txt").write_text("before", encoding="utf-8")
            release = root / "probe-mod/releases/bridgeforge-probe"
            release.mkdir(parents=True)
            (release / "mod_info.json").write_text("before", encoding="utf-8")
            before = snapshot(root)
            self.assertEqual(changed_paths(before, snapshot(root)), [])
            (root / "dirty.txt").write_text("after", encoding="utf-8")
            (release / "mod_info.json").write_text("after", encoding="utf-8")
            changes = changed_paths(before, snapshot(root))
            self.assertIn("dirty.txt", changes)
            self.assertIn("probe-mod/releases/bridgeforge-probe/mod_info.json", changes)

    def test_temp_helper_returns_resolved_path(self):
        with resolved_temp_dir() as root:
            self.assertIsInstance(root, Path)
            self.assertEqual(root, root.resolve())

    def test_runner_fails_if_inputs_change_even_when_command_passes(self):
        with patch("bridgeforge.test_guard.snapshot", side_effect=[{"input": "a"}, {"input": "b"}]), patch(
            "bridgeforge.test_guard.subprocess.call", return_value=0
        ):
            self.assertEqual(main(["fake-test-command"]), 1)

    def test_runner_preserves_test_failure_when_unchanged(self):
        with patch("bridgeforge.test_guard.snapshot", return_value={"input": "a"}), patch(
            "bridgeforge.test_guard.subprocess.call", return_value=7
        ):
            self.assertEqual(main(["fake-test-command"]), 7)


class SuiteLineTests(unittest.TestCase):
    def test_counts_and_failing_names_come_from_the_unittest_summary(self):
        lines = ["FAIL: test_a (mod.Cls.test_a)", "ERROR: test_b (mod.Cls.test_b)", "Ran 1592 tests in 408.8s", "FAILED (failures=1, errors=1, skipped=3)"]
        counts = parse_unittest_output(lines)
        self.assertEqual((counts["tests"], counts["failures"], counts["errors"], counts["skipped"]), (1592, 1, 1, 3))
        self.assertEqual(counts["failed_tests"], ["test_a", "test_b"])
        self.assertEqual(parse_unittest_output(["Ran 5 tests in 1s", "OK"])["failures"], 0)

    def test_the_line_quotes_the_run_and_says_when_code_changed_after_it(self):
        # 2026-10-11: a commit message claimed a failure count the suite run did not have
        with resolved_temp_dir() as root:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("bridgeforge-state/" + chr(10), encoding="utf-8")
            (root / "bridgeforge").mkdir()
            (root / "bridgeforge" / "code.py").write_text("one", encoding="utf-8")
            (root / "ROADMAP.md").write_text("notes", encoding="utf-8")
            counts = {"tests": 10, "failures": 1, "errors": 0, "skipped": 2, "failed_tests": ["test_x"], "verdict": "FAILED (failures=1, skipped=2)"}
            save_result(root, snapshot(root), counts, 1)
            fresh = suite_line(root)
            (root / "ROADMAP.md").write_text("more notes", encoding="utf-8")
            records_only = suite_line(root)
            (root / "bridgeforge" / "code.py").write_text("two", encoding="utf-8")
            stale = suite_line(root)
            missing = suite_line(root / "bridgeforge")
        self.assertIn("10 tests, 1 failure(s) (skipped=2) [test_x]", fresh)
        self.assertNotIn("NOT RERUN", fresh)
        self.assertIn("records only changed since: 1 file(s)", records_only)
        self.assertIn("NOT RERUN since code changed", stale)
        self.assertIn("bridgeforge/code.py", stale)
        self.assertIn("no recorded run", missing)
