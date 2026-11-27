"""ROADMAP-3 93.47: a name from a mod never reaches cmd.exe or a PowerShell script.

The mass test built its log name from the mod's id (`mass-<id>`). That name reached the raw `cmd.exe /c ""bat" > "log" ..."`
launch line and, through the window watcher's screenshot path, a PowerShell single-quoted string that doubled only `'`
(PowerShell also ends such a string at U+2018-U+201B). The security review of 93.45 ran an injected command through each
(2026-11-17).
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import game_click, launch, mass_test, window_watch
from tests.support import resolved_temp_dir

_HOSTILE_ID = 'x" & type nul > INJECTED.txt & rem ’; Write-Output INJECTED; \'%COMSPEC%!x!'


class _Stop(Exception):
    pass


class LaunchLineTests(unittest.TestCase):
    def test_a_path_that_could_change_the_launch_line_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            bat, err = root / "run.bat", root / "x.err"
            launch.command_line(bat, root / "SR6-LIVE-0985a-20261117.stdout.log", err)  # an ordinary name passes
            for name in ['mass-x" & type nul > INJECTED.txt & rem .log', "mass-%COMSPEC%.log", "mass-!x!.log", "mass-a\nb.log"]:
                with self.assertRaises(ValueError, msg=name):
                    launch.command_line(bat, root / name, err)

    def test_start_game_refuses_before_starting_anything(self) -> None:
        with resolved_temp_dir() as root, mock.patch.object(launch.subprocess, "Popen") as popen:
            with self.assertRaises(ValueError):
                launch.start_game(root, root / "run.bat", root / 'a" & calc & rem .log', root / "a.err")
        popen.assert_not_called()


class MassTestLogNameTests(unittest.TestCase):
    def test_a_mod_id_becomes_a_plain_log_name(self) -> None:
        seen: dict = {}

        def capture(*_args, **kwargs):
            seen.update(kwargs)
            raise _Stop

        target = {"name": "Hostile", "id": _HOSTILE_ID, "status": None}
        with resolved_temp_dir() as root, mock.patch.object(mass_test.java_matrix, "run_java_matrix", side_effect=capture):
            with self.assertRaises(_Stop):
                variant = {"id": "j25", "bat": "run.bat", "launcher": "direct", "major": 25, "java_version": "25"}
                mass_test._test_one(root, target, {"ids": [], "folders": []}, [variant], False, False, 1, 10, 1, None, False,
                                    root / "logs")
        self.assertRegex(seen["log_name"], r"\Amass-[A-Za-z0-9._-]+\Z")


class PowerShellPathTests(unittest.TestCase):
    """The screenshot path goes to PowerShell in an environment variable, never inside the script."""

    def _check(self, call, path: Path) -> None:
        recorded: dict = {}

        def run(args, **kwargs):
            recorded["script"], recorded["env"] = args[-1], kwargs.get("env") or {}
            return subprocess.CompletedProcess(args, 0, b"", b"")

        with mock.patch.object(subprocess, "run", side_effect=run):
            call()
        self.assertNotIn(path.name, recorded["script"])
        self.assertIn(str(path), recorded["env"].values())

    def test_the_window_watchers_screenshot(self) -> None:
        with resolved_temp_dir() as root:
            path = root / f"{_HOSTILE_ID.replace(chr(34), '_').replace('>', '_')}-window1.png"
            self._check(lambda: window_watch.save_screenshot(path, 4242), path)

    def test_the_window_watchers_screenshot_is_one_window_never_the_screen(self) -> None:
        # ROADMAP-3 93.24: live tests run on the owner's desktop, which is never captured.
        recorded: dict = {}

        def run(args, **kwargs):
            recorded["script"], recorded["env"] = args[-1], kwargs.get("env") or {}
            return subprocess.CompletedProcess(args, 0, b"", b"")

        with resolved_temp_dir() as root, mock.patch.object(subprocess, "run", side_effect=run) as ran:
            self.assertFalse(window_watch.save_screenshot(root / "x.png"))  # no window: nothing runs, nothing is captured
            ran.assert_not_called()
            window_watch.save_screenshot(root / "y.png", 4242)
        self.assertIn("GetWindowRect", recorded["script"])
        self.assertNotIn("VirtualScreen", recorded["script"])
        self.assertEqual(recorded["env"]["BF_WINDOW"], "4242")

    def test_the_game_window_capture(self) -> None:
        with resolved_temp_dir() as root:
            for suffix in (".png", ".bmp"):
                path = root / f"it’s-{re.sub(r'[^A-Za-z]', '', suffix)}{suffix}"
                self._check(lambda path=path: game_click.capture_client((0, 0, 0, 10, 10), path), path)


if __name__ == "__main__":
    unittest.main()
