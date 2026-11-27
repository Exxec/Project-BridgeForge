"""Classes and content a declared dependency provides count as defined (SEEKER 0.6.6 and MagicLib, 2026-09-28)."""
import json
import unittest

from bridgeforge.scan.scanner import scan_mod
from tests.save_fixtures import build_class_file, write_jar
from tests.support import resolved_temp_dir
from tests.support import write_text as _write


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

    def test_a_rule_command_in_a_dependencys_jar_resolves_through_rule_command_packages(self) -> None:
        # Wide Horizons Content 1.5.1b (98.9): rules.csv calls WHStartBarEventDialog, a class in its dependency Wide Horizons
        # Core's jar under org.widehorizons.rulecmd, which Content's settings.json lists in ruleCommandPackages. The game
        # looks a command up as <package>.<command> for every listed package (RC9 campaign.rules.A.getCommandClass).
        vanilla_extra = "com.fs.starfarer.api.impl.campaign.rulecmd.salvage"

        def missing(listed_by_mod: list[str], listed_by_lib: list[str], package: str = "org/lib/rulecmd") -> list[str]:
            with resolved_temp_dir() as root:
                providers = root / "rig" / "mods"
                lib = providers / "Lib"
                _write(lib / "mod_info.json", json.dumps({"id": "the_lib", "name": "The Lib", "jars": ["jars/lib.jar"]}))
                write_jar(lib / "jars" / "lib.jar", {f"{package}/LibCmd.class": build_class_file(f"{package}/LibCmd"),
                                                     f"{package}/LibEffect.class": build_class_file(f"{package}/LibEffect")})
                _write(lib / "data" / "config" / "settings.json", json.dumps({"ruleCommandPackages": listed_by_lib}))
                mod = root / "mod"
                _write(mod / "mod_info.json", json.dumps({"id": "user", "dependencies": [{"id": "the_lib"}]}))
                _write(mod / "data" / "config" / "settings.json", json.dumps({"ruleCommandPackages": listed_by_mod}))
                _write(mod / "data" / "campaign" / "rules.csv", "id,trigger,conditions,script,text,options,notes\n"
                                                                "r1,OpenInteractionDialog,!LibCmd check,LibCmd go,,,\n")
                # Not a rule command: a full class name, which the package lookup must not resolve by its simple name.
                _write(mod / "data" / "weapons" / "gun.wpn", json.dumps({"id": "gun", "everyFrameEffect": "data.scripts.LibEffect"}))
                core = root / "core"
                _write(core / "data" / "config" / "settings.json",
                       json.dumps({"ruleCommandPackages": ["com.fs.starfarer.api.impl.campaign.rulecmd", vanilla_extra]}))
                found = scan_mod(mod, vanilla_core=core, provider_roots=[providers]).findings
            return sorted({e for f in found if f.id == "data-class-reference-missing" for e in f.evidence if e.startswith("class:")})

        effect = "class:data.scripts.LibEffect"
        self.assertEqual(missing(["org.lib.rulecmd"], []), [effect])  # listed by the mod itself
        self.assertEqual(missing([], ["org.lib.rulecmd"]), [effect])  # listed by the dependency: lists merge
        self.assertEqual(missing([], [], vanilla_extra.replace(".", "/")), [effect])  # listed by vanilla's settings only
        # Not listed anywhere, or listed with a space the game keeps: the game cannot find it, so it stays reported.
        command = "class:com.fs.starfarer.api.impl.campaign.rulecmd.LibCmd"
        self.assertEqual(missing(["org.other.rulecmd"], []), [command, effect])
        self.assertEqual(missing([" org.lib.rulecmd"], []), [command, effect])

    def test_report_draft_resolves_against_providers(self) -> None:
        # SEEKER 0.6.6 (2026-09-28): revive's scan resolved MagicLib weapon effects, but the report draft
        # rescanned without the rig's mods and came out BLOCKED on data-class-reference-missing.
        from bridgeforge.revival_report_draft import draft_revival_report

        with resolved_temp_dir() as root:
            providers = root / "rig" / "mods"
            lib = providers / "Lib"
            _write(lib / "mod_info.json", json.dumps({"id": "the_lib", "name": "The Lib", "jars": ["jars/lib.jar"]}))
            write_jar(lib / "jars" / "lib.jar", {"data/scripts/weapons/LibThruster.class": build_class_file("data/scripts/weapons/LibThruster")})
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "user", "dependencies": [{"id": "the_lib"}]}))
            _write(mod / "data" / "weapons" / "thruster.wpn", json.dumps({"id": "thruster", "everyFrameEffect": "data.scripts.weapons.LibThruster"}))
            without = draft_revival_report(mod)
            with_providers = draft_revival_report(mod, provider_roots=[providers])

        def blocking(draft):
            return [item for item in draft.get("blocking") or [] if "data-class-reference-missing" in str(item)]
        self.assertTrue(blocking(without))
        self.assertEqual(blocking(with_providers), [])


if __name__ == "__main__":
    unittest.main()
