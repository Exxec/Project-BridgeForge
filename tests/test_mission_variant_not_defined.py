"""mission-variant-not-defined (item 73 F4): a mission names a variant or wing nobody defines; the finding names the providing mod."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

MISSION = """package data.missions.demo;
public class MissionDefinition {
    public void defineMission(MissionDefinitionAPI api) {
        boolean swp = Global.getSettings().getModManager().isModEnabled("swp");
        api.addToFleet(FleetSide.PLAYER, "wolf_Hull", FleetMemberType.SHIP, true);
        api.addToFleet(FleetSide.PLAYER, "condor_FS", FleetMemberType.SHIP, false);
        api.addToFleet(FleetSide.PLAYER, "afflictor_Strike", FleetMemberType.SHIP, false);
        api.addToFleet(FleetSide.ENEMY, "ii_basileus_cs", FleetMemberType.SHIP, false);
        api.addToFleet(FleetSide.ENEMY, "demo_own_variant", FleetMemberType.SHIP, false);
        api.addToFleet(FleetSide.ENEMY, "talon_wing", FleetMemberType.FIGHTER_WING, false);
        api.addToFleet(FleetSide.ENEMY, "ghost_wing", FleetMemberType.FIGHTER_WING, false);
        if (swp) {
            api.addToFleet(FleetSide.ENEMY, "swp_arbalest_pir", FleetMemberType.SHIP, false);
        }
    }
}
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build(base: Path, mission: str = MISSION):
    mod, core, providers = base / "mod", base / "core", base / "providers"
    _write(mod / "mod_info.json", '{"id":"demo","name":"Demo","version":"1","gameVersion":"0.98a-RC8"}')
    _write(mod / "data" / "missions" / "demo" / "MissionDefinition.java", mission)
    _write(core / "data" / "variants" / "afflictor_Strike.variant", '{"variantId":"afflictor_Strike","hullId":"afflictor"}')
    _write(core / "data" / "variants" / "sub" / "x.variant", '{"variantId":"talon_x","hullId":"talon"}')
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id\nWolf,wolf\n")
    _write(core / "data" / "hulls" / "wing_data.csv", "id\ntalon_wing\n")
    _write(mod / "data" / "variants" / "demo_own_variant.variant", '{"variantId":"demo_own_variant","hullId":"wolf"}')
    _write(providers / "Imperium" / "mod_info.json", '{"id":"Imperium","name":"Imperium","version":"1","gameVersion":"0.98a-RC8"}')
    _write(providers / "Imperium" / "data" / "variants" / "ii_basileus_cs.variant", '{"variantId":"ii_basileus_cs","hullId":"ii_basileus"}')
    return mod, core, providers


def _hits(mod: Path, core: Path | None, providers: Path | None):
    result = scan_mod(mod, vanilla_core=core, provider_roots=[providers] if providers else None)
    return [f for f in result.findings if f.id == "mission-variant-not-defined"]


class MissionVariantNotDefinedTests(unittest.TestCase):
    def test_missing_variant_and_wing_are_flagged_and_defined_ones_are_not(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = _build(Path(base))
            names = sorted(e.split(":", 1)[1] for f in _hits(mod, core, providers) for e in f.evidence[:1])
        self.assertEqual(names, ["condor_FS", "ghost_wing", "ii_basileus_cs"])

    def test_the_finding_names_the_mod_that_defines_the_variant(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = _build(Path(base))
            hit = next(f for f in _hits(mod, core, providers) if "SHIP:ii_basileus_cs" in f.evidence)
            other = next(f for f in _hits(mod, core, providers) if "SHIP:condor_FS" in f.evidence)
        self.assertIn("Imperium", hit.evidence[1])
        self.assertEqual(hit.confidence, "LOW")  # the mission tests isModEnabled elsewhere
        self.assertIn("no mod under the provider roots defines it", other.evidence[1])

    def test_a_reference_inside_an_ismodenabled_block_is_not_reported(self) -> None:
        with resolved_temp_dir() as base:
            mod, core, providers = _build(Path(base))
            evidence = [e for f in _hits(mod, core, providers) for e in f.evidence]
        self.assertNotIn("SHIP:swp_arbalest_pir", evidence)

    def test_without_vanilla_core_nothing_is_claimed(self) -> None:
        with resolved_temp_dir() as base:
            mod, _, providers = _build(Path(base))
            self.assertEqual(_hits(mod, None, providers), [])


if __name__ == "__main__":
    unittest.main()
