"""Natural-exit observation for live runs: offline, with fake processes (no game is launched)."""
from __future__ import annotations

import json
import unittest

from bridgeforge.exit_observation import (ExitObservationError, observed_exit, read_exit_observation, write_exit_observation)
from bridgeforge.live_run import settle_exit
from bridgeforge.live_trust import write_run_record
from tests.support import resolved_temp_dir
from tests.test_live_trust import _workspace


class FakeProcess:
    """Reports running for `polls_running` polls, then `code` (None = never exits)."""

    def __init__(self, code: int | None, polls_running: int = 0) -> None:
        self.code, self.left = code, polls_running

    def poll(self) -> int | None:
        if self.code is None:
            return None
        if self.left > 0:
            self.left -= 1
            return None
        return self.code


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class SettleExitTests(unittest.TestCase):
    def _settle(self, process, wait=60, java_left=lambda: False):
        clock = FakeClock()
        return settle_exit(process, wait, sleep=clock.sleep, clock=clock, java_left=java_left)

    def test_natural_exit_zero_is_recorded(self) -> None:
        self.assertEqual(self._settle(FakeProcess(0, polls_running=3)), ("NATURAL", 0))

    def test_natural_nonzero_exit_is_recorded(self) -> None:
        self.assertEqual(self._settle(FakeProcess(137, polls_running=2)), ("NATURAL", 137))

    def test_still_running_at_the_bound_is_killed_with_no_code(self) -> None:
        self.assertEqual(self._settle(FakeProcess(None), wait=10), ("KILLED", None))

    def test_a_java_left_behind_is_killed_not_natural(self) -> None:
        self.assertEqual(self._settle(FakeProcess(0), java_left=lambda: True), ("KILLED", None))


class ObservedExitTests(unittest.TestCase):
    def test_exit_by_itself_with_no_java_left_is_natural(self) -> None:
        self.assertEqual(observed_exit(0, java_left=False), ("NATURAL", 0))

    def test_still_running_or_java_left_behind_is_killed_with_no_code(self) -> None:
        self.assertEqual(observed_exit(None, java_left=False), ("KILLED", None))
        self.assertEqual(observed_exit(0, java_left=True), ("KILLED", None))


class ObservationFileAndRecordTests(unittest.TestCase):
    def test_file_roundtrip_and_missing_is_unknown(self) -> None:
        with resolved_temp_dir() as rig:
            self.assertEqual(read_exit_observation(rig, "T"), ("UNKNOWN", None))
            write_exit_observation(rig, "T", "NATURAL", 3)
            self.assertEqual(read_exit_observation(rig, "T"), ("NATURAL", 3))
            write_exit_observation(rig, "K", "KILLED", None)
            self.assertEqual(read_exit_observation(rig, "K"), ("KILLED", None))

    def test_killed_with_a_code_and_natural_without_one_are_refused(self) -> None:
        with resolved_temp_dir() as rig:
            with self.assertRaises(ExitObservationError):
                write_exit_observation(rig, "T", "KILLED", 0)
            with self.assertRaises(ExitObservationError):
                write_exit_observation(rig, "T", "NATURAL", None)
            (rig / "logs").mkdir()
            (rig / "logs" / "X.exit.json").write_text(json.dumps({"process_exit_observed": "KILLED", "process_exit_code": 0}), encoding="utf-8")
            with self.assertRaises(ExitObservationError):
                read_exit_observation(rig, "X")

    def test_run_record_carries_the_observation_and_defaults_are_unchanged(self) -> None:
        with resolved_temp_dir() as root:
            ws = _workspace(root)
            kw = {"triage": {"counts": {}}, "verdicts": {"m": "PASS"}}
            default = write_run_record(root, "T-DEFAULT", [ws], **kw)
            natural = write_run_record(root, "T-NAT", [ws], process_exit_code=0, process_exit_observed="NATURAL", **kw)
            killed = write_run_record(root, "T-KILL", [ws], process_exit_observed="KILLED", **kw)
            with self.assertRaises(ValueError):
                write_run_record(root, "T-BAD", [ws], process_exit_code=0, process_exit_observed="KILLED", **kw)
        self.assertEqual((default["process_exit_code"], default.get("process_exit_observed")), (None, None))
        self.assertEqual((natural["process_exit_code"], natural["process_exit_observed"]), (0, "NATURAL"))
        self.assertEqual((killed["process_exit_code"], killed["process_exit_observed"]), (None, "KILLED"))


if __name__ == "__main__":
    unittest.main()
