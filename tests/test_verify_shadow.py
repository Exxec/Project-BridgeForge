from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.verify_shadow import VerifyShadowError, script_class_name, verify_shadow
from tests.save_fixtures import build_class_file, write_jar, write_text
from tests.support import resolved_temp_dir


def _mod(root: Path) -> Path:
    mod = root / "Rebal"
    write_text(mod / "mod_info.json", '{"id":"rebal","jars":["jars/rebal.jar"]}')
    write_jar(mod / "jars" / "rebal.jar", {"data/scripts/Owned.class": build_class_file("data/scripts/Owned")})
    write_text(mod / "data/scripts/Owned.java", "package data.scripts;\npublic class Owned {}\n")
    write_text(mod / "data/hullmods/Armor.java", "// package data.fake;\npackage data.hullmods;\npublic class Armor {}\n")
    write_text(mod / "data/shipsystems/NoPackage.java", "public class NoPackage {}\n")
    return mod


def _core(root: Path) -> Path:
    core = root / "starsector-core"
    # E12: vanilla ships data/hullmods/Armor.java loose at the same path; no jar compiles it.
    write_text(core / "data/hullmods/Armor.java", "package data.hullmods;\npublic class Armor {}\n")
    write_jar(core / "starfarer.api.jar", {"com/fs/starfarer/api/Global.class": build_class_file("com/fs/starfarer/api/Global")})
    write_jar(core / "starfarer_obf.jar", {"data/shipsystems/NoPackage.class": build_class_file("data/shipsystems/NoPackage")})
    write_text(core / "broken.jar", "not a zip")
    return core


class VerifyShadowTests(unittest.TestCase):
    def test_class_names_come_from_the_package_line_or_the_mod_path(self):
        with resolved_temp_dir() as root:
            mod = _mod(root)
            self.assertEqual(script_class_name(mod / "data/hullmods/Armor.java"), ("data.hullmods.Armor", "package declaration"))
            name, derived = script_class_name(mod / "data/shipsystems/NoPackage.java")
            self.assertEqual(name, "data.shipsystems.NoPackage")
            self.assertTrue(derived.startswith("path below mod root"))
            write_text(root / "loose/Stray.java", "class Stray {}")
            self.assertEqual(script_class_name(root / "loose/Stray.java")[0], "Stray")

    def test_same_path_as_vanilla_is_not_shadowing(self):
        with resolved_temp_dir() as root:
            mod, core = _mod(root), _core(root)
            result = verify_shadow([mod / "data/hullmods/Armor.java"], [core])
        self.assertEqual(result["results"][0]["status"], "NOT_SHADOWED")
        self.assertEqual(len(result["unreadable_jars"]), 1)
        self.assertIn("broken.jar", result["unreadable_jars"][0])
        self.assertEqual(result["jars_checked"], 2)

    def test_names_the_jar_that_supplies_the_class(self):
        with resolved_temp_dir() as root:
            mod, core = _mod(root), _core(root)
            result = verify_shadow([mod / "data/scripts/Owned.java", mod / "data/shipsystems/NoPackage.java"], [mod, core])
        owned, no_package = result["results"]
        self.assertEqual(owned["status"], "SHADOWED")
        self.assertTrue(owned["supplied_by"][0].endswith("rebal.jar!data/scripts/Owned.class"))
        self.assertTrue(no_package["supplied_by"][0].endswith("starfarer_obf.jar!data/shipsystems/NoPackage.class"))

    def test_mod_folder_means_its_declared_jars_only(self):
        with resolved_temp_dir() as root:
            mod = _mod(root)
            write_jar(mod / "jars" / "undeclared.jar", {"data/hullmods/Armor.class": build_class_file("data/hullmods/Armor")})
            result = verify_shadow([mod / "data/hullmods/Armor.java"], [mod])
        self.assertEqual(result["results"][0]["status"], "NOT_SHADOWED")  # the game never loads an undeclared jar
        self.assertEqual(result["jars_checked"], 1)

    def test_errors_and_cli(self):
        with resolved_temp_dir() as root:
            mod, core = _mod(root), _core(root)
            with self.assertRaises(VerifyShadowError):
                verify_shadow([mod / "missing.java"], [core])
            with self.assertRaises(VerifyShadowError):
                verify_shadow([mod / "data/scripts/Owned.java"], [root / "nowhere"])
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["verify-shadow", str(mod / "data/hullmods/Armor.java"), "--against", str(core)]), 0)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["verify-shadow", str(mod / "x.java"), "--against", str(core)]), 2)
        self.assertIn("NOT_SHADOWED:", out.getvalue())
        self.assertIn("(class data.hullmods.Armor, from package declaration)", out.getvalue())
        self.assertIn("NOT checked:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
