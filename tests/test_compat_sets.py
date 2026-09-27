from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.support import link_dir


from bridgeforge.cli import main
from bridgeforge.compat_sets import (
    CompatSetError,
    install_compat_set,
    lib_mod_ids,
    load_compat_sets,
    resolve_set,
    set_mod_ids,
)
from bridgeforge.reference_rigs import write_reference_rig_manifest


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _fixture_data_file(directory: Path) -> Path:
    """A small, self-contained compat-set definitions file so tests never depend on the real standard.json."""
    data = {
        "schema_version": 1,
        "sets": {
            "libs": {
                "mods": {
                    "lib_a": {"name": "Lib A", "role": "lib", "gameVersion": "0.98a-RC8", "required_by": []},
                    "lib_b": {"name": "Lib B", "role": "lib", "gameVersion": "0.98a-RC8", "required_by": []},
                }
            },
            "standard": {
                "extends": ["libs"],
                "mods": {
                    "content_a": {"name": "Content A", "role": "content", "gameVersion": "0.98a-RC8", "required_by": []},
                    "content_b": {"name": "Content B", "role": "content", "gameVersion": "0.98a-RC7", "required_by": []},
                },
            },
        },
    }
    path = directory / "fixture-compat-sets.json"
    _write_json(path, data)
    return path


def _make_source_mod(root: Path, mod_id: str, folder_name: str, game_version: str = "0.98a-RC8") -> Path:
    mod = root / folder_name
    mod.mkdir(parents=True, exist_ok=True)
    _write_json(mod / "mod_info.json", {"id": mod_id, "gameVersion": game_version})
    (mod / "data").mkdir(exist_ok=True)
    (mod / "data" / "file.txt").write_text("content", encoding="utf-8")
    (mod / "runtime_settings.json").write_text('{"enabled":true}', encoding="utf-8")
    return mod


def _make_rig(root: Path) -> Path | None:
    core_real = root / "core_real"
    core_real.mkdir()
    rig = root / "rig"
    (rig / "mods").mkdir(parents=True)
    try:
        link_dir(core_real, rig / "starsector-core")
    except OSError:
        return None
    return rig


class LoadAndResolveTests(unittest.TestCase):
    def test_historical_era_sets_track_exact_library_evidence_status(self) -> None:
        data = load_compat_sets()
        for name in ("era-0.8.1a", "era-0.7.2a", "era-0.97a-RC11", "era-0.65.2a", "era-0.62a"):
            self.assertIn(name, data["sets"])
        exigency = resolve_set(data, "era-0.7.2a")
        self.assertEqual(exigency["lw_lazylib"]["evidence_status"], "EXACT_VERSION_LOCATED")
        self.assertEqual(exigency["lw_lazylib"]["version"], "2.1")
        self.assertEqual(exigency["shaderLib"]["evidence_status"], "EXACT_VERSION_LOCATED")
        self.assertEqual(exigency["shaderLib"]["version"], "Beta 1.2.1b")

    def test_resolve_set_merges_extends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_path = _fixture_data_file(Path(directory))
            data = load_compat_sets(data_path)
            resolved = resolve_set(data, "standard")
            self.assertEqual(set(resolved), {"lib_a", "lib_b", "content_a", "content_b"})
            self.assertEqual(set_mod_ids(data, "libs"), ["lib_a", "lib_b"])
            self.assertEqual(lib_mod_ids(data, "standard"), ["lib_a", "lib_b"])

    def test_unknown_set_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_path = _fixture_data_file(Path(directory))
            data = load_compat_sets(data_path)
            with self.assertRaises(CompatSetError):
                resolve_set(data, "nope")

    def test_bundled_standard_set_loads_and_resolves(self) -> None:
        data = load_compat_sets()
        resolved = resolve_set(data, "standard")
        self.assertIn("lw_lazylib", resolved)
        self.assertIn("MagicLib", resolved)
        self.assertIn("aitweaks", resolved)
        self.assertIn("nexerelin", resolved)
        self.assertGreaterEqual(len([m for m in resolved.values() if m["role"] == "content" and m is not resolved.get("aitweaks") and m is not resolved.get("nexerelin")]), 3)


class InstallCompatSetTests(unittest.TestCase):
    def test_registered_historical_install_does_not_require_core_junction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = root / "historical"
            (rig / "starsector-core").mkdir(parents=True)
            (rig / "starsector-core" / "starfarer.api.jar").write_bytes(b"old-api")
            (rig / "starsector.bat").write_text("@echo off\n", encoding="utf-8")
            (rig / "mods").mkdir()
            manifest = write_reference_rig_manifest(rig, game_version="0.7.2a", output=root / "rig.json")
            data_path = _fixture_data_file(root)
            source = root / "source"
            result = install_compat_set("standard", rig, source, data_path=data_path, dry_run=True, reference_manifest=manifest)
            self.assertEqual(result["missing"], ["content_a", "content_b", "lib_a", "lib_b"])
            self.assertEqual(result["reference_manifest"], str(manifest.resolve()))

    def test_refuses_when_core_is_not_a_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = _fixture_data_file(root)
            runtime_dir = root / "rig"
            (runtime_dir / "starsector-core").mkdir(parents=True)
            source = root / "source"
            source.mkdir()
            with self.assertRaises(CompatSetError):
                install_compat_set("standard", runtime_dir, source, data_path=data_path)

    def test_dry_run_reports_plan_without_copying(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            data_path = _fixture_data_file(root)
            source = root / "source"
            _make_source_mod(source, "lib_a", "LibA")
            _make_source_mod(source, "lib_b", "LibB")
            _make_source_mod(source, "content_a", "ContentA")
            # content_b deliberately absent from source -> reported missing.

            result = install_compat_set("standard", rig, source, data_path=data_path, dry_run=True)
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["missing"], ["content_b"])
            planned_ids = {item["id"] for item in result["plan"]}
            self.assertEqual(planned_ids, {"lib_a", "lib_b", "content_a"})
            for item in result["plan"]:
                self.assertEqual(item["reason"], "missing_in_rig")
            # Nothing was actually copied.
            self.assertFalse((rig / "mods" / "LibA").exists())

    def test_install_copies_missing_mods_and_skips_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            data_path = _fixture_data_file(root)
            source = root / "source"
            _make_source_mod(source, "lib_a", "LibA")
            _make_source_mod(source, "lib_b", "LibB")
            _make_source_mod(source, "content_a", "ContentA")
            _make_source_mod(source, "content_b", "ContentB", game_version="0.98a-RC7")

            result = install_compat_set("standard", rig, source, data_path=data_path)
            self.assertEqual(result["missing"], [])
            installed_ids = {item["id"] for item in result["installed"]}
            self.assertEqual(installed_ids, {"lib_a", "lib_b", "content_a", "content_b"})
            self.assertTrue((rig / "mods" / "LibA" / "data" / "file.txt").is_file())
            self.assertTrue((rig / "mods" / "LibA" / "runtime_settings.json").is_file())
            self.assertTrue((rig / "mods" / "ContentB" / "mod_info.json").is_file())

            # A second install run should find everything already identical and copy nothing.
            result_again = install_compat_set("standard", rig, source, data_path=data_path)
            self.assertEqual(set(result_again["skipped_identical"]), {"lib_a", "lib_b", "content_a", "content_b"})
            self.assertEqual(result_again["installed"], [])

    def test_never_writes_into_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            data_path = _fixture_data_file(root)
            source = root / "source"
            _make_source_mod(source, "lib_a", "LibA")
            _make_source_mod(source, "lib_b", "LibB")
            _make_source_mod(source, "content_a", "ContentA")
            _make_source_mod(source, "content_b", "ContentB")
            before = sorted(p.relative_to(source) for p in source.rglob("*"))

            install_compat_set("standard", rig, source, data_path=data_path)

            after = sorted(p.relative_to(source) for p in source.rglob("*"))
            self.assertEqual(before, after)

    def test_warns_on_game_version_mismatch_with_rig(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            # Pre-populate the rig's own mods/ with an RC8 mod, so _rig_game_version infers RC8.
            _make_source_mod(rig / "mods", "already_installed", "AlreadyInstalled", game_version="0.98a-RC8")
            data_path = _fixture_data_file(root)
            source = root / "source"
            _make_source_mod(source, "lib_a", "LibA", game_version="0.98a-RC8")
            # An older RC of the same base version is accepted by the launcher (real LazyLib/LunaLib are
            # 0.98a-RC5 and ran in the RC8 rig), so it must not warn.
            _make_source_mod(source, "lib_b", "LibB", game_version="0.98a-RC5")
            _make_source_mod(source, "content_a", "ContentA", game_version="0.98a-RC8")
            # A different base version is what actually gets a mod unchecked, so it must warn.
            _make_source_mod(source, "content_b", "ContentB", game_version="0.97a")

            result = install_compat_set("standard", rig, source, data_path=data_path, dry_run=True)
            self.assertEqual(result["rig_game_version"], "0.98a-RC8")
            self.assertTrue(any("content_b" in warning for warning in result["warnings"]))
            self.assertFalse(any("lib_a" in warning for warning in result["warnings"]))
            self.assertFalse(any("lib_b" in warning for warning in result["warnings"]))

    def test_cli_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Could not create an NTFS junction in this environment.")
            source = root / "source"
            _make_source_mod(source, "lw_lazylib", "LazyLib")
            _make_source_mod(source, "MagicLib", "MagicLib")
            _make_source_mod(source, "lunalib", "LunaLib")
            _make_source_mod(source, "shaderLib", "zz GraphicsLib")
            _make_source_mod(source, "aitweaks", "AI Tweaks")
            _make_source_mod(source, "nexerelin", "Nexerelin")
            _make_source_mod(source, "swp", "Ship_Weapon Pack")
            _make_source_mod(source, "IndEvo", "Industrial.Evolution")
            _make_source_mod(source, "US", "Unknown Skies")
            _make_source_mod(source, "tahlan", "Tahlan Shipworks")
            exit_code = main(
                ["compat-set", "install", "standard", "--runtime", str(rig), "--source-mods", str(source), "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
