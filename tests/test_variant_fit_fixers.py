"""Fixers for variant-wings-exceed-bays, variant-weapon-slot-mismatch and variant-weapon-slot-missing
(owner ruling 2026-09-29: "drop only what RC8's changed hulls can no longer fit; keep everything else
exactly as the mod author wrote it")."""
from __future__ import annotations

import unittest

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.scanner import _load_lenient_json_file, scan_mod
from tests.support import resolved_temp_dir
from tests.test_rc8_variant_and_asset_checks import (
    SHIP_DATA_HEADER,
    WEAPON_DATA_HEADER,
    _basic_ship_json,
    _basic_variant,
    _ship_data_row,
    _weapon_data_row,
    _write,
    _write_json,
)


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


class VariantWingsExceedBaysFixerTests(unittest.TestCase):
    def test_trims_from_the_end_and_leaves_the_rest(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 50, 1))
            _write_json(root / "data" / "hulls" / "demo_hull.ship", _basic_ship_json("demo_hull"))
            variant_path = root / "data" / "variants" / "demo_variant.variant"
            _write_json(
                variant_path,
                _basic_variant(
                    "demo_hull", "demo_variant",
                    wings=["wing_a", "wing_b", "wing_c"],
                    hull_mods=["some_mod"],
                    flux_vents=3,
                ),
            )
            before = _findings(scan_mod(root), "variant-wings-exceed-bays")
            self.assertEqual(len(before), 1)
            self.assertIn("wings:3", before[0].evidence)
            self.assertIn("fighter-bays:1", before[0].evidence)
            apply_fix(compute_fix(root, "variant-wings-exceed-bays", {}))
            data = _load_lenient_json_file(variant_path)
            after = scan_mod(root)
        # Only the tail of "wings" is trimmed (kept down to the hull's 1 bay); every other field,
        # including an unrelated hullMods entry and fluxVents, is untouched.
        self.assertEqual(data["wings"], ["wing_a"])
        self.assertEqual(data["hullMods"], ["some_mod"])
        self.assertEqual(data["fluxVents"], 3)
        self.assertEqual(_findings(after, "variant-wings-exceed-bays"), [])
        self.assertEqual(_findings(after, "variant-weapon-slot-mismatch"), [])
        self.assertEqual(_findings(after, "variant-weapon-slot-missing"), [])

    def test_built_in_wings_alone_over_bays_is_refused(self) -> None:
        # Built-in wings live on the .ship file, not the variant: nothing here for the fixer to trim.
        with resolved_temp_dir() as root:
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 50, 1))
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", built_in_wings=["builtin_a", "builtin_b"]),
            )
            _write_json(root / "data" / "variants" / "demo_variant.variant", _basic_variant("demo_hull", "demo_variant"))
            found = scan_mod(root)
            self.assertEqual(_findings(found, "variant-wings-exceed-bays"), [])
            self.assertEqual(len(_findings(found, "variant-built-in-wings-exceed-bays")), 1)  # a SAFE note instead
            with self.assertRaises(FixerError):
                compute_fix(root, "variant-wings-exceed-bays", {})

    def test_already_fitting_variant_is_unchanged(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 50, 2))
            _write_json(root / "data" / "hulls" / "demo_hull.ship", _basic_ship_json("demo_hull"))
            variant_path = root / "data" / "variants" / "demo_variant.variant"
            original = _basic_variant("demo_hull", "demo_variant", wings=["wing_a", "wing_b"])
            _write_json(variant_path, original)
            self.assertEqual(_findings(scan_mod(root), "variant-wings-exceed-bays"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "variant-wings-exceed-bays", {})
            self.assertEqual(_load_lenient_json_file(variant_path), original)


class VariantWeaponSlotMismatchFixerTests(unittest.TestCase):
    def _hull_and_weapons(self, root) -> None:
        _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
        _write(
            root / "data" / "weapons" / "weapon_data.csv",
            WEAPON_DATA_HEADER + _weapon_data_row("big_gun", "5") + _weapon_data_row("small_gun", "5") + _weapon_data_row("other_gun", "5"),
        )
        _write_json(root / "data" / "weapons" / "big_gun.wpn", {"id": "big_gun", "type": "BALLISTIC", "size": "LARGE"})
        _write_json(root / "data" / "weapons" / "small_gun.wpn", {"id": "small_gun", "type": "BALLISTIC", "size": "SMALL"})
        _write_json(root / "data" / "weapons" / "other_gun.wpn", {"id": "other_gun", "type": "BALLISTIC", "size": "SMALL"})
        _write_json(
            root / "data" / "hulls" / "demo_hull.ship",
            _basic_ship_json(
                "demo_hull",
                slots=[
                    {"id": "WS1", "type": "BALLISTIC", "size": "SMALL"},
                    {"id": "WS2", "type": "BALLISTIC", "size": "SMALL"},
                    {"id": "WS3", "type": "BALLISTIC", "size": "SMALL"},
                ],
            ),
        )

    def test_removes_only_the_mismatched_entry_keeps_sibling_and_other_group(self) -> None:
        with resolved_temp_dir() as root:
            self._hull_and_weapons(root)
            variant_path = root / "data" / "variants" / "demo_variant.variant"
            _write_json(
                variant_path,
                _basic_variant(
                    "demo_hull", "demo_variant",
                    weapon_groups=[
                        {"weapons": {"WS1": "big_gun", "WS2": "small_gun"}},  # WS1 too large for its slot
                        {"weapons": {"WS3": "other_gun"}},
                    ],
                ),
            )
            before = _findings(scan_mod(root), "variant-weapon-slot-mismatch")
            self.assertEqual(len(before), 1)
            self.assertIn("slot:WS1", before[0].evidence)
            self.assertIn("weapon:big_gun", before[0].evidence)
            apply_fix(compute_fix(root, "variant-weapon-slot-mismatch", {}))
            data = _load_lenient_json_file(variant_path)
            after = scan_mod(root)
        self.assertEqual(
            data["weaponGroups"],
            [{"weapons": {"WS2": "small_gun"}}, {"weapons": {"WS3": "other_gun"}}],
        )
        self.assertEqual(_findings(after, "variant-weapon-slot-mismatch"), [])
        self.assertEqual(_findings(after, "variant-weapon-slot-missing"), [])
        self.assertEqual(_findings(after, "variant-wings-exceed-bays"), [])

    def test_emptied_group_is_removed_entirely(self) -> None:
        with resolved_temp_dir() as root:
            self._hull_and_weapons(root)
            variant_path = root / "data" / "variants" / "demo_variant.variant"
            _write_json(
                variant_path,
                _basic_variant(
                    "demo_hull", "demo_variant",
                    weapon_groups=[
                        {"weapons": {"WS1": "big_gun"}},  # the group's only weapon, and it's mismatched
                        {"weapons": {"WS2": "small_gun"}},
                    ],
                ),
            )
            apply_fix(compute_fix(root, "variant-weapon-slot-mismatch", {}))
            data = _load_lenient_json_file(variant_path)
            after = scan_mod(root)
        self.assertEqual(data["weaponGroups"], [{"weapons": {"WS2": "small_gun"}}])
        self.assertEqual(_findings(after, "variant-weapon-slot-mismatch"), [])

    def test_already_fitting_variant_is_unchanged(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
            _write(root / "data" / "weapons" / "weapon_data.csv", WEAPON_DATA_HEADER + _weapon_data_row("gun", "5"))
            _write_json(root / "data" / "weapons" / "gun.wpn", {"id": "gun", "type": "BALLISTIC", "size": "SMALL"})
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "BALLISTIC", "size": "SMALL"}]),
            )
            variant_path = root / "data" / "variants" / "demo_variant.variant"
            original = _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "gun"}}])
            _write_json(variant_path, original)
            self.assertEqual(_findings(scan_mod(root), "variant-weapon-slot-mismatch"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "variant-weapon-slot-mismatch", {})
            self.assertEqual(_load_lenient_json_file(variant_path), original)


class VariantWeaponSlotMissingFixerTests(unittest.TestCase):
    def test_removes_only_the_entry_in_the_missing_slot(self) -> None:
        # FlowerGod FGV_hyperion_Attack (FG-SOLO3-20260928): "WS 006" on RC8's three-slot Hyperion.
        with resolved_temp_dir() as root:
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "ENERGY", "size": "MEDIUM"}]),
            )
            variant_path = root / "data" / "variants" / "demo_variant.variant"
            _write_json(
                variant_path,
                _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "gun", "WS 006": "gun"}}]),
            )
            before = _findings(scan_mod(root), "variant-weapon-slot-missing")
            self.assertEqual(len(before), 1)
            self.assertIn("slot:WS 006", before[0].evidence)
            apply_fix(compute_fix(root, "variant-weapon-slot-missing", {}))
            data = _load_lenient_json_file(variant_path)
            after = scan_mod(root)
        self.assertEqual(data["weaponGroups"], [{"weapons": {"WS1": "gun"}}])
        self.assertEqual(_findings(after, "variant-weapon-slot-missing"), [])
        self.assertEqual(_findings(after, "variant-weapon-slot-mismatch"), [])

    def test_emptied_group_is_removed_entirely(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "ENERGY", "size": "MEDIUM"}]),
            )
            variant_path = root / "data" / "variants" / "demo_variant.variant"
            _write_json(
                variant_path,
                _basic_variant(
                    "demo_hull", "demo_variant",
                    weapon_groups=[
                        {"weapons": {"WS 006": "gun"}},  # the group's only weapon, and the slot doesn't exist
                        {"weapons": {"WS1": "gun"}},
                    ],
                ),
            )
            apply_fix(compute_fix(root, "variant-weapon-slot-missing", {}))
            data = _load_lenient_json_file(variant_path)
            after = scan_mod(root)
        self.assertEqual(data["weaponGroups"], [{"weapons": {"WS1": "gun"}}])
        self.assertEqual(_findings(after, "variant-weapon-slot-missing"), [])

    def test_already_fitting_variant_is_unchanged(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "data" / "hulls" / "ship_data.csv", SHIP_DATA_HEADER + _ship_data_row("demo_hull", 100, 0))
            _write_json(
                root / "data" / "hulls" / "demo_hull.ship",
                _basic_ship_json("demo_hull", slots=[{"id": "WS1", "type": "ENERGY", "size": "MEDIUM"}]),
            )
            variant_path = root / "data" / "variants" / "demo_variant.variant"
            original = _basic_variant("demo_hull", "demo_variant", weapon_groups=[{"weapons": {"WS1": "gun"}}])
            _write_json(variant_path, original)
            self.assertEqual(_findings(scan_mod(root), "variant-weapon-slot-missing"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "variant-weapon-slot-missing", {})
            self.assertEqual(_load_lenient_json_file(variant_path), original)


if __name__ == "__main__":
    unittest.main()
