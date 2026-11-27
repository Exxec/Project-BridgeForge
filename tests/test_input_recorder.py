"""ROADMAP-3 98.13: the harness records who had the desktop during a live run, once a second, with the columns of the PowerShell
recorder used for 98.4 (2026-11-26). No screenshot and no window title is taken."""
from __future__ import annotations

import time
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.live import input_recorder as rec
from tests.support import resolved_temp_dir


def _csv(kinds: list[str]) -> str:
    return rec.HEADER + "\n" + "".join(f"00:00:{i:02d},{i},{i},0,1,2,{kind}\n" for i, kind in enumerate(kinds))


class RowTests(unittest.TestCase):
    def test_idle_spans_the_tick_wrap(self) -> None:
        line = rec.row(5, 2 ** 32 - 5, 10, 20, "game", now=time.localtime(0))
        self.assertEqual(line.split(",")[1:], ["5", str(2 ** 32 - 5), "10", "10", "20", "game"])

    def test_the_columns_are_the_powershell_recorders(self) -> None:
        # post_run.py and the live-run skill read the foreground kind from the seventh column of either recorder's file.
        self.assertEqual(rec.HEADER, "time,tick_ms,last_input_tick_ms,idle_ms,cursor_x,cursor_y,foreground")
        self.assertEqual(rec.HEADER.split(",")[rec.KIND_COLUMN], "foreground")


class RecordingTests(unittest.TestCase):
    def test_samples_are_written_while_the_block_runs(self) -> None:
        asked: list[int] = []
        seen: list[set[int]] = []

        def pids() -> set[int]:
            asked.append(1)
            return {42}

        def sample(game: set[int]):
            seen.append(game)
            return 100, 90, 3, 4, "game"

        with resolved_temp_dir() as folder:
            path = folder / "T.stdout.log.input.csv"
            with rec.recording(path, pids, interval=0.01, sample=sample) as written:
                deadline = time.monotonic() + 5
                while len(seen) < 7 and time.monotonic() < deadline:
                    time.sleep(0.01)
            lines = path.read_text(encoding="ascii").splitlines()
        self.assertEqual(written, path)
        self.assertEqual(lines[0], rec.HEADER)
        self.assertGreaterEqual(len(lines) - 1, 7)
        self.assertTrue(all(line.endswith(",10,3,4,game") for line in lines[1:]))
        self.assertEqual(seen[0], {42})
        self.assertEqual(len(asked), -(-len(seen) // rec.PIDS_EVERY))  # re-read every fifth sample

    def test_nothing_is_recorded_outside_windows(self) -> None:
        with resolved_temp_dir() as folder, mock.patch.object(rec.sys, "platform", "linux"):
            with rec.recording(folder / "x.csv", set) as written:
                pass
            self.assertIsNone(written)
            self.assertFalse((folder / "x.csv").exists())

    def test_a_file_that_cannot_be_written_never_stops_the_run(self) -> None:
        with resolved_temp_dir() as folder:
            with rec.recording(folder / "missing" / "x.csv", set, interval=0.01, sample=lambda _pids: (1, 1, 0, 0, "game")):
                time.sleep(0.05)
        # no exception reached the block

    def test_a_failing_sample_never_stops_the_run(self) -> None:
        def broken(_pids):
            raise OSError("user32 said no")

        with resolved_temp_dir() as folder:
            with rec.recording(folder / "x.csv", set, interval=0.01, sample=broken):
                time.sleep(0.05)
            self.assertEqual((folder / "x.csv").read_text(encoding="ascii"), rec.HEADER + "\n")


class SummaryTests(unittest.TestCase):
    def test_away_counts_only_while_the_game_ran(self) -> None:
        # The launcher before the game and the desktop after it are not "away"; the 2 s in the middle are.
        kinds = ["other"] * 3 + ["game"] * 4 + ["other"] * 2 + ["game"] * 5 + ["none"] * 1 + ["other"] * 6
        with resolved_temp_dir() as folder:
            (folder / "x.csv").write_text(_csv(kinds), encoding="ascii")
            found = rec.summary(folder / "x.csv")
        self.assertEqual(found["segments"], "other 3s | game 4s | other 2s | game 5s | none 1s | other 6s")
        self.assertEqual((found["samples"], found["away_seconds"]), (21, 2))
        self.assertIn("for 2 s while the game ran", rec.describe(found))

    def test_an_unbroken_game_is_plain(self) -> None:
        with resolved_temp_dir() as folder:
            (folder / "x.csv").write_text(_csv(["other", "game", "game", "other"]), encoding="ascii")
            found = rec.summary(folder / "x.csv")
        self.assertEqual(found["away_seconds"], 0)
        self.assertEqual(rec.describe(found), "desktop: other 1s | game 2s | other 1s")

    def test_no_game_at_all_and_no_file(self) -> None:
        with resolved_temp_dir() as folder:
            (folder / "x.csv").write_text(_csv(["other", "other"]), encoding="ascii")
            self.assertEqual(rec.summary(folder / "x.csv")["away_seconds"], 0)
            self.assertIsNone(rec.summary(folder / "missing.csv"))
        self.assertIsNone(rec.describe(None))

    def test_the_ninety_eight_point_four_record_reads_the_same(self) -> None:
        # RC9SA-SR2 (Test1, 2026-11-26) read "other 6s | game 305s | other 62s | game 84s | other 1s" from the PowerShell
        # recorder. That recorder spanned the run and its reload, so the 62 s between the two launches reads as away; the
        # harness writes one file per launch, which has no such gap.
        kinds = ["other"] * 6 + ["game"] * 305 + ["other"] * 62 + ["game"] * 84 + ["other"]
        with resolved_temp_dir() as folder:
            (folder / "x.csv").write_text(_csv(kinds), encoding="ascii")
            found = rec.summary(Path(folder / "x.csv"))
        self.assertEqual(found["segments"], "other 6s | game 305s | other 62s | game 84s | other 1s")
        self.assertEqual(found["away_seconds"], 62)


class ResultTests(unittest.TestCase):
    def test_a_run_carries_its_desktop_record(self) -> None:
        from bridgeforge.live.live_run import LiveResult, with_evidence

        with resolved_temp_dir() as rig:
            log = rig / "T.stdout.log"
            log.write_text("", encoding="utf-8")
            Path(f"{log}.input.csv").write_text(_csv(["other", "game", "other", "game"]), encoding="ascii")
            done = with_evidence(LiveResult("LIVE_DONE", log=str(log)), rig, None)
            refused = with_evidence(LiveResult("LIVE_STUCK", "refused", "paused", log=str(log)), rig, None)
            none_written = with_evidence(LiveResult("LIVE_DONE", log=str(rig / "other.stdout.log")), rig, None)
        self.assertEqual((done.desktop["segments"], done.desktop["away_seconds"]), ("other 1s | game 1s | other 1s | game 1s", 1))
        self.assertIsNone(refused.desktop)
        self.assertIsNone(none_written.desktop)

    def test_probe_group_live_prints_and_keeps_the_desktop_line(self) -> None:
        import argparse
        import contextlib
        import io

        from bridgeforge.live import live_run
        from bridgeforge.live.live_run import LiveResult
        from bridgeforge.probe import cmd_probe_group

        desktop = {"file": "x", "samples": 9, "segments": "game 7s | other 2s", "away_seconds": 0}
        args = argparse.Namespace(interactive=False, save_reload=False, json=False, test_id="T1", bat="run.bat", menu_timeout=1,
                                  natural_exit=False, exit_wait=1, no_graceful_close=False)
        out = io.StringIO()
        with mock.patch.object(live_run, "live_run", return_value=LiveResult("LIVE_DONE", log="T1.stdout.log", desktop=desktop)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            result = cmd_probe_group._probe_live(args, Path("queue"), Path("rig"))
        self.assertEqual(result["desktop"], desktop)
        self.assertIn("  desktop: game 7s | other 2s", out.getvalue())


if __name__ == "__main__":
    unittest.main()
