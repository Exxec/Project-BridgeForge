"""ROADMAP 70 H4: state-snapshot copies the irreplaceable state append-only and never deletes."""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.state_snapshot import snapshot_sources, take_snapshot
from tests.support import resolved_temp_dir


def _tree(root: Path) -> Path:
    (root / "Done" / "ModA").mkdir(parents=True)
    (root / "Done" / "ModA" / "a.txt").write_text("one", encoding="utf-8")
    (root / "bridgeforge-state").mkdir()
    (root / "bridgeforge-state" / "s.json").write_text("{}", encoding="utf-8")
    (root / "In operation" / "W1" / "working").mkdir(parents=True)
    (root / "In operation" / "W1" / "working" / "mod_info.json").write_text("{}", encoding="utf-8")
    (root / "In operation" / "_rig").mkdir(parents=True)
    (root / "In operation" / "_rig" / "huge.bin").write_text("x", encoding="utf-8")
    (root / "In operation" / "W2").mkdir()  # no working/: not a source
    return root


class SnapshotTests(unittest.TestCase):
    def test_sources_are_done_state_workings_and_memory_but_not_the_rig(self) -> None:
        with resolved_temp_dir() as base:
            root = _tree(base / "repo")
            memory = base / "home" / "projects"
            sources = snapshot_sources(root, base / "home")
            self.assertEqual(sorted(sources), ["Done", "In operation/W1/working", "bridgeforge-state"])
            self.assertFalse(memory.exists())

    def test_first_copy_then_unchanged_then_changed_file_keeps_the_older_version(self) -> None:
        with resolved_temp_dir() as base:
            root, dest = _tree(base / "repo"), base / "backup"
            first = take_snapshot(root, dest, base / "home", quiet=True, stamp="s1")
            self.assertEqual((first["copied"], first["skipped"], first["versioned"]), (3, 0, 0))
            self.assertEqual((dest / "current" / "Done" / "ModA" / "a.txt").read_text(encoding="utf-8"), "one")
            second = take_snapshot(root, dest, base / "home", quiet=True, stamp="s2")
            self.assertEqual((second["copied"], second["skipped"]), (0, 3))
            changed = root / "Done" / "ModA" / "a.txt"
            changed.write_text("two plus", encoding="utf-8")
            third = take_snapshot(root, dest, base / "home", quiet=True, stamp="s3")
            self.assertEqual((third["copied"], third["versioned"]), (1, 1))
            self.assertEqual((dest / "versions" / "s3" / "Done" / "ModA" / "a.txt").read_text(encoding="utf-8"), "one")
            self.assertEqual((dest / "current" / "Done" / "ModA" / "a.txt").read_text(encoding="utf-8"), "two plus")

    def test_a_file_deleted_at_the_source_stays_in_the_snapshot(self) -> None:
        with resolved_temp_dir() as base:
            root, dest = _tree(base / "repo"), base / "backup"
            take_snapshot(root, dest, base / "home", quiet=True, stamp="s1")
            os.remove(root / "Done" / "ModA" / "a.txt")
            take_snapshot(root, dest, base / "home", quiet=True, stamp="s2")
            self.assertTrue((dest / "current" / "Done" / "ModA" / "a.txt").is_file())

    def test_a_destination_inside_a_source_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            root = _tree(base / "repo")
            with self.assertRaises(ValueError):
                take_snapshot(root, root / "Done" / "backup", base / "home", quiet=True)
            with self.assertRaises(ValueError):
                take_snapshot(root, base, base / "home", quiet=True)  # contains every source

    def test_the_command_reports_and_progress_lines_appear_unless_quiet(self) -> None:
        with resolved_temp_dir() as base:
            root, dest = _tree(base / "repo"), base / "backup"
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["state-snapshot", "--to", str(dest), "--root", str(root), "--claude-home", str(base / "home")])
            self.assertEqual(code, 0)
            self.assertIn("[1/3] Done:", err.getvalue())
            self.assertIn("3 copied", out.getvalue())


if __name__ == "__main__":
    unittest.main()
