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


class KnownFailureTests(unittest.TestCase):
    """ROADMAP 70 H1.8: an environmental failure may be baselined with an expiry; any other failure still fails the run."""

    KNOWN = [{"test": "test_env", "reason": "this machine", "added": "2026-10-12", "expires": "2026-11-12"}]

    def test_a_known_failure_alone_is_expected_and_a_second_failure_is_not(self):
        from bridgeforge.test_guard import apply_known_failures

        only = apply_known_failures({"failed_tests": ["test_env"], "failures": 1, "errors": 0}, self.KNOWN, "2026-10-20")
        self.assertEqual((only["expected"], only["unexpected"], only["uncounted"]), (["test_env"], [], 0))
        two = apply_known_failures({"failed_tests": ["test_env", "test_real"], "failures": 2, "errors": 0}, self.KNOWN, "2026-10-20")
        self.assertEqual(two["unexpected"], ["test_real"])
        unnamed = apply_known_failures({"failed_tests": ["test_env"], "failures": 2, "errors": 0}, self.KNOWN, "2026-10-20")
        self.assertEqual(unnamed["uncounted"], 1)  # the summary counted a failure no FAIL/ERROR line named

    def test_an_expired_entry_counts_as_a_failure_again_and_a_passing_one_is_reported(self):
        from bridgeforge.test_guard import apply_known_failures

        expired = apply_known_failures({"failed_tests": ["test_env"], "failures": 1, "errors": 0}, self.KNOWN, "2026-12-01")
        self.assertEqual((expired["expected"], expired["unexpected"], expired["expired"]), ([], ["test_env"], ["test_env"]))
        passing = apply_known_failures({"failed_tests": [], "failures": 0, "errors": 0}, self.KNOWN, "2026-10-20")
        self.assertEqual(passing["now_passing"], ["test_env"])

    def test_the_known_failures_file_names_a_reason_and_an_expiry_for_every_entry(self):
        from bridgeforge.test_guard import load_known_failures

        # An empty list is the goal (the last entry, test_locks' child-cwd test, was fixed 2026-10-20).
        entries = load_known_failures(Path(__file__).resolve().parent.parent)
        for entry in entries:
            self.assertTrue(entry.get("reason") and entry.get("added") and entry.get("expires"), entry)

    def test_the_suite_line_names_a_known_failure_instead_of_counting_it(self):
        with resolved_temp_dir() as root:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "a.py").write_text("x", encoding="utf-8")
            counts = {"tests": 10, "failures": 1, "errors": 0, "skipped": 0, "failed_tests": ["test_env"], "verdict": "FAILED", "known_failures": ["test_env"]}
            save_result(root, snapshot(root), counts, 0)
            self.assertIn("10 tests, OK (skipped=0), 1 known environmental failure(s): test_env", suite_line(root))