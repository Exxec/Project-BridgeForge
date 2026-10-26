"""`delegate-method`: replace method bodies with a call into a helper class (Exotica 2.1.1-RC4, 2026-10-26)."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
import zipfile
from pathlib import Path

from bridgeforge.bytecode.bytecode import BytecodeUnavailable
from bridgeforge.delegate_method import delegate_methods, load_spec
from bridgeforge.bytecode.java_toolchain import find_jdk
from tests.support import resolved_temp_dir

TARGET = (
    "package p;\n"
    "public class Target {\n"
    "    public int twice(int x) { return x * 2; }\n"
    "    public static String tag(String s) { return \"old:\" + s; }\n"
    "    public int keep() { return 7; }\n"
    "}\n"
)
FIX = (
    "package p;\n"
    "public final class Fix {\n"
    "    public static int twice(Target self, int x) { return x * 3; }\n"
    "    public static String tag(String s) { return \"fixed:\" + s; }\n"
    "}\n"
)
MAIN = (
    "public class Main {\n"
    "    public static void main(String[] a) {\n"
    "        p.Target t = new p.Target();\n"
    "        System.out.println(t.twice(5) + \" \" + p.Target.tag(\"x\") + \" \" + t.keep());\n"
    "    }\n"
    "}\n"
)


def _spec(path: Path, **override: str) -> Path:
    rows = [{"owner": "p/Target", "name": "twice", "descriptor": "(I)I", "helper_owner": "p/Fix", "helper_name": "twice", "reason": "test"},
            {"owner": "p/Target", "name": "tag", "descriptor": "(Ljava/lang/String;)Ljava/lang/String;", "helper_owner": "p/Fix",
             "helper_name": "tag", "reason": "test"}]
    rows[0].update(override)
    path.write_text(json.dumps({"schema_version": 1, "kind": "bridgeforge-delegate-methods", "delegations": rows}), encoding="utf-8")
    return path


class DelegateMethodTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jdk = find_jdk()
        if self.jdk is None or not self.jdk.jar.is_file():
            self.skipTest("needs a JDK with the jar tool")

    def _build(self, root: Path) -> tuple[Path, Path]:
        (root / "src" / "p").mkdir(parents=True)
        (root / "src" / "p" / "Target.java").write_text(TARGET, encoding="utf-8")
        (root / "src" / "p" / "Fix.java").write_text(FIX, encoding="utf-8")
        javac = str(self.jdk.javac)
        subprocess.run([javac, "--release", "17", "-d", str(root / "classes"), str(root / "src" / "p" / "Target.java")], check=True)
        subprocess.run([javac, "--release", "17", "-cp", str(root / "classes"), "-d", str(root / "helper"), str(root / "src" / "p" / "Fix.java")], check=True)
        jar = root / "mod.jar"
        with zipfile.ZipFile(jar, "w") as archive:
            archive.write(root / "classes" / "p" / "Target.class", "p/Target.class")
            archive.writestr("README.txt", "kept")
        return jar, root / "helper"

    def test_only_the_named_methods_change_and_the_jar_runs(self) -> None:
        with resolved_temp_dir() as root:
            jar, helper = self._build(root)
            before = jar.read_bytes()
            result = delegate_methods(jar, _spec(root / "spec.json"), helper, root / "out" / "mod.jar")
            (root / "Main.java").write_text(MAIN, encoding="utf-8")
            subprocess.run([str(self.jdk.javac), "-cp", str(root / "out" / "mod.jar"), "-d", str(root / "main"), str(root / "Main.java")], check=True)
            classpath = os.pathsep.join([str(root / "main"), str(root / "out" / "mod.jar")])
            ran = subprocess.run([str(self.jdk.java), "-Xverify:all", "-cp", classpath, "Main"], capture_output=True, text=True, check=False)
            names = zipfile.ZipFile(root / "out" / "mod.jar").namelist()
            unchanged_input = jar.read_bytes() == before
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["classes"][0]["changed"], ["tag(Ljava/lang/String;)Ljava/lang/String;", "twice(I)I"])
        self.assertEqual(ran.stdout.strip(), "15 fixed:x 7", ran.stderr)
        self.assertIn("p/Fix.class", names)
        self.assertIn("README.txt", names)
        self.assertTrue(unchanged_input)

    def test_refusals(self) -> None:
        with resolved_temp_dir() as root:
            jar, helper = self._build(root)
            existing = root / "exists.jar"
            existing.write_bytes(b"")
            with self.assertRaises(ValueError):
                delegate_methods(jar, _spec(root / "a.json"), helper, existing)
            with self.assertRaises(ValueError):
                delegate_methods(jar, _spec(root / "b.json"), helper, jar)
            with self.assertRaises(ValueError):
                load_spec(_spec(root / "c.json", reason=""))
            with self.assertRaises(ValueError):
                load_spec(_spec(root / "d.json", name="<init>"))
            with self.assertRaises(ValueError):
                delegate_methods(jar, _spec(root / "e.json", helper_owner="p/Missing"), helper, root / "o1.jar")
            with self.assertRaises(BytecodeUnavailable):
                delegate_methods(jar, _spec(root / "f.json", name="absent"), helper, root / "o2.jar")
            self.assertFalse((root / "o2.jar").exists())


if __name__ == "__main__":
    unittest.main()
