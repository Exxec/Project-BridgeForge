from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.corpus_recheck import corpus_recheck, render_markdown
from tests.support import resolved_temp_dir


def _mod(root: Path, folder: str, status_line: str | None = None, extra_data: dict | None = None) -> Path:
    base = root / "In operation" / folder
    working = base / "working"
    working.mkdir(parents=True)
    (working / "mod_info.json").write_text('{"id":"' + folder.lower() + '","name":"' + folder + '"}', encoding="utf-8")
    (base / "reports").mkdir()
    if status_line is not None:
        (base / "reports" / "REVIVAL_REPORT.md").write_text(status_line, encoding="utf-8")
    if extra_data:
        for relative, text in extra_data.items():
            path = working / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return working


class CorpusRecheckTests(unittest.TestCase):
    """ROADMAP P14 item 32: generalizes item 23's full corpus recheck (2026-09-21, done by hand
    with a throwaway script) into a reusable command.
    """

    def test_only_mods_with_a_report_are_included(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, "HasReport", "READY_FOR_LIVE_TEST\n")
            base_no_report = root / "In operation" / "NoReport"
            (base_no_report / "working").mkdir(parents=True)
            (base_no_report / "working" / "mod_info.json").write_text('{"id":"noreport"}', encoding="utf-8")
            result = corpus_recheck(root)
            self.assertEqual(result["mod_count"], 1)
            self.assertEqual(result["mods"][0]["mod"], "HasReport")

    def test_include_intake_widens_scope_to_report_less_mods(self) -> None:
        """ROADMAP P14 item 8 triage pass: the Ironclads intake queue has no REVIVAL_REPORT.md yet,
        but shares the identical working/ layout every other mod uses."""
        with resolved_temp_dir() as root:
            _mod(root, "HasReport", "READY_FOR_LIVE_TEST\n")
            base_no_report = root / "In operation" / "NoReport"
            (base_no_report / "working").mkdir(parents=True)
            (base_no_report / "working" / "mod_info.json").write_text('{"id":"noreport"}', encoding="utf-8")
            result = corpus_recheck(root, require_report=False)
            self.assertEqual(result["mod_count"], 2)
            names = {m["mod"] for m in result["mods"]}
            self.assertEqual(names, {"HasReport", "NoReport"})
            no_report_mod = next(m for m in result["mods"] if m["mod"] == "NoReport")
            self.assertIsNone(no_report_mod["declared_completion_status"])

    def test_finding_counts_and_declared_status_are_reported(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, "Fixture", "**READY_WITH_REVIEW_ITEMS** — looks fine.\n", {
                "mod_info.json": '{"id":"fixture","name":"Fixture"}',  # no jars declared -> no compile-check needed for this test
            })
            result = corpus_recheck(root)
            mod = result["mods"][0]
            self.assertEqual(mod["declared_completion_status"], "READY_WITH_REVIEW_ITEMS")
            self.assertEqual(mod["declared_completion_status_confidence"], "BEST_EFFORT")
            self.assertIn("by_classification", mod)

    def test_regression_detected_when_a_ready_mod_carries_a_manual_finding(self) -> None:
        with resolved_temp_dir() as root:
            # missing-mod-info-jar / jar declared but absent -> a real MANUAL finding, and the mod
            # claims READY_FOR_LIVE_TEST, so this must be flagged as a regression.
            _mod(root, "Broken", "READY_FOR_LIVE_TEST\n", {
                "mod_info.json": '{"id":"broken","name":"Broken","jars":["jars/missing.jar"]}',
            })
            result = corpus_recheck(root)
            self.assertEqual(result["status"], "REGRESSION")
            self.assertIn("Broken", result["regressions"])

    def test_a_mods_own_baseline_suppresses_its_accepted_findings(self) -> None:
        """A reviewed, deliberately accepted finding must stop reporting as a REGRESSION forever.

        Real case (owner call 2026-09-22): Xenoargh-FX-Example's preset overrides are intentional
        custom content. `scan --write-baseline` already produced the file and `scan --baseline`
        already honoured it; corpus-recheck was the one consumer that did not, so baselining a mod
        had no effect on the signal it was meant to quiet.
        """
        with resolved_temp_dir() as root:
            working = _mod(root, "Accepted", "READY_FOR_LIVE_TEST\n", {
                "mod_info.json": '{"id":"accepted","name":"Accepted","jars":["jars/missing.jar"]}',
            })
            before = corpus_recheck(root)
            self.assertEqual(before["status"], "REGRESSION")
            accepted = [f for m in before["mods"] for f in m["manual_ids"]]
            self.assertTrue(accepted, "fixture must produce a MANUAL finding to baseline")

            (working / "reports").mkdir(parents=True, exist_ok=True)
            (working / "reports" / "baseline-test.json").write_text(
                json.dumps({"findings": ["mod-info-jar-missing|mod_info.json|jars/missing.jar"]}), encoding="utf-8"
            )
            after = corpus_recheck(root)
        self.assertEqual(after["status"], "OK")
        self.assertEqual(after["regressions"], [])
        mod = after["mods"][0]
        self.assertEqual(mod["by_classification"].get("MANUAL", 0), 0)
        self.assertEqual(mod["baselined_findings"], 1)
        self.assertTrue(str(mod["baseline"]).endswith("baseline-test.json"))

    def test_an_unreadable_baseline_is_ignored_rather_than_crashing_the_sweep(self) -> None:
        with resolved_temp_dir() as root:
            working = _mod(root, "BadBaseline", "READY_FOR_LIVE_TEST\n", {
                "mod_info.json": '{"id":"badbaseline","name":"BadBaseline","jars":["jars/missing.jar"]}',
            })
            (working / "reports").mkdir(parents=True, exist_ok=True)
            (working / "reports" / "baseline-broken.json").write_text("{not json", encoding="utf-8")
            result = corpus_recheck(root)
        # The finding still counts; a corrupt baseline must never silently hide a real regression.
        self.assertEqual(result["status"], "REGRESSION")
        self.assertEqual(result["mods"][0]["baselined_findings"], 0)
        self.assertIsNone(result["mods"][0]["baseline"])

    def test_no_regression_when_an_in_progress_mod_carries_a_manual_finding(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, "Wip", "still IN_PROGRESS, not claiming ready\n", {
                "mod_info.json": '{"id":"wip","name":"Wip","jars":["jars/missing.jar"]}',
            })
            result = corpus_recheck(root)
            self.assertEqual(result["status"], "OK")
            self.assertEqual(result["regressions"], [])

    def test_a_scan_failure_for_one_mod_is_reported_as_an_error_not_a_crash(self) -> None:
        # _recheck_one must not let one mod's scan_mod failure (e.g. its working/ copy vanished
        # between project_board's discovery and the scan) take down the whole recheck.
        with resolved_temp_dir() as root:
            from bridgeforge.corpus_recheck import _recheck_one
            good = _mod(root, "Good", "READY_FOR_LIVE_TEST\n")
            result_good = _recheck_one("Good", good, None, "READY_FOR_LIVE_TEST", "EXACT")
            self.assertNotIn("error", result_good)
            result_missing = _recheck_one("Vanished", root / "does-not-exist", None, None, None)
            self.assertIn("error", result_missing)
            self.assertEqual(result_missing["mod"], "Vanished")

    def test_render_markdown_produces_a_table_with_a_regression_banner(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, "Broken", "READY_FOR_LIVE_TEST\n", {
                "mod_info.json": '{"id":"broken","name":"Broken","jars":["jars/missing.jar"]}',
            })
            result = corpus_recheck(root)
            markdown = render_markdown(result)
            self.assertIn("Regression", markdown)
            self.assertIn("Broken", markdown)
            self.assertIn("| Mod | Files |", markdown)

    def test_checkpoint_resumes_an_interrupted_sweep(self) -> None:
        from unittest import mock

        import bridgeforge.corpus_recheck as recheck

        class Stop(Exception):
            pass

        def stop_after_one(done, total, mod, seconds):
            if done == 1:
                raise Stop

        with resolved_temp_dir() as root:
            for name in ("Alpha", "Beta", "Gamma"):
                _mod(root, name, "IN_PROGRESS\n")
            checkpoint = root / "recheck.partial.jsonl"
            whole = corpus_recheck(root)
            with self.assertRaises(Stop):
                corpus_recheck(root, checkpoint=checkpoint, progress=stop_after_one)
            with mock.patch.object(recheck, "_recheck_one", wraps=recheck._recheck_one) as scanned:
                resumed = corpus_recheck(root, checkpoint=checkpoint)
            self.assertEqual(scanned.call_count, 2)
            self.assertEqual(resumed["mods"], whole["mods"])
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                main(["corpus-recheck", "--repo-root", str(root)])
            self.assertFalse((root / "In operation" / "CORPUS_RECHECK.partial.jsonl").exists())
        self.assertIn("[1/3] Alpha: ", err.getvalue())

    def test_cli_writes_json_and_markdown_and_returns_regression_exit_code(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, "Broken", "READY_FOR_LIVE_TEST\n", {
                "mod_info.json": '{"id":"broken","name":"Broken","jars":["jars/missing.jar"]}',
            })
            markdown_path = root / "rollup.md"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main([
                    "corpus-recheck", "--repo-root", str(root),
                    "--write-markdown", str(markdown_path), "--json",
                ])
            self.assertEqual(exit_code, 1)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["status"], "REGRESSION")
            self.assertTrue(markdown_path.is_file())


if __name__ == "__main__":
    unittest.main()
