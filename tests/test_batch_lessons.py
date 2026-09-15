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


class LibraryImportOnlyTests(unittest.TestCase):
    def test_an_import_the_jar_never_uses_is_not_a_dependency(self) -> None:
        # Bionic Alteration imports Nexerelin's StringHelper but never calls it; the jar has no exerelin/ ref.
        import zipfile

        from tests.test_personality_ids import _class_with_strings

        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory), jars=["jars/p.jar"])
            (mod / "src" / "demo").mkdir(parents=True)
            (mod / "src" / "demo" / "Plug.java").write_text("package demo;\nimport exerelin.utilities.StringHelper;\npublic class Plug {}\n", encoding="utf-8")
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "p.jar", "w") as archive:
                archive.writestr("demo/Plug.class", _class_with_strings("demo/Plug", ["hello"], []))
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(len(_ids(result, "library-import-unused-in-jar")), 1)
        self.assertEqual(_ids(result, "undeclared-library-dependency"), [])
        self.assertEqual(_ids(result, "source-library-dependency-undeclared"), [])


class ConsoleCommandOptionalTests(unittest.TestCase):
    def test_classes_registered_only_as_console_commands_are_optional(self) -> None:
        # Bionic Alteration: its Console Commands classes are listed in data/console/commands.csv.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "src" / "demo").mkdir(parents=True)
            (mod / "src" / "demo" / "Cheat.java").write_text("package demo;\nimport org.lazywizard.console.BaseCommand;\npublic class Cheat implements BaseCommand {}\n", encoding="utf-8")
            (mod / "data" / "console").mkdir(parents=True)
            (mod / "data" / "console" / "commands.csv").write_text("command,class,tags,syntax,help\ncheat,demo.Cheat,x,cheat,help\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(len(_ids(result, "console-command-optional")), 1)
        self.assertEqual(_ids(result, "external-mod-api-import"), [])

    def test_an_unregistered_class_still_needs_console_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "src" / "demo").mkdir(parents=True)
            (mod / "src" / "demo" / "Plugin.java").write_text("package demo;\nimport org.lazywizard.console.Console;\npublic class Plugin {}\n", encoding="utf-8")
            (mod / "data" / "console").mkdir(parents=True)
            (mod / "data" / "console" / "commands.csv").write_text("command,class,tags,syntax,help\ncheat,demo.Cheat,x,cheat,help\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(len(_ids(result, "external-mod-api-import")), 1)


class MagicLibAttributionTests(unittest.TestCase):
    def test_own_data_scripts_util_classes_are_not_magiclib(self) -> None:
        # AI-War ships data.scripts.util.AIW_StringHelper; only data.scripts.util.Magic* is MagicLib's legacy API.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "scripts" / "util").mkdir(parents=True)
            (mod / "data" / "scripts" / "util" / "AIW_StringHelper.java").write_text("package data.scripts.util;\npublic class AIW_StringHelper {}\n", encoding="utf-8")
            (mod / "data" / "scripts" / "Plugin.java").write_text("package data.scripts;\nimport data.scripts.util.AIW_StringHelper;\npublic class Plugin {}\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(result, "source-library-dependency-undeclared"), [])
        self.assertEqual(_ids(result, "external-mod-api-import"), [])
        self.assertFalse(any(item["library"] == "MagicLib" for item in result.library_usage))

    def test_a_magic_class_import_is_still_magiclib(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "data" / "scripts" / "Plugin.java").write_text("package data.scripts;\nimport data.scripts.util.MagicRender;\npublic class Plugin {}\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertTrue(any(item["library"] == "MagicLib" for item in result.library_usage))
        self.assertTrue(_ids(result, "external-mod-api-import"))


class SourceImportUnresolvedTests(unittest.TestCase):
    def test_another_mods_classes_are_flagged_and_own_classes_are_not(self) -> None:
        # FX Example imports FX Core's data.scripts.fx_Particle without declaring FX Core.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "scripts" / "plugins").mkdir(parents=True)
            (mod / "data" / "scripts" / "fx_ExampleStorage.java").write_text("package data.scripts;\npublic class fx_ExampleStorage {}\n", encoding="utf-8")
            (mod / "data" / "scripts" / "plugins" / "Thruster.java").write_text(
                "package data.scripts.plugins;\nimport data.scripts.fx_ExampleStorage;\nimport data.scripts.fx_Particle;\nimport data.scripts.util.MagicRender;\npublic class Thruster {}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "source-import-unresolved")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].evidence, ["data.scripts.fx_Particle"])  # own class and MagicLib's util package are fine

    def test_vanilla_loose_scripts_are_defined_classes_and_disabled_files_are_ignored(self) -> None:
        # Correction, 2026-09-14: RC8 still ships BaseSpawnPoint and corvus.Corvus as loose scripts in
        # starsector-core/data/scripts, so Cobalt Arms & co. importing them is neither a removed-class
        # use nor another mod's class. Zorg18 keeps old imports in disabled_files, which never load.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "scripts" / "world").mkdir(parents=True)
            (mod / "data" / "scripts" / "world" / "Spawn.java").write_text("package data.scripts.world;\nimport data.scripts.world.BaseSpawnPoint;\nimport data.scripts.world.corvus.Corvus;\npublic class Spawn extends BaseSpawnPoint {}\n", encoding="utf-8")
            (mod / "disabled_files").mkdir()
            (mod / "disabled_files" / "Old.java").write_text("package data.scripts.world;\nimport data.scripts.Gone;\npublic class Old {}\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(result, "legacy-vanilla-class-import"), [])
        self.assertEqual(_ids(result, "source-import-unresolved"), [])

    def test_vanilla_loose_hullmod_import_is_not_another_mods_class(self) -> None:
        # Adjusted Sector imports data.hullmods.HeavyArmor, one of RC8's 116 loose vanilla scripts.
        import bridgeforge.scanner as scanner_module

        self.assertIn("data.hullmods.HeavyArmor", scanner_module.VANILLA_LOOSE_SCRIPT_CLASSES)
        self.assertEqual(len(scanner_module.VANILLA_LOOSE_SCRIPT_CLASSES), 116)
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "hullmods").mkdir(parents=True)
            (mod / "data" / "hullmods" / "Tough.java").write_text("package data.hullmods;\nimport data.hullmods.HeavyArmor;\npublic class Tough extends HeavyArmor {}\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(result, "source-import-unresolved"), [])

    def test_removed_sector_create_fleet_call_is_manual_but_fleet_factory_is_not(self) -> None:
        # Gekelonians' spawn point: getSector().createFleet("gekelonian", type); RC8's SectorAPI has no
        # createFleet (javap). FleetFactoryV3.createFleet(params) is the current API.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            world = mod / "data" / "scripts" / "world"
            world.mkdir(parents=True)
            (world / "Spawn.java").write_text("package data.scripts.world;\npublic class Spawn extends BaseSpawnPoint {\n  Object f() {\n    // getSector().createFleet(\"x\", \"y\") in a comment\n    return getSector().createFleet(\"gekelonian\", type);\n  }\n}\n", encoding="utf-8")
            (world / "Good.java").write_text("package data.scripts.world;\nclass Good { Object f() { return FleetFactoryV3.createFleet(params); } }\n", encoding="utf-8")
            (mod / "disabled_files").mkdir()
            (mod / "disabled_files" / "Old.java").write_text("class Old { Object f() { return Global.getSector().createFleet(\"a\", \"b\"); } }\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "removed-api-call")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "MANUAL")
        self.assertEqual(hits[0].evidence[:2], ["SectorAPI.createFleet(factionId, fleetTypeId): 1 call(s)", "data/scripts/world/Spawn.java:5"])

    def test_global_getsectorapi_create_fleet_receiver_is_also_manual(self) -> None:
        # E6, 2026-09-14: javap confirms Global.getSectorAPI() also returns SectorAPI (same as
        # Global.getSector()), so a spawn point written against that receiver needs the same finding.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            world = mod / "data" / "scripts" / "world"
            world.mkdir(parents=True)
            (world / "Spawn.java").write_text(
                "package data.scripts.world;\npublic class Spawn extends BaseSpawnPoint {\n  Object f() {\n    return Global.getSectorAPI().createFleet(\"CAPSCO\", type);\n  }\n}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "removed-api-call")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].evidence[:2], ["SectorAPI.createFleet(factionId, fleetTypeId): 1 call(s)", "data/scripts/world/Spawn.java:4"])

    def test_sector_add_message_call_is_manual_but_campaignui_addmessage_is_not(self) -> None:
        # E6, 2026-09-14: javap confirms RC8's SectorAPI has no addMessage; CampaignUIAPI (from
        # SectorAPI.getCampaignUI()) does. Real case: CAPSCOConvoySpawnPoint.java calls
        # Global.getSectorAPI().addMessage(String) to post a comm message.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            world = mod / "data" / "scripts" / "world"
            world.mkdir(parents=True)
            (world / "Convoy.java").write_text(
                "package data.scripts.world;\npublic class Convoy extends BaseSpawnPoint {\n"
                "  void arrived() {\n"
                "    // Global.getSectorAPI().addMessage(\"x\") in a comment\n"
                "    Global.getSectorAPI().addMessage(\"A supply convoy is under way\");\n"
                "  }\n"
                "  void good() {\n"
                "    Global.getSectorAPI().getCampaignUI().addMessage(\"fine\");\n"
                "  }\n"
                "}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "removed-api-call")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "MANUAL")
        self.assertEqual(hits[0].evidence[:2], ["SectorAPI.addMessage(String): 1 call(s)", "data/scripts/world/Convoy.java:5"])

    def test_cargo_crewxplevel_reference_is_manual_but_addcrew_int_is_not(self) -> None:
        # E6, 2026-09-14: jar-wide javap search confirms RC8's CargoAPI has no nested CrewXPLevel enum any
        # more (only plain addCrew(int)). Real case: BataviaConvoySpawnPoint.java imports and uses it.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            world = mod / "data" / "scripts" / "world"
            world.mkdir(parents=True)
            (world / "Convoy.java").write_text(
                "package data.scripts.world;\n"
                "import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;\n"
                "public class Convoy extends BaseSpawnPoint {\n"
                "  void crew(CargoAPI cargo) {\n"
                "    cargo.addCrew(CrewXPLevel.VETERAN, 5);\n"
                "  }\n"
                "  void fine(CargoAPI cargo) {\n"
                "    cargo.addCrew(5);\n"
                "  }\n"
                "}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "removed-api-call")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "MANUAL")
        # 2 call(s): the now-unresolvable import line, plus the addCrew(CrewXPLevel.X, ...) call - the
        # fine() method's addCrew(5) (already the RC8 shape) doesn't match at all.
        self.assertEqual(
            hits[0].evidence[:3],
            ["CargoAPI.CrewXPLevel: 2 call(s)", "data/scripts/world/Convoy.java:2", "data/scripts/world/Convoy.java:5"],
        )

    def test_seven_argument_addplanet_is_manual_but_rc8_eight_argument_form_is_not(self) -> None:
        # javap of RC8's starfarer.api.jar (2026-09-15): LocationAPI.addPlanet is id-first, 8 arguments;
        # the removed 0.6 form took 7, the location itself as the receiver.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            world = mod / "data" / "scripts" / "world"
            world.mkdir(parents=True)
            (world / "Gen.java").write_text(
                "package data.scripts.world;\n"
                "public class Gen implements SectorGeneratorPlugin {\n"
                "  public void generate(SectorAPI sector) {\n"
                '    SectorEntityToken old = system.addPlanet(lot, "Anchor", "lava", 0, 0, 1, 1);\n'
                '    PlanetAPI rc8 = system.addPlanet("asharu", star, "Asharu", "desert", 55, 150, 2800, 100);\n'
                "  }\n}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "removed-api-call")
        matching = [h for h in hits if h.evidence[0].startswith("LocationAPI.addPlanet")]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].classification, "MANUAL")
        self.assertEqual(matching[0].evidence[:2], ["LocationAPI.addPlanet(focus, name, type, angle, radius, orbitRadius, orbitDays): 1 call(s)", "data/scripts/world/Gen.java:4"])

    def test_addorbitalstation_has_no_rc8_equivalent_at_all_and_is_manual(self) -> None:
        # javap of RC8's starfarer.api.jar (2026-09-15): LocationAPI/StarSystemAPI have no addOrbitalStation
        # method at all, so unlike addPlanet there is no RC8 form to avoid conflating with.
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            world = mod / "data" / "scripts" / "world"
            world.mkdir(parents=True)
            (world / "Gen.java").write_text(
                "package data.scripts.world;\n"
                "public class Gen implements SectorGeneratorPlugin {\n"
                "  public void generate(SectorAPI sector) {\n"
                '    SectorEntityToken s = system.addOrbitalStation(anchor, 45, 13000, 365, "Depot", "faction");\n'
                "  }\n}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "removed-api-call")
        matching = [h for h in hits if h.evidence[0].startswith("LocationAPI.addOrbitalStation")]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].classification, "MANUAL")
        self.assertEqual(matching[0].evidence[:2], ["LocationAPI.addOrbitalStation(focus, angle, orbitRadius, orbitDays, name, factionId): 1 call(s)", "data/scripts/world/Gen.java:4"])

    def test_a_listed_removed_class_is_found_by_import_or_from_its_own_package(self) -> None:
        # The machinery stays for evidenced entries: an import-only check would miss a same-package use.
        from unittest import mock

        import bridgeforge.scanner as scanner_module

        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(scanner_module.LEGACY_VANILLA_CLASSES, {"data.scripts.world.GoneSpawner": "test entry, removed"}):
            mod = _mod(Path(directory))
            world = mod / "data" / "scripts" / "world"
            world.mkdir(parents=True)
            (world / "A.java").write_text("package data.scripts.world;\npublic class A extends GoneSpawner {}\n", encoding="utf-8")
            (mod / "data" / "scripts" / "B.java").write_text("package data.scripts;\nimport data.scripts.world.GoneSpawner;\npublic class B {}\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        legacy = _ids(result, "legacy-vanilla-class-import")
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0].classification, "MANUAL")
        self.assertIn("(2 file(s):", legacy[0].evidence[0])

    def test_a_mod_shipping_its_own_copy_of_a_listed_removed_class_is_not_flagged(self) -> None:
        # Vacuum's earlier copy shipped its own data.scripts.world.BaseSpawnPoint.
        from unittest import mock

        import bridgeforge.scanner as scanner_module

        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(scanner_module.LEGACY_VANILLA_CLASSES, {"data.scripts.world.GoneSpawner": "test entry, removed"}):
            mod = _mod(Path(directory))
            world = mod / "data" / "scripts" / "world"
            world.mkdir(parents=True)
            (world / "GoneSpawner.java").write_text("package data.scripts.world;\npublic abstract class GoneSpawner {}\n", encoding="utf-8")
            (world / "Spawn.java").write_text("package data.scripts.world;\npublic class Spawn extends GoneSpawner {}\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(result, "legacy-vanilla-class-import"), [])


class UnresolvedContentTests(unittest.TestCase):
    def _core(self, root: Path) -> Path:
        core = root / "core"
        (core / "data" / "hullmods").mkdir(parents=True)
        (core / "data" / "hullmods" / "hull_mods.csv").write_text("name,id,cost_frigate\nArmor,heavyarmor,5\n", encoding="utf-8")
        (core / "data" / "hulls").mkdir(parents=True)
        (core / "data" / "hulls" / "wing_data.csv").write_text("id,variant\ntalon_wing,talon_Interceptor\n", encoding="utf-8")
        (core / "data" / "hulls" / "lasher.ship").write_text(json.dumps({"hullId": "lasher", "hullSize": "FRIGATE"}), encoding="utf-8")
        (core / "data" / "weapons").mkdir(parents=True)
        (core / "data" / "weapons" / "weapon_data.csv").write_text("name,id,OPs\nLight MG,lightmg,3\n", encoding="utf-8")
        return core

    def _scan(self, dependencies: list):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _mod(root, dependencies=dependencies)
            (mod / "data" / "variants").mkdir(parents=True)
            (mod / "data" / "variants" / "x.variant").write_text(json.dumps({"variantId": "x", "hullId": "lasher", "hullMods": ["heavyarmor", "vayra_red_army"], "wings": ["talon_wing", "vayra_yak_wing"], "weaponGroups": [{"weapons": {"WS1": "lightmg", "WS2": "vayra_kashtan"}}]}), encoding="utf-8")
            return _ids(scan_mod(mod, TargetProfile(), self._core(root)), "content-reference-unresolved")

    def test_foreign_ids_are_reported_with_their_prefix(self) -> None:
        # Communist Clouds: a Vayra's Sector add-on that never declared Vayra's Sector.
        hits = self._scan([])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "MANUAL")
        self.assertEqual(hits[0].evidence[0], "common prefix: vayra_ (3 ids)")
        self.assertIn("hullmod:vayra_red_army (1 file(s))", hits[0].evidence)
        self.assertIn("wing:vayra_yak_wing (1 file(s))", hits[0].evidence)
        self.assertIn("weapon:vayra_kashtan (1 file(s))", hits[0].evidence)

    def test_a_declared_dependency_may_provide_them(self) -> None:
        self.assertEqual(self._scan([{"id": "vayrasector"}])[0].classification, "REVIEW")


class CarrierBaysProposalTests(unittest.TestCase):
    def test_pre08_hangar_and_launch_bays_give_a_proposal_and_descriptions_do_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _mod(root)
            hulls = mod / "data" / "hulls"
            hulls.mkdir(parents=True)
            (hulls / "ship_data.csv").write_text(
                "name,id,designation,system id,hangar,hints\n"
                "Big,big,Carrier,,6,\nNoSlots,noslots,Cruiser,,4,\nDrone,droney,Cruiser,dronesys,3,\nPlain,plain,Heavy Carrier,,,\nNothing,nothing,Frigate,,,\n",
                encoding="utf-8",
            )
            bay = {"type": "LAUNCH_BAY", "id": "LB"}
            for hull, slots in (("big", 2), ("noslots", 0), ("droney", 1), ("plain", 1), ("nothing", 0)):
                (hulls / f"{hull}.ship").write_text(json.dumps({"hullId": hull, "hullSize": "CRUISER", "weaponSlots": [bay] * slots}), encoding="utf-8")
            (mod / "data" / "shipsystems").mkdir(parents=True)
            (mod / "data" / "shipsystems" / "dronesys.system").write_text(json.dumps({"id": "dronesys", "type": "DRONE_LAUNCHER"}), encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        evidence = _ids(result, "carrier-bays-proposal")[0].evidence
        self.assertEqual(evidence[0], "big: 2 bay(s) [hangar:6, launch-bays:2]")
        self.assertEqual(evidence[1], "noslots: choose a number (no launch-bay slots) [hangar:4]")
        self.assertIn("droney: 1 bay(s) [hangar:3, launch-bays:1, system:DRONE_LAUNCHER (slots may be for drones)]", evidence)
        self.assertIn("plain: hint only (launch-bays:1, CARRIER hint/designation)", evidence)
        self.assertFalse([item for item in evidence if item.startswith("nothing")])


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
