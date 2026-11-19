"""ROADMAP-3 95.4: the direct start that live-wrappers/live_direct.py and smoke_direct.py patched in, built into the harness."""
from __future__ import annotations

import argparse
import unittest
from unittest import mock

from bridgeforge import launch
from bridgeforge.live import live_run
from bridgeforge.live.direct_start import DirectStart, place_window
from bridgeforge.probe.cmd_probe_group import _direct_from
from tests.bound_runs import make_rig, stage
from tests.support import resolved_temp_dir
from tests.test_run_manifest import _two


class DirectStartTests(unittest.TestCase):
    def test_options_env_and_pins(self) -> None:
        direct = DirectStart("1920x1440", -200)
        self.assertEqual(direct.java_options(), "-DlaunchDirect=true -DstartRes=1920x1440 -DstartFS=false -DstartSound=true")
        base = {"PATH": "x", "JAVA_TOOL_OPTIONS": "-Dfoo=1"}
        env = direct.env(base)
        self.assertEqual(env["JAVA_TOOL_OPTIONS"], "-Dfoo=1 " + direct.java_options())
        self.assertEqual(base["JAVA_TOOL_OPTIONS"], "-Dfoo=1")  # the caller's environment is not changed
        self.assertEqual(DirectStart("1280x960").env({})["JAVA_TOOL_OPTIONS"], DirectStart("1280x960").java_options())
        self.assertEqual(direct.pinned_prefs({"resolution": "a", "fullscreen": "false"}),
                         {"resolution": "1920x1440", "fullscreen": "false"})

    def test_a_malformed_resolution_is_refused(self) -> None:
        for bad in ("1920", "1920x", "x1440", "1920*1440", "19x14", "1920x1440 -Devil=1"):
            with self.subTest(bad), self.assertRaises(ValueError):
                DirectStart(bad)

    def test_without_a_client_top_nothing_is_moved(self) -> None:
        self.assertEqual(place_window(None, None, None), "direct start: no launcher to click")

    def test_start_game_gives_the_environment_to_the_game_process_only(self) -> None:
        seen = {}
        with mock.patch.object(launch.subprocess, "Popen", lambda *a, **k: seen.update(k)):
            with resolved_temp_dir() as root:
                launch.start_game(root, root / "run.bat", root / "o.log", root / "e.log", env={"JAVA_TOOL_OPTIONS": "-Dx=1"})
                self.assertEqual(seen["env"], {"JAVA_TOOL_OPTIONS": "-Dx=1"})
                launch.start_game(root, root / "run.bat", root / "o.log", root / "e.log")
                self.assertIsNone(seen["env"])

    def test_cli_arguments(self) -> None:
        ns = argparse.Namespace
        self.assertIsNone(_direct_from(ns(direct=False, resolution="1920x1440", client_top=None)))
        self.assertEqual(_direct_from(ns(direct=True, resolution="1920x1440", client_top=-200)), DirectStart("1920x1440", -200))
        with self.assertRaisesRegex(ValueError, "only with --direct"):
            _direct_from(ns(direct=False, resolution="1920x1440", client_top=-200))
        with self.assertRaises(ValueError):
            _direct_from(ns(direct=True, resolution="big", client_top=None))


class ReloadDirectTests(unittest.TestCase):
    def test_the_reload_start_is_direct_too(self) -> None:
        # The SEEKER and Station Augments save-reload gates need --save-reload with --direct on Test1 (2026-11-19).
        import contextlib

        from bridgeforge.save import save_reload_run

        seen = {}

        @contextlib.contextmanager
        def fake_running_game(rig, test_id, bat_name, **kwargs):
            seen.update(kwargs)
            yield None, None, 0

        direct = DirectStart("1920x1440", -200)
        with mock.patch.object(save_reload_run, "running_game", fake_running_game), \
                mock.patch.object(save_reload_run, "drive_reload", lambda *a, **k: "result"):
            self.assertEqual(save_reload_run.reload_run(None, "T-reload", direct=direct), "result")
        self.assertEqual(seen["direct"], direct)


class RunningGameDirectTests(unittest.TestCase):
    def _run(self, direct):
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, {"mod_b": targets["mod_b"]}, ["lib"])
            (rig / "run-j25-direct.bat").write_text("@echo off", encoding="utf-8")
            calls = {"popen": None, "clicked": 0, "placed": [], "pinned": []}

            class Proc:
                pid = 1

                def poll(self):
                    return 0

            def popen(*args, **kwargs):
                calls["popen"] = kwargs.get("env")
                return Proc()

            def click(rig_, proc):
                calls["clicked"] += 1
                return "clicked Play"

            def place(rig_, proc, top):
                calls["placed"].append(top)
                return "placed"

            def pin(values=None):
                calls["pinned"].append(values)
                return mock.MagicMock()

            with mock.patch("bridgeforge.boot_test._running_java_under", return_value=[]), \
                    mock.patch("bridgeforge.rig.rig_prefs.pinned_launcher_prefs", pin), \
                    mock.patch.object(launch.subprocess, "Popen", popen), \
                    mock.patch.object(launch, "click_launcher", click), \
                    mock.patch("bridgeforge.live.direct_start.place_window", place), \
                    mock.patch.object(live_run, "real_hands", lambda rig_, pid: mock.MagicMock(alive=lambda: False)), \
                    mock.patch("bridgeforge.launcher_click.descendant_pids", return_value=set()), \
                    mock.patch("bridgeforge.boot_test._terminate_tree"):
                with live_run.running_game(rig, "D-1", graceful_exit=False, direct=direct) as (_log, hands, _rows):
                    hands.alive()  # the first poll: the launcher click, or the window placement
            return calls

    def test_a_direct_start_places_the_window_and_never_clicks_the_launcher(self) -> None:
        calls = self._run(DirectStart("1920x1440", -200))
        self.assertIn("-DlaunchDirect=true -DstartRes=1920x1440", calls["popen"]["JAVA_TOOL_OPTIONS"])
        self.assertEqual((calls["clicked"], calls["placed"]), (0, [-200]))
        self.assertEqual(calls["pinned"][0]["resolution"], "1920x1440")

    def test_without_direct_the_launcher_is_clicked_as_before(self) -> None:
        calls = self._run(None)
        self.assertIsNone(calls["popen"])
        self.assertEqual((calls["clicked"], calls["placed"]), (1, []))


if __name__ == "__main__":
    unittest.main()
