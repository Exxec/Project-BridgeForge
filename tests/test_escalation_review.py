"""Escalation review sheet and watched-directory snapshots (2026-09-30)."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from bridgeforge.escalation_review import diff_snapshots, flag_diff, review_sheet, snapshot_dir
from tests.support import resolved_temp_dir


def _attempt(ws: Path, packet: str, name: str, before: str, after: str, *, output: str = "") -> None:
    (ws / "working" / name).parent.mkdir(parents=True, exist_ok=True)
    (ws / "working" / name).write_bytes(before.encode())
    attempt = ws / "scratch" / "escalations" / packet / "attempt-1"
    (attempt / "working" / name).parent.mkdir(parents=True, exist_ok=True)
    (attempt / "working" / name).write_bytes(after.encode())
    (attempt / "START_TREE.json").write_text(json.dumps({name: hashlib.sha256(before.encode()).hexdigest()}), encoding="utf-8")
    (attempt / "AGENT_OUTPUT.txt").write_text(output, encoding="utf-8")
    (attempt / "NOTE.md").write_text("changed one line", encoding="utf-8")


class ReviewSheetTests(unittest.TestCase):
    def test_flags_the_changes_past_batches_needed_a_human_for(self) -> None:
        self.assertEqual(flag_diff(["-  hints: SHIP_WITH_MODULES", "+  hints: "]), ["hint-or-tag-removed"])
        self.assertEqual(flag_diff(["-  hints: SHIP_WITH_MODULES", "+  hints: SHIP_WITH_MODULES, CARRIER"]), [])
        self.assertEqual(flag_diff(["+Random r = new Random(seed);"]), ["random-or-save-logic"])
        self.assertEqual(flag_diff(["-for (String s : list) {", "+list.forEach(s -> {"]), ["loop-rewritten"])
        self.assertEqual(flag_diff(["+} catch (Throwable t) {}"]), ["exception-swallowed"])
        self.assertEqual(flag_diff(["-a"] * 7), ["net-deletion"])

    def test_sheet_shows_the_diff_and_flags(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "Mod"
            _attempt(ws, "p1", "data/a.java", "int x = 1;\n", "Random r = new Random();\n", output="dangerouslyDisableSandbox")
            result = review_sheet(ws)
            sheet = Path(result["sheet"]).read_text(encoding="utf-8")
        self.assertEqual(result["flagged"], ["p1"])
        self.assertEqual(result["reviews"][0]["flags"], ["asked-to-leave-sandbox", "random-or-save-logic"])
        self.assertIn("+Random r = new Random();", sheet)
        self.assertIn("> changed one line", sheet)

    def test_a_moved_baseline_is_labelled_not_diffed(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "Mod"
            _attempt(ws, "p1", "data/a.java", "int x = 1;\n", "int x = 2;\n")
            (ws / "working" / "data" / "a.java").write_text("merged by hand\n", encoding="utf-8")
            review = review_sheet(ws, write=False)["reviews"][0]
        self.assertEqual(review["flags"], ["baseline-moved"])


class SnapshotTests(unittest.TestCase):
    def test_reports_what_changed_in_a_watched_directory(self) -> None:
        with resolved_temp_dir() as root:
            (root / "keep.md").write_text("a", encoding="utf-8")
            (root / "edit.md").write_text("a", encoding="utf-8")
            before = snapshot_dir(root)
            (root / "edit.md").write_text("b", encoding="utf-8")
            (root / "new.md").write_text("c", encoding="utf-8")
            after = snapshot_dir(root)
        self.assertEqual(diff_snapshots(before, after), {"added": ["new.md"], "removed": [], "changed": ["edit.md"]})



class RunLockTests(unittest.TestCase):
    def test_a_live_run_blocks_a_second_and_a_dead_one_does_not(self) -> None:
        import os
        import subprocess
        import sys

        from bridgeforge.escalation import EscalationError, run_lock
        with resolved_temp_dir() as root:
            live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                lock = root / "scratch" / "escalations" / "RUN.lock"
                lock.parent.mkdir(parents=True)
                lock.write_text(f"{live.pid}\n", encoding="utf-8")
                with self.assertRaises(EscalationError):
                    with run_lock(root):
                        pass
            finally:
                live.kill()
                live.wait()
            with run_lock(root):
                self.assertEqual(lock.read_text(encoding="utf-8").split()[0], str(os.getpid()))
            self.assertFalse(lock.exists())


class RemoveTreeTests(unittest.TestCase):
    def test_read_only_git_objects_do_not_block_cleanup(self) -> None:
        # Hiigaran Descendants and The Nomads ship their .git folder (2026-10-02): plain rmtree hit WinError 5.
        import os
        import stat

        from bridgeforge.escalation import _remove_tree
        with resolved_temp_dir() as root:
            obj = root / "attempt-1" / "working" / ".git" / "objects" / "00" / "abc"
            obj.parent.mkdir(parents=True)
            obj.write_text("x", encoding="utf-8")
            os.chmod(obj, stat.S_IREAD)
            _remove_tree(root / "attempt-1")
            gone = not (root / "attempt-1").exists()
        self.assertTrue(gone)


if __name__ == "__main__":
    unittest.main()
