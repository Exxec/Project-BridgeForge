"""Checks refined on Zorg18 (2026-09-14): campaign fleet ids, and known lists nothing reads."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod


def _mod(root: Path) -> Path:
    mod = root / "mod"
    for folder in ("data/hulls", "data/variants", "data/world/factions", "src/data/scripts/world"):
        (mod / folder).mkdir(parents=True)
    (mod / "mod_info.json").write_text(json.dumps({"id": "zorg", "name": "Zorg", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    (mod / "data" / "hulls" / "zorg_probe.ship").write_text(json.dumps({"hullId": "zorg_probe"}), encoding="utf-8")
    (mod / "data" / "variants" / "zorg_probe_Configurated.variant").write_text(json.dumps({"variantId": "zorg_probe_Configurated", "hullId": "zorg_probe"}), encoding="utf-8")
    with (mod / "data" / "hulls" / "wing_data.csv").open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows([["id", "variant"], ["zorg_sphere_wing", "zorg_probe_Configurated"]])
    (mod / "data" / "world" / "factions" / "zorg.faction").write_text(json.dumps({"id": "zorg"}), encoding="utf-8")
    return mod


def _ids(result, finding_id: str) -> list:
    return [f for f in result.findings if f.id == finding_id]


SPAWNER = """package data.scripts.world;
import com.fs.starfarer.api.fleet.FleetMemberType;
public class Spawner {
    // "zorg_probe_Old" in a comment is not a reference
    private static final String[] SHIPS = {"zorg_probe_Configurated", "zorg_probe_Missing"};
    private static final String[] WINGS = {"zorg_sphere_wing", "zorg_cube_wing"};
    private static final String STATION = "zorg_station_000";
    void spawn() { Object t = FleetMemberType.SHIP; }
}
"""


class CampaignFleetReferenceTests(unittest.TestCase):
    def test_missing_variant_and_wing_ids_in_a_spawner_are_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "src" / "data" / "scripts" / "world" / "Spawner.java").write_text(SPAWNER, encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        missing = _ids(result, "campaign-fleet-reference-missing")
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].evidence, ["src/data/scripts/world/Spawner.java: zorg_cube_wing", "src/data/scripts/world/Spawner.java: zorg_probe_Missing"])


class KnownListsSeverityTests(unittest.TestCase):
    def test_faction_without_markets_or_roles_is_low(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "src" / "data" / "scripts" / "world" / "Gen.java").write_text('class Gen { void g(Object s) { /* addCustomEntity("x", "y", "z", "zorg") */ } }', encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        finding = _ids(result, "faction-known-lists-missing")[0]
        self.assertEqual(finding.severity, "low")
        self.assertIn("market-evidence:none", finding.evidence)

    def test_faction_that_owns_a_market_stays_high(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "src" / "data" / "scripts" / "world" / "Gen.java").write_text('class Gen { void g(Object m) { m.setFactionId("zorg"); } }', encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        finding = _ids(result, "faction-known-lists-missing")[0]
        self.assertEqual(finding.severity, "high")
        self.assertIn("market-evidence:found", finding.evidence)


class KnownListsJarEvidenceTests(unittest.TestCase):
    def test_market_created_only_in_the_jar_keeps_high(self) -> None:
        # Bundled sources often lag the shipped jar, so bytecode counts as market evidence too.
        import zipfile

        from tests.test_personality_ids import _class_with_strings

        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            info = json.loads((mod / "mod_info.json").read_text(encoding="utf-8"))
            info["jars"] = ["jars/z.jar"]
            (mod / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
            (mod / "src" / "data" / "scripts" / "world" / "Gen.java").write_text("class Gen {}", encoding="utf-8")
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "z.jar", "w") as archive:
                archive.writestr("data/scripts/world/Gen.class", _class_with_strings("data/scripts/world/Gen", ["zorg"], ["setFactionId"]))
            result = scan_mod(mod, TargetProfile())
        finding = _ids(result, "faction-known-lists-missing")[0]
        self.assertEqual(finding.severity, "high")
        self.assertIn("market-evidence:found", finding.evidence)


class CoreCampaignPluginTests(unittest.TestCase):
    GEN = "class ZorgGen { void generate(Object sector) {\n  // sector.registerPlugin(new CoreCampaignPluginImpl()); in a comment\n  sector.registerPlugin(new CoreCampaignPluginImpl());\n} }"
    TC = "class VacuumSectorGen implements SectorGeneratorPlugin { public void generate(Object sector) { sector.registerPlugin(new CoreCampaignPluginImpl()); } }"

    def test_system_generator_that_reregisters_the_core_plugin_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "src" / "data" / "scripts" / "world" / "ZorgGen.java").write_text(self.GEN, encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        hits = _ids(result, "core-campaign-plugin-reregistered")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].evidence, ["src/data/scripts/world/ZorgGen.java:3"])

    def test_sector_generator_replacement_is_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "src" / "data" / "scripts" / "world" / "VacuumSectorGen.java").write_text(self.TC, encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(result, "core-campaign-plugin-reregistered"), [])


class SystemGenerationGuardTests(unittest.TestCase):
    GEN = 'class ZorgGen { public void generate(Object sector) { Object s = sector.createStarSystem("Zorg Zeta"); } }'

    def _scan(self, plugin: str):
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            world = mod / "src" / "data" / "scripts" / "world"
            (world / "ZorgGen.java").write_text(self.GEN, encoding="utf-8")
            (world / "ZorgModPlugin.java").write_text(plugin, encoding="utf-8")
            return _ids(scan_mod(mod, TargetProfile()), "system-generation-unguarded")

    def test_unguarded_on_new_game_is_low(self) -> None:
        hits = self._scan("class ZorgModPlugin extends BaseModPlugin { public void onNewGame() { new ZorgGen().generate(null); } }")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].severity, "low")
        self.assertIn("Zorg Zeta (called from onNewGame)", hits[0].evidence[0])

    def test_unguarded_on_game_load_is_medium(self) -> None:
        hits = self._scan("class ZorgModPlugin extends BaseModPlugin { public void onGameLoad(boolean n) { new ZorgGen().generate(null); } }")
        self.assertEqual(hits[0].severity, "medium")
        self.assertIn("(called from onGameLoad)", hits[0].evidence[0])

    def test_static_accessor_in_on_game_load_is_not_generation(self) -> None:
        # Exigency: onGameLoad calls Tasserus.getExiHome(); generation is in initExigency(), from onNewGame.
        plugin = ("class ZorgModPlugin extends BaseModPlugin {\n"
                  "  private static void initZorg() { new ZorgGen().generate(null); }\n"
                  "  public void onNewGame() { initZorg(); }\n"
                  "  public void onGameLoad(boolean n) { Object home = ZorgGen.getHome(); }\n}")
        hits = self._scan(plugin)
        self.assertEqual(hits[0].severity, "low")
        self.assertIn("(called from onNewGame)", hits[0].evidence[0])

    def test_memory_flag_or_lookup_guard_is_quiet(self) -> None:
        flag = 'class ZorgModPlugin extends BaseModPlugin { public void onNewGame() { if (Global.getSector().getMemoryWithoutUpdate().getBoolean("$zorg_done")) return; new ZorgGen().generate(null); } }'
        lookup = 'class ZorgModPlugin extends BaseModPlugin { public void onNewGame() { if (Global.getSector().getStarSystem("Zorg Zeta") != null) return; new ZorgGen().generate(null); } }'
        self.assertEqual(self._scan(flag), [])
        self.assertEqual(self._scan(lookup), [])


class SystemLookupGuardTests(unittest.TestCase):
    def test_null_guarded_lookups_are_safe_and_unguarded_ones_stay_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            world = mod / "src" / "data" / "scripts" / "world"
            (world / "Guarded.java").write_text('class Guarded { void a(com.fs.starfarer.api.campaign.SectorAPI s) {\n  StarSystemAPI askonia = s.getStarSystem("askonia");\n  if (askonia != null) { askonia.getStar(); }\n  if (s.getStarSystem("radikius") == null) { return; }\n} }', encoding="utf-8")
            (world / "Bare.java").write_text('class Bare { void a(com.fs.starfarer.api.campaign.SectorAPI s) { s.getStarSystem("corvus").getStar(); } }', encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        by_system = {f.evidence[0]: f for f in _ids(result, "hard-coded-campaign-system-reference")}
        self.assertEqual(by_system["askonia"].classification, "SAFE")
        self.assertIn("null-guarded", by_system["askonia"].evidence)
        self.assertEqual(by_system["radikius"].classification, "SAFE")
        self.assertEqual(by_system["corvus"].classification, "REVIEW")
        self.assertEqual(by_system["corvus"].severity, "medium")


if __name__ == "__main__":
    unittest.main()
