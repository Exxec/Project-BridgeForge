from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.spw_bridge import SpwBridgeError, ingest_spw_report, log_spam, perf_gate


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class IngestSpwReportTests(unittest.TestCase):
    def test_recognized_schema_extracts_per_mod_and_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "performance-report.json"
            _write(
                report_path,
                json.dumps(
                    {
                        "schema_version": 1,
                        "mods": [
                            {"mod_id": "arkgneisis", "cpu_share": 0.12, "top_scripts": [{"name": "loa_awacs_order_manager", "self_ms": 4.2}]},
                            {"mod_id": "exigency", "cpu_share": 0.03, "top_scripts": []},
                        ],
                        "startup": {"total_ms": 8000, "per_mod": {"arkgneisis": 400}},
                    }
                ),
            )
            result = ingest_spw_report(report_path)
            self.assertEqual(result["report_schema_version"], 1)
            self.assertEqual(len(result["per_mod"]), 2)
            arkgneisis = next(entry for entry in result["per_mod"] if entry["mod_id"] == "arkgneisis")
            self.assertEqual(arkgneisis["cpu_share"], 0.12)
            self.assertEqual(arkgneisis["top_scripts"][0]["name"], "loa_awacs_order_manager")
            self.assertEqual(result["startup"]["total_ms"], 8000)
            self.assertEqual(result["startup"]["per_mod_ms"], {"arkgneisis": 400})
            self.assertEqual(result["limitations"], [])

    def test_unrecognized_schema_degrades_with_limitations_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "performance-report.json"
            _write(report_path, json.dumps({"totally": "unexpected shape"}))
            result = ingest_spw_report(report_path)
            self.assertEqual(result["per_mod"], [])
            self.assertTrue(result["limitations"])

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(SpwBridgeError):
            ingest_spw_report(Path("does-not-exist.json"))

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            _write(path, "{not json")
            with self.assertRaises(SpwBridgeError):
                ingest_spw_report(path)


class LogSpamTests(unittest.TestCase):
    def test_counts_repeated_lines_per_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run.log"
            lines = []
            for i in range(7):
                lines.append(f"{i}0000 [Thread-1] WARN  loa_awacs_order_manager  - advance called with null engine")
            lines.append("70000 [Thread-1] INFO  com.fs.starfarer.Main  - Playing music")
            _write(log_path, "\n".join(lines) + "\n")

            result = log_spam(log_path, ["loa_awacs_order_manager"], min_repeats=5)
            entries = result["by_prefix"]["loa_awacs_order_manager"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["count"], 7)
            self.assertEqual(result["total_spam_lines"], 7)

    def test_below_min_repeats_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run.log"
            _write(log_path, "1 [T] WARN foo.Bar - repeated line\n2 [T] WARN foo.Bar - repeated line\n")
            result = log_spam(log_path, ["foo"], min_repeats=5)
            self.assertEqual(result["by_prefix"]["foo"], [])

    def test_missing_log_raises(self) -> None:
        with self.assertRaises(SpwBridgeError):
            log_spam(Path("nope.log"), ["foo"])


class PerfGateTests(unittest.TestCase):
    def test_no_thresholds_is_report_only(self) -> None:
        result = perf_gate({"cpu_share": 0.9}, None)
        self.assertTrue(result["report_only"])
        self.assertEqual(result["status"], "REPORT_ONLY")

    def test_thresholds_produce_pass_warn_fail(self) -> None:
        thresholds = {"cpu_share": {"warn": 0.1, "fail": 0.2}}
        self.assertEqual(perf_gate({"cpu_share": 0.05}, thresholds)["status"], "PASS")
        self.assertEqual(perf_gate({"cpu_share": 0.15}, thresholds)["status"], "WARN")
        self.assertEqual(perf_gate({"cpu_share": 0.25}, thresholds)["status"], "FAIL")

    def test_worst_metric_wins(self) -> None:
        thresholds = {"cpu_share": {"warn": 0.1, "fail": 0.2}, "startup_ms": {"warn": 1000, "fail": 5000}}
        result = perf_gate({"cpu_share": 0.05, "startup_ms": 9000}, thresholds)
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
