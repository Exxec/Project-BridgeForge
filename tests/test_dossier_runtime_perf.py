from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.dossier import build_dossier


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_mod(root: Path) -> None:
    _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture [BF r1]","version":"1.0+bf.1","gameVersion":"0.98a-RC8"}')


class DossierRuntimeAndPerfTests(unittest.TestCase):
    def test_no_save_or_perf_reports_not_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            result = build_dossier(root)
            self.assertTrue(result["index"]["artifacts"]["runtime_footprint"]["not_supplied"])
            self.assertTrue(result["index"]["artifacts"]["performance"]["not_supplied"])
            self.assertIn("runtime_footprint: not supplied", result["index_markdown"])
            self.assertIn("performance: not supplied", result["index_markdown"])

    def test_save_given_but_not_an_existing_campaign_reports_error_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as save_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            fake_save = Path(save_dir) / "save_Nobody_1"
            fake_save.mkdir()
            result = build_dossier(root, save=fake_save)
            footprint = result["index"]["artifacts"]["runtime_footprint"]
            self.assertFalse(footprint["not_supplied"])
            self.assertIn("classes", footprint)
            # save_inspect is not implemented yet in this repo -- must degrade, not raise.
            self.assertIn("objects", footprint)
            self.assertFalse(footprint["objects"].get("available", False))

    def test_perf_given_but_unreadable_reports_error_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as perf_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            bad_report = Path(perf_dir) / "performance-report.json"
            bad_report.write_text("not json", encoding="utf-8")
            result = build_dossier(root, perf=bad_report)
            performance = result["index"]["artifacts"]["performance"]
            self.assertFalse(performance["not_supplied"])
            self.assertIn("spw_report_error", performance)

    def test_perf_with_valid_report_and_log_summarizes_both(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as perf_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            report_path = Path(perf_dir) / "performance-report.json"
            report_path.write_text(
                json.dumps({"mods": [{"mod_id": "fixture", "cpu_share": 0.1, "top_scripts": []}], "startup": {"total_ms": 1000}}),
                encoding="utf-8",
            )
            log_path = Path(perf_dir) / "run.log"
            lines = "\n".join(f"{i} [T] WARN fixture.Script - noisy line" for i in range(6))
            log_path.write_text(lines, encoding="utf-8")

            result = build_dossier(root, perf=report_path, log=log_path, perf_mod_prefixes=["fixture"])
            performance = result["index"]["artifacts"]["performance"]
            self.assertEqual(performance["spw_report"]["startup"]["total_ms"], 1000)
            self.assertGreaterEqual(performance["log_spam"]["total_spam_lines"], 6)
            self.assertIn("performance:", result["index_markdown"])

    def test_existing_behavior_unaffected_without_new_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            result = build_dossier(root, vanilla_core=None, baseline=None)
            for key in ("dossier_version", "identity", "inventory", "finding_counts", "open_questions", "parts", "artifacts"):
                self.assertIn(key, result["index"])


if __name__ == "__main__":
    unittest.main()
