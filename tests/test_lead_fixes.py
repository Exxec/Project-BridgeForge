"""Regression tests for fixes made while wiring the 2026-09-11 features (crash attribution, profiles)."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.log_triage import class_owner_index
from bridgeforge.probe_config import PROFILE_FILE, parse_profile, write_probe_config

try:
    import _winapi
except ImportError:  # pragma: no cover - non-Windows
    _winapi = None


def _mod_with_jar(mods: Path, folder: str, mod_id: str, classes: list[str]) -> None:
    mod = mods / folder
    (mod / "jars").mkdir(parents=True)
    (mod / "mod_info.json").write_text(json.dumps({"id": mod_id, "jars": ["jars/m.jar"]}), encoding="utf-8")
    with zipfile.ZipFile(mod / "jars" / "m.jar", "w") as archive:
        for name in classes:
            archive.writestr(name.replace(".", "/") + ".class", b"\xca\xfe\xba\xbe")


class OwnerIndexPackageFallbackTests(unittest.TestCase):
    def test_shared_data_packages_are_never_owned_but_exact_classes_are(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mods = Path(directory)
            # Both mods put loose classes in the generic data.scripts package (as Exigency and SEEKER do).
            _mod_with_jar(mods, "A", "mod_a", ["data.scripts.APlugin", "com.alpha.core.Engine"])
            _mod_with_jar(mods, "B", "mod_b", ["data.scripts.BPlugin", "data.hullmods.BOnly"])
            (mods / "enabled_mods.json").write_text('{"enabledMods": ["mod_a", "mod_b"]}', encoding="utf-8")

            index = class_owner_index(mods)

            self.assertEqual(index["data.scripts.APlugin"], "mod_a")
            self.assertEqual(index["data.scripts.BPlugin"], "mod_b")
            self.assertNotIn("data.scripts", index)  # shared: would misattribute
            self.assertNotIn("data.hullmods", index)  # data.* never used as a fallback, even if unique
            self.assertEqual(index["com.alpha.core"], "mod_a")  # unique, non-generic package still falls back

    def test_package_claimed_by_two_mods_is_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mods = Path(directory)
            _mod_with_jar(mods, "A", "mod_a", ["org.shared.util.X"])
            _mod_with_jar(mods, "B", "mod_b", ["org.shared.util.Y"])
            index = class_owner_index(mods, enabled_only=False)
            self.assertNotIn("org.shared.util", index)
            self.assertEqual(index["org.shared.util.X"], "mod_a")


def _make_rig(root: Path) -> Path | None:
    if _winapi is None:
        return None
    (root / "core_real").mkdir()
    rig = root / "rig"
    rig.mkdir()
    try:
        _winapi.CreateJunction(str(root / "core_real"), str(rig / "starsector-core"))
    except OSError:
        return None
    return rig


class StaleProfileTests(unittest.TestCase):
    def test_config_without_profile_retires_a_leftover_rig_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            mod = root / "fixture_mod"
            (mod / "data" / "hulls").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id":"fixture_mod"}', encoding="utf-8")
            (mod / "data" / "hulls" / "ship_data.csv").write_text("id,hints\nfx_hull1,\n", encoding="utf-8")

            write_probe_config(mod, rig, profile=parse_profile("credits = 100\n"))
            profile_path = rig / "saves" / "common" / PROFILE_FILE
            self.assertTrue(profile_path.is_file())

            result = write_probe_config(mod, rig, setups=["credits:5"])
            self.assertFalse(profile_path.exists())
            retired = Path(result["retired_profile"])
            self.assertTrue(retired.is_file())
            self.assertIn("credits = 100", retired.read_text(encoding="utf-8"))

    def test_dry_run_never_retires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            mod = root / "fixture_mod"
            (mod / "data" / "hulls").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id":"fixture_mod"}', encoding="utf-8")
            (mod / "data" / "hulls" / "ship_data.csv").write_text("id,hints\nfx_hull1,\n", encoding="utf-8")
            write_probe_config(mod, rig, profile=parse_profile("credits = 100\n"))
            write_probe_config(mod, rig, dry_run=True)
            self.assertTrue((rig / "saves" / "common" / PROFILE_FILE).is_file())


if __name__ == "__main__":
    unittest.main()
