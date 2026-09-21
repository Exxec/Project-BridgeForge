from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.rebuild_from_reference import rebuild_from_reference


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class RebuildFromReferenceTests(unittest.TestCase):
    """ROADMAP P14 item 21: generalizes E11's real Rebal method - overlay a mod's own genuine
    authored changes (found by diffing against a historical reference rig's vanilla copy) onto a
    fresh copy of current RC8 vanilla, so RC8's own subsequent changes are kept and only the mod's
    real edits carry forward. E12 found the failure mode this whole method exists to avoid: dropping
    a mod's file outright because it shares a path with vanilla, discarding real authored content.
    """

    def _tree(self, root: Path) -> tuple[Path, Path, Path]:
        mod = root / "mod"
        reference = root / "reference"
        current = root / "current"
        return mod, reference, current

    def test_mods_own_field_change_carries_forward_onto_a_field_rc8_added_since(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            rel = "data/hullmods/Foo.java.json"
            _write(reference / rel, {"hitpoints": 100, "shieldType": "FRONT"})
            _write(mod / rel, {"hitpoints": 150, "shieldType": "FRONT"})
            _write(current / rel, {"hitpoints": 100, "shieldType": "FRONT", "smodBonus": 0.1})
            result = rebuild_from_reference(mod, reference, current, "**/*.json")
        self.assertEqual(result["status"], "REBUILT")
        entry = result["files"][0]
        self.assertEqual(entry["status"], "REBUILT")
        self.assertEqual(entry["changes_applied"], ["hitpoints"])
        self.assertEqual(entry["conflicts"], [])

    def test_field_the_mod_removed_is_removed_from_the_rebuilt_current_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            rel = "data/hullmods/Foo.json"
            _write(reference / rel, {"hitpoints": 100, "legacyField": "x"})
            _write(mod / rel, {"hitpoints": 100})
            _write(current / rel, {"hitpoints": 100, "legacyField": "x", "newField": "y"})
            result = rebuild_from_reference(mod, reference, current, "**/*.json", output=root / "out")
            entry = result["files"][0]
            self.assertEqual(entry["status"], "REBUILT")
            rebuilt = json.loads((root / "out" / rel).read_text(encoding="utf-8"))
            self.assertNotIn("legacyField", rebuilt)
            self.assertEqual(rebuilt["newField"], "y")
            self.assertEqual(rebuilt["hitpoints"], 100)

    def test_removed_field_already_absent_in_current_is_not_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            rel = "data/hullmods/Foo.json"
            _write(reference / rel, {"hitpoints": 100, "legacyField": "x"})
            _write(mod / rel, {"hitpoints": 100})
            _write(current / rel, {"hitpoints": 100})  # RC8 also dropped legacyField independently
            result = rebuild_from_reference(mod, reference, current, "**/*.json")
        entry = result["files"][0]
        self.assertEqual(entry["status"], "REBUILT")
        self.assertEqual(entry["conflicts"], [])

    def test_conflict_when_rc8_independently_changed_a_field_the_mod_also_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            rel = "data/hullmods/Foo.json"
            _write(reference / rel, {"hitpoints": 100})
            _write(mod / rel, {"hitpoints": 150})  # mod's own rebalance
            _write(current / rel, {"hitpoints": 200})  # RC8 independently rebalanced it too
            result = rebuild_from_reference(mod, reference, current, "**/*.json")
        entry = result["files"][0]
        self.assertEqual(entry["status"], "CONFLICT")
        self.assertEqual(len(entry["conflicts"]), 1)
        conflict = entry["conflicts"][0]
        self.assertEqual(conflict["path"], "hitpoints")
        self.assertEqual(conflict["reference_value"], 100)
        self.assertEqual(conflict["current_vanilla_value"], 200)
        self.assertEqual(conflict["mod_value"], 150)

    def test_file_identical_to_reference_has_no_genuine_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            rel = "data/hullmods/Foo.json"
            _write(reference / rel, {"hitpoints": 100})
            _write(mod / rel, {"hitpoints": 100})
            _write(current / rel, {"hitpoints": 999})
            result = rebuild_from_reference(mod, reference, current, "**/*.json")
        self.assertEqual(result["status"], "NO_GENUINE_CHANGES")
        self.assertEqual(result["files"][0]["status"], "NO_GENUINE_CHANGES")

    def test_file_with_no_counterpart_in_both_vanilla_copies_is_skipped_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            _write(mod / "data/hullmods/OnlyInMod.json", {"hitpoints": 100})
            result = rebuild_from_reference(mod, reference, current, "**/*.json")
        self.assertEqual(result["files"], [])
        self.assertEqual(result["status"], "NO_GENUINE_CHANGES")

    def test_glob_scopes_which_files_are_considered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            _write(reference / "data/hullmods/Foo.json", {"hitpoints": 100})
            _write(mod / "data/hullmods/Foo.json", {"hitpoints": 150})
            _write(current / "data/hullmods/Foo.json", {"hitpoints": 100})
            _write(reference / "data/weapons/Bar.json", {"damage": 10})
            _write(mod / "data/weapons/Bar.json", {"damage": 20})
            _write(current / "data/weapons/Bar.json", {"damage": 10})
            result = rebuild_from_reference(mod, reference, current, "data/hullmods/**/*.json")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["file"], "data/hullmods/Foo.json")

    def test_output_only_written_for_rebuilt_or_conflict_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            _write(reference / "data/hullmods/Unchanged.json", {"hitpoints": 100})
            _write(mod / "data/hullmods/Unchanged.json", {"hitpoints": 100})
            _write(current / "data/hullmods/Unchanged.json", {"hitpoints": 100})
            rebuild_from_reference(mod, reference, current, "**/*.json", output=root / "out")
            self.assertFalse((root / "out" / "data/hullmods/Unchanged.json").exists())

    def test_cli_rebuild_from_reference_reports_and_applies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, reference, current = self._tree(root)
            rel = "data/hullmods/Foo.json"
            _write(reference / rel, {"hitpoints": 100})
            _write(mod / rel, {"hitpoints": 150})
            _write(current / rel, {"hitpoints": 100, "smodBonus": 0.1})
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main([
                    "rebuild-from-reference", str(mod),
                    "--reference-core", str(reference), "--current-core", str(current),
                    "--glob", "**/*.json", "--apply", str(root / "out"), "--json",
                ])
            self.assertEqual(exit_code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["status"], "REBUILT")
            rebuilt = json.loads((root / "out" / rel).read_text(encoding="utf-8"))
            self.assertEqual(rebuilt, {"hitpoints": 150, "smodBonus": 0.1})


if __name__ == "__main__":
    unittest.main()
