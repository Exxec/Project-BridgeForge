"""decompile-jar (ROADMAP 44): a jar's classes as an editable source tree."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.decompile import decompile_jar, find_vineflower
from bridgeforge.java_toolchain import find_jdk


class DecompileJarTests(unittest.TestCase):
    def test_a_jar_becomes_a_source_tree(self) -> None:
        jdk = find_jdk()
        if jdk is None or find_vineflower() is None:
            self.skipTest("needs a JDK and In operation/_tools/vineflower*.jar")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "data").mkdir(parents=True)
            (root / "src" / "data" / "Mod.java").write_text("package data;\npublic class Mod { public int go() { return 3; } }\n", encoding="utf-8")
            subprocess.run([str(jdk.javac), "-d", str(root / "classes"), str(root / "src" / "data" / "Mod.java")], check=True)
            with zipfile.ZipFile(root / "m.jar", "w") as z:
                z.write(root / "classes" / "data" / "Mod.class", "data/Mod.class")
            result = decompile_jar(root / "m.jar", root / "out")
            text = (root / "out" / "data" / "Mod.java").read_text(encoding="utf-8")
        self.assertEqual((result["exit_code"], result["sources"]), (0, 1))
        self.assertIn("return 3;", text)
        with self.assertRaises(ValueError):
            decompile_jar(Path(directory) / "missing.jar", Path(directory) / "x")


if __name__ == "__main__":
    unittest.main()
