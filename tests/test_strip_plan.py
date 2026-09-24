from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.strip_plan import StripPlanError, strip_plan
from tests.support import resolved_temp_dir


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def _core(root: Path) -> Path:
    core = root / "core"
    weapons = {"lightmg": ("BALLISTIC", "SMALL", ""), "lightac": ("BALLISTIC", "SMALL", ""), "ioncannon": ("ENERGY", "SMALL", ""),
               "heavyac": ("BALLISTIC", "MEDIUM", ""), "harpoon": ("MISSILE", "SMALL", ""), "hybridbeam": ("ENERGY", "SMALL", "HYBRID"),
               "flare": ("DECORATIVE", "SMALL", "")}
    _write(core / "data/weapons/weapon_data.csv", "id\n" + "".join(f"{w}\n" for w in weapons))
    for weapon_id, (kind, size, override) in weapons.items():
        _write(core / f"data/weapons/{weapon_id}.wpn", {"id": weapon_id, "type": kind, "size": size, **({"mountTypeOverride": override} if override else {})})
    _write(core / "data/hullmods/hull_mods.csv", "id\nheavyarmor\n")
    _write(core / "data/hulls/wing_data.csv", "id\ntalon_wing\n")
    _write(core / "data/hulls/ship_data.csv", "id\nwolf\n")
    _write(core / "data/hulls/wolf.ship", {"hullId": "wolf", "hullSize": "FRIGATE", "weaponSlots": [
        {"id": "WS1", "type": "BALLISTIC", "size": "SMALL"}, {"id": "WS2", "type": "HYBRID", "size": "SMALL"},
        {"id": "WS3", "type": "DECORATIVE", "size": "SMALL"}]})
    return core


def _mod(root: Path) -> Path:
    mod = root / "mod"
    _write(mod / "mod_info.json", '{"id":"cc","name":"Communist Clouds","gameVersion":"0.98a"}')
    _write(mod / "data/variants/wolf_Red.variant", {"hullId": "wolf", "variantId": "wolf_Red", "hullMods": ["vayra_red_army", "heavyarmor"],
                                                     "wings": ["vayra_wing"], "weaponGroups": [{"weapons": {"WS1": "vayra_gun", "WS2": "vayra_gun", "WS3": "vayra_gun"}}]})
    _write(mod / "data/variants/ghost_Std.variant", {"hullId": "vayra_ghost", "variantId": "ghost_Std", "weaponGroups": [{"weapons": {"WS1": "vayra_gun"}}]})
    _write(mod / "data/hulls/skins/ghost_red.skin", {"skinHullId": "ghost_red", "baseHullId": "vayra_ghost"})
    _write(mod / "data/world/factions/red_army.faction", {"id": "red_army", "knownShips": {"hulls": ["wolf", "vayra_ghost"]},
                                                          "knownWeapons": {"weapons": ["vayra_gun", "lightmg"]}, "knownFighters": {"fighters": ["vayra_wing"]}})
    return mod


class StripPlanTests(unittest.TestCase):
    def test_every_place_each_unresolved_id_sits(self):
        with resolved_temp_dir() as root:
            result = strip_plan(_mod(root), _core(root))
        actions = sorted((e["file"], e["kind"], e["id"], e["action"]) for e in result["edits"])
        self.assertEqual(actions, [
            ("data/hulls/skins/ghost_red.skin", "hull", "vayra_ghost", "delete this skin: its baseHullId is unresolved, so nothing in it can load"),
            ("data/variants/ghost_Std.variant", "hull", "vayra_ghost", "delete this variant: its hullId is unresolved, so nothing in it can load"),
            ("data/variants/wolf_Red.variant", "hullmod", "vayra_red_army", "remove from hullMods"),
            ("data/variants/wolf_Red.variant", "weapon", "vayra_gun", "empty slot WS1 (weaponGroups[0])"),
            ("data/variants/wolf_Red.variant", "weapon", "vayra_gun", "empty slot WS2 (weaponGroups[0])"),
            ("data/variants/wolf_Red.variant", "weapon", "vayra_gun", "empty slot WS3 (weaponGroups[0])"),
            ("data/variants/wolf_Red.variant", "wing", "vayra_wing", "remove from wings"),
            ("data/world/factions/red_army.faction", "hull", "vayra_ghost", "remove from knownShips.hulls"),
            ("data/world/factions/red_army.faction", "weapon", "vayra_gun", "remove from knownWeapons.weapons"),
            ("data/world/factions/red_army.faction", "wing", "vayra_wing", "remove from knownFighters.fighters"),
        ])

    def test_substitutes_fit_the_slot_type_and_size(self):
        with resolved_temp_dir() as root:
            result = strip_plan(_mod(root), _core(root))
        by_slot = {e["action"].split()[2]: e["substitutes"] for e in result["edits"] if e["action"].startswith("empty slot")}
        # hybridbeam is ENERGY with mountTypeOverride HYBRID, which fits BALLISTIC slots (scanner.MOUNT_OVERRIDE_FITS).
        self.assertEqual(by_slot["WS1"]["candidates"], ["hybridbeam", "lightac", "lightmg"])
        self.assertEqual(by_slot["WS2"]["candidates"], ["hybridbeam", "ioncannon", "lightac", "lightmg"])
        self.assertEqual(by_slot["WS3"]["candidates"], [])
        self.assertIn("not a regular weapon slot", by_slot["WS3"]["note"])

    def test_id_filter_and_errors(self):
        with resolved_temp_dir() as root:
            mod, core = _mod(root), _core(root)
            only = strip_plan(mod, core, ["hullmod:vayra_red_army"])
            self.assertEqual([(e["kind"], e["id"]) for e in only["edits"]], [("hullmod", "vayra_red_army")])
            with self.assertRaises(StripPlanError):
                strip_plan(root / "nope", core)
            with self.assertRaises(StripPlanError):
                strip_plan(mod, root / "nope")

    def test_cli(self):
        with resolved_temp_dir() as root:
            mod, core = _mod(root), _core(root)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["strip-plan", str(mod), "--vanilla-core", str(core), "--id", "weapon:vayra_gun"]), 0)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["strip-plan", str(root / "nope"), "--vanilla-core", str(core)]), 2)
        self.assertIn("data/variants/wolf_Red.variant: empty slot WS1 (weaponGroups[0]) -- weapon:vayra_gun", out.getvalue())
        self.assertIn("    vanilla BALLISTIC SMALL options: hybridbeam, lightac, lightmg", out.getvalue())
        # With only weapons in scope, the variant on the unresolved hull keeps its slot line but no substitutes.
        self.assertIn("ghost_Std.variant: empty slot WS1 (weaponGroups[0]) -- weapon:vayra_gun\n    slot not found on the resolved hull", out.getvalue())


if __name__ == "__main__":
    unittest.main()
