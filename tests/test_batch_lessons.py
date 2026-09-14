"""Lessons from the 2026-09-14 batch intake of 25 old mods (Starsectormodstodo)."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.behavior_discovery import build_archaeology
from bridgeforge.models import TargetProfile
from bridgeforge.scanner import _parse_json, _source_class_index, scan_mod


def _mod(root: Path, **info) -> Path:
    mod = root / "mod"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "mod_info.json").write_text(json.dumps({"id": "old", "name": "Old", "version": "1", "gameVersion": "0.53.1a", **info}), encoding="utf-8")
    return mod


def _ids(result, finding_id: str) -> list:
    return [f for f in result.findings if f.id == finding_id]


LOGGER = 'package data.scripts;\npublic class Loader {\n  void f() { log("couldn\'t find the class for a System"); }\n}\n'


class StringLiteralDeclarationTests(unittest.TestCase):
    def test_words_after_class_in_a_string_are_not_a_class(self) -> None:
        # Xenoargh's AI Overhaul: archaeology read a class `data.scripts.for` out of a log message.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "data" / "scripts" / "Loader.java").write_text(LOGGER, encoding="utf-8")
            text = json.dumps(build_archaeology(mod))
            index = _source_class_index(mod)
        self.assertIn("class:data.scripts.Loader", text)
        self.assertNotIn("class:data.scripts.for", text)
        self.assertEqual(sorted(index), ["data.scripts.Loader"])


class LooseScriptJarTests(unittest.TestCase):
    def test_loose_data_scripts_need_no_jar(self) -> None:
        # Gekelonians (0.53) ships only loose scripts; the game compiles data/**/*.java at load.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory), modPlugin="data.scripts.world.HappyGen")
            (mod / "data" / "scripts" / "world").mkdir(parents=True)
            (mod / "data" / "scripts" / "world" / "HappyGen.java").write_text("package data.scripts.world;\npublic class HappyGen {}\n", encoding="utf-8")
            (mod / "src" / "data" / "scripts").mkdir(parents=True)
            (mod / "src" / "data" / "scripts" / "Packed.java").write_text("package data.scripts;\npublic class Packed {}\n", encoding="utf-8")
            (mod / "data" / "config").mkdir(parents=True)
            (mod / "data" / "config" / "x.json").write_text(json.dumps({"plugin": "data.scripts.Packed"}), encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        missing = _ids(result, "configured-source-class-missing-from-jar")
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].evidence, ["data.scripts.Packed"])  # src/ needs a jar; loose data/ doesn't


class VanillaShadowGroupingTests(unittest.TestCase):
    def test_many_shadows_in_one_folder_become_one_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _mod(root)
            for base, text in ((root / "core", "vanilla"), (mod, "rebalanced")):
                (base / "data" / "hullmods").mkdir(parents=True, exist_ok=True)
                (base / "data" / "weapons").mkdir(parents=True, exist_ok=True)
                for index in range(8):
                    (base / "data" / "hullmods" / f"Mod{index}.java").write_text(f"class Mod{index} {{ /* {text} */ }}", encoding="utf-8")
                (base / "data" / "weapons" / "one.wpn").write_text(json.dumps({"id": "one", "note": text}), encoding="utf-8")
            result = scan_mod(mod, TargetProfile(), root / "core")
        shadows = _ids(result, "vanilla-path-shadowing")
        by_file = {f.file: f for f in shadows}
        self.assertEqual(sorted(by_file), ["data/hullmods", "data/weapons/one.wpn"])
        self.assertEqual(by_file["data/hullmods"].evidence[0], "count:8")
        self.assertEqual(by_file["data/weapons/one.wpn"].classification, "MANUAL")


class GameVersionDefaultTargetTests(unittest.TestCase):
    def _version_findings(self, declared: str) -> list:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            mod.mkdir()
            (mod / "mod_info.json").write_text(json.dumps({"id": "v", "name": "V", "version": "1", "gameVersion": declared}), encoding="utf-8")
            return _ids(scan_mod(mod, TargetProfile()), "mod-info-game-version-inexact")  # default target '0.98.x'

    def test_default_target_flags_an_older_series(self) -> None:
        # The 2026-09-14 batch (0.53a-0.9.1a) got no version finding because '0.98.x' skipped the check.
        hits = self._version_findings("0.9.1a-RC8")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].evidence, ["declared:0.9.1a-RC8", "target:0.98a"])

    def test_same_series_any_rc_is_quiet(self) -> None:
        self.assertEqual(self._version_findings("0.98a-RC7"), [])
        self.assertEqual(self._version_findings("0.98a"), [])


class OrgJsonSeparatorTests(unittest.TestCase):
    # starsector-core/json.jar (org.json) accepts all of these; checked with the rig JDK, 2026-09-14.
    TEXT = '{\n\t# officers\n\t"baseNumOfficers":45;\n\t"b"=2,\n\t"c"=>3;\n\t"note":"a;b=c",\n}'

    def test_semicolons_and_equals_separators_parse_like_org_json(self) -> None:
        data, tolerances = _parse_json(self.TEXT)
        self.assertEqual(data, {"baseNumOfficers": 45, "b": 2, "c": 3, "note": "a;b=c"})  # strings untouched
        self.assertTrue({"semicolon-separators", "equals-key-separators", "hash-comments"} <= tolerances)

    def test_settings_with_semicolons_scan_as_safe_not_unknown(self) -> None:
        # Xenoargh's Rebal: "baseNumOfficers":45; made settings.json an UNKNOWN (unparsed) file.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "config").mkdir(parents=True)
            (mod / "data" / "config" / "settings.json").write_text(self.TEXT, encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(result, "unverified-json-syntax"), [])
        separator = _ids(result, "json-orgjson-separator")
        self.assertEqual(len(separator), 1)
        self.assertEqual(separator[0].evidence, ["equals-key-separators", "semicolon-separators"])

    def test_a_real_error_reports_where_the_lenient_rewrite_stopped(self) -> None:
        with self.assertRaises(json.JSONDecodeError) as caught:
            _parse_json('{\n\t# x\n\t"a":1,\n\t"b" 2\n}')
        self.assertIn("after lenient rewrites it still fails", str(caught.exception))
        self.assertIn("line 4", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
