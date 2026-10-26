"""ROADMAP 65 (raw folder intake, planner listing) and 60f(3) (LunaLib install rule)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.archive_intake import inspect_zip_archive
from bridgeforge.intake import unprocessed_raw_folders, zip_raw_folder
from bridgeforge.probe.probe_group import ProbeGroupError, lunalib_rule
from tests.support import resolved_temp_dir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RawFolderIntakeTests(unittest.TestCase):
    def test_raw_folder_is_zipped_into_the_intake_path_and_is_a_safe_archive(self) -> None:
        with resolved_temp_dir() as root:
            raw = root / "In operation" / "Yellow Jackets"
            _write(raw / "mod_info.json", '{"id": "yj"}')
            _write(raw / "data" / "a.csv", "id\n")
            zipped = zip_raw_folder(raw, root)
            again = zip_raw_folder(raw, root)
            preflight = inspect_zip_archive(zipped)
            untouched = (raw / "mod_info.json").is_file()
        self.assertEqual(zipped, root / "In operation" / "_raw-zips" / "Yellow Jackets.zip")
        self.assertEqual(again, zipped)
        self.assertTrue(preflight["safe_to_stage"])
        self.assertEqual(preflight["candidate_mod_roots"], ["Yellow Jackets"])
        self.assertTrue(untouched)

    def test_a_modpack_folder_name_with_a_note_gets_a_portable_zip_name(self) -> None:
        with resolved_temp_dir() as root:
            raw = root / "packs" / "Templars Expanded V2.5.2 (DISABLE UI SCALING!)"
            _write(raw / "mod_info.json", "{}")
            zipped = zip_raw_folder(raw, root)
            roots = inspect_zip_archive(zipped)["candidate_mod_roots"]
        self.assertEqual(zipped.name, "Templars Expanded V2.5.2 -DISABLE UI SCALING.zip")
        self.assertEqual(roots, ["Templars Expanded V2.5.2 -DISABLE UI SCALING"])

    def test_a_folder_without_a_mod_is_refused_and_a_changed_zip_is_never_overwritten(self) -> None:
        with resolved_temp_dir() as root:
            empty = root / "In operation" / "Empty"
            _write(empty / "notes.txt", "x")
            with self.assertRaises(ValueError):
                zip_raw_folder(empty, root)
            raw = root / "In operation" / "Mod"
            _write(raw / "mod_info.json", "{}")
            zip_raw_folder(raw, root)
            _write(raw / "extra.txt", "changed since")
            with self.assertRaises(ValueError):
                zip_raw_folder(raw, root)

    def test_planner_lists_only_unprocessed_raw_folders(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            _write(queue / "Raw One" / "mod_info.json", "{}")
            _write(queue / "Raw Two" / "Inner" / "mod_info.json", "{}")
            _write(queue / "Done Mod" / "working" / "mod_info.json", "{}")
            _write(queue / "_raw-zips" / "x" / "mod_info.json", "{}")
            _write(queue / "Not a mod" / "readme.txt", "x")
            found = unprocessed_raw_folders(queue)
        self.assertEqual([f["folder"] for f in found], ["Raw One", "Raw Two"])
        self.assertEqual(found[1]["mod_root"], "Inner")


class LunaLibRuleTests(unittest.TestCase):
    def _mods(self, root: Path, graphicslib_version: str) -> tuple[Path, dict[str, str]]:
        mods = root / "mods"
        _write(mods / "GraphicsLib" / "mod_info.json", json.dumps({"id": "shaderLib", "version": graphicslib_version}))
        _write(mods / "LunaLib" / "mod_info.json", json.dumps({"id": "lunalib", "version": "2.0.5"}))
        return mods, {"shaderLib": "GraphicsLib", "lunalib": "LunaLib"}

    def test_graphicslib_1_12_1_gets_lunalib_automatically(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1")
            enable, why, advice = lunalib_rule(["shaderLib", "demo"], installed, mods)
        self.assertTrue(enable)
        self.assertIn("RC8-25", why)
        self.assertIsNone(advice)

    def test_no_lunalib_opts_out_and_keeps_the_advice(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1")
            enable, why, advice = lunalib_rule(["shaderLib"], installed, mods, no_lunalib=True)
        self.assertFalse(enable)
        self.assertIn("--no-lunalib", why)
        self.assertIn("--with-lunalib", advice)

    def test_other_versions_stay_advice_only_until_with_lunalib_is_given(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.7.0")
            plain = lunalib_rule(["shaderLib"], installed, mods)
            forced = lunalib_rule(["shaderLib"], installed, mods, with_lunalib=True)
        self.assertEqual(plain[0], False)
        self.assertIsNotNone(plain[2])
        self.assertTrue(forced[0])
        self.assertIn("forced", forced[1])

    def test_nothing_happens_without_graphicslib_or_when_lunalib_is_already_enabled(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1")
            self.assertEqual(lunalib_rule(["demo"], installed, mods), (False, None, None))
            self.assertEqual(lunalib_rule(["shaderLib", "lunalib"], installed, mods), (False, None, None))

    def test_contradicting_flags_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            mods, installed = self._mods(root, "1.12.1")
            with self.assertRaises(ProbeGroupError):
                lunalib_rule(["shaderLib"], installed, mods, with_lunalib=True, no_lunalib=True)


if __name__ == "__main__":
    unittest.main()
