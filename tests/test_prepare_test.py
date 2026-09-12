from __future__ import annotations

import _winapi
import json
import os
import tempfile
import unittest
from pathlib import Path

from bridgeforge.prepare_test import PrepareTestError, prepare_test


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_mod(root: Path, name: str = "Fixture") -> None:
    _write(root / "mod_info.json", f'{{"id":"fixture","name":"{name}"}}')
    _write(root / "data" / "hulls" / "wing_data.csv", "id,role\nwing_a,FIGHTER\n")


class PrepareTestDriftTests(unittest.TestCase):
    def test_drift_detected_and_reported_without_sync(self) -> None:
        with tempfile.TemporaryDirectory() as working_dir, tempfile.TemporaryDirectory() as rig_dir:
            working = Path(working_dir)
            rig = Path(rig_dir)
            _make_mod(working)
            _make_mod(rig)
            _write(working / "data" / "hulls" / "ship_data.csv", "id,name\nship1,Ship One\n")
            result = prepare_test(working, rig)
            self.assertEqual(result["status"], "DRIFT")
            self.assertFalse(result["synced"])
            self.assertIn("data/hulls/ship_data.csv", result["drift_before_sync"]["missing_in_deployed"])
            # never modifies the rig without --sync
            self.assertFalse((rig / "data" / "hulls" / "ship_data.csv").exists())

    def test_sync_fixes_drift(self) -> None:
        with tempfile.TemporaryDirectory() as working_dir, tempfile.TemporaryDirectory() as rig_dir:
            working = Path(working_dir)
            rig = Path(rig_dir)
            _make_mod(working)
            _make_mod(rig)
            _write(working / "data" / "hulls" / "ship_data.csv", "id,name\nship1,Ship One\n")
            result = prepare_test(working, rig, sync=True)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["synced"])
            self.assertIn("data/hulls/ship_data.csv", result["synced_files"])
            self.assertEqual(
                (rig / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8"),
                "id,name\nship1,Ship One\n",
            )
            self.assertEqual(result["drift_after_sync"]["status"], "PASS")

    def test_sync_never_deletes_extras_but_leftover_drift_is_reported_as_error(self) -> None:
        with tempfile.TemporaryDirectory() as working_dir, tempfile.TemporaryDirectory() as rig_dir:
            working = Path(working_dir)
            rig = Path(rig_dir)
            _make_mod(working)
            _make_mod(rig)
            _write(working / "data" / "hulls" / "ship_data.csv", "id,name\nship1,Ship One\n")
            _write(rig / "data" / "extra" / "leftover.txt", "leftover")
            with self.assertRaises(PrepareTestError):
                prepare_test(working, rig, sync=True)
            # the missing file was still synced, and the extra was never deleted
            self.assertEqual(
                (rig / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8"),
                "id,name\nship1,Ship One\n",
            )
            self.assertTrue((rig / "data" / "extra" / "leftover.txt").is_file())

    def test_sync_never_copies_rig_to_working(self) -> None:
        with tempfile.TemporaryDirectory() as working_dir, tempfile.TemporaryDirectory() as rig_dir:
            working = Path(working_dir)
            rig = Path(rig_dir)
            _make_mod(working)
            _make_mod(rig)
            _write(rig / "data" / "hulls" / "wing_data.csv", "id,role\nwing_a,BOMBER\n")
            result = prepare_test(working, rig, sync=True)
            # working's wing_data.csv content must be untouched (still FIGHTER, not BOMBER)
            self.assertIn("id,role\nwing_a,FIGHTER", (working / "data" / "hulls" / "wing_data.csv").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "PASS")

    def test_no_drift_reports_pass_without_syncing(self) -> None:
        with tempfile.TemporaryDirectory() as working_dir, tempfile.TemporaryDirectory() as rig_dir:
            working = Path(working_dir)
            rig = Path(rig_dir)
            _make_mod(working)
            _make_mod(rig)
            result = prepare_test(working, rig)
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["synced"])


class PrepareTestJunctionTests(unittest.TestCase):
    def test_junction_reports_same_folder(self) -> None:
        with tempfile.TemporaryDirectory() as base_dir:
            base = Path(base_dir)
            working = base / "working"
            working.mkdir()
            _make_mod(working)
            junction = base / "rig_junction"
            try:
                _winapi.CreateJunction(str(working), str(junction))
            except (OSError, AttributeError):
                self.skipTest("Directory junctions are not supported in this environment.")
            try:
                result = prepare_test(working, junction)
                self.assertEqual(result["status"], "SAME_FOLDER")
                self.assertEqual(result["message"], "same folder (junction), nothing to sync")
            finally:
                try:
                    os.rmdir(junction)
                except OSError:
                    pass


class PrepareTestBumpTests(unittest.TestCase):
    def test_bump_changes_tag_before_comparing(self) -> None:
        with tempfile.TemporaryDirectory() as working_dir, tempfile.TemporaryDirectory() as rig_dir:
            working = Path(working_dir)
            rig = Path(rig_dir)
            _make_mod(working)
            _make_mod(rig)
            result = prepare_test(working, rig, bump=True, sync=True)
            self.assertIn("bump", result)
            self.assertEqual(result["bump"]["new_name"], "Fixture [BF r1]")
            data = json.loads((working / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Fixture [BF r1]")
            rig_data = json.loads((rig / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(rig_data["name"], "Fixture [BF r1]")
            self.assertEqual(result["status"], "PASS")


class PrepareTestBootTests(unittest.TestCase):
    def test_boot_module_unavailable_is_reported_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as working_dir, tempfile.TemporaryDirectory() as rig_dir, tempfile.TemporaryDirectory() as runtime_dir:
            working = Path(working_dir)
            rig = Path(rig_dir)
            _make_mod(working)
            _make_mod(rig)
            result = prepare_test(working, rig, boot=Path(runtime_dir), mods=["fixture"])
            self.assertIn("boot_test", result)
            self.assertIn("status", result["boot_test"])

    def test_boot_skipped_when_drift_remains(self) -> None:
        with tempfile.TemporaryDirectory() as working_dir, tempfile.TemporaryDirectory() as rig_dir, tempfile.TemporaryDirectory() as runtime_dir:
            working = Path(working_dir)
            rig = Path(rig_dir)
            _make_mod(working)
            _make_mod(rig)
            _write(working / "data" / "hulls" / "ship_data.csv", "id,name\nship1,Ship One\n")
            result = prepare_test(working, rig, boot=Path(runtime_dir), mods=["fixture"])
            self.assertEqual(result["status"], "DRIFT")
            self.assertEqual(result["boot_test"]["status"], "SKIPPED")


class PrepareTestErrorTests(unittest.TestCase):
    def test_missing_working_dir_raises(self) -> None:
        with tempfile.TemporaryDirectory() as rig_dir:
            with self.assertRaises(PrepareTestError):
                prepare_test(Path(rig_dir) / "does-not-exist", Path(rig_dir))


if __name__ == "__main__":
    unittest.main()
