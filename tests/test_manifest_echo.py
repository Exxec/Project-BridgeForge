"""Startup echo of the manifest id (ROADMAP item 75 R1): the run file the harness writes and how the evaluator reads the probe's echo."""
from __future__ import annotations

import json
import unittest

from bridgeforge import manifest_echo
from bridgeforge.run_manifest import evaluate_run, read_manifest
from tests.bound_runs import BASIC_LOG, bound_run
from tests.support import resolved_temp_dir
from tests.test_run_manifest import _two

ECHO = "9 [Thread-2] INFO  com.bridgeforge.probe.BfProbeModPlugin  - BF-PROBE|0.2.27|run|manifest_id={}"


def _evaluate(root, lines_for_id, test_id="E-1"):
    _, targets = _two(root)
    rig, log = bound_run(root, targets, test_id, None)
    manifest = read_manifest(rig, test_id)
    log.write_text("\n".join([*BASIC_LOG, *lines_for_id(manifest["manifest_id"])]) + "\n", encoding="utf-8")
    return rig, manifest, evaluate_run(rig, manifest, log)


class RunFileTests(unittest.TestCase):
    def test_prepare_writes_the_manifest_id_for_the_probe_to_echo(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig, _ = bound_run(root, targets, "E-0")
            data = json.loads((rig / "saves" / "common" / manifest_echo.RUN_FILE).read_text(encoding="utf-8"))
            self.assertEqual(data, {"manifest_id": read_manifest(rig, "E-0")["manifest_id"], "run_id": "E-0"})


class EchoEvaluationTests(unittest.TestCase):
    def test_a_matching_echo_is_acceptable(self) -> None:
        with resolved_temp_dir() as root:
            _, _, evidence = _evaluate(root, lambda mid: [ECHO.format(mid)])
        self.assertEqual(evidence["manifest_echo"], "MATCH")
        self.assertEqual(evidence["status"], "ACCEPTABLE")

    def test_another_runs_id_is_a_mismatch_and_refuses(self) -> None:
        with resolved_temp_dir() as root:
            _, _, evidence = _evaluate(root, lambda mid: [ECHO.format("0" * 64)])
        self.assertEqual(evidence["manifest_echo"], "MISMATCH")
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertTrue(any("MANIFEST_MISMATCH" in p for p in evidence["problems"]))

    def test_an_echo_without_an_id_is_not_echoed_and_refuses(self) -> None:
        with resolved_temp_dir() as root:
            _, _, evidence = _evaluate(root, lambda mid: [ECHO.format("NONE")])
        self.assertEqual(evidence["manifest_echo"], "NOT_ECHOED")
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertTrue(any("MANIFEST_NOT_ECHOED" in p for p in evidence["problems"]))

    def test_a_legacy_log_without_the_line_is_not_a_failure(self) -> None:
        with resolved_temp_dir() as root:
            _, _, evidence = _evaluate(root, lambda mid: [])
        self.assertEqual(evidence["manifest_echo"], "LEGACY")
        self.assertEqual(evidence["status"], "ACCEPTABLE")

    def test_the_echo_pattern_ignores_ids_in_other_lines(self) -> None:
        self.assertEqual(manifest_echo.echoed_ids("BF-PROBE|0.2.27|run|manifest_id=abc\nnoise manifest_id=zzz"), ["abc"])


if __name__ == "__main__":
    unittest.main()
