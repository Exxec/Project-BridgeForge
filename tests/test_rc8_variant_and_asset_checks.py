from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: object) -> None:
    _write(path, json.dumps(data))


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


SHIP_DATA_HEADER = "name,id,designation,fleet pts,hitpoints,ordnance points,fighter bays,hints,number\n"


def _ship_data_row(hull_id: str, ordnance_points: int, fighter_bays: int, hints: str = "") -> str:
    return f"Demo,{hull_id},Frigate,5,1000,{ordnance_points},{fighter_bays},{hints},1\n"


WEAPON_DATA_HEADER = "name,id,OPs,type,hints,number\n"


def _weapon_data_row(weapon_id: str, ops: str, weapon_type: str = "BALLISTIC", hints: str = "") -> str:
    return f"Demo,{weapon_id},{ops},{weapon_type},{hints},1\n"


def _basic_ship_json(hull_id: str, hull_size: str = "FRIGATE", slots=None, built_in_wings=None, built_in_mods=None, built_in_weapons=None) -> dict:
    return {
        "hullId": hull_id,
        "hullSize": hull_size,
        "spriteName": "graphics/demo.png",
        "weaponSlots": slots or [],
        "builtInWings": built_in_wings or [],
        "builtInMods": built_in_mods or [],
        "builtInWeapons": built_in_weapons or {},
    }


def _basic_variant(hull_id: str, variant_id: str, wings=None, weapon_groups=None, hull_mods=None, flux_vents=0, flux_caps=0) -> dict:
    return {
        "variantId": variant_id,
        "hullId": hull_id,
        "wings": wings or [],
        "weaponGroups": weapon_groups or [],
        "hullMods": hull_mods or [],
        "fluxVents": flux_vents,
        "fluxCapacitors": flux_caps,
    }


class VariantWingsExceedBaysTests(unittest.TestCase):
    def test_variant_wings_exceed_bays_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 40, 1))
            _write_json(root / "data" / "hulls" / "demo_hull.ship", _basic_ship_json("demo_hull"))
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("demo_hull", "demo_variant", wings=["wing_a", "wing_b"]),
            )
            result = scan_mod(root)
            hits = _findings(result, "variant-wings-exceed-bays")
            self.assertEqual(len(hits), 1)
            self.assertIn("fighter-bays:1", hits[0].evidence)
            self.assertIn("wings:2", hits[0].evidence)

    def test_built_in_wings_count_toward_bays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 40, 1))
            _write_json(root / "data" / "hulls" / "demo_hull.ship", _basic_ship_json("demo_hull", built_in_wings=["builtin_wing"]))
            _write_json(root / "data" / "variants" / "demo_variant.variant", _basic_variant("demo_hull", "demo_variant", wings=["wing_a"]))
            result = scan_mod(root)
            self.assertEqual(len(_findings(result, "variant-wings-exceed-bays")), 1)

    def test_within_bays_does_not_fire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 40, 2))
            _write_json(root / "data" / "hulls" / "demo_hull.ship", _basic_ship_json("demo_hull"))
            _write_json(root / "data" / "variants" / "demo_variant.variant", _basic_variant("demo_hull", "demo_variant", wings=["wing_a", "wing_b"]))
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-wings-exceed-bays"), [])

    def test_unresolvable_hull_produces_no_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_json(root / "data" / "variants" / "demo_variant.variant", _basic_variant("missing_hull", "demo_variant", wings=["a", "b", "c"]))
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-wings-exceed-bays"), [])
            self.assertEqual(_findings(result, "variant-op-over-budget"), [])
            self.assertEqual(_findings(result, "variant-weapon-slot-mismatch"), [])

    def test_fighter_size_hull_skipped_entirely(self) -> None:
        """Fighter hulls have OP=0 in ship_data.csv (verified against vanilla); their baked-in
        hullMods/wings must not be checked against a budget/bay count that does not apply to them."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("fighter_hull", 0, 0))
            _write(
                root / "data" / "hullmods" / "hull_mods.csv",
                "name,id,cost_frigate,cost_dest,cost_cruiser,cost_capital,number\nArmor,fighter_mod,20,20,20,20,1\n",
            )
            _write_json(root / "data" / "hulls" / "fighter_hull.ship", _basic_ship_json("fighter_hull", hull_size="FIGHTER"))
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("fighter_hull", "demo_variant", hull_mods=["fighter_mod"]),
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-op-over-budget"), [])
            self.assertEqual(_findings(result, "variant-wings-exceed-bays"), [])

    def test_hull_id_resolved_through_skin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("base_hull", 40, 1))
            _write_json(root / "data" / "hulls" / "base_hull.ship", _basic_ship_json("base_hull"))
            _write_json(root / "data" / "hulls" / "skins" / "skin_hull.skin", {"baseHullId": "base_hull", "skinHullId": "skin_hull"})
            _write_json(root / "data" / "variants" / "demo_variant.variant", _basic_variant("skin_hull", "demo_variant", wings=["a", "b"]))
            result = scan_mod(root)
            hits = _findings(result, "variant-wings-exceed-bays")
            self.assertEqual(len(hits), 1)
            self.assertIn("hull:base_hull", hits[0].evidence)


class VariantOpOverBudgetTests(unittest.TestCase):
    def test_op_over_budget_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 10, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("big_gun", "20"))
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "BALLISTIC", "size": "LARGE"}]),
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "big_gun"}}]),
            )
            result = scan_mod(root)
            hits = _findings(result, "variant-op-over-budget")
            self.assertEqual(len(hits), 1)
            self.assertIn("budget:10.0", hits[0].evidence)

    def test_within_tolerance_does_not_fire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 20, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("gun", "21"))
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "BALLISTIC", "size": "SMALL"}]),
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "gun"}}]),
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-op-over-budget"), [])

    def test_built_in_weapon_slot_and_hullmod_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 5, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("free_gun", "50"))
            _write(
                root / "data" / "hullmods" / "hull_mods.csv",
                "name,id,cost_frigate,cost_dest,cost_cruiser,cost_capital,number\nFree,free_mod,50,50,50,50,1\n",
            )
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json(
                    "demo_hull",
                    slots=[{"id": "WS1", "type": "BALLISTIC", "size": "SMALL"}],
                    built_in_mods=["free_mod"],
                    built_in_weapons={"WS1": "free_gun"},
                ),
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "free_gun"}}], hull_mods=["free_mod"]),
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-op-over-budget"), [])


class VariantWeaponSlotMismatchTests(unittest.TestCase):
    def test_size_mismatch_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("gun", "5"))
            _write_json(root / "data" / "weapons" / "gun.wpn", {"id": "gun", "type": "BALLISTIC", "size": "LARGE"})
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "BALLISTIC", "size": "SMALL"}]),
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "gun"}}]),
            )
            result = scan_mod(root)
            hits = _findings(result, "variant-weapon-slot-mismatch")
            self.assertEqual(len(hits), 1)
            self.assertIn("weapon-size:LARGE", hits[0].evidence)

    def test_type_mismatch_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("missile", "5"))
            _write_json(root / "data" / "weapons" / "missile.wpn", {"id": "missile", "type": "MISSILE", "size": "SMALL"})
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "BALLISTIC", "size": "SMALL"}]),
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "missile"}}]),
            )
            result = scan_mod(root)
            self.assertEqual(len(_findings(result, "variant-weapon-slot-mismatch")), 1)

    def test_skin_slot_override_resolves_a_false_positive(self) -> None:
        """P14 item 28, found 2026-09-20 on Rebal's brawler_tritachyon: a mismatch check comparing
        against the base .ship's raw slot type, when the actual mounting hull is a .skin that
        retypes that exact slot, produces a false positive the skin's own data already resolves."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("base_hull", 100, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("laser", "5"))
            _write_json(root / "data" / "weapons" / "laser.wpn", {"id": "laser", "type": "ENERGY", "size": "SMALL"})
            _write_json(
                root / "data" / "hulls" / "base_hull.ship",
                _basic_ship_json("base_hull", slots=[{"id": "WS 001", "type": "BALLISTIC", "size": "SMALL"}]),
            )
            _write_json(
                root / "data" / "hulls" / "skins" / "skin_hull.skin",
                {
                    "baseHullId": "base_hull",
                    "skinHullId": "skin_hull",
                    "weaponSlotChanges": {"WS 001": {"type": "ENERGY"}},
                },
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("skin_hull", "demo_variant", weapon_groups=[{"weapons": {"WS 001": "laser"}}]),
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-weapon-slot-mismatch"), [])

    def test_skin_slot_override_can_also_reveal_a_real_mismatch(self) -> None:
        """The fix must not just clear false positives -- it must also surface a genuine mismatch
        that only exists because of the skin's own override (found on Rebal's falcon_p: the base
        hull's slot was more permissive than the skin's retyped one)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("base_hull", 100, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("cannon", "5"))
            _write_json(root / "data" / "weapons" / "cannon.wpn", {"id": "cannon", "type": "BALLISTIC", "size": "SMALL"})
            _write_json(
                root / "data" / "hulls" / "base_hull.ship",
                _basic_ship_json("base_hull", slots=[{"id": "WS 001", "type": "HYBRID", "size": "SMALL"}]),
            )
            _write_json(
                root / "data" / "hulls" / "skins" / "skin_hull.skin",
                {
                    "baseHullId": "base_hull",
                    "skinHullId": "skin_hull",
                    "weaponSlotChanges": {"WS 001": {"type": "MISSILE"}},
                },
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("skin_hull", "demo_variant", weapon_groups=[{"weapons": {"WS 001": "cannon"}}]),
            )
            result = scan_mod(root)
            hits = _findings(result, "variant-weapon-slot-mismatch")
            self.assertEqual(len(hits), 1)
            self.assertIn("slot-type:MISSILE", hits[0].evidence)

    def test_hybrid_slot_accepts_ballistic_and_energy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("laser", "5"))
            _write_json(root / "data" / "weapons" / "laser.wpn", {"id": "laser", "type": "ENERGY", "size": "SMALL"})
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "HYBRID", "size": "SMALL"}]),
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "laser"}}]),
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-weapon-slot-mismatch"), [])

    def test_skipped_slot_types_not_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("missile", "5"))
            _write_json(root / "data" / "weapons" / "missile.wpn", {"id": "missile", "type": "MISSILE", "size": "LARGE"})
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "LAUNCH_BAY", "size": "SMALL"}]),
            )
            _write_json(
                root / "data" / "variants" / "demo_variant.variant",
                _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "missile"}}]),
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-weapon-slot-mismatch"), [])


class DescriptionMissingTests(unittest.TestCase):
    def test_hull_missing_description_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 40, 0))
            result = scan_mod(root)
            hits = _findings(result, "description-missing")
            self.assertEqual(len(hits), 1)
            self.assertIn("hull:demo_hull", hits[0].evidence)

    def test_hull_with_description_does_not_fire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 40, 0))
            _write(root / "data" / "strings" / "descriptions.csv", "id,type,text1\ndemo_hull,SHIP,Some text\n")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "description-missing"), [])

    def test_hide_in_codex_hull_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 40, 0, hints="HIDE_IN_CODEX"))
            result = scan_mod(root)
            self.assertEqual(_findings(result, "description-missing"), [])

    def test_weapon_system_tag_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("sys_gun", "5", hints="SYSTEM"))
            result = scan_mod(root)
            self.assertEqual(_findings(result, "description-missing"), [])

    def test_weapon_without_ops_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("no_op_gun", ""))
            result = scan_mod(root)
            self.assertEqual(_findings(result, "description-missing"), [])

    def test_weapon_described_only_in_vanilla_does_not_fire(self) -> None:
        """A mod that rebalances a vanilla weapon id (same id, new stats) inherits vanilla's
        descriptions.csv row unless the mod overrides it; this must not be flagged as missing."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vanilla_root = Path(directory) / "vanilla-core"
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("lightmg", "1"))
            _write(vanilla_root / "data" / "strings" / "descriptions.csv", "id,type,text1\nlightmg,WEAPON,Vanilla text\n")
            result = scan_mod(root, vanilla_core=vanilla_root)
            self.assertEqual(_findings(result, "description-missing"), [])

    def test_ship_system_missing_description_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "shipsystems" / "ship_systems.csv", "name,id,number\nDemo,demo_system,1\n")
            result = scan_mod(root)
            hits = _findings(result, "description-missing")
            self.assertEqual(len(hits), 1)
            self.assertIn("ship-system:demo_system", hits[0].evidence)


class AssetReferenceMissingTests(unittest.TestCase):
    def test_ship_sprite_missing_with_vanilla_core_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vanilla_root = Path(directory) / "vanilla-core"
            vanilla_root.mkdir(parents=True)
            _write_json(root / "data" / "hulls" / "demo_hull.ship", {"hullId": "demo_hull", "spriteName": "graphics/missing.png"})
            result = scan_mod(root, vanilla_core=vanilla_root)
            hits = _findings(result, "asset-reference-missing")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].classification, "REVIEW")

    def test_ship_sprite_missing_without_vanilla_core_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_json(root / "data" / "hulls" / "demo_hull.ship", {"hullId": "demo_hull", "spriteName": "graphics/missing.png"})
            result = scan_mod(root)
            hits = _findings(result, "asset-reference-missing")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].classification, "UNKNOWN")

    def test_ship_sprite_present_in_vanilla_does_not_fire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vanilla_root = Path(directory) / "vanilla-core"
            _write(vanilla_root / "graphics" / "present.png", "fake-png-bytes")
            _write_json(root / "data" / "hulls" / "demo_hull.ship", {"hullId": "demo_hull", "spriteName": "graphics/present.png"})
            result = scan_mod(root, vanilla_core=vanilla_root)
            self.assertEqual(_findings(result, "asset-reference-missing"), [])

    def test_wpn_sprite_missing_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vanilla_root = Path(directory) / "vanilla-core"
            vanilla_root.mkdir(parents=True)
            _write_json(root / "data" / "weapons" / "gun.wpn", {"id": "gun", "turretSprite": "graphics/gun_turret.png"})
            result = scan_mod(root, vanilla_core=vanilla_root)
            hits = _findings(result, "asset-reference-missing")
            self.assertEqual(len(hits), 1)
            self.assertIn("field:turretSprite", hits[0].evidence)

    def test_sounds_json_missing_file_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vanilla_root = Path(directory) / "vanilla-core"
            vanilla_root.mkdir(parents=True)
            _write_json(root / "data" / "config" / "sounds.json", {"my_sound": [{"file": "sounds/missing.ogg"}]})
            result = scan_mod(root, vanilla_core=vanilla_root)
            hits = _findings(result, "asset-reference-missing")
            self.assertEqual(len(hits), 1)
            self.assertIn("path:sounds/missing.ogg", hits[0].evidence)

    def test_sounds_json_present_file_does_not_fire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "sounds" / "present.ogg", "fake-ogg-bytes")
            _write_json(root / "data" / "config" / "sounds.json", {"my_sound": [{"file": "sounds/present.ogg"}]})
            result = scan_mod(root)
            self.assertEqual(_findings(result, "asset-reference-missing"), [])


class VariantRealWorldExemptionTests(unittest.TestCase):
    """Regressions from triaging Legacy of Arkgneisis with its dossier (2026-09-11)."""

    def test_converted_hangar_built_in_adds_a_bay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 40, 0))
            _write_json(root / "data" / "hulls" / "demo_hull.ship", _basic_ship_json("demo_hull", built_in_mods=["converted_hangar"]))
            _write_json(root / "data" / "variants" / "demo_variant.variant", _basic_variant("demo_hull", "demo_variant", wings=["wing_a"]))
            result = scan_mod(root)
            self.assertEqual(_findings(result, "variant-wings-exceed-bays"), [])

    def _slot_fixture(self, root: Path, mount_override: str | None) -> None:
        slot = {"id": "WS 001", "type": "BALLISTIC", "size": "SMALL", "mount": "TURRET"}
        _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 40, 0))
        _write_json(root / "data" / "hulls" / "demo_hull.ship", _basic_ship_json("demo_hull", slots=[slot]))
        wpn = {"id": "demo_beam", "type": "ENERGY", "size": "SMALL"}
        if mount_override:
            wpn["mountTypeOverride"] = mount_override
        _write_json(root / "data" / "weapons" / "demo_beam.wpn", wpn)
        _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("demo_beam", "1", "ENERGY"))
        _write_json(
            root / "data" / "variants" / "demo_variant.variant",
            _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS 001": "demo_beam"}}]),
        )

    def test_mount_type_override_hybrid_fits_ballistic_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._slot_fixture(root, "HYBRID")
            self.assertEqual(_findings(scan_mod(root), "variant-weapon-slot-mismatch"), [])

    def test_energy_weapon_without_override_in_ballistic_slot_still_fires(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._slot_fixture(root, None)
            self.assertEqual(len(_findings(scan_mod(root), "variant-weapon-slot-mismatch")), 1)


if __name__ == "__main__":
    unittest.main()
