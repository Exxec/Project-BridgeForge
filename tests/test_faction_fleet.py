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


class ReviewTests(unittest.TestCase):
    """The independent review of slice 23 (2026-11-23)."""

    def test_priority_lists_count_and_object_fallbacks_travel_with_their_block(self) -> None:
        faction = {**FACTION, "priorityShips": {"tags": [], "hulls": ["prio_hull"]}}
        roles = {"combatMedium": {"prio_Var1": 4, "fallback": {"combatSmall": 1}, "fallback2": {"combatLarge": 1}}}
        with resolved_temp_dir() as root:
            mod = _mod(root, faction=faction)
            _write(mod / ROLES_FILE, json.dumps(roles))
            _write(mod / "data" / "variants" / "prio_Var1.variant", json.dumps({"variantId": "prio_Var1", "hullId": "prio_hull"}))
            gene = describe(mod, "faction:demo_faction", vanilla_core=_core(root))
        self.assertEqual(gene["needs"]["donor"], [f"{ROLES_FILE}#/combatMedium/fallback", f"{ROLES_FILE}#/combatMedium/fallback2",
                                                  f"{ROLES_FILE}#/combatMedium/prio_Var1"])
        self.assertIn("variant:prio_Var1", gene["needs"]["genes"])

    def test_hulls_known_by_tag_and_undefined_role_variants_are_suspects(self) -> None:
        faction = {**KNOWS, "knownShips": {"tags": ["demo_bp"], "hulls": ["demo_hull"]}}
        with resolved_temp_dir() as root:
            mod = _fleet_mod(root)
            _write(mod / "data" / "world" / "factions" / "demo.faction", json.dumps(faction))
            roles = {**ROLES, "combatSmall": {**ROLES["combatSmall"], "ghost_Var1": 2}}
            _write(mod / ROLES_FILE, json.dumps(roles))
            gene = describe(mod, "faction:demo_faction", vanilla_core=_fleet_core(root))
        fleet = [s for s in gene["unknowns"]["suspects"] if s["path"] == ROLES_FILE]
        self.assertEqual([s["mentions"] for s in fleet], [["demo_bp"], ["ghost_Var1"]])
        self.assertFalse([d for d in gene["needs"]["donor"] if "ghost_Var1" in d])

    def test_an_unreadable_role_file_fails_closed(self) -> None:
        with resolved_temp_dir() as root:
            carrier = root / "carrier"
            _write(carrier / ROLES_FILE, "[1, 2")
            gaps = role_gaps(carrier, [_fleet_core(root)])
        self.assertEqual(gaps, [{"finding": "ship-roles-unreadable", "file": ROLES_FILE}])

    def test_a_set_carrier_holds_the_chosen_role_entries_and_their_variants(self) -> None:
        from bridgeforge.genome.gene_set import prove_set

        with resolved_temp_dir() as root:
            mod, core = _fleet_mod(root), _fleet_core(root)
            result = prove_set(mod, "faction:demo_faction", root / "set", vanilla_core=core, quiet=True)
            carrier = root / "set" / "work" / "carrier"
            roles = json.loads((carrier / ROLES_FILE).read_text(encoding="utf-8"))
            variant = (carrier / "data" / "variants" / "demo_hull_Var1.variant").is_file()
            proof = json.loads((root / "set" / "set-isolation-proof.json").read_text(encoding="utf-8"))
        self.assertEqual(roles, {"combatSmall": {"demo_hull_Var1": 10, "wolf_CS": 3, "includeDefault": False},
                                 "fighterWings": {"demo_wing": 5}})
        self.assertTrue(variant)
        self.assertEqual((result["refused"], [g for g in proof["load_gaps"] if g["finding"].startswith("ship-role")]), (0, []))


class TagTests(unittest.TestCase):
    """Slice 24 (2026-11-23; the owner deferred to the advisor, who recommended expanding hull and wing tags). RC7 javap:
    SpecStore adds every hull whose spec has any of a block's `tags`; hull tags are ship_data.csv's comma-separated `tags`
    column; a skin clears its base hull's tags and has only its own `.skin` `tags`."""

    def _tag_mod(self, root):
        faction = {**FACTION, "knownShips": {"tags": ["demo_bp", "nothing_bp"], "hulls": []},
                   "knownFighters": {"tags": ["demo_bp"], "fighters": []}}
        mod = _mod(root, faction=faction)
        _write(mod / "data" / "hulls" / "ship_data.csv",
               'name,id,tags\nDemo,demo_hull,"demo_bp, other"\nOther,other_hull,elsewhere\nHound,hound,\n')
        _write(mod / "data" / "hulls" / "demo_skin.skin", json.dumps({"baseHullId": "demo_hull", "skinHullId": "demo_skin", "tags": ["demo_bp"]}))
        _write(mod / "data" / "hulls" / "plain_skin.skin", json.dumps({"baseHullId": "demo_hull", "skinHullId": "plain_skin"}))
        _write(mod / "data" / "hulls" / "wing_data.csv", "id,variant,tags\ndemo_wing,demo_hull_Var1,demo_bp\n")
        _write(mod / "data" / "variants" / "demo_hull_Var1.variant", json.dumps({"variantId": "demo_hull_Var1", "hullId": "demo_hull"}))
        _write(mod / "data" / "variants" / "other_Var1.variant", json.dumps({"variantId": "other_Var1", "hullId": "other_hull"}))
        _write(mod / ROLES_FILE, json.dumps({"combatSmall": {"demo_hull_Var1": 5, "other_Var1": 3}}))
        return mod

    def _tag_core(self, root):
        core = _core(root)
        _write(core / "data" / "hulls" / "ship_data.csv", "name,id,tags\nWolf,wolf,base_bp\nHound,hound,demo_bp\n")
        return core

    def test_tags_reach_tagged_hulls_skins_by_their_own_tags_wings_and_a_mod_row_wins(self) -> None:
        from bridgeforge.genome.faction_fleet import known
        from bridgeforge.vendor_plan import _Index

        with resolved_temp_dir() as root:
            mod, core = self._tag_mod(root), self._tag_core(root)
            knows = known(json.loads((mod / "data" / "world" / "factions" / "demo.faction").read_text(encoding="utf-8")),
                          _Index(mod), _Index(core))
        self.assertEqual(knows["by_tag"]["hull"], {"demo_hull", "demo_skin"})  # not plain_skin; hound's mod row has no tag
        self.assertEqual(knows["by_tag"]["wing"], {"demo_wing"})
        self.assertEqual(knows["unmatched"], {"nothing_bp"})  # demo_bp, in both lists, is matched by a hull and a wing

    def test_a_tag_known_faction_needs_its_tagged_hulls_and_their_role_variants(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(self._tag_mod(root), "faction:demo_faction", vanilla_core=self._tag_core(root))
        self.assertTrue({"hull:demo_hull", "hull:demo_skin", "wing:demo_wing", "variant:demo_hull_Var1"} <= set(gene["needs"]["genes"]))
        self.assertNotIn("hull:other_hull", gene["needs"]["genes"])
        self.assertEqual(gene["needs"]["donor"], [f"{ROLES_FILE}#/combatSmall/demo_hull_Var1"])
        self.assertIn(["nothing_bp"], [s["mentions"] for s in gene["unknowns"]["suspects"] if s["path"] == ROLES_FILE])


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
