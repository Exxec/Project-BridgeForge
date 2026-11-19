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

    def test_report_success_gets_the_shared_level_plus_one_and_verifies(self) -> None:
        """95.14: RC7's PersonBountyEventData.reportSuccess(int completedLevel) replaced RC8's reportSuccess(); the rule passes
        getLevel() + 1, which counts one success as RC8 did. The rewritten class runs under the verifier."""
        pkg = "com/fs/starfarer/api/impl/campaign/shared/"
        head = "package com.fs.starfarer.api.impl.campaign.shared; public class PersonBountyEventData {"
        old = {pkg + "PersonBountyEventData.java": head + " public int getLevel() { return 3; } public void reportSuccess() {} }"}
        new = {pkg + "PersonBountyEventData.java": head + " public static int got = -99; public int getLevel() { return 3; }"
                                                          " public void reportSuccess(int completedLevel) { got = completedLevel; } }"}
        mod_source = {"mod/Bounty.java": ("package mod; import com.fs.starfarer.api.impl.campaign.shared.PersonBountyEventData;\n"
                                          "public class Bounty { static PersonBountyEventData shared() { return new PersonBountyEventData(); }\n"
                                          "  public static void main(String[] x) throws Exception { shared().reportSuccess();\n"
                                          "    System.out.println(PersonBountyEventData.class.getField(\"got\").getInt(null)); } }")}
        with resolved_temp_dir() as root:
            old_classes = _compile(self.javac, root / "oldbuild", old)
            new_classes = _compile(self.javac, root / "newbuild", new)
            _jar(old_classes, root / "old" / "starfarer.api.jar")
            _jar(new_classes, root / "new" / "starfarer.api.jar")
            mod = root / "mod"
            _jar(_compile(self.javac, root / "modbuild", mod_source, classpath=old_classes), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "jars": ["jars/m.jar"]}), encoding="utf-8")
            before = [f.id for f in scan_mod(mod, vanilla_core=root / "new").findings if f.id.startswith("jar-")]
            on_rc8 = [f.id for f in scan_mod(mod, vanilla_core=root / "old").findings if f.id.startswith("jar-")]
            apply_fix(compute_fix(mod, "jar-call-signature-changed", {"vanilla_core": root / "new"}))
            after = [f.id for f in scan_mod(mod, vanilla_core=root / "new").findings if f.id.startswith("jar-")]
            java = Path(self.javac).with_name("java.exe" if Path(self.javac).suffix else "java")
            sep = ";" if Path(self.javac).suffix else ":"
            run = subprocess.run([str(java), "-Xverify:all", "-cp", f"{mod / 'jars' / 'm.jar'}{sep}{new_classes}", "mod.Bounty"],
                                 capture_output=True, text=True, check=False)
        self.assertEqual(before, ["jar-call-signature-changed"])
        self.assertEqual(on_rc8, [])  # gated: the old API has reportSuccess() only
        self.assertEqual(after, [])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "4")  # getLevel() 3 + 1

    def test_a_getter_argument_needs_a_no_argument_instance_call(self) -> None:
        from bridgeforge.bytecode.bytecode import append_constant_argument

        with resolved_temp_dir() as root:
            source = root / "A.class"
            source.write_bytes(b"\xca\xfe\xba\xbe")
            for constant in ("getter:getLevel:()J:1", "getter::()I:1", "getter:getLevel:()I:1000", "getter:a;b:()I:1"):
                with self.subTest(constant=constant), self.assertRaises(ValueError):
                    append_constant_argument(source, root / "B.class", "o/O", "m", "()V", 182, "(I)V", constant, 1)

    def test_without_the_target_core_the_fixer_refuses(self) -> None:
        from bridgeforge.fixers import FixerError

        with resolved_temp_dir() as root:
            (root / "mod_info.json").write_text('{"id": "m"}', encoding="utf-8")
            with self.assertRaises(FixerError):
                compute_fix(root, "jar-call-signature-changed", {})


if __name__ == "__main__":
    unittest.main()
