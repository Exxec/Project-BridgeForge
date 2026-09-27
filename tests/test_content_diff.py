from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.content_diff import ContentDiffError, annotate_removed_content, diff_content
from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _core(root: Path, weapons: dict[str, str], hullmods: dict[str, str], extra_variant: str | None = None) -> Path:
    """A stand-in starsector-core: just the tables the scanner and content-diff read."""
    core = root
    _write(core / "data/weapons/weapon_data.csv", "name,id\n" + "".join(f"{name},{ident}\n" for ident, name in weapons.items()))
    _write(core / "data/hullmods/hull_mods.csv", "name,id\n" + "".join(f"{name},{ident}\n" for ident, name in hullmods.items()))
    _write(core / "data/hulls/wing_data.csv", "id\ntalon_wing\n")
    _write(core / "data/hulls/ship_data.csv", "name,id\nWolf,wolf\n")
    _write(core / "data/hulls/wolf.ship", '{"hullId":"wolf","hullSize":"FRIGATE"}')
    _write(core / "data/shipsystems/ship_systems.csv", "name,id\nBurn Drive,burndrive\n")
    if extra_variant:
        _write(core / f"data/variants/{extra_variant}.variant", json.dumps({"hullId": "wolf", "variantId": extra_variant}))
    return core


def _cores(root: Path) -> tuple[Path, Path]:
    reference = _core(root / "ref", {"oldgun": "Old Gun", "lightmg": "Light MG"}, {"formshield": "Form Shield", "heavyarmor": "Heavy Armor"}, "wolf_Old")
    rc8 = _core(root / "rc8", {"oldgun_mk2": "Old Gun", "lightmg": "Light MG", "brandnew": "Brand New"}, {"heavyarmor": "Heavy Armor"})
    return reference, rc8


class ContentDiffTests(unittest.TestCase):
    def test_removed_ids_with_same_named_successor_candidates(self):
        with resolved_temp_dir() as root:
            result = diff_content(*_cores(root))
        self.assertEqual(result["removed"]["weapon"], [{"id": "oldgun", "name": "Old Gun", "same_name_in_rc8": ["oldgun_mk2"]}])
        self.assertEqual(result["removed"]["hullmod"], [{"id": "formshield", "name": "Form Shield", "same_name_in_rc8": []}])
        self.assertEqual(result["removed"]["variant"], [{"id": "wolf_Old", "same_name_in_rc8": []}])
        self.assertNotIn("hull", result["removed"])
        self.assertEqual(result["counts"]["weapon"], {"reference": 2, "rc8": 3, "removed": 1, "added": 2})

    def test_scan_annotation_names_only_ids_vanilla_removed(self):
        with resolved_temp_dir() as root:
            reference, rc8 = _cores(root)
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(mod / "data/variants/wolf_Mod.variant", json.dumps({
                "hullId": "wolf", "variantId": "wolf_Mod", "hullMods": ["formshield", "vayra_thing"],
                "weaponGroups": [{"weapons": {"WS 001": "oldgun", "WS 002": "lightmg"}}]}))
            result = scan_mod(mod, TargetProfile("0.98a-RC8", 17), rc8)
            self.assertIn("content-reference-unresolved", [f.id for f in result.findings])
            self.assertEqual(annotate_removed_content(result, diff_content(reference, rc8)), 2)
        finding = next(f for f in result.findings if f.id == "content-reference-removed-in-vanilla")
        self.assertEqual(finding.classification, "MANUAL")
        self.assertEqual(finding.evidence, [
            "hullmod:formshield (1 file(s)) removed from vanilla; no same-named RC8 id",
            "weapon:oldgun (1 file(s)) removed from vanilla; same name in RC8: oldgun_mk2",
        ])  # vayra_thing stays a plain unresolved reference: the older vanilla never had it

    def test_nothing_to_annotate_adds_no_finding(self):
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            result = scan_mod(mod, TargetProfile("0.98a-RC8", 17), None)
            self.assertEqual(annotate_removed_content(result, {"removed": {"weapon": [{"id": "x"}]}}), 0)
        self.assertNotIn("content-reference-removed-in-vanilla", [f.id for f in result.findings])

    def test_cli_catalogue_round_trip_into_scan(self):
        with resolved_temp_dir() as root:
            reference, rc8 = _cores(root)
            catalogue = root / "state" / "removed.json"
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(mod / "data/variants/wolf_Mod.variant", json.dumps({"hullId": "wolf", "variantId": "wolf_Mod", "hullMods": ["formshield"]}))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["content-diff", str(reference), str(rc8), "--output", str(catalogue)]), 0)
                main(["scan", str(mod), "--vanilla-core", str(rc8), "--removed-content", str(catalogue), "--output", str(root / "report")])
            report = json.loads((root / "report" / "bridgeforge.compat.json").read_text(encoding="utf-8"))
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["content-diff", str(root / "nope"), str(rc8)]), 2)
        self.assertIn("  - weapon:oldgun (Old Gun) -> same name in RC8: oldgun_mk2", out.getvalue())
        self.assertIn("content-reference-removed-in-vanilla", [f["id"] for f in report["findings"]])

    def test_core_without_data_is_refused(self):
        with resolved_temp_dir() as root:
            with self.assertRaises(ContentDiffError):
                diff_content(root, root)


if __name__ == "__main__":
    unittest.main()
