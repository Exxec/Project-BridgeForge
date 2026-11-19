"""ROADMAP 70 H4: rig-doctor warns about long-path and non-ASCII path hazards."""
from __future__ import annotations

import unittest

import tests.support  # noqa: F401  installs the registry guard when this module runs alone (96.5 C4)
from pathlib import Path

from bridgeforge.rig.rig_doctor import _check_environment


class EnvironmentCheckTests(unittest.TestCase):
    def test_long_paths_off_is_a_warning(self) -> None:
        result = _check_environment(Path("C:/rig"), Path("C:/repo"), long_paths=False)
        self.assertEqual(result["status"], "WARN")
        self.assertIn("LongPathsEnabled", result["detail"])

    def test_non_ascii_rig_path_is_a_warning_naming_the_path(self) -> None:
        result = _check_environment(Path("C:/Spiel/Gr\u00fc\u00dfe"), Path("C:/repo"), long_paths=True)
        self.assertEqual(result["status"], "WARN")
        self.assertIn("translator", result["detail"])

    def test_enabled_long_paths_and_ascii_paths_pass(self) -> None:
        self.assertEqual(_check_environment(Path("C:/rig"), Path("C:/repo"), long_paths=True)["status"], "PASS")

    def test_unknown_long_path_setting_is_not_a_warning(self) -> None:
        # long_paths=None asked the real HKLM key and accepted either answer; the registry guard found it (96.5 C4).
        from unittest import mock

        with mock.patch("bridgeforge.rig.rig_doctor._long_paths_enabled", return_value=None):
            self.assertEqual(_check_environment(Path("C:/rig"), Path("C:/repo"), long_paths=None)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
