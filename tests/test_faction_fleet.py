"""94.G2 slice 23 (owner 2026-11-23, "Yes, as needs"): a faction's fleet is part of its gene. The donor's ship-role entries
for the hulls and wings the faction knows are needs.donor, the variants and wings they name are needed genes, and a
carrier role entry nothing defines is a load gap (RC8-46). Synthetic fixtures only."""
from __future__ import annotations

import json
import unittest

from bridgeforge.genome.carrier_load import load_gaps
from bridgeforge.genome.faction_fleet import ROLES_FILE, role_gaps
from bridgeforge.genome.gene import describe, validate
from tests.support import resolved_temp_dir, write_text as _write
from tests.test_gene_faction import FACTION, _core, _mod

KNOWS = {**FACTION, "knownFighters": {"tags": [], "fighters": ["demo_wing"]}}
ROLES = {"combatSmall": {"demo_hull_Var1": 10, "stranger_Var1": 5, "wolf_CS": 3, "includeDefault": False},
         "fighterWings": {"demo_wing": 5, "stranger_wing": 2},
         "freighterSmall": {"stranger_Var1": 4},
         "doctrine": {"demo_hull_Var1": 1}}


def _fleet_mod(root):
    mod = _mod(root, faction=KNOWS)
    _write(mod / ROLES_FILE, json.dumps(ROLES))
    _write(mod / "data" / "variants" / "demo_hull_Var1.variant", json.dumps({"variantId": "demo_hull_Var1", "hullId": "demo_hull"}))
    _write(mod / "data" / "variants" / "stranger_Var1.variant", json.dumps({"variantId": "stranger_Var1", "hullId": "stranger"}))
    _write(mod / "data" / "hulls" / "wing_data.csv", "id,variant\ndemo_wing,demo_hull_Var1\nstranger_wing,stranger_Var1\n")
    return mod


def _fleet_core(root):
    core = _core(root)
    _write(core / "data" / "variants" / "wolf_CS.variant", json.dumps({"variantId": "wolf_CS", "hullId": "wolf"}))
    return core


class FleetNeedTests(unittest.TestCase):
    def test_the_roles_of_its_known_hulls_and_wings_are_needs_and_their_variants_genes(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_fleet_mod(root), "faction:demo_faction", vanilla_core=_fleet_core(root))
        self.assertEqual(validate(gene), [])
        self.assertEqual(gene["needs"]["donor"], [
            f"{ROLES_FILE}#/combatSmall/demo_hull_Var1", f"{ROLES_FILE}#/combatSmall/includeDefault",
            f"{ROLES_FILE}#/combatSmall/wolf_CS", f"{ROLES_FILE}#/fighterWings/demo_wing"])
        self.assertTrue({"variant:demo_hull_Var1", "wing:demo_wing"} <= set(gene["needs"]["genes"]))
        self.assertIn("variant:wolf_CS", gene["needs"]["vanilla"])  # a core variant of a known core hull
        self.assertFalse([g for g in gene["needs"]["genes"] if "stranger" in g])  # not a hull or wing it knows
        self.assertFalse([d for d in gene["needs"]["donor"] if "/doctrine/" in d or "freighterSmall" in d])

    def test_a_faction_with_no_role_file_keeps_its_manifest_shape(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "faction:demo_faction", vanilla_core=_core(root))
        self.assertNotIn("donor", gene["needs"])


class RoleGapTests(unittest.TestCase):
    def test_a_carrier_role_entry_nothing_defines_is_a_gap_and_the_subtraction_check_skips_it(self) -> None:
        with resolved_temp_dir() as root:
            core = _fleet_core(root)
            carrier = root / "carrier"
            _write(carrier / ROLES_FILE, json.dumps({"combatSmall": {"wolf_CS": 3, "gone_Var1": 2, "fallback": "combatMedium"},
                                                     "doctrine": {"also_gone": 1}}))
            _write(carrier / "data" / "world" / "factions" / "demo.faction",
                   json.dumps({"id": "demo_faction", "shipRoles": {"combatLarge": {"lost_wing": 1}}}))
            gaps = role_gaps(carrier, [core])
            in_load = load_gaps(carrier, core)
            for_subtraction = load_gaps(carrier, core, carrier_only=False)
        self.assertEqual([(g["file"], g["role"], g["id"]) for g in gaps],
                         [(ROLES_FILE, "combatSmall", "gone_Var1"), ("data/world/factions/demo.faction", "combatLarge", "lost_wing")])
        self.assertEqual([g["finding"] for g in in_load], ["ship-role-variant-missing", "ship-role-variant-missing"])
        self.assertEqual(for_subtraction, [])  # a subtraction rightly leaves a removed variant's role entries behind


if __name__ == "__main__":
    unittest.main()
