"""hulk-death-effect-repeats (RC8-27): SEEKER's Liquid Skin re-ran its death effect on every frame of the wreck."""
from __future__ import annotations

import unittest

from bridgeforge.fixers import FixerError, _fix_hulk_death_effect_repeats
from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

UNGUARDED = """package data.hullmods;
public class Skin extends BaseHullMod {
    public void advanceInCombat(ShipAPI ship, float amount) {
        if (ship.isHulk()) {
            this.DEATH(ship);
        }
    }
    void DEATH(ShipAPI ship) {
        Global.getCombatEngine().getFleetManager(0).spawnShipOrWing("x_debris", ship.getLocation(), 0f);
    }
}
"""
GUARDED_ALREADY = UNGUARDED.replace("if (ship.isHulk()) {", "if (ship.isHulk() && !ship.getCustomData().containsKey(\"k\")) {")
NO_SPAWN = UNGUARDED.replace("spawnShipOrWing", "getHullLevel")


def _hits(text: str):
    with resolved_temp_dir() as root:
        (root / "mod_info.json").write_text('{"id":"demo","version":"1"}', encoding="utf-8")
        path = root / "data" / "hullmods" / "Skin.java"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        return [f for f in scan_mod(root).findings if f.id == "hulk-death-effect-repeats"]


class ScanTests(unittest.TestCase):
    def test_a_wreck_check_that_spawns_through_a_helper_is_flagged(self) -> None:
        hits = _hits(UNGUARDED)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].evidence, ["wreck-check:ship.isHulk()"])

    def test_an_already_guarded_check_or_one_that_spawns_nothing_is_quiet(self) -> None:
        self.assertEqual(_hits(GUARDED_ALREADY), [])
        self.assertEqual(_hits(NO_SPAWN), [])


class FixerTests(unittest.TestCase):
    def test_the_check_becomes_once_per_ship(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "data" / "hullmods" / "Skin.java"
            path.parent.mkdir(parents=True)
            path.write_text(UNGUARDED, encoding="utf-8")
            finding = {"id": "hulk-death-effect-repeats", "file": "data/hullmods/Skin.java", "evidence": []}
            text = _fix_hulk_death_effect_repeats(root, {"scan_findings": [finding]})[0].after.decode("utf-8")
        self.assertIn('if (ship.isHulk() && bfFirstDeath(ship, "Skin_deathDone")) {', text)
        self.assertIn("private static boolean bfFirstDeath(", text)
        self.assertIn("ship.setCustomData(key, Boolean.TRUE)", text)

    def test_jar_classes_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            finding = {"id": "hulk-death-effect-repeats", "file": "jar/x.jar!data/hullmods/Skin.class", "evidence": []}
            with self.assertRaises(FixerError):
                _fix_hulk_death_effect_repeats(root, {"scan_findings": [finding]})


if __name__ == "__main__":
    unittest.main()
