"""ROADMAP 77.17b: the campaign-perf log lines and their run-record summary."""
from __future__ import annotations

import unittest

from bridgeforge.campaign_perf import campaign_perf_summary, parse_campaign_perf
from tests.support import resolved_temp_dir

_DAY = ("9 [t] INFO  x - BF-PROBE|0.2.27|campaign-perf|{status}|day={day}|frames={frames},mean_ms={mean},p95_ms={p95},max_ms={mx},"
        "gaps=0,fleets_here={here},fleets_busiest={busy},busiest={loc}\n")


def _day(status: str, day: int, frames: int, mean: str, p95: str, mx: str, here: int, busy: int, loc: str) -> str:
    return _DAY.format(status=status, day=day, frames=frames, mean=mean, p95=p95, mx=mx, here=here, busy=busy, loc=loc)


class CampaignPerfTests(unittest.TestCase):
    def _log(self, root, text: str):
        log = root / "run.log"
        log.write_text(text, encoding="utf-8")
        return log

    def test_days_are_parsed_in_order_with_numbers(self) -> None:
        with resolved_temp_dir() as root:
            days = parse_campaign_perf(self._log(root, "noise\n" + _day("INFO", 1, 100, "8.00", "12.50", "30.00", 4, 9, "corvus")))
        self.assertEqual(days[0]["day"], 1)
        self.assertEqual((days[0]["p95_ms"], days[0]["frames"], days[0]["busiest"]), (12.5, 100, "corvus"))

    def test_summary_weights_the_mean_and_names_the_worst_day_and_busiest_place(self) -> None:
        with resolved_temp_dir() as root:
            summary = campaign_perf_summary(self._log(
                root,
                _day("INFO", 1, 100, "10.00", "15.00", "30.00", 4, 9, "corvus")
                + _day("INFO", 2, 300, "20.00", "40.00", "90.00", 6, 14, "askonia")))
        self.assertEqual((summary["days"], summary["frames"], summary["mean_ms"]), (2, 400, 17.5))
        self.assertEqual((summary["worst_p95_ms"], summary["worst_p95_day"], summary["max_ms"]), (40.0, 2, 90.0))
        self.assertEqual((summary["max_fleets_busiest"], summary["busiest_location"], summary["max_fleets_here"]), (14, "askonia", 6))
        self.assertEqual(summary["slow_days"], [])

    def test_threshold_flags_slow_days_and_off_flags_none(self) -> None:
        with resolved_temp_dir() as root:
            log = self._log(
                root,
                _day("INFO", 1, 10, "5.00", "15.00", "30.00", 1, 1, "a")
                + _day("INFO", 2, 10, "5.00", "45.00", "90.00", 1, 1, "a")
                + _day("WARN", 3, 10, "5.00", "20.00", "30.00", 1, 1, "a"))
            flagged = campaign_perf_summary(log, slow_p95_ms=40.0)
            off = campaign_perf_summary(log)
        self.assertEqual(flagged["slow_days"], [2, 3])  # day 3 was WARNed by the probe itself
        self.assertEqual(off["slow_days"], [3])

    def test_a_log_without_the_stage_has_no_summary(self) -> None:
        with resolved_temp_dir() as root:
            self.assertIsNone(campaign_perf_summary(self._log(root, "nothing here\n")))


if __name__ == "__main__":
    unittest.main()
