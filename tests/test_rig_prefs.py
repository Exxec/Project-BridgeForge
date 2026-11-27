"""rig_prefs: the rig pins the shared launcher resolution and gives the owner's setting back (2026-10-11)."""
from __future__ import annotations

import sys
import unittest

import tests.support  # noqa: F401  installs the registry guard when this module runs alone (96.5 C4)
from unittest import mock

from bridgeforge.rig import rig_prefs


class PinnedPrefsTests(unittest.TestCase):
    def setUp(self) -> None:
        # These tests are about the pinned values; the other values (98.23 a) are OwnerPrefsTests'.
        patcher = mock.patch.object(rig_prefs, "pref_names", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

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


class OwnerPrefsTests(unittest.TestCase):
    """ROADMAP-3 98.23 a: on White_Legion, the owner's own desktop, every run moved `continue` (the owner's last save) to the
    rig's save; the harness gave back only the values it pins. Every other value now comes back, and the licence key, which
    shares the store, is never read, compared or written."""

    def _patched(self, store: dict[str, str]):
        def read(names):
            if any(name.lower() == "serial" for name in names):
                raise AssertionError("the licence key was read")
            return {name: store.get(name) for name in names}

        def write(values):
            if any(name.lower() == "serial" for name in values):
                raise AssertionError("the licence key was written")
            for name, value in values.items():
                if value is None:
                    store.pop(name, None)
                else:
                    store[name] = value

        return (mock.patch.object(rig_prefs, "read_prefs", side_effect=read), mock.patch.object(rig_prefs, "write_prefs", side_effect=write),
                mock.patch.object(rig_prefs, "pref_names", side_effect=lambda key_path=rig_prefs.PREFS_KEY: list(store)))

    def test_what_the_run_changed_added_or_removed_comes_back_and_the_licence_key_is_never_touched(self) -> None:
        store = {"resolution": "1920x1080", "fullscreen": "false", "continue": "..////saves\\owner_save", "controls1": "keys",
                 "serial": "the licence key"}
        read, write, names = self._patched(store)
        with read, write, names:
            with rig_prefs.pinned_launcher_prefs(rig_prefs.LIVE_PINNED):
                self.assertEqual(store["resolution"], "1920x1440")
                store["continue"] = "..////saves\\rig_save"  # the run's save, as on every White_Legion run of 2026-11-27
                store["new/Value"] = "made by the run"
                del store["controls1"]
                store["serial"] = "changed by the game"
        self.assertEqual(store, {"resolution": "1920x1080", "fullscreen": "false", "continue": "..////saves\\owner_save",
                                 "controls1": "keys", "serial": "changed by the game"})

    def test_the_other_values_come_back_after_an_error_too(self) -> None:
        store = {"resolution": "1920x1080", "continue": "owner"}
        read, write, names = self._patched(store)
        with read, write, names, self.assertRaises(RuntimeError):
            with rig_prefs.pinned_launcher_prefs():
                store["continue"] = "rig"
                raise RuntimeError("the game crashed")
        self.assertEqual(store["continue"], "owner")

    def test_owner_prefs_reads_every_value_but_the_licence_key(self) -> None:
        with mock.patch.object(rig_prefs, "pref_names", return_value=["continue", "serial", "Serial", "resolution"]), \
                mock.patch.object(rig_prefs, "read_prefs", side_effect=lambda names: dict.fromkeys(names, "v")) as read:
            values = rig_prefs.owner_prefs()
        self.assertEqual(sorted(values), ["continue", "resolution"])
        self.assertEqual(sorted(read.call_args.args[0]), ["continue", "resolution"])

    def test_kept_values_come_back_once_after_the_outermost_hold(self) -> None:
        store = {"continue": "owner", "serial": "the licence key"}
        read, write, names = self._patched(store)
        with read, write, names:
            with rig_prefs.owner_prefs_kept():
                with rig_prefs.owner_prefs_kept():
                    store["continue"] = "rig"
                self.assertEqual(store["continue"], "rig")  # the inner hold gives nothing back
        self.assertEqual(store, {"continue": "owner", "serial": "the licence key"})


class SaveReloadPrefsTests(unittest.TestCase):
    """Review of #269: `probe-group live --save-reload` starts the game twice. The first launch saves (the game moves `continue`
    to the rig's save) and the reload clicks Continue, which loads the last save (RC8-29). Each launch gave every value back,
    so the reload started with `continue` naming the owner's save. The real pinned_launcher_prefs runs in both fake launches."""

    _patched = OwnerPrefsTests._patched
    OWNER = {"resolution": "1920x1080", "continue": "..////saves\\owner_save", "serial": "the licence key"}

    def _probe_live(self, first, reload) -> mock.Mock:
        import argparse
        import contextlib
        import io
        from pathlib import Path

        from bridgeforge.live import live_run
        from bridgeforge.probe import cmd_probe_group
        from bridgeforge.save import save_reload_run

        args = argparse.Namespace(interactive=False, save_reload=True, json=False, test_id="T1", bat="run.bat", menu_timeout=1,
                                  natural_exit=False, exit_wait=1, no_graceful_close=False)
        with mock.patch.object(live_run, "live_run", side_effect=first), \
                mock.patch.object(save_reload_run, "save_reload_configured", return_value=True), \
                mock.patch.object(save_reload_run, "clear_stale_fingerprint"), \
                mock.patch.object(save_reload_run, "reload_run", side_effect=reload) as reloaded, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cmd_probe_group._probe_live(args, Path("queue"), Path("rig"))
        return reloaded

    def _launch(self, store: dict, then):
        """A fake launch inside the real pinned_launcher_prefs; `then(store)` is what the game did."""
        from bridgeforge.live.live_run import LiveResult

        def launch(*_args, **_kwargs):
            with rig_prefs.pinned_launcher_prefs(rig_prefs.LIVE_PINNED):
                return then(store) or LiveResult("LIVE_DONE", log=None)
        return launch

    def test_the_reload_starts_with_the_rigs_save_and_the_owners_values_come_back_after_it(self) -> None:
        store, seen = dict(self.OWNER), []
        read, write, names = self._patched(store)
        with read, write, names:
            self._probe_live(self._launch(store, lambda s: s.update({"continue": "..////saves\\rig_save"})),
                             self._launch(store, lambda s: seen.append((s["continue"], s["resolution"]))))
        self.assertEqual(seen, [("..////saves\\rig_save", "1920x1440")])
        self.assertEqual(store, self.OWNER)

    def test_a_first_launch_that_fails_or_does_not_finish_still_gives_everything_back(self) -> None:
        from bridgeforge.live.live_run import LiveResult

        def crash(s):
            s["continue"] = "rig"
            raise RuntimeError("the game crashed")

        def stuck(s):
            s["continue"] = "rig"
            return LiveResult("LIVE_STUCK", "campaign", "x", log=None)

        store = dict(self.OWNER)
        read, write, names = self._patched(store)
        with read, write, names, self.assertRaises(RuntimeError):
            self._probe_live(self._launch(store, crash), self._launch(store, lambda s: None))
        self.assertEqual(store, self.OWNER)
        with read, write, names:
            reloaded = self._probe_live(self._launch(store, stuck), self._launch(store, lambda s: None))
        self.assertEqual((store, reloaded.call_count), (self.OWNER, 0))


@unittest.skipUnless(sys.platform == "win32", "the Windows registry")
class PrefNamesTests(unittest.TestCase):
    """98.23 a: the names are listed without reading any value (winreg.EnumValue would return each value's data, the licence
    key's too)."""

    KEY = r"Software\BridgeForgeTests\pref_names"

    def tearDown(self) -> None:
        import winreg

        for path in (self.KEY, r"Software\BridgeForgeTests"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except OSError:
                pass

    def test_names_are_listed_without_reading_a_value(self) -> None:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY) as key:
            for name in ("serial", "continue", "can/Skip/Tutorial"):
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, "a value no listing may read")
        with mock.patch("winreg.QueryValueEx", side_effect=AssertionError("a preference value was read")), \
                mock.patch("winreg.EnumValue", side_effect=AssertionError("a preference value was read")):
            names = rig_prefs.pref_names(key_path=self.KEY)
            none = rig_prefs.pref_names(key_path=self.KEY + r"\missing")
        self.assertEqual((sorted(names), none), (["can/Skip/Tutorial", "continue", "serial"], []))

    def test_a_listing_error_is_raised_not_taken_for_the_end_of_the_list(self) -> None:
        """Review of #269: a short list taken as complete made the restore delete every owner value it missed."""
        import ctypes
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY):
            pass

        def enum(_handle, index, buffer, *_rest):
            if index == 0:
                buffer.value = "continue"
                return 0
            return 6  # ERROR_INVALID_HANDLE

        with mock.patch.object(ctypes.windll.advapi32, "RegEnumValueW", enum), self.assertRaises(OSError) as raised:
            rig_prefs.pref_names(key_path=self.KEY)
        self.assertIn("after 1 name(s)", str(raised.exception))


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
