"""ROADMAP P15 item 20.17: triage the last N sessions of a rolling starsector.log (a player relaunch logs only there)."""
import unittest

from bridgeforge.log_triage import triage_log
from tests.support import resolved_temp_dir

START = "673  [main] INFO  com.fs.starfarer.StarfarerLauncher  - Starting Starsector 0.98a-RC8 launcher"
CRASH = ("100 [Thread-2] ERROR com.fs.starfarer.combat.CombatMain  - java.lang.RuntimeException: Error loading [x.png] resource, not found in [mods]\n"
         "java.lang.RuntimeException: Error loading [x.png] resource, not found in [mods]\n\tat com.fs.util.C.o00000(Unknown Source)")


class LastSessionsTests(unittest.TestCase):
    def test_only_the_last_sessions_are_triaged(self) -> None:
        with resolved_temp_dir() as root:
            log = root / "starsector.log"
            log.write_text("\n".join([START, CRASH, START, "5 [main] INFO  x  - fine", START, "6 [main] INFO  x  - fine"]) + "\n", encoding="utf-8")
            whole = triage_log(log)
            last_two = triage_log(log, last_sessions=2)
            last_three = triage_log(log, last_sessions=3)
        self.assertEqual(whole["counts"]["FATAL"], 1)
        self.assertEqual(last_two["counts"]["FATAL"], 0)
        self.assertEqual(last_two["sessions"], {"requested": 2, "found": 2, "first_line": 5})
        self.assertEqual(last_three["counts"]["FATAL"], 1)


if __name__ == "__main__":
    unittest.main()
