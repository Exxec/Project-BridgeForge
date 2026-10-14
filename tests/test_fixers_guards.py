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


class OrbitPeriodGuardTests(unittest.TestCase):
    def test_wraps_a_computed_float_variable_at_the_call(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, BINGUS, "atheos_custom_system.java")
            self.assertEqual(_ids(root, ORBIT_ID), ["REVIEW"])
            _apply(root, ORBIT_ID)
            text = (root / "data/scripts/atheos_custom_system.java").read_text(encoding="utf-8")
            after = _ids(root, ORBIT_ID)
        self.assertIn("orbitRadius, Math.max(1f, (float) orbitDays));", text)
        self.assertEqual(after, [])

    def test_wraps_vacuums_int_variable_with_a_cast_and_is_idempotent(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, VACUUM, "VacuumSectorGen.java", "src/vacuum/world")
            self.assertEqual(_ids(root, ORBIT_ID), ["REVIEW"])
            _apply(root, ORBIT_ID)
            text = (root / "src/vacuum/world/VacuumSectorGen.java").read_text(encoding="utf-8")
            after = _ids(root, ORBIT_ID)
            with self.assertRaises(FixerError):
                compute_fix(root, ORBIT_ID, {})
        self.assertIn("setCircularOrbitPointingDown(planet, angle, orbitRadius, Math.max(1f, (float) orbitDays));", text)
        self.assertEqual(after, [])

    def test_wraps_an_inline_expression_in_parentheses(self) -> None:
        source = SPAN.replace("r,\n            r /\n            20f);", "r, r / 20f);")
        with resolved_temp_dir() as root:
            _mod(root, source, "Ring.java")
            _apply(root, ORBIT_ID)
            text = (root / "data/scripts/Ring.java").read_text(encoding="utf-8")
        self.assertIn("r, Math.max(1f, (float) (r / 20f)));", text)

    def test_refuses_an_expression_spanning_lines(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, SPAN, "Ring.java")
            self.assertEqual(_ids(root, ORBIT_ID), ["REVIEW"])
            with self.assertRaisesRegex(FixerError, "spans several lines"):
                compute_fix(root, ORBIT_ID, {})

    def test_refuses_a_loose_script_a_jar_already_shadows(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, VACUUM, "VacuumSectorGen.java", "data/scripts")
            with mock.patch("bridgeforge.scanner.loose_script_jar_shadowed_class", return_value="vacuum.world.VacuumSectorGen"):
                with self.assertRaisesRegex(FixerError, "shadowed"):
                    compute_fix(root, ORBIT_ID, {})


if __name__ == "__main__":
    unittest.main()
