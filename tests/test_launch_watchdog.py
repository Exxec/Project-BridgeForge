"""ROADMAP 60f(4): no java process 60 s after launch is reported and stops the run instead of waiting."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import boot_test
from tests.support import resolved_temp_dir
from tests.test_boot_test import _make_rig, _write_fake_launcher

BF_TEST = Path(__file__).resolve().parent.parent / "tools" / "bf-test.ps1"
SLEEPER = "import time\ntime.sleep(25)\n"


@unittest.skipUnless(sys.platform == "win32", "boot-test launches the rig's Windows .bat")
class BootTestWatchdogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = (boot_test.POLL_INTERVAL_SECONDS, boot_test.LAUNCH_WATCHDOG_SECONDS)
        boot_test.POLL_INTERVAL_SECONDS = 0.2
        boot_test.LAUNCH_WATCHDOG_SECONDS = 1.5

    def tearDown(self) -> None:
        boot_test.POLL_INTERVAL_SECONDS, boot_test.LAUNCH_WATCHDOG_SECONDS = self._saved

    def test_a_launcher_that_never_starts_java_is_stopped_with_a_message(self) -> None:
        with resolved_temp_dir() as directory:
            rig = _make_rig(Path(directory))
            _write_fake_launcher(rig, SLEEPER)
            started = time.monotonic()
            result = boot_test.run_boot_test(rig, ["demo_mod"], timeout=20)
            waited = time.monotonic() - started
        self.assertEqual(result["status"], "LAUNCH_NO_PROCESS")
        self.assertEqual(result["status"], boot_test.LAUNCH_NO_PROCESS)
        self.assertIn("Launch watchdog", result["reason"])
        self.assertIn("no java process", result["reason"])
        self.assertLess(waited, 15)

    def test_a_running_java_keeps_the_run_waiting_until_its_own_timeout(self) -> None:
        with resolved_temp_dir() as directory:
            rig = _make_rig(Path(directory))
            _write_fake_launcher(rig, SLEEPER)
            with mock.patch.object(boot_test, "java_started", return_value=True):
                result = boot_test.run_boot_test(rig, ["demo_mod"], timeout=3)
        self.assertEqual(result["status"], "SUSPECT_FATAL_DIALOG")


class WatchdogWiringTests(unittest.TestCase):
    def test_message_names_the_rig_and_the_limit(self) -> None:
        text = boot_test.watchdog_message(Path("rig"), 60)
        self.assertIn("60 s", text)
        self.assertIn("never started the game", text)

    def test_bf_test_launch_has_the_watchdog(self) -> None:
        script = BF_TEST.read_text(encoding="utf-8")
        self.assertIn("Launch watchdog", script)
        self.assertIn("TotalSeconds -gt 60", script)

    def test_bf_test_launch_names_the_status(self) -> None:
        self.assertIn("LAUNCH_NO_PROCESS", BF_TEST.read_text(encoding="utf-8"))

    def test_live_run_reports_the_watchdog_as_a_named_stage(self) -> None:
        import contextlib

        from bridgeforge import live_run

        @contextlib.contextmanager
        def firing(*_args, **_kwargs):
            raise live_run.LaunchNoProcess("Launch watchdog: no java process")
            yield  # pragma: no cover

        with mock.patch.object(live_run, "running_game", firing):
            result = live_run.live_run(Path("rig"), "T-1")
        self.assertEqual(result.verdict, "LIVE_STUCK")
        self.assertEqual(result.stage, "LAUNCH_NO_PROCESS")

    def test_live_runner_uses_the_same_watchdog(self) -> None:
        source = (Path(boot_test.__file__).parent / "live_run.py").read_text(encoding="utf-8")
        self.assertIn("LAUNCH_WATCHDOG_SECONDS", source)
        self.assertIn("watchdog_message", source)


if __name__ == "__main__":
    unittest.main()
