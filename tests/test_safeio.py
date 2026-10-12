"""ROADMAP 70 H1.1/H1.2: atomic writes and guarded deletes."""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from bridgeforge import safeio
from bridgeforge.safeio import UnsafePathError, atomic_write_json, atomic_write_text, safe_rmtree, safe_unlink
from tests.support import link_dir, resolved_temp_dir


class AtomicWriteTests(unittest.TestCase):
    def test_a_write_replaces_the_file_and_leaves_no_temp_file(self) -> None:
        with resolved_temp_dir() as root:
            target = root / "sub" / "state.json"
            atomic_write_text(target, "old", newline="")
            atomic_write_text(target, "new", newline="")
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertEqual([p.name for p in target.parent.iterdir()], ["state.json"])

    def test_a_failed_swap_keeps_the_old_file_and_removes_the_temp_file(self) -> None:
        with resolved_temp_dir() as root:
            target = root / "state.json"
            atomic_write_text(target, "old", newline="")
            with mock.patch.object(safeio.os, "replace", side_effect=OSError("disk gone")):
                with self.assertRaises(OSError):
                    atomic_write_text(target, "new", newline="")
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual([p.name for p in root.iterdir()], ["state.json"])

    def test_json_round_trips_with_unicode(self) -> None:
        with resolved_temp_dir() as root:
            atomic_write_json(root / "a.json", {"name": "Zörg", "n": [1, 2]})
            self.assertEqual(json.loads((root / "a.json").read_text(encoding="utf-8")), {"name": "Zörg", "n": [1, 2]})


class GuardedDeleteTests(unittest.TestCase):
    def test_a_folder_inside_a_root_is_removed_and_the_root_survives(self) -> None:
        with resolved_temp_dir() as root:
            scratch = root / "scratch"
            (scratch / "a" / "b").mkdir(parents=True)
            (scratch / "a" / "b" / "f.txt").write_text("x", encoding="utf-8")
            self.assertTrue(safe_rmtree(scratch / "a", [scratch]))
            self.assertTrue(scratch.is_dir())
            self.assertFalse((scratch / "a").exists())
            self.assertFalse(safe_rmtree(scratch / "a", [scratch]))  # already gone
            with self.assertRaises(FileNotFoundError):
                safe_rmtree(scratch / "a", [scratch], missing_ok=False)

    def test_outside_the_roots_and_the_root_itself_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            allowed, other = root / "allowed", root / "other"
            allowed.mkdir()
            other.mkdir()
            (other / "keep.txt").write_text("x", encoding="utf-8")
            with self.assertRaises(UnsafePathError):
                safe_rmtree(other, [allowed])
            with self.assertRaises(UnsafePathError):
                safe_rmtree(allowed, [allowed])
            with self.assertRaises(UnsafePathError):
                safe_unlink(other / "keep.txt", [allowed])
            with self.assertRaises(UnsafePathError):
                safe_rmtree(root / "allowed" / ".." / "other", [allowed])  # a '..' escape
            with self.assertRaises(UnsafePathError):
                safe_rmtree(other, [])
            self.assertTrue((other / "keep.txt").is_file())

    def test_a_link_to_the_outside_is_removed_as_a_link_and_the_target_is_never_entered(self) -> None:
        """Deleting through a rig's starsector-core junction would delete the real game install."""
        with resolved_temp_dir() as root:
            real, rig = root / "real_install", root / "rig"
            real.mkdir()
            (real / "game.jar").write_text("x", encoding="utf-8")
            rig.mkdir()
            link_dir(real, rig / "starsector-core")
            (rig / "mods").mkdir()
            self.assertTrue(safe_rmtree(rig / "starsector-core", [rig]))  # the link goes
            self.assertTrue((real / "game.jar").is_file())
            link_dir(real, rig / "mods" / "inner_link")
            self.assertTrue(safe_rmtree(rig / "mods", [rig]))  # a link inside a tree is removed, not followed
            self.assertTrue((real / "game.jar").is_file())
            self.assertFalse((rig / "mods").exists())

    def test_safe_unlink_removes_a_file_and_refuses_a_folder(self) -> None:
        with resolved_temp_dir() as root:
            (root / "d").mkdir()
            (root / "f.txt").write_text("x", encoding="utf-8")
            self.assertTrue(safe_unlink(root / "f.txt", [root]))
            self.assertFalse(safe_unlink(root / "f.txt", [root]))
            with self.assertRaises(UnsafePathError):
                safe_unlink(root / "d", [root])
            self.assertTrue(os.path.isdir(root / "d"))


if __name__ == "__main__":
    unittest.main()
