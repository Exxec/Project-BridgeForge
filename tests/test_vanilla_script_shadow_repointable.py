"""A vanilla-path .java shadow the mod could repoint through its own CSV row instead.

Real case, 2026-09-22 (designing Xenoargh-Rebal's rebuild): all 50 of Rebal's vanilla-path `.java`
shadows (47 hullmod scripts + 3 shipsystem stats scripts) are named by rows in Rebal's *own*
`hull_mods.csv` / `.system` files. Those CSVs merge by row id, so renaming the class and repointing
the row gives identical behaviour with no shadow at all - and survives the next vanilla update
instead of silently reverting it.
"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod


def _dirs(root: Path, *relatives: str) -> None:
    for relative in relatives:
        (root / relative).mkdir(parents=True, exist_ok=True)


def _fixture(base: Path, *, declare: bool, vanilla_has_script: bool = True) -> Path:
    """A mod shadowing vanilla's data/hullmods/BlastDoors.java, optionally declaring the row."""
    mod, core = base / "mod", base / "core"
    _dirs(mod, "data/hullmods")
    _dirs(core, "data/hullmods")
    (mod / "mod_info.json").write_text(
        json.dumps({"id": "reb", "name": "Reb", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8"
    )
    (mod / "data" / "hullmods" / "BlastDoors.java").write_text(
        "package data.hullmods;\npublic class BlastDoors {}\n", encoding="utf-8"
    )
    if vanilla_has_script:
        (core / "data" / "hullmods" / "BlastDoors.java").write_text(
            "package data.hullmods;\npublic class BlastDoors { int vanilla; }\n", encoding="utf-8"
        )
    if declare:
        with (mod / "data" / "hullmods" / "hull_mods.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["name", "id", "script"])
            writer.writerow(["Blast Doors", "blast_doors", "data.hullmods.BlastDoors"])
    return core


def _ids(result, finding_id: str) -> list:
    return [f for f in result.findings if f.id == finding_id]


class VanillaScriptShadowRepointableTests(unittest.TestCase):
    def test_shadow_named_by_the_mods_own_csv_row_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = _fixture(base, declare=True)
            result = scan_mod(base / "mod", TargetProfile(), core)
        findings = _ids(result, "vanilla-script-shadow-repointable")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].file, "data/hullmods/BlastDoors.java")
        self.assertIn("declared-in:data/hullmods/hull_mods.csv id=blast_doors", findings[0].evidence)

    def test_shadow_the_mod_does_not_declare_is_not_repointable(self) -> None:
        """No row naming the class means there is nothing to repoint; vanilla-path-shadowing still covers it."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = _fixture(base, declare=False)
            result = scan_mod(base / "mod", TargetProfile(), core)
        self.assertEqual(_ids(result, "vanilla-script-shadow-repointable"), [])

    def test_a_script_with_no_vanilla_counterpart_is_not_flagged(self) -> None:
        """The mod's own new hullmod is not a shadow at all, even though its row names it."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = _fixture(base, declare=True, vanilla_has_script=False)
            result = scan_mod(base / "mod", TargetProfile(), core)
        self.assertEqual(_ids(result, "vanilla-script-shadow-repointable"), [])

    def test_shipsystem_stats_script_key_also_counts_as_declared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mod, core = base / "mod", base / "core"
            _dirs(mod, "data/shipsystems/scripts", "data/shipsystems")
            _dirs(core, "data/shipsystems/scripts")
            (mod / "mod_info.json").write_text(
                json.dumps({"id": "reb", "name": "Reb", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8"
            )
            (mod / "data" / "shipsystems" / "scripts" / "BurnDriveStats.java").write_text(
                "package data.shipsystems.scripts;\npublic class BurnDriveStats {}\n", encoding="utf-8"
            )
            (core / "data" / "shipsystems" / "scripts" / "BurnDriveStats.java").write_text(
                "package data.shipsystems.scripts;\npublic class BurnDriveStats { int v; }\n", encoding="utf-8"
            )
            (mod / "data" / "shipsystems" / "burndrive.system").write_text(
                '{"id":"burndrive", "statsScript":"data.shipsystems.scripts.BurnDriveStats"}', encoding="utf-8"
            )
            result = scan_mod(mod, TargetProfile(), core)
        findings = _ids(result, "vanilla-script-shadow-repointable")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].file, "data/shipsystems/scripts/BurnDriveStats.java")

    def test_without_a_vanilla_core_the_check_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _fixture(base, declare=True)
            result = scan_mod(base / "mod", TargetProfile(), None)
        self.assertEqual(_ids(result, "vanilla-script-shadow-repointable"), [])


if __name__ == "__main__":
    unittest.main()
