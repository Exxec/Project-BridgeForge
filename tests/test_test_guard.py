from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from bridgeforge.test_guard import changed_paths, main, snapshot
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
