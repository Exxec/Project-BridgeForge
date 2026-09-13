"""Live bug PRB-FIGHTER-01: fighter hulls with blank ship_data hints were deployed as ships."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.probe_config import _hull_inventory


def _mod(root: Path) -> Path:
    hulls = root / "data" / "hulls"
    hulls.mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "fixture"}), encoding="utf-8")
    (hulls / "ship_data.csv").write_text(
        "name,id,designation,system id,hints\n"
        "Cruiser,fx_cruiser,,,\n"
        "Bomber,fx_bomber,,,\n"          # blank hints: only the .ship says it's a fighter (Exigency's case)
        "Old Wing,fx_hinted,,,FIGHTER\n"
        "Pod,fx_module,,,MODULE\n",
        encoding="utf-8",
    )
    for hull_id, size in (("fx_cruiser", "CRUISER"), ("fx_bomber", "FIGHTER"), ("fx_hinted", "FIGHTER"), ("fx_module", "DEFAULT")):
        # File name deliberately differs from the hullId for one hull: lookups go by the declared hullId.
        name = "renamed_bomber.ship" if hull_id == "fx_bomber" else f"{hull_id}.ship"
        (hulls / name).write_text(json.dumps({"hullId": hull_id, "hullSize": size}), encoding="utf-8")
    return root


class ProbeHullInventoryTests(unittest.TestCase):
    def test_fighters_are_excluded_by_hull_size_even_with_blank_hints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(_hull_inventory(_mod(Path(directory))), ["fx_cruiser"])

    def test_wreck_pieces_are_excluded_by_designation(self) -> None:
        # PRB-DEBRIS-01: SEEKER's "Debris" hulks were deployed as ships and crowded real hulls out.
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory))
            csv_path = root / "data" / "hulls" / "ship_data.csv"
            csv_path.write_text(csv_path.read_text(encoding="utf-8") + "Ubique debris,fx_cruiser_hulkA,Debris,,\n", encoding="utf-8")
            (root / "data" / "hulls" / "fx_cruiser_hulkA.ship").write_text(json.dumps({"hullId": "fx_cruiser_hulkA", "hullSize": "CRUISER"}), encoding="utf-8")
            self.assertEqual(_hull_inventory(root), ["fx_cruiser"])


if __name__ == "__main__":
    unittest.main()
