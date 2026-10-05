"""Hooks only one mod can own (owner question 2026-10-04, AoTD compatibility)."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.scanner import scan_mod

HEADER = "id,name,cost mult,build time,income,upkeep,downgrade,upgrade,tags,data,image,plugin,desc,order\n"


def _ids(mod: Path, core: Path, wanted: str) -> list[list[str]]:
    return [f.evidence for f in scan_mod(mod, vanilla_core=core).findings if f.id == wanted]


class SharedHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.core, self.mod = root / "core", root / "mod"
        (self.core / "data" / "campaign").mkdir(parents=True)
        (self.core / "data" / "campaign" / "industries.csv").write_text(
            HEADER + "population,Pop,,,,,,,,,,com.fs.Pop,,1\nmining,Mining,,,,,,,,,,com.fs.Mining,,2\n", encoding="utf-8")
        (self.mod / "data" / "campaign").mkdir(parents=True)
        (self.mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_industry_plugin_override_flags_only_a_changed_vanilla_plugin(self) -> None:
        # DNEEP's population row (2026-10-04); a same-plugin row and a new industry are not flagged.
        (self.mod / "data" / "campaign" / "industries.csv").write_text(
            HEADER + "population,Pop,,,,,,,,,,data.scripts.PopDNEEP,,1\nmining,Mining,,,,,,,,,,com.fs.Mining,,2\n"
            "fx_new,New,,,,,,,,,,data.New,,3\n", encoding="utf-8")
        self.assertEqual(_ids(self.mod, self.core, "industry-plugin-override"),
                         [["industry:population", "plugin:data.scripts.PopDNEEP", "rc8:com.fs.Pop"]])

    def test_new_game_plugin_override(self) -> None:
        # Adjusted Sector's settings.json (2026-10-04).
        (self.mod / "data" / "config").mkdir(parents=True)
        (self.mod / "data" / "config" / "settings.json").write_text(
            '{"plugins": {"newGameSectorProcGen": "data.Gen"}, "other": 1}', encoding="utf-8")
        self.assertEqual(_ids(self.mod, self.core, "new-game-plugin-override"),
                         [["key:newGameSectorProcGen", "plugin:data.Gen"]])

    def test_temporary_market_fleet_source_in_source_and_jar(self) -> None:
        # Exigency's fleet managers (2026-10-04): createMarket, FleetParamsV3, removeMarket in one class.
        (self.mod / "data" / "scripts").mkdir(parents=True)
        (self.mod / "data" / "scripts" / "Spawner.java").write_text(
            "class Spawner { void s() { MarketAPI m = Global.getFactory().createMarket(\"a\", \"a\", 4);\n"
            "  FleetFactoryV3.createFleet(new FleetParamsV3(m, null, \"f\", -1f, \"p\", 1, 0, 0, 0, 0, 0, 0));\n"
            "  Global.getSector().getEconomy().removeMarket(m); } }\n", encoding="utf-8")
        (self.mod / "jars").mkdir()
        with zipfile.ZipFile(self.mod / "jars" / "m.jar", "w") as jar:
            jar.writestr("data/A.class", b"createMarket FleetParamsV3 removeMarket")
            jar.writestr("data/B.class", b"createMarket FleetParamsV3")
            jar.writestr("data/C.class", b"createMarket FleetParamsV3 removeMarket addMarket")  # Omega-Trauma's shape
        found = sorted(f.file for f in scan_mod(self.mod, vanilla_core=self.core).findings
                       if f.id == "temporary-market-fleet-source")
        self.assertEqual(found, ["data/scripts/Spawner.java", "jars/m.jar!data/A.class"])


if __name__ == "__main__":
    unittest.main()


class TemporaryMarketFixerTests(unittest.TestCase):
    def test_drops_only_the_remove_of_a_never_added_market(self) -> None:
        from bridgeforge.fixers import compute_fix

        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            source = mod / "data" / "scripts" / "Spawner.java"
            source.write_text(
                "class Spawner {\n  void s() {\n    MarketAPI m = Global.getFactory().createMarket(\"a\", \"a\", 4);\n"
                "    FleetFactoryV3.createFleet(new FleetParamsV3(m, null, \"f\", -1f, \"p\", 1, 0, 0, 0, 0, 0, 0));\n"
                "    Global.getSector().getEconomy().removeMarket(m);\n  }\n}\n", encoding="utf-8")
            changes = compute_fix(mod, "temporary-market-fleet-source").changes
            after = changes[0].after.decode("utf-8")
        self.assertNotIn("getEconomy().removeMarket(m);", after)
        self.assertIn("// BridgeForge: removeMarket(m) dropped", after)
        self.assertIn("new FleetParamsV3(m,", after)  # the fleet still builds from the same market


class LibraryMentionInCommentTests(unittest.TestCase):
    def test_a_comment_naming_a_library_is_not_a_dependency(self) -> None:
        # DNEEP (2026-10-05): a BridgeForge comment "a Nexerelin random sector" was read as Nexerelin code.
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "plugins").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "plugins" / "P.java").write_text(
                "package data.plugins;\n// a save without this system (a Nexerelin random sector, exerelin.campaign) crashed\n"
                "public class P { }\n", encoding="utf-8")
            used = [f for f in scan_mod(mod).findings if f.id == "undeclared-library-dependency"]
        self.assertEqual(used, [])


class PersonNamesDuplicateRowTests(unittest.TestCase):
    def test_repeated_row_is_found_and_removed_keeping_bytes(self) -> None:
        # Ironclads: "Duplicate key [Mao |  | f | xle | ]" Fatal at startup (GRP10B-20261005); blank rows repeat too
        from bridgeforge.fixers import compute_fix

        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "characters").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "pn"}', encoding="utf-8")
            names = mod / "data" / "characters" / "person_names.csv"
            names.write_bytes(b"name,gender,usage,category\r\nMao,,l,xle\r\n,,,\r\nMao,,f,xle\r\n,,,\r\nMao,,f,xle\r\nTabar,,l,fringe\r\n")
            found = [f for f in scan_mod(mod).findings if f.id == "person-names-duplicate-row"]
            after = compute_fix(mod, "person-names-duplicate-row").changes[0].after
        self.assertEqual(found[0].evidence, ["line:6"])
        self.assertEqual(after, b"name,gender,usage,category\r\nMao,,l,xle\r\n,,,\r\nMao,,f,xle\r\n,,,\r\nTabar,,l,fringe\r\n")


class JsonDuplicateKeyTests(unittest.TestCase):
    def test_a_repeated_key_in_a_faction_is_flagged(self) -> None:
        # Ironclads pirates.faction: Fatal 'Duplicate key "knownFighters"' (GRP10E-20261005); lenient syntax still parses
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod"
            (mod / "data" / "world" / "factions").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "dk"}', encoding="utf-8")
            (mod / "data" / "world" / "factions" / "pirates.faction").write_text(
                '{\n\t# comment\n\t"id":"pirates",\n\t"knownFighters":{"fighters":["a_wing"]},\n'
                '\t"knownShips":{"hulls":["h"]},"knownFighters":{"fighters":["a_wing"]},\n}', encoding="utf-8")
            (mod / "data" / "world" / "factions" / "clean.faction").write_text('{"id":"clean","a":{"x":1},"b":{"x":2}}', encoding="utf-8")
            found = [(f.file, f.evidence) for f in scan_mod(mod).findings if f.id == "json-duplicate-key"]
        self.assertEqual(found, [("data/world/factions/pirates.faction", ["key:knownFighters"])])
