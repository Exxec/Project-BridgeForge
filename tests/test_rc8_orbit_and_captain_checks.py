from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


class OrbitPeriodHazardTests(unittest.TestCase):
    def test_literal_zero_orbit_days_on_set_circular_orbit_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "Spawner.java",
                "class Spawner { void go(SectorEntityToken ship, SectorEntityToken focus) { "
                "ship.setCircularOrbit(focus, 0f, 3000f, 0f); } }",
            )
            result = scan_mod(root)
            findings = _findings(result, "orbit-period-zero")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")
            self.assertEqual(findings[0].severity, "critical")
            self.assertIn("call:setCircularOrbit", findings[0].evidence)
            self.assertIn("arg-index:3", findings[0].evidence)

    def test_literal_zero_orbit_days_on_add_ring_band_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "Ring.java",
                "class Ring { void go(StarSystemAPI system) { "
                "system.addRingBand(system.getCenter(), \"misc\", \"rings_dust0\", 256f, 1, Color.gray, "
                "128f, 3000f, 0.0f, Terrain.RING, \"x\"); } }",
            )
            result = scan_mod(root)
            findings = _findings(result, "orbit-period-zero")
            self.assertEqual(len(findings), 1)
            self.assertIn("call:addRingBand", findings[0].evidence)
            self.assertIn("arg-index:8", findings[0].evidence)

    def test_unguarded_division_derived_orbit_days_is_review(self) -> None:
        # Real case: Arkgneisis SpawnChampionRing -> float orbitTime = orbitRadius / 20f;
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "Champion.java",
                "class Champion { static void spawn(StarSystemAPI system, float orbitRadius) { "
                "float orbitTime = orbitRadius / 20f; "
                "system.addRingBand(system.getCenter(), \"misc\", \"rings_dust0\", 256f, 1, Color.gray, "
                "128f, orbitRadius, orbitTime, Terrain.RING, \"x\"); } }",
            )
            result = scan_mod(root)
            findings = _findings(result, "orbit-period-computed-unguarded")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertEqual(findings[0].severity, "medium")
            self.assertIn("call:addRingBand", findings[0].evidence)

    def test_guarded_division_derived_orbit_days_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "Champion.java",
                "class Champion { static void spawn(StarSystemAPI system, float orbitRadius) { "
                "if (Float.isNaN(orbitRadius) || orbitRadius <= 0f) { orbitRadius = 3000f; } "
                "float orbitTime = Math.max(orbitRadius / 20f, 30f); "
                "system.addRingBand(system.getCenter(), \"misc\", \"rings_dust0\", 256f, 1, Color.gray, "
                "128f, orbitRadius, orbitTime, Terrain.RING, \"x\"); } }",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "orbit-period-computed-unguarded"), [])
            self.assertEqual(_findings(result, "orbit-period-zero"), [])

    def test_nonzero_literal_orbit_days_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "Spawner.java",
                "class Spawner { void go(SectorEntityToken ship, SectorEntityToken focus) { "
                "ship.setCircularOrbit(focus, 0f, 3000f, 45f); } }",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "orbit-period-zero"), [])
            self.assertEqual(_findings(result, "orbit-period-computed-unguarded"), [])

    def test_unrelated_parameter_argument_is_not_flagged(self) -> None:
        # A plain passthrough parameter (no local division assignment) is not proven unsafe; do not claim it is.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "Derelict.java",
                "class Derelict { static void add(SectorEntityToken ship, SectorEntityToken focus, "
                "float startOrbitAngle, float daysToOrbit) { "
                "ship.setCircularOrbit(focus, startOrbitAngle, 3000f, daysToOrbit); } }",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "orbit-period-computed-unguarded"), [])
            self.assertEqual(_findings(result, "orbit-period-zero"), [])


class ModuleCaptainPersonalityRiskTests(unittest.TestCase):
    def test_hull_with_ship_with_modules_hint_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hulls" / "ship_data.csv",
                "name,id,hints\nAnomaly,fixture_module_hull,SHIP_WITH_MODULES\n",
            )
            result = scan_mod(root)
            findings = _findings(result, "module-captain-personality-risk")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertEqual(findings[0].confidence, "MEDIUM")
            self.assertIn("hull:fixture_module_hull", findings[0].evidence)

    def test_hull_without_hint_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id,hints\nDrone,fixture_hull,\n")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "module-captain-personality-risk"), [])


class SpawnedShipCaptainPersonalityRiskTests(unittest.TestCase):
    def test_spawned_ship_variant_is_review(self) -> None:
        # Real case: SEEKER hullmods spawn ART_*_hulk* debris ships on death.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "ART_organicHull.java",
                "class ART_organicHull { void onDeath() { "
                "engine.getFleetManager(0).spawnShipOrWing(\"ART_dimention_hulkA_variant\", loc, angle); } }",
            )
            result = scan_mod(root)
            findings = _findings(result, "spawned-ship-captain-personality-risk")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertIn("spawned:ART_dimention_hulkA_variant", findings[0].evidence)

    def test_spawned_wing_by_suffix_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "Plugin.java",
                "class Plugin { void onDeath() { "
                "engine.getFleetManager(0).spawnShipOrWing(\"talon_wing\", loc, angle); } }",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "spawned-ship-captain-personality-risk"), [])

    def test_spawned_wing_registered_in_wing_data_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "hulls" / "wing_data.csv",
                "id,variant,role,role desc,op cost\nfixture_fighter,v,FIGHTER,Heavy Fighter,5\n",
            )
            _write(
                root / "src" / "Plugin.java",
                "class Plugin { void onDeath() { "
                "engine.getFleetManager(0).spawnFleetMember(\"fixture_fighter\", loc, angle, 1f); } }",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "spawned-ship-captain-personality-risk"), [])

    def test_non_literal_spawn_argument_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "src" / "Plugin.java",
                "class Plugin { void onDeath(FleetMemberAPI member) { "
                "Global.getCombatEngine().getFleetManager(1).spawnFleetMember(member, loc, 270f, 1f); } }",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "spawned-ship-captain-personality-risk"), [])


class ModInfoTriageBannerTests(unittest.TestCase):
    def test_broken_variant_spelling_in_name_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"broke","name":"(BROEKN MAYBE) Broken Star"}')
            result = scan_mod(root)
            findings = _findings(result, "mod-info-triage-banner")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertIn("field:name", findings[0].evidence)

    def test_needs_to_be_updated_in_description_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "mod_info.json",
                '{"id":"fixture","name":"Fixture","description":"NEEDS TO BE UPDATED for 0.98a"}',
            )
            result = scan_mod(root)
            findings = _findings(result, "mod-info-triage-banner")
            self.assertEqual(len(findings), 1)
            self.assertIn("field:description", findings[0].evidence)

    def test_clean_metadata_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture Mod","author":"Someone"}')
            result = scan_mod(root)
            self.assertEqual(_findings(result, "mod-info-triage-banner"), [])

    def test_ordinary_word_broken_in_real_name_is_not_flagged(self) -> None:
        # Regression: the cleaned-up real name "Broken Star" must not read as a banner.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"broke","name":"Broken Star"}')
            result = scan_mod(root)
            self.assertEqual(_findings(result, "mod-info-triage-banner"), [])

    def test_parenthesised_lowercase_and_all_caps_banners_are_flagged(self) -> None:
        for name in ("(broken maybe) Fixture", "BROKEN 0.65 Fixture"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _write(root / "mod_info.json", '{"id":"fixture","name":"%s"}' % name)
                result = scan_mod(root)
                self.assertEqual(len(_findings(result, "mod-info-triage-banner")), 1)


class CommentedCodeIsIgnoredTests(unittest.TestCase):
    """Regression: a commented-out setCircularOrbit block in Arkgneisis's procgen generator was flagged."""

    def test_commented_orbit_calls_are_ignored_but_real_call_still_flagged(self) -> None:
        source = "\n".join([
            "public class Fixture {",
            "    void f(Object ship, Object focus, float r) {",
            "        //    float orbitDays = r / 10f;",
            "        //    ship.setCircularOrbit(focus, 0f, r, orbitDays);",
            "        /* ship.setCircularOrbit(focus, 0f, r, 0f); */",
            '        String url = "http://example.com//not-a-comment";',
            "        ship.setCircularOrbit(focus, 0f, r, 0f);",
            "    }",
            "}",
        ])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "scripts" / "Fixture.java", source)
            result = scan_mod(root)
            zero = _findings(result, "orbit-period-zero")
            self.assertEqual(len(zero), 1)
            self.assertIn("line:7", zero[0].evidence)
            self.assertEqual(_findings(result, "orbit-period-computed-unguarded"), [])

    def test_commented_spawn_call_is_ignored(self) -> None:
        source = "\n".join([
            "public class Fixture {",
            "    void f(Object engine) {",
            '        // engine.getFleetManager(0).spawnShipOrWing("fixture_hulk_variant", null, 0f);',
            "    }",
            "}",
        ])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "scripts" / "Fixture.java", source)
            result = scan_mod(root)
            self.assertEqual(_findings(result, "spawned-ship-captain-personality-risk"), [])


if __name__ == "__main__":
    unittest.main()
