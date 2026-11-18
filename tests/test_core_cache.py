"""ROADMAP-3 96.5 P7: the vanilla core is read once per process, not twice per scan.

A second scan of Bultach Coalition in the same process read the core again. Profiled 2026-11-17, three readers were called
twice per scan and cached nothing:
- `_vanilla_api_jar_class_info`: every class in starfarer.api.jar and starfarer_obf.jar;
- `_vanilla_loose_script_fqns`: every vanilla .java;
- `_vanilla_faction_ids`.
"""
from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from unittest import mock

from bridgeforge.scan import scan_content, scan_jarchecks
from tests.support import resolved_temp_dir

_CLASS = b"\xca\xfe\xba\xbe" + b"\x00" * 8


def _core(root: Path) -> Path:
    core = root / "starsector-core"
    (core / "data" / "world" / "factions").mkdir(parents=True)
    (core / "data" / "world" / "factions" / "hegemony.faction").write_text('{"id": "hegemony"}', encoding="utf-8")
    (core / "data" / "scripts").mkdir(parents=True)
    (core / "data" / "scripts" / "A.java").write_text("package data.scripts;\npublic class A {}\n", encoding="utf-8")
    with zipfile.ZipFile(core / "starfarer.api.jar", "w") as jar:
        jar.writestr("com/fs/starfarer/api/X.class", _CLASS)
    return core


class CoreCacheTests(unittest.TestCase):
    def test_the_api_jars_are_parsed_once_per_process(self) -> None:
        with resolved_temp_dir() as root:
            core = _core(root)
            with mock.patch.object(scan_jarchecks, "_parse_class_file", wraps=scan_jarchecks._parse_class_file) as parse:
                scan_jarchecks._vanilla_api_jar_class_info(core)
                scan_jarchecks._vanilla_api_jar_class_info(core)
        self.assertEqual(parse.call_count, 1)

    def test_a_changed_jar_is_parsed_again(self) -> None:
        with resolved_temp_dir() as root:
            core = _core(root)
            scan_jarchecks._vanilla_api_jar_class_info(core)
            with zipfile.ZipFile(core / "starfarer.api.jar", "a") as jar:
                jar.writestr("com/fs/starfarer/api/Y.class", _CLASS)
            with mock.patch.object(scan_jarchecks, "_parse_class_file", wraps=scan_jarchecks._parse_class_file) as parse:
                scan_jarchecks._vanilla_api_jar_class_info(core)
        self.assertEqual(parse.call_count, 2)

    def test_the_class_info_cannot_be_changed_by_a_caller(self) -> None:
        with resolved_temp_dir() as root:
            info = scan_jarchecks._vanilla_api_jar_class_info(_core(root))
        with self.assertRaises(TypeError):
            info["com.fs.starfarer.api.Z"] = None  # type: ignore[index]

    def test_loose_scripts_are_read_once(self) -> None:
        with resolved_temp_dir() as root:
            core = _core(root)
            first = scan_jarchecks._vanilla_loose_script_fqns(core)
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("read again")):
                second = scan_jarchecks._vanilla_loose_script_fqns(core)
        self.assertEqual(second, {"data.scripts.A"})
        self.assertEqual(first, second)
        self.assertIsInstance(second, frozenset)

    def test_faction_ids_are_read_once_and_each_caller_gets_its_own_set(self) -> None:
        with resolved_temp_dir() as root:
            core = _core(root)
            first = scan_content._vanilla_faction_ids(core)
            first.add("mod_faction")  # the rules check adds the mod's own factions to what it is given
            with mock.patch.object(scan_content, "_load_lenient_json_file", side_effect=AssertionError("read again")):
                second = scan_content._vanilla_faction_ids(core)
        self.assertEqual(second, {"hegemony"})


if __name__ == "__main__":
    unittest.main()
