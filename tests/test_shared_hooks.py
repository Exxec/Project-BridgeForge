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
