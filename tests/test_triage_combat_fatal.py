"""Live run SK13-1: an exception escaping the combat loop is a Fatal dialog, so triage must say FATAL."""

import tempfile
import unittest
from pathlib import Path

from bridgeforge.log_triage import triage_log

# The real SK13-1 lines (SEEKER's ART_thrusterRotation on a hull with no ship system).
LOG = (
    '130014 [Thread-2] ERROR com.fs.starfarer.combat.CombatMain  - java.lang.NullPointerException: Cannot invoke '
    '"com.fs.starfarer.api.combat.ShipSystemAPI.isActive()" because the return value of '
    '"com.fs.starfarer.api.combat.ShipAPI.getSystem()" is null\n'
    'java.lang.NullPointerException: Cannot invoke "com.fs.starfarer.api.combat.ShipSystemAPI.isActive()" because the '
    'return value of "com.fs.starfarer.api.combat.ShipAPI.getSystem()" is null\n'
    "\tat data.scripts.weapons.ART_thrusterRotation.advance(ART_thrusterRotation.java:99)\n"
    "\tat com.fs.starfarer.combat.entities.Ship.advance(Unknown Source)\n"
    "\tat com.fs.starfarer.combat.CombatMain.main(Unknown Source)\n"
)


class CombatFatalTriageTests(unittest.TestCase):
    def test_combat_loop_exception_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(LOG, encoding="utf-8")
            result = triage_log(path)
        self.assertEqual(result["counts"]["FATAL"], 1)
        self.assertEqual(result["fatal"][0]["matched_rule"], "Combat loop exception")


if __name__ == "__main__":
    unittest.main()
