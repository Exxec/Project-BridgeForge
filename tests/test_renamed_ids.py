"""`renamed-ids` (ROADMAP 34.24): renamed ids across two copies of a mod, from the Xhan and Traverser cases."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.renamed_ids import find_renamed
from tests.support import resolved_temp_dir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RenamedIdsTests(unittest.TestCase):
    def test_same_name_and_description_is_a_rename(self) -> None:
        # Xhan Empire 3.0.1: XHAN_targeting_mast became XHAN_TargetingMast.
        with resolved_temp_dir() as root:
            _write(root / "old/data/hullmods/hull_mods.csv", "name,id,desc\nXhanTech Targeting Mast,XHAN_targeting_mast,Extends range by %s.\n")
            _write(root / "new/data/hullmods/hull_mods.csv", "name,id,desc\nXhanTech Targeting Mast,XHAN_TargetingMast,Extends range by %s.\n"
                   "XhanTech Armor,XHAN_armor,Armor.\n")
            result = find_renamed(root / "old", root / "new", ["hullmod:XHAN_targeting_mast", "hullmod:XHAN_armor"])
        self.assertEqual((result[0]["verdict"], result[0]["renamed_to"]), ("RENAMED", ["XHAN_TargetingMast"]))
        self.assertEqual(result[1]["verdict"], "STILL_DEFINED")

    def test_a_redesign_is_only_similar_and_old_tables_count(self) -> None:
        # Traverser: the Scholar survives only in ship_data_old.csv; the Cold Sky Scholar is a different design.
        with resolved_temp_dir() as root:
            _write(root / "old/data/hulls/ship_data.csv", "name,id,designation\n")
            _write(root / "old/data/hulls/ship_data_old.csv", "name,id,designation\nTraverser Scholar,TDB_cyxz,Phase Cruiser\n")
            _write(root / "new/data/hulls/ship_data.csv", "name,id,designation\nCold Sky Scholar,TDB_XZ,Unmanned Phase Cruiser\n")
            result = find_renamed(root / "old", root / "new", ["hull:TDB_cyxz", "hull:nowhere"])
        self.assertEqual(result[0]["verdict"], "SIMILAR")
        self.assertEqual(result[0]["similar"][0]["id"], "TDB_XZ")
        self.assertEqual(result[1]["verdict"], "NOT_IN_OLD_COPY")


if __name__ == "__main__":
    unittest.main()
