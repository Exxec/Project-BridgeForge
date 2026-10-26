"""Graceful close when the probe's done marker appears (item 75 R1): fakes only, no game, no window."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import graceful_exit
from bridgeforge import launch
from bridgeforge.live import live_run
from bridgeforge.exit_observation import KILLED, NATURAL, read_exit_observation
from tests.bound_runs import make_rig, stage
from tests.support import resolved_temp_dir
from tests.test_run_manifest import _two


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _marker(rig: Path, manifest_id: str) -> None:
    path = graceful_exit.done_path(rig)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"manifest_id": manifest_id}), encoding="utf-8")


class WaitForDoneTests(unittest.TestCase):
    def test_a_marker_for_this_manifest_is_seen(self) -> None:
        with resolved_temp_dir() as rig:
            _marker(rig, "abc")
            self.assertTrue(graceful_exit.wait_for_done(rig, "abc", 5, sleep=Clock().sleep, clock=Clock()))

    def test_a_marker_naming_another_manifest_is_never_accepted(self) -> None:
        with resolved_temp_dir() as rig:
            _marker(rig, "other")
            clock = Clock()
            self.assertFalse(graceful_exit.wait_for_done(rig, "abc", 5, sleep=clock.sleep, clock=clock))
            self.assertGreaterEqual(clock.now, 5)

    def test_no_marker_times_out_and_clear_done_removes_a_stale_one(self) -> None:
        with resolved_temp_dir() as rig:
            clock = Clock()
            self.assertFalse(graceful_exit.wait_for_done(rig, "abc", 3, sleep=clock.sleep, clock=clock))
            _marker(rig, "abc")
            graceful_exit.clear_done(rig)
            self.assertIsNone(graceful_exit.read_done(rig))


class GracefulCloseTests(unittest.TestCase):
    def _close(self, rig: Path, *, closes: bool, exits_after: int | None, code: int = 0, java_left: bool = False):
        clock = Clock()
        polls = {"n": 0}

        class Proc:
            def poll(self):
                polls["n"] += 1
                return code if exits_after is not None and polls["n"] > exits_after else None

        sent: list[set[int]] = []
        result = graceful_exit.graceful_close(
            rig, "abc", Proc(), settle=live_run.settle_exit, pids=lambda: {7}, java_left=lambda: java_left,
            close=lambda pids: sent.append(pids) or closes, done_wait=3, close_wait=20, sleep=clock.sleep, clock=clock)
        return result, sent

    def test_marker_then_close_then_exit_is_natural_with_the_code(self) -> None:
        with resolved_temp_dir() as rig:
            _marker(rig, "abc")
            result, sent = self._close(rig, closes=True, exits_after=3, code=0)
        self.assertEqual(result, (NATURAL, 0))
        self.assertEqual(sent, [{7}])

    def test_no_marker_means_no_close_and_killed(self) -> None:
        with resolved_temp_dir() as rig:
            result, sent = self._close(rig, closes=True, exits_after=0)
        self.assertEqual(result, (KILLED, None))
        self.assertEqual(sent, [])

    def test_a_game_that_stays_up_after_the_close_is_killed(self) -> None:
        with resolved_temp_dir() as rig:
            _marker(rig, "abc")
            result, _ = self._close(rig, closes=True, exits_after=None)
        self.assertEqual(result, (KILLED, None))

    def test_no_window_is_killed(self) -> None:
        with resolved_temp_dir() as rig:
            _marker(rig, "abc")
            result, _ = self._close(rig, closes=False, exits_after=0)
        self.assertEqual(result, (KILLED, None))

    def test_a_java_left_behind_is_killed_even_with_a_code(self) -> None:
        with resolved_temp_dir() as rig:
            _marker(rig, "abc")
            result, _ = self._close(rig, closes=True, exits_after=0, code=0, java_left=True)
        self.assertEqual(result, (KILLED, None))


class RunningGameTests(unittest.TestCase):
    def _run(self, *, marker: bool, await_exit: bool = True, graceful: bool = True):
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, {"mod_b": targets["mod_b"]}, ["lib"])
            (rig / "run-j25-direct.bat").write_text("@echo off", encoding="utf-8")
            state = {"closed": False}

            class Proc:
                pid = 1

                def poll(self):
                    return 5 if state["closed"] else None

            def fake_close(pids):
                state["closed"] = True
                return True

            outcome: dict = {}
            with mock.patch("bridgeforge.boot_test._running_java_under", return_value=[]), \
                    mock.patch("bridgeforge.rig.rig_prefs.pinned_launcher_prefs", mock.MagicMock()), \
                    mock.patch.object(launch.subprocess, "Popen", lambda *a, **k: Proc()), \
                    mock.patch.object(live_run, "real_hands", lambda rig_, pid: mock.MagicMock()), \
                    mock.patch("bridgeforge.launcher_click.descendant_pids", return_value=set()), \
                    mock.patch.object(graceful_exit, "post_close", fake_close), \
                    mock.patch.object(live_run, "_terminate_tree", create=True), \
                    mock.patch("bridgeforge.boot_test._terminate_tree"):
                with live_run.running_game(rig, "G-1", outcome=outcome, graceful_exit=graceful):
                    from bridgeforge.run_manifest import read_manifest

                    if marker:
                        _marker(rig, read_manifest(rig, "G-1")["manifest_id"])
                    outcome["await_exit"] = await_exit
            return read_exit_observation(rig, "G-1")

    def test_default_run_with_the_marker_records_natural_with_the_code(self) -> None:
        self.assertEqual(self._run(marker=True), (NATURAL, 5))

    def test_without_the_marker_the_fallback_is_killed(self) -> None:
        with mock.patch.object(graceful_exit, "DONE_WAIT_SECONDS", 0):
            self.assertEqual(self._run(marker=False), (KILLED, None))

    def test_a_stuck_run_records_nothing(self) -> None:
        self.assertEqual(self._run(marker=True, await_exit=False)[0], "UNKNOWN")

    def test_opting_out_records_nothing(self) -> None:
        self.assertEqual(self._run(marker=True, graceful=False)[0], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
