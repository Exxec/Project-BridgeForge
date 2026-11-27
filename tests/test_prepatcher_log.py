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


AGENT = "../mods/StarsectorPrepatcher/agent/StarsectorPrepatcherAgent.jar"  # as Test1's run-j25-frpp.bat names it (2026-11-27)


def _launcher(rig: Path, agent: str | None) -> Path:
    """A rig launcher whose java line loads `agent` as the last -javaagent, or no Prepatcher agent."""
    bat = rig / "run.bat"
    agents = "-javaagent:fast_rendering/fr.jar" + (f" -javaagent:{agent}" if agent else "")
    bat.write_text(f'@echo off\ncd starsector-core\n"C:\\jdk\\bin\\java.exe" {agents} -Xmx4g -cp x com.fs.starfarer.StarfarerLauncher\n',
                   encoding="utf-8")
    return bat


class LauncherDecidesTests(unittest.TestCase):
    """Review, 2026-11-27: the agent is switched on by -javaagent, not by enabled_mods.json, which probe-group install rewrites."""

    def test_an_agent_on_the_java_line_is_summarised_even_when_the_mod_is_not_enabled(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["lw_lazylib"], OLD + CLEAN)
            found = prepatcher_log.summary(rig, SINCE, _launcher(rig, AGENT))
        self.assertEqual((found["verdict"], found["applied"]), ("CLEAN", 2))
        self.assertTrue(found["log"].replace("\\", "/").endswith("mods/StarsectorPrepatcher/logs/prepatcher.log"), found["log"])

    def test_an_enabled_mod_without_the_agent_on_the_line_is_not_loaded(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], OLD + CLEAN)
            found = prepatcher_log.summary(rig, SINCE, _launcher(rig, None))
            plain = _rig(root / "b", ["lw_lazylib"], CLEAN)
            nothing = prepatcher_log.summary(plain, SINCE, _launcher(plain, None))
        self.assertEqual(found["verdict"], "NOT_LOADED")
        self.assertIn("loads no Prepatcher agent", prepatcher_log.describe(found))
        self.assertIsNone(nothing)

    def test_an_agent_after_the_main_class_is_not_loaded(self) -> None:
        # The JVM reads a -javaagent after the main class as an application argument (java-matrix --prepatcher, 2026-10-12).
        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], OLD + CLEAN)
            bat = rig / "late.bat"
            bat.write_text(f'"C:\\jdk\\bin\\java.exe" -Xmx4g -cp x com.fs.starfarer.StarfarerLauncher -javaagent:{AGENT}\n', encoding="utf-8")
            self.assertEqual(prepatcher_log.launch_agents(bat), [])
            self.assertEqual(prepatcher_log.summary(rig, SINCE, bat)["verdict"], "NOT_LOADED")

    def test_the_agents_log_is_its_mod_folders(self) -> None:
        with resolved_temp_dir() as root:
            self.assertEqual(prepatcher_log.agent_log(root, AGENT),
                             root / "starsector-core" / "../mods/StarsectorPrepatcher" / "logs" / "prepatcher.log")
            absolute = root / "elsewhere" / "PP" / "agent" / "StarsectorPrepatcherAgent.jar"
            self.assertEqual(prepatcher_log.agent_log(root, str(absolute)), root / "elsewhere" / "PP" / "logs" / "prepatcher.log")

    def test_an_unreadable_launcher_falls_back_to_the_mod_list(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], OLD + CLEAN)
            self.assertIsNone(prepatcher_log.launch_agents(rig / "missing.bat"))
            self.assertEqual(prepatcher_log.summary(rig, SINCE, rig / "missing.bat")["verdict"], "CLEAN")


class SummariseTests(unittest.TestCase):
    def test_a_hook_without_a_class_is_a_patch_applied(self) -> None:
        # RC9SA-SR2: 65 APPLIED lines, one of them "APPLIED AoTD economy-restore completion hook" (review, 2026-11-27)
        found = prepatcher_log.summarise(CLEAN + "2026-11-27T05:43:11Z [INFO] APPLIED AoTD economy-restore completion hook\n", SINCE)
        self.assertEqual((found["applied"], found["classes"]), (3, 2))

    def test_nothing_applied_or_no_start_is_not_clean(self) -> None:
        start = "2026-11-27T05:43:06Z [INFO] StarsectorPrepatcher 0.18.9 javaagent starting\n"
        self.assertEqual(prepatcher_log.summarise(start, SINCE)["verdict"], "NOTHING_APPLIED")
        no_start = "".join(line + "\n" for line in CLEAN.splitlines()[1:])
        self.assertEqual(prepatcher_log.summarise(no_start, SINCE)["verdict"], "NO_START")

    def test_the_window_floors_stamps_to_the_second(self) -> None:
        # The run's start is taken in whole seconds; a stamp in that second belongs to it, one a moment earlier does not.
        text = ("2026-11-27T05:42:59.999999999Z [INFO] StarsectorPrepatcher 0.18.8 javaagent starting\n"
                "2026-11-27T05:43:00.000000001Z [INFO] StarsectorPrepatcher 0.18.9 javaagent starting\n")
        found = prepatcher_log.summarise(text, SINCE)
        self.assertEqual((found["starts"], found["version"]), (1, "0.18.9"))
        self.assertEqual(prepatcher_log.run_started().microsecond, 0)

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

    def test_the_window_starts_before_the_launch(self) -> None:
        # The clock moves on during the run: a start taken after it would miss the run's own lines (review, 2026-11-27).
        clock = [SINCE]

        def play(*_args, **_kwargs):
            clock[0] = datetime(2026, 11, 27, 6, 30, tzinfo=timezone.utc)  # the run took 47 minutes
            return LiveResult("LIVE_DONE")

        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], OLD + CLEAN)
            with mock.patch.object(prepatcher_log, "run_started", lambda: clock[0]):
                with mock.patch.object(live_run, "_live_run", play):
                    first = live_run.live_run(rig, "T1")
                clock[0] = SINCE
                with mock.patch.object(save_reload_run, "_reload", play):
                    reload = save_reload_run.reload_run(rig, "T1-reload")
        self.assertEqual((first.prepatcher["verdict"], reload.prepatcher["verdict"]), ("CLEAN", "CLEAN"))

    def test_no_game_process_and_a_failing_summary(self) -> None:
        with resolved_temp_dir() as root:
            rig = _rig(root, ["starsector_prepatcher"], CLEAN)
            with mock.patch.object(live_run, "_live_run", return_value=LiveResult("LIVE_STUCK", "LAUNCH_NO_PROCESS", "no java")):
                none_started = live_run.live_run(rig, "T1")
            (rig / "mods" / "StarsectorPrepatcher" / "logs" / "prepatcher.log").write_text(
                "2026-13-45T99:99:99Z [INFO] StarsectorPrepatcher 0.18.9 javaagent starting\n", encoding="utf-8")
            with mock.patch.object(live_run, "_live_run", return_value=LiveResult("LIVE_DONE")):
                bad_stamp = live_run.live_run(rig, "T1")
            with mock.patch.object(prepatcher_log, "_read", return_value=None):  # the file exists and cannot be read
                unreadable = prepatcher_log.summary(rig, SINCE)
            self.assertIsNone(prepatcher_log._read(rig))  # a folder: the OSError is caught
        self.assertIsNone(none_started.prepatcher)
        self.assertEqual((bad_stamp.verdict, bad_stamp.prepatcher["verdict"]), ("LIVE_DONE", "UNREADABLE"))
        self.assertIn("ValueError", bad_stamp.prepatcher["error"])
        self.assertEqual(unreadable["verdict"], "UNREADABLE")

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

    def test_after_a_failed_reload_the_first_launchs_line_says_whose_it_is(self) -> None:
        # Review, 2026-11-27: the verdict printed is the reload's, and the first launch's summary stood under it unlabelled.
        import argparse
        import contextlib
        import io

        from bridgeforge.probe import cmd_probe_group

        args = argparse.Namespace(interactive=False, save_reload=True, json=False, test_id="T1", bat="run.bat", menu_timeout=1,
                                  natural_exit=False, exit_wait=1, no_graceful_close=False)
        first = LiveResult("LIVE_DONE", log="T1.stdout.log", prepatcher=prepatcher_log.summarise(CLEAN, SINCE))
        reloaded = LiveResult("LIVE_STUCK", "main-menu", "reload never reached the menu", prepatcher={"verdict": "NO_LOG"})
        out = io.StringIO()
        with mock.patch.object(live_run, "live_run", return_value=first), \
                mock.patch.object(save_reload_run, "save_reload_configured", return_value=True), \
                mock.patch.object(save_reload_run, "clear_stale_fingerprint"), \
                mock.patch.object(save_reload_run, "reload_run", return_value=reloaded), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            cmd_probe_group._probe_live(args, Path("queue"), Path("rig"))
        text = out.getvalue()
        self.assertIn("  reload prepatcher: NO_LOG", text)
        self.assertIn("  first launch: prepatcher 0.18.9: CLEAN", text)

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
