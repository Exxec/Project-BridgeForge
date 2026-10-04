"""procgen-call-argument-suspect (owner request 2026-10-04): Zorg18's ported initStar/addPlanet arguments."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.procgen_args import javap_suspects, source_suspects
from bridgeforge.scanner import scan_mod

PORTED = """class ZorgGen { void generate() {
    PlanetAPI star = system.initStar("zorg_balls_star_000", "star_zorg", 200f, -10000);
    PlanetAPI z1 = system.addPlanet("zorg_planet_001", star, "Zeta I", "zorg_planet", 0, 0, 100, 5000);
    PlanetAPI z2 = system.addPlanet("zorg_planet_002", star, "Zeta II", "zorg_planet", 90, 150, 10000, 150);
    PlanetAPI z3 = system.addPlanet("x", star, "X", "t", angle, size, dist, days);
} }"""

# javap -c -constants of the archived Zorg18 V18+bf.4 ZorgGen.generate, trimmed to the two calls.
LISTING = """  public void generate(com.fs.starfarer.api.campaign.SectorAPI);
    Code:
      47: ldc           #49                 // String zorg_balls_star_000
      49: ldc           #51                 // String star_zorg
      51: ldc           #53                 // float 200.0f
      53: ldc           #54                 // float -10000.0f
      55: invokeinterface #56,  5           // InterfaceMethod com/fs/starfarer/api/campaign/StarSystemAPI.initStar:(Ljava/lang/String;Ljava/lang/String;FF)Lcom/fs/starfarer/api/campaign/PlanetAPI;
      80: ldc           #70                 // String Zeta I
      82: ldc           #72                 // String zorg_planet
      84: fconst_0
      85: fconst_0
      86: ldc           #74                 // float 100.0f
      88: ldc           #75                 // float 5000.0f
      90: invokeinterface #77,  9           // InterfaceMethod com/fs/starfarer/api/campaign/StarSystemAPI.addPlanet:(Ljava/lang/String;Lcom/fs/starfarer/api/campaign/SectorEntityToken;Ljava/lang/String;Ljava/lang/String;FFFF)Lcom/fs/starfarer/api/campaign/PlanetAPI;
      95: bipush        90
      97: i2f
      98: ldc           #80                 // float 150.0f
     100: ldc           #81                 // float 10000.0f
     102: ldc           #82                 // float 150.0f
     104: invokeinterface #77,  9           // InterfaceMethod com/fs/starfarer/api/campaign/StarSystemAPI.addPlanet:(Ljava/lang/String;Lcom/fs/starfarer/api/campaign/SectorEntityToken;Ljava/lang/String;Ljava/lang/String;FFFF)Lcom/fs/starfarer/api/campaign/PlanetAPI;
"""


class ProcgenArgsTests(unittest.TestCase):
    def test_source_flags_the_shifted_port_and_spares_good_and_variable_calls(self) -> None:
        found = source_suspects(PORTED)
        self.assertEqual([(line, method, problems) for line, method, problems in found],
                         [(2, "initStar", ["corona -10000"]), (3, "addPlanet", ["planet radius 0"])])

    def test_javap_listing_flags_the_same_calls(self) -> None:
        found = javap_suspects(LISTING)
        self.assertEqual(found, [("generate", "initStar", ["corona -10000"]), ("generate", "addPlanet", ["planet radius 0"])])

    def test_scan_reports_the_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id": "zorg"}', encoding="utf-8")
            (root / "data" / "scripts" / "world").mkdir(parents=True)
            (root / "data" / "scripts" / "world" / "ZorgGen.java").write_text(PORTED, encoding="utf-8")
            ids = [f.id for f in scan_mod(root).findings]
        self.assertEqual(ids.count("procgen-call-argument-suspect"), 2)


if __name__ == "__main__":
    unittest.main()


class ProcgenFalsePositiveTests(unittest.TestCase):
    # done-audit 2026-10-04: Exigency's retrograde Tasserus orbits and Arkgneisis' mission planets were flagged.
    def test_retrograde_orbit_and_mission_addplanet_are_not_suspect(self) -> None:
        self.assertEqual(source_suspects('system.addPlanet("a", star, "A", "barren", 0, 100, 5000, -45);'), [])
        mission = ("  public void defineMission(com.fs.starfarer.api.mission.MissionDefinitionAPI);\n"
                   "    Code:\n       0: fconst_0\n       1: fconst_0\n       2: fconst_0\n       3: ldc #9 // String star\n"
                   "       5: fconst_0\n       6: invokeinterface #11,  6 // InterfaceMethod com/fs/starfarer/api/mission/"
                   "MissionDefinitionAPI.addPlanet:(FFFLjava/lang/String;F)V\n")
        self.assertEqual(javap_suspects(mission), [])
