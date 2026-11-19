"""forwarding-class-method-missing (0.98.5a-RC3, 2026-11-15): DroneLib's dl_DroneAPI forwards ShipAPI to a drone and
lacked the six methods 0.98.5a added. The fixer appends forwards and drops an @Override the target no longer backs."""
from __future__ import annotations

import json
import subprocess
import unittest

from bridgeforge.fixers import apply_fix, compute_fix
from bridgeforge.forwarding_methods import forwarding_source
from bridgeforge.scanner import scan_mod
from tests.support import javac_path, resolved_temp_dir
from tests.test_jar_linkage import _compile, _jar

NEW = {"com/fs/starfarer/api/combat/ShipAPI.java": (
    "package com.fs.starfarer.api.combat; public interface ShipAPI { float getFlux(); void setFlux(float f); int getId();"
    " boolean isBeingIgnored(boolean byAlly); java.util.List getCommands2(); void setWasHulk(boolean b); int[] slots(String[] a, long b); }")}
DRONE = ("package data.scripts;\nimport com.fs.starfarer.api.combat.*;\n\n"
         "public class Drone implements ShipAPI {\n    private final ShipAPI drone;\n    public Drone(ShipAPI d) { drone = d; }\n"
         "    @Override\n    public float getFlux() { return drone.getFlux(); }\n"
         "    @Override\n    public void setFlux(float f) { drone.setFlux(f); }\n"
         "    @Override\n    public int getId() { return drone.getId(); }\n"
         "    @Override\n    public boolean isBeingIgnored() { return drone.getFlux() > 0; }\n"
         "    @Override\n    public String toString() { return drone.toString() + drone.getId(); }\n"
         "    @Override\n    public int[] slots(String[] a, long b) { return drone.slots(a, b); }\n}\n")


class ForwardingMethodTests(unittest.TestCase):
    def test_render_of_void_array_and_reference_types(self) -> None:
        self.assertEqual(forwarding_source("slots", "([Ljava/lang/String;J)[I", "d"),
                         "    public int[] slots(java.lang.String[] a0, long a1) { return d.slots(a0, a1); }")
        self.assertEqual(forwarding_source("setWasHulk", "(Z)V", "d"), "    public void setWasHulk(boolean a0) { d.setWasHulk(a0); }")

    def test_scan_fix_and_compile_on_the_new_core(self) -> None:
        javac = javac_path()
        if javac is None:
            self.skipTest("no JDK found")
        with resolved_temp_dir() as root:
            api = _compile(javac, root / "api", NEW)
            _jar(api, root / "core" / "starfarer.api.jar")
            mod = root / "mod"
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "mod_info.json").write_text(json.dumps({"id": "m"}), encoding="utf-8")
            source = mod / "data" / "scripts" / "Drone.java"
            source.write_text(DRONE, encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=root / "core").findings if f.id == "forwarding-class-method-missing"]
            apply_fix(compute_fix(mod, "forwarding-class-method-missing", {"vanilla_core": root / "core"}))
            text = source.read_text(encoding="utf-8")
            again = [f for f in scan_mod(mod, vanilla_core=root / "core").findings if f.id == "forwarding-class-method-missing"]
            built = subprocess.run([javac, "-encoding", "UTF-8", "-d", str(root / "out"), "-cp", str(api), str(source)], capture_output=True, text=True, check=False)
        self.assertEqual(found[0].evidence, ["getCommands2()Ljava/util/List;", "isBeingIgnored(Z)Z", "setWasHulk(Z)V"])
        self.assertIn("public boolean isBeingIgnored(boolean a0) { return drone.isBeingIgnored(a0); }", text)
        self.assertIn("    public boolean isBeingIgnored() {", text)  # kept, but no longer @Override
        self.assertNotIn("@Override\n    public boolean isBeingIgnored()", text)
        self.assertIn("@Override\n    public String toString()", text)  # Object's: kept
        self.assertEqual(again, [])
        self.assertEqual(built.returncode, 0, built.stderr)

    def test_long_generation_lines_do_not_backtrack(self) -> None:
        # Angry Periphery 4 (2026-11-15): the scan spent 1,000 s CPU in this check on 300-line world-generation scripts.
        import time

        from bridgeforge.forwarding_methods import missing_forwards

        line = "        " + ", ".join(f"var{i} value{i} other{i}" for i in range(400)) + " = x;\n"
        text = "public class G implements SectorGeneratorPlugin {\n" + line * 40 + "    public void generate(SectorAPI s) {\n    }\n}\n"
        started = time.monotonic()
        missing_forwards(text, {})
        self.assertLess(time.monotonic() - started, 2.0)

    def test_without_a_delegate_or_a_core_nothing_is_reported(self) -> None:
        with resolved_temp_dir() as root:
            (root / "mod_info.json").write_text('{"id": "m"}', encoding="utf-8")
            (root / "D.java").write_text(DRONE, encoding="utf-8")
            self.assertEqual([f for f in scan_mod(root).findings if f.id == "forwarding-class-method-missing"], [])


if __name__ == "__main__":
    unittest.main()
