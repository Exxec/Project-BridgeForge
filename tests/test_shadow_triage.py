"""`vanilla-path-shadowing` triage against the reference rig (ROADMAP item 73 D3)."""
import json
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.reference_rigs import reference_core_for_game_version
from bridgeforge.shadow_triage import REMOVED_SHADOW_FOLDER, triage
from tests.support import resolved_temp_dir

OLD_SYSTEM = '{"id":"damper","type":"STAT_MOD","regen":1}'
RC8_SYSTEM = '{"id":"damper","type":"STAT_MOD","regen":2}'
EDITED_SYSTEM = '{"id":"damper","type":"STAT_MOD","regen":5}'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _layout(root: Path) -> tuple[Path, Path, Path, Path]:
    """(working, rc8 core, reference core, workspace)"""
    workspace = root / "Mod"
    working = workspace / "working"
    rc8, reference = root / "rc8", root / "ref"
    _write(working / "mod_info.json", '{"id":"m","gameVersion":"0.9a-RC8"}')
    for name in ("damper.system", "flare.system"):
        _write(rc8 / "data" / "shipsystems" / name, RC8_SYSTEM.replace("damper", name[:-7]))
        _write(reference / "data" / "shipsystems" / name, OLD_SYSTEM.replace("damper", name[:-7]))
    return working, rc8, reference, workspace


class ShadowTriageTests(unittest.TestCase):
    def test_identical_copy_of_old_vanilla_is_moved_and_a_changed_file_is_kept_with_a_diff(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, workspace = _layout(root)
            _write(working / "data" / "shipsystems" / "damper.system", OLD_SYSTEM)  # unchanged copy of old vanilla
            _write(working / "data" / "shipsystems" / "flare.system", EDITED_SYSTEM.replace("damper", "flare"))  # the mod's own change
            apply_fix(compute_fix(working, "vanilla-path-shadowing", {"vanilla_core": rc8, "reference_core": reference}))
            moved = workspace / "scratch" / REMOVED_SHADOW_FOLDER / "data" / "shipsystems" / "damper.system"
            report = (workspace / "reports" / "SHADOW_TRIAGE.md").read_text(encoding="utf-8")
            self.assertEqual(moved.read_text(encoding="utf-8"), OLD_SYSTEM)
            self.assertFalse((working / "data" / "shipsystems" / "damper.system").exists())
            self.assertTrue((working / "data" / "shipsystems" / "flare.system").is_file())  # kept
            with self.assertRaises(FixerError):  # idempotent: nothing left to move, the report already exists
                compute_fix(working, "vanilla-path-shadowing", {"vanilla_core": rc8, "reference_core": reference})
        self.assertIn("`data/shipsystems/damper.system`", report)
        self.assertIn("### `data/shipsystems/flare.system`", report)
        self.assertIn("regen: 1 -> 5", report)

    def test_triage_sorts_identical_changed_and_missing_in_reference(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, _ = _layout(root)
            _write(working / "data" / "shipsystems" / "damper.system", OLD_SYSTEM)
            _write(working / "data" / "shipsystems" / "flare.system", EDITED_SYSTEM)
            _write(rc8 / "data" / "shipsystems" / "new.system", RC8_SYSTEM)  # only RC8 has it
            _write(working / "data" / "shipsystems" / "new.system", EDITED_SYSTEM)
            _write(working / "data" / "shipsystems" / "same_as_rc8.system", RC8_SYSTEM)
            _write(rc8 / "data" / "shipsystems" / "same_as_rc8.system", RC8_SYSTEM)  # not a shadow
            result = triage(working, rc8, reference)
        self.assertEqual(result["identical"], ["data/shipsystems/damper.system"])
        self.assertEqual([c["path"] for c in result["changed"]], ["data/shipsystems/flare.system"])
        self.assertEqual([c["path"] for c in result["no_reference"]], ["data/shipsystems/new.system"])

    def test_without_a_reference_core_the_fixer_behaves_as_before(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, _reference, _ = _layout(root)
            _write(working / "data" / "shipsystems" / "damper.system", OLD_SYSTEM)
            with self.assertRaises(FixerError):
                compute_fix(working, "vanilla-path-shadowing", {"vanilla_core": rc8})
            self.assertTrue((working / "data" / "shipsystems" / "damper.system").is_file())

    def test_reference_rig_is_found_by_the_mods_game_version(self) -> None:
        with resolved_temp_dir() as root:
            install = root / "Starsector9a"
            (install / "starsector-core").mkdir(parents=True)
            registry = root / "bridgeforge-state" / "reference-rigs"
            registry.mkdir(parents=True)
            (registry / "0.9a.json").write_text(json.dumps({"schema_version": 1, "mode": "REFERENCE_RIG", "install": str(install)}), encoding="utf-8")
            found = reference_core_for_game_version("0.9a-RC8", repo_root=root)
            near = reference_core_for_game_version("0.95a", repo_root=root)
        self.assertEqual(found, install / "starsector-core")
        self.assertIsNone(near)  # no nearest-version guess


if __name__ == "__main__":
    unittest.main()
