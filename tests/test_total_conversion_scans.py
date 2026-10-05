"""Checks added from Ironclads' live-test crashes (GRP10L, GRP10Q, 2026-10-05)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


MOD_INFO = '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8"}'


class SkillEffectScriptTests(unittest.TestCase):
    def test_skill_naming_a_missing_effect_class_is_flagged(self) -> None:
        # Ironclads' ordnance_expert.skill named data.characters.skills.scripts.OrdnanceExpertEffect1, a 0.7.2 loose script
        # RC8 no longer has: Fatal 'Error loading [...]' at startup (GRP10L-20261005)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", MOD_INFO)
            _write(root / "data" / "characters" / "skills" / "ordnance_expert.skill",
                   '{"id":"ordnance_expert","effectGroups":[{"effects":[{"script":"data.characters.skills.scripts.OrdnanceExpertEffect1"}]}]}')
            hits = _findings(scan_mod(root), "data-class-reference-missing")
        self.assertEqual(len(hits), 1)
        self.assertIn("class:data.characters.skills.scripts.OrdnanceExpertEffect1", hits[0].evidence)
        self.assertIn("field:skill-effect-script", hits[0].evidence)

    def test_skill_effect_resolves_against_a_loose_script_in_the_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", MOD_INFO)
            _write(root / "data" / "characters" / "skills" / "ordnance_expert.skill",
                   '{"id":"ordnance_expert","effectGroups":[{"effects":[{"script":"data.characters.skills.scripts.OrdnanceExpertEffect1"}]}]}')
            _write(root / "data" / "characters" / "skills" / "scripts" / "OrdnanceExpertEffect1.java",
                   "package data.characters.skills.scripts;\npublic class OrdnanceExpertEffect1 {}\n")
            hits = _findings(scan_mod(root), "data-class-reference-missing")
        self.assertEqual(hits, [])


class StarTypeUndefinedTests(unittest.TestCase):
    def _fixture(self, directory: str, mod_planets: str | None = None) -> tuple[Path, Path]:
        base = Path(directory)
        mod, core = base / "mod", base / "core"
        _write(mod / "mod_info.json", MOD_INFO)
        _write(mod / "data" / "scripts" / "Gen.java",
               'public class Gen { void run(Object s) { s.initStar("x", "star_red", 300f, 600f); s.initStar("y", "star_white", 1f, 2f); } }\n')
        _write(core / "data" / "config" / "planets.json", '{"star_white":{"isStar":true},"star_red_dwarf":{"isStar":true}}')
        if mod_planets is not None:
            _write(mod / "data" / "config" / "planets.json", mod_planets)
        return mod, core

    def test_a_star_type_neither_mod_nor_rc8_defines_is_flagged(self) -> None:
        # Ironclads' SystemComposer asked for 0.7's star_red; RC8 has star_red_dwarf: NPE 'PlanetSpec.getPlanetType()' (GRP10Q)
        with tempfile.TemporaryDirectory() as directory:
            mod, core = self._fixture(directory)
            hits = _findings(scan_mod(mod, vanilla_core=core), "star-type-undefined")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "REVIEW")
        self.assertIn("type:star_red", hits[0].evidence)
        self.assertNotIn("type:star_white", hits[0].evidence)

    def test_a_star_the_mod_defines_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = self._fixture(directory, mod_planets='{"star_red":{"isStar":true}}')
            hits = _findings(scan_mod(mod, vanilla_core=core), "star-type-undefined")
        self.assertEqual(hits, [])

    def test_nothing_is_claimed_without_vanilla_core(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, _core = self._fixture(directory)
            hits = _findings(scan_mod(mod), "star-type-undefined")
        self.assertEqual(hits, [])


class LifecyclePluginTests(unittest.TestCase):
    def _mod(self, directory: str, *, settings: str | None = None, replaces: bool = True) -> Path:
        mod = Path(directory) / "mod"
        replace = '"replace":["data/hulls/ship_data.csv"],' if replaces else ""
        _write(mod / "mod_info.json", '{"id":"iron-clads","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8",%s}' % replace)
        if settings is not None:
            _write(mod / "data" / "config" / "settings.json", settings)
        return mod

    def test_a_total_conversion_without_a_lifecycle_plugin_is_flagged_and_fixed(self) -> None:
        # Ironclads: vanilla black site, then Nameless Rock, built fleets from removed hulls (GRP10P, GRP10T-20261005)
        from bridgeforge.fixers import apply_fix, compute_fix
        from bridgeforge.scanner import _load_lenient_json_file

        check = "conversion-vanilla-lifecycle-plugin"
        with tempfile.TemporaryDirectory() as directory:
            mod = self._mod(directory, settings='{\n\t"plugins":{\n\t\t"newGameSectorProcGen":"data.scripts.X",\n\t},\n}\n')
            found = _findings(scan_mod(mod), check)
            apply_fix(compute_fix(mod, check, {}))
            settings = _load_lenient_json_file(mod / "data" / "config" / "settings.json")
            source = (mod / "data" / "scripts" / "plugins" / "IronCladsCoreLifecyclePlugin.java").read_text(encoding="utf-8")
            after = _findings(scan_mod(mod), check)
        self.assertEqual(len(found), 1)
        self.assertEqual(settings["plugins"]["coreLifecyclePlugin"], "data.scripts.plugins.IronCladsCoreLifecyclePlugin")
        self.assertEqual(settings["plugins"]["newGameSectorProcGen"], "data.scripts.X")
        self.assertIn("public class IronCladsCoreLifecyclePlugin extends CoreLifecyclePluginImpl", source)
        self.assertIn("public void onGameLoad(boolean newGame)", source)
        self.assertNotIn("<", source.split("*/", 1)[1].replace("<=", ""), "Janino 2.7.8 has no generics")
        self.assertEqual(after, [])

    def test_the_fix_creates_settings_json_when_the_mod_has_none(self) -> None:
        from bridgeforge.fixers import apply_fix, compute_fix
        from bridgeforge.scanner import _load_lenient_json_file

        with tempfile.TemporaryDirectory() as directory:
            mod = self._mod(directory)
            apply_fix(compute_fix(mod, "conversion-vanilla-lifecycle-plugin", {}))
            settings = _load_lenient_json_file(mod / "data" / "config" / "settings.json")
        self.assertEqual(settings["plugins"]["coreLifecyclePlugin"], "data.scripts.plugins.IronCladsCoreLifecyclePlugin")

    def test_a_mod_that_keeps_vanilla_hulls_or_sets_a_plugin_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            keeps = self._mod(directory, replaces=False)
            sets = self._mod(directory + "/b", settings='{"plugins":{"coreLifecyclePlugin":"data.scripts.Mine"}}')
            found = _findings(scan_mod(keeps), "conversion-vanilla-lifecycle-plugin") + _findings(scan_mod(sets), "conversion-vanilla-lifecycle-plugin")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
