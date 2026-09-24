from __future__ import annotations

import io
import json
import shutil
import subprocess
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.fixers import _LEGACY_FLEETS_CALL, _rewrite_add_orbital_station_span, _rewrite_add_planet_span
from bridgeforge.revenantlib_contract import CONTRACT, RevenantLibCheckError, check_revenantlib
from tests.support import resolved_temp_dir

# Hand-written stand-ins for the three public API types the contract names; not game code.
API_STUBS = {
    "com/fs/starfarer/api/campaign/CampaignFleetAPI.java": "package com.fs.starfarer.api.campaign; public interface CampaignFleetAPI {}",
    "com/fs/starfarer/api/campaign/SectorEntityToken.java": "package com.fs.starfarer.api.campaign; public interface SectorEntityToken {}",
    "com/fs/starfarer/api/campaign/PlanetAPI.java": "package com.fs.starfarer.api.campaign; public interface PlanetAPI extends SectorEntityToken {}",
    "com/fs/starfarer/api/campaign/LocationAPI.java": "package com.fs.starfarer.api.campaign; public interface LocationAPI {}",
}
IMPORTS = "import com.fs.starfarer.api.campaign.*;"
FLEETS = "package bf.legacyfleets; " + IMPORTS + """
public class LegacyFleets {
    public static synchronized CampaignFleetAPI createFleet(String factionId, String fleetTypeId) { return null; }
}"""
WORLD = "package bf.legacyworld; " + IMPORTS + """
public class LegacyWorld {
    public static PlanetAPI addPlanet(LocationAPI system, SectorEntityToken focus, String name, String type,
            float angle, float radius, float orbitRadius, float orbitDays) { return null; }
    public static SectorEntityToken addOrbitalStation(LocationAPI system, SectorEntityToken focus, float angle,
            float orbitRadius, float orbitDays, String name, String factionId) { return null; }
    private static String sanitize(String s) { return s; }
}"""


def _count_args(call: str) -> int:
    inner = call[call.index("(") + 1:call.rindex(")")]
    depth, count = 0, 1
    for char in inner:
        depth += char in "(["
        depth -= char in ")]"
        count += char == "," and depth == 0
    return count


def _param_count(descriptor: str) -> int:
    params, count, pos = descriptor[1:descriptor.index(")")], 0, 0
    while pos < len(params):
        while params[pos] == "[":
            pos += 1
        pos = params.index(";", pos) + 1 if params[pos] == "L" else pos + 1
        count += 1
    return count


class FixerContractTests(unittest.TestCase):
    """The fixer's rewritten call must pass exactly the arguments the pinned RevenantLib method takes."""

    def test_rewrites_match_the_contract_arity(self):
        arity = {name: _param_count(descriptor) for _, name, descriptor, _ in CONTRACT}
        planet = _rewrite_add_planet_span('system.addPlanet(star, "Aurum", "gas_giant", 30f, 300f, 4000f, max(1, days))')
        station = _rewrite_add_orbital_station_span('system.addOrbitalStation(planet, 45f, 300f, 50f, "Port", "pirates")')
        self.assertTrue(planet.startswith("bf.legacyworld.LegacyWorld.addPlanet(system, "))
        self.assertEqual(_count_args(planet), arity["addPlanet"])
        self.assertEqual(_count_args(station), arity["addOrbitalStation"])
        self.assertEqual(_LEGACY_FLEETS_CALL, "bf.legacyfleets.LegacyFleets.createFleet(")
        self.assertEqual(arity["createFleet"], 2)  # the 0.6 call's own two arguments are carried through unchanged


class RevenantLibJarTests(unittest.TestCase):
    """Stand-in RevenantLib builds compiled by a real javac; skipped cleanly when no JDK is on PATH."""

    def setUp(self):
        self.javac = shutil.which("javac")
        if self.javac is None:
            self.skipTest("no javac on PATH")

    def _build(self, root: Path, sources: dict[str, str], jar_sources: dict[str, str] | None = None) -> Path:
        """A RevenantLib-shaped mod folder: working/{mod_info.json, src/, jars/RevenantLib.jar}."""
        mod = root / "working"
        src, api, out = mod / "src", root / "api-src", root / "classes"
        for base, files in ((api, API_STUBS), (src, sources)):
            for relative, text in files.items():
                (base / relative).parent.mkdir(parents=True, exist_ok=True)
                (base / relative).write_text(text, encoding="utf-8")
        compiled = jar_sources if jar_sources is not None else sources
        build = root / "build-src"
        for relative, text in compiled.items():
            (build / relative).parent.mkdir(parents=True, exist_ok=True)
            (build / relative).write_text(text, encoding="utf-8")
        files = [str(p) for p in list(api.rglob("*.java")) + list(build.rglob("*.java"))]
        completed = subprocess.run([self.javac, "--release", "17", "-d", str(out), *files], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        jar = mod / "jars" / "RevenantLib.jar"
        jar.parent.mkdir(parents=True)
        with zipfile.ZipFile(jar, "w") as archive:
            for path in sorted(out.rglob("*.class")):
                if not path.relative_to(out).as_posix().startswith("com/"):
                    archive.write(path, path.relative_to(out).as_posix())
        (mod / "mod_info.json").write_text(json.dumps({"id": "revenantlib", "jars": ["jars/RevenantLib.jar"]}), encoding="utf-8")
        return root

    SOURCES = {"bf/legacyfleets/LegacyFleets.java": FLEETS, "bf/legacyworld/LegacyWorld.java": WORLD}

    def test_matching_build_passes_from_repo_root_mod_folder_or_jar(self):
        with resolved_temp_dir() as root:
            self._build(root, self.SOURCES)
            for target in (root, root / "working"):
                result = check_revenantlib(target)
                self.assertEqual(result["status"], "PASS", result)
                self.assertTrue(result["jar_vs_source"]["checked"])
            jar_only = check_revenantlib(root / "working" / "jars" / "RevenantLib.jar")
            self.assertEqual(jar_only["status"], "PASS")
            self.assertFalse(jar_only["jar_vs_source"]["checked"])

    def test_renamed_resignatured_or_instance_methods_fail(self):
        broken = WORLD.replace("public static PlanetAPI addPlanet", "public PlanetAPI addPlanet").replace(
            "float orbitRadius, float orbitDays, String name, String factionId)", "float orbitRadius, String name, String factionId)")
        with resolved_temp_dir() as root:
            self._build(root, {"bf/legacyworld/LegacyWorld.java": broken})
            result = check_revenantlib(root)
        by_name = {entry["call"].split("(")[0].rsplit(".", 1)[-1]: entry for entry in result["contract"]}
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(by_name["createFleet"]["detail"], "class missing from the jar")
        self.assertIn("not public static", by_name["addPlanet"]["detail"])
        self.assertIn("same name: SectorEntityToken addOrbitalStation(LocationAPI, SectorEntityToken, float, float, String, String)",
                      by_name["addOrbitalStation"]["detail"])

    def test_stale_jar_is_caught(self):
        extra = {**self.SOURCES, "bf/legacyworld/NewHelper.java": "package bf.legacyworld; public class NewHelper {}"}
        with resolved_temp_dir() as root:
            self._build(root, extra, jar_sources=self.SOURCES)
            result = check_revenantlib(root)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["jar_vs_source"]["sources_without_class"], ["bf/legacyworld/NewHelper"])
        self.assertTrue(all(entry["status"] == "PASS" for entry in result["contract"]))

    def test_cli_reports_and_exits_nonzero_on_failure(self):
        with resolved_temp_dir() as root:
            self._build(root, {"bf/legacyfleets/LegacyFleets.java": FLEETS})
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["revenantlib-check", str(root)])
        self.assertEqual(code, 1)
        self.assertIn("PASS bf.legacyfleets.LegacyFleets.createFleet(String, String)", stdout.getvalue())
        self.assertIn("FAIL bf.legacyworld.LegacyWorld.addPlanet(", stdout.getvalue())


class LocateTests(unittest.TestCase):
    def test_folder_must_declare_exactly_one_existing_jar(self):
        with resolved_temp_dir() as root:
            with self.assertRaises(RevenantLibCheckError):
                check_revenantlib(root)
            (root / "mod_info.json").write_text('{"id": "revenantlib", "jars": ["jars/missing.jar"]}', encoding="utf-8")
            with self.assertRaises(RevenantLibCheckError):
                check_revenantlib(root)
            (root / "mod_info.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(RevenantLibCheckError):
                check_revenantlib(root)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["revenantlib-check", str(root)]), 2)


if __name__ == "__main__":
    unittest.main()
