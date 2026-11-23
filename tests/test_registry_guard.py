"""96.5 C4 (narrowed by the owner 2026-11-18): tests cannot reach the real Windows registry unless they patch winreg."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.support import TEST_REGISTRY_ROOT, RegistryGuardError

ROOT = Path(__file__).resolve().parents[1]
# Test modules whose code can reach a registry call: they must install the guard themselves, so running one alone is guarded.
REGISTRY_REACH = re.compile(r"\bwinreg\b|rig_prefs|rig_doctor|probe_group|live_run")


@unittest.skipUnless(sys.platform == "win32", "the registry exists only on Windows")
class RegistryGuardTests(unittest.TestCase):
    def test_the_starsector_preferences_key_is_refused(self) -> None:
        import winreg

        with self.assertRaises(RegistryGuardError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\JavaSoft\Prefs\com\fs\starfarer")
        with self.assertRaises(RegistryGuardError):
            winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\JavaSoft\Prefs\com\fs\starfarer")

    def test_machine_keys_are_refused(self) -> None:
        import winreg

        with self.assertRaises(RegistryGuardError):
            winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem")

    def test_the_test_root_under_another_hive_is_refused(self) -> None:
        # Only HKEY_CURRENT_USER's test root is allowed; checked without opening any key (mutation re-run 2026-11-22).
        import winreg

        from tests import support

        self.assertTrue(support._registry_allowed(winreg.HKEY_CURRENT_USER, TEST_REGISTRY_ROOT))
        self.assertFalse(support._registry_allowed(winreg.HKEY_LOCAL_MACHINE, TEST_REGISTRY_ROOT))
        self.assertFalse(support._registry_allowed(winreg.HKEY_USERS, TEST_REGISTRY_ROOT + r"\x"))

    def test_product_code_cannot_swallow_the_refusal(self) -> None:
        # rig_doctor catches OSError as "unreadable"; the guard's error is not one, so the access shows.
        self.assertFalse(issubclass(RegistryGuardError, OSError))
        from bridgeforge.rig import rig_doctor

        with self.assertRaises(RegistryGuardError):
            rig_doctor._long_paths_enabled()

    def test_the_test_root_is_allowed(self) -> None:
        import winreg

        path = TEST_REGISTRY_ROOT + r"\registry_guard"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path):
            pass
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        with self.assertRaises(RegistryGuardError):  # a look-alike prefix is not the root
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_REGISTRY_ROOT + "Evil")

    def test_a_patched_call_replaces_the_guard(self) -> None:
        import winreg

        with mock.patch("winreg.OpenKey", return_value="patched"):
            self.assertEqual(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "anything"), "patched")
        self.assertTrue(getattr(winreg.OpenKey, "registry_guard", False))  # restored afterwards


class GuardCoverageTests(unittest.TestCase):
    def test_modules_that_reach_registry_code_install_the_guard(self) -> None:
        missing = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            text = path.read_text(encoding="utf-8-sig")
            if REGISTRY_REACH.search(text) and "tests.support" not in text:
                missing.append(path.name)
        self.assertEqual(missing, [], "import tests.support in these modules so running one alone is guarded")


if __name__ == "__main__":
    unittest.main()
