"""market-on-hyperspace-entity (ROADMAP 58, item 73 F1): a market on an entity created in hyperspace (Exigency Avesta, LTA, Tahlan)."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.scan.scan_hyperspace_market import hyperspace_market_entities
from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

# Excerpt shape of LTA_gen.java (LTA 2026-10-14): hyperspace location in a variable, entity, then market.
VIA_VARIABLE = """class Gen {
    void run(SectorAPI sector) {
        LocationAPI hyperspace = sector.getHyperspace();
        SectorEntityToken station = hyperspace.addCustomEntity("st", "Tech", "station", "pirates");
        MarketAPI market = Global.getFactory().createMarket("st", "Tech", 7);
        market.setPrimaryEntity(station);
        station.setMarket(market);
        Global.getSector().getEconomy().addMarket(market, true);
    }
}
"""
# Shape of LegioSiegeBaseIntel.java (Tahlan): a field assigned from the hyperspace location, market by setPrimaryEntity.
FIELD_ENTITY = """class Intel {
    SectorEntityToken entity;
    void build() {
        LocationAPI hyperspace = Global.getSector().getHyperspace();
        entity = hyperspace.addCustomEntity(null, name, Entities.MAKESHIFT_STATION, id);
        market.setPrimaryEntity(entity);
    }
}
"""
DIRECT = 'class G { void r() { SectorEntityToken e = Global.getSector().getHyperspace().addEntity(null, "n", "t", "f"); e.setMarket(m); } }\n'
IN_SYSTEM = """class Gen {
    void run(StarSystemAPI system) {
        LocationAPI hyperspace = Global.getSector().getHyperspace();
        SectorEntityToken jump = hyperspace.addCustomEntity("j", "Jump", "jump", "neutral");
        SectorEntityToken station = system.addCustomEntity("st", "Tech", "station", "pirates");
        station.setMarket(market);
        Global.getSector().getEconomy().addMarket(market, true);
    }
}
"""
COMMENTED = "class G { void r() { // SectorEntityToken e = Global.getSector().getHyperspace().addEntity(null, \"n\"); e.setMarket(m);\n } }\n"


def _hits(source: str):
    with resolved_temp_dir() as base:
        mod = Path(base) / "mod"
        (mod / "data" / "scripts").mkdir(parents=True)
        (mod / "mod_info.json").write_text('{"id":"demo","name":"Demo","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
        (mod / "data" / "scripts" / "Gen.java").write_text(source, encoding="utf-8")
        return [f for f in scan_mod(mod).findings if f.id == "market-on-hyperspace-entity"]


class MarketOnHyperspaceEntityTests(unittest.TestCase):
    def test_entity_from_hyperspace_variable_with_market_is_found(self) -> None:
        self.assertEqual(hyperspace_market_entities(VIA_VARIABLE), ["station"])

    def test_field_entity_with_set_primary_entity_is_found(self) -> None:
        self.assertEqual(hyperspace_market_entities(FIELD_ENTITY), ["entity"])

    def test_direct_getHyperspace_call_is_found(self) -> None:
        self.assertEqual(hyperspace_market_entities(DIRECT), ["e"])

    def test_hyperspace_entity_without_market_is_quiet(self) -> None:
        self.assertEqual(hyperspace_market_entities(IN_SYSTEM), [])

    def test_scan_reports_the_finding_with_the_entity(self) -> None:
        hits = _hits(VIA_VARIABLE)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].classification, "REVIEW")
        self.assertIn("entity:station", hits[0].evidence)

    def test_scan_is_quiet_when_the_market_never_reaches_the_economy(self) -> None:
        self.assertEqual(_hits(VIA_VARIABLE.replace("addMarket", "keepMarket")), [])

    def test_scan_is_quiet_for_a_market_in_a_system_and_for_commented_code(self) -> None:
        self.assertEqual(_hits(IN_SYSTEM), [])
        self.assertEqual(_hits(COMMENTED), [])


if __name__ == "__main__":
    unittest.main()
