"""Scanner robustness guards (ROADMAP-3 item 89, 2026-11-15).

1. No JDK: `helper_java_tools` falls back to bare `javac`/`java`; their FileNotFoundError ended a 316-workspace
   `finding-stats --scan` on its first mod. A scan must degrade (source-ast-unavailable), not crash.
2. Long lines: a new check's regex backtracked for 1,000 s of CPU on Angry Periphery 4's world-generation lines and
   stalled the archive scan. The whole scanner gets a time budget on a synthetic mod with very long lines, so the next
   such pattern fails here instead of in a sweep.
"""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

BUDGET_SECONDS = 60.0  # measured about 5 s on the reference machine; generous for CI


def _long_line_mod(root: Path) -> Path:
    mod = root / "mod"
    (mod / "data" / "scripts" / "world").mkdir(parents=True)
    (mod / "data" / "config").mkdir()
    (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    declarations = "        " + ", ".join(f"var{i} value{i} other{i}" for i in range(400)) + " = x;\n"
    calls = ('        system.addPlanet("p", star, "P", "terran", 30, 90, 3500, 180f); '
             + " ".join(f"a{i}.b{i}(c{i}, d{i});" for i in range(300)) + "\n")
    source = ("package data.scripts.world;\nimport com.fs.starfarer.api.*;\npublic class G implements SectorGeneratorPlugin {\n"
              + (declarations + calls) * 12 + "    public void generate(SectorAPI s) {\n    }\n}\n")
    (mod / "data" / "scripts" / "world" / "G.java").write_text(source, encoding="utf-8")
    (mod / "data" / "config" / "settings.json").write_text(
        "{" + ",".join(f'"k{i}": [1, 2, 3, "x y z"]' for i in range(3000)) + "}", encoding="utf-8")
    return mod


class ScanRobustnessTests(unittest.TestCase):
    def test_a_missing_jdk_degrades_instead_of_crashing(self) -> None:
        with resolved_temp_dir() as root:
            mod = _long_line_mod(root)
            with mock.patch("bridgeforge.bytecode.java_toolchain.helper_java_tools", return_value=("no-such-javac", "no-such-java")), \
                    mock.patch("bridgeforge.bytecode.java_ast._helper_directory", return_value=root / "ast-helper"):
                ids = {f.id for f in scan_mod(mod).findings}
        self.assertIn("source-ast-unavailable", ids)

    def test_the_whole_scan_stays_within_budget_on_very_long_lines(self) -> None:
        with resolved_temp_dir() as root:
            mod = _long_line_mod(root)
            started = time.monotonic()
            scan_mod(mod)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, BUDGET_SECONDS, f"scan took {elapsed:.1f} s: a check's pattern probably backtracks on long lines")

    def test_core_gated_checks_also_stay_within_budget(self) -> None:
        # The forwarding check that stalled the sweep only runs with a target core whose API jar it can read.
        from tests.support import javac_path
        from tests.test_jar_linkage import _compile, _jar

        javac = javac_path()
        if javac is None:
            self.skipTest("no JDK found")
        api = {"com/fs/starfarer/api/SectorGeneratorPlugin.java":
               "package com.fs.starfarer.api; public interface SectorGeneratorPlugin { void generate(Object s); }"}
        with resolved_temp_dir() as root:
            mod = _long_line_mod(root)
            _jar(_compile(javac, root / "api", api), root / "core" / "starfarer.api.jar")
            started = time.monotonic()
            scan_mod(mod, vanilla_core=root / "core")
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, BUDGET_SECONDS, f"scan with a core took {elapsed:.1f} s")


if __name__ == "__main__":
    unittest.main()
