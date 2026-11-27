"""ROADMAP-3 98.13: the harness records who had the desktop during a live run, about once a second, with the columns of the
PowerShell recorder used for 98.4 (2026-11-26). No screenshot and no window title is taken."""
from __future__ import annotations

import os
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.live import input_recorder as rec
from tests.support import resolved_temp_dir


def _csv(kinds: list[str]) -> str:
    return rec.HEADER + "\n" + "".join(f"00:00:{i % 60:02d},{i},{i},0,1,2,{kind}\n" for i, kind in enumerate(kinds))


def _alive() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "bf-input-recorder" and t.is_alive()]


class FakeApi:
    def __init__(self, tick: int = 1000, last_input: int | None = 900, cursor=(3, 4), owner: int | None = 42) -> None:
        self._tick, self._last, self._cursor, self._owner = tick, last_input, cursor, owner

    def tick(self) -> int:
        return self._tick

    def last_input(self):
        return self._last

    def cursor(self):
        return self._cursor

    def foreground_owner(self):
        return self._owner


class RowTests(unittest.TestCase):
    def test_idle_spans_the_tick_wrap(self) -> None:
        line = rec.row(5, 2 ** 32 - 5, 10, 20, "game", now=time.localtime(0))
        self.assertEqual(line.split(",")[1:], ["5", str(2 ** 32 - 5), "10", "10", "20", "game"])

    def test_a_field_a_call_could_not_give_is_empty(self) -> None:
        line = rec.row(5, None, None, None, "error", now=time.localtime(0))
        self.assertEqual(line.split(",")[1:], ["5", "", "", "", "", "error"])

    def test_the_columns_are_the_powershell_recorders(self) -> None:
        # The live-run skill's post_run.py reads the foreground kind from the seventh column.
        self.assertEqual(rec.HEADER, "time,tick_ms,last_input_tick_ms,idle_ms,cursor_x,cursor_y,foreground")
        self.assertEqual(rec.HEADER.split(",")[rec.KIND_COLUMN], "foreground")


class SampleTests(unittest.TestCase):
    """Review, 2026-11-27: the calls are typed, a failed call leaves its field empty, and every kind is told apart."""

    def test_the_kinds(self) -> None:
        self.assertEqual(rec.sample(FakeApi(owner=42), {42})[4], "game")
        self.assertEqual(rec.sample(FakeApi(owner=7), {42})[4], "other")
        self.assertEqual(rec.sample(FakeApi(owner=None), {42})[4], "none")
        self.assertEqual(rec.sample(FakeApi(owner=42), set())[4], "gone")  # no game process: not running yet, or ended

    def test_a_negative_tick_is_masked_and_failed_calls_are_empty(self) -> None:
        tick, last, x, y, _kind = rec.sample(FakeApi(tick=-5, last_input=None, cursor=None), {42})
        self.assertEqual((tick, last, x, y), (2 ** 32 - 5, None, None, None))

    @unittest.skipUnless(os.name == "nt", "user32 is Windows only")
    def test_the_real_calls_answer(self) -> None:
        api = rec._User32()
        self.assertIsInstance(api.tick(), int)
        self.assertGreaterEqual(api.tick(), 0)
        self.assertIn(type(api.foreground_owner()), (int, type(None)))


class RecordingTests(unittest.TestCase):
    def _record(self, path: Path, pids, take, seconds: float = 0.1, interval: float = 0.01):
        with rec.recording(path, pids, interval=interval, take=take) as written:
            time.sleep(seconds)
        return written

    def test_samples_are_written_while_the_block_runs_and_the_thread_ends_with_it(self) -> None:
        asked: list[int] = []
        seen: list[set[int]] = []

        def pids() -> set[int]:
            asked.append(1)
            return {42}

        def take(game: set[int]):
            seen.append(game)
            return 100, 90, 3, 4, "game"

        with resolved_temp_dir() as folder, mock.patch.object(threading, "excepthook") as hook:
            path = folder / "T.stdout.log.input.csv"
            written = self._record(path, pids, take, seconds=0.15)
            self.assertEqual(_alive(), [])
            lines = path.read_text(encoding="ascii").splitlines()
        hook.assert_not_called()
        self.assertEqual(written, path)
        self.assertEqual(lines[0], rec.HEADER)
        self.assertGreaterEqual(len(lines) - 1, 7)
        self.assertTrue(all(line.endswith(",10,3,4,game") for line in lines[1:]))
        self.assertEqual(seen[0], {42})
        self.assertEqual(len(asked), -(-len(seen) // rec.PIDS_EVERY))  # re-read every fifth sample

    def test_nothing_is_recorded_outside_windows_or_when_switched_off(self) -> None:
        with resolved_temp_dir() as folder:
            with mock.patch.object(rec.sys, "platform", "linux"), rec.recording(folder / "x.csv", set) as written:
                pass
            self.assertIsNone(written)
            with mock.patch.object(rec.sys, "platform", "win32"), mock.patch.dict(os.environ, {rec.SWITCH_ENV: "off"}), \
                    rec.recording(folder / "x.csv", set) as written:
                pass
            self.assertIsNone(written)
            self.assertFalse((folder / "x.csv").exists())

    def test_a_file_that_cannot_be_written_records_nothing_and_never_stops_the_run(self) -> None:
        ran = []
        with resolved_temp_dir() as folder:
            with rec.recording(folder / "missing" / "x.csv", lambda: {42}, interval=0.01, take=lambda _p: (1, 1, 0, 0, "game")) as written:
                ran.append(True)
        self.assertEqual((written, ran, _alive()), (None, [True], []))

    def test_a_failing_sample_is_a_row_and_the_record_goes_on(self) -> None:
        calls = []

        def take(_pids):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("user32 said no")
            return 1, 1, 0, 0, "game"

        with resolved_temp_dir() as folder:
            self._record(folder / "x.csv", lambda: {42}, take, seconds=0.1)
            kinds = [line.split(",")[rec.KIND_COLUMN] for line in (folder / "x.csv").read_text(encoding="ascii").splitlines()[1:]]
            found = rec.summary(folder / "x.csv")
        self.assertEqual(kinds[:3], ["game", "error", "game"])
        self.assertEqual(found["errors"], 1)

    def test_an_earlier_record_never_passes_for_this_one(self) -> None:
        with resolved_temp_dir() as folder:
            path = folder / "x.csv"
            path.write_text(_csv(["other"] * 50), encoding="ascii")
            self._record(path, lambda: {42}, lambda _p: (1, 1, 0, 0, "game"), seconds=0.05)
            text = path.read_text(encoding="ascii")
        self.assertNotIn("other", text)

    def test_a_slow_process_lookup_writes_nothing_after_the_block(self) -> None:
        # Review, 2026-11-27: descendant_pids' PowerShell fallback can take seconds; the thread outlived the block and kept
        # writing (and held the file open, so the folder could not be removed).
        gate = threading.Event()

        def pids() -> set[int]:
            gate.wait(1.0)
            return {42}

        with resolved_temp_dir() as folder:
            path = folder / "x.csv"
            with rec.recording(path, pids, interval=0.01, take=lambda _p: (1, 1, 0, 0, "game")):
                time.sleep(0.05)  # the first lookup is still running
            gate.set()
            time.sleep(0.2)
            rows = path.read_text(encoding="ascii").splitlines()[1:]
            path.unlink()  # no handle is held
        self.assertEqual(rows, [])


class SummaryTests(unittest.TestCase):
    def test_away_counts_while_the_game_ran_including_a_takeover_to_the_end(self) -> None:
        # The launcher before the game and the desktop after it exited (`gone`) are not away; another window or none
        # between or after the game's stretches is (review, 2026-11-27: a takeover kept to the end read clean).
        kinds = ["other"] * 3 + ["game"] * 4 + ["other"] * 2 + ["game"] * 5 + ["none"] * 1 + ["other"] * 6 + ["gone"] * 4
        with resolved_temp_dir() as folder:
            (folder / "x.csv").write_text(_csv(kinds), encoding="ascii")
            found = rec.summary(folder / "x.csv")
        self.assertEqual(found["segments"], "other 3s | game 4s | other 2s | game 5s | none 1s | other 6s | gone 4s")
        self.assertEqual((found["samples"], found["away_seconds"], found["errors"]), (25, 9, 0))
        self.assertIn("not in front for 9 s while it ran", rec.describe(found))

    def test_an_unbroken_game_is_plain(self) -> None:
        with resolved_temp_dir() as folder:
            (folder / "x.csv").write_text(_csv(["other", "game", "game", "gone"]), encoding="ascii")
            found = rec.summary(folder / "x.csv")
        self.assertEqual(found["away_seconds"], 0)
        self.assertEqual(rec.describe(found), "desktop: other 1s | game 2s | gone 1s")

    def test_no_game_no_samples_and_no_file(self) -> None:
        with resolved_temp_dir() as folder:
            (folder / "x.csv").write_text(_csv(["other", "other"]), encoding="ascii")
            self.assertEqual(rec.summary(folder / "x.csv")["away_seconds"], 0)
            (folder / "h.csv").write_text(rec.HEADER + "\n", encoding="ascii")
            self.assertEqual(rec.describe(rec.summary(folder / "h.csv")), "desktop: no samples (the recorder wrote none)")
            self.assertIsNone(rec.summary(folder / "missing.csv"))
        self.assertIsNone(rec.describe(None))

    def test_the_ninety_eight_point_four_record_reads_the_same(self) -> None:
        # RC9SA-SR2 (Test1, 2026-11-26) read "other 6s | game 305s | other 62s | game 84s | other 1s" from the PowerShell
        # recorder, which spans the run and its reload and has no `gone` kind, so the 62 s between the two launches and the
        # last second read as away; the harness writes one file per launch and marks the game's absence.
        kinds = ["other"] * 6 + ["game"] * 305 + ["other"] * 62 + ["game"] * 84 + ["other"]
        with resolved_temp_dir() as folder:
            (folder / "x.csv").write_text(_csv(kinds), encoding="ascii")
            found = rec.summary(Path(folder / "x.csv"))
        self.assertEqual(found["segments"], "other 6s | game 305s | other 62s | game 84s | other 1s")
        self.assertEqual(found["away_seconds"], 63)


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

    def _probe_live(self, save_reload: bool, first, reloaded=None):
        import argparse
        import contextlib
        import io

        from bridgeforge.live import live_run
        from bridgeforge.probe import cmd_probe_group
        from bridgeforge.save import save_reload_run

        args = argparse.Namespace(interactive=False, save_reload=save_reload, json=False, test_id="T1", bat="run.bat", menu_timeout=1,
                                  natural_exit=False, exit_wait=1, no_graceful_close=False)
        out = io.StringIO()
        with mock.patch.object(live_run, "live_run", return_value=first), \
                mock.patch.object(save_reload_run, "save_reload_configured", return_value=True), \
                mock.patch.object(save_reload_run, "clear_stale_fingerprint"), \
                mock.patch.object(save_reload_run, "reload_run", return_value=reloaded), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            result = cmd_probe_group._probe_live(args, Path("queue"), Path("rig"))
        return result, out.getvalue()

    def test_probe_group_live_prints_and_keeps_the_desktop_lines(self) -> None:
        from bridgeforge.live.live_run import LiveResult

        first_desktop = {"file": "x", "samples": 9, "segments": "game 7s | gone 2s", "away_seconds": 0, "errors": 0}
        reload_desktop = {"file": "y", "samples": 5, "segments": "game 3s | other 2s", "away_seconds": 2, "errors": 0}
        result, text = self._probe_live(False, LiveResult("LIVE_DONE", log="T1.stdout.log", desktop=first_desktop))
        self.assertEqual(result["desktop"], first_desktop)
        self.assertIn("  desktop: game 7s | gone 2s", text)
        _result, text = self._probe_live(True, LiveResult("LIVE_DONE", log="T1.stdout.log", desktop=first_desktop),
                                         LiveResult("LIVE_STUCK", "main-menu", "x", log=None, desktop=reload_desktop))
        self.assertIn("  reload desktop: game 3s | other 2s: the game was not in front for 2 s", text)
        self.assertIn("  first launch: desktop: game 7s | gone 2s", text)

    def test_a_live_queue_row_keeps_the_desktop_record(self) -> None:
        from types import SimpleNamespace

        from bridgeforge import live_queue

        desktop = {"segments": "game 7s"}
        row: dict = {}
        live = SimpleNamespace(verdict="LIVE_STUCK", stage="main-menu", detail="d", log=None, prepatcher=None, desktop=desktop)
        live_queue._run_group(row, {}, 1, Path("rig"), "T1", None, False, play=lambda _rig, _id: live,
                              install=lambda _plan, _n: None, judge=None, record=None)
        self.assertEqual(row["live"]["desktop"], desktop)


if __name__ == "__main__":
    unittest.main()
