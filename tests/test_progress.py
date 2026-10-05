from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge.cli import main
from bridgeforge.progress import LONG_RUNNING_COMMANDS, Checkpoint, report
from tests.support import resolved_temp_dir


class CheckpointTests(unittest.TestCase):
    def test_same_header_resumes_other_header_restarts_and_finish_removes(self):
        with resolved_temp_dir() as root:
            path = root / "run.partial.jsonl"
            with Checkpoint(path, {"inputs": 1}) as saved:
                saved.add("a", {"n": 1})
                saved.add("b", {"n": 2})
            with open(path, "a", encoding="utf-8") as handle:
                handle.write('{"key": "c", "val')  # cut short
            again = Checkpoint(path, {"inputs": 1})
            self.assertEqual((again.get("a"), again.get("b"), again.get("c")), ({"n": 1}, {"n": 2}, None))
            again.close()
            other = Checkpoint(path, {"inputs": 2})
            self.assertIsNone(other.get("a"))
            other.close()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8").splitlines()[0]), {"inputs": 2})
            other.finish()
            self.assertFalse(path.exists())
            nothing = Checkpoint(None, {})
            nothing.add("x", {})
            nothing.finish()

    def test_a_grown_item_list_resumes_and_a_shrunk_one_restarts(self):
        # ROADMAP 49: the 2026-10-04 queue pass restarted from 0 because two workspaces had been added.
        with resolved_temp_dir() as root:
            path = root / "run.partial.jsonl"
            with Checkpoint(path, {"queue": "q", "workspaces": ["A", "B"]}) as saved:
                saved.add("A", {"n": 1})
            grown = Checkpoint(path, {"queue": "q", "workspaces": ["A", "B", "C"]})
            self.assertEqual(grown.get("A"), {"n": 1})
            grown.add("C", {"n": 3})
            grown.close()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8").splitlines()[0])["workspaces"], ["A", "B", "C"])
            again = Checkpoint(path, {"queue": "q", "workspaces": ["A", "B", "C"]})
            self.assertEqual((again.get("A"), again.get("C")), ({"n": 1}, {"n": 3}))
            again.close()
            shrunk = Checkpoint(path, {"queue": "q", "workspaces": ["A"]})  # B dropped: different inputs
            self.assertIsNone(shrunk.get("A"))
            shrunk.close()
            other = Checkpoint(path, {"queue": "other", "workspaces": ["A"]})
            self.assertIsNone(other.get("A"))
            other.finish()

    def test_report_format(self):
        err = io.StringIO()
        with redirect_stderr(err):
            report(3, 10, "Mod", "2 finding(s)", 1.25)
            report(4, 10, "Other", "done", None)
        self.assertEqual(err.getvalue().splitlines(), ["[3/10] Mod: 2 finding(s) (1.2s)", "[4/10] Other: done (from checkpoint)"])


class LongRunningCommandRuleTests(unittest.TestCase):
    """House rule 2026-09-27 (CLAUDE.md): a command that walks a whole queue or archive prints
    per-item progress and resumes from a checkpoint. Each listed command must at least offer --quiet,
    which only exists where progress is printed."""

    def test_every_long_running_command_offers_quiet(self):
        for command in LONG_RUNNING_COMMANDS:
            out = io.StringIO()
            with self.subTest(command=" ".join(command)), redirect_stdout(out), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main([*command, "--help"])
            self.assertIn("--quiet", out.getvalue(), f"{' '.join(command)} prints no progress")


if __name__ == "__main__":
    unittest.main()
