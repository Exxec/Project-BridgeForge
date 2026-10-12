"""`bridgeforge ready-list`: the mods ready for live testing (2026-09-30)."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from tests.support import resolved_temp_dir


def _ws(queue: Path, name: str, report_status: str, revive_status: str) -> None:
    working = queue / name / "working"
    (working / "reports").mkdir(parents=True)
    (working / "mod_info.json").write_text('{"id":"m","name":"m","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
    (working / "reports" / "REVIVAL_REPORT.md").write_text(f"# Report\n\n{report_status}\n", encoding="utf-8")
    (queue / name / "reports" / "revive").mkdir(parents=True)
    (queue / name / "reports" / "revive" / "REVIVE.json").write_text(json.dumps({"status": revive_status, "compile_checked": True}), encoding="utf-8")


class ReadyListTests(unittest.TestCase):
    def test_lists_only_ready_mods_whose_latest_revive_finished(self) -> None:
        with resolved_temp_dir() as queue:
            _ws(queue, "Ready", "READY_FOR_LIVE_TEST", "UNATTENDED_DONE")
            _ws(queue, "Stale", "READY_FOR_LIVE_TEST", "ESCALATED")
            _ws(queue, "Done", "LIVE_VALIDATED", "UNATTENDED_DONE")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["ready-list", str(queue), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["ready"], [{"workspace": "Ready", "compile_checked": True}])


if __name__ == "__main__":
    unittest.main()
