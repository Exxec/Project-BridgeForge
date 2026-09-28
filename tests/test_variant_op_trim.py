"""variant-op-over-budget fixer (owner ruling 2026-09-27: trim to fit, best estimate)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.scanner import _load_lenient_json_file, scan_mod
from tests.support import resolved_temp_dir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(root: Path, weapons: int, caps: int, vents: int, mods: list[str]) -> tuple[Path, Path]:
    mod, core = root / "mod", root / "core"
    _write(mod / "mod_info.json", '{"id": "x"}')
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id,ordnance points\n")
    _write(core / "data" / "weapons" / "weapon_data.csv", "name,id,OPs\n")
    _write(core / "data" / "hulls" / "wing_data.csv", "id,op cost\n")
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id,cost_frigate,cost_dest,cost_cruiser,cost_capital\nBig,big_mod,1,2,10,20\nSmall,small_mod,1,1,3,5\n")
    _write(mod / "data" / "hulls" / "ship_data.csv", "name,id,ordnance points\nTest,x_hull,50\n")
    _write(mod / "data" / "weapons" / "weapon_data.csv", f"name,id,OPs\nGun,x_gun,{weapons}\n")
    _write(mod / "data" / "hulls" / "x_hull.ship", json.dumps({"hullId": "x_hull", "hullSize": "CRUISER", "weaponSlots": [
        {"id": "WS1", "type": "BALLISTIC", "size": "LARGE", "mount": "TURRET"}]}))
    _write(mod / "data" / "variants" / "x_hull_std.variant",
           '{\n  "variantId": "x_hull_std",\n  "hullId": "x_hull",\n  "fluxCapacitors": %d,\n  "fluxVents": %d,\n'
           '  "hullMods": [%s],\n  "weaponGroups": [{"weapons": {"WS1": "x_gun"}}]\n}\n' % (caps, vents, ", ".join(json.dumps(m) for m in mods)))
    return mod, core


class VariantOpTrimTests(unittest.TestCase):
    def test_flux_first_then_costliest_hull_mod(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, weapons=30, caps=10, vents=10, mods=["big_mod", "small_mod"])  # 30+20+13 = 63 vs 50
            apply_fix(compute_fix(mod, "variant-op-over-budget", {"vanilla_core": core}))
            data = _load_lenient_json_file(mod / "data" / "variants" / "x_hull_std.variant")
            remaining = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "variant-op-over-budget"]
        self.assertEqual((data["fluxCapacitors"], data["fluxVents"]), (0, 7))  # 13 over: 10 capacitors, then 3 vents
        self.assertEqual(data["hullMods"], ["big_mod", "small_mod"])
        self.assertEqual(remaining, [])

    def test_s_mods_listed_in_hull_mods_cost_nothing(self) -> None:
        # 9 queue variants list S-mods in hullMods too; they cost 0 OP. 50 weapons + big_mod (10) as an S-mod = 50.
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, weapons=50, caps=0, vents=0, mods=["big_mod"])
            path = mod / "data" / "variants" / "x_hull_std.variant"
            original = path.read_text(encoding="utf-8")
            path.write_text(original.replace('"hullMods": ["big_mod"],', '"hullMods": ["big_mod"], "sMods": ["big_mod"],'), encoding="utf-8")
            with_s_mod = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "variant-op-over-budget"]
            path.write_text(original, encoding="utf-8")
            without = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "variant-op-over-budget"]
        self.assertEqual(with_s_mod, [])
        self.assertEqual(len(without), 1)

    def test_hull_mods_go_after_flux_and_weapons_are_never_removed(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, weapons=45, caps=2, vents=2, mods=["big_mod", "small_mod"])  # 45+4+13 = 62 vs 50
            apply_fix(compute_fix(mod, "variant-op-over-budget", {"vanilla_core": core}))
            data = _load_lenient_json_file(mod / "data" / "variants" / "x_hull_std.variant")
        self.assertEqual((data["fluxCapacitors"], data["fluxVents"]), (0, 0))
        self.assertEqual(data["hullMods"], ["small_mod"])
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, weapons=70, caps=1, vents=1, mods=[])
            with self.assertRaises(FixerError):
                compute_fix(mod, "variant-op-over-budget", {"vanilla_core": core})


if __name__ == "__main__":
    unittest.main()


class ReferenceCoreTests(unittest.TestCase):
    def test_only_variants_that_fit_under_the_reference_are_trimmed(self) -> None:
        # Owner ruling 2026-09-27, option 2: an over-budget variant that is over on the reference game too was
        # authored that way and is left alone.
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, weapons=30, caps=10, vents=10, mods=["big_mod", "small_mod"])  # 63 vs 50 on "RC8"
            old = root / "old"
            import shutil
            shutil.copytree(core, old)
            (old / "data" / "hullmods" / "hull_mods.csv").write_text(
                "name,id,cost_frigate,cost_dest,cost_cruiser,cost_capital\nBig,big_mod,1,1,1,1\nSmall,small_mod,1,1,1,1\n", encoding="utf-8")  # 52: fits
            fits_there = compute_fix(mod, "variant-op-over-budget", {"vanilla_core": core, "reference_core": old})
            (old / "data" / "hullmods" / "hull_mods.csv").write_text(
                "name,id,cost_frigate,cost_dest,cost_cruiser,cost_capital\nBig,big_mod,1,1,20,1\nSmall,small_mod,1,1,20,1\n", encoding="utf-8")  # over there too
            with self.assertRaises(FixerError):
                compute_fix(mod, "variant-op-over-budget", {"vanilla_core": core, "reference_core": old})
        self.assertEqual(len(fits_there.changes), 1)
