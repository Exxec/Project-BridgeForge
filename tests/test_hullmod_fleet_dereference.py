"""hullmod-fleet-dereference-unguarded: Epta Consortium's refunder hull mods crashed on opening a market (crash report 2026-10-13)."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.scan.scan_combat import unguarded_fleet_dereference_lines
from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

UNGUARDED = """package data.hullmods;
public class Refunder extends BaseHullMod {
    @Override
    public void advanceInCampaign(FleetMemberAPI member, float amount) {
        if (!member.getVariant().hasHullMod("x")) {
            if (member.getFleetData().getFleet().equals(Global.getSector().getPlayerFleet())) {
                refund();
            }
        }
    }
}
"""
GUARDED = UNGUARDED.replace("if (member.getFleetData().getFleet().equals(",
                            "if (member.getFleetData() != null && member.getFleetData().getFleet() != null && member.getFleetData().getFleet().equals(")


def _mod(root: Path, source: str) -> Path:
    mod = root / "mod"
    (mod / "data" / "hullmods").mkdir(parents=True)
    (mod / "mod_info.json").write_text('{"id":"m","name":"M","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
    (mod / "data" / "hullmods" / "Refunder.java").write_text(source, encoding="utf-8")
    return mod


class FleetDereferenceTests(unittest.TestCase):
    def test_the_line_of_an_unguarded_call_is_found_and_a_guarded_one_is_not(self) -> None:
        body = UNGUARDED.split("advanceInCampaign(FleetMemberAPI member, float amount) {", 1)[1]
        self.assertEqual(unguarded_fleet_dereference_lines(body), [3])
        self.assertEqual(unguarded_fleet_dereference_lines(GUARDED.split("float amount) {", 1)[1]), [])

    def test_scan_flags_the_hull_mod_by_id_and_stays_quiet_when_guarded(self) -> None:
        with resolved_temp_dir() as root:
            flagged = [f for f in scan_mod(_mod(root / "a", UNGUARDED)).findings if f.id == "hullmod-fleet-dereference-unguarded"]
            quiet = [f for f in scan_mod(_mod(root / "b", GUARDED)).findings if f.id == "hullmod-fleet-dereference-unguarded"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].classification, "REVIEW")
        self.assertEqual(quiet, [])


if __name__ == "__main__":
    unittest.main()
