"""Two mods shipping a modified copy of the SAME vanilla script, and whether a shared library can own it.

Real case, 2026-09-22: Xenoargh-Rebal and Better-Deserving-Smods both ship modified copies of ~22
vanilla hullmod scripts at vanilla's own paths. Both land at one path, load order picks a winner,
and the loser's changes vanish silently - a mod-vs-mod conflict, not just duplication.

The resolution depends on whether every colliding mod also declares the class in its own
merge-by-row CSV (the scanner's vanilla-script-shadow-repointable condition). If they all do, one
reconciled implementation can live in a shared library (RevenantLib, per the fold-in policy) with
each mod repointing its own row at it, and nobody shadows vanilla. If one relies purely on path
shadowing, it needs a row first - which is exactly the real Rebal/Better-Deserving-Smods case.
"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.cross_mod import analyze_mod_set
from bridgeforge.models import TargetProfile

SCRIPT = "package data.hullmods;\npublic class BlastDoors {{ int v{}; }}\n"


def _mod(base: Path, name: str, mod_id: str, *, declare: bool, shadow: bool = True, marker: int = 0) -> Path:
    """A mod directory, optionally shadowing vanilla's BlastDoors.java and/or declaring its row."""
    mod = base / name / "working"
    (mod / "data" / "hullmods").mkdir(parents=True, exist_ok=True)
    (mod / "mod_info.json").write_text(
        json.dumps({"id": mod_id, "name": name, "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8"
    )
    if shadow:
        (mod / "data" / "hullmods" / "BlastDoors.java").write_text(SCRIPT.format(marker), encoding="utf-8")
    if declare:
        with (mod / "data" / "hullmods" / "hull_mods.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["name", "id", "script"])
            writer.writerow(["Blast Doors", "blast_doors", "data.hullmods.BlastDoors"])
    return mod


def _core(base: Path) -> Path:
    core = base / "core"
    (core / "data" / "hullmods").mkdir(parents=True, exist_ok=True)
    (core / "data" / "hullmods" / "BlastDoors.java").write_text(SCRIPT.format(99), encoding="utf-8")
    return core


class VanillaScriptShadowCollisionTests(unittest.TestCase):
    def test_two_mods_shadowing_one_vanilla_script_collide(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = _core(base)
            a = _mod(base, "Alpha", "alpha", declare=True, marker=1)
            b = _mod(base, "Beta", "beta", declare=True, marker=2)
            report = analyze_mod_set([a, b], TargetProfile(), None, core)
        self.assertTrue(report["vanilla_script_shadow_collisions_checked"])
        collisions = report["vanilla_script_shadow_collisions"]
        self.assertEqual(len(collisions), 1)
        entry = collisions[0]
        self.assertEqual(entry["path"], "data/hullmods/BlastDoors.java")
        self.assertEqual(entry["owners"], ["alpha", "beta"])

    def test_all_owners_declaring_a_row_means_a_shared_library_can_own_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = _core(base)
            a = _mod(base, "Alpha", "alpha", declare=True, marker=1)
            b = _mod(base, "Beta", "beta", declare=True, marker=2)
            report = analyze_mod_set([a, b], TargetProfile(), None, core)
        entry = report["vanilla_script_shadow_collisions"][0]
        self.assertEqual(entry["resolution"], "REPOINT_TO_SHARED_LIBRARY")
        self.assertEqual(entry["undeclared_owners"], [])
        self.assertEqual(sorted(entry["declared_by"]), ["alpha", "beta"])

    def test_an_owner_with_no_row_needs_one_before_repointing(self) -> None:
        """The real Rebal/Better-Deserving-Smods shape: one declares the row, the other path-shadows only."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = _core(base)
            a = _mod(base, "Alpha", "alpha", declare=True, marker=1)
            b = _mod(base, "Beta", "beta", declare=False, marker=2)
            report = analyze_mod_set([a, b], TargetProfile(), None, core)
        entry = report["vanilla_script_shadow_collisions"][0]
        self.assertEqual(entry["resolution"], "NEEDS_ROW_BEFORE_REPOINTING")
        self.assertEqual(entry["undeclared_owners"], ["beta"])
        self.assertEqual(sorted(entry["declared_by"]), ["alpha"])

    def test_one_mod_shadowing_alone_is_not_a_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = _core(base)
            a = _mod(base, "Alpha", "alpha", declare=True, marker=1)
            b = _mod(base, "Beta", "beta", declare=False, shadow=False)
            report = analyze_mod_set([a, b], TargetProfile(), None, core)
        self.assertEqual(report["vanilla_script_shadow_collisions"], [])

    def test_identically_named_working_dirs_are_still_distinct_owners(self) -> None:
        """Regression: every working copy in this repo is named "working"; keying owners by
        directory name collapsed both mods into one and reported zero collisions."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            core = _core(base)
            a = _mod(base, "Alpha", "alpha", declare=True, marker=1)
            b = _mod(base, "Beta", "beta", declare=True, marker=2)
            self.assertEqual(a.name, b.name)
            report = analyze_mod_set([a, b], TargetProfile(), None, core)
        self.assertEqual(len(report["vanilla_script_shadow_collisions"]), 1)
        self.assertEqual(report["vanilla_script_shadow_collisions"][0]["owners"], ["alpha", "beta"])

    def test_without_a_vanilla_core_the_check_is_skipped_not_silently_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _core(base)
            a = _mod(base, "Alpha", "alpha", declare=True, marker=1)
            b = _mod(base, "Beta", "beta", declare=True, marker=2)
            report = analyze_mod_set([a, b], TargetProfile())
        self.assertFalse(report["vanilla_script_shadow_collisions_checked"])
        self.assertEqual(report["vanilla_script_shadow_collisions"], [])


if __name__ == "__main__":
    unittest.main()
