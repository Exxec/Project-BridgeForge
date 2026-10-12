"""ROADMAP item 57: the capacity-overage rules read from the 2026-10-12 live run (RC8-34 to RC8-36)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.capacity_run import CAPACITY_MOD_ID, check_rules, install_capacity_mod, parse_capacity_log
from tests.support import resolved_temp_dir

SAMPLE = Path(__file__).with_name("capacity_sample_log.txt")


class CapacityRuleTests(unittest.TestCase):
    def test_the_recorded_states_obey_the_rules(self) -> None:
        rows = parse_capacity_log(SAMPLE.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(rows), 10)
        self.assertEqual(check_rules(rows), [])

    def test_a_changed_speed_or_cost_is_reported(self) -> None:
        rows = parse_capacity_log(SAMPLE.read_text(encoding="utf-8"))
        over = next(r for r in rows if r["fleet"].startswith("A") and r["state"] == "cargo=1.5")
        over["travelSpeed"] = "160.0"
        over["excessCargoCost"] = "1.0"
        problems = check_rules(rows)
        self.assertTrue(any("speed 160.0" in p for p in problems))
        self.assertTrue(any("cargo excess cost" in p for p in problems))

    def test_start_end_and_save_lines_are_not_states(self) -> None:
        rows = parse_capacity_log("x BF-CAP|START|paused=false\nBF-CAP|SAVE|a=1|b=2\nBF-CAP|END|frames=9\n")
        self.assertEqual(rows, [])


class InstallTests(unittest.TestCase):
    def test_install_copies_the_mod_and_enables_it_once(self) -> None:
        with resolved_temp_dir() as rig:
            (rig / "starsector-core").mkdir()
            (rig / "mods").mkdir()
            (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["a"]}), encoding="utf-8")
            install_capacity_mod(rig)
            install_capacity_mod(rig)
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            self.assertTrue((rig / "mods" / "bf-capacity" / "mod_info.json").is_file())
        self.assertEqual(enabled, ["a", CAPACITY_MOD_ID])

    def test_a_folder_that_is_not_a_rig_is_refused(self) -> None:
        with resolved_temp_dir() as root, self.assertRaises(ValueError):
            install_capacity_mod(root)


if __name__ == "__main__":
    unittest.main()
