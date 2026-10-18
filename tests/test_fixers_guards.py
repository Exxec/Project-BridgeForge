"""B1 (ROADMAP item 73): system-generation-unguarded and orbit-period-computed-unguarded fixers.

Fixtures are excerpts of real files: zzz-Bingus-Sustem `original/` (atheos_custom_system.java) and Vacuum's
VacuumSectorGen.buildSystem as it stood before the agent's 2026-10-02 edit.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.fixers import SUPPORTED_FINDINGS, FixerError, compute_fix
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

SYSTEM_ID = "system-generation-unguarded"
ORBIT_ID = "orbit-period-computed-unguarded"

BINGUS = """package data.scripts;

import com.fs.starfarer.api.BaseModPlugin;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.*;

public class atheos_custom_system extends BaseModPlugin {
\t@Override
\tpublic void onGameLoad(boolean newGame) {
\t\tnew atheos_custom_system().build();
\t}

\tpublic void build() {

\t\tboolean presetConditions = true;

\t\tSectorAPI sector = Global.getSector();
\t\tStarSystemAPI system = sector.createStarSystem("Bingus");
\t\tsystem.setType(StarSystemType.BINARY_FAR);
\t}

\t// addDerelict taken from Galatia.java
\tprotected void addDerelict(StarSystemAPI system, SectorEntityToken focus, float orbitRadius) {
\t\tSectorEntityToken ship = system.addCustomEntity("w", "w", "wreck", "neutral");
\t\t
\t\tfloat orbitDays = orbitRadius / (10f + (float) Math.random() * 5f);
\t\tship.setCircularOrbit(focus, (float) Math.random() * 360f, orbitRadius, orbitDays);
\t}
}
"""

VACUUM = """package vacuum.world;

import com.fs.starfarer.api.campaign.*;

public class VacuumSectorGen {
    void buildSystem(StarSystemAPI system, PlanetAPI planet, int distance) {
        for (int k = 0; k < 3; k++) {
            int angle = (int) MathUtils.getRandomNumberInRange(1, 360);
            int orbitRadius = (int) planet.getRadius() + (int) MathUtils.getRandomNumberInRange(150, 400);
            int orbitDays = distance / 16 * (int) MathUtils.getRandomNumberInRange(1, 3);

            SectorEntityToken newStation = system.addCustomEntity("s", "s", "station", "neutral");
            newStation.setCircularOrbitPointingDown(planet, angle, orbitRadius, orbitDays);
        }
    }
}
"""

SPAN = """package data.scripts;

import com.fs.starfarer.api.campaign.*;

public class Ring {
    public void make(SectorEntityToken a, SectorEntityToken focus, float r) {
        a.setCircularOrbit(focus, 0f,
            r,
            r /
            20f);
    }
}
"""


def _mod(root: Path, source: str, name: str = "Gen.java", folder: str = "data/scripts") -> Path:
    (root / folder).mkdir(parents=True, exist_ok=True)
    (root / folder / name).write_bytes(source.encode())
    (root / "mod_info.json").write_text('{"id":"m","name":"m","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
    return root


def _apply(root: Path, finding_id: str) -> None:
    for change in compute_fix(root, finding_id, {}).changes:
        change.path.write_bytes(change.after)


def _ids(root: Path, finding_id: str) -> list[str]:
    return [f.classification for f in scan_mod(root).findings if f.id == finding_id]


class SystemGenerationGuardTests(unittest.TestCase):
    def test_supported_ids(self) -> None:
        self.assertIn(SYSTEM_ID, SUPPORTED_FINDINGS)
        self.assertIn(ORBIT_ID, SUPPORTED_FINDINGS)

    def test_guards_the_bingus_generator_and_the_finding_clears(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, BINGUS, "atheos_custom_system.java")
            self.assertEqual(_ids(root, SYSTEM_ID), ["REVIEW"])
            _apply(root, SYSTEM_ID)
            text = (root / "data/scripts/atheos_custom_system.java").read_text(encoding="utf-8")
            after = _ids(root, SYSTEM_ID)
        guard = 'if (com.fs.starfarer.api.Global.getSector().getStarSystem("Bingus") != null) return;'
        self.assertIn("\t\t" + guard, text)
        self.assertLess(text.index(guard), text.index("boolean presetConditions"))
        self.assertEqual(after, [])

    def test_second_run_computes_no_change(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, BINGUS, "atheos_custom_system.java")
            _apply(root, SYSTEM_ID)
            with self.assertRaises(FixerError):
                compute_fix(root, SYSTEM_ID, {})

    def test_uses_the_sector_parameter_when_the_method_has_one(self) -> None:
        source = BINGUS.replace("public void build() {", "public void build(SectorAPI sec) {").replace("build();", "build(Global.getSector());")
        with resolved_temp_dir() as root:
            _mod(root, source, "atheos_custom_system.java")
            _apply(root, SYSTEM_ID)
            text = (root / "data/scripts/atheos_custom_system.java").read_text(encoding="utf-8")
        self.assertIn('if (sec.getStarSystem("Bingus") != null) return;', text)

    def test_crlf_and_bom_survive(self) -> None:
        source = BINGUS.replace("\n", "\r\n").encode()
        with resolved_temp_dir() as root:
            _mod(root, "", "atheos_custom_system.java")
            (root / "data/scripts/atheos_custom_system.java").write_bytes(b"\xef\xbb\xbf" + source)
            _apply(root, SYSTEM_ID)
            data = (root / "data/scripts/atheos_custom_system.java").read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        self.assertIn(b'return; // BridgeForge: do not create the system twice\r\n', data)

    def test_refuses_a_non_void_method(self) -> None:
        source = BINGUS.replace("public void build()", "public boolean build()").replace("system.setType(StarSystemType.BINARY_FAR);", "return true;")
        with resolved_temp_dir() as root:
            _mod(root, source, "atheos_custom_system.java")
            with self.assertRaisesRegex(FixerError, "does not return void"):
                compute_fix(root, SYSTEM_ID, {})

    def test_refuses_when_the_method_already_looks_the_system_up(self) -> None:
        source = BINGUS.replace("\t\tboolean presetConditions = true;", '\t\tStarSystemAPI old = Global.getSector().getStarSystem("Bingus");')
        with resolved_temp_dir() as root:
            _mod(root, source, "atheos_custom_system.java")
            # The scanner reads an un-compared lookup as unguarded, so the finding is still raised; the fixer refuses.
            with self.assertRaisesRegex(FixerError, "already looks the system up"):
                compute_fix(root, SYSTEM_ID, {})

    def test_refuses_a_name_that_is_not_one_literal_on_the_flagged_line(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, BINGUS, "atheos_custom_system.java")
            options = {"scan_findings": [{"id": SYSTEM_ID, "file": "data/scripts/atheos_custom_system.java",
                                           "evidence": ["data/scripts/atheos_custom_system.java:3: Bingus (called from onGameLoad)"]}]}
            with self.assertRaisesRegex(FixerError, "not called with this one string literal"):
                compute_fix(root, SYSTEM_ID, options)


    def test_refuses_a_method_that_also_does_unrelated_setup(self) -> None:
        for extra in ("		sector.getFaction(\"pirates\").setRelationship(\"player\", -1f);",
                      "		Global.getSector().registerPlugin(null);",
                      "		Global.getSector().getMemoryWithoutUpdate().set(\"$x\", true);"):
            with self.subTest(extra=extra):
                source = BINGUS.replace("		system.setType(StarSystemType.BINARY_FAR);", extra)
                with resolved_temp_dir() as root:
                    _mod(root, source, "atheos_custom_system.java")
                    with self.assertRaisesRegex(FixerError, "initialization an early return would skip"):
                        compute_fix(root, SYSTEM_ID, {})

    def test_refuses_a_method_that_creates_two_systems(self) -> None:
        source = BINGUS.replace("		system.setType(StarSystemType.BINARY_FAR);", '		StarSystemAPI second = sector.createStarSystem("Other");')
        with resolved_temp_dir() as root:
            _mod(root, source, "atheos_custom_system.java")
            with self.assertRaisesRegex(FixerError, "more than one star system"):
                compute_fix(root, SYSTEM_ID, {})


PROVEN = """package data.scripts;

import com.fs.starfarer.api.campaign.*;

public class Ring {
    public void make(SectorEntityToken a, SectorEntityToken focus, float r) {
        float days = (float) Math.random() * 30f / 4f - 3f;
        a.setCircularOrbit(focus, 0f, r, days);
    }
}
"""


def _ring(expression: str, declaration: str = "float days") -> str:
    return PROVEN.replace("float days = (float) Math.random() * 30f / 4f - 3f;", f"{declaration} = {expression};")


class OrbitPeriodGuardTests(unittest.TestCase):
    def _fix(self, source: str) -> str:
        with resolved_temp_dir() as root:
            _mod(root, source, "Ring.java")
            self.assertEqual(_ids(root, ORBIT_ID), ["REVIEW"])
            _apply(root, ORBIT_ID)
            text = (root / "data/scripts/Ring.java").read_text(encoding="utf-8")
            self.assertEqual(_ids(root, ORBIT_ID), [])
            with self.assertRaises(FixerError):
                compute_fix(root, ORBIT_ID, {})
        return text

    def _refusal(self, source: str, pattern: str) -> None:
        with resolved_temp_dir() as root:
            _mod(root, source, "Ring.java")
            self.assertEqual(_ids(root, ORBIT_ID), ["REVIEW"])
            with self.assertRaisesRegex(FixerError, pattern):
                compute_fix(root, ORBIT_ID, {})

    def test_wraps_a_proven_bounded_expression_whose_range_includes_negatives(self) -> None:
        text = self._fix(PROVEN)
        self.assertIn("a.setCircularOrbit(focus, 0f, r, Math.max(1f, (float) days));", text)

    def test_crlf_survives(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, PROVEN.replace("\n", "\r\n"), "Ring.java")
            _apply(root, ORBIT_ID)
            data = (root / "data/scripts/Ring.java").read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_wraps_an_inline_expression_in_parentheses(self) -> None:
        source = PROVEN.replace("float days = (float) Math.random() * 30f / 4f - 3f;\n        ", "").replace("r, days", "r, Math.random() * 8f / 2f - 1f")
        text = self._fix(source)
        self.assertIn("r, Math.max(1f, (float) (Math.random() * 8f / 2f - 1f))", text)

    def test_refuses_the_real_vacuum_case_whose_range_comes_from_a_library_call(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, VACUUM, "VacuumSectorGen.java", "data/scripts")
            self.assertEqual(_ids(root, ORBIT_ID), ["REVIEW"])
            with self.assertRaisesRegex(FixerError, "not provably finite"):
                compute_fix(root, ORBIT_ID, {})

    def test_refuses_jar_sources_and_hash_folders_for_both_fixers(self) -> None:
        for folder, pattern in (("src/vacuum/world", "jar's source tree"), ("jars/src/x", "jar's source tree"), ("data/#Under construction", "'#' folder")):
            with self.subTest(folder=folder), resolved_temp_dir() as root:
                _mod(root, PROVEN, "Ring.java", folder)
                with self.assertRaisesRegex(FixerError, pattern):
                    compute_fix(root, ORBIT_ID, {})
                _mod(root, BINGUS, "atheos_custom_system.java", folder)
                with self.assertRaisesRegex(FixerError, pattern):
                    compute_fix(root, SYSTEM_ID, {})

    def test_refuses_the_real_bingus_case_with_a_float_parameter(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, BINGUS, "atheos_custom_system.java")
            with self.assertRaisesRegex(FixerError, "orbitRadius.*parameter, field or reassigned"):
                compute_fix(root, ORBIT_ID, {})

    def test_refuses_nan_and_infinity_producing_divisors(self) -> None:
        for expression in ("0f / 0f", "1f / 0f", "Math.random() / (Math.random() - 0.5f)", "7f / (Math.random() * 0f)"):
            with self.subTest(expression=expression):
                self._refusal(_ring(expression), "divisor may be zero")

    def test_refuses_a_lower_bound_that_needs_no_clamp(self) -> None:
        self._refusal(_ring("10f + Math.random() * 5f / 2f"), "does not justify a one-day minimum")

    def test_refuses_side_effects_and_unknown_calls(self) -> None:
        for expression in ("counter++ / 4f", "(counter = 3) / 4f", "helper() / 4f", "Math.sqrt(2f) / 4f", "a.getRadius() / 4f"):
            with self.subTest(expression=expression):
                self._refusal(_ring(expression), "not provably finite")

    def test_refuses_a_variable_that_is_reassigned(self) -> None:
        source = PROVEN.replace("        a.setCircularOrbit", "        days = r;\n        a.setCircularOrbit")
        self._refusal(source, "reassigned variable")

    def test_refuses_an_expression_spanning_lines(self) -> None:
        self._refusal(SPAN.replace("r /\n            20f", "(float) Math.random() /\n            20f"), "spans several lines")

    def test_refuses_a_loose_script_a_jar_already_shadows(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, PROVEN, "Ring.java")
            with mock.patch("bridgeforge.scanner.loose_script_jar_shadowed_class", return_value="data.scripts.Ring"):
                with self.assertRaisesRegex(FixerError, "shadowed"):
                    compute_fix(root, ORBIT_ID, {})


if __name__ == "__main__":
    unittest.main()
