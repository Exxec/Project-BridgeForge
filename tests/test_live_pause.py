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

    def test_status_says_paused_for_an_empty_record(self) -> None:
        # refusal() refuses a flag holding {}; status said "not paused", so gate_once.sh went on (review, 2026-11-27)
        with resolved_temp_dir() as folder, mock.patch.dict(os.environ, {pause.PAUSE_FILE_ENV: str(folder / "live-paused.json")}):
            (folder / "live-paused.json").write_text("{}", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                pause.run_cli(argparse.Namespace(live_action="status"))
            self.assertIsNotNone(pause.refusal())
        self.assertTrue(out.getvalue().startswith("PAUSED"))

    def test_a_runtime_smoke_execute_is_refused(self) -> None:
        import json

        from bridgeforge import runtime

        with resolved_temp_dir() as folder, self._paused(folder):
            (folder / "runtime-profile.json").write_text(json.dumps({"scenarios": ["campaign-load"]}), encoding="utf-8")
            with mock.patch.object(runtime, "workspace_paths"), \
                    mock.patch.object(runtime.subprocess, "run", side_effect=AssertionError("a paused machine started a game")):
                result = runtime.run_runtime_smoke(folder, execute=True)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("live testing is paused", result["reason"])

    def test_a_paused_queue_installs_nothing_and_keeps_its_checkpoint(self) -> None:
        import json

        from bridgeforge.live_queue import live_queue
        from bridgeforge.run_manifest import CONFIG_RELATIVE

        plan = {"groups": [{"group": 1, "members": [{"workspace": "A"}]}, {"group": 2, "members": [{"workspace": "B"}]}]}
        played: list[str] = []
        with resolved_temp_dir() as root:
            (root / "rig" / CONFIG_RELATIVE).parent.mkdir(parents=True)
            (root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            out = root / "out" / "lq.json"

            def play(_rig, test_id):  # group 1 plays, then the owner pauses
                played.append(test_id)
                pause.pause("owner: Pause live testing.", state=root)
                return mock.Mock(verdict="LIVE_STUCK", stage="combat-round-1", detail="d", log=None)

            installed: list[int] = []
            with mock.patch.dict(os.environ, {pause.PAUSE_FILE_ENV: str(root / "live-paused.json")}):
                result = live_queue(root / "plan.json", root, root / "rig", out, play=play, install=lambda _p, n: installed.append(n),
                                    judge=None, record=None, quiet=True, test_prefix="LQ")
            kept = out.with_name("lq.partial.jsonl").read_text(encoding="utf-8")
        self.assertEqual((played, installed), (["LQ-G1"], [1]))
        self.assertEqual([r["live"]["stage"] for r in result["groups"]], ["combat-round-1", "refused"])
        self.assertIn("live testing is paused", result["stopped"])
        self.assertIn('"key": "G1:A"', kept)
        self.assertNotIn('"key": "G2:', kept)  # a resumed queue plays group 2


class MachineFlagTests(unittest.TestCase):
    """The flag is the machine's, not a checkout's: the first version kept it in state_dir(), so a worktree or a run with
    another BRIDGEFORGE_DATA_ROOT read a different flag and started the game (review, 2026-11-27)."""

    def test_every_data_root_reads_the_one_flag(self) -> None:
        with resolved_temp_dir() as local:
            seen = set()
            for root in ("A", "B"):
                env = {"LOCALAPPDATA": str(local), "BRIDGEFORGE_DATA_ROOT": str(local / root)}
                with mock.patch.dict(os.environ, env), mock.patch.dict(os.environ, {pause.PAUSE_FILE_ENV: ""}):
                    seen.add(pause.pause_file())
        self.assertEqual(seen, {local / "BridgeForge" / "live-paused.json"})

    def test_without_local_app_data_the_user_state_folder(self) -> None:
        with resolved_temp_dir() as xdg, mock.patch.dict(os.environ, {"LOCALAPPDATA": "", "XDG_STATE_HOME": str(xdg), pause.PAUSE_FILE_ENV: ""}):
            self.assertEqual(pause.pause_file(), xdg / "bridgeforge" / "live-paused.json")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": "", "XDG_STATE_HOME": "", pause.PAUSE_FILE_ENV: ""}):
            self.assertEqual(pause.pause_file(), Path.home() / ".local" / "state" / "bridgeforge" / "live-paused.json")

    def test_a_flag_that_cannot_be_checked_pauses(self) -> None:
        with resolved_temp_dir() as state, mock.patch.object(Path, "stat", side_effect=PermissionError("denied")):
            self.assertIn("cannot be checked", pause.refusal(state=state))


if __name__ == "__main__":
    unittest.main()
