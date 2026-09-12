from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.build_tag import record_build_manifest
from bridgeforge.test_plan import TestPlanError, plan_tests


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_mod(root: Path) -> None:
    _write(root / "mod_info.json", '{"id":"fixture_mod","name":"Fixture Mod","version":"1.0"}')
    _write(root / "data" / "world" / "factions" / "fixture.faction", '{"id":"fixture_faction","knownShips":[]}')
    _write(root / "data" / "hullmods" / "hull_mods.csv", "id\nfixture_hm\n")
    _write(root / "data" / "hulls" / "fixture.variant", "{}")


LIVE_TEST_FIXTURE = """# Live test instructions

## 1. Fixture Mod

| ID | Step | Expected |
|---|---|---|
| FX-1 | Baseline boot | Reaches main menu |
| FX-2 | Dock at a market and trade | Ships/weapons stocked |
| FX-3 | Install a hullmod in refit | Applies correctly |
"""


class TestPlanTests(unittest.TestCase):
    def _manifests_dir_with_snapshot(self, root: Path, tmp: str) -> Path:
        manifests_dir = Path(tmp) / "manifests"
        record_build_manifest(root, 1, manifests_dir=manifests_dir)
        return manifests_dir

    def test_no_changes_yields_no_features(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as tmp:
            root = Path(mod_dir)
            _fixture_mod(root)
            manifests_dir = self._manifests_dir_with_snapshot(root, tmp)
            plan = plan_tests(root, "r1", manifests_dir=manifests_dir, live_test_instructions=Path(tmp) / "missing.md")
            self.assertEqual(plan["changed_file_count"], 0)
            self.assertEqual(plan["features"], [])
            self.assertEqual(plan["probe_assertions"], [])

    def test_faction_change_maps_to_markets_and_fleets(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as tmp:
            root = Path(mod_dir)
            _fixture_mod(root)
            manifests_dir = self._manifests_dir_with_snapshot(root, tmp)
            _write(root / "data" / "world" / "factions" / "fixture.faction", '{"id":"fixture_faction","knownShips":["a"]}')
            live_test_path = Path(tmp) / "LIVE_TEST_INSTRUCTIONS.md"
            live_test_path.write_text(LIVE_TEST_FIXTURE, encoding="utf-8")

            plan = plan_tests(root, "r1", manifests_dir=manifests_dir, live_test_instructions=live_test_path)

            self.assertIn("data/world/factions/fixture.faction", plan["changed_files"]["modified"])
            self.assertEqual(plan["features"], ["fleets", "markets"])
            self.assertTrue(any("market" in a.lower() for a in plan["probe_assertions"]))
            self.assertIn("FX-2", plan["live_test_ids"])  # "market" keyword row
            self.assertNotIn("FX-3", plan["live_test_ids"])  # refit-only row, unrelated

    def test_jar_change_selects_every_live_test_id(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as tmp:
            root = Path(mod_dir)
            _fixture_mod(root)
            manifests_dir = self._manifests_dir_with_snapshot(root, tmp)
            _write(root / "jars" / "fixture.jar", "not-a-real-jar-but-a-tracked-file")
            live_test_path = Path(tmp) / "LIVE_TEST_INSTRUCTIONS.md"
            live_test_path.write_text(LIVE_TEST_FIXTURE, encoding="utf-8")

            plan = plan_tests(root, "r1", manifests_dir=manifests_dir, live_test_instructions=live_test_path)

            self.assertIn("scripted", plan["features"])
            self.assertEqual(set(plan["live_test_ids"]), {"FX-1", "FX-2", "FX-3"})

    def test_hullmod_change_maps_to_refit(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as tmp:
            root = Path(mod_dir)
            _fixture_mod(root)
            manifests_dir = self._manifests_dir_with_snapshot(root, tmp)
            _write(root / "data" / "hullmods" / "hull_mods.csv", "id\nfixture_hm\nsecond_hm\n")

            plan = plan_tests(root, "r1", manifests_dir=manifests_dir, live_test_instructions=Path(tmp) / "missing.md")
            self.assertEqual(plan["features"], ["refit"])

    def test_unknown_since_tag_raises(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as tmp:
            root = Path(mod_dir)
            _fixture_mod(root)
            with self.assertRaises(TestPlanError):
                plan_tests(root, "r99", manifests_dir=Path(tmp), live_test_instructions=Path(tmp) / "missing.md")

    def test_no_matching_live_test_section_degrades_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as tmp:
            root = Path(mod_dir)
            _write(root / "mod_info.json", '{"id":"unlisted_mod","name":"Unlisted Mod","version":"1.0"}')
            manifests_dir = self._manifests_dir_with_snapshot(root, tmp)
            _write(root / "data" / "hullmods" / "hull_mods.csv", "id\nx\n")
            live_test_path = Path(tmp) / "LIVE_TEST_INSTRUCTIONS.md"
            live_test_path.write_text(LIVE_TEST_FIXTURE, encoding="utf-8")

            plan = plan_tests(root, "r1", manifests_dir=manifests_dir, live_test_instructions=live_test_path)
            self.assertIsNone(plan["live_test_section"])
            self.assertEqual(plan["live_test_ids"], [])
            self.assertEqual(plan["features"], ["refit"])  # probe assertions still work without the doc


if __name__ == "__main__":
    unittest.main()
