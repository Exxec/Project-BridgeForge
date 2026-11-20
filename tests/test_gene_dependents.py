"""94.G2 slice 9: the files that still name what a gene provides, graded, with an evidenced load condition."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from bridgeforge.genome.dependents import _provider_paths, graded, literal_matches, load_condition
from bridgeforge.genome.proof import classify_subtraction
from tests.support import resolved_temp_dir, write_text as _write


def _javac() -> str | None:
    return shutil.which("javac")


def _core(root: Path) -> Path:
    core = root / "core"
    _write(core / "data" / "world" / "factions" / "default_ship_roles.json", "{}")
    _write(core / "data" / "variants" / "wolf" / "wolf_Assault.variant", "{}")  # the core nests variants
    _write(core / "data" / "config" / "settings.json", "{}")  # and nests nothing under data/config
    _write(core / "data" / "missions" / "ambush" / "MissionDefinition.java", "")
    return core


class LiteralTests(unittest.TestCase):
    def test_a_path_matches_its_literal_a_template_or_a_specific_folder(self) -> None:
        self.assertTrue(literal_matches("data/config/modFiles/magicBounty_data.json", "data/config/modFiles/magicBounty_data.json"))
        # Nexerelin's NexFactionConfig: javac's concatenation recipe leaves \x01 for the faction id.
        self.assertTrue(literal_matches("data/config/exerelinFactionConfig/\x01.json", "data/config/exerelinFactionConfig/x.json"))
        self.assertFalse(literal_matches("data/config/exerelinFactionConfig/\x01.json", "data/config/exerelinFactionConfig/a/x.json"))
        self.assertTrue(literal_matches("data/config/modFiles/magicBounty_variants/", "data/config/modFiles/magicBounty_variants/v.variant"))

    def test_a_bare_folder_literal_names_nothing(self) -> None:
        # AshLib's `data/` and MagicLib's `data/config/` matched every config file before (2026-11-20).
        self.assertFalse(literal_matches("data/", "data/config/exerelinFactionConfig/x.json"))
        self.assertFalse(literal_matches("data/config/", "data/config/x.json"))

    def test_a_template_needs_a_fixed_folder_and_a_fixed_part_of_the_name(self) -> None:
        # `"data/config/" + name` and a variable folder name every file there (review 2026-11-20).
        self.assertFalse(literal_matches("data/config/\x01", "data/config/x.json"))
        self.assertFalse(literal_matches("data/x/\x01/\x01.csv", "data/x/a/b.csv"))
        self.assertFalse(literal_matches("data/\x01.json", "data/x.json"))


class LoadConditionTests(unittest.TestCase):
    def test_conditions_come_from_the_core_the_mission_path_and_provider_jars(self) -> None:
        with resolved_temp_dir() as root:
            core = _core(root)
            self.assertEqual(load_condition("data/world/factions/default_ship_roles.json", core, []), "always")
            self.assertEqual(load_condition("data/variants/new_folder/x_Std.variant", core, []), "always")  # a scanned spec folder
            self.assertEqual(load_condition("data/hulls/x.ship", core, []), "always")
            self.assertEqual(load_condition("data/config/someMod/thing.json", core, []), "unknown")
            # The core's data/config holds settings.json, but nothing reads a mod's own data/config/x.json by that (review).
            self.assertEqual(load_condition("data/config/sa_custom.json", core, []), "unknown")
            self.assertEqual(load_condition("data/missions/testbed/MissionDefinition.java", core, []), "on mission start")
            self.assertEqual(load_condition("src/a/B.java", core, []), "unknown")

    @unittest.skipUnless(_javac(), "needs javac")
    def test_a_provider_jar_naming_the_path_makes_it_loaded_with_that_mod(self) -> None:
        with resolved_temp_dir() as root:
            core, mods = _core(root), root / "mods"
            lib = mods / "SomeLib"
            _write(lib / "mod_info.json", json.dumps({"id": "some_lib", "jars": ["jars/lib.jar"]}))
            _write(root / "src" / "lib" / "Loader.java",
                   'package lib;\npublic class Loader { public static final String P = "data/config/someLib/thing.json";'
                   ' String p() { return P; } }\n')
            subprocess.run([_javac(), "-encoding", "UTF-8", "-proc:none", "-d", str(root / "classes"),
                            str(root / "src" / "lib" / "Loader.java")], check=True, capture_output=True)
            (lib / "jars").mkdir()
            with zipfile.ZipFile(lib / "jars" / "lib.jar", "w") as jar:
                jar.write(root / "classes" / "lib" / "Loader.class", "lib/Loader.class")
            _provider_paths.cache_clear()
            self.assertEqual(load_condition("data/config/someLib/thing.json", core, [mods]), "with some_lib")
            self.assertEqual(load_condition("data/config/otherLib/thing.json", core, [mods]), "unknown")


class GradedTests(unittest.TestCase):
    def test_suspects_become_graded_dependents_by_whole_token_and_not_located_goes(self) -> None:
        with resolved_temp_dir() as root:
            core, mod = _core(root), root / "mod"
            _write(mod / "data" / "world" / "factions" / "default_ship_roles.json", '{"x_ship_Royal": 10}')
            _write(mod / "data" / "strings" / "notes.txt", "x_ship is a word here")
            gene = {"provides": ["variant:x_ship_Royal", "hull:x_ship"], "unknowns": {"suspects": [
                {"path": "data/world/factions/default_ship_roles.json", "mentions": ["x_ship_Royal", "x_ship"]},
                {"path": "data/strings/notes.txt", "mentions": ["x_ship"]}]}}
            rows = graded(gene, [{"from": "(not located)", "to": "variant:x_ship_Royal"}], core, [], mod)
        self.assertEqual(rows, [
            {"from": "data/strings/notes.txt", "to": "hull:x_ship", "grade": "mention", "loaded": "unknown"},
            {"from": "data/world/factions/default_ship_roles.json", "to": "variant:x_ship_Royal", "grade": "reference",
             "loaded": "always"}])  # `x_ship` inside `x_ship_Royal` is not a mention of the hull; (not located) is gone

    def test_a_mere_mention_does_not_hide_a_reference_nobody_located(self) -> None:
        with resolved_temp_dir() as root:
            core, mod = _core(root), root / "mod"
            _write(mod / "data" / "strings" / "notes.txt", "x_Royal is described here")
            gene = {"provides": ["variant:x_Royal"], "unknowns": {"suspects": [{"path": "data/strings/notes.txt", "mentions": ["x_Royal"]}]}}
            rows = graded(gene, [{"from": "(not located)", "to": "variant:x_Royal"}], core, [], mod)
        self.assertEqual([r["from"] for r in rows], ["(not located)", "data/strings/notes.txt"])


def _scan(*findings):
    return SimpleNamespace(findings=[SimpleNamespace(id=i, file=f, evidence=list(e), explanation="") for i, f, e in findings])


class FindingContextTests(unittest.TestCase):
    def test_a_findings_other_lines_are_context_of_its_dependent(self) -> None:
        gene = {"kind": "variant", "provides": ["variant:x_Royal"], "members": [], "registrations": []}
        after = _scan(("mission-variant-missing", "data/missions/t/MissionDefinition.java",
                       ["x_Royal", "mission:data/missions/t/MissionDefinition.java", "not inside an isModEnabled block"]))
        result = classify_subtraction(_scan(), after, gene, [])
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual([c["reference"] for c in result["context"]],
                         ["mission:data/missions/t/MissionDefinition.java", "not inside an isModEnabled block"])
        # An id-like line of the same finding is not absolved by the dependent line beside it (review 2026-11-20).
        broad = _scan(("mission-variant-missing", "data/missions/t/MissionDefinition.java", ["x_Royal", "variant:y_Other"]))
        self.assertEqual(classify_subtraction(_scan(), broad, gene, [])["verdict"], "FAIL")
        alone = _scan(("other-finding", "a.json", ["not inside an isModEnabled block"]))
        self.assertEqual(classify_subtraction(_scan(), alone, gene, [])["verdict"], "FAIL")  # without a dependent it is unexplained


if __name__ == "__main__":
    unittest.main()
