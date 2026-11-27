"""ROADMAP-3 98.18: every live result carries Prepatcher's own summary of the run."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bridgeforge.live import live_run, prepatcher_log
from bridgeforge.live.live_run import LiveResult
from bridgeforge.save import save_reload_run
from tests.support import resolved_temp_dir

SINCE = datetime(2026, 11, 27, 5, 43, 0, tzinfo=timezone.utc)
# The shape of RC9SA-SR2-0985a-20261126's log (Test1, 2026-11-26), cut down; the first line is an earlier start's.
OLD = "2026-11-27T05:20:01.000Z [ERROR] an earlier start's error\n"
CLEAN = (
    "2026-11-27T05:43:06.500912300Z [INFO] StarsectorPrepatcher 0.18.9 javaagent starting\n"
    "2026-11-27T05:43:06.507911300Z [INFO] Mod root: C:\\rig\\mods\\StarsectorPrepatcher\n"
    "2026-11-27T05:43:09.404025100Z [INFO] APPLIED marketScheduler to com/fs/starfarer/campaign/CampaignState: marketScheduler{x}\n"
    "2026-11-27T05:43:10.841215800Z [INFO] APPLIED marketSchedulerB to com/fs/starfarer/campaign/CampaignState: y{z}\n"
    "2026-11-27T05:43:19.081863700Z [INFO] Patched com/fs/starfarer/campaign/JumpPoint structurally: idx{epilogues=3}, bytes 15390 -> 15827\n"
)


def _rig(root: Path, enabled: list[str], log: str | None) -> Path:
    rig = root / "rig"
    folder = rig / "mods" / "StarsectorPrepatcher"
    (folder / "logs").mkdir(parents=True)
    (folder / "mod_info.json").write_text(json.dumps({"id": "starsector_prepatcher", "version": "0.18.9"}), encoding="utf-8")
    (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": enabled}), encoding="utf-8")
    if log is not None:
        (folder / "logs" / "prepatcher.log").write_text(log, encoding="utf-8")
    return rig


class SummariseTests(unittest.TestCase):
    def test_a_clean_start_counts_patches_and_classes(self) -> None:
        found = prepatcher_log.summarise(OLD + CLEAN, SINCE)
        self.assertEqual(found["verdict"], "CLEAN")
        self.assertEqual(found["version"], "0.18.9")
        self.assertEqual((found["starts"], found["lines"], found["applied"], found["classes"]), (1, 5, 2, 2))
        self.assertEqual((found["warnings"], found["errors"], found["rolled_back"], found["failed_open"]), (0, 0, 0, 0))

    def test_lines_from_before_the_run_are_not_counted(self) -> None:
        found = prepatcher_log.summarise(OLD, SINCE)
        self.assertEqual(found["verdict"], "NO_LOG")
        self.assertEqual((found["lines"], found["errors"], found["version"]), (0, 0, None))

    def test_errors_rollbacks_and_fail_open_are_problems_and_quoted(self) -> None:
        text = CLEAN + (
            "2026-11-27T05:43:20Z [WARN] slow transform\n"
            "2026-11-27T05:43:21Z [ERROR] Atomic transformer pipeline rolled back for com/fs/X\n"
            "  at the second line of the error\n"
            "2026-11-27T05:43:22Z [INFO] Trade mutation inspection/refresh failed open; the original Economy.doubleStep will run.\n")
        found = prepatcher_log.summarise(text, SINCE)
        self.assertEqual(found["verdict"], "PROBLEMS")
        self.assertEqual((found["warnings"], found["errors"], found["rolled_back"], found["failed_open"]), (1, 1, 1, 1))
        self.assertEqual(len(found["problem_lines"]), 2)  # the error that rolled back is one problem, quoted once
        self.assertIn("at the second line of the error", found["problem_lines"][0])
        self.assertIn("failed open", found["problem_lines"][1])

    def test_warnings_alone_are_quoted_and_not_clean(self) -> None:
        found = prepatcher_log.summarise(CLEAN + "2026-11-27T05:43:20Z [WARN] slow transform\n", SINCE)
        self.assertEqual(found["verdict"], "WARNINGS")
        self.assertEqual(found["problem_lines"], ["slow transform"])

    def test_problem_lines_are_capped(self) -> None:
        text = CLEAN + "".join(f"2026-11-27T05:44:{i:02d}Z [ERROR] e{i}\n" for i in range(9))
        found = prepatcher_log.summarise(text, SINCE)
        self.assertEqual((found["errors"], len(found["problem_lines"])), (9, prepatcher_log.MAX_PROBLEM_LINES))


class SummaryTests(unittest.TestCase):
    def test_a_rig_without_prepatcher_enabled_has_no_summary(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["lw_lazylib"], CLEAN)
            self.assertIsNone(prepatcher_log.summary(rig, SINCE))
            self.assertIsNone(prepatcher_log.summary(root / "no-rig", SINCE))

    def test_an_enabled_prepatcher_reports_its_log(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], OLD + CLEAN)
            found = prepatcher_log.summary(rig, SINCE)
        self.assertEqual((found["verdict"], found["applied"]), ("CLEAN", 2))
        self.assertTrue(found["log"].endswith("prepatcher.log"))

    def test_an_enabled_prepatcher_with_no_log_is_no_log(self) -> None:
        with resolved_temp_dir() as root:
            found = prepatcher_log.summary(_rig(root, ["starsector_prepatcher"], None), SINCE)
        self.assertEqual(found["verdict"], "NO_LOG")
        self.assertIn("wrote no line", prepatcher_log.describe(found))

    def test_describe(self) -> None:
        self.assertIsNone(prepatcher_log.describe(None))
        line = prepatcher_log.describe(prepatcher_log.summarise(CLEAN, SINCE))
        self.assertEqual(line, "prepatcher 0.18.9: CLEAN; applied 2 on 2 classes; WARN 0, ERROR 0, rolled back 0, failed open 0")
        self.assertIn("UNREADABLE", prepatcher_log.describe({"verdict": "UNREADABLE", "log": "x"}))


class ResultTests(unittest.TestCase):
    def test_live_run_attaches_the_summary_of_its_own_launch(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], OLD + CLEAN)
            with mock.patch.object(prepatcher_log, "run_started", return_value=SINCE), \
                    mock.patch.object(live_run, "_live_run", return_value=LiveResult("LIVE_DONE")):
                result = live_run.live_run(rig, "T1")
        self.assertEqual(result.prepatcher["applied"], 2)

    def test_a_refused_run_started_nothing_to_summarise(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], CLEAN)
            with mock.patch.object(live_run, "_live_run", return_value=LiveResult("LIVE_STUCK", "refused", "paused")):
                result = live_run.live_run(rig, "T1")
        self.assertIsNone(result.prepatcher)

    def test_the_reload_carries_the_summary_of_its_own_start(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], OLD + CLEAN)
            with mock.patch.object(prepatcher_log, "run_started", return_value=datetime(2026, 11, 27, 6, 0, tzinfo=timezone.utc)), \
                    mock.patch.object(save_reload_run, "_reload", return_value=LiveResult("LIVE_DONE")):
                result = save_reload_run.reload_run(rig, "T1-reload")
        self.assertEqual(result.prepatcher["verdict"], "NO_LOG")  # every line predates the reload's start

    def test_probe_group_live_prints_and_keeps_the_summary(self) -> None:
        import argparse
        import contextlib
        import io

        from bridgeforge.probe import cmd_probe_group

        summary = prepatcher_log.summarise(CLEAN, SINCE)
        args = argparse.Namespace(interactive=False, save_reload=False, json=False, test_id="T1", bat="run.bat", menu_timeout=1,
                                  natural_exit=False, exit_wait=1, no_graceful_close=False)
        played = LiveResult("LIVE_DONE", log="T1.stdout.log", prepatcher=summary)
        out = io.StringIO()
        with mock.patch.object(live_run, "live_run", return_value=played), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            result = cmd_probe_group._probe_live(args, Path("queue"), Path("rig"))
        self.assertEqual(result["prepatcher"], summary)
        self.assertIn("  prepatcher 0.18.9: CLEAN; applied 2 on 2 classes", out.getvalue())

    def test_a_live_queue_row_keeps_the_summary(self) -> None:
        from bridgeforge import live_queue

        summary = {"verdict": "CLEAN"}
        row: dict = {}
        live = SimpleNamespace(verdict="LIVE_STUCK", stage="main-menu", detail="d", log=None, prepatcher=summary)
        live_queue._run_group(row, {}, 1, Path("rig"), "T1", None, False, play=lambda _rig, _id: live,
                              install=lambda _plan, _n: None, judge=None, record=None)
        self.assertEqual(row["live"]["prepatcher"], summary)


if __name__ == "__main__":
    unittest.main()
