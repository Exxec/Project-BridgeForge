"""ROADMAP-3 79.7: `boot-test` and `probe-group live` start the game through the same launch function."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import boot_test, launch, live_run, log_triage, window_watch
from bridgeforge.exit_observation import read_exit_observation
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


class WindowWatcherTests(unittest.TestCase):
    def _watcher(self, rig: Path, windows, texts, shots, clock):
        return window_watch.WindowWatcher(rig, "W-1", lambda: {5}, enumerate_fn=lambda pids: list(windows), child_text_fn=lambda h: texts.get(h, ""),
                                          screenshot=lambda path: shots.append(path.name), clock=clock, sleep=lambda _s: None)

    def test_dialog_text_goes_to_the_file_log_triage_reads(self) -> None:
        with resolved_temp_dir() as directory:
            rig = Path(directory)
            shots: list[str] = []
            windows = [(1, "Starsector"), (2, "Fatal Error")]
            watcher = self._watcher(rig, windows, {2: "Fatal: Weapon spec [X] not found!"}, shots, lambda: 0.0)
            watcher.poll_once()
            watcher.poll_once()  # nothing is recorded twice
            text = (rig / "logs" / "W-1.windows.txt").read_text(encoding="utf-8")
            self.assertEqual(text.count("window: 'Fatal Error'"), 1)
            self.assertEqual(shots, ["W-1-window1.png"])
            (rig / "logs" / "W-1.stdout.log").write_text("x\n", encoding="utf-8")
            fatals = log_triage._dialog_fatals(rig / "logs" / "W-1.windows.txt")
            self.assertEqual(len(fatals), 1)
            self.assertIn("Weapon spec", fatals[0]["message"])

    def test_no_main_menu_screenshot_after_three_minutes_and_earlier_log_moved_aside(self) -> None:
        with resolved_temp_dir() as directory:
            rig = Path(directory)
            (rig / "logs").mkdir()
            (rig / "logs" / "W-1.windows.txt").write_text("old\n", encoding="utf-8")
            now = {"t": 0.0}
            shots: list[str] = []
            watcher = self._watcher(rig, [], {}, shots, lambda: now["t"])
            now["t"] = 181.0
            watcher.poll_once()
            self.assertEqual(shots, ["W-1-no-main-menu.png"])
            self.assertTrue(list((rig / "logs").glob("W-1.windows.*.prev.txt")))
            self.assertFalse((rig / "logs" / "W-1.windows.txt").exists())

    def test_both_callers_start_the_watcher(self) -> None:
        for module in (boot_test, live_run):
            self.assertIn("launch.watch_windows", Path(module.__file__).read_text(encoding="utf-8"))


class InteractiveTests(unittest.TestCase):
    def test_interactive_run_waits_for_the_operator_and_records_natural(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, {"mod_b": targets["mod_b"]}, ["lib"])
            (rig / "run-j25-direct.bat").write_text("@echo off", encoding="utf-8")
            hands = mock.MagicMock()
            hands.alive.side_effect = [True, True, False]

            class Proc(_Process):
                returncode = 7

                def poll(self):
                    return 7

            with mock.patch.object(launch, "start_game", return_value=Proc()),                     mock.patch.object(launch, "watch_windows", return_value=mock.MagicMock()) as watch,                     mock.patch("bridgeforge.boot_test._running_java_under", return_value=[]),                     mock.patch("bridgeforge.boot_test._terminate_tree"),                     mock.patch("bridgeforge.rig_prefs.pinned_launcher_prefs") as prefs,                     mock.patch.object(live_run, "real_hands", lambda rig_, pid: hands),                     mock.patch.object(live_run, "EXIT_POLL_SECONDS", 0):
                result = live_run.live_run(rig, "INT-1", interactive=True)
            self.assertEqual(result.verdict, "LIVE_DONE")
            self.assertEqual(read_exit_observation(rig, "INT-1"), ("NATURAL", 7))
            watch.assert_called_once()
            prefs.assert_not_called()
            hands.click.assert_not_called()
            hands.key.assert_not_called()

    def test_bf_test_has_an_interactive_switch(self) -> None:
        script = (Path(__file__).resolve().parent.parent / "tools" / "bf-test.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$Interactive", script)
        self.assertIn('"--interactive"', script)


if __name__ == "__main__":
    unittest.main()
