"""Classes and content a declared dependency provides count as defined (SEEKER 0.6.6 and MagicLib, 2026-09-28)."""
import json
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod
from tests.save_fixtures import build_class_file, write_jar
from tests.support import resolved_temp_dir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class DependencyResolutionTests(unittest.TestCase):
    def test_dependency_jar_classes_and_hull_mods_resolve(self) -> None:
        with resolved_temp_dir() as root:
            providers = root / "rig" / "mods"
            lib = providers / "Lib"
            _write(lib / "mod_info.json", json.dumps({"id": "the_lib", "name": "The Lib", "jars": ["jars/lib.jar"]}))
            write_jar(lib / "jars" / "lib.jar", {"data/scripts/weapons/LibThruster.class": build_class_file("data/scripts/weapons/LibThruster")})
            _write(lib / "data" / "hullmods" / "hull_mods.csv", "name,id,tier\nLib Warning,lib_warning,0\n")
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "user", "dependencies": [{"id": "the_lib"}]}))
            _write(mod / "data" / "weapons" / "thruster.wpn", json.dumps({"id": "thruster", "everyFrameEffect": "data.scripts.weapons.LibThruster"}))
            _write(mod / "data" / "hulls" / "user_ship.ship", json.dumps({"hullId": "user_ship", "builtInMods": ["lib_warning"]}))
            core = root / "core"
            for relative, header in (("data/weapons/weapon_data.csv", "name,id\nV,v_gun\n"), ("data/hullmods/hull_mods.csv", "name,id\nV,v_mod\n"),
                                     ("data/hulls/wing_data.csv", "id,variant\nv_wing,v_wing_x\n")):
                _write(core / relative, header)
            _write(core / "data" / "hulls" / "v_hull.ship", json.dumps({"hullId": "v_hull"}))
            without = scan_mod(mod, vanilla_core=core).findings
            with_providers = scan_mod(mod, vanilla_core=core, provider_roots=[providers]).findings
        ids = ("data-class-reference-missing", "content-reference-unresolved")
        self.assertTrue(any(f.id == "data-class-reference-missing" for f in without))
        self.assertEqual([f.id for f in with_providers if f.id in ids], [])


if __name__ == "__main__":
    unittest.main()
