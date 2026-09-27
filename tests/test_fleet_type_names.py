"""P15 item 20.15: fleets created with a type their faction has no display name for (Zorg18, 2026-09-27)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FleetTypeNameTests(unittest.TestCase):
    def _scan(self, root: Path, faction: dict) -> list:
        mod, core = root / "mod", root / "core"
        _write(mod / "mod_info.json", '{"id": "zorg"}')
        _write(mod / "src" / "data" / "scripts" / "Spawner.java",
               'class S { void f() { FleetFactoryV3.createEmptyFleet("zorg", "Zeta AI raid", null);\n'
               '  FleetFactoryV3.createEmptyFleet("zorg", "patrolSmall", null); } }')
        _write(mod / "data" / "world" / "factions" / "zorg.faction", json.dumps(faction))
        _write(core / "data" / "world" / "factions" / "default_fleet_type_names.json", '{"patrolSmall": "Patrol"}')
        return [f for f in scan_mod(mod, TargetProfile(), core).findings if f.id == "fleet-type-name-missing"]

    def test_an_unnamed_type_is_reported_and_a_vanilla_default_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            hits = self._scan(Path(directory), {"id": "zorg"})
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].evidence[:2], ["type:Zeta AI raid", "faction:zorg"])
        self.assertEqual(hits[0].file, "data/world/factions/zorg.faction")

    def test_a_named_type_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            hits = self._scan(Path(directory), {"id": "zorg", "fleetTypeNames": {"Zeta AI raid": "Zeta AI Raid"}})
        self.assertEqual(hits, [])


    def test_fixer_adds_title_cased_names_and_keeps_the_file_readable(self) -> None:
        from bridgeforge.fixers import apply_fix, compute_fix
        from bridgeforge.scanner import _load_lenient_json_file

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._scan(root, {"id": "zorg", "color": [1, 2, 3, 255]})
            apply_fix(compute_fix(root / "mod", "fleet-type-name-missing", {"vanilla_core": root / "core"}))
            faction = _load_lenient_json_file(root / "mod" / "data" / "world" / "factions" / "zorg.faction")
            remaining = [f for f in scan_mod(root / "mod", TargetProfile(), root / "core").findings if f.id == "fleet-type-name-missing"]
        self.assertEqual(faction["fleetTypeNames"], {"Zeta AI raid": "Zeta AI Raid"})
        self.assertEqual(faction["color"], [1, 2, 3, 255])
        self.assertEqual(remaining, [])

if __name__ == "__main__":
    unittest.main()
