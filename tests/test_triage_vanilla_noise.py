"""Live runs FLX-R4 / SK13-1e: vanilla RC8's own weapon_data.csv logs a harmless WARN every run."""

import tempfile
import unittest
from pathlib import Path

from bridgeforge.log_triage import triage_log

LOG = (
    "4174 [Thread-2] WARN  com.fs.starfarer.loading.WeaponSpreadsheetLoader  - "
    "Weapon [lightmortar_fighter] from weapon_data.csv not found in store\n"
    "4174 [Thread-2] WARN  com.fs.starfarer.loading.WeaponSpreadsheetLoader  - "
    "Weapon [my_mod_gun] from weapon_data.csv not found in store\n"
)


class VanillaNoiseTriageTests(unittest.TestCase):
    def test_vanilla_lightmortar_fighter_row_is_known_noise_but_mod_weapons_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(LOG, encoding="utf-8")
            result = triage_log(path)
        self.assertEqual(result["counts"]["KNOWN-NOISE"], 1)
        self.assertEqual(result["counts"]["OTHER"], 1)
        self.assertIn("my_mod_gun", result["other"][0]["message"])


if __name__ == "__main__":
    unittest.main()
