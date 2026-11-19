"""rig_prefs: the rig pins the shared launcher resolution and gives the owner's setting back (2026-10-11)."""
from __future__ import annotations

import sys
import unittest

import tests.support  # noqa: F401  installs the registry guard when this module runs alone (96.5 C4)
from unittest import mock

from bridgeforge.rig import rig_prefs


class PinnedPrefsTests(unittest.TestCase):
    def test_values_are_pinned_inside_and_the_owners_come_back_after_an_error(self) -> None:
        store = {"resolution": "2048x1152", "fullscreen": "true"}
        writes = []

        def read(names):
            return {n: store.get(n) for n in names}

        def write(values):
            writes.append(dict(values))
            for k, v in values.items():
                if v is None:
                    store.pop(k, None)
                else:
                    store[k] = v

        with mock.patch.object(rig_prefs, "read_prefs", side_effect=read), mock.patch.object(rig_prefs, "write_prefs", side_effect=write):
            with self.assertRaises(RuntimeError):
                with rig_prefs.pinned_launcher_prefs():
                    self.assertEqual(store, {"resolution": "1920x1440", "fullscreen": "false"})
                    raise RuntimeError("the game crashed")
        self.assertEqual(store, {"resolution": "2048x1152", "fullscreen": "true"})
        self.assertEqual(len(writes), 2)

    def test_an_absent_value_is_removed_again(self) -> None:
        store: dict[str, str] = {}

        def write(values):
            for k, v in values.items():
                if v is None:
                    store.pop(k, None)
                else:
                    store[k] = v

        with mock.patch.object(rig_prefs, "read_prefs", side_effect=lambda names: {n: store.get(n) for n in names}), \
                mock.patch.object(rig_prefs, "write_prefs", side_effect=write):
            with rig_prefs.pinned_launcher_prefs():
                self.assertIn("resolution", store)
        self.assertEqual(store, {})

    def test_a_live_run_pins_can_skip_tutorial_and_the_owners_state_comes_back(self) -> None:
        """ROADMAP-3 93.28: on a Windows user who never started a game, New Game's "Skip it" is disabled (rules.csv
        `ngcSkipTutorialNoSkip`, backed by the preference canSkipTutorial, stored as can/Skip/Tutorial)."""
        store = {"resolution": "1920x1440"}

        def write(values):
            for k, v in values.items():
                if v is None:
                    store.pop(k, None)
                else:
                    store[k] = v

        with mock.patch.object(rig_prefs, "read_prefs", side_effect=lambda names: {n: store.get(n) for n in names}), \
                mock.patch.object(rig_prefs, "write_prefs", side_effect=write):
            with rig_prefs.pinned_launcher_prefs(rig_prefs.LIVE_PINNED):
                self.assertEqual(store["can/Skip/Tutorial"], "true")
        self.assertEqual(store, {"resolution": "1920x1440"})
        self.assertEqual({k: rig_prefs.LIVE_PINNED[k] for k in rig_prefs.PINNED}, rig_prefs.PINNED)


@unittest.skipUnless(sys.platform == "win32", "the Windows registry")
class HasPrefTests(unittest.TestCase):
    """ROADMAP-3 93.28 (review 2026-11-17): the presence check runs against a real registry key and never reads a value."""

    KEY = r"Software\BridgeForgeTests\has_pref"

    def tearDown(self) -> None:
        import winreg

        for path in (self.KEY, r"Software\BridgeForgeTests"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except OSError:
                pass

    def test_presence_is_answered_without_reading_the_value(self) -> None:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY) as key:
            winreg.SetValueEx(key, "present", 0, winreg.REG_SZ, "a value no check may read")
        with mock.patch("winreg.QueryValueEx", side_effect=AssertionError("a preference value was read")), \
                mock.patch("winreg.EnumValue", side_effect=AssertionError("a preference value was read")):
            present = rig_prefs.has_pref("present", key_path=self.KEY)
            absent = rig_prefs.has_pref("absent", key_path=self.KEY)
            no_key = rig_prefs.has_pref("present", key_path=self.KEY + r"\missing")
        self.assertEqual((present, absent, no_key), (True, False, False))


class FirstRunPreflightTests(unittest.TestCase):
    """ROADMAP-3 93.28: what an unattended run needs from the Windows user's Java preferences, checked before a run."""

    def _check(self, present: dict[str, bool | None], skip_tutorial: str | None = "true") -> dict:
        from bridgeforge.rig.rig_doctor import _check_launcher_prefs

        with mock.patch.object(rig_prefs, "has_pref", side_effect=lambda name: present.get(name, False)), \
                mock.patch.object(rig_prefs, "read_prefs", return_value={rig_prefs.CAN_SKIP_TUTORIAL: skip_tutorial}):
            return _check_launcher_prefs()

    def test_no_licence_key_fails_and_its_value_is_never_read(self) -> None:
        result = self._check({"serial": False, "controls/Version": True})
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("licence key", result["detail"])

    def test_no_stored_controls_warns_of_the_dialog(self) -> None:
        result = self._check({"serial": True, "controls/Version": False}, skip_tutorial=None)
        self.assertEqual(result["status"], "WARN")
        self.assertIn("Key configuration options have changed", result["detail"])
        self.assertIn("canSkipTutorial", result["detail"])  # noted: live runs pin it

    def test_a_played_machine_passes_and_another_platform_is_skipped(self) -> None:
        self.assertEqual(self._check({"serial": True, "controls/Version": True})["status"], "PASS")
        self.assertEqual(self._check({"serial": None, "controls/Version": None})["status"], "SKIPPED")


if __name__ == "__main__":
    unittest.main()
