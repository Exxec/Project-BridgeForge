from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_mod_with_finding(root: Path) -> None:
    # A mod_info.json triage banner produces a stable, deterministic finding.
    _write(
        root / "mod_info.json",
        '{"id":"fixture","name":"BROKEN Fixture","version":"1.0","gameVersion":"0.98a-RC8"}',
    )


class ScanBaselineTests(unittest.TestCase):
    def test_write_baseline_then_clean_rescan_reports_zero_new(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            _make_mod_with_finding(root)
            output = Path(directory) / "artifacts"
            baseline = Path(directory) / "baseline.json"

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main(["scan", str(root), "--output", str(output), "--write-baseline", str(baseline)])
            self.assertEqual(code, 0)
            self.assertTrue(baseline.is_file())
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            self.assertGreater(len(payload["findings"]), 0)
            self.assertIn("Baseline written", buffer.getvalue())

            buffer2 = io.StringIO()
            with contextlib.redirect_stdout(buffer2):
                code2 = main(["scan", str(root), "--output", str(output), "--baseline", str(baseline)])
            self.assertEqual(code2, 0)
            self.assertIn("found 0 new finding(s) not in baseline", buffer2.getvalue())
            self.assertIn("0 previously accepted finding(s) resolved", buffer2.getvalue())

    def test_new_finding_after_baseline_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","version":"1.0","gameVersion":"0.98a-RC8"}')
            output = Path(directory) / "artifacts"
            baseline = Path(directory) / "baseline.json"

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                main(["scan", str(root), "--output", str(output), "--write-baseline", str(baseline)])

            # Now introduce a new finding (triage banner) not present in the baseline.
            _write(root / "mod_info.json", '{"id":"fixture","name":"BROKEN Fixture","version":"1.0","gameVersion":"0.98a-RC8"}')

            buffer2 = io.StringIO()
            with contextlib.redirect_stdout(buffer2):
                code = main(["scan", str(root), "--output", str(output), "--baseline", str(baseline)])
            self.assertEqual(code, 0)
            self.assertIn("found 1 new finding(s) not in baseline", buffer2.getvalue())

    def test_resolved_finding_is_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            _make_mod_with_finding(root)
            output = Path(directory) / "artifacts"
            baseline = Path(directory) / "baseline.json"

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                main(["scan", str(root), "--output", str(output), "--write-baseline", str(baseline)])

            # Fix the triage banner; the previously accepted finding should now be "resolved".
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","version":"1.0","gameVersion":"0.98a-RC8"}')

            buffer2 = io.StringIO()
            with contextlib.redirect_stdout(buffer2):
                code = main(["scan", str(root), "--output", str(output), "--baseline", str(baseline)])
            self.assertEqual(code, 0)
            self.assertIn("found 0 new finding(s) not in baseline", buffer2.getvalue())
            self.assertIn("1 previously accepted finding(s) resolved", buffer2.getvalue())

    def test_default_output_unchanged_when_no_baseline_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mod"
            _make_mod_with_finding(root)
            output = Path(directory) / "artifacts"

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main(["scan", str(root), "--output", str(output)])
            self.assertEqual(code, 0)
            text = buffer.getvalue()
            self.assertIn("Scanned", text)
            self.assertIn("findings.", text)
            self.assertNotIn("baseline", text.lower())


if __name__ == "__main__":
    unittest.main()
