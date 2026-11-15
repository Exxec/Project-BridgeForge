"""jar-call-signature-changed (0.98.5a-RC3, 2026-11-15): a jar's call to a member that gained one trailing parameter is
rewritten in the bytecode, and the rewritten class runs on the new core with the JVM verifier on."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from bridgeforge.fixers import apply_fix, compute_fix
from bridgeforge.scanner import scan_mod
from tests.support import javac_path, resolved_temp_dir
from tests.test_jar_linkage import _compile, _jar

_PKG = "com/fs/starfarer/api/combat/"
OLD = {_PKG + "ShipAPI.java": "package com.fs.starfarer.api.combat; public interface ShipAPI { boolean isBeingIgnored(); }",
       _PKG + "ShipAIConfig.java": "package com.fs.starfarer.api.combat; public class ShipAIConfig { public ShipAIConfig() {} }"}
NEW = {_PKG + "ShipAPI.java": "package com.fs.starfarer.api.combat; public interface ShipAPI { boolean isBeingIgnored(boolean byAlly); }",
       _PKG + "ShipAIConfig.java": ("package com.fs.starfarer.api.combat; public class ShipAIConfig { public final boolean gotNull;"
                                    " public ShipAIConfig(ShipAPI ship) { gotNull = ship == null; } }")}
MOD = {"mod/Ai.java": ("package mod; import com.fs.starfarer.api.combat.*;\n"
                       "public class Ai { public static Object make() { int a = 1; Object c = a > 0 ? new ShipAIConfig() : null; return c; }\n"
                       "  public static boolean ignored(ShipAPI s) { return s.isBeingIgnored(); }\n"
                       "  public static void main(String[] x) {\n"
                       "    ShipAPI s = (ShipAPI) java.lang.reflect.Proxy.newProxyInstance(Ai.class.getClassLoader(), new Class[]{ShipAPI.class},\n"
                       "        (p, m, args) -> args != null && args.length == 1 && Boolean.FALSE.equals(args[0]) ? Boolean.TRUE : Boolean.FALSE);\n"
                       "    System.out.println(((ShipAIConfig) make()).getClass().getName() + \" \" + ignored(s)); } }")}


class JarCallRewriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.javac = javac_path()
        if self.javac is None:
            self.skipTest("no JDK found")

    def test_scan_fix_rescan_and_run_on_the_new_core(self) -> None:
        with resolved_temp_dir() as root:
            old_classes = _compile(self.javac, root / "oldbuild", OLD)
            new_classes = _compile(self.javac, root / "newbuild", NEW)
            _jar(old_classes, root / "old" / "starfarer.api.jar")
            _jar(new_classes, root / "new" / "starfarer.api.jar")
            mod = root / "mod"
            _jar(_compile(self.javac, root / "modbuild", MOD, classpath=old_classes), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "jars": ["jars/m.jar"]}), encoding="utf-8")
            before = scan_mod(mod, vanilla_core=root / "new").findings
            on_rc8 = [f.id for f in scan_mod(mod, vanilla_core=root / "old").findings if f.id.startswith("jar-")]
            apply_fix(compute_fix(mod, "jar-call-signature-changed", {"vanilla_core": root / "new"}))
            after = [(f.id, f.file, f.evidence) for f in scan_mod(mod, vanilla_core=root / "new").findings if f.id.startswith("jar-")]
            java = Path(self.javac).with_name("java.exe" if Path(self.javac).suffix else "java")
            sep = ";" if Path(self.javac).suffix else ":"
            run = subprocess.run([str(java), "-Xverify:all", "-cp", f"{mod / 'jars' / 'm.jar'}{sep}{new_classes}", "mod.Ai"],
                                 capture_output=True, text=True, check=False)
        changed = [f for f in before if f.id == "jar-call-signature-changed"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(len(changed[0].evidence), 2)
        self.assertNotIn("jar-linkage-unresolved", [f.id for f in before])  # the fixable calls are not reported twice
        self.assertEqual(on_rc8, [])  # gated: RC8 lacks the new forms
        self.assertEqual(after, [])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "com.fs.starfarer.api.combat.ShipAIConfig true")  # null and false were passed

    def test_without_the_target_core_the_fixer_refuses(self) -> None:
        from bridgeforge.fixers import FixerError

        with resolved_temp_dir() as root:
            (root / "mod_info.json").write_text('{"id": "m"}', encoding="utf-8")
            with self.assertRaises(FixerError):
                compute_fix(root, "jar-call-signature-changed", {})


if __name__ == "__main__":
    unittest.main()
