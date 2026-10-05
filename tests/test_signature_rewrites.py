"""rc8-signature-changed (ROADMAP 41; Ironclads, javap 2026-10-04): old-form calls with an exact RC8 equivalent."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.fixers import apply_fix, compute_fix
from bridgeforge.scanner import scan_mod

OLD = ('class G {\n  void g() {\n'
       '    Global.getSector().getEconomy().addMarket(market);\n'
       '    Misc.addNebulaFromPNG("a.png", 0, 0, hyper, "terrain", "deep", 4, 4, Terrain.HYPERSPACE);\n'
       '    system.addTerrain("nebula", new TileParams("  x, y  ", 6, 6, "terrain", "nebula", 4, 4));\n'
       '    this.market.addCondition("event, bounty", true, this);\n'
       '    m.addCondition("x"); m.addCondition("y", data); econ.addMarket(m, true); // addMarket(m)\n'
       '  }\n}\n')


class SignatureRewriteTests(unittest.TestCase):
    def test_check_flags_each_old_form_and_the_fixer_writes_rc8s(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            path = mod / "data" / "scripts" / "G.java"
            path.write_text(OLD, encoding="utf-8")
            calls = sorted(f.evidence[1] for f in scan_mod(mod).findings if f.id == "rc8-signature-changed")
            apply_fix(compute_fix(mod, "rc8-signature-changed"))
            text = path.read_text(encoding="utf-8")
            after = [f for f in scan_mod(mod).findings if f.id == "rc8-signature-changed"]
        self.assertEqual(calls, ["call:TileParams", "call:addCondition", "call:addMarket", "call:addNebulaFromPNG"])
        self.assertIn("addMarket(market, true);", text)
        self.assertIn("Terrain.HYPERSPACE, null);", text)
        self.assertIn('"nebula", 4, 4, null));', text)  # a comma inside the tile string is not an argument
        self.assertIn('addCondition("event, bounty", this);', text)  # comma in the id string kept
        self.assertIn('m.addCondition("y", data); econ.addMarket(m, true); // addMarket(m)', text)  # RC8 forms kept
        self.assertEqual(after, [])


if __name__ == "__main__":
    unittest.main()


class ReplaceDropsRc8EntriesTests(unittest.TestCase):
    def test_a_replaced_csv_missing_rc8_rows_is_flagged(self) -> None:
        # Ironclads (2026-10-05) replaced hull_mods.csv with a 0.7 copy lacking 92 of RC8's hull mods.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core, mod = root / "core", root / "mod"
            (core / "data" / "hullmods").mkdir(parents=True)
            (core / "data" / "hullmods" / "hull_mods.csv").write_text("name,id\nA,automated\nB,heavyarmor\n", encoding="utf-8")
            (mod / "data" / "hullmods").mkdir(parents=True)
            (mod / "data" / "hullmods" / "hull_mods.csv").write_text("name,id\nB,heavyarmor\nC,fx_own\n", encoding="utf-8")
            (mod / "mod_info.json").write_text('{"id": "fx", "replace": ["data/hullmods/hull_mods.csv"]}', encoding="utf-8")
            found = [f.evidence for f in scan_mod(mod, vanilla_core=core).findings if f.id == "replace-drops-rc8-entries"]
        self.assertEqual(found, [["replace:data/hullmods/hull_mods.csv", "lost:1", "id:automated"]])


class RetiredVanillaClassTests(unittest.TestCase):
    def test_a_class_only_an_older_vanilla_shipped_is_flagged(self) -> None:
        # Ironclads' jar bundled 0.7.2's SystemBountyEvent, which RC8 no longer ships (2026-10-05).
        import zipfile

        from bridgeforge import scanner

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = base / "Starsector" / "starsector-core"
            old = base / "Starsector7.2" / "starsector-core"
            core.mkdir(parents=True)
            old.mkdir(parents=True)
            api = "com/fs/starfarer/api/impl/campaign/"
            with zipfile.ZipFile(core / "starfarer.api.jar", "w") as z:
                z.writestr(api + "CoreScript.class", b"")
            with zipfile.ZipFile(old / "starfarer.api.jar", "w") as z:
                z.writestr(api + "CoreScript.class", b"")
                z.writestr(api + "events/SystemBountyEvent.class", b"")
            mod = base / "mod"
            (mod / "jars").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            with zipfile.ZipFile(mod / "jars" / "m.jar", "w") as z:
                z.writestr(api + "events/SystemBountyEvent.class", b"")
                z.writestr(api + "CoreScript.class", b"")  # still in RC8: another check's business
                z.writestr(api + "rulecmd/payFee.class", b"")  # a mod's own class in vanilla's package
            scanner._OLD_VANILLA_CLASSES.clear()
            found = [f.evidence for f in scan_mod(mod, vanilla_core=core).findings if f.id == "retired-vanilla-class-copy"]
            scanner._OLD_VANILLA_CLASSES.clear()
        self.assertEqual(found, [["class:com.fs.starfarer.api.impl.campaign.events.SystemBountyEvent"]])


class InheritedInterfaceMethodTests(unittest.TestCase):
    def test_extending_rc8s_base_class_supplies_the_method(self) -> None:
        # Grytpype & Moriarty (2026-10-05): "extends BaseHullMod implements HullModEffect" was flagged.
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "hullmods").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "hullmods" / "A.java").write_text(
                "package data.hullmods;\npublic class A extends BaseHullMod implements HullModEffect { }\n", encoding="utf-8")
            (mod / "data" / "hullmods" / "B.java").write_text(
                "package data.hullmods;\npublic class B implements HullModEffect { }\n", encoding="utf-8")
            files = sorted({f.file for f in scan_mod(mod).findings if f.id == "target-interface-method-missing"})
        self.assertEqual(files, ["data/hullmods/B.java"])


class EntityLookupCaseTests(unittest.TestCase):
    def test_a_lookup_differing_only_in_case_from_its_creation_is_safe(self) -> None:
        # Aivon Republic (2026-10-05): addPlanet("Atempause", ...) then getEntityById("atempause"); RC8-20.
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "scripts" / "Gen.java").write_text(
                'class Gen { void g(StarSystemAPI system, PlanetAPI star) {\n'
                '  PlanetAPI a = system.addPlanet("Atempause", star, "Atempause", "terran", 30, 90, 3500, 180f);\n'
                '  station.setCircularOrbit(system.getEntityById("atempause"), 45, 200, 15);\n} }\n', encoding="utf-8")
            found = [f.classification for f in scan_mod(mod).findings if f.id == "hard-coded-campaign-entity-reference"]
        self.assertEqual(found, ["SAFE"])


class VariantSubfolderTests(unittest.TestCase):
    def test_a_mission_variant_in_a_subfolder_resolves(self) -> None:
        # Sanguinary Autonomist Defectors (2026-10-05): data/variants/mothership/*.variant.
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "variants" / "mothership").mkdir(parents=True)
            (mod / "data" / "missions" / "m").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "variants" / "mothership" / "fx_big_Standard.variant").write_text(
                '{"variantId": "fx_big_Standard", "hullId": "fx_big"}', encoding="utf-8")
            (mod / "data" / "missions" / "m" / "MissionDefinition.java").write_text(
                'class M { void d(MissionDefinitionAPI api) { api.addToFleet(FleetSide.PLAYER, "fx_big_Standard", FleetMemberType.SHIP, true); } }',
                encoding="utf-8")
            found = [f for f in scan_mod(mod).findings if f.id == "mission-local-fleet-reference-missing"]
        self.assertEqual(found, [])


class NeverCalledGeneratorTests(unittest.TestCase):
    def test_a_generator_nothing_references_is_safe(self) -> None:
        # Galaxy Tigers' test/Testo (2026-10-05): a system generator no class calls cannot duplicate a system.
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "scripts" / "world").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "scripts" / "world" / "Testo.java").write_text(
                'package data.scripts.world;\npublic class Testo { public void generate(SectorAPI sector) {\n'
                '  StarSystemAPI system = sector.createStarSystem("Test");\n} }\n', encoding="utf-8")
            found = [(f.classification, f.evidence) for f in scan_mod(mod).findings if f.id == "system-generation-unguarded"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], "SAFE")
        self.assertIn("never called", found[0][1][0])


class GenerationGuardPatternTests(unittest.TestCase):
    # ROADMAP 51 (2026-10-05): SLPC's persistent-data flag and Artefact's qualified generator call.
    def _scan(self, plugin: str) -> list:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "scripts" / "world").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "scripts" / "world" / "Gen.java").write_text(
                'package data.scripts.world;\npublic class Gen { public void generate(SectorAPI sector) {\n'
                '  StarSystemAPI system = sector.createStarSystem("Uclora");\n} }\n', encoding="utf-8")
            (mod / "data" / "scripts" / "Plugin.java").write_text(plugin, encoding="utf-8")
            return [(f.classification, f.evidence[0]) for f in scan_mod(mod).findings if f.id == "system-generation-unguarded"]

    def test_a_persistent_data_flag_in_onGameLoad_guards_generation(self) -> None:
        found = self._scan('public class Plugin extends BaseModPlugin { public void onGameLoad(boolean n) {\n'
                           '  if (!Global.getSector().getPersistentData().containsKey("mark")) {\n'
                           '    Global.getSector().getPersistentData().put("mark", true); new Gen().generate(Global.getSector()); } } }\n')
        self.assertEqual(found, [])

    def test_a_qualified_generator_call_is_traced(self) -> None:
        found = self._scan('public class Plugin extends BaseModPlugin { public void onNewGame() {\n'
                           '  new data.scripts.world.Gen().generate(Global.getSector()); } }\n')
        self.assertEqual(found, [("SAFE", "data/scripts/world/Gen.java:3: Uclora (called from onNewGame)")])


class BundledSourceStaleTests(unittest.TestCase):
    def test_source_whose_class_header_or_presence_differs_from_the_jar(self) -> None:
        # ROADMAP 47 (2026-10-05): Grytpype's src said "implements HullModEffect", the jar's class extends BaseHullMod.
        import shutil
        import subprocess

        javac = shutil.which("javac")
        jdk = Path(r"C:\Users\exxec\Documents\Project BridgeForge\In operation\_rig\jdk-25.0.4.1+1\bin")
        if (jdk / "javac.exe").is_file():
            javac = str(jdk / "javac.exe")
        if not javac:
            self.skipTest("no javac")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "build" / "data"
            build.mkdir(parents=True)
            (build / "Base.java").write_text("package data;\npublic class Base { }\n", encoding="utf-8")
            (build / "Mod.java").write_text("package data;\npublic class Mod extends Base { public void go() {} }\n", encoding="utf-8")
            subprocess.run([javac, "-d", str(root / "classes"), str(build / "Base.java"), str(build / "Mod.java")], check=True)
            mod = root / "mod"
            (mod / "jars").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            with zipfile.ZipFile(mod / "jars" / "m.jar", "w") as z:
                for name in ("Base", "Mod"):
                    z.write(root / "classes" / "data" / f"{name}.class", f"data/{name}.class")
            (mod / "src" / "data").mkdir(parents=True)
            (mod / "src" / "data" / "Mod.java").write_text("package data;\npublic class Mod { public void go() {} }\n", encoding="utf-8")
            (mod / "src" / "data" / "Ghost.java").write_text("package data;\npublic class Ghost { }\n", encoding="utf-8")
            found = [f.evidence for f in scan_mod(mod).findings if f.id == "bundled-source-stale"]
        self.assertEqual(found[0][:2], ["differ:1", "source-only:1"])
        self.assertIn("extends Object in source, Base in jar", found[0][2])
