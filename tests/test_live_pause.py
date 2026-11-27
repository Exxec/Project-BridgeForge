"""ROADMAP-3 98.16: a pause the code enforces. On 2026-11-26 the owner paused live testing at about 20:05, and an idle gate
already polling in the background launched RC9NC-LIVE4 at 22:03 anyway."""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

import tests.support  # noqa: F401  (registry guard, environment, and the suite's own pause-flag path)
from bridgeforge.live import pause
from tests.support import resolved_temp_dir


class PauseFlagTests(unittest.TestCase):
    def test_pause_then_resume(self) -> None:
        with resolved_temp_dir() as state:
            self.assertIsNone(pause.refusal(state=state))
            record = pause.pause("owner: Pause live testing.", state=state)
            text = pause.refusal(state=state)
            self.assertTrue(pause.resume(state=state))
            self.assertFalse(pause.resume(state=state))
            self.assertIsNone(pause.refusal(state=state))
        self.assertIn("owner: Pause live testing.", text)
        self.assertIn(record["paused_at"], text)
        self.assertIn("live resume", text)

    def test_an_unreadable_flag_still_pauses(self) -> None:
        with resolved_temp_dir() as state:
            pause.pause_file(state).write_text("{not json", encoding="utf-8")
            text = pause.refusal(state=state)
        self.assertIn("cannot be read", text)

    def test_the_suite_never_reads_the_machines_flag(self) -> None:
        # tests/support.py points the flag at a temporary path, so a paused Test1 cannot fail these tests.
        self.assertIn("bf-suite-pause-", os.environ[pause.PAUSE_FILE_ENV])
        self.assertEqual(pause.pause_file(), Path(os.environ[pause.PAUSE_FILE_ENV]))


class EnforcedTests(unittest.TestCase):
    def _paused(self, folder: Path):
        flag = folder / "live-paused.json"
        pause.pause("owner: Pause live testing.", state=folder)
        return mock.patch.dict(os.environ, {pause.PAUSE_FILE_ENV: str(flag)})

    def test_running_game_refuses_before_it_looks_at_the_rig(self) -> None:
        from bridgeforge.live import live_run

        with resolved_temp_dir() as folder, self._paused(folder):
            with self.assertRaises(live_run.GameRefused) as refused:
                with live_run.running_game(folder / "no-such-rig", "T"):
                    self.fail("a paused machine started a game")
        self.assertIn("live testing is paused", str(refused.exception))

    def test_a_live_run_ends_refused(self) -> None:
        from bridgeforge.live import live_run

        with resolved_temp_dir() as folder, self._paused(folder):
            result = live_run.live_run(folder / "no-such-rig", "T")
        self.assertEqual((result.verdict, result.stage), ("LIVE_STUCK", "refused"))
        self.assertIn("live testing is paused", result.detail)

    def test_a_boot_test_is_refused(self) -> None:
        from bridgeforge.boot_test import run_boot_test

        with resolved_temp_dir() as folder, self._paused(folder):
            result = run_boot_test(folder / "no-such-rig", ["demo"])
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("live testing is paused", result["reason"])

    def test_cli_pause_status_resume(self) -> None:
        with resolved_temp_dir() as folder, mock.patch.dict(os.environ, {pause.PAUSE_FILE_ENV: str(folder / "live-paused.json")}):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                pause.run_cli(argparse.Namespace(live_action="pause", reason="owner: Pause live testing."))
                pause.run_cli(argparse.Namespace(live_action="status"))
                pause.run_cli(argparse.Namespace(live_action="resume"))
                pause.run_cli(argparse.Namespace(live_action="status"))
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("Live testing paused at"))
        self.assertTrue(lines[1].startswith("PAUSED since"))
        self.assertEqual(lines[2:], ["Live testing resumed.", "not paused"])


if __name__ == "__main__":
    unittest.main()
