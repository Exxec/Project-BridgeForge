import tempfile
import unittest
from pathlib import Path

from bridgeforge.log_triage import triage_log


def _log_line(millis: int, message: str) -> str:
    return f"{millis} [Thread-2] INFO  com.bridgeforge.probe.ProbeLog  - {message}"


class ProbeLogTriageTests(unittest.TestCase):
    def test_parses_bf_probe_lines_into_probe_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text(
                "\n".join(
                    [
                        _log_line(100, "BF-PROBE|0.1.0|probe|INFO|campaign|START"),
                        _log_line(200, "BF-PROBE|0.1.0|rings-orbits|FAIL|Corvus/ring0|Non-finite orbital period: NaN"),
                        _log_line(300, "BF-PROBE|0.1.0|faction-known-lists|WARN|some_faction|knownShips=0 knownWeapons=3 knownFighters=1"),
                        _log_line(400, "BF-PROBE|0.1.0|planet-specs|OK|Corvus/planet0|type=barren"),
                        _log_line(500, "BF-PROBE|0.1.0|probe|INFO|campaign|END"),
                    ]
                ),
                encoding="utf-8",
            )
            result = triage_log(log)
            probe = result["probe"]
            self.assertEqual(probe["entry_count"], 5)
            self.assertEqual(probe["counts_by_status"]["FAIL"], 1)
            self.assertEqual(probe["counts_by_status"]["WARN"], 1)
            self.assertEqual(probe["counts_by_status"]["OK"], 1)
            self.assertEqual(probe["counts_by_status"]["INFO"], 2)
            self.assertEqual(probe["counts_by_check"]["rings-orbits"], 1)
            self.assertTrue(probe["started"])
            self.assertTrue(probe["ended"])
            flagged_checks = {entry["check"] for entry in probe["flagged"]}
            self.assertEqual(flagged_checks, {"rings-orbits", "faction-known-lists"})

    def test_no_probe_lines_yields_empty_probe_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text(_log_line(100, "Playing music with id [miscallenous_main_menu.ogg]"), encoding="utf-8")
            result = triage_log(log)
            probe = result["probe"]
            self.assertEqual(probe["entry_count"], 0)
            self.assertFalse(probe["started"])
            self.assertFalse(probe["ended"])
            self.assertEqual(probe["flagged"], [])

    def test_probe_line_survives_being_flagged_as_mod_error_level(self) -> None:
        # A probe FAIL is still logged at log4j level INFO by ProbeLog; make sure a probe line
        # never gets misclassified into the FATAL/MOD-ERROR/OTHER buckets meant for ERROR/WARN/FATAL levels.
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text(_log_line(100, "BF-PROBE|0.1.0|submarket-stock|FAIL|market0/open_market|threw"), encoding="utf-8")
            result = triage_log(log)
            self.assertEqual(result["counts"]["OTHER"], 0)
            self.assertEqual(result["counts"]["MOD-ERROR"], 0)
            self.assertEqual(result["probe"]["counts_by_status"]["FAIL"], 1)


if __name__ == "__main__":
    unittest.main()


class MarketStarSystemProbeTests(unittest.TestCase):
    """`market-star-system` (probe 0.2.16, ROADMAP item 58): a market with no star system crashes Nexerelin raid intel."""

    def test_probe_source_emits_the_check_and_the_version_is_current(self) -> None:
        root = Path(__file__).resolve().parents[1] / "probe-mod"
        source = (root / "src/com/bridgeforge/probe/CampaignProbeScript.java").read_text(encoding="utf-8")
        self.assertIn('runCheck("market-star-system"', source)
        self.assertIn("RaidIntel.getETA", source)
        version = (root / "src/com/bridgeforge/probe/ProbeLog.java").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.16"', version)

    def test_a_fail_line_for_a_market_without_a_star_system_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text(
                "\n".join(
                    [
                        _log_line(100, "BF-PROBE|0.2.16|market-star-system|FAIL|station_market|entity station in Hyperspace; MarketAPI.getStarSystem() is null"),
                        _log_line(200, "BF-PROBE|0.2.16|market-star-system|OK|markets|every market has a star system"),
                    ]
                ),
                encoding="utf-8",
            )
            probe = triage_log(log)["probe"]
        self.assertEqual({entry["check"] for entry in probe["flagged"]}, {"market-star-system"})
        self.assertEqual(probe["counts_by_status"]["FAIL"], 1)
