"""launcher_click (ROADMAP 60f): the Play click for unattended boots; the real click is proven live, not here."""
from __future__ import annotations

import sys
import unittest
from unittest import mock

from bridgeforge import boot_test, launcher_click


class LauncherClickTests(unittest.TestCase):
    def test_no_processes_means_no_click(self) -> None:
        self.assertIsNone(launcher_click.click_launcher_once(set()))

    @unittest.skipUnless(sys.platform == "win32", "window enumeration is Windows only")
    def test_clicks_the_starsector_window_and_ignores_others(self) -> None:
        windows = [(11, "Some other dialog"), (22, "Starsector 0.98a-RC8")]
        with mock.patch.object(launcher_click, "_windows_for", return_value=windows), \
                mock.patch.object(launcher_click, "click_window", return_value="posted") as click, \
                mock.patch.object(launcher_click.time, "sleep"):
            note = launcher_click.click_launcher_once({123})
        self.assertEqual(note, "posted")
        click.assert_called_once_with(22)

    @unittest.skipUnless(sys.platform == "win32", "window enumeration is Windows only")
    def test_window_of_another_title_is_not_clicked(self) -> None:
        with mock.patch.object(launcher_click, "_windows_for", return_value=[(11, "Notepad")]), \
                mock.patch.object(launcher_click, "click_window") as click:
            self.assertIsNone(launcher_click.click_launcher_once({123}))
        click.assert_not_called()

    def test_boot_test_takes_the_auto_click_flag(self) -> None:
        import inspect
        self.assertIn("auto_click", inspect.signature(boot_test.run_boot_test).parameters)

    def test_descendant_pids_finds_a_child_outside_any_rig_folder(self) -> None:
        import os
        import subprocess
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertIn(child.pid, launcher_click.descendant_pids(os.getpid()))
        finally:
            child.kill()
            child.wait()


if __name__ == "__main__":
    unittest.main()
