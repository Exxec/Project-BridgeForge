import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.log_triage import triage_log


def _line(millis: int, level: str, logger: str, message: str) -> str:
    return f"{millis} [Thread-3] {level} {logger}  - {message}"


_NPE = "java.lang.NullPointerException: Cannot invoke \"StarSystemAPI.getHyperspaceAnchor()\" because \"this.system\" is null"


def _error_block(millis: int, frame: str = "RaidIntel.getETA(RaidIntel.java:292)") -> list[str]:
    return [
        _line(millis, "ERROR", "exerelin.campaign.ai.StrategicAI", "Strategic AI: executive module failed to generate actions for faction X"),
        _NPE,
        f"        at com.fs.starfarer.api.impl.campaign.intel.raid.{frame} ~[starfarer.api.jar:?]",
        "        at exerelin.campaign.intel.fleets.OffensiveFleetIntel.addETABullet(OffensiveFleetIntel.java:465) ~[ExerelinCore.jar:?]",
        "",
    ]


class CaughtExceptionTests(unittest.TestCase):
    def _triage(self, lines: list[str]) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text("\n".join(lines), encoding="utf-8")
            return triage_log(log)

    def test_a_logged_but_survived_exception_is_reported_and_grouped(self) -> None:
        lines = [*_error_block(100), *_error_block(200), *_error_block(300, "RaidIntel.getOther(RaidIntel.java:10)")]
        result = self._triage(lines)
        caught = result["caught_exceptions"]
        self.assertEqual(caught["total_events"], 3)
        self.assertEqual(caught["distinct"], 2)
        top = caught["groups"][0]
        self.assertEqual(top["exception"], "java.lang.NullPointerException")
        self.assertEqual(top["count"], 2)
        self.assertIn("RaidIntel.getETA", top["first_frame"])
        self.assertEqual(result["counts"]["FATAL"], 0)          # it never crashed: that is the point

    def test_an_error_without_an_exception_is_not_counted(self) -> None:
        result = self._triage([_line(100, "ERROR", "lunalib.lunaSettings.LunaSettings", "LunaSettings: Could not find mod IndEvo")])
        self.assertEqual(result["caught_exceptions"], {"total_events": 0, "distinct": 0, "groups": []})

    def test_the_cli_summary_lists_the_group(self) -> None:
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text("\n".join(_error_block(100)), encoding="utf-8")
            done = subprocess.run([sys.executable, "-m", "bridgeforge", "log-triage", str(log)], capture_output=True, text=True, check=False)
        self.assertIn("Caught exceptions (logged, game carried on): 1 event(s), 1 distinct", done.stdout)
        self.assertIn("x1 java.lang.NullPointerException", done.stdout)
        json.dumps(done.stdout)


if __name__ == "__main__":
    unittest.main()
