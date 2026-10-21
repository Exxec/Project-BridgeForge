"""ROADMAP-3 79.7: `boot-test` and `probe-group live` start the game through the same launch function."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import boot_test, launch, live_run
from tests.bound_runs import make_rig, stage
from tests.support import resolved_temp_dir
from tests.test_boot_test import _make_rig
from tests.test_run_manifest import _two


class _Process:
    pid = 1
    returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


class OneLauncherTests(unittest.TestCase):
    def test_boot_test_starts_the_game_through_launch(self) -> None:
        with resolved_temp_dir() as directory:
            rig = _make_rig(Path(directory))
            (rig / boot_test.BAT_NAME).write_text("@echo off", encoding="utf-8")
            with mock.patch.object(launch, "start_game", return_value=_Process()) as start, \
                    mock.patch.object(boot_test, "_running_java_under", return_value=[]):
                result = boot_test.run_boot_test(rig, ["demo_mod"], timeout=1, log_name="one")
            start.assert_called_once()
            self.assertEqual(start.call_args.args[1], rig / boot_test.BAT_NAME)
            self.assertEqual(start.call_args.args[2], rig / "logs" / "one.stdout.log")
            self.assertEqual(result["status"], "FAIL")

    def test_probe_group_live_starts_the_game_through_launch(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, {"mod_b": targets["mod_b"]}, ["lib"])
            (rig / "run-j25-direct.bat").write_text("@echo off", encoding="utf-8")
            with mock.patch.object(launch, "start_game", return_value=_Process()) as start, \
                    mock.patch("bridgeforge.boot_test._running_java_under", return_value=[]), \
                    mock.patch("bridgeforge.boot_test._terminate_tree"), \
                    mock.patch("bridgeforge.rig_prefs.pinned_launcher_prefs", mock.MagicMock()), \
                    mock.patch.object(live_run, "real_hands", lambda rig_, pid: mock.MagicMock()):
                with live_run.running_game(rig, "ONE-1"):
                    pass
            start.assert_called_once()
            self.assertEqual(start.call_args.args[1], rig / "run-j25-direct.bat")
            self.assertEqual(start.call_args.args[2], rig / "logs" / "ONE-1.stdout.log")

    def test_the_game_is_started_in_one_place_only(self) -> None:
        for module in (boot_test, live_run):
            self.assertNotIn("Popen", Path(module.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
