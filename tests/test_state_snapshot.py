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


class RetryTests(unittest.TestCase):
    def test_a_source_with_an_unreadable_file_is_not_checkpointed_so_the_next_run_retries_it(self) -> None:
        from unittest import mock
        with resolved_temp_dir() as base:
            root, dest = _tree(base / "repo"), base / "backup"
            real_copy2 = __import__("shutil").copy2

            def failing(src, dst, *a, **k):
                if str(src).endswith("a.txt"):
                    raise PermissionError(13, "denied")
                return real_copy2(src, dst, *a, **k)

            with mock.patch("bridgeforge.state_snapshot.shutil.copy2", side_effect=failing):
                first = take_snapshot(root, dest, base / "home", quiet=True, stamp="s1")
            self.assertEqual(len(first["errors"]), 1)
            second = take_snapshot(root, dest, base / "home", quiet=True, stamp="s2")
            self.assertEqual(second["errors"], [])
            self.assertTrue((dest / "current" / "Done" / "ModA" / "a.txt").is_file())


class AfterArchiveTests(unittest.TestCase):
    def test_nothing_happens_without_a_config_and_a_configured_root_snapshots_after_an_archive(self) -> None:
        import json as _json
        from bridgeforge.state_snapshot import snapshot_after_archive
        with resolved_temp_dir() as base:
            root = _tree(base / "repo")
            self.assertIsNone(snapshot_after_archive(root / "Done", base / "home"))
            self.assertFalse((base / "backup").exists())
            (root / "bridgeforge-state" / "snapshot.json").write_text(_json.dumps({"to": str(base / "backup")}), encoding="utf-8")
            note = snapshot_after_archive(root / "Done", base / "home")
            self.assertIn("copied", note)
            self.assertTrue((base / "backup" / "current" / "Done" / "ModA" / "a.txt").is_file())

    def test_a_broken_config_is_reported_not_raised(self) -> None:
        from bridgeforge.state_snapshot import snapshot_after_archive
        with resolved_temp_dir() as base:
            root = _tree(base / "repo")
            (root / "bridgeforge-state" / "snapshot.json").write_text("{}", encoding="utf-8")
            self.assertIn("FAILED", snapshot_after_archive(root / "Done", base / "home"))
