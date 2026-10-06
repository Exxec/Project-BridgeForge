import tempfile
import unittest
from pathlib import Path

from bridgeforge.soak_report import soak_report


def _line(millis: int, message: str, level: str = "INFO", logger: str = "com.bridgeforge.probe.ProbeLog") -> str:
    return f"{millis} [Thread-2] {level} {logger}  - {message}"


def _day(millis: int, days: float) -> str:
    return _line(millis, f"BF-PROBE|0.2.17|campaign-day|INFO|clock|daysSinceStart={days}")


_NPE_BLOCK = [
    _line(500, "Strategic AI: executive module failed", level="ERROR", logger="exerelin.campaign.ai.StrategicAI"),
    "java.lang.NullPointerException: x",
    "        at com.fs.starfarer.api.impl.campaign.intel.raid.RaidIntel.getETA(RaidIntel.java:292) ~[starfarer.api.jar:?]",
    "",
]


class SoakReportTests(unittest.TestCase):
    def _report(self, lines: list[str], days: float = 60) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text("\n".join(lines), encoding="utf-8")
            return soak_report(log, days)

    def test_enough_days_and_nothing_logged_is_a_pass(self) -> None:
        result = self._report([_day(100, 1.0), _day(200, 31.0), _day(300, 66.0)])
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["campaign_days_covered"], 66.0)

    def test_too_few_days_is_incomplete(self) -> None:
        result = self._report([_day(100, 1.0), _day(200, 31.0)])
        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("31 campaign days of the 60", result["reason"])

    def test_no_heartbeat_is_incomplete_not_a_pass(self) -> None:
        result = self._report([_line(100, "Playing music with id [miscallenous_main_menu.ogg]")])
        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("no campaign-day heartbeat", result["reason"])

    def test_a_caught_exception_over_enough_days_needs_attention(self) -> None:
        result = self._report([_day(100, 70.0), *_NPE_BLOCK])
        self.assertEqual(result["verdict"], "ATTENTION")
        self.assertIn("1 caught exception(s), 1 distinct", result["reason"])

    def test_a_probe_fail_needs_attention(self) -> None:
        fail = _line(150, "BF-PROBE|0.2.17|market-star-system|FAIL|m1|entity e in Hyperspace; MarketAPI.getStarSystem() is null")
        result = self._report([_day(100, 70.0), fail])
        self.assertEqual(result["verdict"], "ATTENTION")
        self.assertIn("1 probe FAIL line(s)", result["reason"])

    def test_a_non_positive_day_count_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                soak_report(log, 0)


if __name__ == "__main__":
    unittest.main()
