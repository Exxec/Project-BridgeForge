import unittest
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.copy_drift import compare_copies, sync_copies
from tests.support import link_dir, resolved_temp_dir


def _mod(root: Path) -> Path:
    (root / "data").mkdir(parents=True)
    (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
    (root / "data" / "a.csv").write_text("a", encoding="utf-8")
    return root


class CopyDriftSyncTests(unittest.TestCase):
    def _rig(self, base: Path) -> Path:
        (base / "core").mkdir()
        rig = base / "rig"
        (rig / "mods").mkdir(parents=True)
        link_dir(base / "core", rig / "starsector-core")
        return rig

    def test_sync_copies_working_to_rig_and_keeps_extras_without_prune(self) -> None:
        with resolved_temp_dir() as base:
            working, rig = _mod(base / "working"), self._rig(base)
            deployed = _mod(rig / "mods" / "Fixture")
            (working / "data" / "a.csv").write_text("changed", encoding="utf-8")
            (working / "data" / "new.csv").write_text("n", encoding="utf-8")
            (deployed / "data" / "old.csv").write_text("o", encoding="utf-8")
            result = sync_copies(working, deployed)
            self.assertEqual(sorted(result["copied"]), ["data/a.csv", "data/new.csv"])
            self.assertEqual(result["extra_kept"], ["data/old.csv"])
            self.assertEqual(result["status"], "DRIFT")
            self.assertEqual((deployed / "data" / "a.csv").read_text(encoding="utf-8"), "changed")
            self.assertEqual((working / "data" / "a.csv").read_text(encoding="utf-8"), "changed")

    def test_sync_makes_the_first_copy_when_the_rig_folder_does_not_exist(self) -> None:
        with resolved_temp_dir() as base:
            working, rig = _mod(base / "working"), self._rig(base)
            result = sync_copies(working, rig / "mods" / "Fixture")
            self.assertEqual(result["status"], "PASS")
            self.assertTrue((rig / "mods" / "Fixture" / "data" / "a.csv").is_file())
            with self.assertRaises(ValueError):
                sync_copies(working, base / "elsewhere" / "Fixture")
            self.assertFalse((base / "elsewhere").exists())

    def test_prune_moves_extras_into_the_rig_pruned_folder(self) -> None:
        with resolved_temp_dir() as base:
            working, rig = _mod(base / "working"), self._rig(base)
            deployed = _mod(rig / "mods" / "Fixture")
            (deployed / "data" / "old.csv").write_text("o", encoding="utf-8")
            result = sync_copies(working, deployed, prune=True, today="2026-09-27")
            self.assertEqual(result["status"], "PASS")
            self.assertTrue((rig / "pruned" / "2026-09-27" / "Fixture" / "data" / "old.csv").is_file())
            self.assertEqual(compare_copies(working, deployed)["drift_count"], 0)

    def test_sync_refuses_a_copy_outside_a_linked_rig(self) -> None:
        with resolved_temp_dir() as base:
            working = _mod(base / "working")
            (base / "real" / "starsector-core").mkdir(parents=True)
            deployed = _mod(base / "real" / "mods" / "Fixture")
            (working / "data" / "a.csv").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                sync_copies(working, deployed)
            self.assertEqual((deployed / "data" / "a.csv").read_text(encoding="utf-8"), "a")
            self.assertEqual(main(["copy-drift", str(working), str(deployed), "--sync"]), 2)

    def test_prune_without_sync_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            working = _mod(base / "working")
            self.assertEqual(main(["copy-drift", str(working), str(working), "--prune"]), 2)


if __name__ == "__main__":
    unittest.main()
